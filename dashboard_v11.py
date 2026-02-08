#!/usr/bin/env python3
"""
Pi 400 Dashboard v11 - Safe Commands Edition
For Pimoroni HyperPixel 4.0 (800x480)

Panels:
1. Dashboard - Clock, weather, status
2. Tasks - Todoist integration
3. Chat - Flat list chat interface
4. Commands - Safe command cards with confirmation

F1-F4 or 1-4 to switch panels
"""

import pygame
import sys
import os
import json
import time
import threading
import subprocess
import requests
import pty
import select
import fcntl
import struct
import termios
from datetime import datetime
from collections import deque
from pathlib import Path

try:
    import pyte
except ImportError:
    print("Installing pyte...")
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyte'], check=True)
    import pyte

# Configuration
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 480
GATEWAY_URL = "http://127.0.0.1:18789"
GATEWAY_TOKEN = "8ee708fa05cfe60da1182554737e8f556ff0333784479bf9"
AGENT_ID = "main"
SETTINGS_FILE = Path.home() / '.openclaw' / 'workspace' / 'dashboard' / 'settings.json'
TASKS_FILE = Path.home() / '.openclaw' / 'workspace' / 'dashboard' / 'local_tasks.json'

# Terminal config
TERM_COLS = 95
TERM_ROWS = 24

# Color palette
C = {
    'bg': (18, 18, 22),
    'bg_header': (28, 28, 35),
    'bg_input': (35, 35, 45),
    'bg_overlay': (25, 25, 32),
    'bg_item': (40, 42, 52),
    'bg_item_hover': (55, 58, 72),
    'bg_tab': (35, 38, 48),
    'bg_tab_active': (55, 60, 75),
    'bg_term': (15, 15, 20),
    
    'text': (220, 220, 230),
    'text_bright': (250, 250, 255),
    'text_dim': (140, 140, 160),
    'text_muted': (90, 90, 110),
    
    'accent': (88, 166, 255),
    'success': (82, 196, 125),
    'warning': (255, 193, 70),
    'error': (255, 107, 107),
    
    'user_bubble': (45, 85, 140),
    'bot_bubble': (38, 70, 55),
    'system_bubble': (55, 50, 65),
    
    'border': (50, 50, 65),
    'cursor': (88, 166, 255),
}

# Terminal ANSI colors
TERM_COLORS = {
    'black': (40, 42, 54),
    'red': (255, 85, 85),
    'green': (80, 200, 120),
    'yellow': (241, 250, 140),
    'blue': (100, 160, 255),
    'magenta': (255, 121, 198),
    'cyan': (140, 220, 240),
    'white': (248, 248, 242),
    'default': (220, 225, 235),
}

TEXT_SIZES = {
    'small': {'msg': 12, 'input': 13, 'title': 16, 'status': 10, 'time': 10, 'line_height': 15},
    'medium': {'msg': 14, 'input': 15, 'title': 18, 'status': 12, 'time': 11, 'line_height': 18},
    'large': {'msg': 17, 'input': 18, 'title': 20, 'status': 14, 'time': 13, 'line_height': 22},
}

# Panel modes
MODE_DASHBOARD = 0
MODE_TASKS = 1
MODE_CHAT = 2
MODE_COMMANDS = 3
MODE_NAMES = ['Dashboard', 'Tasks', 'Chat', 'Commands']


class Message:
    def __init__(self, text, role='user', timestamp=None):
        self.text = text
        self.role = role
        self.timestamp = timestamp or datetime.now()


class Settings:
    def __init__(self):
        self.text_size = 'medium'
        self.session_key = 'pi-display'
        self.last_mode = MODE_DASHBOARD
        self.load()
    
    def load(self):
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE) as f:
                    data = json.load(f)
                    self.text_size = data.get('text_size', 'medium')
                    self.session_key = data.get('session_key', 'pi-display')
                    self.last_mode = data.get('last_mode', MODE_DASHBOARD)
        except:
            pass
    
    def save(self):
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SETTINGS_FILE, 'w') as f:
                json.dump({
                    'text_size': self.text_size,
                    'session_key': self.session_key,
                    'last_mode': self.last_mode
                }, f)
        except:
            pass


class Terminal:
    """Embedded terminal using pyte"""
    
    def __init__(self, cols=TERM_COLS, rows=TERM_ROWS):
        self.cols = cols
        self.rows = rows
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.Stream(self.screen)
        self.master_fd = None
        self.pid = None
        self.started = False
        
    def start(self, command=['bash', '--login'], auto_command='openclaw tui --url ws://127.0.0.1:18789 --token 8ee708fa05cfe60da1182554737e8f556ff0333784479bf9'):
        if self.started:
            return
            
        self.pid, self.master_fd = pty.fork()
        
        if self.pid == 0:
            # Child process
            os.chdir(os.path.expanduser('~'))
            env = os.environ.copy()
            env['TERM'] = 'xterm-256color'
            env['COLUMNS'] = str(self.cols)
            env['LINES'] = str(self.rows)
            os.execvpe(command[0], command, env)
        else:
            # Parent
            flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
            fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            # Set terminal size
            size = struct.pack('HHHH', self.rows, self.cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, size)
            self.started = True
            
            # Auto-run command after shell starts
            if auto_command:
                time.sleep(0.5)  # Let bash initialize
                self.write(auto_command + '\n')
            
    def read(self):
        if not self.started or self.master_fd is None:
            return
        try:
            while True:
                r, _, _ = select.select([self.master_fd], [], [], 0)
                if not r:
                    break
                data = os.read(self.master_fd, 4096)
                if data:
                    self.stream.feed(data.decode('utf-8', errors='replace'))
                else:
                    break
        except (OSError, IOError):
            pass
            
    def write(self, data):
        if self.started and self.master_fd:
            try:
                os.write(self.master_fd, data.encode('utf-8'))
            except:
                pass
                
    def send_key(self, key):
        self.write(key)
        
    def stop(self):
        if self.pid:
            try:
                os.kill(self.pid, 9)
            except:
                pass
        if self.master_fd:
            try:
                os.close(self.master_fd)
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
        pygame.display.set_caption('OpenClaw Dashboard')
        pygame.mouse.set_visible(False)
        
        self.settings = Settings()
        self.rebuild_fonts()
        
        # Current mode
        self.mode = self.settings.last_mode
        
        # Chat state
        self.messages = deque(maxlen=100)
        self.conversation = []
        self.chat_input = ""
        self.chat_cursor = 0
        self.chat_scroll = 0
        self.chat_waiting = False
        self.chat_status = "ready"
        self.chat_menu_open = False
        self.chat_menu_mode = 'main'
        self.chat_menu_selection = 0
        self.available_sessions = []
        
        # Terminal state
        self.terminal = Terminal()
        self.terminal_started = False
        
        # Tasks state (local task list)
        self.tasks = []
        self.task_selected = 0
        self.task_editing = False
        self.task_edit_text = ""
        self.task_edit_cursor = 0
        self.task_scroll = 0
        self.load_local_tasks()
        
        # Dashboard state
        self.weather = None
        self.weather_loading = False
        self.weather_last_load = 0
        
        # Commands state
        self.command_selection = 0
        self.command_confirm = None  # Which command is awaiting confirmation
        self.command_running = None  # Which command is currently running
        self.command_result = None   # Last command result
        
        # Screen off state
        self.screen_off = False
        
        self.clock = pygame.time.Clock()
        self.messages.append(Message(f"Session: {self.settings.session_key}", 'system'))
        
    def rebuild_fonts(self):
        sizes = TEXT_SIZES[self.settings.text_size]
        self.fonts = {
            'title': pygame.font.SysFont('liberationsans', sizes['title'], bold=True),
            'big': pygame.font.SysFont('liberationsans', 48, bold=True),
            'msg': pygame.font.SysFont('liberationsans', sizes['msg']),
            'input': pygame.font.SysFont('liberationsans', sizes['input']),
            'time': pygame.font.SysFont('liberationsans', sizes['time']),
            'status': pygame.font.SysFont('liberationsans', sizes['status']),
            'menu': pygame.font.SysFont('liberationsans', 14),
            'menu_title': pygame.font.SysFont('liberationsans', 16, bold=True),
            'term': pygame.font.SysFont('liberationmono', 12),
            'task': pygame.font.SysFont('liberationsans', 13),
            'button': pygame.font.SysFont('liberationsans', 13, bold=True),
            'button_desc': pygame.font.SysFont('liberationsans', 11),
        }
        self.line_height = sizes['line_height']
        
    def switch_mode(self, mode):
        self.mode = mode
        self.settings.last_mode = mode
        self.settings.save()
        
        # Reset command state when leaving commands panel
        if mode != MODE_COMMANDS:
            self.command_confirm = None
            self.command_result = None
        
            
    def load_local_tasks(self):
        """Load tasks from local JSON file"""
        try:
            if TASKS_FILE.exists():
                with open(TASKS_FILE) as f:
                    self.tasks = json.load(f)
            else:
                self.tasks = []
        except:
            self.tasks = []
            
    def save_local_tasks(self):
        """Save tasks to local JSON file"""
        try:
            TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(TASKS_FILE, 'w') as f:
                json.dump(self.tasks, f, indent=2)
        except:
            pass
            
    def add_task(self):
        """Add a new task and enter edit mode"""
        new_task = {
            'id': int(time.time() * 1000),
            'content': '',
            'priority': 1,
            'done': False
        }
        self.tasks.insert(0, new_task)
        self.task_selected = 0
        self.task_editing = True
        self.task_edit_text = ''
        self.task_edit_cursor = 0
        
    def delete_task(self):
        """Delete the selected task"""
        if self.tasks and 0 <= self.task_selected < len(self.tasks):
            self.tasks.pop(self.task_selected)
            self.save_local_tasks()
            if self.task_selected >= len(self.tasks) and self.tasks:
                self.task_selected = len(self.tasks) - 1
                
    def toggle_task_done(self):
        """Toggle done state of selected task"""
        if self.tasks and 0 <= self.task_selected < len(self.tasks):
            self.tasks[self.task_selected]['done'] = not self.tasks[self.task_selected].get('done', False)
            self.save_local_tasks()
            
    def cycle_task_priority(self):
        """Cycle priority of selected task (1 -> 2 -> 3 -> 4 -> 1)"""
        if self.tasks and 0 <= self.task_selected < len(self.tasks):
            current = self.tasks[self.task_selected].get('priority', 1)
            self.tasks[self.task_selected]['priority'] = (current % 4) + 1
            self.save_local_tasks()
            
    def move_task(self, direction):
        """Move selected task up or down"""
        if not self.tasks:
            return
        new_idx = self.task_selected + direction
        if 0 <= new_idx < len(self.tasks):
            self.tasks[self.task_selected], self.tasks[new_idx] = self.tasks[new_idx], self.tasks[self.task_selected]
            self.task_selected = new_idx
            self.save_local_tasks()
        
    def load_weather(self):
        if self.weather_loading:
            return
        if time.time() - self.weather_last_load < 300:  # 5 min cache
            return
            
        self.weather_loading = True
        threading.Thread(target=self._load_weather_async, daemon=True).start()
        
    def _load_weather_async(self):
        try:
            # Use wttr.in for simple weather
            response = requests.get('https://wttr.in/?format=%t+%C', timeout=5)
            if response.status_code == 200:
                self.weather = response.text.strip()
        except:
            self.weather = None
        self.weather_loading = False
        self.weather_last_load = time.time()
        
    # ===== CHAT METHODS =====
    
    def chat_send_message(self):
        if not self.chat_input.strip() or self.chat_waiting:
            return
            
        msg = self.chat_input.strip()
        self.chat_input = ""
        self.chat_cursor = 0
        
        if msg.startswith('/'):
            if self.chat_handle_command(msg):
                return
        
        self.messages.append(Message(msg, 'user'))
        self.conversation.append({"role": "user", "content": msg})
        self.chat_scroll = 0
        self.chat_waiting = True
        self.chat_status = "thinking"
        
        threading.Thread(target=self._chat_send_async, args=(msg,), daemon=True).start()
        
    def _chat_send_async(self, user_msg):
        try:
            url = f"{GATEWAY_URL}/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {GATEWAY_TOKEN}",
                "x-openclaw-session-key": self.settings.session_key
            }
            
            payload = {
                "model": f"openclaw:{AGENT_ID}",
                "messages": self.conversation[-10:]
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    self.messages.append(Message(content, 'assistant'))
                    self.conversation.append({"role": "assistant", "content": content})
                    self.chat_status = "ready"
                else:
                    self.messages.append(Message("[Empty]", 'system'))
                    self.chat_status = "ready"
            else:
                self.messages.append(Message(f"[HTTP {response.status_code}]", 'system'))
                self.chat_status = "error"
        except Exception as e:
            self.messages.append(Message(f"[{str(e)[:25]}]", 'system'))
            self.chat_status = "error"
            
        self.chat_waiting = False
        self.chat_scroll = 0
        
    def chat_handle_command(self, cmd):
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        if command in ['/help', '/?']:
            self.messages.append(Message(
                "/sessions - List sessions\n"
                "/session <key> - Switch\n"
                "/new - New session\n"
                "/size s/m/l - Text size\n"
                "/clear - Clear chat\n"
                "F1-F4 - Switch panels",
                'system'
            ))
            return True
        elif command in ['/sessions', '/s']:
            self.chat_menu_open = True
            self.chat_menu_mode = 'sessions'
            self._fetch_sessions()
            return True
        elif command == '/session' and args:
            self.settings.session_key = args
            self.settings.save()
            self.conversation.clear()
            self.messages.append(Message(f"Session: {args}", 'system'))
            return True
        elif command in ['/new', '/n']:
            self.settings.session_key = f"pi-{datetime.now().strftime('%H%M')}"
            self.settings.save()
            self.conversation.clear()
            self.messages.append(Message(f"New: {self.settings.session_key}", 'system'))
            return True
        elif command == '/size' and args:
            if args[0] in ['s', 'm', 'l']:
                size_map = {'s': 'small', 'm': 'medium', 'l': 'large'}
                self.settings.text_size = size_map.get(args[0], args)
                self.settings.save()
                self.rebuild_fonts()
                self.messages.append(Message(f"Size: {self.settings.text_size}", 'system'))
            return True
        elif command in ['/clear', '/c']:
            self.conversation.clear()
            self.messages.clear()
            self.messages.append(Message("Cleared", 'system'))
            return True
        elif command == '/status':
            self.messages.append(Message(f"Session: {self.settings.session_key}\nMsgs: {len(self.conversation)}", 'system'))
            return True
        return False
        
    def _fetch_sessions(self):
        """Fetch sessions in background thread"""
        if hasattr(self, '_sessions_loading') and self._sessions_loading:
            return
        self._sessions_loading = True
        self.available_sessions = [{'key': 'loading', 'name': 'Loading...'}]
        threading.Thread(target=self._fetch_sessions_async, daemon=True).start()
        
    def _fetch_sessions_async(self):
        try:
            result = subprocess.run(['openclaw', 'sessions', '--json'],
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                sessions = []
                for s in data.get('sessions', []):
                    key = s.get('key', '')
                    # Create friendly name
                    name = self._friendly_session_name(key, s)
                    sessions.append({'key': key, 'name': name})
                self.available_sessions = sessions
        except Exception as e:
            self.available_sessions = [{'key': '', 'name': f'Error: {str(e)[:15]}'}]
        self._sessions_loading = False
        
    def _friendly_session_name(self, key, session_data):
        """Convert session key to friendly display name"""
        display = session_data.get('displayName', '')
        
        if ':main' in key and key.endswith(':main'):
            return "📱 Main"
        elif 'pi-' in key or 'pi-display' in key:
            return "🖥️ Pi Display"
        elif 'discord' in key:
            if '#' in display:
                channel = display.split('#')[-1][:15]
                return f"💬 #{channel}"
            return "💬 Discord"
        elif 'slack' in key:
            return "💼 Slack"
        elif 'whatsapp' in key:
            return "📲 WhatsApp"
        elif 'openai:' in key:
            return "🔌 API Session"
        elif 'cron:' in key:
            return "⏰ Scheduled"
        else:
            short = key.split(':')[-1][:12]
            return short.replace('-', ' ').title()
            
    # ===== COMMAND METHODS =====
    
    def get_commands(self):
        """Return list of available commands"""
        return [
            {
                'label': 'Gateway Status',
                'desc': 'Check gateway status',
                'cmd': 'openclaw status',
                'color': C['accent'],
                'safe': True
            },
            {
                'label': 'Node Status',
                'desc': 'Check node connection',
                'cmd': 'openclaw nodes status',
                'color': C['accent'],
                'safe': True
            },
            {
                'label': 'Ping Test',
                'desc': 'Check internet',
                'cmd': 'ping -c 3 8.8.8.8 | tail -1',
                'color': C['accent'],
                'safe': True
            },
            {
                'label': 'Restart Gateway',
                'desc': 'Restart OpenClaw',
                'cmd': 'systemctl --user restart openclaw-gateway',
                'color': C['warning'],
                'safe': False
            },
            {
                'label': 'Update Gateway',
                'desc': 'Pull latest & install',
                'cmd': 'cd ~/.openclaw && git pull && npm install',
                'color': C['warning'],
                'safe': False
            },
            {
                'label': 'Disk Space',
                'desc': 'Check storage',
                'cmd': "df -h / | awk 'NR==2 {print $3 \"/\" $2 \" (\" $5 \" used)\"}'",
                'color': C['accent'],
                'safe': True
            },
            {
                'label': 'Reboot Pi',
                'desc': 'System reboot',
                'cmd': 'sudo reboot',
                'color': C['error'],
                'safe': False
            },
            {
                'label': 'Shutdown Pi',
                'desc': 'Power off system',
                'cmd': 'sudo shutdown -h now',
                'color': C['error'],
                'safe': False
            },
            {
                'label': 'Screen Off',
                'desc': 'Any key to wake',
                'cmd': '__screen_off__',
                'color': C['text_dim'],
                'safe': True
            },
        ]
        
    def execute_command(self, cmd_idx):
        """Execute a command by index"""
        commands = self.get_commands()
        if 0 <= cmd_idx < len(commands):
            cmd = commands[cmd_idx]
            
            # Special handling for screen off
            if cmd['cmd'] == '__screen_off__':
                self.screen_off = True
                return
            
            # Safe commands run immediately
            if cmd['safe']:
                self.command_running = cmd['label']
                self.command_result = None
                threading.Thread(target=self._run_command_async, args=(cmd,), daemon=True).start()
            else:
                # Dangerous commands need confirmation
                self.command_confirm = cmd_idx
                
    def confirm_command(self, confirmed):
        """Handle command confirmation"""
        if self.command_confirm is None:
            return
            
        if confirmed:
            commands = self.get_commands()
            cmd = commands[self.command_confirm]
            self.command_running = cmd['label']
            self.command_result = None
            threading.Thread(target=self._run_command_async, args=(cmd,), daemon=True).start()
        
        self.command_confirm = None
        
    def _run_command_async(self, cmd):
        """Run command in background thread"""
        try:
            result = subprocess.run(
                cmd['cmd'],
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()[:100] if result.stdout else "✓ Success"
                self.command_result = ('success', output)
            else:
                error = result.stderr.strip()[:100] if result.stderr else f"Exit code: {result.returncode}"
                self.command_result = ('error', error)
        except subprocess.TimeoutExpired:
            self.command_result = ('error', 'Command timeout')
        except Exception as e:
            self.command_result = ('error', str(e)[:100])
        
        self.command_running = None
        
        # Result stays visible until user presses a key
            
    # ===== DRAWING =====
    
    def draw_tabs(self):
        """Draw tab bar at top"""
        tab_h = 28
        tab_w = SCREEN_WIDTH // 4
        
        for i, name in enumerate(MODE_NAMES):
            x = i * tab_w
            is_active = i == self.mode
            
            color = C['bg_tab_active'] if is_active else C['bg_tab']
            pygame.draw.rect(self.screen, color, (x, 0, tab_w - 1, tab_h))
            
            if is_active:
                pygame.draw.rect(self.screen, C['accent'], (x, tab_h - 3, tab_w - 1, 3))
            
            text_color = C['text_bright'] if is_active else C['text_dim']
            label = self.fonts['status'].render(f"F{i+1} {name}", True, text_color)
            self.screen.blit(label, (x + (tab_w - label.get_width()) // 2, 7))
            
        pygame.draw.line(self.screen, C['border'], (0, tab_h), (SCREEN_WIDTH, tab_h), 1)
        
    def draw_dashboard(self):
        """Draw dashboard panel"""
        y_start = 32
        
        # Big clock (12hr format)
        now = datetime.now()
        time_str = now.strftime("%I:%M %p").lstrip('0')
        time_surf = self.fonts['big'].render(time_str, True, C['text_bright'])
        self.screen.blit(time_surf, ((SCREEN_WIDTH - time_surf.get_width()) // 2, y_start + 20))
        
        # Date
        date_str = now.strftime("%A, %B %d")
        date_surf = self.fonts['title'].render(date_str, True, C['text_dim'])
        self.screen.blit(date_surf, ((SCREEN_WIDTH - date_surf.get_width()) // 2, y_start + 80))
        
        # Weather
        if self.weather:
            weather_surf = self.fonts['msg'].render(self.weather, True, C['text'])
            self.screen.blit(weather_surf, ((SCREEN_WIDTH - weather_surf.get_width()) // 2, y_start + 115))
        else:
            self.load_weather()
            
        # Status cards
        card_y = y_start + 160
        card_h = 50
        card_w = 145
        
        # Session card
        pygame.draw.rect(self.screen, C['bg_item'], (20, card_y, card_w, card_h), border_radius=8)
        self.fonts['status'].render("Session", True, C['text_muted'])
        label = self.fonts['status'].render("Session", True, C['text_muted'])
        self.screen.blit(label, (30, card_y + 8))
        val = self.fonts['msg'].render(self.settings.session_key[:12], True, C['text'])
        self.screen.blit(val, (30, card_y + 26))
        
        # Gateway card
        pygame.draw.rect(self.screen, C['bg_item'], (175, card_y, card_w, card_h), border_radius=8)
        label = self.fonts['status'].render("Gateway", True, C['text_muted'])
        self.screen.blit(label, (185, card_y + 8))
        val = self.fonts['msg'].render("● Online", True, C['success'])
        self.screen.blit(val, (185, card_y + 26))
        
        # Tasks card
        pygame.draw.rect(self.screen, C['bg_item'], (330, card_y, card_w - 10, card_h), border_radius=8)
        label = self.fonts['status'].render("Tasks", True, C['text_muted'])
        self.screen.blit(label, (340, card_y + 8))
        task_count = len(self.tasks) if self.tasks else "?"
        val = self.fonts['msg'].render(f"{task_count} today", True, C['warning'] if self.tasks else C['text_dim'])
        self.screen.blit(val, (340, card_y + 26))
        
        # Hint
        hint = "F2: Tasks  F3: Chat  F4: Commands"
        hint_surf = self.fonts['status'].render(hint, True, C['text_muted'])
        self.screen.blit(hint_surf, ((SCREEN_WIDTH - hint_surf.get_width()) // 2, SCREEN_HEIGHT - 24))
        
    def draw_tasks(self):
        """Draw local task cards"""
        y_start = 36
        card_height = 36
        card_margin = 4
        max_visible = 7
        
        # Header with count
        count_text = f"Tasks ({len(self.tasks)})"
        header = self.fonts['title'].render(count_text, True, C['text_bright'])
        self.screen.blit(header, (16, y_start))
        
        if not self.tasks:
            empty = self.fonts['msg'].render("No tasks. Press N to add one.", True, C['text_dim'])
            self.screen.blit(empty, (16, y_start + 50))
        else:
            # Ensure scroll keeps selection visible
            if self.task_selected < self.task_scroll:
                self.task_scroll = self.task_selected
            elif self.task_selected >= self.task_scroll + max_visible:
                self.task_scroll = self.task_selected - max_visible + 1
                
            # Draw visible task cards
            visible_tasks = self.tasks[self.task_scroll:self.task_scroll + max_visible]
            card_y = y_start + 32
            
            for i, task in enumerate(visible_tasks):
                actual_idx = self.task_scroll + i
                is_selected = actual_idx == self.task_selected
                is_done = task.get('done', False)
                priority = task.get('priority', 1)
                
                # Card background
                card_rect = (8, card_y, SCREEN_WIDTH - 16, card_height)
                bg_color = C['bg_item_hover'] if is_selected else C['bg_item']
                pygame.draw.rect(self.screen, bg_color, card_rect, border_radius=6)
                
                # Selection indicator
                if is_selected:
                    pygame.draw.rect(self.screen, C['accent'], (8, card_y, 3, card_height), border_radius=2)
                
                # Priority indicator (left side colored bar)
                priority_colors = {1: C['text_dim'], 2: C['success'], 3: C['warning'], 4: C['error']}
                p_color = priority_colors.get(priority, C['text_dim'])
                pygame.draw.rect(self.screen, p_color, (14, card_y + 8, 4, card_height - 16), border_radius=2)
                
                # Done checkbox
                checkbox_x = 26
                checkbox_y = card_y + (card_height - 16) // 2
                checkbox_rect = (checkbox_x, checkbox_y, 16, 16)
                pygame.draw.rect(self.screen, C['border'], checkbox_rect, width=2, border_radius=3)
                if is_done:
                    # Checkmark
                    pygame.draw.line(self.screen, C['success'], (checkbox_x + 3, checkbox_y + 8), (checkbox_x + 6, checkbox_y + 12), 2)
                    pygame.draw.line(self.screen, C['success'], (checkbox_x + 6, checkbox_y + 12), (checkbox_x + 13, checkbox_y + 4), 2)
                
                # Task content
                content_x = 50
                if is_selected and self.task_editing:
                    # Editing mode - show input with cursor
                    display_text = self.task_edit_text
                    text_color = C['text_bright']
                    text_surf = self.fonts['msg'].render(display_text[:40], True, text_color)
                    self.screen.blit(text_surf, (content_x, card_y + 10))
                    
                    # Draw cursor
                    cursor_x = content_x + self.fonts['msg'].size(display_text[:self.task_edit_cursor])[0]
                    if int(time.time() * 2) % 2:
                        pygame.draw.line(self.screen, C['cursor'], (cursor_x, card_y + 8), (cursor_x, card_y + 28), 2)
                else:
                    # Normal display
                    content = task.get('content', '')[:40] or '(empty)'
                    text_color = C['text_dim'] if is_done else C['text']
                    text_surf = self.fonts['msg'].render(content, True, text_color)
                    self.screen.blit(text_surf, (content_x, card_y + 10))
                
                card_y += card_height + card_margin
        
        # Help bar at bottom
        if self.task_editing:
            hint = "Enter: Save | Esc: Cancel"
        else:
            hint = "N: New | Enter: Edit | Space: Done | P: Priority | Del: Remove"
        hint_surf = self.fonts['status'].render(hint, True, C['text_muted'])
        hint_x = (SCREEN_WIDTH - hint_surf.get_width()) // 2
        self.screen.blit(hint_surf, (hint_x, SCREEN_HEIGHT - 22))
        
    def draw_commands(self):
        """Draw commands panel with cards"""
        y_start = 36
        
        # Show confirmation dialog if active
        if self.command_confirm is not None:
            self._draw_confirm_dialog()
            return
            
        # Show running indicator if active
        if self.command_running:
            running_text = f"Running: {self.command_running}..."
            running_surf = self.fonts['msg'].render(running_text[:40], True, C['accent'])
            self.screen.blit(running_surf, (16, y_start))
            
            # Spinner
            dots = "●" * (int(time.time() * 2) % 3 + 1)
            dots_surf = self.fonts['title'].render(dots, True, C['accent'])
            self.screen.blit(dots_surf, (16, y_start + 25))
            return
            
        # Show result if available
        if self.command_result:
            result_type, result_msg = self.command_result
            color = C['success'] if result_type == 'success' else C['error']
            
            # Result header
            header = "✓ Success" if result_type == 'success' else "✗ Error"
            header_surf = self.fonts['title'].render(header, True, color)
            self.screen.blit(header_surf, (16, y_start))
            
            # Result message
            msg_surf = self.fonts['msg'].render(result_msg[:45], True, C['text'])
            self.screen.blit(msg_surf, (16, y_start + 30))
            
            # Hint
            hint = "Press any key to continue"
            hint_surf = self.fonts['status'].render(hint, True, C['text_dim'])
            self.screen.blit(hint_surf, (16, y_start + 55))
            return
        
        # Draw command cards
        commands = self.get_commands()
        
        # 3x3 grid - fits 800x480 screen
        card_w = 245
        card_h = 85
        margin_x = 12
        margin_y = 10
        spacing_x = 10
        spacing_y = 10
        
        for idx, cmd in enumerate(commands):
            col = idx % 3
            row = idx // 3
            
            x = margin_x + col * (card_w + spacing_x)
            y = y_start + row * (card_h + spacing_y)
            
            # Highlight if selected
            is_selected = idx == self.command_selection
            bg_color = C['bg_item_hover'] if is_selected else C['bg_item']
            
            # Card background
            pygame.draw.rect(self.screen, bg_color, (x, y, card_w, card_h), border_radius=8)
            pygame.draw.rect(self.screen, cmd['color'], (x, y, card_w, card_h), width=2, border_radius=8)
            
            # Label
            label_surf = self.fonts['button'].render(cmd['label'], True, C['text_bright'])
            label_x = x + (card_w - label_surf.get_width()) // 2
            self.screen.blit(label_surf, (label_x, y + 10))
            
            # Description
            desc_surf = self.fonts['button_desc'].render(cmd['desc'], True, C['text_dim'])
            desc_x = x + (card_w - desc_surf.get_width()) // 2
            self.screen.blit(desc_surf, (desc_x, y + 30))
            
            # Safety indicator
            if not cmd['safe']:
                warn_surf = self.fonts['status'].render("⚠", True, C['warning'])
                self.screen.blit(warn_surf, (x + 6, y + 6))
        
        # Instructions
        help_text = "↑↓←→: Navigate  Enter: Execute  ESC: Cancel"
        help_surf = self.fonts['status'].render(help_text, True, C['text_dim'])
        help_x = (SCREEN_WIDTH - help_surf.get_width()) // 2
        self.screen.blit(help_surf, (help_x, SCREEN_HEIGHT - 20))
        
    def _draw_confirm_dialog(self):
        """Draw confirmation dialog"""
        # Dim background
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        overlay.fill((0, 0, 0))
        overlay.set_alpha(200)
        self.screen.blit(overlay, (0, 0))
        
        # Dialog box
        dialog_w, dialog_h = 450, 180
        dialog_x = (SCREEN_WIDTH - dialog_w) // 2
        dialog_y = (SCREEN_HEIGHT - dialog_h) // 2
        
        pygame.draw.rect(self.screen, C['bg_overlay'], (dialog_x, dialog_y, dialog_w, dialog_h), border_radius=12)
        pygame.draw.rect(self.screen, C['error'], (dialog_x, dialog_y, dialog_w, dialog_h), width=3, border_radius=12)
        
        # Title
        title = "⚠ Confirm Action"
        title_surf = self.fonts['menu_title'].render(title, True, C['text_bright'])
        title_x = dialog_x + (dialog_w - title_surf.get_width()) // 2
        self.screen.blit(title_surf, (title_x, dialog_y + 16))
        
        # Command info
        commands = self.get_commands()
        cmd = commands[self.command_confirm]
        
        msg = f"Execute: {cmd['label']}?"
        msg_surf = self.fonts['msg'].render(msg, True, C['text'])
        msg_x = dialog_x + (dialog_w - msg_surf.get_width()) // 2
        self.screen.blit(msg_surf, (msg_x, dialog_y + 50))
        
        # Warning
        warn = "This action cannot be undone"
        warn_surf = self.fonts['status'].render(warn, True, C['warning'])
        warn_x = dialog_x + (dialog_w - warn_surf.get_width()) // 2
        self.screen.blit(warn_surf, (warn_x, dialog_y + 75))
        
        # Buttons
        button_y = dialog_y + dialog_h - 36
        button_h = 28
        
        # Cancel button
        cancel_x = dialog_x + 40
        cancel_w = 100
        pygame.draw.rect(self.screen, C['bg_item'], (cancel_x, button_y, cancel_w, button_h), border_radius=6)
        cancel_text = self.fonts['button'].render("ESC Cancel", True, C['text_dim'])
        cancel_text_x = cancel_x + (cancel_w - cancel_text.get_width()) // 2
        self.screen.blit(cancel_text, (cancel_text_x, button_y + 6))
        
        # Confirm button
        confirm_x = dialog_x + dialog_w - 140
        confirm_w = 100
        pygame.draw.rect(self.screen, C['error'], (confirm_x, button_y, confirm_w, button_h), border_radius=6)
        confirm_text = self.fonts['button'].render("⏎ Confirm", True, C['text_bright'])
        confirm_text_x = confirm_x + (confirm_w - confirm_text.get_width()) // 2
        self.screen.blit(confirm_text, (confirm_text_x, button_y + 6))
                
    def draw_chat(self):
        """Draw chat panel"""
        y_start = 32
        
        # Session indicator at top
        session_text = f"Session: {self.settings.session_key}"
        session_surf = self.fonts['status'].render(session_text[:35], True, C['text_dim'])
        self.screen.blit(session_surf, (10, y_start + 4))
        y_start += 20
        
        # Messages
        msg_bottom = SCREEN_HEIGHT - 52
        messages = list(self.messages)
        
        if self.chat_scroll > 0 and len(messages) > self.chat_scroll:
            messages = messages[:-self.chat_scroll]
            
        y = msg_bottom
        for msg in reversed(messages):
            new_y = self._draw_bubble(msg, y, y_start + 8)
            if new_y is None:
                break
            y = new_y
            
        # Thinking indicator
        if self.chat_waiting:
            dots = "●" * (int(time.time() * 2) % 3 + 1)
            dots_surf = self.fonts['msg'].render(dots, True, C['accent'])
            self.screen.blit(dots_surf, (14, msg_bottom - 20))
            
        # Scroll indicator
        if self.chat_scroll > 0:
            scroll_text = f"↑ {self.chat_scroll} older"
            scroll_surf = self.fonts['status'].render(scroll_text, True, C['warning'])
            self.screen.blit(scroll_surf, (SCREEN_WIDTH - scroll_surf.get_width() - 10, y_start + 4))
            
        # Input
        input_y = SCREEN_HEIGHT - 48
        pygame.draw.line(self.screen, C['border'], (0, input_y), (SCREEN_WIDTH, input_y), 1)
        
        box = (8, input_y + 6, SCREEN_WIDTH - 16, 36)
        pygame.draw.rect(self.screen, C['bg_input'], box, border_radius=8)
        
        # Input with scrolling
        display_text = self.chat_input
        cursor_pos = self.chat_cursor
        
        # Calculate max width based on available space
        input_box_width = SCREEN_WIDTH - 16 - 32
        
        # Dynamic text scrolling based on pixel width
        if self.chat_input:
            full_width = self.fonts['input'].size(display_text)[0]
            if full_width > input_box_width:
                cursor_x = self.fonts['input'].size(display_text[:cursor_pos])[0]
                
                if cursor_x > input_box_width - 20:
                    offset = 0
                    while offset < len(display_text):
                        remaining = display_text[offset:]
                        remaining_cursor = cursor_pos - offset
                        if self.fonts['input'].size(remaining[:remaining_cursor])[0] < input_box_width - 40:
                            break
                        offset += 1
                    display_text = display_text[offset:]
                    cursor_pos = cursor_pos - offset
        
        display = display_text or ("..." if self.chat_waiting else "/help for commands")
        color = C['text'] if self.chat_input else C['text_muted']
        surf = self.fonts['input'].render(display, True, color)
        self.screen.blit(surf, (16, input_y + 15))
        
        # Cursor
        if self.chat_input and int(time.time() * 2) % 2 and not self.chat_waiting:
            cx = 16 + self.fonts['input'].size(display_text[:cursor_pos])[0]
            pygame.draw.rect(self.screen, C['cursor'], (cx, input_y + 12, 2, 20))
            
        # Menu overlay
        if self.chat_menu_open:
            self._draw_chat_menu()
            
    def _draw_bubble(self, msg, y, min_y):
        is_user = msg.role == 'user'
        is_system = msg.role == 'system'
        
        margin = 6
        max_w = SCREEN_WIDTH - margin * 2 - 8
        
        # Prefix for role
        if is_user:
            prefix = "You: "
            text_color = C['accent']
        elif is_system:
            prefix = "System: "
            text_color = C['warning']
        else:
            prefix = "Bot: "
            text_color = C['success']
        
        # Word wrap with prefix on first line
        full_text = prefix + msg.text
        lines = self._word_wrap(full_text, 'msg', max_w)
        
        msg_h = len(lines) * self.line_height + 2
        
        if y - msg_h < min_y:
            return None
            
        y = y - msg_h
        
        # Draw lines
        ty = y
        for i, line in enumerate(lines):
            if i == 0:
                prefix_surf = self.fonts['msg'].render(prefix, True, text_color)
                self.screen.blit(prefix_surf, (margin, ty))
                
                text_after = line[len(prefix):]
                if text_after:
                    text_surf = self.fonts['msg'].render(text_after, True, C['text'])
                    prefix_w = self.fonts['msg'].size(prefix)[0]
                    self.screen.blit(text_surf, (margin + prefix_w, ty))
            else:
                surf = self.fonts['msg'].render(line, True, C['text'])
                self.screen.blit(surf, (margin, ty))
            ty += self.line_height
            
        return y - 2
        
    def _word_wrap(self, text, font, max_w):
        words = text.replace('\n', ' \n ').split(' ')
        lines, current = [], ""
        for word in words:
            if word == '\n':
                if current: lines.append(current)
                current = ""
                continue
            test = current + (' ' if current else '') + word
            if self.fonts[font].size(test)[0] <= max_w:
                current = test
            else:
                if current: lines.append(current)
                current = word
        if current: lines.append(current)
        return lines or [""]
        
    def _draw_chat_menu(self):
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        overlay.fill((0, 0, 0))
        overlay.set_alpha(180)
        self.screen.blit(overlay, (0, 0))
        
        menu_w, menu_h = 280, 220
        menu_x = (SCREEN_WIDTH - menu_w) // 2
        menu_y = (SCREEN_HEIGHT - menu_h) // 2
        
        pygame.draw.rect(self.screen, C['bg_overlay'], (menu_x, menu_y, menu_w, menu_h), border_radius=10)
        pygame.draw.rect(self.screen, C['border'], (menu_x, menu_y, menu_w, menu_h), width=1, border_radius=10)
        
        title = "Switch Session"
        title_surf = self.fonts['menu_title'].render(title, True, C['text_bright'])
        self.screen.blit(title_surf, (menu_x + 16, menu_y + 12))
        
        if hasattr(self, '_sessions_loading') and self._sessions_loading:
            loading_surf = self.fonts['status'].render("loading...", True, C['accent'])
            self.screen.blit(loading_surf, (menu_x + menu_w - 80, menu_y + 14))
        
        pygame.draw.line(self.screen, C['border'], (menu_x + 10, menu_y + 38), (menu_x + menu_w - 10, menu_y + 38))
        
        items = ["➕ New Session"] + [s['name'] for s in self.available_sessions[:6]]
        item_y = menu_y + 46
        for i, item in enumerate(items):
            is_sel = i == self.chat_menu_selection
            
            is_current = False
            if i > 0 and i <= len(self.available_sessions):
                is_current = self.available_sessions[i-1]['key'] == self.settings.session_key
            
            if is_sel:
                pygame.draw.rect(self.screen, C['bg_item_hover'], (menu_x + 8, item_y, menu_w - 16, 24), border_radius=4)
            
            prefix = "✓ " if is_current else "  "
            color = C['accent'] if is_current else (C['text_bright'] if is_sel else C['text'])
            surf = self.fonts['menu'].render(prefix + item[:22], True, color)
            self.screen.blit(surf, (menu_x + 12, item_y + 4))
            item_y += 26
            
        hint = "Enter: Select | Esc: Cancel"
        hint_surf = self.fonts['status'].render(hint, True, C['text_muted'])
        self.screen.blit(hint_surf, (menu_x + (menu_w - hint_surf.get_width()) // 2, menu_y + menu_h - 20))
            
    def draw(self):
        # Screen off mode - just black
        if self.screen_off:
            self.screen.fill((0, 0, 0))
            pygame.display.flip()
            return
            
        self.screen.fill(C['bg'])
        self.draw_tabs()
        
        if self.mode == MODE_DASHBOARD:
            self.draw_dashboard()
        elif self.mode == MODE_TASKS:
            self.draw_tasks()
        elif self.mode == MODE_CHAT:
            self.draw_chat()
        elif self.mode == MODE_COMMANDS:
            self.draw_commands()
            
        pygame.display.flip()
        
    def handle_key(self, event):
        # Wake from screen off on any key
        if self.screen_off:
            self.screen_off = False
            return
            
        # Global keys
        if event.key == pygame.K_F1:
            self.switch_mode(MODE_DASHBOARD)
            return
        elif event.key == pygame.K_F2:
            self.switch_mode(MODE_TASKS)
            return
        elif event.key == pygame.K_F3:
            self.switch_mode(MODE_CHAT)
            return
        elif event.key == pygame.K_F4:
            self.switch_mode(MODE_COMMANDS)
            return
                
        # Ctrl+Q behavior
        if event.key == pygame.K_q and event.mod & pygame.KMOD_CTRL:
            if self.mode == MODE_DASHBOARD:
                return 'quit'
            else:
                self.switch_mode(MODE_DASHBOARD)
                return
                
        # Mode-specific
        if self.mode == MODE_CHAT:
            self._handle_chat_key(event)
        elif self.mode == MODE_COMMANDS:
            self._handle_commands_key(event)
        elif self.mode == MODE_TASKS:
            self._handle_tasks_key(event)
                
    def _handle_chat_key(self, event):
        if self.chat_menu_open:
            if event.key == pygame.K_ESCAPE:
                self.chat_menu_open = False
            elif event.key == pygame.K_UP:
                self.chat_menu_selection = max(0, self.chat_menu_selection - 1)
            elif event.key == pygame.K_DOWN:
                self.chat_menu_selection = min(len(self.available_sessions), self.chat_menu_selection + 1)
            elif event.key == pygame.K_RETURN:
                if hasattr(self, '_sessions_loading') and self._sessions_loading:
                    return
                if self.available_sessions and self.available_sessions[0].get('key') == 'loading':
                    return
                    
                if self.chat_menu_selection == 0:
                    new_name = f"pi-{datetime.now().strftime('%H%M%S')}"
                    self.settings.session_key = new_name
                    self.settings.save()
                    self.conversation.clear()
                    self.messages.clear()
                    self.messages.append(Message(f"New session: {new_name}", 'system'))
                elif self.chat_menu_selection <= len(self.available_sessions):
                    selected = self.available_sessions[self.chat_menu_selection - 1]
                    self.settings.session_key = selected['key']
                    self.settings.save()
                    self.conversation.clear()
                    self.messages.clear()
                    self.messages.append(Message(f"Switched to: {selected['name']}", 'system'))
                self.chat_menu_open = False
            return
            
        if event.key == pygame.K_RETURN:
            self.chat_send_message()
        elif event.key == pygame.K_BACKSPACE:
            if self.chat_cursor > 0:
                self.chat_input = self.chat_input[:self.chat_cursor-1] + self.chat_input[self.chat_cursor:]
                self.chat_cursor -= 1
        elif event.key == pygame.K_LEFT:
            self.chat_cursor = max(0, self.chat_cursor - 1)
        elif event.key == pygame.K_RIGHT:
            self.chat_cursor = min(len(self.chat_input), self.chat_cursor + 1)
        elif event.key == pygame.K_UP:
            # Scroll up through history (show older messages)
            max_scroll = max(0, len(self.messages) - 3)
            self.chat_scroll = min(self.chat_scroll + 1, max_scroll)
        elif event.key == pygame.K_DOWN:
            # Scroll down (show newer messages)
            self.chat_scroll = max(0, self.chat_scroll - 1)
        elif event.key == pygame.K_ESCAPE:
            self.chat_input = ""
            self.chat_cursor = 0
        elif event.key == pygame.K_TAB:
            self.chat_menu_open = True
            self.chat_menu_mode = 'sessions'
            self.chat_menu_selection = 0
            self._fetch_sessions()
        elif event.unicode and ord(event.unicode) >= 32:
            self.chat_input = self.chat_input[:self.chat_cursor] + event.unicode + self.chat_input[self.chat_cursor:]
            self.chat_cursor += 1
            
    def _handle_tasks_key(self, event):
        """Handle keyboard input for tasks panel"""
        
        if self.task_editing:
            # Editing mode
            if event.key == pygame.K_RETURN:
                # Save edit
                if self.tasks and 0 <= self.task_selected < len(self.tasks):
                    self.tasks[self.task_selected]['content'] = self.task_edit_text
                    self.save_local_tasks()
                self.task_editing = False
            elif event.key == pygame.K_ESCAPE:
                # Cancel edit - if empty, delete the task
                if self.tasks and 0 <= self.task_selected < len(self.tasks):
                    if not self.task_edit_text.strip() and not self.tasks[self.task_selected].get('content'):
                        self.delete_task()
                self.task_editing = False
            elif event.key == pygame.K_BACKSPACE:
                if self.task_edit_cursor > 0:
                    self.task_edit_text = self.task_edit_text[:self.task_edit_cursor-1] + self.task_edit_text[self.task_edit_cursor:]
                    self.task_edit_cursor -= 1
            elif event.key == pygame.K_DELETE:
                self.task_edit_text = self.task_edit_text[:self.task_edit_cursor] + self.task_edit_text[self.task_edit_cursor+1:]
            elif event.key == pygame.K_LEFT:
                self.task_edit_cursor = max(0, self.task_edit_cursor - 1)
            elif event.key == pygame.K_RIGHT:
                self.task_edit_cursor = min(len(self.task_edit_text), self.task_edit_cursor + 1)
            elif event.key == pygame.K_HOME:
                self.task_edit_cursor = 0
            elif event.key == pygame.K_END:
                self.task_edit_cursor = len(self.task_edit_text)
            elif event.unicode and ord(event.unicode) >= 32:
                self.task_edit_text = self.task_edit_text[:self.task_edit_cursor] + event.unicode + self.task_edit_text[self.task_edit_cursor:]
                self.task_edit_cursor += 1
        else:
            # Navigation mode
            if event.key == pygame.K_UP:
                if event.mod & pygame.KMOD_SHIFT:
                    self.move_task(-1)
                else:
                    if self.tasks:
                        self.task_selected = max(0, self.task_selected - 1)
            elif event.key == pygame.K_DOWN:
                if event.mod & pygame.KMOD_SHIFT:
                    self.move_task(1)
                else:
                    if self.tasks:
                        self.task_selected = min(len(self.tasks) - 1, self.task_selected + 1)
            elif event.key == pygame.K_RETURN:
                if self.tasks and 0 <= self.task_selected < len(self.tasks):
                    self.task_editing = True
                    self.task_edit_text = self.tasks[self.task_selected].get('content', '')
                    self.task_edit_cursor = len(self.task_edit_text)
            elif event.key == pygame.K_n:
                self.add_task()
            elif event.key == pygame.K_SPACE:
                self.toggle_task_done()
            elif event.key == pygame.K_p:
                self.cycle_task_priority()
            elif event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
                self.delete_task()
                
    def _handle_commands_key(self, event):
        # Handle confirmation dialog
        if self.command_confirm is not None:
            if event.key == pygame.K_RETURN:
                self.confirm_command(True)
            elif event.key == pygame.K_ESCAPE:
                self.confirm_command(False)
            return
            
        # Clear result on any key
        if self.command_result is not None:
            self.command_result = None
            return
            
        # Arrow key navigation (3x3 grid)
        num_commands = len(self.get_commands())
        if event.key == pygame.K_UP:
            if self.command_selection >= 3:
                self.command_selection -= 3
        elif event.key == pygame.K_DOWN:
            if self.command_selection + 3 < num_commands:
                self.command_selection += 3
        elif event.key == pygame.K_LEFT:
            if self.command_selection % 3 > 0:
                self.command_selection -= 1
        elif event.key == pygame.K_RIGHT:
            if self.command_selection % 3 < 2 and self.command_selection < num_commands - 1:
                self.command_selection += 1
        elif event.key == pygame.K_RETURN:
            self.execute_command(self.command_selection)
            
    def run(self):
        running = True
        
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    result = self.handle_key(event)
                    if result == 'quit':
                        running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    # Tab clicks
                    if event.pos[1] < 28:
                        tab_idx = event.pos[0] // (SCREEN_WIDTH // 4)
                        if 0 <= tab_idx < 4:
                            self.switch_mode(tab_idx)
                            
            self.draw()
            # Slow refresh when screen is off to save CPU
            self.clock.tick(5 if self.screen_off else 30)
            
        self.terminal.stop()
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
