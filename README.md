<div align="center">

# 📡 SRM-WIFI-DAEMON

### *Zero-Drop, Autonomous 802.1X Keep-Alive & 24h Auth Manager for SRMIST Campus Network*

[![Linux](https://img.shields.io/badge/Platform-Linux%20%7C%20Kali-orange.svg?style=flat-square&logo=linux)](https://github.com/thanvish21)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=flat-square&logo=python)](https://python.org)
[![Systemd](https://img.shields.io/badge/Service-Systemd%20User%20Daemon-red.svg?style=flat-square&logo=systemd)](https://systemd.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)

*Engineered by [Thanvish Reddy](https://github.com/thanvish21) (SRM Institute of Science & Technology)*

---

</div>

## ⚡ Overview

The SRMIST campus Wi-Fi network operates under two major constraints:
1. **Periodic 24-Hour Auth Drops:** Active 802.1X Enterprise sessions (PEAP/MSCHAPv2) are forcibly terminated every 24 hours.
2. **Campus AP Roaming Drops:** Signal drops between academic blocks and hostels often leave the interface in a half-connected state where DHCP is valid but the gateway drops all egress packets.

**`srm-wifi-daemon`** is a high-reliability background service designed to eliminate disconnections completely. It continuously monitors true end-to-end internet connectivity and automatically handles re-authentication in milliseconds without interrupting workflows.

---

## 🎯 Key Features

- **Continuous Health Probing:** Tests egress connectivity every 15 seconds against lightweight, zero-payload validation endpoints (`gstatic`, `mozilla`, `google`).
- **Preemptive 24-Hour Token Renewal:** Refreshes credentials automatically at 23.5 hours to guarantee you never drop mid-work.
- **Fast Silent Auto-Recovery:** Restores broken sessions with exponential backoff on intermittent campus access-point failures.
- **Strict Security Enclosure:** Reads credentials from mode `600` isolated configuration (`~/.config/srmist/credentials.env`) without ever passing plaintext tokens in process arguments or logs.
- **Systemd User Unit:** Runs as a standard unprivileged user service with auto-restart on failure.

---

## 🏗️ Architecture

```
                       +-----------------------------+
                       |    SRM Wi-Fi Daemon         |
                       +--------------+--------------+
                                      |
                         [Every 15s Health Probe]
                                      |
                     +----------------+----------------+
                     |                                 |
              [HTTP 204 OK]                   [Interception / Drop]
                     |                                 |
           (Keep Session Alive)             (Trigger 802.1X Reauth)
                     |                                 |
      [23.5h Proactive Timer?]              [nmcli PEAP Handshake]
          /              \                             |
       (Yes)             (No)                [DHCP Egress Verify]
         |                 |                           |
  (Renew Session)     (Continue)                  (Done / Log)
```

---

## 🚀 Quick Start

### 1. Clone & Configure
```bash
git clone https://github.com/thanvish21/srm-wifi-daemon.git
cd srm-wifi-daemon
```

### 2. Set Up Credentials
Create `~/.config/srmist/credentials.env` with your NetID credentials:
```bash
mkdir -p ~/.config/srmist
cat << 'EOF' > ~/.config/srmist/credentials.env
SRMIST_USER='your_netid'
SRMIST_PASS='your_password'
EOF
chmod 600 ~/.config/srmist/credentials.env
```

### 3. Run Installer
```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

---

## 💻 CLI Commands

```bash
# Check current connection state & reachability
srmist-connect --status

# Force an immediate 802.1X re-authentication
srmist-connect --force

# View live background daemon logs
journalctl --user -fu srm-wifi-daemon
```

---

## 🛡️ Security

- **No Password Leaks:** Authentication uses the stored NetworkManager connection secret via internal IPC; the password is never placed on the command line or visible in `ps aux`.
- **Credential File Lockdown:** The daemon refuses to run if `credentials.env` is readable by any other user (`chmod 600` enforced).

---

## 📜 License

MIT © [Machireddy Venkata Thanvish Reddy](https://github.com/thanvish21)
