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
    'small': {'msg': 16, 'input': 17, 'title': 22, 'status': 14, 'time': 14, 'line_height': 22},
    'medium': {'msg': 19, 'input': 20, 'title': 24, 'status': 15, 'time': 15, 'line_height': 26},
    'large': {'msg': 24, 'input': 25, 'title': 30, 'status': 18, 'time': 17, 'line_height': 32},
}

# Panel modes
MODE_DASHBOARD = 0
MODE_TASKS = 1
MODE_CHAT = 2
MODE_COMMANDS = 3
MODE_KANBAN = 4
MODE_NAMES = ['Home', 'Tasks', 'Chat', 'Cmds', 'Kanban']


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
        """Load tasks from Todoist"""
        self._load_todoist_tasks()
            
    def save_local_tasks(self):
        """No-op - Todoist syncs automatically"""
        pass
    
    def _load_todoist_tasks(self):
        """Fetch tasks from Todoist API with subtask support"""
        try:
            result = subprocess.run(
                ['todoist', 'tasks', '--all', '--json'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                raw_tasks = json.loads(result.stdout)
                
                # Build task dict and identify parent/child relationships
                task_dict = {}
                children_map = {}  # parentId -> list of children
                
                for t in raw_tasks:
                    due_str = ''
                    if t.get('due'):
                        due_str = t['due'].get('string', '') or t['due'].get('date', '')
                    
                    task = {
                        'id': t['id'],
                        'content': t.get('content', ''),
                        'priority': t.get('priority', 1),
                        'done': t.get('checked', False),
                        'due': due_str,
                        'project_id': t.get('projectId', ''),
                        'parent_id': t.get('parentId'),
                        'child_order': t.get('childOrder', 0),
                        'subtasks': [],
                        'expanded': False,
                        'is_subtask': t.get('parentId') is not None,
                    }
                    task_dict[t['id']] = task
                    
                    # Track children
                    parent_id = t.get('parentId')
                    if parent_id:
                        if parent_id not in children_map:
                            children_map[parent_id] = []
                        children_map[parent_id].append(task)
                
                # Attach subtasks to parents
                for parent_id, children in children_map.items():
                    if parent_id in task_dict:
                        task_dict[parent_id]['subtasks'] = sorted(children, key=lambda x: x['child_order'])
                
                # Build flat list - only top-level tasks (no parentId)
                self.tasks = [t for t in task_dict.values() if not t['is_subtask']]
                self.tasks = sorted(self.tasks, key=lambda x: x['child_order'])[:50]
                
                # Initialize expanded state tracking
                if not hasattr(self, 'task_expanded'):
                    self.task_expanded = set()
                
                self.todoist_sync_status = 'live'
                self.todoist_last_sync = time.time()
            else:
                self.todoist_sync_status = 'error'
        except Exception as e:
            self.todoist_sync_status = 'error'
    
    def _todoist_complete_task(self, task_id):
        """Mark task complete in Todoist"""
        try:
            self.todoist_sync_status = 'syncing'
            result = subprocess.run(
                ['todoist', 'done', str(task_id)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                self.todoist_sync_status = 'live'
                return True
            else:
                self.todoist_sync_status = 'error'
                return False
        except:
            self.todoist_sync_status = 'error'
            return False
    
    def _todoist_add_task(self, content, due=None):
        """Add task to Todoist"""
        try:
            self.todoist_sync_status = 'syncing'
            cmd = ['todoist', 'add', content]
            if due:
                cmd.extend(['--due', due])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.todoist_sync_status = 'live'
                self._load_todoist_tasks()  # Refresh
                return True
            else:
                self.todoist_sync_status = 'error'
                return False
        except:
            self.todoist_sync_status = 'error'
            return False
            
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
        """Complete task in Todoist"""
        if self.tasks and 0 <= self.task_selected < len(self.tasks):
            task = self.tasks[self.task_selected]
            task_id = task.get('id')
            if task_id and not task.get('done'):
                # Complete in Todoist
                if self._todoist_complete_task(task_id):
                    # Remove from local list
                    self.tasks.pop(self.task_selected)
                    if self.task_selected >= len(self.tasks) and self.tasks:
                        self.task_selected = len(self.tasks) - 1
            
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
                'label': 'Restart Dashboard',
                'desc': 'Reload this interface',
                'cmd': '__restart_dashboard__',
                'icon': '1',
                'color': C['accent'],
                'category': 'safe'
            },
            {
                'label': 'Node Status',
                'desc': 'Check connection to gateway',
                'cmd': 'openclaw nodes status',
                'icon': '2',
                'color': C['accent'],
                'category': 'safe'
            },
            {
                'label': 'Disk Space',
                'desc': 'View storage usage',
                'cmd': "df -h / | awk 'NR==2 {print $3 \"/\" $2 \" (\" $5 \" used)\"}'",
                'icon': '3',
                'color': C['accent'],
                'category': 'safe'
            },
            {
                'label': 'Screen Off',
                'desc': 'Turn off display (any key to wake)',
                'cmd': '__screen_off__',
                'icon': '4',
                'color': (100, 100, 120),
                'category': 'safe'
            },
            {
                'label': 'Restart Gateway',
                'desc': 'Restart OpenClaw service',
                'cmd': 'systemctl --user restart openclaw-gateway',
                'icon': '5',
                'color': C['warning'],
                'category': 'caution'
            },
            {
                'label': 'Update System',
                'desc': 'Pull latest code & install',
                'cmd': 'cd ~/.openclaw && git pull && npm install',
                'icon': '6',
                'color': C['warning'],
                'category': 'caution'
            },
            {
                'label': 'Reboot Pi',
                'desc': 'Restart the entire system',
                'cmd': 'sudo reboot',
                'icon': '7',
                'color': C['error'],
                'category': 'danger'
            },
            {
                'label': 'Shutdown',
                'desc': 'Power off completely',
                'cmd': 'sudo shutdown -h now',
                'icon': '8',
                'color': C['error'],
                'category': 'danger'
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
            
            # Safe commands run immediately, others need confirmation
            if cmd.get('category', 'safe') == 'safe':
                self.command_running = cmd['label']
                self.command_result = None
                threading.Thread(target=self._run_command_async, args=(cmd,), daemon=True).start()
            else:
                # Caution/Danger commands need confirmation
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
        tab_w = SCREEN_WIDTH // 5
        
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
        
        # Version indicator
        ver_surf = self.fonts['status'].render("v15", True, C['text_muted'])
        self.screen.blit(ver_surf, (SCREEN_WIDTH - ver_surf.get_width() - 8, 12))
            
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
        """WOW Edition - Premium animated task interface"""
        import math
        
        # Initialize state
        if not hasattr(self, 'todoist_last_sync'):
            self.todoist_last_sync = 0
            self.todoist_sync_status = 'live'
        if not hasattr(self, 'task_filter'):
            self.task_filter = 'all'
        if not hasattr(self, 'wow_anim_time'):
            self.wow_anim_time = 0
        if not hasattr(self, 'task_expanded'):
            self.task_expanded = set()
        
        self.wow_anim_time += 0.03  # Animation timer
        
        # Auto-refresh every 30 seconds
        if time.time() - self.todoist_last_sync > 30:
            self._load_todoist_tasks()
        
        # Filter tasks
        all_tasks = self.tasks
        projects = {
            'all': {'name': 'All Tasks', 'color': (100, 140, 220), 'tasks': all_tasks},
            'inbox': {'name': 'Inbox', 'color': (130, 180, 255), 'tasks': [t for t in all_tasks if 'inbox' in t.get('project', '').lower() or not t.get('project')]},
            'salon': {'name': 'Nail Salon', 'color': (255, 140, 180), 'tasks': [t for t in all_tasks if 'salon' in t.get('project', '').lower() or 'nail' in t.get('project', '').lower()]},
        }
        
        if self.task_filter == 'today':
            filtered = [t for t in all_tasks if 'today' in t.get('due', '').lower()]
        elif self.task_filter == 'overdue':
            filtered = [t for t in all_tasks if any(x in t.get('due', '').lower() for x in ['overdue', 'yesterday'])]
        elif self.task_filter in projects:
            filtered = projects[self.task_filter]['tasks']
        else:
            filtered = all_tasks
        
        # Stats
        total = len(all_tasks)
        today_count = len([t for t in all_tasks if 'today' in t.get('due', '').lower()])
        overdue_count = len([t for t in all_tasks if any(x in t.get('due', '').lower() for x in ['overdue', 'yesterday'])])
        
        # ═══════════════════════════════════════════════════════════════
        # BACKGROUND - Animated gradient
        # ═══════════════════════════════════════════════════════════════
        # Dark base with subtle animated gradient
        for y in range(36, SCREEN_HEIGHT):
            progress = (y - 36) / (SCREEN_HEIGHT - 36)
            wave = math.sin(self.wow_anim_time * 0.5 + progress * 2) * 3
            r = int(18 + wave)
            g = int(20 + wave)
            b = int(28 + progress * 8 + wave)
            pygame.draw.line(self.screen, (max(0,min(255,r)), max(0,min(255,g)), max(0,min(255,b))), (0, y), (SCREEN_WIDTH, y))
        
        # ═══════════════════════════════════════════════════════════════
        # LEFT SIDEBAR - Project cards with progress rings (180px)
        # ═══════════════════════════════════════════════════════════════
        sidebar_w = 175
        sidebar_x = 8
        
        # Sidebar glass panel
        sidebar_surf = pygame.Surface((sidebar_w, SCREEN_HEIGHT - 50), pygame.SRCALPHA)
        sidebar_surf.fill((30, 32, 45, 200))
        self.screen.blit(sidebar_surf, (sidebar_x, 44))
        pygame.draw.rect(self.screen, (60, 65, 85), (sidebar_x, 44, sidebar_w, SCREEN_HEIGHT - 50), width=1, border_radius=12)
        
        # Project cards with progress rings
        card_y = 54
        proj_items = [
            ('all', 'All', total, (100, 140, 220)),
            ('inbox', 'Inbox', len(projects['inbox']['tasks']), (130, 180, 255)),
            ('salon', 'Salon', len(projects['salon']['tasks']), (255, 140, 180)),
            ('today', 'Today', today_count, (255, 200, 80)),
            ('overdue', 'Late', overdue_count, (255, 90, 90)),
        ]
        
        for proj_id, proj_name, count, color in proj_items:
            is_active = self.task_filter == proj_id
            card_h = 48
            
            # Card background with glow for active
            if is_active:
                # Animated glow
                glow_intensity = 0.6 + 0.4 * math.sin(self.wow_anim_time * 3)
                glow_color = (int(color[0] * glow_intensity), int(color[1] * glow_intensity), int(color[2] * glow_intensity))
                for g in range(4, 0, -1):
                    glow_surf = pygame.Surface((sidebar_w - 12 + g*4, card_h + g*4), pygame.SRCALPHA)
                    glow_surf.fill((*glow_color, int(30 * g)))
                    self.screen.blit(glow_surf, (sidebar_x + 6 - g*2, card_y - g*2))
                pygame.draw.rect(self.screen, (50, 55, 70), (sidebar_x + 6, card_y, sidebar_w - 12, card_h), border_radius=10)
            else:
                pygame.draw.rect(self.screen, (35, 38, 50), (sidebar_x + 6, card_y, sidebar_w - 12, card_h), border_radius=10)
            
            # Progress ring
            ring_x = sidebar_x + 32
            ring_y = card_y + card_h // 2
            ring_r = 16
            
            # Background ring
            pygame.draw.circle(self.screen, (50, 52, 65), (ring_x, ring_y), ring_r, width=3)
            
            # Progress arc (animated)
            if total > 0:
                progress = count / total
                end_angle = -math.pi/2 + progress * 2 * math.pi
                if progress > 0:
                    points = [(ring_x, ring_y)]
                    for angle in [a * 0.1 for a in range(int(-math.pi/2 * 10), int(end_angle * 10) + 1)]:
                        x = ring_x + int(ring_r * math.cos(angle))
                        y = ring_y + int(ring_r * math.sin(angle))
                        points.append((x, y))
                    if len(points) > 2:
                        # Draw arc segments
                        for i in range(len(points) - 1):
                            pygame.draw.line(self.screen, color, points[i], points[i+1], 3)
            
            # Count in center
            count_surf = self.fonts['status'].render(str(count), True, color if is_active else (160, 165, 180))
            self.screen.blit(count_surf, (ring_x - count_surf.get_width()//2, ring_y - count_surf.get_height()//2))
            
            # Project name
            name_color = (240, 245, 255) if is_active else (140, 145, 160)
            name_surf = self.fonts['msg'].render(proj_name, True, name_color)
            self.screen.blit(name_surf, (ring_x + ring_r + 10, card_y + card_h//2 - name_surf.get_height()//2))
            
            card_y += card_h + 6
        
        # ═══════════════════════════════════════════════════════════════
        # MAIN AREA - Focus card + task list (600px)
        # ═══════════════════════════════════════════════════════════════
        main_x = sidebar_x + sidebar_w + 10
        main_w = SCREEN_WIDTH - main_x - 8
        
        # Build display list
        display_list = []
        for task in filtered:
            display_list.append({'task': task, 'indent': 0})
            subtasks = task.get('subtasks', [])
            if subtasks and task['id'] in self.task_expanded:
                for sub in subtasks:
                    display_list.append({'task': sub, 'indent': 1})
        
        if not display_list:
            # Beautiful empty state with animation
            empty_y = 180
            
            # Floating card
            float_offset = math.sin(self.wow_anim_time * 2) * 5
            card_y_pos = empty_y + float_offset
            
            pygame.draw.rect(self.screen, (40, 45, 60), (main_x + 80, card_y_pos, main_w - 160, 140), border_radius=24)
            
            # Animated checkmark
            check_x = main_x + main_w // 2
            check_y = int(card_y_pos + 55)
            pulse = 0.8 + 0.2 * math.sin(self.wow_anim_time * 3)
            radius = int(30 * pulse)
            
            # Glow
            for g in range(3):
                glow_r = radius + g * 4
                pygame.draw.circle(self.screen, (60, 180, 100, 50), (check_x, check_y), glow_r, width=2)
            
            pygame.draw.circle(self.screen, (80, 200, 120), (check_x, check_y), radius, width=4)
            pygame.draw.line(self.screen, (80, 200, 120), (check_x - 12, check_y + 2), (check_x - 2, check_y + 12), 4)
            pygame.draw.line(self.screen, (80, 200, 120), (check_x - 2, check_y + 12), (check_x + 14, check_y - 8), 4)
            
            msg_surf = self.fonts['title'].render("All clear!", True, (200, 205, 220))
            self.screen.blit(msg_surf, (check_x - msg_surf.get_width()//2, int(card_y_pos + 95)))
        else:
            # Scroll handling
            if self.task_selected >= len(display_list):
                self.task_selected = max(0, len(display_list) - 1)
            
            # FOCUS CARD - Big card for selected task
            if 0 <= self.task_selected < len(display_list):
                focus_task = display_list[self.task_selected]['task']
                focus_y = 50
                focus_h = 130
                
                priority = focus_task.get('priority', 1)
                p_colors = {4: (255, 90, 90), 3: (255, 180, 70), 2: (100, 160, 255), 1: (100, 105, 130)}
                p_color = p_colors.get(priority, p_colors[1])
                
                # Animated glow border
                glow_phase = self.wow_anim_time * 2
                glow_intensity = 0.5 + 0.5 * math.sin(glow_phase)
                
                # Glass card with glow
                for g in range(5, 0, -1):
                    glow_c = (int(p_color[0] * glow_intensity * 0.3), int(p_color[1] * glow_intensity * 0.3), int(p_color[2] * glow_intensity * 0.3))
                    pygame.draw.rect(self.screen, glow_c, (main_x - g*2, focus_y - g*2, main_w + g*4, focus_h + g*4), border_radius=20)
                
                # Card background
                pygame.draw.rect(self.screen, (35, 40, 55), (main_x, focus_y, main_w, focus_h), border_radius=16)
                pygame.draw.rect(self.screen, p_color, (main_x, focus_y, 6, focus_h), border_top_left_radius=16, border_bottom_left_radius=16)
                
                # Top highlight
                pygame.draw.line(self.screen, (70, 75, 95), (main_x + 16, focus_y + 2), (main_x + main_w - 16, focus_y + 2), 1)
                
                # Priority badge
                badge_labels = {4: 'URGENT', 3: 'HIGH', 2: 'MEDIUM', 1: ''}
                if priority > 1:
                    badge_text = badge_labels[priority]
                    badge_surf = self.fonts['status'].render(badge_text, True, (255, 255, 255))
                    badge_w = badge_surf.get_width() + 16
                    pygame.draw.rect(self.screen, p_color, (main_x + main_w - badge_w - 12, focus_y + 12, badge_w, 22), border_radius=11)
                    self.screen.blit(badge_surf, (main_x + main_w - badge_w - 4, focus_y + 15))
                
                # Task title - large
                title_font = self.fonts['menu_title']
                title_text = focus_task.get('content', '')[:45] + ('...' if len(focus_task.get('content', '')) > 45 else '')
                title_surf = title_font.render(title_text, True, (235, 240, 255))
                self.screen.blit(title_surf, (main_x + 20, focus_y + 18))
                
                # Due date with icon
                due = focus_task.get('due', '')
                if due:
                    due_color = (255, 100, 100) if 'overdue' in due.lower() else (180, 185, 200)
                    due_icon = '⏰ ' if 'today' in due.lower() else '📅 '
                    due_surf = self.fonts['msg'].render(due_icon + due, True, due_color)
                    self.screen.blit(due_surf, (main_x + 20, focus_y + 55))
                
                # Description preview
                desc = focus_task.get('description', '')
                if desc:
                    desc_text = desc[:70] + ('...' if len(desc) > 70 else '')
                    desc_surf = self.fonts['status'].render(desc_text, True, (120, 125, 145))
                    self.screen.blit(desc_surf, (main_x + 20, focus_y + 80))
                
                # Subtask count
                subtasks = focus_task.get('subtasks', [])
                if subtasks:
                    sub_text = f"📋 {len(subtasks)} subtasks"
                    sub_surf = self.fonts['status'].render(sub_text, True, (130, 170, 220))
                    self.screen.blit(sub_surf, (main_x + 20, focus_y + 102))
                
                # Recurring indicator
                if focus_task.get('isRecurring'):
                    rec_surf = self.fonts['status'].render('🔄 Recurring', True, (140, 200, 160))
                    self.screen.blit(rec_surf, (main_x + 150, focus_y + 102))
            
            # TASK LIST - Below focus card
            list_y = 190
            row_h = 44
            max_visible = 5
            
            if self.task_selected < self.task_scroll:
                self.task_scroll = self.task_selected
            elif self.task_selected >= self.task_scroll + max_visible:
                self.task_scroll = self.task_selected - max_visible + 1
            
            visible = display_list[self.task_scroll:self.task_scroll + max_visible]
            row_y = list_y
            
            for i, item in enumerate(visible):
                task = item['task']
                indent = item['indent']
                actual_idx = self.task_scroll + i
                is_selected = actual_idx == self.task_selected
                priority = task.get('priority', 1)
                due = task.get('due', '')
                content = task.get('content', '') or '(empty)'
                
                p_colors = {4: (255, 90, 90), 3: (255, 180, 70), 2: (100, 160, 255), 1: (70, 75, 95)}
                p_color = p_colors.get(priority, p_colors[1])
                
                # Row background
                indent_px = indent * 24
                row_x = main_x + indent_px
                row_w = main_w - indent_px
                
                if is_selected:
                    # Subtle highlight
                    pygame.draw.rect(self.screen, (45, 50, 68), (row_x, row_y, row_w, row_h), border_radius=8)
                    # Selection indicator
                    pygame.draw.rect(self.screen, p_color, (row_x, row_y + 8, 3, row_h - 16), border_radius=2)
                
                # Check for subtasks
                subtasks = task.get('subtasks', [])
                has_subtasks = len(subtasks) > 0 and indent == 0
                is_expanded = task['id'] in self.task_expanded if has_subtasks else False
                
                # Checkbox
                cb_x = row_x + 20
                cb_y = row_y + row_h // 2
                pygame.draw.circle(self.screen, p_color if priority > 1 else (60, 65, 80), (cb_x, cb_y), 10, width=2)
                if priority >= 3:
                    pygame.draw.circle(self.screen, p_color, (cb_x, cb_y), 5)
                
                # Task text
                text_color = (220, 225, 240) if is_selected else (160, 165, 180)
                max_len = 28 - indent * 3
                display_text = content[:max_len] + ('...' if len(content) > max_len else '')
                text_surf = self.fonts['msg'].render(display_text, True, text_color)
                self.screen.blit(text_surf, (cb_x + 18, row_y + row_h//2 - text_surf.get_height()//2))
                
                # Subtask indicator RIGHT AFTER task name
                text_end_x = cb_x + 18 + text_surf.get_width() + 6
                if has_subtasks:
                    chevron_color = (130, 170, 220) if is_selected else (100, 140, 200)
                    sub_text = f"{len(subtasks)}"
                    sub_surf = self.fonts['status'].render(sub_text, True, chevron_color)
                    self.screen.blit(sub_surf, (text_end_x, row_y + row_h//2 - sub_surf.get_height()//2))
                    
                    chev_x = text_end_x + sub_surf.get_width() + 6
                    chev_y = row_y + row_h // 2
                    if is_expanded:
                        # Down chevron (expanded)
                        pygame.draw.line(self.screen, chevron_color, (chev_x - 4, chev_y - 3), (chev_x, chev_y + 2), 2)
                        pygame.draw.line(self.screen, chevron_color, (chev_x, chev_y + 2), (chev_x + 4, chev_y - 3), 2)
                    else:
                        # Right chevron (collapsed)
                        pygame.draw.line(self.screen, chevron_color, (chev_x - 2, chev_y - 4), (chev_x + 3, chev_y), 2)
                        pygame.draw.line(self.screen, chevron_color, (chev_x + 3, chev_y), (chev_x - 2, chev_y + 4), 2)
                
                # Right side for due pill
                right_x = row_x + row_w - 12
                
                # Due pill on right side
                if due and not is_selected:
                    due_text = due[:6]
                    due_bg = (180, 60, 60) if 'overdue' in due.lower() else (50, 55, 70)
                    due_surf = self.fonts['status'].render(due_text, True, (200, 205, 220))
                    pill_w = due_surf.get_width() + 12
                    pill_x = right_x - pill_w
                    pygame.draw.rect(self.screen, due_bg, (pill_x, row_y + row_h//2 - 10, pill_w, 20), border_radius=10)
                    self.screen.blit(due_surf, (pill_x + 6, row_y + row_h//2 - due_surf.get_height()//2))
                
                row_y += row_h
            
            # Scroll indicators with style
            if self.task_scroll > 0:
                up_surf = self.fonts['status'].render(f"▲ {self.task_scroll} above", True, (100, 140, 220))
                self.screen.blit(up_surf, (main_x + main_w//2 - up_surf.get_width()//2, list_y - 18))
            
            remaining = len(display_list) - self.task_scroll - max_visible
            if remaining > 0:
                down_surf = self.fonts['status'].render(f"▼ {remaining} below", True, (100, 140, 220))
                self.screen.blit(down_surf, (main_x + main_w//2 - down_surf.get_width()//2, row_y + 4))
        
        # ═══════════════════════════════════════════════════════════════
        # FOOTER - Stylish hints + sync indicator
        # ═══════════════════════════════════════════════════════════════
        if self.task_editing:
            hint = "Enter: Save  •  Esc: Cancel"
        else:
            hint = "↑↓ Navigate  •  Space Complete  •  1-5 Filter  •  N New  •  R Sync"
        hint_surf = self.fonts['status'].render(hint, True, (90, 95, 115))
        self.screen.blit(hint_surf, ((SCREEN_WIDTH - hint_surf.get_width())//2, SCREEN_HEIGHT - 18))
        
        # Sync indicator in bottom-right of panel
        sync_status = getattr(self, 'todoist_sync_status', 'live')
        if sync_status == 'live':
            sync_text = "● Synced"
            sync_color = (80, 200, 120)
        elif sync_status == 'syncing':
            sync_text = "◐ Syncing"
            sync_color = (220, 180, 60)
        else:
            sync_text = "✗ Error"
            sync_color = (220, 80, 80)
        sync_surf = self.fonts['status'].render(sync_text, True, sync_color)
        self.screen.blit(sync_surf, (SCREEN_WIDTH - sync_surf.get_width() - 12, SCREEN_HEIGHT - 18))


    def draw_commands(self):
        """Draw commands panel with modern card design"""
        
        # Show confirmation dialog if active
        if self.command_confirm is not None:
            self._draw_confirm_dialog()
            return
        
        # Show running indicator if active
        if self.command_running:
            self._draw_command_running()
            return
        
        # Show result if available
        if self.command_result:
            self._draw_command_result()
            return
        
        commands = self.get_commands()
        
        # Layout: 2 columns, 4 rows - fills the screen nicely
        card_w = 380
        card_h = 80
        margin_x = 15
        margin_y = 65
        spacing_x = 10
        spacing_y = 10
        
        for idx, cmd in enumerate(commands):
            col = idx % 2
            row = idx // 2
            
            x = margin_x + col * (card_w + spacing_x)
            y = margin_y + row * (card_h + spacing_y)
            
            is_selected = idx == self.command_selection
            category = cmd.get('category', 'safe')
            
            # Card background with gradient effect
            if is_selected:
                # Glow effect
                glow_color = cmd['color']
                pygame.draw.rect(self.screen, glow_color, (x - 2, y - 2, card_w + 4, card_h + 4), border_radius=14)
            
            bg_color = C['bg_item_hover'] if is_selected else C['bg_item']
            pygame.draw.rect(self.screen, bg_color, (x, y, card_w, card_h), border_radius=12)
            
            # Thick color bar on left based on category
            bar_w = 8
            pygame.draw.rect(self.screen, cmd['color'], (x, y, bar_w, card_h), 
                           border_top_left_radius=12, border_bottom_left_radius=12)
            
            # Icon circle
            icon_x = x + 45
            icon_y = y + card_h // 2
            icon_r = 24
            icon_bg = cmd['color'] if is_selected else (60, 60, 75)
            pygame.draw.circle(self.screen, icon_bg, (icon_x, icon_y), icon_r)
            
            # Icon letter
            icon = cmd.get('icon', '?')
            icon_surf = self.fonts['title'].render(icon, True, C['text_bright'])
            icon_text_x = icon_x - icon_surf.get_width() // 2
            icon_text_y = icon_y - icon_surf.get_height() // 2
            self.screen.blit(icon_surf, (icon_text_x, icon_text_y))
            
            # Label - bigger and bolder
            label_surf = self.fonts['title'].render(cmd['label'], True, C['text_bright'])
            self.screen.blit(label_surf, (x + 80, y + 18))
            
            # Description
            desc_surf = self.fonts['msg'].render(cmd['desc'], True, C['text_dim'])
            self.screen.blit(desc_surf, (x + 80, y + 50))
            
            # Warning icon on right for non-safe commands
            if category == 'danger':
                # Red warning triangle
                badge_x = x + card_w - 40
                badge_y = y + card_h // 2
                pygame.draw.circle(self.screen, C['error'], (badge_x, badge_y), 16)
                warn_surf = self.fonts['title'].render("!", True, C['text_bright'])
                self.screen.blit(warn_surf, (badge_x - warn_surf.get_width() // 2, badge_y - warn_surf.get_height() // 2))
            elif category == 'caution':
                # Yellow warning
                badge_x = x + card_w - 40
                badge_y = y + card_h // 2
                pygame.draw.circle(self.screen, C['warning'], (badge_x, badge_y), 16)
                warn_surf = self.fonts['title'].render("!", True, (40, 40, 40))
                self.screen.blit(warn_surf, (badge_x - warn_surf.get_width() // 2, badge_y - warn_surf.get_height() // 2))
        
        # Footer
        help_text = "1-8: Quick Run  |  Arrows: Navigate  |  Enter: Execute"
        help_surf = self.fonts['status'].render(help_text, True, C['text_muted'])
        help_x = (SCREEN_WIDTH - help_surf.get_width()) // 2
        self.screen.blit(help_surf, (help_x, SCREEN_HEIGHT - 18))
    
    def _draw_command_running(self):
        """Draw running command indicator"""
        # Center card
        card_w, card_h = 350, 120
        x = (SCREEN_WIDTH - card_w) // 2
        y = (SCREEN_HEIGHT - card_h) // 2
        
        pygame.draw.rect(self.screen, C['bg_item'], (x, y, card_w, card_h), border_radius=16)
        pygame.draw.rect(self.screen, C['accent'], (x, y, card_w, card_h), width=3, border_radius=16)
        
        # Spinner animation
        spinner_chars = "◐◓◑◒"
        spinner = spinner_chars[int(time.time() * 4) % 4]
        spinner_surf = self.fonts['menu_title'].render(spinner, True, C['accent'])
        self.screen.blit(spinner_surf, (x + card_w // 2 - 15, y + 20))
        
        # Running text
        text = f"Running: {self.command_running}"
        if len(text) > 35:
            text = text[:32] + "..."
        text_surf = self.fonts['msg'].render(text, True, C['text'])
        text_x = x + (card_w - text_surf.get_width()) // 2
        self.screen.blit(text_surf, (text_x, y + 65))
        
        # Please wait
        wait_surf = self.fonts['status'].render("Please wait...", True, C['text_dim'])
        wait_x = x + (card_w - wait_surf.get_width()) // 2
        self.screen.blit(wait_surf, (wait_x, y + 92))
    
    def _draw_command_result(self):
        """Draw command result"""
        result_type, result_msg = self.command_result
        is_success = result_type == 'success'
        
        # Center card
        card_w, card_h = 400, 140
        x = (SCREEN_WIDTH - card_w) // 2
        y = (SCREEN_HEIGHT - card_h) // 2
        
        border_color = C['success'] if is_success else C['error']
        pygame.draw.rect(self.screen, C['bg_item'], (x, y, card_w, card_h), border_radius=16)
        pygame.draw.rect(self.screen, border_color, (x, y, card_w, card_h), width=3, border_radius=16)
        
        # Icon and header
        icon = "✓" if is_success else "✗"
        header = "Success" if is_success else "Error"
        icon_surf = self.fonts['menu_title'].render(icon, True, border_color)
        header_surf = self.fonts['title'].render(header, True, border_color)
        self.screen.blit(icon_surf, (x + card_w // 2 - 60, y + 18))
        self.screen.blit(header_surf, (x + card_w // 2 - 30, y + 20))
        
        # Result message (wrap if needed)
        msg_lines = [result_msg[i:i+45] for i in range(0, len(result_msg), 45)][:2]
        msg_y = y + 60
        for line in msg_lines:
            msg_surf = self.fonts['msg'].render(line, True, C['text'])
            msg_x = x + (card_w - msg_surf.get_width()) // 2
            self.screen.blit(msg_surf, (msg_x, msg_y))
            msg_y += 24
        
        # Hint
        hint_surf = self.fonts['status'].render("Press any key to continue", True, C['text_muted'])
        hint_x = x + (card_w - hint_surf.get_width()) // 2
        self.screen.blit(hint_surf, (hint_x, y + card_h - 28))
        
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
    
    def draw_kanban(self):
        """WOW Kanban v3 - Fast Track row at top, columns below"""
        import math
        
        # Auto-refresh every 5 seconds
        now = time.time()
        if not hasattr(self, 'kanban_last_refresh'):
            self.kanban_last_refresh = 0
        if now - self.kanban_last_refresh > 5:
            self._load_kanban_data()
            self.kanban_last_refresh = now
        
        # Animation timer
        if not hasattr(self, 'kanban_anim'):
            self.kanban_anim = 0
        self.kanban_anim += 0.02
        
        # Initialize state
        if not hasattr(self, 'kanban_col'):
            self.kanban_col = 0
            self.kanban_card = 0
            self.kanban_board = 'salon'
            self.kanban_detail = False
            self.kanban_scroll = {}
            self.kanban_sync_status = 'live'
            self.kanban_sync_time = 0
            self.kanban_in_fasttrack = False  # Are we in fast track row?
            self.kanban_ft_card = 0  # Selected card in fast track
        
        all_columns = ['Not Started', 'Research', 'Active', 'Stuck', 'Review', 'Implement', 'Finished']
        col_colors = {
            'Not Started': (90, 95, 130), 'Research': (70, 130, 200), 
            'Active': (60, 180, 100), 'Stuck': (200, 70, 70),
            'Review': (200, 160, 50), 'Implement': (140, 90, 190), 'Finished': (50, 160, 90)
        }
        col_icons = {'Not Started': '○', 'Research': '◎', 'Active': '●', 'Stuck': '!', 
                     'Review': '◐', 'Implement': '▸', 'Finished': '✓'}
        
        # ═══════════════════════════════════════════════════════════════
        # BACKGROUND
        # ═══════════════════════════════════════════════════════════════
        for y in range(36, SCREEN_HEIGHT):
            progress = (y - 36) / (SCREEN_HEIGHT - 36)
            r = int(14 + progress * 4)
            g = int(16 + progress * 4)
            b = int(22 + progress * 8)
            pygame.draw.line(self.screen, (r, g, b), (0, y), (SCREEN_WIDTH, y))
        
        # ═══════════════════════════════════════════════════════════════
        # HEADER - Just Salon/Personal tabs (Fast Track is always visible)
        # ═══════════════════════════════════════════════════════════════
        header_y = 44
        header_h = 28
        
        # Glass header bar
        header_surf = pygame.Surface((SCREEN_WIDTH - 20, header_h), pygame.SRCALPHA)
        header_surf.fill((30, 32, 45, 180))
        self.screen.blit(header_surf, (10, header_y - 4))
        pygame.draw.rect(self.screen, (50, 55, 70), (10, header_y - 4, SCREEN_WIDTH - 20, header_h), width=1, border_radius=6)
        
        boards = [
            ('salon', 'Salon', (100, 150, 220)),
            ('personal', 'Personal', (120, 180, 120)),
        ]
        
        tab_x = 20
        for board_id, board_name, board_color in boards:
            is_active = self.kanban_board == board_id
            display_color = board_color if is_active else (90, 95, 115)
            
            tab_surf = self.fonts['msg'].render(board_name, True, display_color)
            self.screen.blit(tab_surf, (tab_x, header_y + 2))
            
            if is_active:
                pygame.draw.rect(self.screen, display_color, (tab_x, header_y + 18, tab_surf.get_width(), 2), border_radius=1)
            
            tab_x += tab_surf.get_width() + 25
        
        # Sync indicator
        sync_status = getattr(self, 'kanban_sync_status', 'live')
        sync_time = getattr(self, 'kanban_sync_time', 0)
        if sync_status == 'syncing' and time.time() - sync_time > 1:
            self.kanban_sync_status = 'live'
            sync_status = 'live'
        
        sync_colors = {'live': (80, 200, 120), 'syncing': (220, 180, 60), 'error': (220, 80, 80)}
        sync_texts = {'live': '●', 'syncing': '◐', 'error': '✗'}
        sync_surf = self.fonts['status'].render(sync_texts.get(sync_status, '●'), True, sync_colors.get(sync_status, (80, 200, 120)))
        self.screen.blit(sync_surf, (SCREEN_WIDTH - 25, header_y + 4))
        
        # ═══════════════════════════════════════════════════════════════
        # FAST TRACK ROW - Always visible at top, column layout
        # ═══════════════════════════════════════════════════════════════
        ft_y = header_y + header_h + 4
        ft_h = 70  # Taller for better visibility
        
        # Get fast track items from parsed data
        ft_cards = []
        ft_data = getattr(self, 'kanban_fasttrack', {})
        for col_name in all_columns:
            for card in ft_data.get(col_name, []):
                ft_cards.append(card)
        
        # Fast track container with pulsing border
        pulse = 0.6 + 0.4 * math.sin(self.kanban_anim * 3)
        ft_border = (int(200 * pulse), int(60 * pulse), int(60 * pulse))
        is_ft_selected = getattr(self, 'kanban_in_fasttrack', False)
        
        if is_ft_selected:
            # Brighter when selected
            pygame.draw.rect(self.screen, (45, 30, 30), (10, ft_y, SCREEN_WIDTH - 20, ft_h), border_radius=8)
            pygame.draw.rect(self.screen, (255, 100, 80), (10, ft_y, SCREEN_WIDTH - 20, ft_h), width=2, border_radius=8)
        else:
            pygame.draw.rect(self.screen, (30, 22, 22), (10, ft_y, SCREEN_WIDTH - 20, ft_h), border_radius=8)
            pygame.draw.rect(self.screen, ft_border, (10, ft_y, SCREEN_WIDTH - 20, ft_h), width=1, border_radius=8)
        
        # Fast track label with fire
        fire_pulse = 0.8 + 0.2 * math.sin(self.kanban_anim * 4)
        ft_label = self.fonts['status'].render('🔥 FAST TRACK', True, (int(255 * fire_pulse), int(100 * fire_pulse), 80))
        self.screen.blit(ft_label, (18, ft_y + 4))
        
        # Fast track cards - column layout matching main columns
        ft_card_h = 24
        ft_cards_y = ft_y + 22
        
        # Use same column positions as main columns for alignment
        finished_w = 55
        normal_w = (SCREEN_WIDTH - 20 - finished_w) // 6
        col_gap = 3
        
        ft_col_positions = []
        current_x = 10
        for i, col_name in enumerate(all_columns):
            w = finished_w if col_name == 'Finished' else normal_w
            ft_col_positions.append((current_x, w))
            current_x += w + col_gap
        
        # Group fast track cards by their source column
        ft_by_col = {col: [] for col in all_columns}
        for card in ft_cards:
            src_col = card.get('_from_column', 'Active')
            if src_col in ft_by_col:
                ft_by_col[src_col].append(card)
        
        # Draw fast track cards in their column positions
        ft_card_idx = 0
        for col_idx, col_name in enumerate(all_columns):
            col_x, col_w = ft_col_positions[col_idx]
            col_ft_cards = ft_by_col[col_name]
            
            for i, card in enumerate(col_ft_cards[:2]):  # Max 2 per column in FT row
                is_selected = is_ft_selected and ft_card_idx == getattr(self, 'kanban_ft_card', 0)
                card_y = ft_cards_y + i * (ft_card_h + 2)
                
                # Card background
                if is_selected:
                    pygame.draw.rect(self.screen, (80, 50, 50), (col_x + 2, card_y, col_w - col_gap - 4, ft_card_h), border_radius=4)
                    pygame.draw.rect(self.screen, (255, 120, 100), (col_x + 2, card_y, col_w - col_gap - 4, ft_card_h), border_radius=4, width=2)
                else:
                    pygame.draw.rect(self.screen, (55, 38, 38), (col_x + 2, card_y, col_w - col_gap - 4, ft_card_h), border_radius=4)
                
                # Fire + title
                title = card.get('title', '').lstrip('🔥').strip()[:10]
                title_color = (255, 220, 200) if is_selected else (200, 150, 140)
                title_surf = self.fonts['status'].render(f"🔥{title}", True, title_color)
                self.screen.blit(title_surf, (col_x + 5, card_y + 5))
                
                ft_card_idx += 1
        
        # Show empty hint if no fast track items
        if not ft_cards:
            empty_surf = self.fonts['status'].render('↑ Space to add urgent items', True, (70, 55, 55))
            self.screen.blit(empty_surf, (SCREEN_WIDTH // 2 - empty_surf.get_width() // 2, ft_y + 32))
        
        # ═══════════════════════════════════════════════════════════════
        # COLUMNS - Below fast track
        # ═══════════════════════════════════════════════════════════════
        cols_y = ft_y + ft_h + 6
        cols_h = SCREEN_HEIGHT - cols_y - 22
        col_gap = 3
        
        # Finished column is narrow
        finished_w = 55
        normal_w = (SCREEN_WIDTH - 20 - finished_w) // 6
        
        col_positions = []
        current_x = 10
        for i, col_name in enumerate(all_columns):
            w = finished_w if col_name == 'Finished' else normal_w
            col_positions.append((current_x, w))
            current_x += w + col_gap
        
        for col_idx, col_name in enumerate(all_columns):
            col_x, col_w = col_positions[col_idx]
            is_selected_col = (not self.kanban_in_fasttrack) and col_idx == self.kanban_col
            col_color = col_colors[col_name]
            cards = self._get_kanban_column_cards(col_name)
            is_finished = col_name == 'Finished'
            
            # Selected column glow
            if is_selected_col:
                glow = 0.6 + 0.4 * math.sin(self.kanban_anim * 3)
                glow_color = (int(col_color[0] * glow * 0.5), int(col_color[1] * glow * 0.5), int(col_color[2] * glow * 0.5))
                pygame.draw.rect(self.screen, glow_color, (col_x - 2, cols_y - 2, col_w - col_gap + 4, cols_h + 4), border_radius=8, width=2)
            
            # Column background
            bg_color = (32, 35, 48) if is_selected_col else (24, 27, 38)
            pygame.draw.rect(self.screen, bg_color, (col_x, cols_y, col_w - col_gap, cols_h), border_radius=6)
            
            # Column header
            col_header_h = 24
            pygame.draw.rect(self.screen, col_color, (col_x, cols_y, col_w - col_gap, col_header_h), border_top_left_radius=6, border_top_right_radius=6)
            
            if is_finished:
                count_text = f"✓{len(cards)}"
                count_surf = self.fonts['status'].render(count_text, True, (255, 255, 255))
                self.screen.blit(count_surf, (col_x + (col_w - col_gap) // 2 - count_surf.get_width() // 2, cols_y + 4))
            else:
                icon = col_icons[col_name]
                icon_surf = self.fonts['status'].render(icon, True, (255, 255, 255))
                self.screen.blit(icon_surf, (col_x + 5, cols_y + 4))
                
                count_surf = self.fonts['status'].render(str(len(cards)), True, (255, 255, 255))
                self.screen.blit(count_surf, (col_x + col_w - col_gap - count_surf.get_width() - 5, cols_y + 4))
            
            # Cards
            cards_y = cols_y + col_header_h + 2
            card_h = 18 if is_finished else 38
            card_gap_inner = 2
            available_h = cols_h - col_header_h - 4
            max_visible = available_h // (card_h + card_gap_inner)
            
            scroll = self.kanban_scroll.get(col_idx, 0)
            visible_cards = cards[scroll:scroll + max_visible]
            
            if not cards:
                empty_surf = self.fonts['status'].render("—", True, (45, 50, 60))
                self.screen.blit(empty_surf, (col_x + (col_w - col_gap) // 2 - 4, cards_y + 15))
            
            for card_idx, card in enumerate(visible_cards):
                actual_idx = scroll + card_idx
                is_selected_card = is_selected_col and actual_idx == self.kanban_card
                card_y_pos = cards_y + card_idx * (card_h + card_gap_inner)
                
                is_fast = '🔥' in card.get('title', '') or card.get('fast_track', False)
                
                if is_finished:
                    # Minimal finished cards
                    if is_selected_card:
                        pygame.draw.rect(self.screen, (50, 70, 55), (col_x + 2, card_y_pos, col_w - col_gap - 4, card_h), border_radius=3)
                        pygame.draw.rect(self.screen, col_color, (col_x + 2, card_y_pos, col_w - col_gap - 4, card_h), border_radius=3, width=1)
                    else:
                        pygame.draw.rect(self.screen, (35, 48, 40), (col_x + 2, card_y_pos, col_w - col_gap - 4, card_h), border_radius=3)
                    
                    check_color = (100, 200, 120) if is_selected_card else (60, 130, 80)
                    check_surf = self.fonts['status'].render('✓', True, check_color)
                    self.screen.blit(check_surf, (col_x + (col_w - col_gap) // 2 - check_surf.get_width() // 2, card_y_pos + 2))
                else:
                    # Normal cards
                    if is_selected_card:
                        pygame.draw.rect(self.screen, (55, 60, 80), (col_x + 2, card_y_pos, col_w - col_gap - 4, card_h), border_radius=4)
                        pygame.draw.rect(self.screen, col_color, (col_x + 2, card_y_pos, col_w - col_gap - 4, card_h), border_radius=4, width=2)
                    elif is_fast:
                        pulse = 0.7 + 0.3 * math.sin(self.kanban_anim * 5)
                        pygame.draw.rect(self.screen, (int(50 * pulse), int(30 * pulse), int(30 * pulse)), (col_x + 2, card_y_pos, col_w - col_gap - 4, card_h), border_radius=4)
                        pygame.draw.rect(self.screen, (160, 50, 50), (col_x + 2, card_y_pos, 3, card_h), border_top_left_radius=4, border_bottom_left_radius=4)
                    else:
                        pygame.draw.rect(self.screen, (38, 42, 55), (col_x + 2, card_y_pos, col_w - col_gap - 4, card_h), border_radius=4)
                    
                    # Priority bar
                    priority = card.get('priority', 'green')
                    p_colors = {'red': (200, 60, 60), 'yellow': (200, 160, 40), 'green': (60, 160, 90)}
                    if not is_fast:
                        pygame.draw.rect(self.screen, p_colors.get(priority, p_colors['green']), 
                                       (col_x + 2, card_y_pos, 3, card_h), border_top_left_radius=4, border_bottom_left_radius=4)
                    
                    # Title - 2 lines
                    title = card.get('title', 'Untitled').lstrip('🔥').strip()
                    text_x = col_x + 8
                    text_y = card_y_pos + 3
                    
                    if is_fast:
                        fire_pulse = 0.8 + 0.2 * math.sin(self.kanban_anim * 6 + card_idx)
                        fire_surf = self.fonts['status'].render('🔥', True, (int(255 * fire_pulse), int(100 * fire_pulse), 50))
                        self.screen.blit(fire_surf, (text_x, text_y))
                        text_x += 12
                    
                    title_color = (235, 240, 255) if is_selected_card else (170, 175, 195)
                    max_chars = 11
                    
                    line1 = title[:max_chars]
                    line1_surf = self.fonts['status'].render(line1, True, title_color)
                    self.screen.blit(line1_surf, (text_x, text_y))
                    
                    if len(title) > max_chars:
                        line2 = title[max_chars:max_chars*2]
                        if len(title) > max_chars * 2:
                            line2 = line2[:-1] + '…'
                        line2_surf = self.fonts['status'].render(line2, True, title_color)
                        self.screen.blit(line2_surf, (col_x + 8, text_y + 13))
            
            # Scroll indicators
            if scroll > 0:
                pygame.draw.polygon(self.screen, (90, 100, 130), [
                    (col_x + (col_w - col_gap) // 2, cards_y - 4),
                    (col_x + (col_w - col_gap) // 2 - 5, cards_y),
                    (col_x + (col_w - col_gap) // 2 + 5, cards_y)
                ])
            if len(cards) > scroll + max_visible:
                arrow_y = cols_y + cols_h - 4
                pygame.draw.polygon(self.screen, (90, 100, 130), [
                    (col_x + (col_w - col_gap) // 2 - 5, arrow_y - 4),
                    (col_x + (col_w - col_gap) // 2 + 5, arrow_y - 4),
                    (col_x + (col_w - col_gap) // 2, arrow_y)
                ])
        
        # Detail popup
        if self.kanban_detail:
            self._draw_kanban_detail()
        
        # Floating card when holding
        if hasattr(self, 'kanban_holding') and self.kanban_holding:
            ghost_x, ghost_w = col_positions[self.kanban_col]
            ghost_y = cols_y + 40
            pulse = 0.7 + 0.3 * math.sin(self.kanban_anim * 5)
            pygame.draw.rect(self.screen, (int(80 * pulse), int(120 * pulse), int(200 * pulse)), 
                           (ghost_x + 2, ghost_y, ghost_w - col_gap - 4, 32), border_radius=5, width=2)
            title = self.kanban_holding.get('title', '')[:10]
            title_surf = self.fonts['status'].render(title, True, (180, 200, 240))
            self.screen.blit(title_surf, (ghost_x + 10, ghost_y + 8))
        
        # Footer
        if hasattr(self, 'kanban_holding') and self.kanban_holding:
            hint = "←→ Move  •  Space Place  •  Esc Cancel"
            hint_color = (220, 180, 80)
        elif self.kanban_in_fasttrack:
            hint = "←→ Card  •  ↓ Columns  •  Space Grab  •  Enter Details"
            hint_color = (255, 150, 120)
        else:
            hint = "↑ Fast Track  •  ←→ Col  •  ↑↓ Card  •  Space Grab  •  Tab Board"
            hint_color = (90, 95, 115)
        hint_surf = self.fonts['status'].render(hint, True, hint_color)
        self.screen.blit(hint_surf, ((SCREEN_WIDTH - hint_surf.get_width())//2, SCREEN_HEIGHT - 14))

    def _get_kanban_column_cards(self, col_name):
        """Get cards for a column"""
        return self.kanban_data.get(col_name, [])
    
    def _draw_kanban_column(self, x, y, w, h, col_name, col_idx, col_colors, col_icons):
        """Draw a single kanban column with scroll support"""
        is_selected = col_idx == self.kanban_col
        cards = self.kanban_data.get(col_name, [])
        col_color = col_colors.get(col_name, C['text_dim'])
        
        # Get scroll offset for this column
        scroll = self.kanban_scroll.get(col_idx, 0)
        
        # Column container with selection highlight
        if is_selected:
            pygame.draw.rect(self.screen, col_color, (x - 2, y - 2, w + 4, h + 4), width=3, border_radius=10)
        
        # Header
        pygame.draw.rect(self.screen, col_color, (x, y, w, 26), border_radius=6)
        icon = col_icons.get(col_name, '📌')
        short_name = col_name[:8] if len(col_name) > 8 else col_name
        header_surf = self.fonts['status'].render(f"{icon} {short_name}", True, C['text_bright'])
        self.screen.blit(header_surf, (x + 6, y + 5))
        
        # Count badge
        count_surf = self.fonts['status'].render(str(len(cards)), True, C['text_bright'])
        self.screen.blit(count_surf, (x + w - 18, y + 5))
        
        # Body
        body_y = y + 30
        body_h = h - 34
        pygame.draw.rect(self.screen, C['bg_item'], (x, body_y, w, body_h), border_radius=6)
        
        # Card dimensions
        card_h = 48
        card_spacing = 4
        card_area_top = body_y + 4
        card_area_bottom = body_y + body_h - 4
        available_h = card_area_bottom - card_area_top
        max_cards = available_h // (card_h + card_spacing)
        
        if not cards:
            empty_surf = self.fonts['status'].render("—", True, C['text_muted'])
            self.screen.blit(empty_surf, (x + w // 2 - 5, body_y + body_h // 2 - 8))
            return
        
        # Ensure scroll is valid
        if scroll > len(cards) - 1:
            scroll = max(0, len(cards) - 1)
            self.kanban_scroll[col_idx] = scroll
        
        # Draw visible cards
        card_y = card_area_top
        visible_cards = cards[scroll:scroll + max_cards]
        
        for j, card in enumerate(visible_cards):
            actual_idx = scroll + j
            is_card_sel = is_selected and actual_idx == self.kanban_card
            
            # Card background
            card_bg = C['bg_item_hover'] if is_card_sel else C['bg']
            pygame.draw.rect(self.screen, card_bg, (x + 3, card_y, w - 6, card_h), border_radius=5)
            
            # Selection border
            if is_card_sel:
                pygame.draw.rect(self.screen, C['accent'], (x + 3, card_y, w - 6, card_h), width=2, border_radius=5)
            
            # Priority bar
            p_color = {'🔴': C['error'], '🟡': C['warning'], '🟢': C['success']}.get(card.get('priority', '🟡'), C['warning'])
            pygame.draw.rect(self.screen, p_color, (x + 3, card_y, 4, card_h), border_radius=2)
            
            # Title
            title = card.get('title', '?')
            max_chars = (w - 20) // 7
            if len(title) > max_chars:
                title = title[:max_chars-1] + "…"
            title_surf = self.fonts['status'].render(title, True, C['text_bright'])
            self.screen.blit(title_surf, (x + 12, card_y + 8))
            
            # Due date on second line
            due = card.get('due', '')
            if due and due != 'TBD':
                due_color = C['error'] if 'TODAY' in due.upper() else C['text_dim']
                due_surf = self.fonts['status'].render(due[:12], True, due_color)
                self.screen.blit(due_surf, (x + 12, card_y + 28))
            
            card_y += card_h + card_spacing
        
        # Scroll indicators
        if scroll > 0:
            up_surf = self.fonts['status'].render(f"▲{scroll}", True, C['warning'])
            self.screen.blit(up_surf, (x + w - 24, body_y + 4))
        
        remaining = len(cards) - scroll - max_cards
        if remaining > 0:
            down_surf = self.fonts['status'].render(f"▼{remaining}", True, C['warning'])
            self.screen.blit(down_surf, (x + w - 24, body_y + body_h - 14))
    
    def _draw_kanban_detail(self):
        """Draw card detail popup"""
        columns = list(self.kanban_data.keys())
        cards = self.kanban_data.get(columns[self.kanban_col], [])
        if not cards or self.kanban_card >= len(cards):
            self.kanban_detail = False
            return
        
        card = cards[self.kanban_card]
        
        # Overlay
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        overlay.fill((0, 0, 0))
        overlay.set_alpha(200)
        self.screen.blit(overlay, (0, 0))
        
        # Popup
        pw, ph = 500, 300
        px, py = (SCREEN_WIDTH - pw) // 2, (SCREEN_HEIGHT - ph) // 2
        pygame.draw.rect(self.screen, C['bg_overlay'], (px, py, pw, ph), border_radius=12)
        pygame.draw.rect(self.screen, C['accent'], (px, py, pw, ph), width=2, border_radius=12)
        
        # Priority bar
        p_color = {'🔴': C['error'], '🟡': C['warning'], '🟢': C['success']}.get(card.get('priority', '🟡'), C['warning'])
        pygame.draw.rect(self.screen, p_color, (px, py, 8, ph), border_radius=6)
        
        # Title
        title_surf = self.fonts['title'].render(card.get('title', 'Untitled')[:35], True, C['text_bright'])
        self.screen.blit(title_surf, (px + 20, py + 15))
        
        # Details
        details_y = py + 55
        if card.get('due'):
            due_surf = self.fonts['msg'].render(f"📅 Due: {card['due']}", True, C['text'])
            self.screen.blit(due_surf, (px + 20, details_y))
            details_y += 28
        if card.get('context'):
            ctx_surf = self.fonts['msg'].render(f"🏷️ {card['context']}", True, C['text_dim'])
            self.screen.blit(ctx_surf, (px + 20, details_y))
            details_y += 28
        if card.get('description'):
            desc_lines = [card['description'][i:i+50] for i in range(0, len(card['description']), 50)][:4]
            for dl in desc_lines:
                desc_surf = self.fonts['status'].render(dl, True, C['text'])
                self.screen.blit(desc_surf, (px + 20, details_y))
                details_y += 20
        
        # Close hint
        close_surf = self.fonts['status'].render("Press Esc or Enter to close", True, C['text_muted'])
        self.screen.blit(close_surf, (px + (pw - close_surf.get_width()) // 2, py + ph - 30))
    
    def _load_kanban_data(self):
        """Parse kanban markdown file into structured data"""
        import re
        self.kanban_data = {
            'Not Started': [], 'Research': [], 'Active': [], 
            'Stuck': [], 'Review': [], 'Implement': [], 'Finished': []
        }
        self.kanban_fasttrack = {
            'Not Started': [], 'Research': [], 'Active': [], 
            'Stuck': [], 'Review': [], 'Implement': [], 'Finished': []
        }
        
        board_name = getattr(self, 'kanban_board', 'salon')
        
        # Select file based on current board
        kanban_file = Path.home() / f'.openclaw/workspace/work/kanban/{board_name}.md'
        if not kanban_file.exists():
            return
        
        self._parse_kanban_file(kanban_file)
    
    def _load_fasttrack_data(self):
        """Load Fast Track items from both salon and personal boards"""
        import re
        
        for board in ['salon', 'personal']:
            kanban_file = Path.home() / f'.openclaw/workspace/work/kanban/{board}.md'
            if not kanban_file.exists():
                continue
            
            try:
                content = kanban_file.read_text()
                in_fasttrack = False
                current_column = None
                current_card = None
                
                for line in content.split('\n'):
                    # Detect Fast Track section
                    if '## 🔥' in line or '## Fast Track' in line.replace(' ', ''):
                        in_fasttrack = True
                        continue
                    
                    # Exit fast track on next major section
                    if in_fasttrack and line.startswith('## ') and '🔥' not in line:
                        in_fasttrack = False
                        current_card = None
                        continue
                    
                    if not in_fasttrack:
                        continue
                    
                    # Column headers in fast track
                    if line.startswith('### '):
                        col_name = line[4:].strip().replace(' (Urgent)', '')
                        for known in self.kanban_data.keys():
                            if known.lower() in col_name.lower():
                                current_column = known
                                break
                        current_card = None
                    
                    # Card titles
                    elif line.startswith('- **') or line.startswith('- '):
                        title_match = re.match(r'-\s*\*?\*?(.+?)\*?\*?\s*(🔴|🟡|🟢)?$', line)
                        if title_match and current_column:
                            title = title_match.group(1).strip().strip('*')
                            priority = title_match.group(2) or '🔴'  # Fast track defaults to high priority
                            source = '🏪' if board == 'salon' else '👤'
                            current_card = {'title': f"{source} {title}", 'priority': priority, 'due': '', 'context': board, 'description': ''}
                            self.kanban_data[current_column].append(current_card)
            except:
                pass
        
        # Sort by priority
        priority_order = {'🔴': 0, '🟡': 1, '🟢': 2}
        for col in self.kanban_data:
            self.kanban_data[col].sort(key=lambda c: priority_order.get(c.get('priority', '🟡'), 1))
    
    def _parse_kanban_file(self, kanban_file):
        """Parse a single kanban file - separates main board from Fast Track"""
        import re
        
        # Initialize fast track data
        if not hasattr(self, 'kanban_fasttrack'):
            self.kanban_fasttrack = {col: [] for col in self.kanban_data.keys()}
        
        try:
            content = kanban_file.read_text()
            current_column = None
            current_card = None
            in_fasttrack = False  # Track if we're in Fast Track section
            
            for line in content.split('\n'):
                # Detect Fast Track section start
                if line.startswith('## 🔥 Fast Track'):
                    in_fasttrack = True
                    current_column = None
                    current_card = None
                    continue
                
                # Detect end of Fast Track (Archive section)
                if line.startswith('## Archive'):
                    in_fasttrack = False
                    current_column = None
                    current_card = None
                    continue
                
                # Detect column headers (### Column Name)
                if line.startswith('### ') and not line.startswith('### Idea') and not line.startswith('### Status') and not line.startswith('### Check') and not line.startswith('### Notes'):
                    col_name = line[4:].strip()
                    # Remove (Urgent) suffix for matching
                    col_name = col_name.replace(' (Urgent)', '')
                    # Match to known columns
                    for known in self.kanban_data.keys():
                        if known.lower() in col_name.lower():
                            current_column = known
                            break
                    current_card = None
                
                # Detect card titles (## Title 🔴/🟡/🟢)
                elif line.startswith('## ') and current_column and not line.startswith('## Main') and not line.startswith('## 💡'):
                    title_match = re.match(r'## (.+?)\s*(🔴|🟡|🟢)?$', line)
                    if title_match:
                        title = title_match.group(1).strip()
                        priority = title_match.group(2) or '🟡'
                        current_card = {
                            'title': title, 
                            'priority': priority, 
                            'due': '', 
                            'context': '', 
                            'description': '',
                            '_from_column': current_column
                        }
                        # Add to appropriate data structure
                        if in_fasttrack:
                            self.kanban_fasttrack[current_column].append(current_card)
                        else:
                            self.kanban_data[current_column].append(current_card)
                
                # Parse card metadata
                elif current_card:
                    if line.startswith('**Due:**'):
                        due_match = re.search(r'\*\*Due:\*\*\s*([^|]+)', line)
                        if due_match:
                            current_card['due'] = due_match.group(1).strip()
                        ctx_match = re.search(r'\*\*Context:\*\*\s*([^*\n]+)', line)
                        if ctx_match:
                            current_card['context'] = ctx_match.group(1).strip()
                    elif line.strip() and not line.startswith('**') and not line.startswith('#') and not line.startswith('-') and not line.startswith('<!--'):
                        if not current_card['description']:
                            current_card['description'] = line.strip()
            
            # Sort cards by priority (🔴 > 🟡 > 🟢)
            priority_order = {'🔴': 0, '🟡': 1, '🟢': 2}
            for col in self.kanban_data:
                self.kanban_data[col].sort(key=lambda c: priority_order.get(c.get('priority', '🟡'), 1))
            for col in self.kanban_fasttrack:
                self.kanban_fasttrack[col].sort(key=lambda c: priority_order.get(c.get('priority', '🟡'), 1))
                
        except Exception as e:
            pass  # Silently fail, show empty board
                
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
        
        menu_w, menu_h = 500, 380
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
        max_visible = 9
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
                pygame.draw.rect(self.screen, C['bg_item_hover'], (menu_x + 10, item_y, menu_w - 20, 34), border_radius=6)
            
            prefix = "✓ " if is_current else "  "
            color = C['accent'] if is_current else (C['text_bright'] if is_sel else C['text'])
            
            display_name = item['name'][:35]
            surf = self.fonts['msg'].render(prefix + display_name, True, color)
            self.screen.blit(surf, (menu_x + 16, item_y + 7))
            item_y += 36
        
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
        elif self.mode == MODE_KANBAN:
            self.draw_kanban()
            
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
        elif event.key == pygame.K_F5:
            self.switch_mode(MODE_KANBAN)
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
        elif self.mode == MODE_KANBAN:
            self._handle_kanban_key(event)
                
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
                # Save to Todoist
                if self.task_edit_text.strip():
                    task = self.tasks[self.task_selected] if self.tasks and 0 <= self.task_selected < len(self.tasks) else None
                    if task and isinstance(task.get('id'), int):
                        # New local task - add to Todoist
                        self._todoist_add_task(self.task_edit_text.strip(), 'today')
                    else:
                        # Existing Todoist task - can't edit via CLI easily, just refresh
                        self._load_todoist_tasks()
                self.task_editing = False
            elif event.key == pygame.K_ESCAPE:
                # Cancel edit - if new task, remove from local list
                if self.tasks and 0 <= self.task_selected < len(self.tasks):
                    task = self.tasks[self.task_selected]
                    if isinstance(task.get('id'), int):  # Local temp task
                        self.tasks.pop(self.task_selected)
                        if self.task_selected >= len(self.tasks) and self.tasks:
                            self.task_selected = len(self.tasks) - 1
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
                # Build display list to find actual task
                display_list = []
                task_expanded = getattr(self, 'task_expanded', set())
                for task in self.tasks:
                    display_list.append({'task': task, 'indent': 0})
                    if task.get('subtasks') and task['id'] in task_expanded:
                        for sub in task.get('subtasks', []):
                            display_list.append({'task': sub, 'indent': 1})
                
                if display_list and 0 <= self.task_selected < len(display_list):
                    item = display_list[self.task_selected]
                    task = item['task']
                    # If task has subtasks, toggle expand
                    if task.get('subtasks') and item['indent'] == 0:
                        if task['id'] in self.task_expanded:
                            self.task_expanded.discard(task['id'])
                        else:
                            self.task_expanded.add(task['id'])
                    else:
                        # Edit mode
                        self.task_editing = True
                        self.task_edit_text = task.get('content', '')
                        self.task_edit_cursor = len(self.task_edit_text)
            elif event.key == pygame.K_n:
                self.add_task()
            elif event.key == pygame.K_SPACE:
                self.toggle_task_done()
            elif event.key == pygame.K_p:
                self.cycle_task_priority()
            elif event.key == pygame.K_r:
                # Manual refresh
                self._load_todoist_tasks()
            elif event.key == pygame.K_TAB:
                # Cycle filter through all 5 options
                filters = ['all', 'inbox', 'salon', 'today', 'overdue']
                current = getattr(self, 'task_filter', 'all')
                idx = filters.index(current) if current in filters else 0
                self.task_filter = filters[(idx + 1) % len(filters)]
                self.task_selected = 0
                self.task_scroll = 0
            # Number keys for project filter (WOW edition)
            elif event.key == pygame.K_1:
                self.task_filter = 'all'
                self.task_selected = 0
                self.task_scroll = 0
            elif event.key == pygame.K_2:
                self.task_filter = 'inbox'
                self.task_selected = 0
                self.task_scroll = 0
            elif event.key == pygame.K_3:
                self.task_filter = 'salon'
                self.task_selected = 0
                self.task_scroll = 0
            elif event.key == pygame.K_4:
                self.task_filter = 'today'
                self.task_selected = 0
                self.task_scroll = 0
            elif event.key == pygame.K_5:
                self.task_filter = 'overdue'
                self.task_selected = 0
                self.task_scroll = 0
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
        
        num_commands = len(self.get_commands())
        
        # Number keys 1-8 for quick activation
        number_keys = {
            pygame.K_1: 0, pygame.K_2: 1, pygame.K_3: 2, pygame.K_4: 3,
            pygame.K_5: 4, pygame.K_6: 5, pygame.K_7: 6, pygame.K_8: 7,
            pygame.K_KP1: 0, pygame.K_KP2: 1, pygame.K_KP3: 2, pygame.K_KP4: 3,
            pygame.K_KP5: 4, pygame.K_KP6: 5, pygame.K_KP7: 6, pygame.K_KP8: 7,
        }
        
        if event.key in number_keys:
            cmd_idx = number_keys[event.key]
            if cmd_idx < num_commands:
                self.command_selection = cmd_idx
                self.execute_command(cmd_idx)
            return
            
        # Arrow key navigation (2x4 grid)
        if event.key == pygame.K_UP:
            if self.command_selection >= 2:
                self.command_selection -= 2
        elif event.key == pygame.K_DOWN:
            if self.command_selection + 2 < num_commands:
                self.command_selection += 2
        elif event.key == pygame.K_LEFT:
            if self.command_selection % 2 > 0:
                self.command_selection -= 1
        elif event.key == pygame.K_RIGHT:
            if self.command_selection % 2 < 1 and self.command_selection < num_commands - 1:
                self.command_selection += 1
        elif event.key == pygame.K_RETURN:
            self.execute_command(self.command_selection)
    
    def _handle_kanban_key(self, event):
        """Handle keyboard input for kanban panel with fast track row"""
        all_columns = ['Not Started', 'Research', 'Active', 'Stuck', 'Review', 'Implement', 'Finished']
        current_col = all_columns[self.kanban_col] if self.kanban_col < len(all_columns) else all_columns[0]
        current_cards = self.kanban_data.get(current_col, [])
        
        # Initialize state
        if not hasattr(self, 'kanban_holding'):
            self.kanban_holding = None
            self.kanban_holding_from = None
        if not hasattr(self, 'kanban_in_fasttrack'):
            self.kanban_in_fasttrack = False
            self.kanban_ft_card = 0
        
        # Get fast track cards from parsed Fast Track section
        ft_cards = []
        ft_data = getattr(self, 'kanban_fasttrack', {})
        for col_name in all_columns:
            for card in ft_data.get(col_name, []):
                ft_cards.append(card)
        
        # Close detail popup
        if hasattr(self, 'kanban_detail') and self.kanban_detail:
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                self.kanban_detail = False
            return
        
        # Space = pick up or place card
        if event.key == pygame.K_SPACE:
            if self.kanban_holding:
                self._place_kanban_card()
            else:
                if self.kanban_in_fasttrack:
                    # Pick up from fast track
                    if ft_cards and self.kanban_ft_card < len(ft_cards):
                        self.kanban_holding = ft_cards[self.kanban_ft_card]
                        self.kanban_holding_from = -1  # Special: from fast track
                else:
                    if current_cards and self.kanban_card < len(current_cards):
                        self.kanban_holding = current_cards[self.kanban_card]
                        self.kanban_holding_from = self.kanban_col
            return
        
        # LEFT/RIGHT - move between columns (works same in FT or main)
        if event.key == pygame.K_LEFT:
            if self.kanban_in_fasttrack and not self.kanban_holding:
                if self.kanban_ft_card > 0:
                    self.kanban_ft_card -= 1
            else:
                if self.kanban_col > 0:
                    self.kanban_col -= 1
                    if not self.kanban_holding:
                        self.kanban_card = 0
                        self.kanban_scroll[self.kanban_col] = 0
        
        elif event.key == pygame.K_RIGHT:
            if self.kanban_in_fasttrack and not self.kanban_holding:
                if ft_cards and self.kanban_ft_card < len(ft_cards) - 1:
                    self.kanban_ft_card += 1
            else:
                if self.kanban_col < 6:
                    self.kanban_col += 1
                    if not self.kanban_holding:
                        self.kanban_card = 0
                        self.kanban_scroll[self.kanban_col] = 0
        
        # UP - go to fast track row (or scroll up in column)
        elif event.key == pygame.K_UP:
            if self.kanban_in_fasttrack:
                pass  # Already at top
            elif self.kanban_holding:
                # Move to fast track while holding
                self.kanban_in_fasttrack = True
            elif self.kanban_card > 0:
                self.kanban_card -= 1
                scroll = self.kanban_scroll.get(self.kanban_col, 0)
                if self.kanban_card < scroll:
                    self.kanban_scroll[self.kanban_col] = self.kanban_card
            elif self.kanban_card == 0 and not self.kanban_holding:
                # At top of column - move to fast track row
                self.kanban_in_fasttrack = True
                self.kanban_ft_card = 0
        
        # DOWN - go to columns (or scroll down)
        elif event.key == pygame.K_DOWN:
            if self.kanban_in_fasttrack:
                # Exit fast track to columns
                self.kanban_in_fasttrack = False
                self.kanban_card = 0
            elif not self.kanban_holding and current_cards:
                max_idx = len(current_cards) - 1
                if self.kanban_card < max_idx:
                    self.kanban_card += 1
                    scroll = self.kanban_scroll.get(self.kanban_col, 0)
                    max_visible = 6
                    if self.kanban_card > scroll + max_visible - 1:
                        self.kanban_scroll[self.kanban_col] = self.kanban_card - max_visible + 1
        
        # ENTER - show detail
        elif event.key == pygame.K_RETURN:
            if not self.kanban_holding:
                if self.kanban_in_fasttrack and ft_cards:
                    self.kanban_detail = True
                elif current_cards:
                    self.kanban_detail = True
        
        # Tab = switch boards (salon ↔ personal only, fast track is always visible)
        if event.key == pygame.K_TAB:
            if not self.kanban_holding:
                self.kanban_board = 'personal' if self.kanban_board == 'salon' else 'salon'
                self._load_kanban_data()
                self.kanban_col = 0
                self.kanban_card = 0
                self.kanban_scroll = {}
                self.kanban_in_fasttrack = False
        
        # R = refresh
        elif event.key == pygame.K_r:
            if not self.kanban_holding:
                self._load_kanban_data()
                self.kanban_last_refresh = time.time()
        
        # Escape = cancel hold or go home
        elif event.key == pygame.K_ESCAPE:
            if self.kanban_holding:
                self.kanban_holding = None
                self.kanban_holding_from = None
            else:
                self.switch_mode(MODE_DASHBOARD)
    
    def _place_kanban_card(self):
        """
        Place held card. Handles 4 scenarios:
        1. Main → Main (different column)
        2. Fast Track → Fast Track (different column)  
        3. Main → Fast Track
        4. Fast Track → Main
        """
        import re
        all_columns = ['Not Started', 'Research', 'Active', 'Stuck', 'Review', 'Implement', 'Finished']
        
        if not self.kanban_holding:
            return
        
        self.kanban_sync_status = 'syncing'
        self.kanban_sync_time = time.time()
        
        card = self.kanban_holding
        card_title = card.get('title', '')
        
        # Where is it going?
        to_fasttrack = getattr(self, 'kanban_in_fasttrack', False)
        dst_col_name = all_columns[self.kanban_col]
        
        # Where did it come from?
        from_fasttrack = (self.kanban_holding_from == -1)
        if from_fasttrack:
            src_col_name = card.get('_from_column', 'Active')
        else:
            src_col_name = all_columns[self.kanban_holding_from]
        
        # Build target column header name
        if to_fasttrack:
            target_header = f'{dst_col_name} (Urgent)'
        else:
            target_header = dst_col_name
        
        # Update markdown file
        board_name = getattr(self, 'kanban_board', 'salon')
        kanban_file = Path.home() / f'.openclaw/workspace/work/kanban/{board_name}.md'
        
        try:
            content = kanban_file.read_text()
            
            # Find the card block
            pattern = rf'## {re.escape(card_title)}.*?(?=\n## |\n### |\Z)'
            match = re.search(pattern, content, re.DOTALL)
            
            if not match:
                self.kanban_sync_status = 'error'
                self._clear_holding()
                return
            
            card_block = match.group(0).strip()
            
            # Remove card from current location
            content = content.replace(match.group(0), '', 1)
            
            # Clean up empty lines and duplicate separators
            content = re.sub(r'\n{3,}', '\n\n', content)
            content = re.sub(r'(---\n)+---', '---', content)
            
            # Find target column and insert card
            # Match "### Column Name" followed by optional comment line
            target_pattern = rf'(### {re.escape(target_header)}\n(?:<!--[^>]*-->\n)?)'
            target_match = re.search(target_pattern, content)
            
            if target_match:
                insert_at = target_match.end()
                new_content = (
                    content[:insert_at] + 
                    '\n' + card_block + '\n\n---\n\n' + 
                    content[insert_at:].lstrip('\n')
                )
                # Final cleanup
                new_content = re.sub(r'\n{3,}', '\n\n', new_content)
                new_content = re.sub(r'(---\n)+---', '---', new_content)
                
                kanban_file.write_text(new_content)
                self.kanban_sync_status = 'live'
                
                # Reload data to reflect changes
                self._load_kanban_data()
            else:
                self.kanban_sync_status = 'error'
                
        except Exception as e:
            self.kanban_sync_status = 'error'
        
        self._clear_holding()
    
    def _clear_holding(self):
        """Clear the card holding state"""
        self.kanban_holding = None
        self.kanban_holding_from = None
        self.kanban_card = 0
            
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
