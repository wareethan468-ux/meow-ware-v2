import os
import secrets
import string
from datetime import datetime, timedelta, timezone
import discord
from discord import app_commands
from discord.ext import commands
import httpx
from dotenv import load_dotenv

load_dotenv()

# Configuration
TOKEN = os.getenv("DISCORD_TOKEN", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://rdrtqrvozedfvcskwtna.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY", "")
ADMIN_ID = int(os.getenv("ADMIN_USER_ID", "1244476245249626133"))

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def generate_key_string(prefix="MEOW"):
    chars = string.ascii_uppercase + string.digits
    part1 = ''.join(secrets.choice(chars) for _ in range(4))
    part2 = ''.join(secrets.choice(chars) for _ in range(4))
    part3 = ''.join(secrets.choice(chars) for _ in range(4))
    return f"{prefix}-{part1}-{part2}-{part3}"


# ─── Supabase Database Helpers ───
async def get_user_cooldown(discord_id: str):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.get(
                f"{SUPABASE_URL}/rest/v1/user_cooldowns?discord_id=eq.{discord_id}&select=*",
                headers=HEADERS
            )
            if res.status_code == 200:
                data = res.json()
                return data[0] if data else None
            else:
                print(f"[!] get_user_cooldown HTTP {res.status_code}: {res.text}")
        except Exception as e:
            print(f"[!] get_user_cooldown exception: {e}")
    return None


async def set_user_cooldown(discord_id: str, key_code: str):
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "discord_id": discord_id,
        "last_generated": now_iso,
        "last_key_code": key_code
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.post(
                f"{SUPABASE_URL}/rest/v1/user_cooldowns",
                headers={**HEADERS, "Prefer": "resolution=merge-duplicates"},
                json=payload
            )
            print(f"[+] set_user_cooldown for {discord_id} -> {res.status_code}")
        except Exception as e:
            print(f"[!] set_user_cooldown exception: {e}")


async def insert_key(key_code: str, key_type: str, created_by: str, duration_hours: int, expires_at_iso: str = None):
    payload = {
        "key_code": key_code,
        "key_type": key_type,
        "created_by": created_by,
        "duration_hours": duration_hours,
        "expires_at": expires_at_iso,
        "is_active": True
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.post(
                f"{SUPABASE_URL}/rest/v1/access_keys",
                headers=HEADERS,
                json=payload
            )
            print(f"[+] insert_key '{key_code}' -> HTTP {res.status_code}: {res.text[:120]}")
            return res.status_code in (200, 201)
        except Exception as e:
            print(f"[!] insert_key exception: {e}")
            return False


async def lookup_key(key_code: str):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.get(
                f"{SUPABASE_URL}/rest/v1/access_keys?key_code=eq.{key_code.strip()}&select=*",
                headers=HEADERS
            )
            if res.status_code == 200:
                data = res.json()
                return data[0] if data else None
        except Exception as e:
            print(f"[!] lookup_key exception: {e}")
    return None


# ─── Bot Events ───
@bot.event
async def on_ready():
    activity = discord.Activity(type=discord.ActivityType.watching, name="Meow Ware Keys • /getkey")
    await bot.change_presence(status=discord.Status.online, activity=activity)
    try:
        synced = await bot.tree.sync()
        print(f"[+] Bot logged in as {bot.user} (ID: {bot.user.id})")
        print(f"[+] Successfully synced {len(synced)} slash commands globally")
        for cmd in synced:
            print(f"    - /{cmd.name}: {cmd.description}")
    except Exception as e:
        print(f"[-] Slash command sync failed: {e}")


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    print(f"[-] Command error in {interaction.command.name if interaction.command else 'unknown'}: {error}")
    try:
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ Error: {error}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Error: {error}", ephemeral=True)
    except Exception:
        pass


# ─── Slash Command: /getkey (Daily 12h Access Key) ───
@bot.tree.command(name="getkey", description="Claim your 12-hour Meow Ware access key")
async def getkey_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    user_id = str(interaction.user.id)
    now = datetime.now(timezone.utc)

    # Check cooldown (exempt if admin)
    if interaction.user.id != ADMIN_ID:
        cooldown_data = await get_user_cooldown(user_id)
        if cooldown_data and cooldown_data.get("last_generated"):
            last_gen_str = cooldown_data["last_generated"]
            try:
                last_time = datetime.fromisoformat(last_gen_str.replace("Z", "+00:00"))
                diff = now - last_time
                if diff < timedelta(hours=12):
                    remaining = timedelta(hours=12) - diff
                    hours, rem = divmod(int(remaining.total_seconds()), 3600)
                    minutes, _ = divmod(rem, 60)

                    embed = discord.Embed(
                        title="⏳ Key Cooldown Active",
                        description=f"You have already claimed a daily key.\nYou can generate your next key in **{hours}h {minutes}m**.",
                        color=0xef4444
                    )
                    if cooldown_data.get("last_key_code"):
                        embed.add_field(
                            name="Your Current Key",
                            value=f"```{cooldown_data['last_key_code']}```",
                            inline=False
                        )
                    embed.set_footer(text="Meow Ware Authentication • 12 Hour Cooldown")
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return
            except Exception as e:
                print(f"[!] Cooldown parsing error: {e}")

    # Generate 12-hour key
    key_code = generate_key_string("MEOW")
    expires_at = now + timedelta(hours=12)
    expires_iso = expires_at.isoformat()

    success = await insert_key(
        key_code=key_code,
        key_type="daily",
        created_by=user_id,
        duration_hours=12,
        expires_at_iso=expires_iso
    )

    if not success:
        await interaction.followup.send("❌ Database error creating access key. Please try again in a moment.", ephemeral=True)
        return

    await set_user_cooldown(user_id, key_code)

    # Fancy DM Embed
    dm_embed = discord.Embed(
        title="✨ Meow Ware Access Key",
        description="Your 12-hour session key is ready. Copy and paste this key into Meow Ware to unlock the client.",
        color=0xa855f7
    )
    dm_embed.add_field(name="🔑 Key Code", value=f"```{key_code}```", inline=False)
    dm_embed.add_field(name="⏱ Duration", value="`12 Hours`", inline=True)
    dm_embed.add_field(name="📅 Expires", value=f"<t:{int(expires_at.timestamp())}:R>", inline=True)
    dm_embed.add_field(
        name="💡 How to activate",
        value="Open Meow Ware -> Complete Discord Auth -> Paste this key into the Key Prompt.",
        inline=False
    )
    dm_embed.set_footer(text="Meow Ware • Do not share your key with others")

    try:
        await interaction.user.send(embed=dm_embed)
        reply_embed = discord.Embed(
            title="✅ Key Delivered!",
            description=f"Your key has been sent to your **Direct Messages**!\n\nKey: `{key_code}`",
            color=0x10b981
        )
        await interaction.followup.send(embed=reply_embed, ephemeral=True)
    except discord.Forbidden:
        # Fallback if DMs are disabled
        await interaction.followup.send(embed=dm_embed, ephemeral=True)


# ─── Slash Command: /createkey (Admin Lifetime / Custom) ───
@bot.tree.command(name="createkey", description="Admin: Generate custom or lifetime access keys")
@app_commands.describe(
    key_type="Type of key",
    duration_hours="Duration in hours (0 for permanent lifetime)",
    target_user="User to automatically assign and DM the key"
)
@app_commands.choices(key_type=[
    app_commands.Choice(name="Lifetime (Permanent)", value="lifetime"),
    app_commands.Choice(name="Daily (12 Hours)", value="daily"),
    app_commands.Choice(name="Custom Hours", value="custom")
])
async def createkey_command(
    interaction: discord.Interaction,
    key_type: app_commands.Choice[str],
    duration_hours: int = 0,
    target_user: discord.User = None
):
    if interaction.user.id != ADMIN_ID:
        embed = discord.Embed(title="🚫 Unauthorized", description="You do not have permission to execute administrator commands.", color=0xef4444)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    now = datetime.now(timezone.utc)
    is_lifetime = (key_type.value == "lifetime" or duration_hours == 0)

    prefix = "LIFE" if is_lifetime else "MEOW"
    key_code = generate_key_string(prefix)

    expires_at = None if is_lifetime else (now + timedelta(hours=duration_hours or 12))
    expires_iso = expires_at.isoformat() if expires_at else None

    assigned_id = str(target_user.id) if target_user else str(interaction.user.id)

    success = await insert_key(
        key_code=key_code,
        key_type="lifetime" if is_lifetime else key_type.value,
        created_by=str(interaction.user.id),
        duration_hours=0 if is_lifetime else (duration_hours or 12),
        expires_at_iso=expires_iso
    )

    if not success:
        await interaction.followup.send("❌ Failed to insert key into database.", ephemeral=True)
        return

    embed = discord.Embed(
        title="👑 Admin Key Generated",
        color=0xf59e0b
    )
    embed.add_field(name="🔑 Key Code", value=f"```{key_code}```", inline=False)
    embed.add_field(name="Key Type", value=f"`{key_type.name}`", inline=True)
    embed.add_field(name="Duration", value="`Lifetime (Never Expires)`" if is_lifetime else f"`{duration_hours or 12} Hours`", inline=True)
    if target_user:
        embed.add_field(name="Assigned User", value=target_user.mention, inline=False)
    embed.set_footer(text="Meow Ware Admin Panel")

    await interaction.followup.send(embed=embed, ephemeral=True)

    if target_user:
        try:
            target_embed = discord.Embed(
                title="🎁 You Received a Meow Ware Access Key!",
                description=f"An administrator has granted you a **{key_type.name}** access key for Meow Ware.",
                color=0xf59e0b
            )
            target_embed.add_field(name="🔑 Key Code", value=f"```{key_code}```", inline=False)
            target_embed.add_field(name="Duration", value="`Lifetime`" if is_lifetime else f"`{duration_hours or 12} Hours`", inline=True)
            target_embed.set_footer(text="Meow Ware Authentication")
            await target_user.send(embed=target_embed)
        except discord.Forbidden:
            pass


# ─── Slash Command: /checkkey (Check Key Details) ───
@bot.tree.command(name="checkkey", description="Check the status and validity of an access key")
@app_commands.describe(key_code="The key to verify (e.g. MEOW-XXXX-XXXX-XXXX)")
async def checkkey_command(interaction: discord.Interaction, key_code: str):
    await interaction.response.defer(ephemeral=True)
    key_data = await lookup_key(key_code.strip())

    if not key_data:
        embed = discord.Embed(title="❌ Key Not Found", description=f"The key `{key_code}` does not exist in the database.", color=0xef4444)
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    now = datetime.now(timezone.utc)
    is_active = key_data.get("is_active", True)
    expires_str = key_data.get("expires_at")
    is_expired = False

    if expires_str:
        try:
            exp_dt = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
            if now > exp_dt:
                is_expired = True
        except Exception:
            pass

    status_str = "🔴 Expired" if is_expired else "🟢 Active" if is_active else "⚫ Revoked"

    embed = discord.Embed(
        title="🔍 Key Status Report",
        color=0x10b981 if (is_active and not is_expired) else 0xef4444
    )
    embed.add_field(name="Key Code", value=f"```{key_data['key_code']}```", inline=False)
    embed.add_field(name="Status", value=f"**{status_str}**", inline=True)
    embed.add_field(name="Type", value=f"`{key_data.get('key_type', 'daily')}`", inline=True)
    embed.add_field(
        name="Expires At",
        value=f"<t:{int(datetime.fromisoformat(expires_str.replace('Z', '+00:00')).timestamp())}:F>" if expires_str else "`Never (Lifetime)`",
        inline=False
    )
    if interaction.user.id == ADMIN_ID:
        embed.add_field(name="Created By (Discord ID)", value=f"`{key_data.get('created_by', 'Unknown')}`", inline=True)
        embed.add_field(name="Claimed By", value=f"`{key_data.get('claimed_by') or 'Unclaimed'}`", inline=True)

    await interaction.followup.send(embed=embed, ephemeral=True)


if __name__ == "__main__":
    if not TOKEN or not SUPABASE_KEY:
        raise SystemExit("Set DISCORD_TOKEN and SUPABASE_SECRET_KEY before starting the bot")
    bot.run(TOKEN)
