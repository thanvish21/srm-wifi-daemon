# Changelog

## v1.0 – 2024-12-15

### Added
- **Continuous health probing** – connectivity tested every 15 s against lightweight
  zero‑payload endpoints (`gstatic`, `mozilla`, `google`).
- **Preemptive 24-hour token renewal** – credentials refreshed automatically at 23.5 h
  to avoid any mid-session drop.
- **Exponential-backoff reconnect** – automatically recovers from campus AP roaming drops
  with configurable retry intervals.
- **Authorised network control** – switch between campus, hotspot, and roaming profiles via
  `srmist-connect --profile <name>`.
- **systemd user unit** – runs unprivileged with `Restart=on-failure`; survives reboots
  without root.

### Security
- Credentials stored in `~/.config/srmist/credentials.env` (mode 600); daemon refuses to
  start if file is world-readable.
- No password ever appears on the command line or in log output.
