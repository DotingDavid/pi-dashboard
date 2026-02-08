#!/usr/bin/env python3
"""
Pi 400 Dashboard v2 - Fullscreen Kiosk with Embedded Terminal
For 3.5" Waveshare TFT (480x320)
"""

import pygame
import sys
import os
import subprocess
import json
import time
import pty
import select
import termios
import struct
import fcntl
from datetime import datetime
from pathlib import Path

# Configuration
SCREEN_WIDTH = 480
SCREEN_HEIGHT = 320
TERMINAL_HEIGHT = int(SCREEN_HEIGHT * 0.4)  # Bottom 40%
STATUS_HEIGHT = SCREEN_HEIGHT - TERMINAL_HEIGHT

# Colors - Modern dark theme
BG_DARK = (26, 26, 46)  # #1a1a2e
BG_DARKER = (16, 16, 30)
TEXT_PRIMARY = (230, 230, 240)
TEXT_SECONDARY = (160, 160, 170)
ACCENT_CYAN = (80, 200, 220)
ACCENT_GREEN = (80, 220, 120)
ACCENT_RED = (240, 80, 80)
ACCENT_YELLOW = (255, 200, 60)
SEPARATOR = (50, 50, 70)
TERMINAL_BG = (20, 20, 30)
TERMINAL_FG = (200, 200, 210)
TERMINAL_CURSOR = (80, 200, 220)

REFRESH_INTERVAL = 45  # seconds

class PTYTerminal:
    """Manages a PTY with a bash shell"""
    
    def __init__(self):
        self.master_fd = None
        self.pid = None
        self.buffer = []
        self.input_buffer = ""
        self.cursor_col = 0
        self.max_lines = 10
        self.prompt_line = ""
        
    def start(self):
        """Start the bash shell in a PTY"""
        self.pid, self.master_fd = pty.fork()
        
        if self.pid == 0:  # Child process
            # Set up the shell environment
            env = os.environ.copy()
            env['TERM'] = 'linux'
            env['PS1'] = r'\u@\h:\w\$ '
            
            # Execute bash
            os.execvpe('/bin/bash', ['/bin/bash'], env)
        else:  # Parent process
            # Set non-blocking
            flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            
            # Set terminal size
            self.set_size(80, self.max_lines)
            
            # Give bash a moment to start
            time.sleep(0.1)
            self.read_output()
    
    def set_size(self, cols, rows):
        """Set terminal size"""
        if self.master_fd:
            size = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, size)
    
    def write_input(self, data):
        """Write input to the terminal"""
        if self.master_fd:
            try:
                os.write(self.master_fd, data.encode())
            except:
                pass
    
    def read_output(self):
        """Read output from the terminal"""
        if not self.master_fd:
            return
        
        try:
            while True:
                ready, _, _ = select.select([self.master_fd], [], [], 0)
                if not ready:
                    break
                
                data = os.read(self.master_fd, 1024)
                if not data:
                    break
                
                # Process output
                text = data.decode('utf-8', errors='replace')
                self._process_output(text)
        except:
            pass
    
    def _process_output(self, text):
        """Process terminal output and update buffer"""
        # Simple line buffering - split on newlines
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            # Strip ANSI codes (simple version)
            clean_line = self._strip_ansi(line)
            
            if i == len(lines) - 1 and line and '\n' not in text[-1:]:
                # Last line without newline - this is the prompt
                self.prompt_line = clean_line
            else:
                # Complete line
                if clean_line.strip():
                    self.buffer.append(clean_line)
                    # Keep buffer from growing too large
                    if len(self.buffer) > 100:
                        self.buffer = self.buffer[-100:]
    
    def _strip_ansi(self, text):
        """Strip ANSI escape codes"""
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)
    
    def get_display_lines(self, num_lines):
        """Get the last N lines for display"""
        lines = []
        
        # Get recent output lines
        start_idx = max(0, len(self.buffer) - (num_lines - 1))
        lines = self.buffer[start_idx:]
        
        # Add current prompt line
        if self.prompt_line:
            lines.append(self.prompt_line)
        
        # Pad if needed
        while len(lines) < num_lines:
            lines.insert(0, "")
        
        return lines[-num_lines:]
    
    def close(self):
        """Close the PTY"""
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

class DashboardApp:
    def __init__(self):
        pygame.init()
        
        # TRUE FULLSCREEN - no window decorations
        self.screen = pygame.display.set_mode(
            (SCREEN_WIDTH, SCREEN_HEIGHT),
            pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF
        )
        pygame.display.set_caption('OpenClaw Dashboard')
        
        # Hide mouse cursor
        pygame.mouse.set_visible(False)
        
        # Fonts - monospace for terminal feel
        try:
            self.font_header = pygame.font.SysFont('liberationmono', 16, bold=True)
            self.font_status = pygame.font.SysFont('liberationmono', 13)
            self.font_terminal = pygame.font.SysFont('liberationmono', 12)
            self.font_small = pygame.font.SysFont('liberationmono', 10)
        except:
            # Fallback to default
            self.font_header = pygame.font.Font(None, 16)
            self.font_status = pygame.font.Font(None, 13)
            self.font_terminal = pygame.font.Font(None, 12)
            self.font_small = pygame.font.Font(None, 10)
        
        # Initialize terminal
        self.terminal = PTYTerminal()
        self.terminal.start()
        
        # Data cache
        self.openclaw_status = {}
        self.system_stats = {}
        self.todoist_tasks = []
        self.last_refresh = 0
        
        # Clock
        self.clock = pygame.time.Clock()
        
    def run_command(self, cmd, shell=True, timeout=5):
        """Run a shell command and return output"""
        try:
            result = subprocess.run(
                cmd if shell else cmd.split(),
                shell=shell,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.stdout.strip(), result.returncode
        except subprocess.TimeoutExpired:
            return "TIMEOUT", -1
        except Exception as e:
            return f"ERROR: {e}", -1
    
    def get_openclaw_status(self):
        """Get OpenClaw gateway status"""
        status = {}
        
        # Check if gateway is running
        output, code = self.run_command("pgrep -f 'openclaw.*gateway'")
        status['running'] = code == 0
        
        if status['running']:
            # Get model from config
            config_path = Path.home() / '.openclaw' / 'config.json'
            if config_path.exists():
                try:
                    with open(config_path) as f:
                        config = json.load(f)
                        model = config.get('defaultModel', '')
                        if 'opus' in model.lower():
                            status['model'] = 'opus'
                        elif 'sonnet' in model.lower():
                            status['model'] = 'sonnet'
                        else:
                            status['model'] = model.split('/')[-1][:12]
                except:
                    status['model'] = 'unknown'
            
            # Check last heartbeat
            log_path = Path.home() / '.openclaw' / 'logs' / 'gateway.log'
            if log_path.exists():
                try:
                    # Check last modified time
                    mtime = log_path.stat().st_mtime
                    age_minutes = int((time.time() - mtime) / 60)
                    if age_minutes < 5:
                        status['heartbeat'] = f'{age_minutes}m ago'
                    else:
                        status['heartbeat'] = f'{age_minutes}m'
                except:
                    status['heartbeat'] = 'unknown'
            else:
                status['heartbeat'] = 'unknown'
        else:
            status['model'] = '-'
            status['heartbeat'] = '-'
        
        return status
    
    def get_system_stats(self):
        """Get system statistics"""
        stats = {}
        
        # CPU usage - simpler method
        output, _ = self.run_command("top -bn1 | grep 'Cpu' | awk '{print $2}' | cut -d'%' -f1")
        try:
            stats['cpu'] = float(output)
        except:
            stats['cpu'] = 0.0
        
        # Memory usage
        output, _ = self.run_command("free -m | awk 'NR==2{print $3}'")
        try:
            stats['mem'] = int(output)
        except:
            stats['mem'] = 0
        
        # Temperature
        temp_path = Path('/sys/class/thermal/thermal_zone0/temp')
        if temp_path.exists():
            try:
                with open(temp_path) as f:
                    stats['temp'] = int(f.read().strip()) / 1000.0
            except:
                stats['temp'] = 0.0
        else:
            stats['temp'] = 0.0
        
        return stats
    
    def get_todoist_tasks(self):
        """Get Todoist tasks"""
        tasks = []
        
        # Check for API token
        token = os.environ.get('TODOIST_API_TOKEN')
        if not token:
            # Try to source from bashrc
            bashrc = Path.home() / '.bashrc'
            if bashrc.exists():
                with open(bashrc) as f:
                    for line in f:
                        if 'TODOIST_API_TOKEN' in line and '=' in line:
                            token = line.split('=')[1].strip().strip('"').strip("'")
                            os.environ['TODOIST_API_TOKEN'] = token
                            break
        
        if not token:
            return [{'content': 'No API token configured', 'overdue': False}]
        
        # Use todoist-cli
        output, code = self.run_command("todoist --csv list", timeout=5)
        
        if code != 0 or output == "TIMEOUT":
            return [{'content': 'Failed to fetch tasks', 'overdue': False}]
        
        try:
            lines = output.strip().split('\n')
            if len(lines) > 1:
                for line in lines[1:4]:  # Top 3 tasks
                    parts = line.split(',')
                    if len(parts) >= 2:
                        content = parts[1].strip().strip('"')
                        # Simple overdue detection
                        overdue = 'overdue' in line.lower() or 'p1' in line.lower()
                        tasks.append({'content': content, 'overdue': overdue})
        except Exception as e:
            return [{'content': f'Parse error: {str(e)[:20]}', 'overdue': False}]
        
        if not tasks:
            tasks = [{'content': 'No tasks', 'overdue': False}]
        
        return tasks
    
    def refresh_data(self):
        """Refresh all status data"""
        self.openclaw_status = self.get_openclaw_status()
        self.system_stats = self.get_system_stats()
        self.todoist_tasks = self.get_todoist_tasks()
        self.last_refresh = time.time()
    
    def draw_text(self, text, font, color, x, y):
        """Draw text at position"""
        surface = font.render(text, True, color)
        self.screen.blit(surface, (x, y))
        return surface.get_width()
    
    def draw_status_section(self):
        """Draw the status section (top 60%)"""
        # Fill status area background
        status_rect = pygame.Rect(0, 0, SCREEN_WIDTH, STATUS_HEIGHT)
        pygame.draw.rect(self.screen, BG_DARK, status_rect)
        
        # Get current time
        now = datetime.now().strftime("%I:%M %p").lstrip('0')
        
        # --- HEADER LINE ---
        y = 8
        
        # Status indicator + title
        status_color = ACCENT_GREEN if self.openclaw_status.get('running') else ACCENT_RED
        self.draw_text("●", self.font_header, status_color, 10, y)
        self.draw_text("OpenClaw", self.font_header, TEXT_PRIMARY, 28, y)
        
        # Time on right
        self.draw_text(now, self.font_header, TEXT_SECONDARY, SCREEN_WIDTH - 85, y)
        
        # Separator line
        y = 30
        pygame.draw.line(self.screen, SEPARATOR, (8, y), (SCREEN_WIDTH - 8, y), 1)
        
        # --- STATUS GRID (2 columns) ---
        y = 40
        col1_x = 12
        col2_x = 250
        line_height = 18
        
        # Column 1: OpenClaw details
        status_text = "running" if self.openclaw_status.get('running') else "stopped"
        self.draw_text(f"Gateway: {status_text}", self.font_status, TEXT_PRIMARY, col1_x, y)
        
        y += line_height
        hb = self.openclaw_status.get('heartbeat', '-')
        self.draw_text(f"Heartbeat: {hb}", self.font_status, TEXT_SECONDARY, col1_x, y)
        
        y += line_height
        model = self.openclaw_status.get('model', '-')
        self.draw_text(f"Model: {model}", self.font_status, TEXT_SECONDARY, col1_x, y)
        
        # Column 2: System stats
        y = 40
        cpu = self.system_stats.get('cpu', 0)
        self.draw_text(f"CPU: {cpu:.0f}%", self.font_status, TEXT_PRIMARY, col2_x, y)
        
        y += line_height
        mem = self.system_stats.get('mem', 0)
        self.draw_text(f"Mem: {mem}M", self.font_status, TEXT_SECONDARY, col2_x, y)
        
        y += line_height
        temp = self.system_stats.get('temp', 0)
        temp_color = ACCENT_RED if temp > 70 else TEXT_SECONDARY
        self.draw_text(f"Temp: {temp:.0f}°C", self.font_status, temp_color, col2_x, y)
        
        # Separator line
        y = 112
        pygame.draw.line(self.screen, SEPARATOR, (8, y), (SCREEN_WIDTH - 8, y), 1)
        
        # --- TASKS SECTION ---
        y = 122
        
        overdue_count = sum(1 for t in self.todoist_tasks if t.get('overdue'))
        if overdue_count > 0:
            tasks_header = f"Tasks ({overdue_count} overdue)"
            header_color = ACCENT_YELLOW
        else:
            tasks_header = f"Tasks ({len(self.todoist_tasks)})"
            header_color = ACCENT_CYAN
        
        self.draw_text(tasks_header, self.font_status, header_color, col1_x, y)
        
        y += 20
        for task in self.todoist_tasks[:3]:  # Show top 3
            content = task['content']
            if len(content) > 38:
                content = content[:35] + "..."
            
            task_color = ACCENT_YELLOW if task.get('overdue') else TEXT_SECONDARY
            self.draw_text(f"• {content}", self.font_small, task_color, col1_x, y)
            y += 16
    
    def draw_terminal_section(self):
        """Draw the terminal section (bottom 40%)"""
        # Terminal background
        term_rect = pygame.Rect(0, STATUS_HEIGHT, SCREEN_WIDTH, TERMINAL_HEIGHT)
        pygame.draw.rect(self.screen, TERMINAL_BG, term_rect)
        
        # Top border
        pygame.draw.line(self.screen, SEPARATOR, (0, STATUS_HEIGHT), (SCREEN_WIDTH, STATUS_HEIGHT), 2)
        
        # Read terminal output
        self.terminal.read_output()
        
        # Get display lines
        num_lines = 8  # Fit ~8 lines in terminal area
        lines = self.terminal.get_display_lines(num_lines)
        
        # Draw terminal content
        y = STATUS_HEIGHT + 8
        line_height = 15
        
        for i, line in enumerate(lines):
            # Truncate long lines
            if len(line) > 60:
                line = line[:57] + "..."
            
            # Last line gets cursor
            if i == len(lines) - 1:
                # Draw line
                width = self.draw_text(line, self.font_terminal, TERMINAL_FG, 8, y)
                
                # Draw cursor
                cursor_x = 8 + width + 2
                cursor_y = y
                if int(time.time() * 2) % 2:  # Blink
                    pygame.draw.rect(self.screen, TERMINAL_CURSOR, 
                                   (cursor_x, cursor_y, 8, 14))
            else:
                self.draw_text(line, self.font_terminal, TERMINAL_FG, 8, y)
            
            y += line_height
    
    def handle_keypress(self, event):
        """Handle keyboard input"""
        # Ctrl+Q = quit
        if event.key == pygame.K_q and event.mod & pygame.KMOD_CTRL:
            return False
        
        # Ctrl+R = refresh
        if event.key == pygame.K_r and event.mod & pygame.KMOD_CTRL:
            self.refresh_data()
            return True
        
        # All other keys go to terminal
        if event.key == pygame.K_RETURN:
            self.terminal.write_input('\n')
        elif event.key == pygame.K_BACKSPACE:
            self.terminal.write_input('\x7f')
        elif event.key == pygame.K_TAB:
            self.terminal.write_input('\t')
        elif event.key == pygame.K_UP:
            self.terminal.write_input('\x1b[A')
        elif event.key == pygame.K_DOWN:
            self.terminal.write_input('\x1b[B')
        elif event.key == pygame.K_LEFT:
            self.terminal.write_input('\x1b[D')
        elif event.key == pygame.K_RIGHT:
            self.terminal.write_input('\x1b[C')
        elif event.unicode:
            # Regular character
            self.terminal.write_input(event.unicode)
        
        return True
    
    def run(self):
        """Main event loop"""
        running = True
        
        # Initial data load
        self.refresh_data()
        
        while running:
            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if not self.handle_keypress(event):
                        running = False
            
            # Auto-refresh status
            if time.time() - self.last_refresh > REFRESH_INTERVAL:
                self.refresh_data()
            
            # Clear screen
            self.screen.fill(BG_DARKER)
            
            # Draw sections
            self.draw_status_section()
            self.draw_terminal_section()
            
            # Update display
            pygame.display.flip()
            
            # Frame rate
            self.clock.tick(30)  # 30 FPS for smooth cursor blink
        
        # Cleanup
        self.terminal.close()
        pygame.quit()

if __name__ == '__main__':
    try:
        app = DashboardApp()
        app.run()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
