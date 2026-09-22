import os
import secrets
import string
from pathlib import Path
from datetime import datetime, timedelta, timezone
import discord
from discord import app_commands
from discord.ext import commands
import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

# Configuration
TOKEN = os.getenv("DISCORD_TOKEN", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://rdrtqrvozedfvcskwtna.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY", "")
ADMIN_ID = int(os.getenv("ADMIN_USER_ID", "1244476245249626133"))
DOWNLOAD_URL = os.getenv("DOWNLOAD_URL", "").strip()
DOWNLOAD_FILE = os.getenv("DOWNLOAD_FILE", "").strip()
DOWNLOAD_VERSION = os.getenv("DOWNLOAD_VERSION", "Latest").strip() or "Latest"
DOWNLOAD_TERMS_VERSION = os.getenv("DOWNLOAD_TERMS_VERSION", "2026-09-03").strip()

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


async def record_download_agreement(user: discord.abc.User):
    """Best-effort audit record. A temporary database problem must not trap a
    user in the agreement screen after they explicitly accepted the terms."""
    payload = {
        "discord_id": str(user.id),
        "discord_name": str(user),
        "terms_version": DOWNLOAD_TERMS_VERSION,
        "accepted_at": datetime.now(timezone.utc).isoformat(),
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.post(
                f"{SUPABASE_URL}/rest/v1/download_agreements",
                headers={**HEADERS, "Prefer": "resolution=merge-duplicates,return=minimal"},
                json=payload,
            )
            if res.status_code not in (200, 201, 204):
                print(f"[!] download agreement audit HTTP {res.status_code}: {res.text[:120]}")
        except Exception as exc:
            print(f"[!] download agreement audit failed: {exc}")


class DownloadAgreementView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=300)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            "Run `/download` yourself to review and accept the terms.", ephemeral=True
        )
        return False

    @discord.ui.button(label="I agree — continue", style=discord.ButtonStyle.success, emoji="✅")
    async def agree(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.defer()
        await record_download_agreement(interaction.user)
        embed = discord.Embed(
            title="✅ Agreement accepted",
            description="Your private download is ready. Keep this link and the downloaded file to yourself.",
            color=0x10B981,
        )
        embed.add_field(name="Version", value=f"`{DOWNLOAD_VERSION}`", inline=True)
        embed.add_field(name="Terms", value=f"`{DOWNLOAD_TERMS_VERSION}`", inline=True)
        embed.set_footer(text="Meow Ware • Access is personal and non-transferable")
        artifact = Path(DOWNLOAD_FILE).expanduser() if DOWNLOAD_FILE else None
        if artifact and not artifact.is_absolute():
            artifact = Path(__file__).resolve().parent / artifact
        if artifact and artifact.is_file():
            embed.description = "Your agreement was accepted. Your private file is being delivered below."
            await interaction.edit_original_response(embed=embed, view=None)
            try:
                await interaction.followup.send(
                    content="⬇️ **Your private Meow Ware download**",
                    file=discord.File(artifact, filename=artifact.name),
                    ephemeral=True,
                )
                self.stop()
                return
            except discord.HTTPException as exc:
                print(f"[!] Direct download upload failed: {exc}")

        view = discord.ui.View(timeout=300)
        if DOWNLOAD_URL:
            embed.description = "Your agreement was accepted. Use the private download button below."
            view.add_item(discord.ui.Button(label="Download Meow Ware", style=discord.ButtonStyle.link, url=DOWNLOAD_URL, emoji="⬇️"))
        else:
            embed.description = "Your agreement was accepted, but the download is not configured yet. Please contact an administrator."
        await interaction.edit_original_response(embed=embed, view=view)
        self.stop()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def decline(self, interaction: discord.Interaction, _button: discord.ui.Button):
        embed = discord.Embed(
            title="Download cancelled",
            description="You must accept the distribution terms before downloading Meow Ware.",
            color=0x6B7280,
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


def make_download_agreement_embed():
    embed = discord.Embed(
        title="Meow Ware Download Agreement",
        description=(
            "Before downloading, confirm that you understand and agree to these terms:\n\n"
            "• Do not leak, share, mirror, upload, or redistribute the app or download link.\n"
            "• Do not resell, sublicense, decompile, reverse-engineer, or bypass access controls.\n"
            "• Do not use the software to harm others, distribute malware, or abuse third-party services.\n"
            "• You are responsible for following Discord, Roblox, and local rules and laws.\n"
            "• Access may be revoked if these terms are violated.\n\n"
            "Selecting **I agree — continue** records your Discord account and acceptance time."
        ),
        color=0xA855F7,
    )
    embed.add_field(name="Release", value=f"`{DOWNLOAD_VERSION}`", inline=True)
    embed.add_field(name="Terms revision", value=f"`{DOWNLOAD_TERMS_VERSION}`", inline=True)
    embed.set_footer(text="This prompt is private and expires after 5 minutes")
    return embed


class DownloadPanelView(discord.ui.View):
    """Persistent public entry point. Each click creates a user-bound,
    ephemeral agreement so the release URL never appears in the panel."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Get Download",
        style=discord.ButtonStyle.primary,
        emoji="⬇️",
        custom_id="meowware:download-panel:v1",
    )
    async def open_download(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await interaction.response.send_message(
            embed=make_download_agreement_embed(),
            view=DownloadAgreementView(interaction.user.id),
            ephemeral=True,
        )

# ─── Bot Events ───
@bot.event
async def on_ready():
    if not getattr(bot, "_download_panel_registered", False):
        bot.add_view(DownloadPanelView())
        bot._download_panel_registered = True
    activity = discord.Activity(type=discord.ActivityType.watching, name="Meow Ware • /download")
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


# ─── Slash Command: /download (Private agreement gate) ───
@bot.tree.command(name="download", description="Accept the terms and get the private Meow Ware download")
async def download_command(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=make_download_agreement_embed(),
        view=DownloadAgreementView(interaction.user.id),
        ephemeral=True,
    )


@bot.tree.command(name="downloadpanel", description="Admin: Post the permanent Meow Ware download panel")
@app_commands.describe(channel="Channel where the download panel should be posted")
async def download_panel_command(
    interaction: discord.Interaction,
    channel: discord.TextChannel = None,
):
    if interaction.user.id != ADMIN_ID:
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🚫 Unauthorized",
                description="Only the configured bot administrator can create download panels.",
                color=0xEF4444,
            ),
            ephemeral=True,
        )
        return

    target = channel or interaction.channel
    if not isinstance(target, (discord.TextChannel, discord.Thread)):
        await interaction.response.send_message(
            "Choose a server text channel for the panel.", ephemeral=True
        )
        return

    panel = discord.Embed(
        title="Download Meow Ware",
        description=(
            "Get the latest private Meow Ware release.\n\n"
            "Press **Get Download** to review the distribution agreement. "
            "After accepting, your download button will appear privately."
        ),
        color=0xA855F7,
    )
    panel.add_field(name="Current release", value=f"`{DOWNLOAD_VERSION}`", inline=True)
    panel.add_field(name="Private delivery", value="Agreement required", inline=True)
    panel.set_footer(text="Meow Ware • Do not redistribute")
    try:
        message = await target.send(embed=panel, view=DownloadPanelView())
    except discord.Forbidden:
        await interaction.response.send_message(
            f"I cannot post in {target.mention}. Give me View Channel, Send Messages, Embed Links, and Use External Emojis permissions.",
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        f"✅ Download panel created in {target.mention}: {message.jump_url}",
        ephemeral=True,
    )


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
