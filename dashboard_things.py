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
        ver_surf = self.fonts['status'].render("THINGS", True, (120, 200, 160))
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
        """Style 3: Things Minimal - Beautiful, one-at-a-time focus"""
        import math
        
        # Initialize state
        if not hasattr(self, 'todoist_last_sync'):
            self.todoist_last_sync = 0
            self.todoist_sync_status = 'live'
        if not hasattr(self, 'task_filter'):
            self.task_filter = 'all'
        
        # Auto-refresh every 30 seconds
        if time.time() - self.todoist_last_sync > 30:
            self._load_todoist_tasks()
        
        # Filter tasks
        all_tasks = self.tasks
        if self.task_filter == 'today':
            filtered = [t for t in all_tasks if 'today' in t.get('due', '').lower()]
        elif self.task_filter == 'overdue':
            filtered = [t for t in all_tasks if any(x in t.get('due', '').lower() for x in ['overdue', 'yesterday'])]
        else:
            filtered = all_tasks
        
        total = len(all_tasks)
        
        # Soft dark background
        self.screen.fill((25, 26, 32))
        
        # ═══════════════════════════════════════════════════════════════
        # HEADER - Minimal with project name
        # ═══════════════════════════════════════════════════════════════
        header_y = 50
        
        # Project name
        project_name = "Inbox" if self.task_filter == 'all' else self.task_filter.title()
        title_surf = self.fonts['menu_title'].render(project_name, True, (220, 225, 235))
        self.screen.blit(title_surf, (30, header_y))
        
        # Task count
        count_text = f"{len(filtered)} tasks"
        count_surf = self.fonts['status'].render(count_text, True, (100, 105, 125))
        self.screen.blit(count_surf, (30 + title_surf.get_width() + 15, header_y + 8))
        
        # Sync dot
        sync_status = getattr(self, 'todoist_sync_status', 'live')
        if sync_status == 'live':
            pygame.draw.circle(self.screen, (80, 180, 120), (SCREEN_WIDTH - 25, header_y + 12), 6)
        elif sync_status == 'syncing':
            angle = time.time() * 4
            x = SCREEN_WIDTH - 25 + int(3 * math.cos(angle))
            y = header_y + 12 + int(3 * math.sin(angle))
            pygame.draw.circle(self.screen, (200, 180, 80), (x, y), 6)
        else:
            pygame.draw.circle(self.screen, (200, 80, 80), (SCREEN_WIDTH - 25, header_y + 12), 6)
        
        # ═══════════════════════════════════════════════════════════════
        # TASK LIST - Cards with generous spacing
        # ═══════════════════════════════════════════════════════════════
        list_y = header_y + 50
        card_h = 72
        card_gap = 12
        max_visible = 4
        
        # Build display list
        if not hasattr(self, 'task_expanded'):
            self.task_expanded = set()
        
        display_list = []
        for task in filtered:
            display_list.append({'task': task, 'indent': 0})
            subtasks = task.get('subtasks', [])
            if subtasks and task['id'] in self.task_expanded:
                for sub in subtasks:
                    display_list.append({'task': sub, 'indent': 1})
        
        if not display_list:
            # Beautiful empty state
            empty_y = list_y + 60
            
            # Soft card
            pygame.draw.rect(self.screen, (35, 37, 45), (60, empty_y, SCREEN_WIDTH - 120, 140), border_radius=24)
            
            # Checkmark
            check_x = SCREEN_WIDTH // 2
            check_y = empty_y + 50
            pygame.draw.circle(self.screen, (80, 180, 120), (check_x, check_y), 28, width=3)
            pygame.draw.line(self.screen, (80, 180, 120), (check_x - 12, check_y + 2), (check_x - 2, check_y + 12), 4)
            pygame.draw.line(self.screen, (80, 180, 120), (check_x - 2, check_y + 12), (check_x + 14, check_y - 10), 4)
            
            msg_surf = self.fonts['title'].render("All clear", True, (180, 185, 200))
            self.screen.blit(msg_surf, ((SCREEN_WIDTH - msg_surf.get_width())//2, empty_y + 95))
        else:
            # Scroll handling  
            if self.task_selected >= len(display_list):
                self.task_selected = max(0, len(display_list) - 1)
            if self.task_selected < self.task_scroll:
                self.task_scroll = self.task_selected
            elif self.task_selected >= self.task_scroll + max_visible:
                self.task_scroll = self.task_selected - max_visible + 1
            
            visible = display_list[self.task_scroll:self.task_scroll + max_visible]
            card_y = list_y
            
            for i, item in enumerate(visible):
                task = item['task']
                indent = item['indent']
                actual_idx = self.task_scroll + i
                is_selected = actual_idx == self.task_selected
                priority = task.get('priority', 1)
                due = task.get('due', '')
                content = task.get('content', '') or '(empty)'
                description = task.get('description', '')
                subtasks = task.get('subtasks', [])
                is_recurring = task.get('isRecurring', False)
                note_count = task.get('noteCount', 0)
                
                # Card dimensions
                indent_px = indent * 25
                card_x = 25 + indent_px
                card_w = SCREEN_WIDTH - 50 - indent_px
                
                # Card background with soft shadow
                if is_selected:
                    # Expanded card for selected
                    exp_h = card_h + (40 if description else 0) + (25 if subtasks else 0)
                    pygame.draw.rect(self.screen, (50, 52, 62), (card_x, card_y, card_w, exp_h), border_radius=18)
                    # Subtle glow
                    pygame.draw.rect(self.screen, (100, 140, 220), (card_x, card_y, card_w, exp_h), width=2, border_radius=18)
                else:
                    pygame.draw.rect(self.screen, (38, 40, 50), (card_x, card_y, card_w, card_h), border_radius=16)
                
                # Checkbox - beautiful ring
                cb_x = card_x + 32
                cb_y = card_y + 28
                cb_r = 14 if indent == 0 else 11
                
                p_colors = {4: (235, 85, 85), 3: (235, 175, 55), 2: (100, 160, 235), 1: (90, 95, 115)}
                p_color = p_colors.get(priority, p_colors[1])
                
                pygame.draw.circle(self.screen, p_color, (cb_x, cb_y), cb_r, width=2)
                if priority >= 3:
                    pygame.draw.circle(self.screen, p_color, (cb_x, cb_y), cb_r - 5)
                
                # Task text
                text_x = cb_x + cb_r + 18
                text_surf = self.fonts['title'].render(content[:35] + ('…' if len(content) > 35 else ''), True, (230, 235, 245))
                self.screen.blit(text_surf, (text_x, card_y + 14))
                
                # Metadata line
                meta_y = card_y + 42
                meta_x = text_x
                
                # Due
                if due:
                    due_color = (220, 90, 90) if 'overdue' in due.lower() else (140, 145, 165)
                    due_surf = self.fonts['status'].render(due[:12], True, due_color)
                    self.screen.blit(due_surf, (meta_x, meta_y))
                    meta_x += due_surf.get_width() + 15
                
                # Recurring
                if is_recurring:
                    rec_surf = self.fonts['status'].render("↻ Repeats", True, (120, 160, 220))
                    self.screen.blit(rec_surf, (meta_x, meta_y))
                    meta_x += rec_surf.get_width() + 15
                
                # Comments
                if note_count > 0:
                    note_surf = self.fonts['status'].render(f"💬 {note_count}", True, (140, 145, 165))
                    self.screen.blit(note_surf, (meta_x, meta_y))
                
                # Description preview (if selected and has description)
                if is_selected and description:
                    desc_y = card_y + 62
                    desc_text = description[:60] + ('…' if len(description) > 60 else '')
                    desc_surf = self.fonts['status'].render(desc_text, True, (120, 125, 145))
                    self.screen.blit(desc_surf, (text_x, desc_y))
                
                # Subtask count (if has subtasks)
                if subtasks and indent == 0:
                    sub_y = card_y + card_h - 8 if not (is_selected and description) else card_y + 85
                    if is_selected:
                        sub_text = f"▸ {len(subtasks)} subtasks"
                        sub_surf = self.fonts['status'].render(sub_text, True, (100, 140, 200))
                        self.screen.blit(sub_surf, (text_x, sub_y))
                
                # Calculate actual card height for next position
                if is_selected:
                    actual_h = card_h + (40 if description else 0) + (25 if subtasks else 0)
                else:
                    actual_h = card_h
                
                card_y += actual_h + card_gap
            
            # Scroll hints
            if self.task_scroll > 0:
                hint_surf = self.fonts['status'].render(f"↑ {self.task_scroll} above", True, (90, 95, 115))
                self.screen.blit(hint_surf, (SCREEN_WIDTH//2 - hint_surf.get_width()//2, list_y - 20))
            
            remaining = len(display_list) - self.task_scroll - max_visible
            if remaining > 0:
                hint_surf = self.fonts['status'].render(f"↓ {remaining} below", True, (90, 95, 115))
                self.screen.blit(hint_surf, (SCREEN_WIDTH//2 - hint_surf.get_width()//2, SCREEN_HEIGHT - 50))
        
        # ═══════════════════════════════════════════════════════════════
        # NAVIGATION BAR at bottom
        # ═══════════════════════════════════════════════════════════════
        nav_y = SCREEN_HEIGHT - 28
        
        # Project switcher hint
        if self.task_filter == 'all':
            left_hint = "← Inbox"
            right_hint = "Salon →"
        else:
            left_hint = "← All"
            right_hint = ""
        
        left_surf = self.fonts['status'].render(left_hint, True, (100, 105, 125))
        self.screen.blit(left_surf, (25, nav_y))
        
        if right_hint:
            right_surf = self.fonts['status'].render(right_hint, True, (100, 105, 125))
            self.screen.blit(right_surf, (SCREEN_WIDTH - right_surf.get_width() - 25, nav_y))


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
        """Draw native Kanban board - 2-row layout with auto-refresh"""
        
        # Auto-refresh every 5 seconds
        now = time.time()
        if not hasattr(self, 'kanban_last_refresh'):
            self.kanban_last_refresh = 0
        if now - self.kanban_last_refresh > 5:
            self._load_kanban_data()
            self.kanban_last_refresh = now
        
        # Initialize state
        if not hasattr(self, 'kanban_col'):
            self.kanban_col = 0
            self.kanban_card = 0
            self.kanban_board = 'salon'
            self.kanban_detail = False
            self.kanban_scroll = {}  # Scroll offset per column
            self.kanban_sync_status = 'live'  # live, syncing, error
            self.kanban_sync_time = 0
        
        # 2-row layout: top row and bottom row
        top_cols = ['Not Started', 'Research', 'Active', 'Stuck']
        bottom_cols = ['Review', 'Implement', 'Finished']
        all_columns = top_cols + bottom_cols
        
        col_colors = {
            'Not Started': (100, 100, 130), 'Research': (70, 130, 190), 
            'Active': (70, 170, 90), 'Stuck': (190, 70, 70),
            'Review': (190, 150, 50), 'Implement': (130, 90, 170), 'Finished': (50, 150, 90)
        }
        col_icons = {'Not Started': '📋', 'Research': '🔍', 'Active': '⚡', 'Stuck': '🚧', 
                     'Review': '👀', 'Implement': '🚀', 'Finished': '✅'}
        
        # Header with board selector (3 tabs)
        header_y = 42
        salon_color = C['accent'] if self.kanban_board == 'salon' else C['text_dim']
        personal_color = C['accent'] if self.kanban_board == 'personal' else C['text_dim']
        fast_color = C['warning'] if self.kanban_board == 'fasttrack' else C['text_dim']
        salon_surf = self.fonts['msg'].render("🏪 Salon", True, salon_color)
        personal_surf = self.fonts['msg'].render("👤 Personal", True, personal_color)
        fast_surf = self.fonts['msg'].render("🔥 Fast", True, fast_color)
        self.screen.blit(salon_surf, (15, header_y))
        self.screen.blit(personal_surf, (115, header_y))
        self.screen.blit(fast_surf, (230, header_y))
        
        # Sync status indicator
        sync_status = getattr(self, 'kanban_sync_status', 'live')
        sync_time = getattr(self, 'kanban_sync_time', 0)
        
        # Auto-clear syncing status after 1 second
        if sync_status == 'syncing' and time.time() - sync_time > 1:
            self.kanban_sync_status = 'live'
            sync_status = 'live'
        
        if sync_status == 'live':
            sync_color = C['success']
            sync_text = "● Live"
        elif sync_status == 'syncing':
            sync_color = C['warning']
            sync_text = "◐ Sync..."
        else:  # error
            sync_color = C['error']
            sync_text = "✗ Error"
        
        sync_surf = self.fonts['status'].render(sync_text, True, sync_color)
        self.screen.blit(sync_surf, (SCREEN_WIDTH - 65, header_y + 4))
        
        # Layout dimensions
        row_h = 185
        top_y = header_y + 28
        bottom_y = top_y + row_h + 8
        
        # Draw top row (4 columns)
        top_col_w = (SCREEN_WIDTH - 25) // 4
        for i, col_name in enumerate(top_cols):
            x = 10 + i * top_col_w
            col_idx = i
            self._draw_kanban_column(x, top_y, top_col_w - 5, row_h, col_name, col_idx, col_colors, col_icons)
        
        # Draw bottom row (3 columns, centered)
        bottom_col_w = (SCREEN_WIDTH - 40) // 3
        bottom_start_x = 20
        for i, col_name in enumerate(bottom_cols):
            x = bottom_start_x + i * bottom_col_w
            col_idx = len(top_cols) + i
            self._draw_kanban_column(x, bottom_y, bottom_col_w - 8, row_h, col_name, col_idx, col_colors, col_icons)
        
        # Detail popup
        if self.kanban_detail:
            self._draw_kanban_detail()
        
        # Floating card when holding
        if hasattr(self, 'kanban_holding') and self.kanban_holding:
            self._draw_floating_card(top_cols, bottom_cols, top_col_w, bottom_col_w, top_y, bottom_y, header_y, bottom_start_x)
            
            # Footer with holding hint
            hint = "←→:Move card | Space:Place | Esc:Cancel"
            hint_surf = self.fonts['msg'].render(hint, True, C['warning'])
            self.screen.blit(hint_surf, ((SCREEN_WIDTH - hint_surf.get_width()) // 2, SCREEN_HEIGHT - 18))
        else:
            # Normal footer
            hint = "←→:Columns | ↑↓:Cards | Space:Pick | Enter:Detail | Tab:Board"
            hint_surf = self.fonts['status'].render(hint, True, C['text_muted'])
            self.screen.blit(hint_surf, ((SCREEN_WIDTH - hint_surf.get_width()) // 2, SCREEN_HEIGHT - 18))
    
    def _draw_floating_card(self, top_cols, bottom_cols, top_col_w, bottom_col_w, top_y, bottom_y, header_y, bottom_start_x):
        """Draw the card being held as floating above the board"""
        card = self.kanban_holding
        if not card:
            return
        
        # Calculate position based on current column
        if self.kanban_col < 4:
            # Top row
            x = 10 + self.kanban_col * top_col_w + top_col_w // 2 - 80
            y = top_y + 50
        else:
            # Bottom row
            col_in_row = self.kanban_col - 4
            x = bottom_start_x + col_in_row * bottom_col_w + bottom_col_w // 2 - 80
            y = bottom_y + 50
        
        # Floating card dimensions
        card_w = 160
        card_h = 70
        
        # Shadow
        shadow_offset = 6
        pygame.draw.rect(self.screen, (0, 0, 0), (x + shadow_offset, y + shadow_offset, card_w, card_h), border_radius=10)
        
        # Card background with glow
        glow_color = C['warning']
        pygame.draw.rect(self.screen, glow_color, (x - 3, y - 3, card_w + 6, card_h + 6), border_radius=12)
        pygame.draw.rect(self.screen, C['bg_item_hover'], (x, y, card_w, card_h), border_radius=10)
        
        # Priority bar
        p_color = {'🔴': C['error'], '🟡': C['warning'], '🟢': C['success']}.get(card.get('priority', '🟡'), C['warning'])
        pygame.draw.rect(self.screen, p_color, (x, y, 6, card_h), border_radius=4)
        
        # Title
        title = card.get('title', 'Untitled')
        if len(title) > 18:
            title = title[:17] + "…"
        title_surf = self.fonts['msg'].render(title, True, C['text_bright'])
        self.screen.blit(title_surf, (x + 14, y + 12))
        
        # Due date
        due = card.get('due', '')
        if due and due != 'TBD':
            due_surf = self.fonts['status'].render(f"📅 {due[:12]}", True, C['text_dim'])
            self.screen.blit(due_surf, (x + 14, y + 40))
        
        # "Drop here" indicator on target column
        all_columns = ['Not Started', 'Research', 'Active', 'Stuck', 'Review', 'Implement', 'Finished']
        target_col = all_columns[self.kanban_col]
        
        # Pulsing border on target column (using time for animation)
        pulse = int((time.time() * 4) % 2)
        if pulse:
            if self.kanban_col < 4:
                tx = 10 + self.kanban_col * top_col_w
                pygame.draw.rect(self.screen, C['warning'], (tx - 2, top_y - 2, top_col_w - 1, 190), width=3, border_radius=10)
            else:
                col_in_row = self.kanban_col - 4
                tx = bottom_start_x + col_in_row * bottom_col_w
                pygame.draw.rect(self.screen, C['warning'], (tx - 2, bottom_y - 2, bottom_col_w - 4, 190), width=3, border_radius=10)
    
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
        
        board_name = getattr(self, 'kanban_board', 'salon')
        
        # Fast Track: collect 🔥 items from both boards
        if board_name == 'fasttrack':
            self._load_fasttrack_data()
            return
        
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
        """Parse a single kanban file"""
        import re
        
        try:
            content = kanban_file.read_text()
            current_column = None
            current_card = None
            in_description = False
            
            for line in content.split('\n'):
                # Detect column headers (### Column Name)
                if line.startswith('### ') and not line.startswith('### Idea') and not line.startswith('### Status') and not line.startswith('### Check') and not line.startswith('### Notes'):
                    col_name = line[4:].strip()
                    # Remove (Urgent) suffix
                    col_name = col_name.replace(' (Urgent)', '')
                    # Match to known columns
                    for known in self.kanban_data.keys():
                        if known.lower() in col_name.lower():
                            current_column = known
                            break
                    current_card = None
                    in_description = False
                
                # Detect card titles (## Title 🔴/🟡/🟢)
                elif line.startswith('## ') and current_column and not line.startswith('## Main') and not line.startswith('## 💡') and not line.startswith('## 🔥') and not line.startswith('## Archive'):
                    title_match = re.match(r'## (.+?)\s*(🔴|🟡|🟢)?$', line)
                    if title_match:
                        title = title_match.group(1).strip()
                        priority = title_match.group(2) or '🟡'
                        current_card = {'title': title, 'priority': priority, 'due': '', 'context': '', 'description': ''}
                        self.kanban_data[current_column].append(current_card)
                        in_description = False
                
                # Parse card metadata
                elif current_card:
                    if line.startswith('**Due:**'):
                        due_match = re.search(r'\*\*Due:\*\*\s*([^|]+)', line)
                        if due_match:
                            current_card['due'] = due_match.group(1).strip()
                        ctx_match = re.search(r'\*\*Context:\*\*\s*([^*\n]+)', line)
                        if ctx_match:
                            current_card['context'] = ctx_match.group(1).strip()
                    # Capture description (line after metadata, before ### Status)
                    elif line.strip() and not line.startswith('**') and not line.startswith('#') and not line.startswith('-') and not line.startswith('<!--'):
                        if not current_card['description']:
                            current_card['description'] = line.strip()
            
            # Sort cards by priority (🔴 > 🟡 > 🟢)
            priority_order = {'🔴': 0, '🟡': 1, '🟢': 2}
            for col in self.kanban_data:
                self.kanban_data[col].sort(key=lambda c: priority_order.get(c.get('priority', '🟡'), 1))
                
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
                # Cycle filter
                filters = ['all', 'today', 'overdue']
                current = getattr(self, 'task_filter', 'all')
                idx = filters.index(current) if current in filters else 0
                self.task_filter = filters[(idx + 1) % len(filters)]
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
        """Handle keyboard input for kanban panel"""
        all_columns = ['Not Started', 'Research', 'Active', 'Stuck', 'Review', 'Implement', 'Finished']
        current_col = all_columns[self.kanban_col] if self.kanban_col < len(all_columns) else all_columns[0]
        current_cards = self.kanban_data.get(current_col, [])
        
        # Initialize holding state
        if not hasattr(self, 'kanban_holding'):
            self.kanban_holding = None  # Card being held
            self.kanban_holding_from = None  # Source column index
        
        # Close detail popup
        if hasattr(self, 'kanban_detail') and self.kanban_detail:
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                self.kanban_detail = False
            return
        
        # Space = pick up or place card
        if event.key == pygame.K_SPACE:
            if self.kanban_holding:
                # Place the card
                self._place_kanban_card()
            else:
                # Pick up current card
                if current_cards and self.kanban_card < len(current_cards):
                    self.kanban_holding = current_cards[self.kanban_card]
                    self.kanban_holding_from = self.kanban_col
            return
        
        # Left/Right = move between columns 1-7
        if event.key == pygame.K_LEFT:
            if self.kanban_col > 0:
                self.kanban_col -= 1
                if not self.kanban_holding:
                    self.kanban_card = 0
                    self.kanban_scroll[self.kanban_col] = 0
        elif event.key == pygame.K_RIGHT:
            if self.kanban_col < 6:
                self.kanban_col += 1
                if not self.kanban_holding:
                    self.kanban_card = 0
                    self.kanban_scroll[self.kanban_col] = 0
        
        # Up/Down = scroll cards in current column (only if not holding)
        elif event.key == pygame.K_UP:
            if not self.kanban_holding and current_cards:
                if self.kanban_card > 0:
                    self.kanban_card -= 1
                    # Scroll up if selection goes above visible area
                    scroll = self.kanban_scroll.get(self.kanban_col, 0)
                    if self.kanban_card < scroll:
                        self.kanban_scroll[self.kanban_col] = self.kanban_card
        elif event.key == pygame.K_DOWN:
            if not self.kanban_holding and current_cards:
                max_idx = len(current_cards) - 1
                if self.kanban_card < max_idx:
                    self.kanban_card += 1
                    # Scroll down if selection goes below visible area
                    # Row height ~180, body ~146, available ~138, card+space=52 → 2 visible
                    scroll = self.kanban_scroll.get(self.kanban_col, 0)
                    max_visible = 2
                    if self.kanban_card > scroll + max_visible - 1:
                        self.kanban_scroll[self.kanban_col] = self.kanban_card - max_visible + 1
        
        # Enter = detail popup
        elif event.key == pygame.K_RETURN:
            if not self.kanban_holding and current_cards:
                self.kanban_detail = True
        
        # Tab = switch boards (salon → personal → fasttrack → salon)
        elif event.key == pygame.K_TAB:
            if not self.kanban_holding:
                boards = ['salon', 'personal', 'fasttrack']
                idx = boards.index(self.kanban_board) if self.kanban_board in boards else 0
                self.kanban_board = boards[(idx + 1) % 3]
                self._load_kanban_data()
                self.kanban_col = 0
                self.kanban_card = 0
                self.kanban_scroll = {}
        
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
        """Place the held card in current column"""
        import re
        all_columns = ['Not Started', 'Research', 'Active', 'Stuck', 'Review', 'Implement', 'Finished']
        
        if not self.kanban_holding:
            return
        
        # Show syncing status
        self.kanban_sync_status = 'syncing'
        self.kanban_sync_time = time.time()
        
        src_col = all_columns[self.kanban_holding_from]
        dst_col = all_columns[self.kanban_col]
        card = self.kanban_holding
        
        # Update in-memory
        if card in self.kanban_data[src_col]:
            self.kanban_data[src_col].remove(card)
        self.kanban_data[dst_col].insert(0, card)
        
        # Update file
        board_name = getattr(self, 'kanban_board', 'salon')
        kanban_file = Path.home() / f'.openclaw/workspace/work/kanban/{board_name}.md'
        
        try:
            content = kanban_file.read_text()
            card_title = card.get('title', '')
            
            # Find card block
            pattern = rf'(## {re.escape(card_title)}.*?(?=\n## |\n### |\Z))'
            match = re.search(pattern, content, re.DOTALL)
            
            if match:
                card_block = match.group(1)
                content = content.replace(card_block, '', 1)
                
                # Find target column
                dst_pattern = rf'(### {dst_col}.*?\n(?:<!--.*?-->\n)?)'
                dst_match = re.search(dst_pattern, content)
                if dst_match:
                    insert_pos = dst_match.end()
                    content = content[:insert_pos] + '\n' + card_block.strip() + '\n\n---\n' + content[insert_pos:]
                    kanban_file.write_text(content)
                    self.kanban_sync_status = 'live'
                else:
                    self.kanban_sync_status = 'error'
            else:
                self.kanban_sync_status = 'error'
        except Exception as e:
            self.kanban_sync_status = 'error'
        
        # Clear holding state
        self.kanban_holding = None
        self.kanban_holding_from = None
        self.kanban_card = 0
    
    def _move_kanban_card(self, target_col_idx):
        """Move current card to target column and save to file"""
        import re
        all_columns = ['Not Started', 'Research', 'Active', 'Stuck', 'Review', 'Implement', 'Finished']
        src_col = all_columns[self.kanban_col]
        dst_col = all_columns[target_col_idx]
        
        cards = self.kanban_data.get(src_col, [])
        if not cards or self.kanban_card >= len(cards):
            return
        
        card = cards[self.kanban_card]
        
        # Update in-memory data
        self.kanban_data[src_col].remove(card)
        self.kanban_data[dst_col].insert(0, card)
        
        # Update the markdown file
        board_name = getattr(self, 'kanban_board', 'salon')
        kanban_file = Path.home() / f'.openclaw/workspace/work/kanban/{board_name}.md'
        
        try:
            content = kanban_file.read_text()
            card_title = card.get('title', '')
            
            # Find the card block (## Title ... ---)
            pattern = rf'(## {re.escape(card_title)}.*?(?=\n## |\n### |\Z))'
            match = re.search(pattern, content, re.DOTALL)
            
            if match:
                card_block = match.group(1)
                # Remove from current location
                content = content.replace(card_block, '', 1)
                
                # Find target column and insert
                dst_pattern = rf'(### {dst_col}.*?\n(?:<!--.*?-->\n)?)'
                dst_match = re.search(dst_pattern, content)
                if dst_match:
                    insert_pos = dst_match.end()
                    content = content[:insert_pos] + '\n' + card_block.strip() + '\n\n---\n' + content[insert_pos:]
                    kanban_file.write_text(content)
        except Exception as e:
            pass  # Silent fail, in-memory state still updated
        
        # Move selection to new column
        self.kanban_col = target_col_idx
        self.kanban_card = 0
        self.kanban_moving = False
            
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
