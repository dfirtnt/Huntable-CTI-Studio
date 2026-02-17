# macOS system-wide max open files limit

Raises the system limit so Docker Desktop and other processes don't hit "too many open files".

## What's included

- **limit.maxfiles.plist** — Same plist used for both system (LaunchDaemon) and user (LaunchAgent). Sets soft 65536, hard 200000.

## Install

### 1. User session (Docker Desktop runs here) — already installed

The plist is in `~/Library/LaunchAgents/limit.maxfiles.plist`. Load it:

```bash
launchctl load ~/Library/LaunchAgents/limit.maxfiles.plist
```

To apply the limit immediately in this session (optional):

```bash
launchctl limit maxfiles 65536 200000
```

### 2. System-wide (optional, for all users / services)

```bash
sudo cp "$(dirname "$0")/limit.maxfiles.plist" /Library/LaunchDaemons/
sudo chown root:wheel /Library/LaunchDaemons/limit.maxfiles.plist
sudo chmod 644 /Library/LaunchDaemons/limit.maxfiles.plist
sudo launchctl load /Library/LaunchDaemons/limit.maxfiles.plist
```

## Verify

```bash
launchctl limit maxfiles
```

You should see `65536 200000` (or higher). First number = soft, second = hard.

## Persistence

- **LaunchAgent** (user): Runs at login; limit applies to your GUI session (Docker Desktop).
- **LaunchDaemon** (system): Runs at boot; limit applies to system services.

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/limit.maxfiles.plist
# Optional: remove plist
rm ~/Library/LaunchAgents/limit.maxfiles.plist
```

System daemon (if installed):

```bash
sudo launchctl unload /Library/LaunchDaemons/limit.maxfiles.plist
sudo rm /Library/LaunchDaemons/limit.maxfiles.plist
```
