import os
import httpx

SUPABASE_URL = "https://rdrtqrvozedfvcskwtna.supabase.co"
PUB_KEY = "sb_publishable_9ibbPO1-YKfliFE2e5bdtQ_V5SeNSpy"
SEC_KEY = os.getenv("SUPABASE_SECRET_KEY", "")
KEY_CODE = os.getenv("TEST_LICENSE_KEY", "")

print("--- Testing with PUBLISHABLE KEY ---")
try:
    headers = {
        "apikey": PUB_KEY,
        "Authorization": f"Bearer {PUB_KEY}",
        "Content-Type": "application/json",
    }
    res = httpx.get(f"{SUPABASE_URL}/rest/v1/access_keys?key_code=eq.{KEY_CODE}&select=*", headers=headers)
    print("Status:", res.status_code)
    print("Data:", res.json())
except Exception as e:
    print("Error:", e)

print("\n--- Testing with SECRET KEY ---")
try:
    headers = {
        "apikey": SEC_KEY,
        "Authorization": f"Bearer {SEC_KEY}",
        "Content-Type": "application/json",
    }
    res = httpx.get(f"{SUPABASE_URL}/rest/v1/access_keys?key_code=eq.{KEY_CODE}&select=*", headers=headers)
    print("Status:", res.status_code)
    print("Data:", res.json())
except Exception as e:
    print("Error:", e)
