"""
One-time OAuth setup for Tesla Fleet API.
Run this script to authorize the app and get access/refresh tokens.
"""

import os
import json
import hashlib
import secrets
import base64
import urllib.parse
import webbrowser
from dotenv import load_dotenv
import requests

load_dotenv()

CLIENT_ID = os.getenv("TESLA_CLIENT_ID")
CLIENT_SECRET = os.getenv("TESLA_CLIENT_SECRET")
REDIRECT_URI = "https://steieralan.github.io/callback"
AUTH_URL = "https://auth.tesla.com/oauth2/v3/authorize"
TOKEN_URL = "https://auth.tesla.com/oauth2/v3/token"
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokens.json")

# PKCE
code_verifier = secrets.token_urlsafe(64)
code_challenge_b64 = base64.urlsafe_b64encode(
    hashlib.sha256(code_verifier.encode()).digest()
).decode().rstrip("=")

state = secrets.token_urlsafe(16)


def get_auth_url():
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "openid offline_access vehicle_device_data vehicle_location",
        "state": state,
        "code_challenge": code_challenge_b64,
        "code_challenge_method": "S256",
        "audience": "https://fleet-api.prd.na.vn.cloud.tesla.com",
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def exchange_code(code):
    resp = requests.post(TOKEN_URL, json={
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": code_verifier,
    })
    resp.raise_for_status()
    return resp.json()


def save_tokens(token_data):
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)
    print(f"Tokens saved to {TOKEN_FILE}")


def main():
    print("=" * 50)
    print("Tesla Fleet API - OAuth Setup")
    print("=" * 50)

    url = get_auth_url()
    print(f"\nOpening browser for Tesla login...")
    print(f"If it doesn't open, go to:\n{url}\n")
    webbrowser.open(url)

    print("After you log in and approve, you'll be redirected to a 404 page.")
    print("That's expected! Copy the FULL URL from your browser's address bar")
    print("and paste it here:\n")

    callback_url = input("Paste URL here: ").strip()

    # Extract the authorization code from the URL
    parsed = urllib.parse.urlparse(callback_url)
    params = urllib.parse.parse_qs(parsed.query)

    if "code" not in params:
        print("\nError: No authorization code found in that URL.")
        return

    code = params["code"][0]
    print("\nAuthorization code received. Exchanging for tokens...")
    token_data = exchange_code(code)
    save_tokens(token_data)
    print("\nSetup complete! You can now run monitor.py")


if __name__ == "__main__":
    main()
