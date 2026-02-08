#!/usr/bin/env python3
"""
Pi 400 Dashboard v13 - HyperPixel Edition
For Pimoroni HyperPixel 4.0 (800x480)

Panels:
1. Dashboard - Clock, weather, system stats
2. Tasks - Local task list
3. Chat - Chat with session management (rename/archive/delete)
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
    'small': {'msg': 14, 'input': 15, 'title': 20, 'status': 12, 'time': 12, 'line_height': 18},
    'medium': {'msg': 16, 'input': 17, 'title': 22, 'status': 14, 'time': 13, 'line_height': 22},
    'large': {'msg': 20, 'input': 21, 'title': 26, 'status': 16, 'time': 15, 'line_height': 26},
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
        self.archived_sessions = []  # List of archived session keys
        self.session_renames = {}    # Dict: session_key -> custom_name
        self.load()
    
    def load(self):
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE) as f:
                    data = json.load(f)
                    self.text_size = data.get('text_size', 'medium')
                    self.session_key = data.get('session_key', 'pi-display')
                    self.last_mode = data.get('last_mode', MODE_DASHBOARD)
                    self.archived_sessions = data.get('archived_sessions', [])
                    self.session_renames = data.get('session_renames', {})
        except:
            pass
    
    def save(self):
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SETTINGS_FILE, 'w') as f:
                json.dump({
                    'text_size': self.text_size,
                    'session_key': self.session_key,
                    'last_mode': self.last_mode,
                    'archived_sessions': self.archived_sessions,
                    'session_renames': self.session_renames
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
        self.chat_menu_mode = 'sessions'  # 'sessions', 'archived', 'confirm_archive', 'confirm_delete', 'rename'
        self.chat_menu_selection = 0
        self.chat_menu_scroll = 0  # For scrolling long lists
        self.available_sessions = []
        self.session_rename_text = ""
        self.session_rename_cursor = 0
        self.session_action_target = None  # Session being acted on
        
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
            'big': pygame.font.SysFont('liberationsans', 72, bold=True),
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
            # OpenClaw command - send but don't add to conversation history
            self.messages.append(Message(msg, 'user'))
            self.chat_scroll = 0
            self.chat_waiting = True
            self.chat_status = "command"
            threading.Thread(target=self._chat_send_command, args=(msg,), daemon=True).start()
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
    
    def _chat_send_command(self, cmd):
        """Send OpenClaw slash command (not added to conversation)"""
        try:
            url = f"{GATEWAY_URL}/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {GATEWAY_TOKEN}",
                "x-openclaw-session-key": self.settings.session_key
            }
            
            # Send just the command, not the full conversation
            payload = {
                "model": f"openclaw:{AGENT_ID}",
                "messages": [{"role": "user", "content": cmd}]
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    self.messages.append(Message(content, 'system'))
                else:
                    self.messages.append(Message("✓ Command sent", 'system'))
                self.chat_status = "ready"
            else:
                self.messages.append(Message(f"[HTTP {response.status_code}]", 'system'))
                self.chat_status = "error"
        except Exception as e:
            self.messages.append(Message(f"[{str(e)[:30]}]", 'system'))
            self.chat_status = "error"
            
        self.chat_waiting = False
        self.chat_scroll = 0
        
    def chat_handle_command(self, cmd):
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        if command in ['/help', '/?']:
            self.messages.append(Message(
                "LOCAL: /sessions /new /size /clear\n"
                "OPENCLAW: /compact /think /model /status\n"
                "All other /commands → OpenClaw",
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
            # Read directly from sessions.json file (much faster than CLI)
            sessions_file = Path.home() / '.openclaw' / 'agents' / 'main' / 'sessions' / 'sessions.json'
            
            if sessions_file.exists():
                with open(sessions_file) as f:
                    data = json.load(f)
                
                # Get all keys to check for duplicates
                all_keys = set(data.keys())
                
                sessions = []
                for key, s in data.items():
                    # Skip archived sessions
                    if key in self.settings.archived_sessions:
                        continue
                    
                    # Skip short keys if a full key exists (avoid duplicates)
                    # e.g., skip "pi-0258" if "agent:main:pi-0258" exists
                    if not key.startswith('agent:') and f'agent:main:{key}' in all_keys:
                        continue
                    
                    # Create friendly name
                    name = self._friendly_session_name(key, s)
                    sessions.append({'key': key, 'name': name, 'data': s})
                
                # Sort by updatedAt (most recent first)
                sessions.sort(key=lambda x: x['data'].get('updatedAt', 0), reverse=True)
                self.available_sessions = sessions
            else:
                self.available_sessions = [{'key': '', 'name': 'No sessions file'}]
        except Exception as e:
            self.available_sessions = [{'key': '', 'name': f'Err: {str(e)[:12]}'}]
        self._sessions_loading = False
        
    def _get_archived_sessions(self):
        """Get list of archived sessions with names"""
        archived = []
        for key in self.settings.archived_sessions:
            name = self.settings.session_renames.get(key, key.split(':')[-1][:15])
            archived.append({'key': key, 'name': f"📦 {name}"})
        return archived
        
    def _friendly_session_name(self, key, session_data):
        """Convert session key to friendly display name"""
        # Check for custom rename first
        if key in self.settings.session_renames:
            return self.settings.session_renames[key]
            
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
                'label': 'Restart Dash',
                'desc': 'Restart dashboard',
                'cmd': '__restart_dashboard__',
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
                'label': 'Disk Space',
                'desc': 'Check storage',
                'cmd': "df -h / | awk 'NR==2 {print $3 \"/\" $2 \" (\" $5 \" used)\"}'",
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
            
            # Special handling for restart dashboard
            if cmd['cmd'] == '__restart_dashboard__':
                pygame.quit()
                os.execv(sys.executable, [sys.executable] + sys.argv)
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
        tab_h = 36
        tab_w = SCREEN_WIDTH // 4
        
        for i, name in enumerate(MODE_NAMES):
            x = i * tab_w
            is_active = i == self.mode
            
            color = C['bg_tab_active'] if is_active else C['bg_tab']
            pygame.draw.rect(self.screen, color, (x, 0, tab_w - 1, tab_h))
            
            if is_active:
                pygame.draw.rect(self.screen, C['accent'], (x, tab_h - 4, tab_w - 1, 4))
            
            text_color = C['text_bright'] if is_active else C['text_dim']
            label = self.fonts['msg'].render(f"F{i+1} {name}", True, text_color)
            self.screen.blit(label, (x + (tab_w - label.get_width()) // 2, 9))
            
        pygame.draw.line(self.screen, C['border'], (0, tab_h), (SCREEN_WIDTH, tab_h), 1)
        
    def get_system_stats(self):
        """Get Pi system stats (cached for 2 seconds)"""
        now = time.time()
        if hasattr(self, '_stats_cache') and now - self._stats_cache_time < 2:
            return self._stats_cache
        
        stats = {'cpu': 0, 'mem': 0, 'temp': 0, 'uptime': '?'}
        
        try:
            # CPU usage
            with open('/proc/stat') as f:
                line = f.readline()
                vals = list(map(int, line.split()[1:8]))
                idle = vals[3]
                total = sum(vals)
                if hasattr(self, '_last_cpu'):
                    diff_idle = idle - self._last_cpu[0]
                    diff_total = total - self._last_cpu[1]
                    stats['cpu'] = int(100 * (1 - diff_idle / max(diff_total, 1)))
                self._last_cpu = (idle, total)
        except:
            pass
            
        try:
            # Memory usage
            with open('/proc/meminfo') as f:
                lines = f.readlines()
                total = int(lines[0].split()[1])
                avail = int(lines[2].split()[1])
                stats['mem'] = int(100 * (1 - avail / total))
        except:
            pass
            
        try:
            # Pi temperature
            with open('/sys/class/thermal/thermal_zone0/temp') as f:
                stats['temp'] = int(f.read()) // 1000
        except:
            pass
            
        try:
            # Uptime
            with open('/proc/uptime') as f:
                secs = int(float(f.read().split()[0]))
                if secs < 3600:
                    stats['uptime'] = f"{secs // 60}m"
                elif secs < 86400:
                    stats['uptime'] = f"{secs // 3600}h {(secs % 3600) // 60}m"
                else:
                    stats['uptime'] = f"{secs // 86400}d {(secs % 86400) // 3600}h"
        except:
            pass
            
        self._stats_cache = stats
        self._stats_cache_time = now
        return stats
        
    def draw_progress_bar(self, x, y, w, h, pct, color, bg_color=None):
        """Draw a progress bar"""
        bg = bg_color or C['bg']
        pygame.draw.rect(self.screen, bg, (x, y, w, h), border_radius=3)
        fill_w = int(w * min(pct, 100) / 100)
        if fill_w > 0:
            pygame.draw.rect(self.screen, color, (x, y, fill_w, h), border_radius=3)
    
    def draw_dashboard(self):
        """Draw dashboard panel - HyperPixel 800x480 layout"""
        stats = self.get_system_stats()
        now = datetime.now()
        
        # === LEFT SIDE: Big clock and date ===
        left_x = 40
        
        # Time - huge
        time_str = now.strftime("%I:%M").lstrip('0')
        time_surf = self.fonts['big'].render(time_str, True, C['text_bright'])
        self.screen.blit(time_surf, (left_x, 50))
        
        # AM/PM next to time
        ampm = now.strftime("%p")
        ampm_surf = self.fonts['title'].render(ampm, True, C['text_dim'])
        self.screen.blit(ampm_surf, (left_x + time_surf.get_width() + 8, 80))
        
        # Date below time
        date_str = now.strftime("%A, %B %d")
        date_surf = self.fonts['title'].render(date_str, True, C['text_dim'])
        self.screen.blit(date_surf, (left_x, 120))
        
        # Weather
        if self.weather:
            weather_surf = self.fonts['msg'].render(self.weather[:30], True, C['text_muted'])
            self.screen.blit(weather_surf, (left_x, 150))
        else:
            self.load_weather()
        
        # === RIGHT SIDE: System stats panel ===
        panel_x = 420
        panel_y = 45
        panel_w = 360
        panel_h = 130
        
        # Stats background
        pygame.draw.rect(self.screen, C['bg_item'], (panel_x, panel_y, panel_w, panel_h), border_radius=12)
        
        # CPU
        cpu_color = C['success'] if stats['cpu'] < 50 else C['warning'] if stats['cpu'] < 80 else C['error']
        cpu_label = self.fonts['status'].render("CPU", True, C['text_muted'])
        self.screen.blit(cpu_label, (panel_x + 20, panel_y + 15))
        cpu_val = self.fonts['title'].render(f"{stats['cpu']}%", True, cpu_color)
        self.screen.blit(cpu_val, (panel_x + 20, panel_y + 35))
        self.draw_progress_bar(panel_x + 20, panel_y + 65, 140, 10, stats['cpu'], cpu_color, C['bg'])
        
        # Memory
        mem_color = C['success'] if stats['mem'] < 60 else C['warning'] if stats['mem'] < 85 else C['error']
        mem_label = self.fonts['status'].render("MEMORY", True, C['text_muted'])
        self.screen.blit(mem_label, (panel_x + 190, panel_y + 15))
        mem_val = self.fonts['title'].render(f"{stats['mem']}%", True, mem_color)
        self.screen.blit(mem_val, (panel_x + 190, panel_y + 35))
        self.draw_progress_bar(panel_x + 190, panel_y + 65, 140, 10, stats['mem'], mem_color, C['bg'])
        
        # Temperature and Uptime row
        temp = stats['temp']
        temp_color = C['success'] if temp < 55 else C['warning'] if temp < 70 else C['error']
        temp_label = self.fonts['status'].render("TEMP", True, C['text_muted'])
        self.screen.blit(temp_label, (panel_x + 20, panel_y + 85))
        temp_val = self.fonts['title'].render(f"{temp}°C", True, temp_color)
        self.screen.blit(temp_val, (panel_x + 20, panel_y + 105))
        
        up_label = self.fonts['status'].render("UPTIME", True, C['text_muted'])
        self.screen.blit(up_label, (panel_x + 190, panel_y + 85))
        up_val = self.fonts['title'].render(stats['uptime'], True, C['accent'])
        self.screen.blit(up_val, (panel_x + 190, panel_y + 105))
        
        # === BOTTOM: Info cards row ===
        card_y = 200
        card_h = 70
        card_w = 240
        gap = 20
        
        # Session card
        pygame.draw.rect(self.screen, C['bg_item'], (20, card_y, card_w, card_h), border_radius=12)
        pygame.draw.rect(self.screen, C['accent'], (20, card_y, 5, card_h), border_radius=2)
        label = self.fonts['status'].render("SESSION", True, C['text_muted'])
        self.screen.blit(label, (36, card_y + 12))
        display_name = self.settings.session_renames.get(self.settings.session_key, self.settings.session_key)
        if len(display_name) > 20:
            display_name = display_name[:19] + "…"
        val = self.fonts['title'].render(display_name, True, C['text_bright'])
        self.screen.blit(val, (36, card_y + 36))
        
        # Gateway card
        pygame.draw.rect(self.screen, C['bg_item'], (20 + card_w + gap, card_y, card_w, card_h), border_radius=12)
        pygame.draw.rect(self.screen, C['success'], (20 + card_w + gap, card_y, 5, card_h), border_radius=2)
        label = self.fonts['status'].render("GATEWAY", True, C['text_muted'])
        self.screen.blit(label, (36 + card_w + gap, card_y + 12))
        val = self.fonts['title'].render("● Online", True, C['success'])
        self.screen.blit(val, (36 + card_w + gap, card_y + 36))
        
        # Tasks card
        task_count = len([t for t in self.tasks if not t.get('done')]) if self.tasks else 0
        task_color = C['warning'] if task_count > 0 else C['success']
        pygame.draw.rect(self.screen, C['bg_item'], (20 + (card_w + gap) * 2, card_y, card_w, card_h), border_radius=12)
        pygame.draw.rect(self.screen, task_color, (20 + (card_w + gap) * 2, card_y, 5, card_h), border_radius=2)
        label = self.fonts['status'].render("TASKS", True, C['text_muted'])
        self.screen.blit(label, (36 + (card_w + gap) * 2, card_y + 12))
        val = self.fonts['title'].render(f"{task_count} pending", True, task_color)
        self.screen.blit(val, (36 + (card_w + gap) * 2, card_y + 36))
        
        # === CHAT PREVIEW - larger with more context ===
        preview_y = card_y + card_h + 20
        preview_h = 80
        
        # Preview background
        pygame.draw.rect(self.screen, C['bg_item'], (20, preview_y, SCREEN_WIDTH - 40, preview_h), border_radius=12)
        
        if self.messages:
            # Show last 2 messages
            recent = list(self.messages)[-2:]
            msg_y = preview_y + 12
            for msg in recent:
                if msg.role == 'system':
                    continue
                # Role indicator
                if msg.role == 'user':
                    indicator_color = C['accent']
                    prefix = "You: "
                else:
                    indicator_color = C['success']
                    prefix = "Bot: "
                
                pygame.draw.rect(self.screen, indicator_color, (30, msg_y + 2, 4, 18), border_radius=2)
                
                preview_text = prefix + msg.text[:70] + ("…" if len(msg.text) > 70 else "")
                preview_surf = self.fonts['msg'].render(preview_text, True, C['text'])
                self.screen.blit(preview_surf, (42, msg_y))
                msg_y += 28
        else:
            empty_surf = self.fonts['msg'].render("No messages yet. Press F3 to chat.", True, C['text_dim'])
            self.screen.blit(empty_surf, (30, preview_y + 30))
        
        # === FOOTER ===
        hint = "F2 Tasks  •  F3 Chat  •  F4 Commands"
        hint_surf = self.fonts['status'].render(hint, True, C['text_muted'])
        self.screen.blit(hint_surf, ((SCREEN_WIDTH - hint_surf.get_width()) // 2, SCREEN_HEIGHT - 25))
        
    def draw_tasks(self):
        """Draw local task cards"""
        y_start = 45
        card_height = 44
        card_margin = 6
        max_visible = 9
        
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
        card_h = 80
        margin_x = 15
        margin_y = 10
        spacing_x = 12
        spacing_y = 12
        
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
        dialog_w, dialog_h = 320, 140
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
        y_start = 38
        
        # Session indicator at top
        display_name = self.settings.session_renames.get(self.settings.session_key, self.settings.session_key)
        session_text = f"Session: {display_name}"
        session_surf = self.fonts['status'].render(session_text[:50], True, C['text_dim'])
        self.screen.blit(session_surf, (15, y_start + 4))
        y_start += 24
        
        # Messages
        msg_bottom = SCREEN_HEIGHT - 60
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
        input_y = SCREEN_HEIGHT - 55
        pygame.draw.line(self.screen, C['border'], (0, input_y), (SCREEN_WIDTH, input_y), 1)
        
        box = (12, input_y + 8, SCREEN_WIDTH - 24, 42)
        pygame.draw.rect(self.screen, C['bg_input'], box, border_radius=10)
        
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
            prefix = "Sys: "
            text_color = C['warning']
        else:
            prefix = "Bot: "
            text_color = C['success']
        
        # Word wrap with prefix on first line
        full_text = prefix + msg.text
        lines = self._word_wrap(full_text, 'msg', max_w)
        
        # Calculate how many lines we can fit
        available_height = y - min_y
        max_lines = max(1, int(available_height / self.line_height))
        
        # Truncate if too many lines
        truncated = False
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            truncated = True
            # Add ellipsis to last line
            if lines:
                lines[-1] = lines[-1][:30] + "..."
        
        msg_h = len(lines) * self.line_height + 2
        
        # If we can't fit even one line, skip this message
        if msg_h > available_height and available_height < self.line_height:
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
        
        menu_w, menu_h = 300, 240
        menu_x = (SCREEN_WIDTH - menu_w) // 2
        menu_y = (SCREEN_HEIGHT - menu_h) // 2
        
        pygame.draw.rect(self.screen, C['bg_overlay'], (menu_x, menu_y, menu_w, menu_h), border_radius=10)
        pygame.draw.rect(self.screen, C['border'], (menu_x, menu_y, menu_w, menu_h), width=1, border_radius=10)
        
        # Handle different menu modes
        if self.chat_menu_mode == 'confirm_archive':
            self._draw_confirm_session_dialog(menu_x, menu_y, menu_w, menu_h, 'archive')
            return
        elif self.chat_menu_mode == 'confirm_delete':
            self._draw_confirm_session_dialog(menu_x, menu_y, menu_w, menu_h, 'delete')
            return
        elif self.chat_menu_mode == 'rename':
            self._draw_rename_dialog(menu_x, menu_y, menu_w, menu_h)
            return
        elif self.chat_menu_mode == 'archived':
            self._draw_archived_menu(menu_x, menu_y, menu_w, menu_h)
            return
        
        # Main sessions menu
        title = "Sessions"
        title_surf = self.fonts['menu_title'].render(title, True, C['text_bright'])
        self.screen.blit(title_surf, (menu_x + 16, menu_y + 12))
        
        # Loading indicator
        if hasattr(self, '_sessions_loading') and self._sessions_loading:
            loading_surf = self.fonts['status'].render("loading...", True, C['accent'])
            self.screen.blit(loading_surf, (menu_x + menu_w - 80, menu_y + 14))
        
        # Archived count
        archived_count = len(self.settings.archived_sessions)
        if archived_count > 0:
            arch_text = f"📦 {archived_count}"
            arch_surf = self.fonts['status'].render(arch_text, True, C['text_dim'])
            self.screen.blit(arch_surf, (menu_x + menu_w - 45, menu_y + 14))
        
        pygame.draw.line(self.screen, C['border'], (menu_x + 10, menu_y + 38), (menu_x + menu_w - 10, menu_y + 38))
        
        # Build items list: New Session + sessions + View Archived
        items = [{'type': 'new', 'name': '➕ New Session'}]
        for s in self.available_sessions:
            items.append({'type': 'session', 'key': s['key'], 'name': s['name']})
        if archived_count > 0:
            items.append({'type': 'archived', 'name': f'📦 View Archived ({archived_count})'})
        
        # Scrolling
        max_visible = 6
        total_items = len(items)
        
        # Ensure selection stays in bounds
        self.chat_menu_selection = max(0, min(self.chat_menu_selection, total_items - 1))
        
        # Adjust scroll to keep selection visible
        if self.chat_menu_selection < self.chat_menu_scroll:
            self.chat_menu_scroll = self.chat_menu_selection
        elif self.chat_menu_selection >= self.chat_menu_scroll + max_visible:
            self.chat_menu_scroll = self.chat_menu_selection - max_visible + 1
        
        # Draw visible items
        visible_items = items[self.chat_menu_scroll:self.chat_menu_scroll + max_visible]
        item_y = menu_y + 46
        
        for i, item in enumerate(visible_items):
            actual_idx = self.chat_menu_scroll + i
            is_sel = actual_idx == self.chat_menu_selection
            
            is_current = False
            if item['type'] == 'session':
                # Check exact match or if session key ends with our key (handles agent:main:X vs X)
                is_current = (item['key'] == self.settings.session_key or 
                             item['key'].endswith(':' + self.settings.session_key))
            
            if is_sel:
                pygame.draw.rect(self.screen, C['bg_item_hover'], (menu_x + 8, item_y, menu_w - 16, 26), border_radius=4)
            
            prefix = "✓ " if is_current else "  "
            color = C['accent'] if is_current else (C['text_bright'] if is_sel else C['text'])
            
            display_name = item['name'][:24]
            surf = self.fonts['menu'].render(prefix + display_name, True, color)
            self.screen.blit(surf, (menu_x + 12, item_y + 5))
            item_y += 28
        
        # Scroll indicators
        if self.chat_menu_scroll > 0:
            up_surf = self.fonts['status'].render("▲ more", True, C['text_dim'])
            self.screen.blit(up_surf, (menu_x + menu_w - 55, menu_y + 42))
        if self.chat_menu_scroll + max_visible < total_items:
            down_surf = self.fonts['status'].render("▼ more", True, C['text_dim'])
            self.screen.blit(down_surf, (menu_x + menu_w - 55, menu_y + menu_h - 38))
        
        # Hints at bottom
        hint = "Enter:Select R:Rename A:Archive D:Del"
        hint_surf = self.fonts['status'].render(hint, True, C['text_muted'])
        self.screen.blit(hint_surf, (menu_x + (menu_w - hint_surf.get_width()) // 2, menu_y + menu_h - 20))
        
    def _draw_archived_menu(self, menu_x, menu_y, menu_w, menu_h):
        """Draw the archived sessions popup"""
        title = "📦 Archived Sessions"
        title_surf = self.fonts['menu_title'].render(title, True, C['text_bright'])
        self.screen.blit(title_surf, (menu_x + 16, menu_y + 12))
        
        pygame.draw.line(self.screen, C['border'], (menu_x + 10, menu_y + 38), (menu_x + menu_w - 10, menu_y + 38))
        
        archived = self._get_archived_sessions()
        if not archived:
            empty_surf = self.fonts['msg'].render("No archived sessions", True, C['text_dim'])
            self.screen.blit(empty_surf, (menu_x + 20, menu_y + 60))
        else:
            max_visible = 6
            total = len(archived)
            
            self.chat_menu_selection = max(0, min(self.chat_menu_selection, total - 1))
            
            if self.chat_menu_selection < self.chat_menu_scroll:
                self.chat_menu_scroll = self.chat_menu_selection
            elif self.chat_menu_selection >= self.chat_menu_scroll + max_visible:
                self.chat_menu_scroll = self.chat_menu_selection - max_visible + 1
            
            visible = archived[self.chat_menu_scroll:self.chat_menu_scroll + max_visible]
            item_y = menu_y + 46
            
            for i, item in enumerate(visible):
                actual_idx = self.chat_menu_scroll + i
                is_sel = actual_idx == self.chat_menu_selection
                
                if is_sel:
                    pygame.draw.rect(self.screen, C['bg_item_hover'], (menu_x + 8, item_y, menu_w - 16, 26), border_radius=4)
                
                color = C['text_bright'] if is_sel else C['text_dim']
                surf = self.fonts['menu'].render(item['name'][:26], True, color)
                self.screen.blit(surf, (menu_x + 12, item_y + 5))
                item_y += 28
        
        hint = "A:Unarchive D:Delete Esc:Back"
        hint_surf = self.fonts['status'].render(hint, True, C['text_muted'])
        self.screen.blit(hint_surf, (menu_x + (menu_w - hint_surf.get_width()) // 2, menu_y + menu_h - 20))
        
    def _draw_confirm_session_dialog(self, menu_x, menu_y, menu_w, menu_h, action):
        """Draw confirmation dialog for archive/delete"""
        if action == 'archive':
            title = "Archive Session?"
            color = C['warning']
        else:
            title = "Delete Session?"
            color = C['error']
        
        title_surf = self.fonts['menu_title'].render(title, True, color)
        self.screen.blit(title_surf, (menu_x + 16, menu_y + 12))
        
        pygame.draw.line(self.screen, C['border'], (menu_x + 10, menu_y + 38), (menu_x + menu_w - 10, menu_y + 38))
        
        # Show session name
        if self.session_action_target:
            name = self.session_action_target.get('name', 'Unknown')[:30]
            name_surf = self.fonts['msg'].render(name, True, C['text'])
            self.screen.blit(name_surf, (menu_x + 20, menu_y + 60))
            
            if action == 'archive':
                desc = "Session will be hidden from list"
            else:
                desc = "This cannot be undone!"
            desc_surf = self.fonts['status'].render(desc, True, C['text_dim'])
            self.screen.blit(desc_surf, (menu_x + 20, menu_y + 90))
        
        # Y/N buttons
        hint = "Y: Confirm | N/Esc: Cancel"
        hint_surf = self.fonts['status'].render(hint, True, C['text_muted'])
        self.screen.blit(hint_surf, (menu_x + (menu_w - hint_surf.get_width()) // 2, menu_y + menu_h - 20))
        
    def _draw_rename_dialog(self, menu_x, menu_y, menu_w, menu_h):
        """Draw rename input dialog"""
        title = "Rename Session"
        title_surf = self.fonts['menu_title'].render(title, True, C['accent'])
        self.screen.blit(title_surf, (menu_x + 16, menu_y + 12))
        
        pygame.draw.line(self.screen, C['border'], (menu_x + 10, menu_y + 38), (menu_x + menu_w - 10, menu_y + 38))
        
        # Input box
        input_rect = (menu_x + 15, menu_y + 60, menu_w - 30, 36)
        pygame.draw.rect(self.screen, C['bg_input'], input_rect, border_radius=6)
        pygame.draw.rect(self.screen, C['border'], input_rect, width=1, border_radius=6)
        
        # Text
        display_text = self.session_rename_text or "Enter new name..."
        text_color = C['text'] if self.session_rename_text else C['text_muted']
        text_surf = self.fonts['input'].render(display_text[:25], True, text_color)
        self.screen.blit(text_surf, (menu_x + 22, menu_y + 70))
        
        # Cursor
        if self.session_rename_text and int(time.time() * 2) % 2:
            cursor_x = menu_x + 22 + self.fonts['input'].size(self.session_rename_text[:self.session_rename_cursor])[0]
            pygame.draw.rect(self.screen, C['cursor'], (cursor_x, menu_y + 66, 2, 24))
        
        hint = "Enter: Save | Esc: Cancel"
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
            # Handle different menu modes
            if self.chat_menu_mode == 'rename':
                self._handle_rename_input(event)
                return
            elif self.chat_menu_mode in ('confirm_archive', 'confirm_delete'):
                self._handle_confirm_input(event)
                return
            elif self.chat_menu_mode == 'archived':
                self._handle_archived_menu(event)
                return
            
            # Main sessions menu
            if event.key == pygame.K_ESCAPE:
                self.chat_menu_open = False
                self.chat_menu_scroll = 0
            elif event.key == pygame.K_UP:
                self.chat_menu_selection = max(0, self.chat_menu_selection - 1)
            elif event.key == pygame.K_DOWN:
                # Calculate max based on items list
                items_count = 1 + len(self.available_sessions)  # New Session + sessions
                if self.settings.archived_sessions:
                    items_count += 1  # View Archived
                self.chat_menu_selection = min(self.chat_menu_selection + 1, items_count - 1)
            elif event.key == pygame.K_RETURN:
                if hasattr(self, '_sessions_loading') and self._sessions_loading:
                    return
                if self.available_sessions and self.available_sessions[0].get('key') == 'loading':
                    return
                
                # Calculate what item is selected
                items_count = 1 + len(self.available_sessions)
                has_archived = len(self.settings.archived_sessions) > 0
                
                if self.chat_menu_selection == 0:
                    # New Session
                    new_name = f"pi-{datetime.now().strftime('%H%M%S')}"
                    self.settings.session_key = new_name
                    self.settings.save()
                    self.conversation.clear()
                    self.messages.clear()
                    self.messages.append(Message(f"New: {new_name}", 'system'))
                    self.chat_menu_open = False
                elif self.chat_menu_selection <= len(self.available_sessions):
                    # Switch to session
                    selected = self.available_sessions[self.chat_menu_selection - 1]
                    self.settings.session_key = selected['key']
                    self.settings.save()
                    self.conversation.clear()
                    self.messages.clear()
                    self.messages.append(Message(f"Switched: {selected['name'][:20]}", 'system'))
                    self.chat_menu_open = False
                elif has_archived and self.chat_menu_selection == items_count:
                    # View Archived
                    self.chat_menu_mode = 'archived'
                    self.chat_menu_selection = 0
                    self.chat_menu_scroll = 0
            elif event.key == pygame.K_r:
                # Rename (only for sessions, not New Session or View Archived)
                if 0 < self.chat_menu_selection <= len(self.available_sessions):
                    selected = self.available_sessions[self.chat_menu_selection - 1]
                    self.session_action_target = selected
                    self.session_rename_text = selected.get('name', '')
                    self.session_rename_cursor = len(self.session_rename_text)
                    self.chat_menu_mode = 'rename'
            elif event.key == pygame.K_a:
                # Archive
                if 0 < self.chat_menu_selection <= len(self.available_sessions):
                    selected = self.available_sessions[self.chat_menu_selection - 1]
                    self.session_action_target = selected
                    self.chat_menu_mode = 'confirm_archive'
            elif event.key == pygame.K_d or event.key == pygame.K_DELETE:
                # Delete
                if 0 < self.chat_menu_selection <= len(self.available_sessions):
                    selected = self.available_sessions[self.chat_menu_selection - 1]
                    self.session_action_target = selected
                    self.chat_menu_mode = 'confirm_delete'
            return
        
        # Normal chat input (when menu is not open)
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
            # Scroll up through history
            max_scroll = max(0, len(self.messages) - 3)
            self.chat_scroll = min(self.chat_scroll + 1, max_scroll)
        elif event.key == pygame.K_DOWN:
            # Scroll down
            self.chat_scroll = max(0, self.chat_scroll - 1)
        elif event.key == pygame.K_ESCAPE:
            self.chat_input = ""
            self.chat_cursor = 0
        elif event.key == pygame.K_TAB:
            self.chat_menu_open = True
            self.chat_menu_mode = 'sessions'
            self.chat_menu_selection = 0
            self.chat_menu_scroll = 0
            self._fetch_sessions()
        elif event.unicode and ord(event.unicode) >= 32:
            self.chat_input = self.chat_input[:self.chat_cursor] + event.unicode + self.chat_input[self.chat_cursor:]
            self.chat_cursor += 1
            
    def _handle_rename_input(self, event):
        """Handle keyboard input for rename dialog"""
        if event.key == pygame.K_ESCAPE:
            self.chat_menu_mode = 'sessions'
        elif event.key == pygame.K_RETURN:
            # Save rename
            if self.session_action_target and self.session_rename_text.strip():
                key = self.session_action_target.get('key', '')
                self.settings.session_renames[key] = self.session_rename_text.strip()
                self.settings.save()
                self._fetch_sessions()  # Refresh list
            self.chat_menu_mode = 'sessions'
        elif event.key == pygame.K_BACKSPACE:
            if self.session_rename_cursor > 0:
                self.session_rename_text = self.session_rename_text[:self.session_rename_cursor-1] + self.session_rename_text[self.session_rename_cursor:]
                self.session_rename_cursor -= 1
        elif event.key == pygame.K_LEFT:
            self.session_rename_cursor = max(0, self.session_rename_cursor - 1)
        elif event.key == pygame.K_RIGHT:
            self.session_rename_cursor = min(len(self.session_rename_text), self.session_rename_cursor + 1)
        elif event.unicode and ord(event.unicode) >= 32:
            self.session_rename_text = self.session_rename_text[:self.session_rename_cursor] + event.unicode + self.session_rename_text[self.session_rename_cursor:]
            self.session_rename_cursor += 1
            
    def _handle_confirm_input(self, event):
        """Handle Y/N confirmation for archive/delete"""
        if event.key == pygame.K_ESCAPE or event.key == pygame.K_n:
            self.chat_menu_mode = 'sessions'
            self.session_action_target = None
        elif event.key == pygame.K_y:
            if self.session_action_target:
                key = self.session_action_target.get('key', '')
                if self.chat_menu_mode == 'confirm_archive':
                    # Archive the session
                    if key and key not in self.settings.archived_sessions:
                        self.settings.archived_sessions.append(key)
                        self.settings.save()
                        self.messages.append(Message(f"Archived session", 'system'))
                elif self.chat_menu_mode == 'confirm_delete':
                    # Delete session from settings
                    if key in self.settings.session_renames:
                        del self.settings.session_renames[key]
                    if key in self.settings.archived_sessions:
                        self.settings.archived_sessions.remove(key)
                    self.settings.save()
                    
                    # Also delete from sessions.json
                    try:
                        sessions_file = Path.home() / '.openclaw' / 'agents' / 'main' / 'sessions' / 'sessions.json'
                        if sessions_file.exists():
                            with open(sessions_file) as f:
                                sessions_data = json.load(f)
                            if key in sessions_data:
                                del sessions_data[key]
                                with open(sessions_file, 'w') as f:
                                    json.dump(sessions_data, f, indent=2)
                    except Exception as e:
                        pass  # Silently fail if can't delete from file
                    
                    self.messages.append(Message(f"Deleted session", 'system'))
                self._fetch_sessions()  # Refresh
            self.chat_menu_mode = 'sessions'
            self.session_action_target = None
            self.chat_menu_selection = 0
            
    def _handle_archived_menu(self, event):
        """Handle keyboard input for archived sessions menu"""
        archived = self._get_archived_sessions()
        
        if event.key == pygame.K_ESCAPE:
            self.chat_menu_mode = 'sessions'
            self.chat_menu_selection = 0
            self.chat_menu_scroll = 0
        elif event.key == pygame.K_UP:
            self.chat_menu_selection = max(0, self.chat_menu_selection - 1)
        elif event.key == pygame.K_DOWN:
            if archived:
                self.chat_menu_selection = min(self.chat_menu_selection + 1, len(archived) - 1)
        elif event.key == pygame.K_a:
            # Unarchive
            if archived and 0 <= self.chat_menu_selection < len(archived):
                key = archived[self.chat_menu_selection]['key']
                if key in self.settings.archived_sessions:
                    self.settings.archived_sessions.remove(key)
                    self.settings.save()
                    self.messages.append(Message(f"Unarchived session", 'system'))
                    self._fetch_sessions()
                    if not self.settings.archived_sessions:
                        self.chat_menu_mode = 'sessions'
                        self.chat_menu_selection = 0
                    else:
                        self.chat_menu_selection = min(self.chat_menu_selection, len(self.settings.archived_sessions) - 1)
        elif event.key == pygame.K_d or event.key == pygame.K_DELETE:
            # Delete archived session
            if archived and 0 <= self.chat_menu_selection < len(archived):
                self.session_action_target = archived[self.chat_menu_selection]
                self.chat_menu_mode = 'confirm_delete'
            
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
