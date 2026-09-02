import os
import httpx
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://rdrtqrvozedfvcskwtna.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY", "")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates"
}

payload = {
    "discord_id": "123456",
    "last_generated": datetime.now(timezone.utc).isoformat(),
    "last_key_code": "TEST-1234-5678-ABCD"
}

print(f"Testing insertion to {SUPABASE_URL}/rest/v1/user_cooldowns ...")
try:
    res = httpx.post(f"{SUPABASE_URL}/rest/v1/user_cooldowns", headers=headers, json=payload, timeout=10.0)
    print("Status Code:", res.status_code)
    print("Response Text:", res.text)
except Exception as e:
    print("Error:", e)
