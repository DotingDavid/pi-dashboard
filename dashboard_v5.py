#!/usr/bin/env python3
"""
Pi 400 Dashboard v5 - Polish & UX Edition
For 3.5" Waveshare TFT (480x320)

Iteration 3: UX refinements
- Smooth fade transitions
- Status history mini-graphs
- Notification area
- Better visual hierarchy
- Modes: Dashboard / Tasks / Terminal
"""

import pygame
import sys
import os
import subprocess
import json
import time
import socket
import pty
import select
import fcntl
import struct
import termios
from datetime import datetime
from pathlib import Path
from collections import deque

# Configuration
SCREEN_WIDTH = 480
SCREEN_HEIGHT = 320

# Refined color palette
C = {
    # Backgrounds
    'bg': (30, 32, 40),
    'bg_card': (42, 45, 56),
    'bg_hover': (52, 56, 70),
    'bg_input': (25, 27, 33),
    
    # Text
    'text': (200, 205, 215),
    'text_bright': (240, 245, 255),
    'text_dim': (100, 105, 120),
    'text_muted': (70, 75, 88),
    
    # Accents
    'primary': (100, 180, 255),    # Blue
    'success': (120, 210, 140),    # Green
    'warning': (250, 200, 80),     # Yellow/Orange
    'danger': (240, 100, 100),     # Red
    'info': (150, 200, 255),       # Light blue
    'purple': (180, 140, 220),     # Purple
    
    # UI elements
    'border': (60, 65, 80),
    'divider': (50, 54, 66),
}

REFRESH_INTERVAL = 30
MODE_DASHBOARD = 0
MODE_TASKS = 1
MODE_TERMINAL = 2


class MiniTerminal:
    """Embedded terminal for quick commands"""
    def __init__(self, rows=8, cols=52):
        self.rows = rows
        self.cols = cols
        self.master_fd = None
        self.pid = None
        self.buffer = deque(maxlen=50)
        self.prompt = ""
        
    def start(self):
        self.pid, self.master_fd = pty.fork()
        if self.pid == 0:
            # Start in home directory
            os.chdir(os.path.expanduser('~'))
            env = os.environ.copy()
            env['TERM'] = 'dumb'  # Simpler terminal - less escape codes
            env['PS1'] = '$ '     # Super short prompt
            env['HOME'] = os.path.expanduser('~')
            os.execvpe('/bin/bash', ['/bin/bash', '--norc', '--noprofile'], env)
        else:
            flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            size = struct.pack('HHHH', self.rows, self.cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, size)
            time.sleep(0.1)
            self.read()
    
    def write(self, data):
        if self.master_fd:
            try:
                os.write(self.master_fd, data.encode())
            except: pass
    
    def read(self):
        if not self.master_fd: return
        import re
        # Strip ANSI escapes and control chars
        ansi = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])|\r')
        try:
            while True:
                r, _, _ = select.select([self.master_fd], [], [], 0)
                if not r: break
                data = os.read(self.master_fd, 1024)
                if not data: break
                text = ansi.sub('', data.decode('utf-8', errors='replace'))
                # Handle carriage returns and clean up
                text = text.replace('\r\n', '\n').replace('\r', '')
                lines = text.split('\n')
                for i, line in enumerate(lines):
                    # Truncate to terminal width
                    clean = line[:self.cols]
                    if i < len(lines) - 1:
                        # Complete line
                        if clean:
                            self.buffer.append(clean)
                    else:
                        # Last segment - might be partial/prompt
                        self.prompt = clean
        except: pass
    
    def get_lines(self, n):
        self.read()
        lines = list(self.buffer)[-n:]
        while len(lines) < n:
            lines.insert(0, "")
        return lines
    
    def close(self):
        if self.master_fd:
            try: os.close(self.master_fd)
            except: pass
        if self.pid:
            try: os.kill(self.pid, 9)
            except: pass


class DashboardApp:
    def __init__(self):
        pygame.init()
        
        self.screen = pygame.display.set_mode(
            (SCREEN_WIDTH, SCREEN_HEIGHT),
            pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF
        )
        pygame.display.set_caption('OpenClaw Dashboard v5')
        pygame.mouse.set_visible(False)
        
        self.fonts = {
            'xl': pygame.font.SysFont('liberationmono', 24, bold=True),
            'lg': pygame.font.SysFont('liberationmono', 16, bold=True),
            'md': pygame.font.SysFont('liberationmono', 12),
            'sm': pygame.font.SysFont('liberationmono', 10),
            'xs': pygame.font.SysFont('liberationmono', 9),
        }
        
        # State
        self.mode = MODE_DASHBOARD
        self.openclaw = {}
        self.system = {}
        self.network = {}
        self.weather = {}
        self.tasks = []
        self.notifications = deque(maxlen=3)
        self.last_refresh = 0
        
        # History
        self.cpu_hist = deque(maxlen=30)
        self.temp_hist = deque(maxlen=30)
        
        # UI state
        self.task_scroll = 0
        self.fade_alpha = 0
        
        # Terminal
        self.terminal = MiniTerminal()
        
        self.clock = pygame.time.Clock()
    
    def cmd(self, c, timeout=5):
        try:
            r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=timeout)
            return r.stdout.strip(), r.returncode
        except:
            return "", -1
    
    def refresh_openclaw(self):
        out, code = self.cmd("pgrep -f 'openclaw.*gateway'")
        self.openclaw['running'] = code == 0
        
        if self.openclaw['running']:
            cfg = Path.home() / '.openclaw' / 'config.json'
            if cfg.exists():
                try:
                    with open(cfg) as f:
                        c = json.load(f)
                        m = c.get('defaultModel', '')
                        self.openclaw['model'] = 'Opus' if 'opus' in m.lower() else 'Sonnet' if 'sonnet' in m.lower() else m.split('/')[-1][:8]
                except:
                    self.openclaw['model'] = '?'
            
            log = Path.home() / '.openclaw' / 'logs' / 'gateway.log'
            if log.exists():
                try:
                    self.openclaw['hb'] = int((time.time() - log.stat().st_mtime) / 60)
                except:
                    self.openclaw['hb'] = -1
        else:
            self.openclaw['model'] = '-'
            self.openclaw['hb'] = -1
    
    def refresh_system(self):
        # CPU
        out, _ = self.cmd("grep 'cpu ' /proc/stat | awk '{print ($2+$4)*100/($2+$4+$5)}'")
        try:
            self.system['cpu'] = min(100, max(0, float(out)))
        except:
            self.system['cpu'] = 0
        self.cpu_hist.append(self.system['cpu'])
        
        # Memory
        out, _ = self.cmd("free | awk 'NR==2{printf \"%.0f\", $3/$2*100}'")
        try:
            self.system['mem'] = float(out)
        except:
            self.system['mem'] = 0
        
        out, _ = self.cmd("free -h | awk 'NR==2{print $3\"/\"$2}'")
        self.system['mem_str'] = out.replace('i', '') if out else '?'
        
        # Temp
        tp = Path('/sys/class/thermal/thermal_zone0/temp')
        if tp.exists():
            try:
                with open(tp) as f:
                    self.system['temp'] = int(f.read().strip()) / 1000
            except:
                self.system['temp'] = 0
        self.temp_hist.append(self.system.get('temp', 0))
        
        # Disk
        out, _ = self.cmd("df / | awk 'NR==2{print $5}' | tr -d '%'")
        try:
            self.system['disk'] = int(out)
        except:
            self.system['disk'] = 0
    
    def refresh_network(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            self.network['ip'] = s.getsockname()[0]
            s.close()
        except:
            self.network['ip'] = 'Offline'
        
        out, _ = self.cmd("iwconfig wlan0 2>/dev/null | grep Quality")
        import re
        m = re.search(r'Quality=(\d+)/(\d+)', out) if out else None
        self.network['wifi'] = int(100 * int(m.group(1)) / int(m.group(2))) if m else -1
        
        out, _ = self.cmd("iwgetid -r 2>/dev/null")
        self.network['ssid'] = out[:10] if out else None
    
    def refresh_weather(self):
        out, code = self.cmd("curl -s 'wttr.in/?format=%c+%t' 2>/dev/null", timeout=3)
        self.weather['summary'] = out.strip() if code == 0 and out and len(out) < 25 else None
    
    def refresh_tasks(self):
        token = os.environ.get('TODOIST_API_TOKEN')
        if not token:
            rc = Path.home() / '.bashrc'
            if rc.exists():
                with open(rc) as f:
                    for line in f:
                        if 'TODOIST_API_TOKEN' in line and '=' in line:
                            token = line.split('=')[1].strip().strip('"').strip("'")
                            os.environ['TODOIST_API_TOKEN'] = token
                            break
        
        if not token:
            self.tasks = [{'text': 'No API token', 'p': 4}]
            return
        
        out, code = self.cmd("todoist --csv list", timeout=5)
        if code != 0:
            self.tasks = [{'text': 'Fetch error', 'p': 4}]
            return
        
        self.tasks = []
        lines = out.strip().split('\n')
        if len(lines) > 1:
            for line in lines[1:15]:
                parts = line.split(',')
                if len(parts) >= 2:
                    txt = parts[1].strip().strip('"')
                    over = 'overdue' in line.lower()
                    p = 1 if 'p1' in line.lower() else 2 if 'p2' in line.lower() else 3 if 'p3' in line.lower() else 4
                    self.tasks.append({'text': txt, 'p': p, 'over': over})
        
        if not self.tasks:
            self.tasks = [{'text': 'All clear! 🎉', 'p': 4}]
    
    def refresh_all(self):
        self.refresh_openclaw()
        self.refresh_system()
        self.refresh_network()
        self.refresh_weather()
        self.refresh_tasks()
        self.last_refresh = time.time()
    
    def add_notification(self, msg, level='info'):
        self.notifications.append({'msg': msg, 'level': level, 'time': time.time()})
    
    def text(self, txt, font, color, x, y, right=False, center=False):
        s = self.fonts[font].render(txt, True, color)
        if right: x -= s.get_width()
        elif center: x -= s.get_width() // 2
        self.screen.blit(s, (x, y))
        return s.get_width()
    
    def bar(self, x, y, w, h, val, mx, color, bg=None):
        bg = bg or C['bg_hover']
        pygame.draw.rect(self.screen, bg, (x, y, w, h), border_radius=h//2)
        fw = int((val / mx) * w) if mx > 0 else 0
        if fw > 0:
            pygame.draw.rect(self.screen, color, (x, y, max(h, fw), h), border_radius=h//2)
    
    def spark(self, x, y, w, h, data, color):
        if len(data) < 2: return
        pygame.draw.rect(self.screen, C['bg_input'], (x, y, w, h), border_radius=2)
        mx = max(max(data), 1)
        mn = min(data)
        rng = max(mx - mn, 1)
        pts = []
        for i, v in enumerate(data):
            px = x + int((i / (len(data) - 1)) * w)
            py = y + h - 2 - int(((v - mn) / rng) * (h - 4))
            pts.append((px, py))
        if len(pts) >= 2:
            pygame.draw.lines(self.screen, color, False, pts, 2)
    
    def draw_header(self):
        # Header bar
        pygame.draw.rect(self.screen, C['bg_card'], (0, 0, SCREEN_WIDTH, 36))
        
        # Status dot
        running = self.openclaw.get('running', False)
        dot_col = C['success'] if running else C['danger']
        pygame.draw.circle(self.screen, dot_col, (18, 18), 6)
        
        # Title
        self.text("OpenClaw", 'lg', C['text_bright'], 32, 9)
        
        # Model badge
        model = self.openclaw.get('model', '-')
        if model not in ['-', '?']:
            badge_col = C['purple'] if model == 'Opus' else C['primary']
            tw = self.fonts['xs'].size(model)[0]
            pygame.draw.rect(self.screen, badge_col, (120, 11, tw + 10, 14), border_radius=7)
            self.text(model, 'xs', C['bg'], 125, 12)
        
        # Weather
        if self.weather.get('summary'):
            self.text(self.weather['summary'], 'sm', C['text_dim'], 200, 12)
        
        # Time
        now = datetime.now()
        self.text(now.strftime("%I:%M %p").lstrip('0'), 'md', C['text_bright'], SCREEN_WIDTH - 10, 6, right=True)
        self.text(now.strftime("%a, %b %d"), 'xs', C['text_dim'], SCREEN_WIDTH - 10, 21, right=True)
        
        # Bottom border with gradient effect
        pygame.draw.line(self.screen, C['divider'], (0, 36), (SCREEN_WIDTH, 36), 1)
    
    def draw_system_card(self):
        """System metrics with sparklines"""
        x, y, w, h = 8, 44, 200, 115
        
        # Card
        pygame.draw.rect(self.screen, C['bg_card'], (x, y, w, h), border_radius=8)
        
        # Title
        self.text("System", 'sm', C['primary'], x + 10, y + 6)
        cy = y + 24
        
        # CPU with sparkline
        cpu = self.system.get('cpu', 0)
        cpu_col = C['danger'] if cpu > 80 else C['warning'] if cpu > 60 else C['success']
        self.text("CPU", 'xs', C['text_dim'], x + 10, cy)
        self.text(f"{cpu:.0f}%", 'sm', cpu_col, x + 45, cy - 1)
        self.spark(x + 80, cy, 110, 14, list(self.cpu_hist), cpu_col)
        cy += 22
        
        # Memory
        mem = self.system.get('mem', 0)
        mem_col = C['warning'] if mem > 75 else C['info']
        self.text("MEM", 'xs', C['text_dim'], x + 10, cy)
        self.bar(x + 45, cy + 3, 100, 8, mem, 100, mem_col)
        self.text(self.system.get('mem_str', '?'), 'xs', C['text_muted'], x + 150, cy)
        cy += 22
        
        # Temp with sparkline
        temp = self.system.get('temp', 0)
        temp_col = C['danger'] if temp > 70 else C['warning'] if temp > 55 else C['info']
        self.text("TEMP", 'xs', C['text_dim'], x + 10, cy)
        self.text(f"{temp:.0f}°C", 'sm', temp_col, x + 50, cy - 1)
        self.spark(x + 90, cy, 100, 14, list(self.temp_hist), temp_col)
        cy += 22
        
        # Disk
        disk = self.system.get('disk', 0)
        disk_col = C['danger'] if disk > 90 else C['warning'] if disk > 75 else C['success']
        self.text("DISK", 'xs', C['text_dim'], x + 10, cy)
        self.bar(x + 45, cy + 3, 100, 8, disk, 100, disk_col)
        self.text(f"{disk}%", 'xs', C['text_muted'], x + 150, cy)
    
    def draw_status_card(self):
        """OpenClaw status and network"""
        x, y, w, h = 216, 44, 130, 115
        
        pygame.draw.rect(self.screen, C['bg_card'], (x, y, w, h), border_radius=8)
        
        self.text("Status", 'sm', C['primary'], x + 10, y + 6)
        cy = y + 24
        
        # Gateway
        running = self.openclaw.get('running', False)
        gw_txt = "● Online" if running else "○ Offline"
        gw_col = C['success'] if running else C['danger']
        self.text(gw_txt, 'sm', gw_col, x + 10, cy)
        cy += 18
        
        # Heartbeat
        hb = self.openclaw.get('hb', -1)
        if hb >= 0:
            hb_txt = "♥ Active" if hb < 5 else f"♥ {hb}m"
            hb_col = C['success'] if hb < 5 else C['text'] if hb < 30 else C['warning']
        else:
            hb_txt, hb_col = "♥ -", C['text_dim']
        self.text(hb_txt, 'sm', hb_col, x + 10, cy)
        cy += 22
        
        # Network
        self.text("Network", 'xs', C['text_dim'], x + 10, cy)
        cy += 14
        
        ip = self.network.get('ip', '?')
        self.text(ip, 'xs', C['text'], x + 10, cy)
        cy += 14
        
        wifi = self.network.get('wifi', -1)
        if wifi >= 0:
            bars = '▂▄▆█'[:max(1, (wifi + 24) // 25)]
            ssid = self.network.get('ssid', '')
            wifi_txt = f"{bars} {ssid}" if ssid else f"{bars}"
            wifi_col = C['success'] if wifi > 60 else C['warning'] if wifi > 30 else C['danger']
            self.text(wifi_txt, 'xs', wifi_col, x + 10, cy)
        else:
            self.text("⌁ Wired", 'xs', C['info'], x + 10, cy)
    
    def draw_tasks_card(self):
        """Task list with priorities"""
        x, y, w, h = 354, 44, 118, 115
        
        pygame.draw.rect(self.screen, C['bg_card'], (x, y, w, h), border_radius=8)
        
        overdue = sum(1 for t in self.tasks if t.get('over'))
        title = f"Tasks ({overdue}!)" if overdue else f"Tasks"
        title_col = C['warning'] if overdue else C['primary']
        self.text(title, 'sm', title_col, x + 10, y + 6)
        
        cy = y + 24
        visible = self.tasks[self.task_scroll:self.task_scroll + 5]
        
        for t in visible:
            txt = t['text']
            if len(txt) > 12:
                txt = txt[:10] + ".."
            
            p_colors = {1: C['danger'], 2: C['warning'], 3: C['info'], 4: C['text_muted']}
            pygame.draw.circle(self.screen, p_colors.get(t['p'], C['text_muted']), (x + 14, cy + 5), 3)
            
            txt_col = C['warning'] if t.get('over') else C['text']
            self.text(txt, 'xs', txt_col, x + 22, cy)
            cy += 15
        
        # Scroll hint
        if len(self.tasks) > 5:
            self.text("↕", 'xs', C['text_muted'], x + w - 15, y + h - 18)
    
    def draw_quick_bar(self):
        """Quick stats bar"""
        y = 166
        
        pygame.draw.line(self.screen, C['divider'], (8, y), (SCREEN_WIDTH - 8, y), 1)
        y += 8
        
        # Quick stats in a row
        items = [
            (f"CPU {self.system.get('cpu', 0):.0f}%", C['success'] if self.system.get('cpu', 0) < 60 else C['warning']),
            (f"MEM {self.system.get('mem', 0):.0f}%", C['info']),
            (f"{self.system.get('temp', 0):.0f}°C", C['info'] if self.system.get('temp', 0) < 60 else C['warning']),
            (f"DSK {self.system.get('disk', 0)}%", C['success'] if self.system.get('disk', 0) < 80 else C['warning']),
        ]
        
        spacing = SCREEN_WIDTH // len(items)
        for i, (txt, col) in enumerate(items):
            self.text(txt, 'sm', col, spacing // 2 + i * spacing, y, center=True)
    
    def draw_big_time(self):
        """Large time display in dashboard mode"""
        now = datetime.now()
        
        # Big time
        time_str = now.strftime("%I:%M").lstrip('0')
        self.text(time_str, 'xl', C['text_bright'], SCREEN_WIDTH // 2, 210, center=True)
        
        # Seconds ticker
        secs = now.strftime(":%S")
        self.text(secs, 'lg', C['text_dim'], SCREEN_WIDTH // 2 + 70, 213)
        
        # Date
        date_str = now.strftime("%A, %B %d, %Y")
        self.text(date_str, 'sm', C['text_dim'], SCREEN_WIDTH // 2, 250, center=True)
    
    def draw_notifications(self):
        """Show recent notifications"""
        y = 275
        now = time.time()
        
        for n in list(self.notifications):
            if now - n['time'] > 30:  # Expire after 30s
                continue
            
            level_colors = {'info': C['info'], 'warn': C['warning'], 'error': C['danger'], 'success': C['success']}
            col = level_colors.get(n['level'], C['text'])
            
            self.text(f"• {n['msg']}", 'xs', col, 10, y)
            y += 14
    
    def draw_footer(self):
        y = SCREEN_HEIGHT - 20
        pygame.draw.line(self.screen, C['divider'], (8, y - 4), (SCREEN_WIDTH - 8, y - 4), 1)
        
        # Mode tabs
        modes = ["Dashboard", "Tasks", "Terminal"]
        mode_x = 10
        for i, m in enumerate(modes):
            col = C['primary'] if i == self.mode else C['text_dim']
            w = self.text(f"[{i+1}]{m}", 'xs', col, mode_x, y)
            mode_x += w + 15
        
        # Refresh indicator
        since = int(time.time() - self.last_refresh)
        self.text(f"↻{since}s", 'xs', C['text_muted'], SCREEN_WIDTH - 10, y, right=True)
    
    def draw_task_mode(self):
        """Full task list view"""
        self.text("Tasks", 'lg', C['text_bright'], 10, 44)
        
        overdue = sum(1 for t in self.tasks if t.get('over'))
        if overdue:
            self.text(f"({overdue} overdue)", 'sm', C['warning'], 80, 48)
        
        y = 70
        visible = self.tasks[self.task_scroll:self.task_scroll + 12]
        
        for t in visible:
            txt = t['text']
            if len(txt) > 50:
                txt = txt[:47] + "..."
            
            p_colors = {1: C['danger'], 2: C['warning'], 3: C['info'], 4: C['text_muted']}
            pygame.draw.circle(self.screen, p_colors.get(t['p'], C['text_muted']), (18, y + 6), 4)
            
            txt_col = C['warning'] if t.get('over') else C['text']
            self.text(txt, 'sm', txt_col, 30, y)
            y += 18
        
        # Scroll bar
        if len(self.tasks) > 12:
            total = len(self.tasks)
            bar_h = max(20, 180 * 12 // total)
            bar_y = 70 + int((self.task_scroll / (total - 12)) * (180 - bar_h))
            pygame.draw.rect(self.screen, C['border'], (SCREEN_WIDTH - 8, bar_y, 4, bar_h), border_radius=2)
    
    def draw_terminal_mode(self):
        """Terminal view"""
        if not self.terminal.master_fd:
            self.terminal.start()
        
        self.text("Terminal", 'lg', C['text_bright'], 10, 44)
        self.text("(type commands, Ctrl+C to cancel)", 'xs', C['text_dim'], 100, 48)
        
        # Terminal area
        pygame.draw.rect(self.screen, C['bg_input'], (8, 68, SCREEN_WIDTH - 16, 200), border_radius=4)
        
        lines = self.terminal.get_lines(11)
        y = 75
        for line in lines:
            # Truncate to fit display
            self.text(line[:52], 'sm', C['text'], 14, y)
            y += 16
        
        # Prompt with cursor
        prompt = self.terminal.prompt or '$ '
        # Truncate prompt if too long
        if len(prompt) > 50:
            prompt = '...' + prompt[-47:]
        self.text(prompt, 'sm', C['success'], 14, y)
        # Blinking cursor
        if int(time.time() * 2) % 2:
            cursor_x = 14 + self.fonts['sm'].size(prompt)[0]
            pygame.draw.rect(self.screen, C['primary'], (cursor_x, y, 8, 12))
    
    def draw(self):
        self.screen.fill(C['bg'])
        
        self.draw_header()
        
        if self.mode == MODE_DASHBOARD:
            self.draw_system_card()
            self.draw_status_card()
            self.draw_tasks_card()
            self.draw_quick_bar()
            self.draw_big_time()
            self.draw_notifications()
        elif self.mode == MODE_TASKS:
            self.draw_task_mode()
        elif self.mode == MODE_TERMINAL:
            self.draw_terminal_mode()
        
        self.draw_footer()
        
        pygame.display.flip()
    
    def handle_key(self, event):
        # Mode switching
        if event.key == pygame.K_1:
            self.mode = MODE_DASHBOARD
        elif event.key == pygame.K_2:
            self.mode = MODE_TASKS
        elif event.key == pygame.K_3:
            self.mode = MODE_TERMINAL
            if not self.terminal.master_fd:
                self.terminal.start()
        
        # Global keys
        elif event.key == pygame.K_q and event.mod & pygame.KMOD_CTRL:
            return False
        elif event.key == pygame.K_r and event.mod & pygame.KMOD_CTRL:
            self.refresh_all()
        
        # Scrolling
        elif event.key == pygame.K_UP:
            self.task_scroll = max(0, self.task_scroll - 1)
        elif event.key == pygame.K_DOWN:
            max_scroll = max(0, len(self.tasks) - (12 if self.mode == MODE_TASKS else 5))
            self.task_scroll = min(max_scroll, self.task_scroll + 1)
        
        # Terminal input
        elif self.mode == MODE_TERMINAL:
            if event.key == pygame.K_RETURN:
                self.terminal.write('\n')
            elif event.key == pygame.K_BACKSPACE:
                self.terminal.write('\x7f')
            elif event.key == pygame.K_TAB:
                self.terminal.write('\t')
            elif event.unicode:
                self.terminal.write(event.unicode)
        
        return True
    
    def run(self):
        running = True
        self.refresh_all()
        
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if not self.handle_key(event):
                        running = False
            
            if time.time() - self.last_refresh > REFRESH_INTERVAL:
                self.refresh_all()
            
            self.draw()
            self.clock.tick(4 if self.mode == MODE_TERMINAL else 2)
        
        self.terminal.close()
        pygame.quit()


if __name__ == '__main__':
    try:
        app = DashboardApp()
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
