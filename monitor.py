"""
Tesla Trip Monitor
Polls Tesla Fleet API and sends an SMS alert when the car shifts into Drive.
"""

import os
import sys
import json
import time
import smtplib
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from email.message import EmailMessage
from dotenv import load_dotenv
import requests
from twilio.rest import Client as TwilioClient

load_dotenv()

# --- Config ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM = os.getenv("TWILIO_FROM")
TWILIO_TO = os.getenv("TWILIO_TO")
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
CLIENT_ID = os.getenv("TESLA_CLIENT_ID")
CLIENT_SECRET = os.getenv("TESLA_CLIENT_SECRET")

FLEET_API_BASE = "https://fleet-api.prd.na.vn.cloud.tesla.com"
TOKEN_URL = "https://auth.tesla.com/oauth2/v3/token"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "tokens.json")
STATE_FILE = os.path.join(BASE_DIR, "state.json")
POLL_INTERVAL = 90  # seconds between checks

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor.log")),
    ],
)
log = logging.getLogger(__name__)


class TeslaMonitor:
    def __init__(self):
        self.tokens = self._load_tokens()
        self.state = self._load_state()
        self.last_shift_state = self.state.get("last_shift_state")
        self.vehicle_id = None
        self.vehicle_name = None

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                return json.load(f)
        return {}

    def _save_state(self):
        self.state["last_shift_state"] = self.last_shift_state
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=2)

    def _load_tokens(self):
        # Prefer TESLA_TOKENS env var (for cloud deployment), fall back to file
        tokens_env = os.getenv("TESLA_TOKENS")
        if tokens_env:
            return json.loads(tokens_env)
        if not os.path.exists(TOKEN_FILE):
            log.error(f"No tokens found. Run auth.py first.")
            sys.exit(1)
        with open(TOKEN_FILE) as f:
            return json.load(f)

    def _save_tokens(self):
        # Save to file locally; in cloud, tokens live in memory until next refresh
        try:
            with open(TOKEN_FILE, "w") as f:
                json.dump(self.tokens, f, indent=2)
        except OSError:
            pass  # Cloud environment, file write may not persist

    def _refresh_token(self):
        log.info("Refreshing access token...")
        resp = requests.post(TOKEN_URL, json={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": self.tokens["refresh_token"],
        })
        resp.raise_for_status()
        new_tokens = resp.json()
        self.tokens["access_token"] = new_tokens["access_token"]
        if "refresh_token" in new_tokens:
            self.tokens["refresh_token"] = new_tokens["refresh_token"]
        self._save_tokens()
        log.info("Token refreshed.")

    def _api(self, endpoint):
        """Make an authenticated Fleet API request. Auto-refreshes token on 401."""
        url = f"{FLEET_API_BASE}{endpoint}"
        headers = {"Authorization": f"Bearer {self.tokens['access_token']}"}

        resp = requests.get(url, headers=headers)

        if resp.status_code == 401:
            self._refresh_token()
            headers["Authorization"] = f"Bearer {self.tokens['access_token']}"
            resp = requests.get(url, headers=headers)

        resp.raise_for_status()
        return resp.json()

    def get_vehicles(self):
        data = self._api("/api/1/vehicles")
        return data.get("response", [])

    def select_vehicle(self):
        vehicles = self.get_vehicles()
        if not vehicles:
            log.error("No vehicles found on your Tesla account.")
            sys.exit(1)

        # Auto-select first vehicle (for unattended cloud operation)
        v = vehicles[0]

        self.vehicle_id = v["id"]
        self.vehicle_name = v.get("display_name", v["vin"])
        log.info(f"Monitoring: {self.vehicle_name}")
        return v

    def get_vehicle_state(self):
        """Check if vehicle is online without waking it."""
        vehicles = self.get_vehicles()
        for v in vehicles:
            if v["id"] == self.vehicle_id:
                return v.get("state", "unknown")
        return "unknown"

    def get_drive_state(self):
        """Get the vehicle's drive state (shift_state, speed, location)."""
        data = self._api(f"/api/1/vehicles/{self.vehicle_id}/vehicle_data?endpoints=drive_state")
        drive = data.get("response", {}).get("drive_state", {})
        return drive

    def send_alert(self, drive_state):
        """Send alert that a trip has started."""
        lat = drive_state.get("latitude", "?")
        lon = drive_state.get("longitude", "?")
        timestamp = datetime.now(ZoneInfo("America/New_York")).strftime("%I:%M %p ET")
        maps_link = f"maps.google.com/?q={lat},{lon}"

        body = f"{self.vehicle_name} started a trip at {timestamp}\n{maps_link}"

        if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
            try:
                client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                client.messages.create(body=body, from_=TWILIO_FROM, to=TWILIO_TO)
                log.info("SMS alert sent via Twilio!")
                return
            except Exception as e:
                log.error(f"Twilio failed: {e}. Falling back to email.")

        # Fallback: send email
        try:
            msg = EmailMessage()
            msg.set_content(body)
            msg["Subject"] = f"Tesla Trip Started"
            msg["From"] = GMAIL_USER
            msg["To"] = GMAIL_USER
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
                server.send_message(msg)
            log.info("Alert sent via email!")
        except Exception as e:
            log.error(f"Email failed: {e}")

    def poll(self):
        """Single poll cycle."""
        state = self.get_vehicle_state()

        if state != "online":
            log.info(f"Vehicle is {state}. Skipping.")
            return

        try:
            drive = self.get_drive_state()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 408:
                log.info("Vehicle went to sleep during request.")
                return
            raise

        shift_state = drive.get("shift_state")  # None=Park, D=Drive, R=Reverse, N=Neutral
        speed = drive.get("speed") or 0

        log.info(f"Online | shift={shift_state} speed={speed}")

        # Detect transition to Drive (or Reverse)
        if shift_state in ("D", "R") and self.last_shift_state not in ("D", "R"):
            log.info(f"TRIP STARTED! Shift: {self.last_shift_state} -> {shift_state}")
            self.send_alert(drive)

        self.last_shift_state = shift_state
        self._save_state()

    def run_once(self):
        """Single check (for scheduled task use)."""
        self.select_vehicle()
        try:
            self.poll()
        except requests.exceptions.HTTPError as e:
            log.error(f"API error: {e}")
        except requests.exceptions.ConnectionError:
            log.error("Connection error.")
        except Exception as e:
            log.error(f"Unexpected error: {e}")

    def run_for(self, duration=270, interval=60):
        """Run checks for a fixed duration (for GitHub Actions).
        Default: 4.5 minutes with 60s intervals, leaving buffer before 5min cron."""
        self.select_vehicle()
        start = time.time()
        log.info(f"Running for {duration}s with {interval}s intervals.")

        while time.time() - start < duration:
            try:
                self.poll()
            except requests.exceptions.HTTPError as e:
                log.error(f"API error: {e}")
            except requests.exceptions.ConnectionError:
                log.error("Connection error.")
            except Exception as e:
                log.error(f"Unexpected error: {e}")

            remaining = duration - (time.time() - start)
            if remaining > interval:
                time.sleep(interval)
            else:
                break

        log.info("Run complete.")

    def run(self):
        """Main monitoring loop."""
        self.select_vehicle()
        log.info(f"Polling every {POLL_INTERVAL}s. Press Ctrl+C to stop.")

        while True:
            try:
                self.poll()
            except requests.exceptions.HTTPError as e:
                log.error(f"API error: {e}")
            except requests.exceptions.ConnectionError:
                log.error("Connection error. Retrying...")
            except Exception as e:
                log.error(f"Unexpected error: {e}")

            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        monitor = TeslaMonitor()
        if "--once" in sys.argv:
            monitor.run_once()
        elif "--loop" in sys.argv:
            monitor.run_for()
        else:
            monitor.run()
    except KeyboardInterrupt:
        print("\nStopped.")
