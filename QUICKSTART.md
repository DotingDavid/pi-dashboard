# 🚀 Quick Start Guide

## TL;DR

```bash
cd /home/moltbot/.openclaw/workspace/dashboard/
./launch.sh
```

Press `ESC` to quit, `F2` to refresh, `F1` for terminal.

---

## First Time Setup

### 1. Test Everything Works
```bash
cd /home/moltbot/.openclaw/workspace/dashboard/
python3 test_dashboard.py
```

Expected output: 4/5 tests pass (Todoist optional)

### 2. Run the Dashboard
```bash
./launch.sh
```

You should see:
- OpenClaw status in top left
- System stats in top right
- Time in header
- "No API token" for Todoist (if token not set)
- Keyboard shortcuts in footer

### 3. Add Todoist (Optional)

Get token from: https://todoist.com/prefs/integrations

```bash
echo 'export TODOIST_API_TOKEN="YOUR_TOKEN_HERE"' >> ~/.bashrc
source ~/.bashrc
```

Restart dashboard to see tasks.

### 4. Make It Auto-Start (Optional)

```bash
cp dashboard.service ~/.config/systemd/user/
systemctl --user enable dashboard.service
systemctl --user start dashboard.service
```

Now it starts on boot!

---

## Troubleshooting

### "pygame not found"
```bash
sudo apt-get install python3-pygame
```

### "Display :0 not found"
Check X is running:
```bash
echo $DISPLAY
ps aux | grep X
```

### Dashboard not showing
Make sure you're viewing the TFT display (not HDMI/SSH)

### Tasks not loading
1. Check token: `echo $TODOIST_API_TOKEN`
2. Test CLI: `todoist tasks`
3. Dashboard will show error message

---

## Controls

- **ESC**: Quit
- **F2**: Force refresh now
- **F1**: Switch to terminal (needs sudo)

---

## Files

All in: `/home/moltbot/.openclaw/workspace/dashboard/`

- `dashboard.py` - Main app
- `launch.sh` - Launcher
- `test_dashboard.py` - Tests
- `README.md` - Full docs
- `INSTALL.md` - Install guide
- `SUMMARY.md` - Build report

---

## What It Shows

```
┌─────────────────────────────────┐
│  OpenClaw Status    │ 02:42 AM │
├─────────────────────┼──────────┤
│ ● Gateway: running  │ CPU: 12% │
│ ● Last HB: < 5m     │ Mem: 340M│
│ ● Model: opus       │ Tmp: 48°C│
├─────────────────────┴──────────┤
│ Todoist (0 tasks)              │
│ No tasks                       │
├────────────────────────────────┤
│ [F1] Terminal  [F2] Refresh    │
└────────────────────────────────┘
```

Updates every 45 seconds automatically.

---

**That's it! Enjoy your dashboard.** 🎉
