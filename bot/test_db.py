import os
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://rdrtqrvozedfvcskwtna.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY", "")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

payload = {
    "key_code": "TEST-1234-5678-ABCD",
    "key_type": "daily",
    "created_by": "123456",
    "duration_hours": 12,
    "is_active": True
}

print(f"Testing insertion to {SUPABASE_URL}/rest/v1/access_keys ...")
try:
    res = httpx.post(f"{SUPABASE_URL}/rest/v1/access_keys", headers=headers, json=payload, timeout=10.0)
    print("Status Code:", res.status_code)
    print("Response Text:", res.text)
except Exception as e:
    print("Error:", e)
