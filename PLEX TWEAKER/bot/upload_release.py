"""Upload a release artifact to the configured Discord channel.

Usage: python upload_release.py <path-to-file> [channel-id]
Prints only the resulting CDN URL; credentials remain in .env.
"""
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv


def main():
    load_dotenv()
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python upload_release.py <path-to-file> [channel-id]")
    artifact = Path(sys.argv[1]).resolve()
    channel_id = (sys.argv[2] if len(sys.argv) > 2 else os.getenv("DOWNLOAD_CHANNEL_ID", "")).strip()
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not artifact.is_file():
        raise SystemExit(f"Artifact not found: {artifact}")
    if not token or not channel_id:
        raise SystemExit("DISCORD_TOKEN and DOWNLOAD_CHANNEL_ID are required")

    payload = {"content": f"New Meow Ware release: **{artifact.name}**"}
    with artifact.open("rb") as handle:
        response = httpx.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            headers={"Authorization": f"Bot {token}"},
            files={
                "payload_json": (None, json.dumps(payload), "application/json"),
                "files[0]": (artifact.name, handle, "application/octet-stream"),
            },
            timeout=180.0,
        )
    if response.status_code not in (200, 201):
        raise SystemExit(f"Discord upload failed ({response.status_code}): {response.text[:300]}")
    attachments = response.json().get("attachments", [])
    if not attachments:
        raise SystemExit("Discord accepted the message but returned no attachment")
    print(attachments[0]["url"])


if __name__ == "__main__":
    main()
