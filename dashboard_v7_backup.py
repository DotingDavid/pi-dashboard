#!/usr/bin/env python3
"""
Pi 400 Dashboard v7 - Chat Mode Edition
For 3.5" Waveshare TFT (480x320)

New: Dedicated chat interface for messaging OpenClaw directly.
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
import threading
from datetime import datetime
from pathlib import Path
from collections import deque

import pyte

# Configuration
SCREEN_WIDTH = 480
SCREEN_HEIGHT = 320

# Terminal dimensions
TERM_COLS = 58
TERM_ROWS = 14

# Color palette
C = {
    'bg': (30, 32, 40),
    'bg_card': (42, 45, 56),
    'bg_hover': (52, 56, 70),
    'bg_term': (20, 22, 28),
    'bg_input': (35, 38, 48),
    
    'text': (200, 205, 215),
    'text_bright': (240, 245, 255),
    'text_dim': (100, 105, 120),
    'text_muted': (70, 75, 88),
    
    'primary': (100, 180, 255),
    'success': (120, 210, 140),
    'warning': (250, 200, 80),
    'danger': (240, 100, 100),
    'info': (150, 200, 255),
    'purple': (180, 140, 220),
    
    'border': (60, 65, 80),
    'divider': (50, 54, 66),
    'cursor': (100, 180, 255),
    
    'user_msg': (100, 180, 255),
    'bot_msg': (120, 210, 140),
}

ANSI_COLORS = {
    'black': (40, 42, 54),
    'red': (255, 85, 85),
    'green': (80, 250, 123),
    'brown': (241, 250, 140),
    'blue': (98, 114, 164),
    'magenta': (255, 121, 198),
    'cyan': (139, 233, 253),
    'white': (248, 248, 242),
    'default': (200, 205, 215),
}

REFRESH_INTERVAL = 30
MODE_DASHBOARD = 0
MODE_TASKS = 1
MODE_TERMINAL = 2
MODE_CHAT = 3


class ChatMessage:
    def __init__(self, text, is_user=True, timestamp=None, msg_id=None):
        self.text = text
        self.is_user = is_user
        self.timestamp = timestamp or datetime.now()
        self.msg_id = msg_id


class ChatInterface:
    """Manages chat with OpenClaw via Discord"""
    
    # Discord channel for Pi chat
    DISCORD_CHANNEL = "1469210966083244081"  # #pi-chat channel
    
    def __init__(self):
        self.messages = deque(maxlen=50)
        self.input_text = ""
        self.input_cursor = 0
        self.scroll_offset = 0
        self.waiting_response = False
        self.response_thread = None
        self.last_bot_msg_id = None
        self.poll_thread = None
        self.polling = False
        
    def add_message(self, text, is_user=True, msg_id=None):
        self.messages.append(ChatMessage(text, is_user, msg_id=msg_id))
        self.scroll_offset = 0  # Auto-scroll to bottom
        
    def send_message(self):
        """Send current input to OpenClaw via Discord"""
        if not self.input_text.strip() or self.waiting_response:
            return
            
        msg = self.input_text.strip()
        self.add_message(f"[Pi] {msg}", is_user=True)
        self.input_text = ""
        self.input_cursor = 0
        self.waiting_response = True
        
        # Send in background thread
        self.response_thread = threading.Thread(target=self._send_async, args=(msg,))
        self.response_thread.daemon = True
        self.response_thread.start()
    
    def _send_async(self, msg):
        """Send message to Discord and poll for response"""
        try:
            # Send via openclaw message command
            result = subprocess.run(
                ['openclaw', 'message', 'send', 
                 '--channel', 'discord',
                 '--target', self.DISCORD_CHANNEL,
                 '--message', f'[Pi Chat] {msg}'],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=os.path.expanduser('~')
            )
            
            if result.returncode != 0:
                error = result.stderr.strip() if result.stderr else 'Send failed'
                self.add_message(f"[Send error: {error[:50]}]", is_user=False)
                self.waiting_response = False
                return
            
            # Poll for response (wait up to 60 seconds)
            self._poll_for_response()
                
        except subprocess.TimeoutExpired:
            self.add_message("[Send timeout]", is_user=False)
        except Exception as e:
            self.add_message(f"[Error: {str(e)[:40]}]", is_user=False)
        
        self.waiting_response = False
    
    def _poll_for_response(self):
        """Poll Discord for bot response"""
        start_time = time.time()
        max_wait = 90  # seconds
        poll_interval = 2  # seconds
        
        while time.time() - start_time < max_wait:
            time.sleep(poll_interval)
            
            try:
                # Read recent messages from channel
                result = subprocess.run(
                    ['openclaw', 'message', 'read',
                     '--channel', 'discord', 
                     '--target', self.DISCORD_CHANNEL,
                     '--limit', '5',
                     '--json'],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=os.path.expanduser('~')
                )
                
                if result.returncode == 0 and result.stdout.strip():
                    try:
                        data = json.loads(result.stdout)
                        messages = data.get('messages', [])
                        
                        for m in messages:
                            # Look for bot response (not from user, after our message)
                            author = m.get('author', {})
                            is_bot = author.get('bot', False)
                            content = m.get('content', '')
                            msg_id = m.get('id')
                            
                            # Skip if it's our own message or already seen
                            if '[Pi Chat]' in content:
                                continue
                            if msg_id == self.last_bot_msg_id:
                                continue
                            
                            # Found a bot response!
                            if is_bot and content:
                                self.last_bot_msg_id = msg_id
                                # Truncate long responses for display
                                if len(content) > 200:
                                    content = content[:197] + "..."
                                self.add_message(content, is_user=False, msg_id=msg_id)
                                return
                    except json.JSONDecodeError:
                        pass
                        
            except:
                pass
        
        self.add_message("[No response - check Discord]", is_user=False)
    
    def handle_key(self, event):
        """Handle keyboard input for chat"""
        if event.key == pygame.K_RETURN:
            self.send_message()
        elif event.key == pygame.K_BACKSPACE:
            if self.input_cursor > 0:
                self.input_text = self.input_text[:self.input_cursor-1] + self.input_text[self.input_cursor:]
                self.input_cursor -= 1
        elif event.key == pygame.K_DELETE:
            if self.input_cursor < len(self.input_text):
                self.input_text = self.input_text[:self.input_cursor] + self.input_text[self.input_cursor+1:]
        elif event.key == pygame.K_LEFT:
            self.input_cursor = max(0, self.input_cursor - 1)
        elif event.key == pygame.K_RIGHT:
            self.input_cursor = min(len(self.input_text), self.input_cursor + 1)
        elif event.key == pygame.K_HOME:
            self.input_cursor = 0
        elif event.key == pygame.K_END:
            self.input_cursor = len(self.input_text)
        elif event.key == pygame.K_UP:
            # Scroll up
            self.scroll_offset = min(self.scroll_offset + 1, max(0, len(self.messages) - 5))
        elif event.key == pygame.K_DOWN:
            # Scroll down
            self.scroll_offset = max(0, self.scroll_offset - 1)
        elif event.key == pygame.K_ESCAPE:
            # Clear input
            self.input_text = ""
            self.input_cursor = 0
        elif event.unicode and len(event.unicode) == 1 and ord(event.unicode) >= 32:
            # Regular character
            self.input_text = self.input_text[:self.input_cursor] + event.unicode + self.input_text[self.input_cursor:]
            self.input_cursor += 1
    
    def clear_history(self):
        self.messages.clear()
        self.scroll_offset = 0


class PyteTerminal:
    """Terminal emulator using pyte"""
    
    def __init__(self, cols=TERM_COLS, rows=TERM_ROWS):
        self.cols = cols
        self.rows = rows
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.Stream(self.screen)
        self.master_fd = None
        self.pid = None
        self.started = False
        
    def start(self):
        if self.started:
            return
            
        self.pid, self.master_fd = pty.fork()
        
        if self.pid == 0:
            os.chdir(os.path.expanduser('~'))
            env = os.environ.copy()
            env['TERM'] = 'xterm-256color'
            env['COLUMNS'] = str(self.cols)
            env['LINES'] = str(self.rows)
            os.execvpe('/bin/bash', ['/bin/bash'], env)
        else:
            flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            size = struct.pack('HHHH', self.rows, self.cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, size)
            self.started = True
            time.sleep(0.1)
            self.read()
    
    def write(self, data):
        if self.master_fd:
            try:
                os.write(self.master_fd, data.encode() if isinstance(data, str) else data)
            except:
                pass
    
    def read(self):
        if not self.master_fd:
            return
        try:
            while True:
                r, _, _ = select.select([self.master_fd], [], [], 0)
                if not r:
                    break
                data = os.read(self.master_fd, 4096)
                if not data:
                    break
                self.stream.feed(data.decode('utf-8', errors='replace'))
        except:
            pass
    
    def get_display(self):
        self.read()
        lines = []
        for y in range(self.rows):
            line = []
            for x in range(self.cols):
                char = self.screen.buffer[y][x]
                line.append({
                    'char': char.data if char.data else ' ',
                    'fg': char.fg if char.fg != 'default' else 'default',
                    'bold': char.bold,
                    'reverse': char.reverse,
                })
            lines.append(line)
        return lines
    
    def get_cursor(self):
        return (self.screen.cursor.x, self.screen.cursor.y)
    
    def close(self):
        if self.master_fd:
            try:
                os.close(self.master_fd)
            except:
                pass
        if self.pid:
            try:
                os.kill(self.pid, 9)
            except:
                pass
        self.started = False


class DashboardApp:
    def __init__(self):
        pygame.init()
        
        self.screen = pygame.display.set_mode(
            (SCREEN_WIDTH, SCREEN_HEIGHT),
            pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF
        )
        pygame.display.set_caption('OpenClaw Dashboard v7')
        pygame.mouse.set_visible(False)
        
        self.fonts = {
            'xl': pygame.font.SysFont('liberationmono', 24, bold=True),
            'lg': pygame.font.SysFont('liberationmono', 16, bold=True),
            'md': pygame.font.SysFont('liberationmono', 12),
            'sm': pygame.font.SysFont('liberationmono', 10),
            'xs': pygame.font.SysFont('liberationmono', 9),
            'term': pygame.font.SysFont('liberationmono', 11),
            'chat': pygame.font.SysFont('liberationmono', 11),
        }
        
        self.char_width = self.fonts['term'].size('M')[0]
        self.char_height = self.fonts['term'].get_linesize()
        
        # State
        self.mode = MODE_DASHBOARD
        self.openclaw = {}
        self.system = {}
        self.network = {}
        self.weather = {}
        self.tasks = []
        self.last_refresh = 0
        
        # History
        self.cpu_hist = deque(maxlen=30)
        self.temp_hist = deque(maxlen=30)
        
        # UI state
        self.task_scroll = 0
        self.selected_button = 0
        
        # Terminal and Chat
        self.terminal = None
        self.chat = ChatInterface()
        
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
        out, _ = self.cmd("grep 'cpu ' /proc/stat | awk '{print ($2+$4)*100/($2+$4+$5)}'")
        try:
            self.system['cpu'] = min(100, max(0, float(out)))
        except:
            self.system['cpu'] = 0
        self.cpu_hist.append(self.system['cpu'])
        
        out, _ = self.cmd("free | awk 'NR==2{printf \"%.0f\", $3/$2*100}'")
        try:
            self.system['mem'] = float(out)
        except:
            self.system['mem'] = 0
        
        out, _ = self.cmd("free -h | awk 'NR==2{print $3\"/\"$2}'")
        self.system['mem_str'] = out.replace('i', '') if out else '?'
        
        tp = Path('/sys/class/thermal/thermal_zone0/temp')
        if tp.exists():
            try:
                with open(tp) as f:
                    self.system['temp'] = int(f.read().strip()) / 1000
            except:
                self.system['temp'] = 0
        self.temp_hist.append(self.system.get('temp', 0))
        
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
        pygame.draw.rect(self.screen, C['bg_term'], (x, y, w, h), border_radius=2)
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
    
    def draw_button(self, x, y, w, h, text, selected=False, color=None):
        """Draw a button"""
        color = color or C['primary']
        bg = C['bg_hover'] if selected else C['bg_card']
        border = color if selected else C['border']
        
        pygame.draw.rect(self.screen, bg, (x, y, w, h), border_radius=4)
        pygame.draw.rect(self.screen, border, (x, y, w, h), width=1, border_radius=4)
        
        text_color = color if selected else C['text_dim']
        self.text(text, 'xs', text_color, x + w//2, y + h//2 - 5, center=True)
        
        return pygame.Rect(x, y, w, h)
    
    def draw_header(self):
        pygame.draw.rect(self.screen, C['bg_card'], (0, 0, SCREEN_WIDTH, 36))
        
        running = self.openclaw.get('running', False)
        dot_col = C['success'] if running else C['danger']
        pygame.draw.circle(self.screen, dot_col, (18, 18), 6)
        
        self.text("OpenClaw", 'lg', C['text_bright'], 32, 9)
        
        model = self.openclaw.get('model', '-')
        if model not in ['-', '?']:
            badge_col = C['purple'] if model == 'Opus' else C['primary']
            tw = self.fonts['xs'].size(model)[0]
            pygame.draw.rect(self.screen, badge_col, (120, 11, tw + 10, 14), border_radius=7)
            self.text(model, 'xs', C['bg'], 125, 12)
        
        if self.weather.get('summary'):
            self.text(self.weather['summary'], 'sm', C['text_dim'], 200, 12)
        
        now = datetime.now()
        self.text(now.strftime("%I:%M %p").lstrip('0'), 'md', C['text_bright'], SCREEN_WIDTH - 10, 6, right=True)
        self.text(now.strftime("%a, %b %d"), 'xs', C['text_dim'], SCREEN_WIDTH - 10, 21, right=True)
        
        pygame.draw.line(self.screen, C['divider'], (0, 36), (SCREEN_WIDTH, 36), 1)
    
    def draw_system_card(self):
        x, y, w, h = 8, 44, 200, 115
        pygame.draw.rect(self.screen, C['bg_card'], (x, y, w, h), border_radius=8)
        
        self.text("System", 'sm', C['primary'], x + 10, y + 6)
        cy = y + 24
        
        cpu = self.system.get('cpu', 0)
        cpu_col = C['danger'] if cpu > 80 else C['warning'] if cpu > 60 else C['success']
        self.text("CPU", 'xs', C['text_dim'], x + 10, cy)
        self.text(f"{cpu:.0f}%", 'sm', cpu_col, x + 45, cy - 1)
        self.spark(x + 80, cy, 110, 14, list(self.cpu_hist), cpu_col)
        cy += 22
        
        mem = self.system.get('mem', 0)
        mem_col = C['warning'] if mem > 75 else C['info']
        self.text("MEM", 'xs', C['text_dim'], x + 10, cy)
        self.bar(x + 45, cy + 3, 100, 8, mem, 100, mem_col)
        self.text(self.system.get('mem_str', '?'), 'xs', C['text_muted'], x + 150, cy)
        cy += 22
        
        temp = self.system.get('temp', 0)
        temp_col = C['danger'] if temp > 70 else C['warning'] if temp > 55 else C['info']
        self.text("TEMP", 'xs', C['text_dim'], x + 10, cy)
        self.text(f"{temp:.0f}°C", 'sm', temp_col, x + 50, cy - 1)
        self.spark(x + 90, cy, 100, 14, list(self.temp_hist), temp_col)
        cy += 22
        
        disk = self.system.get('disk', 0)
        disk_col = C['danger'] if disk > 90 else C['warning'] if disk > 75 else C['success']
        self.text("DISK", 'xs', C['text_dim'], x + 10, cy)
        self.bar(x + 45, cy + 3, 100, 8, disk, 100, disk_col)
        self.text(f"{disk}%", 'xs', C['text_muted'], x + 150, cy)
    
    def draw_status_card(self):
        x, y, w, h = 216, 44, 130, 115
        pygame.draw.rect(self.screen, C['bg_card'], (x, y, w, h), border_radius=8)
        
        self.text("Status", 'sm', C['primary'], x + 10, y + 6)
        cy = y + 24
        
        running = self.openclaw.get('running', False)
        gw_txt = "● Online" if running else "○ Offline"
        gw_col = C['success'] if running else C['danger']
        self.text(gw_txt, 'sm', gw_col, x + 10, cy)
        cy += 18
        
        hb = self.openclaw.get('hb', -1)
        if hb >= 0:
            hb_txt = "♥ Active" if hb < 5 else f"♥ {hb}m"
            hb_col = C['success'] if hb < 5 else C['text'] if hb < 30 else C['warning']
        else:
            hb_txt, hb_col = "♥ -", C['text_dim']
        self.text(hb_txt, 'sm', hb_col, x + 10, cy)
        cy += 22
        
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
        
        if len(self.tasks) > 5:
            self.text("↕", 'xs', C['text_muted'], x + w - 15, y + h - 18)
    
    def draw_quick_bar(self):
        y = 166
        pygame.draw.line(self.screen, C['divider'], (8, y), (SCREEN_WIDTH - 8, y), 1)
        y += 8
        
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
        now = datetime.now()
        time_str = now.strftime("%I:%M").lstrip('0')
        self.text(time_str, 'xl', C['text_bright'], SCREEN_WIDTH // 2, 210, center=True)
        secs = now.strftime(":%S")
        self.text(secs, 'lg', C['text_dim'], SCREEN_WIDTH // 2 + 70, 213)
        date_str = now.strftime("%A, %B %d, %Y")
        self.text(date_str, 'sm', C['text_dim'], SCREEN_WIDTH // 2, 250, center=True)
    
    def draw_footer(self):
        y = SCREEN_HEIGHT - 20
        pygame.draw.line(self.screen, C['divider'], (8, y - 4), (SCREEN_WIDTH - 8, y - 4), 1)
        
        modes = ["Dash", "Tasks", "Term", "Chat"]
        mode_x = 10
        for i, m in enumerate(modes):
            col = C['primary'] if i == self.mode else C['text_dim']
            w = self.text(f"[{i+1}]{m}", 'xs', col, mode_x, y)
            mode_x += w + 10
        
        since = int(time.time() - self.last_refresh)
        self.text(f"↻{since}s", 'xs', C['text_muted'], SCREEN_WIDTH - 10, y, right=True)
    
    def draw_task_mode(self):
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
        
        if len(self.tasks) > 12:
            total = len(self.tasks)
            bar_h = max(20, 180 * 12 // total)
            bar_y = 70 + int((self.task_scroll / max(1, total - 12)) * (180 - bar_h))
            pygame.draw.rect(self.screen, C['border'], (SCREEN_WIDTH - 8, bar_y, 4, bar_h), border_radius=2)
    
    def draw_terminal_mode(self):
        if self.terminal is None:
            self.terminal = PyteTerminal(TERM_COLS, TERM_ROWS)
        
        if not self.terminal.started:
            self.terminal.start()
        
        self.text("Terminal", 'lg', C['text_bright'], 10, 44)
        self.text("(Ctrl+Q: back)", 'xs', C['text_dim'], 100, 48)
        
        term_x = 8
        term_y = 68
        term_w = SCREEN_WIDTH - 16
        term_h = TERM_ROWS * self.char_height + 8
        
        pygame.draw.rect(self.screen, C['bg_term'], (term_x, term_y, term_w, term_h), border_radius=4)
        
        display = self.terminal.get_display()
        cursor_x, cursor_y = self.terminal.get_cursor()
        
        for row_idx, row in enumerate(display):
            for col_idx, cell in enumerate(row):
                char = cell['char']
                fg_name = cell['fg'] if cell['fg'] else 'default'
                fg_color = ANSI_COLORS.get(fg_name, ANSI_COLORS['default'])
                
                if cell['bold']:
                    fg_color = tuple(min(255, c + 50) for c in fg_color)
                
                if cell['reverse']:
                    fg_color, bg_color = C['bg_term'], fg_color
                    pygame.draw.rect(self.screen, bg_color, 
                        (term_x + 4 + col_idx * self.char_width,
                         term_y + 4 + row_idx * self.char_height,
                         self.char_width, self.char_height))
                
                if char and char != ' ':
                    char_surface = self.fonts['term'].render(char, True, fg_color)
                    self.screen.blit(char_surface, 
                        (term_x + 4 + col_idx * self.char_width,
                         term_y + 4 + row_idx * self.char_height))
        
        if int(time.time() * 2) % 2:
            cursor_px = term_x + 4 + cursor_x * self.char_width
            cursor_py = term_y + 4 + cursor_y * self.char_height
            pygame.draw.rect(self.screen, C['cursor'], 
                (cursor_px, cursor_py, self.char_width, self.char_height))
            
            if cursor_y < len(display) and cursor_x < len(display[cursor_y]):
                cell = display[cursor_y][cursor_x]
                if cell['char'] and cell['char'] != ' ':
                    char_surface = self.fonts['term'].render(cell['char'], True, C['bg_term'])
                    self.screen.blit(char_surface, (cursor_px, cursor_py))
    
    def draw_chat_mode(self):
        """Draw the chat interface"""
        self.text("Chat", 'lg', C['text_bright'], 10, 44)
        
        if self.chat.waiting_response:
            self.text("(waiting...)", 'xs', C['warning'], 60, 48)
        else:
            self.text("(Enter: send, ↑↓: scroll)", 'xs', C['text_dim'], 60, 48)
        
        # Message area
        msg_x = 8
        msg_y = 65
        msg_w = SCREEN_WIDTH - 16
        msg_h = 170
        
        pygame.draw.rect(self.screen, C['bg_term'], (msg_x, msg_y, msg_w, msg_h), border_radius=4)
        
        # Draw messages
        messages = list(self.chat.messages)
        if self.chat.scroll_offset > 0 and len(messages) > 0:
            messages = messages[:-(self.chat.scroll_offset)]
        
        # Word wrap and draw messages from bottom up
        line_height = 14
        max_chars = 54
        y = msg_y + msg_h - 10
        
        for msg in reversed(messages[-10:]):  # Show last 10 messages
            prefix = "You: " if msg.is_user else "Bot: "
            color = C['user_msg'] if msg.is_user else C['bot_msg']
            
            # Word wrap
            full_text = prefix + msg.text
            lines = []
            while len(full_text) > max_chars:
                # Find break point
                break_at = full_text[:max_chars].rfind(' ')
                if break_at == -1:
                    break_at = max_chars
                lines.append(full_text[:break_at])
                full_text = full_text[break_at:].lstrip()
            if full_text:
                lines.append(full_text)
            
            # Draw lines bottom-up
            for line in reversed(lines):
                y -= line_height
                if y < msg_y + 5:
                    break
                self.text(line, 'chat', color, msg_x + 8, y)
            
            if y < msg_y + 5:
                break
            y -= 4  # Gap between messages
        
        # Input area
        input_y = msg_y + msg_h + 5
        input_h = 24
        
        pygame.draw.rect(self.screen, C['bg_input'], (msg_x, input_y, msg_w, input_h), border_radius=4)
        pygame.draw.rect(self.screen, C['border'], (msg_x, input_y, msg_w, input_h), width=1, border_radius=4)
        
        # Draw input text
        display_text = self.chat.input_text
        cursor_offset = self.chat.input_cursor
        
        # Scroll input if too long
        max_input_chars = 50
        if len(display_text) > max_input_chars:
            start = max(0, cursor_offset - max_input_chars + 10)
            display_text = display_text[start:start + max_input_chars]
            cursor_offset = cursor_offset - start
        
        self.text("> " + display_text, 'chat', C['text'], msg_x + 8, input_y + 6)
        
        # Cursor
        if int(time.time() * 2) % 2:
            cursor_x = msg_x + 8 + self.fonts['chat'].size("> " + display_text[:cursor_offset])[0]
            pygame.draw.rect(self.screen, C['cursor'], (cursor_x, input_y + 5, 2, 14))
        
        # Buttons
        btn_y = input_y + input_h + 5
        btn_w = 55
        btn_h = 20
        btn_gap = 5
        
        buttons = [("Send", C['success']), ("Clear", C['warning']), ("Stop", C['danger'])]
        for i, (label, color) in enumerate(buttons):
            self.draw_button(msg_x + i * (btn_w + btn_gap), btn_y, btn_w, btn_h, label, 
                           selected=(i == self.selected_button), color=color)
    
    def handle_key(self, event):
        # Mode switching
        if self.mode not in [MODE_TERMINAL, MODE_CHAT] or (event.mod & pygame.KMOD_CTRL):
            if event.key == pygame.K_1:
                self.mode = MODE_DASHBOARD
                return True
            elif event.key == pygame.K_2:
                self.mode = MODE_TASKS
                return True
            elif event.key == pygame.K_3:
                self.mode = MODE_TERMINAL
                return True
            elif event.key == pygame.K_4:
                self.mode = MODE_CHAT
                return True
            elif event.key == pygame.K_q and event.mod & pygame.KMOD_CTRL:
                if self.mode in [MODE_TERMINAL, MODE_CHAT]:
                    self.mode = MODE_DASHBOARD
                    return True
                else:
                    return False
        
        # Refresh
        if event.key == pygame.K_r and event.mod & pygame.KMOD_CTRL:
            self.refresh_all()
            return True
        
        # Mode-specific handling
        if self.mode == MODE_CHAT:
            # Tab to switch buttons
            if event.key == pygame.K_TAB:
                self.selected_button = (self.selected_button + 1) % 3
            # F1-F3 for buttons
            elif event.key == pygame.K_F1:
                self.chat.send_message()
            elif event.key == pygame.K_F2:
                self.chat.clear_history()
            elif event.key == pygame.K_F3:
                # Stop - would need to implement process killing
                pass
            else:
                self.chat.handle_key(event)
        
        elif self.mode in [MODE_DASHBOARD, MODE_TASKS]:
            if event.key == pygame.K_UP:
                self.task_scroll = max(0, self.task_scroll - 1)
            elif event.key == pygame.K_DOWN:
                max_scroll = max(0, len(self.tasks) - (12 if self.mode == MODE_TASKS else 5))
                self.task_scroll = min(max_scroll, self.task_scroll + 1)
        
        elif self.mode == MODE_TERMINAL and self.terminal:
            if event.key == pygame.K_RETURN:
                self.terminal.write('\r')
            elif event.key == pygame.K_BACKSPACE:
                self.terminal.write('\x7f')
            elif event.key == pygame.K_DELETE:
                self.terminal.write('\x1b[3~')
            elif event.key == pygame.K_TAB:
                self.terminal.write('\t')
            elif event.key == pygame.K_UP:
                self.terminal.write('\x1b[A')
            elif event.key == pygame.K_DOWN:
                self.terminal.write('\x1b[B')
            elif event.key == pygame.K_LEFT:
                self.terminal.write('\x1b[D')
            elif event.key == pygame.K_RIGHT:
                self.terminal.write('\x1b[C')
            elif event.key == pygame.K_HOME:
                self.terminal.write('\x1b[H')
            elif event.key == pygame.K_END:
                self.terminal.write('\x1b[F')
            elif event.key == pygame.K_ESCAPE:
                self.terminal.write('\x1b')
            elif event.mod & pygame.KMOD_CTRL:
                if event.key >= pygame.K_a and event.key <= pygame.K_z:
                    ctrl_char = chr(event.key - pygame.K_a + 1)
                    self.terminal.write(ctrl_char)
            elif event.unicode:
                self.terminal.write(event.unicode)
        
        return True
    
    def draw(self):
        self.screen.fill(C['bg'])
        
        self.draw_header()
        
        if self.mode == MODE_DASHBOARD:
            self.draw_system_card()
            self.draw_status_card()
            self.draw_tasks_card()
            self.draw_quick_bar()
            self.draw_big_time()
        elif self.mode == MODE_TASKS:
            self.draw_task_mode()
        elif self.mode == MODE_TERMINAL:
            self.draw_terminal_mode()
        elif self.mode == MODE_CHAT:
            self.draw_chat_mode()
        
        self.draw_footer()
        
        pygame.display.flip()
    
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
            
            if self.mode not in [MODE_TERMINAL, MODE_CHAT] and time.time() - self.last_refresh > REFRESH_INTERVAL:
                self.refresh_all()
            
            self.draw()
            self.clock.tick(30 if self.mode in [MODE_TERMINAL, MODE_CHAT] else 4)
        
        if self.terminal:
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
