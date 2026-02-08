#!/usr/bin/env python3
"""
Pi 400 Dashboard v4 - Feature-Rich Edition
For 3.5" Waveshare TFT (480x320)

Iteration 2: More functionality
- Weather widget
- Network status (IP, wifi strength)
- Better info density
- Mini sparklines for CPU history
- Scrollable task list
"""

import pygame
import sys
import os
import subprocess
import json
import time
import socket
from datetime import datetime
from pathlib import Path
from collections import deque

# Configuration
SCREEN_WIDTH = 480
SCREEN_HEIGHT = 320

# Nord color palette
C = {
    'bg': (46, 52, 64),
    'bg_card': (59, 66, 82),
    'bg_hover': (67, 76, 94),
    'border': (76, 86, 106),
    'text': (216, 222, 233),
    'text_bright': (236, 239, 244),
    'text_dim': (76, 86, 106),
    
    'cyan': (136, 192, 208),
    'blue': (129, 161, 193),
    'green': (163, 190, 140),
    'yellow': (235, 203, 139),
    'red': (191, 97, 106),
    'purple': (180, 142, 173),
    'orange': (208, 135, 112),
}

REFRESH_INTERVAL = 30


class DashboardApp:
    def __init__(self):
        pygame.init()
        
        self.screen = pygame.display.set_mode(
            (SCREEN_WIDTH, SCREEN_HEIGHT),
            pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF
        )
        pygame.display.set_caption('OpenClaw Dashboard v4')
        pygame.mouse.set_visible(False)
        
        self.fonts = {
            'title': pygame.font.SysFont('liberationmono', 18, bold=True),
            'header': pygame.font.SysFont('liberationmono', 13, bold=True),
            'body': pygame.font.SysFont('liberationmono', 11),
            'small': pygame.font.SysFont('liberationmono', 10),
            'tiny': pygame.font.SysFont('liberationmono', 9),
            'icon': pygame.font.SysFont('dejavusansmono', 14),  # For unicode icons
        }
        
        # Data
        self.openclaw_status = {}
        self.system_stats = {}
        self.todoist_tasks = []
        self.weather = {}
        self.network = {}
        self.last_refresh = 0
        
        # CPU history for sparkline
        self.cpu_history = deque(maxlen=20)
        
        # Task scroll
        self.task_scroll = 0
        
        self.clock = pygame.time.Clock()
    
    def run_command(self, cmd, timeout=5):
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return result.stdout.strip(), result.returncode
        except:
            return "", -1
    
    def get_openclaw_status(self):
        status = {}
        output, code = self.run_command("pgrep -f 'openclaw.*gateway'")
        status['running'] = code == 0
        
        if status['running']:
            config_path = Path.home() / '.openclaw' / 'config.json'
            if config_path.exists():
                try:
                    with open(config_path) as f:
                        config = json.load(f)
                        model = config.get('defaultModel', '')
                        if 'opus' in model.lower():
                            status['model'] = 'Opus'
                        elif 'sonnet' in model.lower():
                            status['model'] = 'Sonnet'
                        else:
                            status['model'] = model.split('/')[-1][:10]
                except:
                    status['model'] = '?'
            
            log_path = Path.home() / '.openclaw' / 'logs' / 'gateway.log'
            if log_path.exists():
                try:
                    mtime = log_path.stat().st_mtime
                    status['hb_age'] = int((time.time() - mtime) / 60)
                except:
                    status['hb_age'] = -1
        else:
            status['model'] = '-'
            status['hb_age'] = -1
        
        return status
    
    def get_system_stats(self):
        stats = {}
        
        # CPU
        output, _ = self.run_command("grep 'cpu ' /proc/stat | awk '{print ($2+$4)*100/($2+$4+$5)}'")
        try:
            stats['cpu'] = min(100, max(0, float(output)))
        except:
            stats['cpu'] = 0
        
        self.cpu_history.append(stats['cpu'])
        
        # Memory
        output, _ = self.run_command("free | awk 'NR==2{printf \"%.0f\", $3/$2*100}'")
        try:
            stats['mem'] = min(100, max(0, float(output)))
        except:
            stats['mem'] = 0
        
        output, _ = self.run_command("free -m | awk 'NR==2{print $3\"/\"$2}'")
        stats['mem_str'] = output if output else "?/?"
        
        # Temperature
        temp_path = Path('/sys/class/thermal/thermal_zone0/temp')
        if temp_path.exists():
            try:
                with open(temp_path) as f:
                    stats['temp'] = int(f.read().strip()) / 1000.0
            except:
                stats['temp'] = 0
        else:
            stats['temp'] = 0
        
        # Disk
        output, _ = self.run_command("df / | awk 'NR==2{print $5}' | tr -d '%'")
        try:
            stats['disk'] = int(output)
        except:
            stats['disk'] = 0
        
        return stats
    
    def get_network(self):
        net = {}
        
        # Local IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            net['ip'] = s.getsockname()[0]
            s.close()
        except:
            net['ip'] = 'No network'
        
        # Wifi signal
        output, code = self.run_command("iwconfig wlan0 2>/dev/null | grep -i quality")
        if code == 0 and output:
            try:
                # Extract quality like "Link Quality=70/70"
                import re
                match = re.search(r'Quality=(\d+)/(\d+)', output)
                if match:
                    net['wifi'] = int(100 * int(match.group(1)) / int(match.group(2)))
                else:
                    net['wifi'] = -1
            except:
                net['wifi'] = -1
        else:
            net['wifi'] = -1  # Not wifi or not connected
        
        # SSID
        output, _ = self.run_command("iwgetid -r 2>/dev/null")
        net['ssid'] = output[:12] if output else None
        
        return net
    
    def get_weather(self):
        """Get weather using wttr.in (lightweight)"""
        weather = {}
        
        # Simple curl to wttr.in
        output, code = self.run_command("curl -s 'wttr.in/?format=%c%t' 2>/dev/null", timeout=3)
        
        if code == 0 and output and len(output) < 20:
            weather['summary'] = output.strip()
        else:
            weather['summary'] = None
        
        return weather
    
    def get_todoist_tasks(self):
        tasks = []
        token = os.environ.get('TODOIST_API_TOKEN')
        
        if not token:
            bashrc = Path.home() / '.bashrc'
            if bashrc.exists():
                with open(bashrc) as f:
                    for line in f:
                        if 'TODOIST_API_TOKEN' in line and '=' in line:
                            token = line.split('=')[1].strip().strip('"').strip("'")
                            os.environ['TODOIST_API_TOKEN'] = token
                            break
        
        if not token:
            return [{'content': 'No API token', 'priority': 4}]
        
        output, code = self.run_command("todoist --csv list", timeout=5)
        
        if code != 0:
            return [{'content': 'Fetch failed', 'priority': 4}]
        
        try:
            lines = output.strip().split('\n')
            if len(lines) > 1:
                for line in lines[1:10]:  # Get more tasks
                    parts = line.split(',')
                    if len(parts) >= 2:
                        content = parts[1].strip().strip('"')
                        overdue = 'overdue' in line.lower()
                        priority = 4
                        if 'p1' in line.lower(): priority = 1
                        elif 'p2' in line.lower(): priority = 2
                        elif 'p3' in line.lower(): priority = 3
                        tasks.append({'content': content, 'overdue': overdue, 'priority': priority})
        except:
            pass
        
        return tasks if tasks else [{'content': 'No tasks', 'priority': 4}]
    
    def refresh_data(self):
        self.openclaw_status = self.get_openclaw_status()
        self.system_stats = self.get_system_stats()
        self.network = self.get_network()
        self.weather = self.get_weather()
        self.todoist_tasks = self.get_todoist_tasks()
        self.last_refresh = time.time()
    
    def draw_text(self, text, font_name, color, x, y, right_align=False, center=False):
        font = self.fonts[font_name]
        surface = font.render(text, True, color)
        if right_align:
            x = x - surface.get_width()
        elif center:
            x = x - surface.get_width() // 2
        self.screen.blit(surface, (x, y))
        return surface.get_width()
    
    def draw_bar(self, x, y, w, h, val, max_val, color):
        pygame.draw.rect(self.screen, C['bg_hover'], (x, y, w, h), border_radius=h//2)
        fill_w = int((val / max_val) * w) if max_val > 0 else 0
        if fill_w > 0:
            pygame.draw.rect(self.screen, color, (x, y, max(h, fill_w), h), border_radius=h//2)
    
    def draw_sparkline(self, x, y, w, h, data, color):
        """Draw a mini sparkline graph"""
        if len(data) < 2:
            return
        
        # Background
        pygame.draw.rect(self.screen, C['bg_hover'], (x, y, w, h), border_radius=2)
        
        # Calculate points
        points = []
        max_val = max(data) if max(data) > 0 else 100
        min_val = min(data)
        val_range = max(max_val - min_val, 1)
        
        for i, val in enumerate(data):
            px = x + int((i / (len(data) - 1)) * w) if len(data) > 1 else x
            py = y + h - int(((val - min_val) / val_range) * (h - 4)) - 2
            points.append((px, py))
        
        # Draw line
        if len(points) >= 2:
            pygame.draw.lines(self.screen, color, False, points, 1)
    
    def draw_header(self):
        # Background
        pygame.draw.rect(self.screen, C['bg_card'], (0, 0, SCREEN_WIDTH, 32))
        pygame.draw.line(self.screen, C['border'], (0, 32), (SCREEN_WIDTH, 32), 1)
        
        # Status indicator
        running = self.openclaw_status.get('running', False)
        color = C['green'] if running else C['red']
        pygame.draw.circle(self.screen, color, (16, 16), 5)
        
        # Title
        self.draw_text("OpenClaw", 'title', C['text_bright'], 28, 6)
        
        # Model badge
        model = self.openclaw_status.get('model', '-')
        if model not in ['-', '?']:
            badge_col = C['purple'] if model == 'Opus' else C['blue']
            tw = self.fonts['tiny'].size(model.upper())[0]
            pygame.draw.rect(self.screen, badge_col, (115, 9, tw + 8, 14), border_radius=3)
            self.draw_text(model.upper(), 'tiny', C['bg'], 119, 10)
        
        # Weather (if available)
        weather = self.weather.get('summary')
        if weather:
            self.draw_text(weather, 'body', C['text'], 180, 10)
        
        # Time & date
        now = datetime.now()
        self.draw_text(now.strftime("%I:%M").lstrip('0'), 'header', C['text_bright'], SCREEN_WIDTH - 8, 5, right_align=True)
        self.draw_text(now.strftime("%a %b %d"), 'tiny', C['text_dim'], SCREEN_WIDTH - 8, 19, right_align=True)
    
    def draw_system_panel(self):
        """Left panel: system stats"""
        x, y = 8, 40
        w = 155
        
        # Title
        self.draw_text("SYSTEM", 'tiny', C['cyan'], x, y)
        y += 14
        
        # CPU with sparkline
        cpu = self.system_stats.get('cpu', 0)
        cpu_col = C['red'] if cpu > 80 else C['green']
        self.draw_text("CPU", 'small', C['text'], x, y)
        self.draw_text(f"{cpu:.0f}%", 'small', cpu_col, x + 35, y)
        self.draw_sparkline(x + 65, y + 1, 85, 10, list(self.cpu_history), cpu_col)
        y += 16
        
        # Memory
        mem = self.system_stats.get('mem', 0)
        mem_str = self.system_stats.get('mem_str', '?')
        mem_col = C['yellow'] if mem > 75 else C['blue']
        self.draw_text("MEM", 'small', C['text'], x, y)
        self.draw_bar(x + 35, y + 2, 80, 8, mem, 100, mem_col)
        self.draw_text(mem_str, 'tiny', C['text_dim'], x + 120, y)
        y += 16
        
        # Temperature
        temp = self.system_stats.get('temp', 0)
        temp_col = C['red'] if temp > 65 else C['cyan']
        self.draw_text("TMP", 'small', C['text'], x, y)
        self.draw_bar(x + 35, y + 2, 80, 8, temp, 85, temp_col)
        self.draw_text(f"{temp:.0f}°C", 'tiny', C['text_dim'], x + 120, y)
        y += 16
        
        # Disk
        disk = self.system_stats.get('disk', 0)
        disk_col = C['red'] if disk > 85 else C['green']
        self.draw_text("DSK", 'small', C['text'], x, y)
        self.draw_bar(x + 35, y + 2, 80, 8, disk, 100, disk_col)
        self.draw_text(f"{disk}%", 'tiny', C['text_dim'], x + 120, y)
    
    def draw_status_panel(self):
        """Middle panel: OpenClaw status"""
        x, y = 170, 40
        
        # Title
        self.draw_text("STATUS", 'tiny', C['cyan'], x, y)
        y += 14
        
        # Gateway
        running = self.openclaw_status.get('running', False)
        status_txt = "● Running" if running else "○ Stopped"
        status_col = C['green'] if running else C['red']
        self.draw_text(status_txt, 'small', status_col, x, y)
        y += 16
        
        # Heartbeat
        hb = self.openclaw_status.get('hb_age', -1)
        if hb >= 0:
            if hb < 5:
                hb_txt, hb_col = "♥ Active", C['green']
            elif hb < 30:
                hb_txt, hb_col = f"♥ {hb}m ago", C['text']
            else:
                hb_txt, hb_col = f"♥ {hb}m ago", C['yellow']
        else:
            hb_txt, hb_col = "♥ -", C['text_dim']
        self.draw_text(hb_txt, 'small', hb_col, x, y)
        y += 18
        
        # Network section
        self.draw_text("NETWORK", 'tiny', C['cyan'], x, y)
        y += 14
        
        ip = self.network.get('ip', '?')
        self.draw_text(ip, 'small', C['text'], x, y)
        y += 14
        
        wifi = self.network.get('wifi', -1)
        ssid = self.network.get('ssid', '')
        if wifi >= 0:
            wifi_col = C['green'] if wifi > 60 else C['yellow'] if wifi > 30 else C['red']
            bars = '▂▄▆█'[:max(1, wifi // 25)]
            wifi_txt = f"{bars} {ssid}" if ssid else f"{bars} {wifi}%"
            self.draw_text(wifi_txt, 'small', wifi_col, x, y)
        else:
            self.draw_text("⌁ Wired", 'small', C['blue'], x, y)
    
    def draw_tasks_panel(self):
        """Right panel: Todoist tasks"""
        x, y = 315, 40
        w = SCREEN_WIDTH - x - 8
        
        # Title with count
        overdue = sum(1 for t in self.todoist_tasks if t.get('overdue'))
        title = f"TASKS ({overdue}!)" if overdue else f"TASKS ({len(self.todoist_tasks)})"
        title_col = C['yellow'] if overdue else C['cyan']
        self.draw_text(title, 'tiny', title_col, x, y)
        y += 14
        
        # Tasks
        visible_tasks = self.todoist_tasks[self.task_scroll:self.task_scroll + 6]
        
        for task in visible_tasks:
            content = task['content']
            if len(content) > 18:
                content = content[:15] + "..."
            
            priority = task.get('priority', 4)
            overdue = task.get('overdue', False)
            
            # Priority dot
            p_colors = {1: C['red'], 2: C['orange'], 3: C['blue'], 4: C['text_dim']}
            pygame.draw.circle(self.screen, p_colors.get(priority, C['text_dim']), (x + 4, y + 5), 3)
            
            text_col = C['yellow'] if overdue else C['text']
            self.draw_text(content, 'small', text_col, x + 12, y)
            y += 14
        
        # Scroll indicator
        if len(self.todoist_tasks) > 6:
            total = len(self.todoist_tasks)
            pos = self.task_scroll / max(1, total - 6)
            indicator_h = max(10, 70 // total * 6)
            indicator_y = 60 + int(pos * (70 - indicator_h))
            pygame.draw.rect(self.screen, C['border'], (SCREEN_WIDTH - 4, indicator_y, 2, indicator_h), border_radius=1)
    
    def draw_quick_actions(self):
        """Bottom bar with quick actions"""
        y = SCREEN_HEIGHT - 70
        
        pygame.draw.line(self.screen, C['border'], (8, y), (SCREEN_WIDTH - 8, y), 1)
        y += 8
        
        # Quick action buttons (visual only for now)
        actions = [
            ("🔄 Refresh", C['cyan']),
            ("📋 Tasks", C['blue']),
            ("⚡ Status", C['green']),
        ]
        
        btn_w = 145
        for i, (label, color) in enumerate(actions):
            bx = 12 + i * (btn_w + 8)
            pygame.draw.rect(self.screen, C['bg_card'], (bx, y, btn_w, 24), border_radius=4)
            pygame.draw.rect(self.screen, color, (bx, y, btn_w, 24), width=1, border_radius=4)
            self.draw_text(label, 'small', color, bx + btn_w // 2, y + 6, center=True)
    
    def draw_footer(self):
        """Footer with controls"""
        y = SCREEN_HEIGHT - 24
        
        pygame.draw.line(self.screen, C['border'], (8, y - 4), (SCREEN_WIDTH - 8, y - 4), 1)
        
        self.draw_text("Ctrl+Q:Quit  Ctrl+R:Refresh  ↑↓:Scroll", 'tiny', C['text_dim'], 12, y)
        
        time_since = int(time.time() - self.last_refresh)
        self.draw_text(f"↻ {time_since}s", 'tiny', C['text_dim'], SCREEN_WIDTH - 12, y, right_align=True)
    
    def draw(self):
        self.screen.fill(C['bg'])
        
        self.draw_header()
        self.draw_system_panel()
        self.draw_status_panel()
        self.draw_tasks_panel()
        self.draw_quick_actions()
        self.draw_footer()
        
        pygame.display.flip()
    
    def run(self):
        running = True
        self.refresh_data()
        
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q and event.mod & pygame.KMOD_CTRL:
                        running = False
                    elif event.key == pygame.K_r and event.mod & pygame.KMOD_CTRL:
                        self.refresh_data()
                    elif event.key == pygame.K_UP:
                        self.task_scroll = max(0, self.task_scroll - 1)
                    elif event.key == pygame.K_DOWN:
                        self.task_scroll = min(len(self.todoist_tasks) - 6, self.task_scroll + 1)
            
            if time.time() - self.last_refresh > REFRESH_INTERVAL:
                self.refresh_data()
            
            self.draw()
            self.clock.tick(2)
        
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
