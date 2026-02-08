# Dashboard Iterations - Feb 5, 2026

David asked for 3 iterations to make the Pi 400 dashboard "as pretty and useful as possible."

## Version Summary

| Version | Focus | Key Features |
|---------|-------|--------------|
| v1-v2 | Original | Basic status, terminal embed |
| **v3** | Visual Polish | Nord palette, progress bars, cards, typography |
| **v4** | Functionality | Weather, network, sparklines, scrollable tasks |
| **v5** | UX & Modes | 3 modes, big clock, notifications, animations |

---

## v3 - Visual Polish Edition

**Philosophy:** Make it look good on the small display with a cohesive design.

**Changes:**
- 🎨 Nord-inspired color palette (cohesive, easy on eyes)
- 📊 Progress bars with rounded ends for CPU/Mem/Temp
- 🃏 Card-based layout with subtle borders and rounded corners
- 📝 Better typography hierarchy (title/header/body/small/tiny)
- ⬤ Priority dots for tasks (color-coded P1-P4)
- 🔄 Model badge with color (Opus=purple, Sonnet=blue)
- ⏱️ Time & date in header
- 🦶 Clean footer with controls hint

**Screenshot zones:**
```
[Header: ● OpenClaw [OPUS] ................. 10:30 PM]
[═══════════════════════════════════════════ Feb 05]
┌─────── System ───────┐ ┌─────── Status ───────┐
│ CPU [████████░░] 75% │ │ Gateway: Running     │
│ Mem [██████░░░░] 54% │ │ Heartbeat: Active    │
│ Tmp [███░░░░░░░] 45°C│ │ Uptime: 2h 15m       │
└──────────────────────┘ └──────────────────────┘
┌─────────────── Tasks (3 overdue) ───────────────┐
│ ● Fix the thing that's broken                   │
│ ● Review PR #42                                 │
│ ○ Update documentation                          │
└─────────────────────────────────────────────────┘
[Ctrl+Q] Quit  [Ctrl+R] Refresh            ↻ 15s
```

---

## v4 - Feature-Rich Edition

**Philosophy:** Pack more useful information into the same space.

**Changes:**
- 🌤️ Weather widget (wttr.in - lightweight)
- 🌐 Network status (IP address, wifi strength bars, SSID)
- 📈 CPU sparkline (last 20 readings as mini graph)
- 📜 Scrollable task list (up to 10 tasks, arrow keys to scroll)
- 💾 Disk usage indicator
- 🔘 Visual quick action buttons (decorative)
- ▂▄▆█ Wifi signal strength bars
- 📊 More compact info layout (3 columns)

**New data sources:**
- `curl wttr.in` for weather
- `iwconfig` for wifi signal
- `iwgetid` for SSID
- `df /` for disk usage

---

## v5 - Polish & UX Edition

**Philosophy:** Multiple modes for different needs, with smooth UX.

**Changes:**
- 🔢 **Three modes** (press 1/2/3 to switch):
  1. Dashboard - overview with big clock
  2. Tasks - full task list view
  3. Terminal - embedded bash terminal
- 🕐 Large time display in dashboard mode
- 📈 Dual sparklines (CPU + Temperature history)
- 🔔 Notification area for alerts
- ⌨️ Full keyboard input in terminal mode
- 📜 Scroll bar indicator for tasks
- ✨ Refined colors and spacing
- 🎯 Better visual hierarchy

**Mode Details:**

**Dashboard Mode (1):**
- System card with sparklines
- Status card with network
- Mini task preview
- Big time display with seconds
- Notification area

**Tasks Mode (2):**
- Full 12-task view
- Visual scroll bar
- Priority indicators
- Overdue highlighting

**Terminal Mode (3):**
- Embedded PTY terminal
- Full keyboard input
- Command history
- Blinking cursor

---

## Recommended Version

**For daily use: v5**
- Most polished and versatile
- Switch modes based on need
- Dashboard for glanceable info
- Tasks when focused on work
- Terminal for quick commands

**For simplicity: v3**
- Clean and focused
- Less cognitive load
- No mode switching
- Good "digital clock" vibes

---

## Running

```bash
# Test a version
cd ~/workspace/dashboard
python3 dashboard_v5.py

# Make executable
chmod +x dashboard_v5.py

# Update the service to use v5
sudo systemctl --user edit dashboard

# Change ExecStart to:
# ExecStart=/usr/bin/python3 /home/moltbot/.openclaw/workspace/dashboard/dashboard_v5.py
```

---

## Hardware Notes

- Display: 480x320 (3.5" Waveshare TFT)
- Font: Liberation Mono (good for small screens)
- FPS: 2-4 (saves CPU on Pi 400)
- Refresh: Every 30 seconds
