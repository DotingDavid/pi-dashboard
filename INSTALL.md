# Quick Installation Guide

## 1. Test the Dashboard

First, verify all components work:

```bash
cd /home/moltbot/.openclaw/workspace/dashboard/
python3 test_dashboard.py
```

This will check:
- pygame installation
- Display configuration  
- OpenClaw status detection
- System stats collection
- Todoist integration

## 2. Manual Test Run

Launch the dashboard manually to see it in action:

```bash
./launch.sh
```

**Controls:**
- Press `F2` to force refresh
- Press `ESC` to quit
- Press `F1` to switch to terminal (requires sudo for chvt)

## 3. Configure Todoist (Optional)

If you want Todoist tasks to show up:

1. Get your Todoist API token from https://todoist.com/prefs/integrations

2. Add to ~/.bashrc:
   ```bash
   echo 'export TODOIST_API_TOKEN="your_token_here"' >> ~/.bashrc
   source ~/.bashrc
   ```

3. Test it:
   ```bash
   todoist tasks
   ```

## 4. Auto-start on Boot (Optional)

To have the dashboard start automatically when the Pi boots:

```bash
# Copy service file
mkdir -p ~/.config/systemd/user/
cp dashboard.service ~/.config/systemd/user/

# Enable and start
systemctl --user daemon-reload
systemctl --user enable dashboard.service
systemctl --user start dashboard.service

# Check status
systemctl --user status dashboard.service
```

## 5. Verify It's Working

After auto-start is enabled, the dashboard should appear on the TFT display when the Pi boots.

**Troubleshooting:**

Check service status:
```bash
systemctl --user status dashboard.service
```

View logs:
```bash
journalctl --user -u dashboard.service -f
```

Stop the service:
```bash
systemctl --user stop dashboard.service
```

Disable auto-start:
```bash
systemctl --user disable dashboard.service
```

## File Locations

```
/home/moltbot/.openclaw/workspace/dashboard/
├── dashboard.py          # Main application
├── launch.sh            # Launcher script
├── test_dashboard.py    # Component test
├── dashboard.service    # Systemd service file
├── README.md           # Full documentation
└── INSTALL.md          # This file
```

## What Works Now

✅ Dashboard displays on 480x320 TFT
✅ Shows OpenClaw gateway status
✅ Shows system stats (CPU, RAM, temperature)
✅ Shows current time
✅ Auto-refreshes every 45 seconds
✅ Keyboard shortcuts (F1, F2, ESC)
✅ Dark theme, clean layout
✅ Handles missing Todoist token gracefully

⚠️ Todoist integration requires API token to be set

## Next Steps

1. Run `python3 test_dashboard.py` to verify setup
2. Run `./launch.sh` to test manually
3. Set up Todoist token if desired
4. Enable auto-start if you want it on boot

That's it! Enjoy your dashboard.
