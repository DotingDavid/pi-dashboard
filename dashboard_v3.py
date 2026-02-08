#!/usr/bin/env python3
"""
Pi 400 Dashboard v3 - Visual Polish Edition
For 3.5" Waveshare TFT (480x320)

Iteration 1: Focus on visual polish
- Cohesive color palette (Nord-inspired)
- Progress bars for system stats
- Better typography hierarchy
- Subtle visual improvements
"""

import pygame
import sys
import os
import subprocess
import json
import time
from datetime import datetime
from pathlib import Path

# Configuration
SCREEN_WIDTH = 480
SCREEN_HEIGHT = 320

# Nord-inspired color palette
COLORS = {
    'bg_dark': (46, 52, 64),       # Nord0 - darkest
    'bg_mid': (59, 66, 82),        # Nord1
    'bg_light': (67, 76, 94),      # Nord2
    'fg_dim': (76, 86, 106),       # Nord3
    'fg_light': (216, 222, 233),   # Nord4
    'fg_bright': (236, 239, 244),  # Nord6
    
    'accent_cyan': (136, 192, 208),    # Nord8 - frost
    'accent_blue': (129, 161, 193),    # Nord9
    'accent_green': (163, 190, 140),   # Nord14
    'accent_yellow': (235, 203, 139),  # Nord13
    'accent_red': (191, 97, 106),      # Nord11
    'accent_purple': (180, 142, 173),  # Nord15
}

REFRESH_INTERVAL = 30  # seconds


class DashboardApp:
    def __init__(self):
        pygame.init()
        
        self.screen = pygame.display.set_mode(
            (SCREEN_WIDTH, SCREEN_HEIGHT),
            pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF
        )
        pygame.display.set_caption('OpenClaw Dashboard v3')
        pygame.mouse.set_visible(False)
        
        # Load fonts
        self.fonts = {
            'title': pygame.font.SysFont('liberationmono', 18, bold=True),
            'header': pygame.font.SysFont('liberationmono', 14, bold=True),
            'body': pygame.font.SysFont('liberationmono', 12),
            'small': pygame.font.SysFont('liberationmono', 10),
            'tiny': pygame.font.SysFont('liberationmono', 9),
        }
        
        # Data
        self.openclaw_status = {}
        self.system_stats = {}
        self.todoist_tasks = []
        self.last_refresh = 0
        
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
                    status['model'] = 'Unknown'
            
            log_path = Path.home() / '.openclaw' / 'logs' / 'gateway.log'
            if log_path.exists():
                try:
                    mtime = log_path.stat().st_mtime
                    age_min = int((time.time() - mtime) / 60)
                    status['heartbeat_age'] = age_min
                except:
                    status['heartbeat_age'] = -1
        else:
            status['model'] = '-'
            status['heartbeat_age'] = -1
        
        return status
    
    def get_system_stats(self):
        stats = {}
        
        # CPU
        output, _ = self.run_command("top -bn1 | grep 'Cpu' | awk '{print $2}' | cut -d'%' -f1")
        try:
            stats['cpu'] = min(100, max(0, float(output)))
        except:
            stats['cpu'] = 0
        
        # Memory
        output, _ = self.run_command("free | awk 'NR==2{printf \"%.0f\", $3/$2*100}'")
        try:
            stats['mem'] = min(100, max(0, float(output)))
        except:
            stats['mem'] = 0
        
        output, _ = self.run_command("free -m | awk 'NR==2{print $3}'")
        try:
            stats['mem_mb'] = int(output)
        except:
            stats['mem_mb'] = 0
        
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
        
        # Uptime
        output, _ = self.run_command("uptime -p | sed 's/up //'")
        stats['uptime'] = output[:15] if output else 'unknown'
        
        return stats
    
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
            return [{'content': 'No API token', 'overdue': False, 'priority': 4}]
        
        output, code = self.run_command("todoist --csv list", timeout=5)
        
        if code != 0:
            return [{'content': 'Failed to fetch', 'overdue': False, 'priority': 4}]
        
        try:
            lines = output.strip().split('\n')
            if len(lines) > 1:
                for line in lines[1:6]:
                    parts = line.split(',')
                    if len(parts) >= 2:
                        content = parts[1].strip().strip('"')
                        overdue = 'overdue' in line.lower()
                        priority = 4
                        if 'p1' in line.lower():
                            priority = 1
                        elif 'p2' in line.lower():
                            priority = 2
                        elif 'p3' in line.lower():
                            priority = 3
                        tasks.append({'content': content, 'overdue': overdue, 'priority': priority})
        except:
            pass
        
        return tasks if tasks else [{'content': 'No tasks', 'overdue': False, 'priority': 4}]
    
    def refresh_data(self):
        self.openclaw_status = self.get_openclaw_status()
        self.system_stats = self.get_system_stats()
        self.todoist_tasks = self.get_todoist_tasks()
        self.last_refresh = time.time()
    
    def draw_text(self, text, font_name, color, x, y, right_align=False):
        font = self.fonts[font_name]
        surface = font.render(text, True, color)
        if right_align:
            x = x - surface.get_width()
        self.screen.blit(surface, (x, y))
        return surface.get_width()
    
    def draw_progress_bar(self, x, y, width, height, value, max_val, color, bg_color):
        """Draw a progress bar with rounded ends"""
        # Background
        pygame.draw.rect(self.screen, bg_color, (x, y, width, height), border_radius=height//2)
        
        # Filled portion
        fill_width = int((value / max_val) * width) if max_val > 0 else 0
        if fill_width > 0:
            fill_width = max(height, fill_width)  # Minimum for rounded corners
            pygame.draw.rect(self.screen, color, (x, y, fill_width, height), border_radius=height//2)
    
    def draw_card(self, x, y, width, height, title=None):
        """Draw a card with optional title"""
        # Card background
        pygame.draw.rect(self.screen, COLORS['bg_mid'], (x, y, width, height), border_radius=8)
        pygame.draw.rect(self.screen, COLORS['fg_dim'], (x, y, width, height), width=1, border_radius=8)
        
        if title:
            self.draw_text(title, 'header', COLORS['accent_cyan'], x + 10, y + 8)
            return y + 28  # Return content start y
        return y + 8
    
    def draw_header(self):
        """Draw the header bar"""
        # Header background
        pygame.draw.rect(self.screen, COLORS['bg_mid'], (0, 0, SCREEN_WIDTH, 36))
        pygame.draw.line(self.screen, COLORS['fg_dim'], (0, 36), (SCREEN_WIDTH, 36), 1)
        
        # Status indicator
        is_running = self.openclaw_status.get('running', False)
        status_color = COLORS['accent_green'] if is_running else COLORS['accent_red']
        pygame.draw.circle(self.screen, status_color, (18, 18), 6)
        
        # Title
        self.draw_text("OpenClaw", 'title', COLORS['fg_bright'], 32, 8)
        
        # Model badge
        model = self.openclaw_status.get('model', '-')
        if model and model != '-':
            badge_color = COLORS['accent_purple'] if model == 'Opus' else COLORS['accent_blue']
            model_text = model.upper()
            text_width = self.fonts['small'].size(model_text)[0]
            badge_x = 130
            pygame.draw.rect(self.screen, badge_color, (badge_x, 10, text_width + 12, 16), border_radius=4)
            self.draw_text(model_text, 'small', COLORS['bg_dark'], badge_x + 6, 11)
        
        # Time
        now = datetime.now()
        time_str = now.strftime("%I:%M %p").lstrip('0')
        self.draw_text(time_str, 'header', COLORS['fg_light'], SCREEN_WIDTH - 10, 10, right_align=True)
        
        # Date (smaller)
        date_str = now.strftime("%b %d")
        self.draw_text(date_str, 'small', COLORS['fg_dim'], SCREEN_WIDTH - 10, 24, right_align=True)
    
    def draw_system_stats(self):
        """Draw system stats card"""
        card_x = 10
        card_y = 46
        card_w = 225
        card_h = 100
        
        content_y = self.draw_card(card_x, card_y, card_w, card_h, "System")
        
        bar_width = 140
        bar_height = 10
        bar_x = card_x + 65
        label_x = card_x + 15
        value_x = card_x + card_w - 15
        
        # CPU
        cpu = self.system_stats.get('cpu', 0)
        cpu_color = COLORS['accent_red'] if cpu > 80 else COLORS['accent_green']
        self.draw_text("CPU", 'body', COLORS['fg_light'], label_x, content_y)
        self.draw_progress_bar(bar_x, content_y + 2, bar_width, bar_height, cpu, 100, cpu_color, COLORS['bg_light'])
        self.draw_text(f"{cpu:.0f}%", 'small', COLORS['fg_dim'], value_x, content_y, right_align=True)
        content_y += 22
        
        # Memory
        mem = self.system_stats.get('mem', 0)
        mem_mb = self.system_stats.get('mem_mb', 0)
        mem_color = COLORS['accent_yellow'] if mem > 70 else COLORS['accent_blue']
        self.draw_text("Mem", 'body', COLORS['fg_light'], label_x, content_y)
        self.draw_progress_bar(bar_x, content_y + 2, bar_width, bar_height, mem, 100, mem_color, COLORS['bg_light'])
        self.draw_text(f"{mem_mb}M", 'small', COLORS['fg_dim'], value_x, content_y, right_align=True)
        content_y += 22
        
        # Temperature
        temp = self.system_stats.get('temp', 0)
        temp_color = COLORS['accent_red'] if temp > 65 else COLORS['accent_cyan']
        self.draw_text("Temp", 'body', COLORS['fg_light'], label_x, content_y)
        self.draw_progress_bar(bar_x, content_y + 2, bar_width, bar_height, temp, 85, temp_color, COLORS['bg_light'])
        self.draw_text(f"{temp:.0f}°C", 'small', COLORS['fg_dim'], value_x, content_y, right_align=True)
    
    def draw_status_card(self):
        """Draw OpenClaw status card"""
        card_x = 245
        card_y = 46
        card_w = 225
        card_h = 100
        
        content_y = self.draw_card(card_x, card_y, card_w, card_h, "Status")
        
        label_x = card_x + 15
        value_x = card_x + card_w - 15
        
        # Gateway status
        is_running = self.openclaw_status.get('running', False)
        status_text = "Running" if is_running else "Stopped"
        status_color = COLORS['accent_green'] if is_running else COLORS['accent_red']
        self.draw_text("Gateway", 'body', COLORS['fg_light'], label_x, content_y)
        self.draw_text(status_text, 'body', status_color, value_x, content_y, right_align=True)
        content_y += 20
        
        # Heartbeat
        hb_age = self.openclaw_status.get('heartbeat_age', -1)
        if hb_age >= 0:
            if hb_age < 5:
                hb_text = "Active"
                hb_color = COLORS['accent_green']
            elif hb_age < 30:
                hb_text = f"{hb_age}m ago"
                hb_color = COLORS['fg_light']
            else:
                hb_text = f"{hb_age}m ago"
                hb_color = COLORS['accent_yellow']
        else:
            hb_text = "-"
            hb_color = COLORS['fg_dim']
        
        self.draw_text("Heartbeat", 'body', COLORS['fg_light'], label_x, content_y)
        self.draw_text(hb_text, 'body', hb_color, value_x, content_y, right_align=True)
        content_y += 20
        
        # Uptime
        uptime = self.system_stats.get('uptime', 'unknown')
        self.draw_text("Uptime", 'body', COLORS['fg_light'], label_x, content_y)
        self.draw_text(uptime, 'body', COLORS['fg_dim'], value_x, content_y, right_align=True)
    
    def draw_tasks(self):
        """Draw Todoist tasks card"""
        card_x = 10
        card_y = 156
        card_w = 460
        card_h = 130
        
        # Count overdue
        overdue_count = sum(1 for t in self.todoist_tasks if t.get('overdue'))
        title = f"Tasks ({overdue_count} overdue)" if overdue_count else f"Tasks ({len(self.todoist_tasks)})"
        
        content_y = self.draw_card(card_x, card_y, card_w, card_h, title)
        
        # Draw tasks
        for task in self.todoist_tasks[:5]:
            content = task['content']
            if len(content) > 52:
                content = content[:49] + "..."
            
            priority = task.get('priority', 4)
            overdue = task.get('overdue', False)
            
            # Priority indicator
            if priority == 1:
                bullet_color = COLORS['accent_red']
            elif priority == 2:
                bullet_color = COLORS['accent_yellow']
            elif priority == 3:
                bullet_color = COLORS['accent_blue']
            else:
                bullet_color = COLORS['fg_dim']
            
            pygame.draw.circle(self.screen, bullet_color, (card_x + 18, content_y + 6), 3)
            
            text_color = COLORS['accent_yellow'] if overdue else COLORS['fg_light']
            self.draw_text(content, 'body', text_color, card_x + 28, content_y)
            content_y += 18
    
    def draw_footer(self):
        """Draw footer with controls and refresh indicator"""
        footer_y = SCREEN_HEIGHT - 24
        
        pygame.draw.line(self.screen, COLORS['fg_dim'], (10, footer_y - 4), (SCREEN_WIDTH - 10, footer_y - 4), 1)
        
        # Controls hint
        self.draw_text("[Ctrl+Q] Quit  [Ctrl+R] Refresh", 'tiny', COLORS['fg_dim'], 12, footer_y)
        
        # Refresh indicator
        time_since = int(time.time() - self.last_refresh)
        refresh_text = f"↻ {time_since}s"
        self.draw_text(refresh_text, 'tiny', COLORS['fg_dim'], SCREEN_WIDTH - 12, footer_y, right_align=True)
    
    def draw(self):
        """Draw the entire dashboard"""
        self.screen.fill(COLORS['bg_dark'])
        
        self.draw_header()
        self.draw_system_stats()
        self.draw_status_card()
        self.draw_tasks()
        self.draw_footer()
        
        pygame.display.flip()
    
    def run(self):
        """Main loop"""
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
            
            if time.time() - self.last_refresh > REFRESH_INTERVAL:
                self.refresh_data()
            
            self.draw()
            self.clock.tick(2)  # 2 FPS - saves CPU
        
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
