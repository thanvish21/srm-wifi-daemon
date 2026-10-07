#!/usr/bin/env bash
# Install script for SRM WiFi Daemon

set -e

echo "📡 Installing SRM WiFi Daemon..."

# Setup links
mkdir -p ~/.local/bin
ln -sf /home/thanvish/srm-wifi-daemon/src/srm_wifi.py ~/.local/bin/srmist-connect
chmod +x /home/thanvish/srm-wifi-daemon/src/srm_wifi.py

# Disable old timer and service
echo "🛑 Stopping and disabling old srmist-login service..."
systemctl --user stop srmist-login.timer srmist-login.service 2>/dev/null || true
systemctl --user disable srmist-login.timer srmist-login.service 2>/dev/null || true

# Setup new service
echo "⚙️ Configuring systemd daemon..."
mkdir -p ~/.config/systemd/user/
cp /home/thanvish/srm-wifi-daemon/systemd/srm-wifi-daemon.service ~/.config/systemd/user/

# Ensure permissions on credentials
mkdir -p ~/.config/srmist
touch ~/.config/srmist/credentials.env
chmod 600 ~/.config/srmist/credentials.env

systemctl --user daemon-reload
systemctl --user enable srm-wifi-daemon.service
systemctl --user start srm-wifi-daemon.service

echo ""
echo "✅ Installation complete!"
echo "Daemon is now running in the background. It will check connectivity every 15s."
echo "It also proactively renews the 24-hour authentication token at 23.5 hours."
echo ""
echo "Commands available:"
echo "  srmist-connect --status   : Check current connection state"
echo "  srmist-connect --force    : Force an immediate reconnect"
echo "  journalctl --user -fu srm-wifi-daemon : View live daemon logs"
