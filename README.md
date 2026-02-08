# Pi 400 Dashboard for Waveshare 3.5" TFT

A Pygame-based dashboard that displays OpenClaw status, system stats, and Todoist tasks on a 3.5" TFT screen (480x320).

## Features

- **OpenClaw Status**: Gateway running state, model info, last heartbeat
- **System Stats**: CPU usage, memory usage, temperature
- **Todoist Tasks**: Top 5 tasks with overdue highlighting
- **Current Time**: 12-hour format in header
- **Auto-refresh**: Every 45 seconds
- **Keyboard Shortcuts**:
  - `F1`: Switch to terminal (VT2)
  - `F2`: Force refresh
  - `ESC`: Quit dashboard

## Requirements

### Software
- Python 3
- pygame: `sudo apt-get install python3-pygame`
- todoist-python: `pip3 install todoist-python`
- TODOIST_API_TOKEN environment variable (set in ~/.bashrc)

### Hardware
- Raspberry Pi 400 (or Pi with keyboard)
- Waveshare 3.5" TFT (or compatible)
- Display configured with `dtoverlay=tft35a:rotate=90`
- X server running on DISPLAY=:0

## Installation

1. Files are already in `/home/moltbot/.openclaw/workspace/dashboard/`

2. Install dependencies:
   ```bash
   sudo apt-get install python3-pygame
   pip3 install todoist-python
   ```

3. Ensure TODOIST_API_TOKEN is set:
   ```bash
   echo $TODOIST_API_TOKEN
   ```

## Usage

### Manual Launch
```bash
cd /home/moltbot/.openclaw/workspace/dashboard/
./launch.sh
```

Or directly:
```bash
python3 /home/moltbot/.openclaw/workspace/dashboard/dashboard.py
```

### Auto-start on Boot (Optional)

Create a systemd user service:

```bash
mkdir -p ~/.config/systemd/user/
cat > ~/.config/systemd/user/dashboard.service << 'EOF'
[Unit]
Description=Pi 400 Dashboard
After=graphical.target

[Service]
Environment="DISPLAY=:0"
ExecStart=/home/moltbot/.openclaw/workspace/dashboard/launch.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable dashboard.service
systemctl --user start dashboard.service
```

## Layout

```
┌─────────────────────────────────┐
│  OpenClaw Status    │ 2:42 AM  │
├─────────────────────┼──────────┤
│ ● Gateway: running  │ CPU: 12% │
│ ● Last HB: 2m ago   │ Mem: 340M│
│ ● Model: opus       │ Tmp: 48°C│
├─────────────────────┴──────────┤
│ Todoist (3 overdue)            │
│ • Warm oil in towel machine    │
│ • MAC USA                      │
│ • Make Badges                  │
├────────────────────────────────┤
│ [F1] Terminal  [F2] Refresh    │
└────────────────────────────────┘
```

## Theme

- **Dark theme**: Easy on eyes, OLED-friendly
- **Color scheme**:
  - Background: Dark blue-gray (#14141A)
  - Text: Light gray (#DCDCDC)
  - Headers: Blue (#6496C8)
  - Status OK: Green (#50C878)
  - Errors/Overdue: Red (#DC5050)
  - Muted: Gray (#787882)

## Customization

Edit `dashboard.py` to customize:
- `REFRESH_INTERVAL`: Auto-refresh time (default: 45 seconds)
- Colors: `BG_COLOR`, `TEXT_COLOR`, etc.
- Font sizes: `font_large`, `font_medium`, `font_small`
- Task count: Change `[:5]` to show more/fewer tasks

## Troubleshooting

### Display not showing
- Check X is running: `echo $DISPLAY` should show `:0`
- Verify framebuffer: `ls /dev/fb*`
- Test X display: `DISPLAY=:0 xeyes`

### Todoist not loading
- Check API token: `echo $TODOIST_API_TOKEN`
- Test CLI: `todoist tasks`
- Dashboard will show error message if token missing

### F1 terminal switch not working
- Requires sudo permissions for `chvt` command
- Alternative: SSH into Pi or use second terminal

### Fonts look wrong
- Liberation Mono should be available by default
- If missing: `sudo apt-get install fonts-liberation`

## Files

- `dashboard.py` - Main dashboard application
- `launch.sh` - Launcher script (handles environment)
- `README.md` - This file

## Performance

- Runs at 1 FPS when idle (very low CPU usage)
- Refresh operations take 1-3 seconds
- Typical CPU usage: < 5%
- Memory footprint: ~30-50MB

## Future Enhancements

Possible additions:
- Unread message count (from Discord/WhatsApp)
- Weather info
- Calendar events
- Network status (WiFi/Ethernet)
- Custom status indicators
- Touch screen support (if enabled)
