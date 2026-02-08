#!/usr/bin/env python3
"""
Pi 400 Dashboard v9 - Full Featured Edition
For 3.5" Waveshare TFT (480x320)

Features:
- Session management (list/switch/new/end)
- Menu overlay with settings
- Adjustable text size
- Slash command support
- Persistent settings
"""

import pygame
import sys
import os
import json
import time
import threading
import requests
from datetime import datetime
from collections import deque
from pathlib import Path

# Configuration
SCREEN_WIDTH = 480
SCREEN_HEIGHT = 320
GATEWAY_URL = "http://127.0.0.1:18789"
GATEWAY_TOKEN = "8ee708fa05cfe60da1182554737e8f556ff0333784479bf9"
AGENT_ID = "main"
SETTINGS_FILE = Path.home() / '.openclaw' / 'workspace' / 'dashboard' / 'settings.json'

# Color palette
C = {
    'bg': (18, 18, 22),
    'bg_header': (28, 28, 35),
    'bg_input': (35, 35, 45),
    'bg_overlay': (25, 25, 32),
    'bg_item': (40, 42, 52),
    'bg_item_hover': (55, 58, 72),
    'bg_button': (60, 100, 180),
    'bg_button_danger': (160, 60, 60),
    'bg_button_hover': (80, 120, 200),
    
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

# Text size presets
TEXT_SIZES = {
    'small': {'msg': 12, 'input': 13, 'title': 16, 'status': 10, 'time': 10, 'line_height': 15},
    'medium': {'msg': 14, 'input': 15, 'title': 18, 'status': 12, 'time': 11, 'line_height': 18},
    'large': {'msg': 17, 'input': 18, 'title': 20, 'status': 14, 'time': 13, 'line_height': 22},
}


class Message:
    def __init__(self, text, role='user', timestamp=None):
        self.text = text
        self.role = role
        self.timestamp = timestamp or datetime.now()


class Settings:
    def __init__(self):
        self.text_size = 'medium'
        self.session_key = 'pi-display'
        self.load()
    
    def load(self):
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE) as f:
                    data = json.load(f)
                    self.text_size = data.get('text_size', 'medium')
                    self.session_key = data.get('session_key', 'pi-display')
        except:
            pass
    
    def save(self):
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SETTINGS_FILE, 'w') as f:
                json.dump({
                    'text_size': self.text_size,
                    'session_key': self.session_key
                }, f)
        except:
            pass


class ChatApp:
    def __init__(self):
        pygame.init()
        
        self.screen = pygame.display.set_mode(
            (SCREEN_WIDTH, SCREEN_HEIGHT),
            pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF
        )
        pygame.display.set_caption('OpenClaw')
        pygame.mouse.set_visible(False)
        
        # Settings
        self.settings = Settings()
        self.rebuild_fonts()
        
        # State
        self.messages = deque(maxlen=100)
        self.conversation = []
        self.input_text = ""
        self.input_cursor = 0
        self.scroll_offset = 0
        self.status = "ready"
        self.waiting = False
        self.send_thread = None
        
        # Menu state
        self.menu_open = False
        self.menu_mode = 'main'  # 'main', 'sessions', 'settings'
        self.menu_selection = 0
        self.sessions_list = []
        self.sessions_loading = False
        
        # Available sessions cache
        self.available_sessions = []
        
        self.clock = pygame.time.Clock()
        self.messages.append(Message(f"Session: {self.settings.session_key}", 'system'))
        
    def rebuild_fonts(self):
        sizes = TEXT_SIZES[self.settings.text_size]
        self.fonts = {
            'title': pygame.font.SysFont('liberationsans', sizes['title'], bold=True),
            'msg': pygame.font.SysFont('liberationsans', sizes['msg']),
            'input': pygame.font.SysFont('liberationsans', sizes['input']),
            'time': pygame.font.SysFont('liberationsans', sizes['time']),
            'status': pygame.font.SysFont('liberationsans', sizes['status']),
            'menu': pygame.font.SysFont('liberationsans', 14),
            'menu_title': pygame.font.SysFont('liberationsans', 16, bold=True),
        }
        self.line_height = sizes['line_height']
        
    def fetch_sessions(self):
        """Fetch available sessions from gateway"""
        self.sessions_loading = True
        try:
            # Use CLI to get sessions
            import subprocess
            result = subprocess.run(
                ['openclaw', 'sessions', '--json'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                self.available_sessions = []
                for s in data.get('sessions', []):
                    key = s.get('key', '')
                    # Extract display name
                    if 'displayName' in s:
                        name = s['displayName']
                    else:
                        name = key.split(':')[-1]
                    self.available_sessions.append({
                        'key': key,
                        'name': name,
                        'tokens': s.get('totalTokens', 0)
                    })
        except Exception as e:
            self.messages.append(Message(f"[Failed to load sessions: {str(e)[:30]}]", 'system'))
        self.sessions_loading = False
        
    def switch_session(self, session_key):
        """Switch to a different session"""
        self.settings.session_key = session_key
        self.settings.save()
        self.conversation.clear()
        self.messages.clear()
        self.messages.append(Message(f"Switched to: {session_key}", 'system'))
        self.menu_open = False
        
    def new_session(self):
        """Create a new session"""
        # Generate a simple session name
        timestamp = datetime.now().strftime("%H%M")
        new_key = f"pi-{timestamp}"
        self.switch_session(new_key)
        
    def end_session(self):
        """End current session and start fresh"""
        self.conversation.clear()
        self.messages.clear()
        self.messages.append(Message("Session ended. Starting fresh.", 'system'))
        self.new_session()
        self.menu_open = False
        
    def handle_command(self, cmd):
        """Handle slash commands"""
        parts = cmd.strip().split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        if command in ['/sessions', '/s']:
            self.menu_open = True
            self.menu_mode = 'sessions'
            self.menu_selection = 0
            self.fetch_sessions()
            return True
            
        elif command in ['/session']:
            if args:
                self.switch_session(args)
            else:
                self.messages.append(Message(f"Current: {self.settings.session_key}", 'system'))
            return True
            
        elif command in ['/new', '/n']:
            self.new_session()
            return True
            
        elif command in ['/end', '/e']:
            self.end_session()
            return True
            
        elif command in ['/settings']:
            self.menu_open = True
            self.menu_mode = 'settings'
            self.menu_selection = 0
            return True
            
        elif command in ['/size']:
            if args in TEXT_SIZES:
                self.settings.text_size = args
                self.settings.save()
                self.rebuild_fonts()
                self.messages.append(Message(f"Text size: {args}", 'system'))
            else:
                self.messages.append(Message(f"Sizes: small, medium, large", 'system'))
            return True
            
        elif command in ['/status']:
            self.messages.append(Message(
                f"Session: {self.settings.session_key}\n"
                f"Text: {self.settings.text_size}\n"
                f"Messages: {len(self.conversation)}",
                'system'
            ))
            return True
            
        elif command in ['/clear', '/c']:
            self.conversation.clear()
            self.messages.clear()
            self.messages.append(Message("Cleared", 'system'))
            return True
            
        elif command in ['/help', '/?']:
            self.messages.append(Message(
                "/sessions - List sessions\n"
                "/session <key> - Switch session\n"
                "/new - New session\n"
                "/end - End session\n"
                "/size <s/m/l> - Text size\n"
                "/clear - Clear chat\n"
                "/status - Show status\n"
                "Tab - Open menu",
                'system'
            ))
            return True
            
        return False  # Not a command, send as message
        
    def send_message(self):
        if not self.input_text.strip() or self.waiting:
            return
            
        msg = self.input_text.strip()
        self.input_text = ""
        self.input_cursor = 0
        
        # Check for commands
        if msg.startswith('/'):
            if self.handle_command(msg):
                return
        
        self.messages.append(Message(msg, 'user'))
        self.conversation.append({"role": "user", "content": msg})
        self.scroll_offset = 0
        self.waiting = True
        self.status = "thinking"
        
        self.send_thread = threading.Thread(target=self._send_async, args=(msg,), daemon=True)
        self.send_thread.start()
        
    def _send_async(self, user_msg):
        try:
            url = f"{GATEWAY_URL}/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {GATEWAY_TOKEN}",
                "x-openclaw-session-key": self.settings.session_key
            }
            
            context_msgs = self.conversation[-10:]
            payload = {
                "model": f"openclaw:{AGENT_ID}",
                "messages": context_msgs
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                if content:
                    self.messages.append(Message(content, 'assistant'))
                    self.conversation.append({"role": "assistant", "content": content})
                    self.status = "ready"
                else:
                    self.messages.append(Message("[Empty response]", 'system'))
                    self.status = "ready"
            else:
                error = response.text[:40] if response.text else f"HTTP {response.status_code}"
                self.messages.append(Message(f"[{error}]", 'system'))
                self.status = "error"
                
        except requests.Timeout:
            self.messages.append(Message("[Timeout]", 'system'))
            self.status = "timeout"
        except requests.ConnectionError:
            self.messages.append(Message("[Disconnected]", 'system'))
            self.status = "offline"
        except Exception as e:
            self.messages.append(Message(f"[{str(e)[:30]}]", 'system'))
            self.status = "error"
            
        self.waiting = False
        self.scroll_offset = 0
        
    def handle_menu_key(self, event):
        """Handle keyboard in menu"""
        if event.key == pygame.K_ESCAPE or event.key == pygame.K_TAB:
            self.menu_open = False
            return
            
        if event.key == pygame.K_UP:
            self.menu_selection = max(0, self.menu_selection - 1)
        elif event.key == pygame.K_DOWN:
            if self.menu_mode == 'main':
                self.menu_selection = min(2, self.menu_selection + 1)
            elif self.menu_mode == 'sessions':
                self.menu_selection = min(len(self.available_sessions), self.menu_selection + 1)
            elif self.menu_mode == 'settings':
                self.menu_selection = min(2, self.menu_selection + 1)
                
        elif event.key == pygame.K_RETURN:
            if self.menu_mode == 'main':
                if self.menu_selection == 0:  # Sessions
                    self.menu_mode = 'sessions'
                    self.menu_selection = 0
                    self.fetch_sessions()
                elif self.menu_selection == 1:  # Settings
                    self.menu_mode = 'settings'
                    self.menu_selection = 0
                elif self.menu_selection == 2:  # Close
                    self.menu_open = False
                    
            elif self.menu_mode == 'sessions':
                if self.menu_selection == 0:  # New session
                    self.new_session()
                elif self.menu_selection <= len(self.available_sessions):
                    session = self.available_sessions[self.menu_selection - 1]
                    self.switch_session(session['key'])
                    
            elif self.menu_mode == 'settings':
                sizes = list(TEXT_SIZES.keys())
                if self.menu_selection < len(sizes):
                    self.settings.text_size = sizes[self.menu_selection]
                    self.settings.save()
                    self.rebuild_fonts()
                    self.messages.append(Message(f"Text size: {sizes[self.menu_selection]}", 'system'))
                    self.menu_open = False
                    
        elif event.key == pygame.K_BACKSPACE or event.key == pygame.K_LEFT:
            if self.menu_mode != 'main':
                self.menu_mode = 'main'
                self.menu_selection = 0
                
    def handle_key(self, event):
        if self.menu_open:
            self.handle_menu_key(event)
            return
            
        if event.key == pygame.K_TAB:
            self.menu_open = True
            self.menu_mode = 'main'
            self.menu_selection = 0
            return
            
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
            self.scroll_offset = min(self.scroll_offset + 2, max(0, len(self.messages) - 2))
        elif event.key == pygame.K_DOWN:
            self.scroll_offset = max(0, self.scroll_offset - 2)
        elif event.key == pygame.K_PAGEUP:
            self.scroll_offset = min(self.scroll_offset + 6, max(0, len(self.messages) - 2))
        elif event.key == pygame.K_PAGEDOWN:
            self.scroll_offset = max(0, self.scroll_offset - 6)
        elif event.key == pygame.K_ESCAPE:
            self.input_text = ""
            self.input_cursor = 0
        elif event.key == pygame.K_n and event.mod & pygame.KMOD_CTRL:
            self.new_session()
        elif event.key == pygame.K_w and event.mod & pygame.KMOD_CTRL:
            self.end_session()
        elif event.unicode and len(event.unicode) == 1 and ord(event.unicode) >= 32:
            self.input_text = self.input_text[:self.input_cursor] + event.unicode + self.input_text[self.input_cursor:]
            self.input_cursor += 1
            
    def word_wrap(self, text, font, max_width):
        words = text.split(' ')
        lines = []
        current_line = ""
        
        for word in words:
            if '\n' in word:
                parts = word.split('\n')
                for i, part in enumerate(parts):
                    if i > 0:
                        if current_line:
                            lines.append(current_line)
                        current_line = part
                    else:
                        test_line = current_line + (' ' if current_line else '') + part
                        w, _ = self.fonts[font].size(test_line)
                        if w <= max_width:
                            current_line = test_line
                        else:
                            if current_line:
                                lines.append(current_line)
                            current_line = part
            else:
                test_line = current_line + (' ' if current_line else '') + word
                w, _ = self.fonts[font].size(test_line)
                if w <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    while self.fonts[font].size(word)[0] > max_width and len(word) > 1:
                        for i in range(len(word), 0, -1):
                            if self.fonts[font].size(word[:i])[0] <= max_width:
                                lines.append(word[:i])
                                word = word[i:]
                                break
                        else:
                            break
                    current_line = word
                    
        if current_line:
            lines.append(current_line)
            
        return lines if lines else [""]
        
    def draw_bubble(self, msg, y):
        is_user = msg.role == 'user'
        is_system = msg.role == 'system'
        
        margin = 10
        padding_x = 12
        padding_y = 8
        max_bubble_width = SCREEN_WIDTH - margin * 2 - 30
        
        lines = self.word_wrap(msg.text, 'msg', max_bubble_width - padding_x * 2)
        
        bubble_height = len(lines) * self.line_height + padding_y * 2
        bubble_width = max(self.fonts['msg'].size(line)[0] for line in lines) + padding_x * 2
        bubble_width = max(60, min(bubble_width, max_bubble_width))
        
        if y - bubble_height - 10 < 44:
            return None
            
        y = y - bubble_height - 8
        
        if is_user:
            x = SCREEN_WIDTH - bubble_width - margin
            color = C['user_bubble']
        elif is_system:
            x = (SCREEN_WIDTH - bubble_width) // 2
            color = C['system_bubble']
        else:
            x = margin
            color = C['bot_bubble']
            
        pygame.draw.rect(self.screen, color, (x, y, bubble_width, bubble_height), border_radius=12)
        
        text_y = y + padding_y
        text_color = C['text_bright']
        for line in lines:
            surf = self.fonts['msg'].render(line, True, text_color)
            self.screen.blit(surf, (x + padding_x, text_y))
            text_y += self.line_height
            
        return y - 4
        
    def draw_menu(self):
        """Draw the menu overlay"""
        # Semi-transparent background
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        overlay.fill((0, 0, 0))
        overlay.set_alpha(180)
        self.screen.blit(overlay, (0, 0))
        
        # Menu box
        menu_w, menu_h = 280, 220
        menu_x = (SCREEN_WIDTH - menu_w) // 2
        menu_y = (SCREEN_HEIGHT - menu_h) // 2
        
        pygame.draw.rect(self.screen, C['bg_overlay'], (menu_x, menu_y, menu_w, menu_h), border_radius=12)
        pygame.draw.rect(self.screen, C['border'], (menu_x, menu_y, menu_w, menu_h), width=2, border_radius=12)
        
        # Title
        if self.menu_mode == 'main':
            title = "Menu"
            items = ["Sessions", "Text Size", "Close"]
        elif self.menu_mode == 'sessions':
            title = "Sessions"
            items = ["+ New Session"] + [s['name'][:25] for s in self.available_sessions]
        elif self.menu_mode == 'settings':
            title = "Text Size"
            items = ["Small", "Medium", "Large"]
            
        title_surf = self.fonts['menu_title'].render(title, True, C['text_bright'])
        self.screen.blit(title_surf, (menu_x + 16, menu_y + 12))
        
        # Back hint
        if self.menu_mode != 'main':
            back_surf = self.fonts['status'].render("← Back", True, C['text_dim'])
            self.screen.blit(back_surf, (menu_x + menu_w - 60, menu_y + 14))
        
        pygame.draw.line(self.screen, C['border'], 
                        (menu_x + 12, menu_y + 40), (menu_x + menu_w - 12, menu_y + 40))
        
        # Items
        item_y = menu_y + 50
        for i, item in enumerate(items[:6]):  # Max 6 items visible
            is_selected = i == self.menu_selection
            
            item_rect = (menu_x + 8, item_y, menu_w - 16, 28)
            if is_selected:
                pygame.draw.rect(self.screen, C['bg_item_hover'], item_rect, border_radius=6)
            
            # Checkmark for current
            prefix = ""
            if self.menu_mode == 'settings':
                sizes = list(TEXT_SIZES.keys())
                if i < len(sizes) and sizes[i] == self.settings.text_size:
                    prefix = "✓ "
            elif self.menu_mode == 'sessions' and i > 0:
                if self.available_sessions[i-1]['key'] == self.settings.session_key:
                    prefix = "● "
                    
            text_color = C['text_bright'] if is_selected else C['text']
            item_surf = self.fonts['menu'].render(prefix + item, True, text_color)
            self.screen.blit(item_surf, (menu_x + 16, item_y + 6))
            
            item_y += 30
            
        # Footer hint
        hint = "Enter: Select  |  Tab/Esc: Close"
        hint_surf = self.fonts['status'].render(hint, True, C['text_muted'])
        self.screen.blit(hint_surf, (menu_x + (menu_w - hint_surf.get_width()) // 2, menu_y + menu_h - 24))
        
    def draw(self):
        self.screen.fill(C['bg'])
        
        # Header
        pygame.draw.rect(self.screen, C['bg_header'], (0, 0, SCREEN_WIDTH, 40))
        
        # Menu button
        menu_btn = pygame.Rect(10, 8, 32, 24)
        pygame.draw.rect(self.screen, C['bg_item'], menu_btn, border_radius=4)
        # Hamburger icon
        for i in range(3):
            pygame.draw.line(self.screen, C['text'], (16, 13 + i*6), (36, 13 + i*6), 2)
        
        # Title + session
        session_short = self.settings.session_key[:15]
        title = self.fonts['title'].render("OpenClaw", True, C['text_bright'])
        self.screen.blit(title, (50, 6))
        session_surf = self.fonts['status'].render(session_short, True, C['text_dim'])
        self.screen.blit(session_surf, (50, 24))
        
        # Status dot
        if self.waiting:
            dot_color = C['accent']
        elif self.status == "ready":
            dot_color = C['success']
        elif self.status in ("error", "offline", "timeout"):
            dot_color = C['error']
        else:
            dot_color = C['warning']
        pygame.draw.circle(self.screen, dot_color, (SCREEN_WIDTH - 24, 20), 6)
        
        # Time
        time_str = datetime.now().strftime("%H:%M")
        time_surf = self.fonts['time'].render(time_str, True, C['text_dim'])
        self.screen.blit(time_surf, (SCREEN_WIDTH - 70, 13))
        
        pygame.draw.line(self.screen, C['border'], (0, 40), (SCREEN_WIDTH, 40), 2)
        
        # Messages
        msg_bottom = SCREEN_HEIGHT - 56
        messages = list(self.messages)
        
        if self.scroll_offset > 0 and len(messages) > self.scroll_offset:
            messages = messages[:-self.scroll_offset]
            
        y = msg_bottom
        for msg in reversed(messages):
            new_y = self.draw_bubble(msg, y)
            if new_y is None:
                break
            y = new_y
            
        # Thinking dots
        if self.waiting:
            dots = "●" * (int(time.time() * 2) % 3 + 1) + "○" * (2 - int(time.time() * 2) % 3)
            dots_surf = self.fonts['msg'].render(dots, True, C['accent'])
            self.screen.blit(dots_surf, (14, msg_bottom - 24))
            
        # Scroll indicator
        if self.scroll_offset > 0:
            ind = f"↑ {self.scroll_offset}"
            ind_surf = self.fonts['status'].render(ind, True, C['warning'])
            self.screen.blit(ind_surf, (SCREEN_WIDTH // 2 - 20, 46))
            
        # Input area
        input_y = SCREEN_HEIGHT - 52
        pygame.draw.line(self.screen, C['border'], (0, input_y), (SCREEN_WIDTH, input_y), 2)
        
        box_rect = (10, input_y + 8, SCREEN_WIDTH - 20, 38)
        pygame.draw.rect(self.screen, C['bg_input'], box_rect, border_radius=10)
        pygame.draw.rect(self.screen, C['border'], box_rect, width=1, border_radius=10)
        
        # Input text
        display_text = self.input_text
        cursor_pos = self.input_cursor
        max_chars = 38
        
        if len(display_text) > max_chars:
            start = max(0, cursor_pos - max_chars + 8)
            display_text = display_text[start:start + max_chars]
            cursor_pos = cursor_pos - start
            
        text_color = C['text'] if display_text else C['text_muted']
        placeholder = "..." if self.waiting else "Message or /help"
        text_content = display_text or placeholder
        surf = self.fonts['input'].render(text_content, True, text_color)
        self.screen.blit(surf, (20, input_y + 18))
        
        # Cursor
        if int(time.time() * 2) % 2 and not self.waiting and not self.menu_open:
            cursor_x = 20 + self.fonts['input'].size(display_text[:cursor_pos])[0]
            pygame.draw.rect(self.screen, C['cursor'], (cursor_x, input_y + 14, 2, 22))
            
        # Draw menu overlay if open
        if self.menu_open:
            self.draw_menu()
            
        pygame.display.flip()
        
    def run(self):
        running = True
        
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q and event.mod & pygame.KMOD_CTRL:
                        running = False
                    else:
                        self.handle_key(event)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    # Menu button click
                    if not self.menu_open and 10 <= event.pos[0] <= 42 and 8 <= event.pos[1] <= 32:
                        self.menu_open = True
                        self.menu_mode = 'main'
                        self.menu_selection = 0
                        
            self.draw()
            self.clock.tick(30)
            
        pygame.quit()


if __name__ == '__main__':
    try:
        app = ChatApp()
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
