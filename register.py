"""
One-time partner registration with Tesla Fleet API.
Run this ONCE before using monitor.py.
"""

import os
from dotenv import load_dotenv
import requests

load_dotenv()

CLIENT_ID = os.getenv("TESLA_CLIENT_ID")
CLIENT_SECRET = os.getenv("TESLA_CLIENT_SECRET")
TOKEN_URL = "https://auth.tesla.com/oauth2/v3/token"
FLEET_API_BASE = "https://fleet-api.prd.na.vn.cloud.tesla.com"


def main():
    print("Getting partner token...")
    token_resp = requests.post(TOKEN_URL, json={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "openid vehicle_device_data vehicle_location",
        "audience": "https://fleet-api.prd.na.vn.cloud.tesla.com",
    })
    token_resp.raise_for_status()
    access_token = token_resp.json()["access_token"]
    print("Partner token acquired.")

    print("Registering app with Tesla...")
    reg_resp = requests.post(
        f"{FLEET_API_BASE}/api/1/partner_accounts",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"domain": "steieralan.github.io"},
    )
    print(f"Status: {reg_resp.status_code}")
    print(f"Response: {reg_resp.json()}")

    if reg_resp.status_code == 200:
        print("\nRegistration complete! You can now run monitor.py")
    else:
        print("\nRegistration failed. Check the error above.")


if __name__ == "__main__":
    main()
