#!/usr/bin/env python3
"""
Pi 400 Dashboard v8 - HTTP Chat Edition
For 3.5" Waveshare TFT (480x320)

Uses OpenAI-compatible /v1/chat/completions endpoint.
Clean UI with larger fonts for readability.
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

# Configuration
SCREEN_WIDTH = 480
SCREEN_HEIGHT = 320
GATEWAY_URL = "http://127.0.0.1:18789"
GATEWAY_TOKEN = "8ee708fa05cfe60da1182554737e8f556ff0333784479bf9"
AGENT_ID = "main"
SESSION_KEY = "pi-display"  # Persistent session for Pi chat

# Color palette - clean dark theme
C = {
    'bg': (18, 18, 22),
    'bg_header': (28, 28, 35),
    'bg_input': (35, 35, 45),
    
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


class Message:
    """Chat message"""
    def __init__(self, text, role='user', timestamp=None):
        self.text = text
        self.role = role
        self.timestamp = timestamp or datetime.now()


class ChatApp:
    """Main chat application"""
    
    def __init__(self):
        pygame.init()
        
        self.screen = pygame.display.set_mode(
            (SCREEN_WIDTH, SCREEN_HEIGHT),
            pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF
        )
        pygame.display.set_caption('OpenClaw')
        pygame.mouse.set_visible(False)
        
        # Larger fonts for 3.5" display
        self.fonts = {
            'title': pygame.font.SysFont('liberationsans', 18, bold=True),
            'msg': pygame.font.SysFont('liberationsans', 14),
            'input': pygame.font.SysFont('liberationsans', 15),
            'time': pygame.font.SysFont('liberationsans', 11),
            'status': pygame.font.SysFont('liberationsans', 12),
        }
        
        # State
        self.messages = deque(maxlen=100)
        self.conversation = []
        self.input_text = ""
        self.input_cursor = 0
        self.scroll_offset = 0
        self.status = "ready"
        self.waiting = False
        self.send_thread = None
        
        self.clock = pygame.time.Clock()
        
        # Welcome
        self.messages.append(Message("Ready", 'system'))
        
    def send_message(self):
        """Send current input"""
        if not self.input_text.strip() or self.waiting:
            return
            
        msg = self.input_text.strip()
        self.messages.append(Message(msg, 'user'))
        self.conversation.append({"role": "user", "content": msg})
        self.input_text = ""
        self.input_cursor = 0
        self.scroll_offset = 0
        self.waiting = True
        self.status = "thinking"
        
        self.send_thread = threading.Thread(target=self._send_async, args=(msg,), daemon=True)
        self.send_thread.start()
        
    def _send_async(self, user_msg):
        """Send message via HTTP API"""
        try:
            url = f"{GATEWAY_URL}/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {GATEWAY_TOKEN}",
                "x-openclaw-session-key": SESSION_KEY
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
        
    def handle_key(self, event):
        """Handle keyboard input"""
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
        elif event.key == pygame.K_c and event.mod & pygame.KMOD_CTRL:
            self.conversation.clear()
            self.messages.append(Message("[Cleared]", 'system'))
        elif event.unicode and len(event.unicode) == 1 and ord(event.unicode) >= 32:
            self.input_text = self.input_text[:self.input_cursor] + event.unicode + self.input_text[self.input_cursor:]
            self.input_cursor += 1
            
    def word_wrap(self, text, font, max_width):
        """Word wrap text"""
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
        """Draw chat bubble. Returns new y or None."""
        is_user = msg.role == 'user'
        is_system = msg.role == 'system'
        
        margin = 10
        padding_x = 12
        padding_y = 8
        max_bubble_width = SCREEN_WIDTH - margin * 2 - 30
        
        lines = self.word_wrap(msg.text, 'msg', max_bubble_width - padding_x * 2)
        
        line_height = 18
        bubble_height = len(lines) * line_height + padding_y * 2
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
            
        # Rounded bubble
        pygame.draw.rect(self.screen, color, (x, y, bubble_width, bubble_height), border_radius=12)
        
        # Text
        text_y = y + padding_y
        text_color = C['text_bright']
        for line in lines:
            surf = self.fonts['msg'].render(line, True, text_color)
            self.screen.blit(surf, (x + padding_x, text_y))
            text_y += line_height
            
        return y - 4
        
    def draw(self):
        """Draw interface"""
        self.screen.fill(C['bg'])
        
        # Header bar
        pygame.draw.rect(self.screen, C['bg_header'], (0, 0, SCREEN_WIDTH, 40))
        
        # Title
        title = self.fonts['title'].render("OpenClaw", True, C['text_bright'])
        self.screen.blit(title, (14, 10))
        
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
        time_surf = self.fonts['status'].render(time_str, True, C['text_dim'])
        self.screen.blit(time_surf, (SCREEN_WIDTH - 70, 13))
        
        # Header line
        pygame.draw.line(self.screen, C['border'], (0, 40), (SCREEN_WIDTH, 40), 2)
        
        # Messages area
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
        
        # Input box
        box_rect = (10, input_y + 8, SCREEN_WIDTH - 20, 38)
        pygame.draw.rect(self.screen, C['bg_input'], box_rect, border_radius=10)
        pygame.draw.rect(self.screen, C['border'], box_rect, width=1, border_radius=10)
        
        # Input text
        display_text = self.input_text
        cursor_pos = self.input_cursor
        max_chars = 40
        
        if len(display_text) > max_chars:
            start = max(0, cursor_pos - max_chars + 8)
            display_text = display_text[start:start + max_chars]
            cursor_pos = cursor_pos - start
            
        text_color = C['text'] if display_text else C['text_muted']
        placeholder = "..." if self.waiting else "Message"
        text_content = display_text or placeholder
        surf = self.fonts['input'].render(text_content, True, text_color)
        self.screen.blit(surf, (20, input_y + 18))
        
        # Cursor
        if int(time.time() * 2) % 2 and not self.waiting and display_text:
            cursor_x = 20 + self.fonts['input'].size(display_text[:cursor_pos])[0]
            pygame.draw.rect(self.screen, C['cursor'], (cursor_x, input_y + 14, 2, 22))
            
        pygame.display.flip()
        
    def run(self):
        """Main loop"""
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
