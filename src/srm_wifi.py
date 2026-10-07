#!/usr/bin/env python3
"""
SRM WiFi Daemon - Core Engine
Handles connection monitoring, captive portal detection, and automated 802.1X PEAP/MSCHAPv2 logins.
"""

import os
import sys
import time
import subprocess
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# Configuration
CONFIG_DIR = Path.home() / ".config" / "srmist"
CRED_FILE = CONFIG_DIR / "credentials.env"
LOG_FILE = CONFIG_DIR / "srmist-daemon.log"

CONNECTION_NAME = os.environ.get("SRMIST_CONNECTION", "SRMIST")
IFACE = os.environ.get("SRMIST_IFACE", "wlan0")

# Probes for testing true internet connectivity (fast, no heavy payload)
PROBE_URLS = [
    "http://connectivitycheck.gstatic.com/generate_204",
    "http://detectportal.firefox.com/canonical.html",
    "http://clients3.google.com/generate_204"
]

# Set up logging
os.makedirs(CONFIG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)-8s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("srm-wifi")

def load_credentials():
    """Load credentials from ~/.config/srmist/credentials.env with strict permissions."""
    if not CRED_FILE.exists():
        log.error(f"Credentials file missing: {CRED_FILE}")
        sys.exit(1)

    stat = CRED_FILE.stat()
    if oct(stat.st_mode)[-3:] != "600":
        log.warning(f"Insecure permissions on {CRED_FILE} - fixing to 600")
        CRED_FILE.chmod(0o600)

    creds = {}
    with open(CRED_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key, _, value = line.partition("=")
                creds[key.strip()] = value.strip().strip("'\"")

    if "SRMIST_USER" not in creds or "SRMIST_PASS" not in creds:
        log.error("SRMIST_USER or SRMIST_PASS missing from credentials file")
        sys.exit(1)

    return creds["SRMIST_USER"], creds["SRMIST_PASS"]

def is_interface_up():
    """Check if the physical wireless interface is connected to the network."""
    try:
        # Check NM connection state
        res = subprocess.run(["nmcli", "-t", "-f", "DEVICE,STATE", "device", "status"],
                           capture_output=True, text=True, timeout=5)
        for line in res.stdout.splitlines():
            dev, state = line.split(":", 1)
            if dev == IFACE and state == "connected":
                return True
        return False
    except Exception as e:
        log.debug(f"Interface check failed: {e}")
        return False

def check_true_connectivity():
    """Verify actual internet access to detect captive portals or silent drops."""
    if not is_interface_up():
        return False

    import urllib.request
    from urllib.error import URLError, HTTPError
    import ssl

    # Disable cert verification for captive portal redirect checks
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for url in PROBE_URLS:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=5, context=ctx)
            # A 204 No Content means we have direct access, no captive portal interception
            if resp.getcode() == 204 or b"success" in resp.read(256).lower():
                return True
        except HTTPError as e:
            # If intercepted by captive portal, it usually throws a redirect/error
            if e.code in [200, 301, 302]:
                log.warning("Captive portal intercepted the probe.")
                return False
        except Exception as e:
            continue

    return False

def force_reconnect():
    """Force NetworkManager to drop and rebuild the 802.1X PEAP session."""
    user, _ = load_credentials()
    log.info(f"Initiating full 802.1X re-authentication for user {user} on {CONNECTION_NAME}...")

    # Drop connection
    subprocess.run(["nmcli", "connection", "down", CONNECTION_NAME],
                  capture_output=True, timeout=15)
    time.sleep(2)

    # Re-establish
    res = subprocess.run(["nmcli", "--wait", "90", "connection", "up", CONNECTION_NAME],
                        capture_output=True, text=True, timeout=120)

    if res.returncode == 0:
        time.sleep(5)  # Wait for DHCP
        if check_true_connectivity():
            log.info("✅ Re-authentication successful and internet is reachable.")
            return True
        else:
            log.warning("⚠️ Network connected, but internet is NOT reachable (Captive Portal or DNS failure).")
            return False
    else:
        log.error(f"❌ Failed to bring up connection: {res.stderr.strip()}")
        return False

def daemon_mode():
    """Run continuously, monitoring and fixing drops."""
    log.info("🚀 SRM WiFi Daemon started. Monitoring network connectivity.")

    # Initialize variables for exponential backoff on failure
    backoff = 10
    max_backoff = 300

    # 24-Hour Auth Expiration Tracker
    # We preemptively force a reauth every 23.5 hours to prevent sudden drops during work
    last_forced_auth = datetime.now()
    FORCE_REAUTH_INTERVAL = timedelta(hours=23, minutes=30)

    while True:
        try:
            # 1. Check if it's time for the daily 24-hour token refresh
            now = datetime.now()
            if now - last_forced_auth >= FORCE_REAUTH_INTERVAL:
                log.info("⏰ 24-hour token expiration approaching. Preemptively renewing 802.1X session.")
                if force_reconnect():
                    last_forced_auth = now
                    backoff = 10

            # 2. Check active connectivity
            if check_true_connectivity():
                # All good, sleep and check again
                time.sleep(15)
                backoff = 10  # Reset backoff on success
                continue

            # 3. Connection dropped or portal intercepted!
            log.warning("🚨 Connectivity lost! Attempting recovery...")
            if force_reconnect():
                last_forced_auth = datetime.now()
                backoff = 10
            else:
                log.info(f"Retrying in {backoff} seconds...")
                time.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

        except KeyboardInterrupt:
            log.info("Daemon stopped by user.")
            break
        except Exception as e:
            log.error(f"Unexpected error in daemon loop: {e}")
            time.sleep(30)

def main():
    parser = argparse.ArgumentParser(description="SRMIST WiFi Keep-Alive & Auto-Authenticator")
    parser.add_argument("--daemon", action="store_true", help="Run in continuous monitoring mode")
    parser.add_argument("--force", action="store_true", help="Force immediate re-authentication")
    parser.add_argument("--status", action="store_true", help="Check current connectivity status")

    args = parser.parse_args()

    if args.status:
        if check_true_connectivity():
            print("✅ SRMIST Network is CONNECTED and internet is REACHABLE.")
            sys.exit(0)
        elif is_interface_up():
            print("⚠️ Interface is UP, but internet is UNREACHABLE (Login required).")
            sys.exit(1)
        else:
            print("❌ Interface is DOWN or disconnected.")
            sys.exit(1)

    if args.force:
        if force_reconnect():
            sys.exit(0)
        sys.exit(1)

    if args.daemon:
        daemon_mode()
    else:
        # Default behavior: run once if disconnected, exit 0 if already connected
        if check_true_connectivity():
            log.info("✅ Already connected and working.")
            sys.exit(0)
        if force_reconnect():
            sys.exit(0)
        sys.exit(1)

if __name__ == "__main__":
    main()
