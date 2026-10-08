#!/usr/bin/env python3
"""
SRM WiFi Daemon - Ultra-Reliable 802.1X Auto-Reconnect & 24h Watchdog
Author: Machireddy Venkata Thanvish Reddy (RA2611027010109)
"""

import os
import sys
import time
import subprocess
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta

CONFIG_DIR = Path.home() / ".config" / "srmist"
CRED_FILE = CONFIG_DIR / "credentials.env"
LOG_FILE = CONFIG_DIR / "srmist-daemon.log"

CONNECTION_NAME = os.environ.get("SRMIST_CONNECTION", "SRMIST")
IFACE = os.environ.get("SRMIST_IFACE", "wlan0")

PROBE_URLS = [
    "http://connectivitycheck.gstatic.com/generate_204",
    "http://detectportal.firefox.com/canonical.html",
    "http://clients3.google.com/generate_204"
]

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

def run_cmd(cmd, timeout=30):
    """Run a command, preferring sudo if normal execution fails authorization."""
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if res.returncode != 0 and "Not authorized" in res.stderr:
            sudo_cmd = ["sudo", "-n"] + cmd
            return subprocess.run(sudo_cmd, capture_output=True, text=True, timeout=timeout)
        return res
    except Exception as e:
        log.debug(f"Command execution error for {cmd}: {e}")
        return None

def load_credentials():
    """Load credentials from ~/.config/srmist/credentials.env with fallback defaults."""
    user = "vm7036"
    password = "Nehitha21@"

    if CRED_FILE.exists():
        try:
            with open(CRED_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        key, _, val = line.partition("=")
                        k = key.strip()
                        v = val.strip().strip("'\"")
                        if k == "SRMIST_USER":
                            user = v
                        elif k == "SRMIST_PASS":
                            password = v
        except Exception as e:
            log.warning(f"Could not read {CRED_FILE}: {e}")

    return user, password

def sync_networkmanager_profile():
    """Ensure the NetworkManager profile has the exact 802.1X PEAP/MSCHAPv2 credentials."""
    user, password = load_credentials()

    # Check if connection exists
    res = run_cmd(["nmcli", "-t", "-f", "NAME", "connection", "show"])
    if res and CONNECTION_NAME in res.stdout.splitlines():
        # Update existing profile
        run_cmd([
            "nmcli", "connection", "modify", CONNECTION_NAME,
            "802-1x.eap", "peap",
            "802-1x.identity", user,
            "802-1x.anonymous-identity", user,
            "802-1x.password", password,
            "802-1x.phase2-auth", "mschapv2",
            "802-1x.domain-suffix-match", "srmist.edu.in",
            "connection.autoconnect", "yes",
            "connection.autoconnect-priority", "10"
        ])
    else:
        # Create connection if missing
        run_cmd([
            "nmcli", "connection", "add",
            "type", "wifi",
            "con-name", CONNECTION_NAME,
            "ifname", IFACE,
            "ssid", CONNECTION_NAME,
            "wifi-sec.key-mgmt", "wpa-eap",
            "802-1x.eap", "peap",
            "802-1x.identity", user,
            "802-1x.anonymous-identity", user,
            "802-1x.password", password,
            "802-1x.phase2-auth", "mschapv2",
            "802-1x.domain-suffix-match", "srmist.edu.in"
        ])

def is_srmist_available():
    """Check if SRMIST SSID is visible in the current environment."""
    res = run_cmd(["nmcli", "-t", "-f", "SSID", "device", "wifi", "list"], timeout=10)
    if res and CONNECTION_NAME in res.stdout.splitlines():
        return True
    return False

def get_current_connection():
    """Return the currently active Wi-Fi connection name."""
    res = run_cmd(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"])
    if res and res.stdout:
        for line in res.stdout.splitlines():
            parts = line.split(":")
            if len(parts) >= 4 and parts[0] == IFACE and parts[2] == "connected":
                return parts[3]
    return None

def check_true_connectivity():
    """Verify true end-to-end internet connectivity."""
    import urllib.request
    import ssl

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for url in PROBE_URLS:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4, context=ctx) as resp:
                if resp.getcode() == 204 or b"success" in resp.read(256).lower():
                    return True
        except Exception:
            continue
    return False

def force_reconnect():
    """Execute clean 802.1X PEAP re-authentication."""
    user, _ = load_credentials()
    log.info(f"Initiating full 802.1X re-authentication for user '{user}' on '{CONNECTION_NAME}'...")

    sync_networkmanager_profile()

    # Drop and reconnect
    run_cmd(["nmcli", "connection", "down", CONNECTION_NAME], timeout=10)
    time.sleep(1)

    res = run_cmd(["nmcli", "--wait", "60", "connection", "up", CONNECTION_NAME], timeout=90)
    if res and res.returncode == 0:
        time.sleep(3)
        if check_true_connectivity():
            log.info("✅ Connection established and internet is reachable.")
            return True
        else:
            log.warning("⚠️ Connected to Wi-Fi, verifying egress gateway...")
            time.sleep(3)
            return check_true_connectivity()
    else:
        err = res.stderr.strip() if res else "Command timed out"
        log.error(f"❌ Connection activation failed: {err}")
        return False

def daemon_mode():
    """Continuous auto-reconnect and 24h watchdog loop."""
    log.info("🚀 SRM WiFi Daemon running. Monitoring network health.")
    sync_networkmanager_profile()

    last_forced_auth = datetime.now()
    FORCE_REAUTH_INTERVAL = timedelta(hours=23, minutes=30)
    backoff = 10
    max_backoff = 180

    while True:
        try:
            now = datetime.now()
            current_conn = get_current_connection()

            # 1. Handle 24-hour proactive token expiration when on SRMIST
            if current_conn == CONNECTION_NAME and (now - last_forced_auth >= FORCE_REAUTH_INTERVAL):
                log.info("⏰ 24-hour token expiration approaching. Renewing 802.1X session proactively.")
                if force_reconnect():
                    last_forced_auth = now
                    backoff = 10

            # 2. Check active connectivity
            if check_true_connectivity():
                time.sleep(15)
                backoff = 10
                continue

            # 3. Connection dropped or no internet!
            # Only attempt SRMIST connection if we were on SRMIST or SRMIST is in range
            if current_conn == CONNECTION_NAME or current_conn is None or is_srmist_available():
                log.warning("🚨 Internet connectivity lost! Re-authenticating SRMIST...")
                if force_reconnect():
                    last_forced_auth = datetime.now()
                    backoff = 10
                else:
                    log.info(f"Retrying in {backoff}s...")
                    time.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)
            else:
                # Connected to a different network (e.g. personal hotspot/home), don't hijack it
                time.sleep(20)

        except KeyboardInterrupt:
            log.info("Daemon stopped by user.")
            break
        except Exception as e:
            log.error(f"Unexpected loop exception: {e}")
            time.sleep(15)

def main():
    parser = argparse.ArgumentParser(description="SRMIST WiFi Keep-Alive & Auto-Authenticator")
    parser.add_argument("--daemon", action="store_true", help="Run continuous watchdog daemon")
    parser.add_argument("--force", action="store_true", help="Force immediate re-authentication")
    parser.add_argument("--status", action="store_true", help="Check current connectivity status")

    args = parser.parse_args()

    if args.status:
        if check_true_connectivity():
            print("✅ Internet is reachable.")
            cur = get_current_connection()
            print(f"📡 Active Connection: {cur}")
            sys.exit(0)
        else:
            print("❌ Internet is unreachable.")
            sys.exit(1)

    if args.force:
        if force_reconnect():
            sys.exit(0)
        sys.exit(1)

    if args.daemon:
        daemon_mode()
    else:
        if check_true_connectivity():
            print("✅ Already connected.")
            sys.exit(0)
        if force_reconnect():
            sys.exit(0)
        sys.exit(1)

if __name__ == "__main__":
    main()
