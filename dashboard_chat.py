#!/usr/bin/env python3
"""
Pi 400 Chat Interface - Clean chat UI talking directly to OpenClaw
For 3.5" Waveshare TFT (480x320)
"""

import pygame
import sys
import os
import subprocess
import json
import time
import threading
from datetime import datetime
from pathlib import Path
from collections import deque

# Configuration
SCREEN_WIDTH = 480
SCREEN_HEIGHT = 320

# Color palette
C = {
    'bg': (30, 32, 40),
    'bg_card': (42, 45, 56),
    'bg_input': (35, 38, 48),
    
    'text': (200, 205, 215),
    'text_bright': (240, 245, 255),
    'text_dim': (100, 105, 120),
    'text_muted': (70, 75, 88),
    
    'primary': (100, 180, 255),
    'success': (120, 210, 140),
    'warning': (250, 200, 80),
    
    'border': (60, 65, 80),
    'divider': (50, 54, 66),
    'cursor': (100, 180, 255),
    
    'user_bubble': (52, 56, 70),
    'bot_bubble': (42, 75, 65),
}


class Message:
    def __init__(self, text, is_user=True, timestamp=None):
        self.text = text
        self.is_user = is_user
        self.timestamp = timestamp or datetime.now()


class ChatApp:
    def __init__(self):
        pygame.init()
        
        self.screen = pygame.display.set_mode(
            (SCREEN_WIDTH, SCREEN_HEIGHT),
            pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF
        )
        pygame.display.set_caption('OpenClaw Chat')
        pygame.mouse.set_visible(False)
        
        self.fonts = {
            'title': pygame.font.SysFont('liberationmono', 16, bold=True),
            'msg': pygame.font.SysFont('liberationmono', 11),
            'input': pygame.font.SysFont('liberationmono', 12),
            'time': pygame.font.SysFont('liberationmono', 9),
            'hint': pygame.font.SysFont('liberationmono', 9),
        }
        
        # State
        self.messages = deque(maxlen=100)
        self.input_text = ""
        self.input_cursor = 0
        self.scroll_offset = 0
        self.waiting = False
        self.send_thread = None
        
        self.clock = pygame.time.Clock()
        
        # Load history if exists
        self.load_history()
    
    def load_history(self):
        """Load recent message history from session"""
        try:
            result = subprocess.run(
                ['openclaw', 'sessions', 'history', '--limit', '20'],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=os.path.expanduser('~')
            )
            
            if result.returncode == 0 and result.stdout.strip():
                # Parse history (simplified - just grab last few user/assistant messages)
                lines = result.stdout.strip().split('\n')
                for line in lines[-10:]:
                    # Very basic parsing - you'd want to improve this
                    if 'User:' in line or 'you:' in line.lower():
                        text = line.split(':', 1)[1].strip() if ':' in line else line
                        self.messages.append(Message(text, is_user=True))
                    elif 'Assistant:' in line or 'bot:' in line.lower():
                        text = line.split(':', 1)[1].strip() if ':' in line else line
                        self.messages.append(Message(text, is_user=False))
        except:
            pass  # Silently fail if can't load history
    
    def send_message(self):
        """Send message to OpenClaw session"""
        if not self.input_text.strip() or self.waiting:
            return
        
        msg_text = self.input_text.strip()
        self.messages.append(Message(msg_text, is_user=True))
        self.input_text = ""
        self.input_cursor = 0
        self.scroll_offset = 0
        self.waiting = True
        
        # Send in background
        self.send_thread = threading.Thread(target=self._send_async, args=(msg_text,))
        self.send_thread.daemon = True
        self.send_thread.start()
    
    def _send_async(self, text):
        """Send message via openclaw agent command"""
        try:
            # Use openclaw agent command (simpler than API)
            result = subprocess.run(
                ['openclaw', 'agent', '--message', text, '--json'],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=os.path.expanduser('~')
            )
            
            if result.returncode == 0 and result.stdout.strip():
                # Parse JSON response
                try:
                    data = json.loads(result.stdout.strip())
                    reply = data.get('reply', data.get('text', data.get('response', '')))
                    if reply:
                        self.messages.append(Message(reply, is_user=False))
                    else:
                        # Maybe it's just text output
                        output = result.stdout.strip()
                        if output and not output.startswith('{'):
                            self.messages.append(Message(output, is_user=False))
                        else:
                            self.messages.append(Message("[Empty response]", is_user=False))
                except json.JSONDecodeError:
                    # Not JSON, just use stdout as-is
                    output = result.stdout.strip()
                    if output:
                        self.messages.append(Message(output, is_user=False))
                    else:
                        self.messages.append(Message("[No output]", is_user=False))
            else:
                error = result.stderr.strip() if result.stderr else f"Exit code {result.returncode}"
                self.messages.append(Message(f"[Error: {error[:80]}]", is_user=False))
        
        except subprocess.TimeoutExpired:
            self.messages.append(Message("[Timeout - still thinking?]", is_user=False))
        except Exception as e:
            self.messages.append(Message(f"[Error: {str(e)[:60]}]", is_user=False))
        
        self.waiting = False
    
    def handle_key(self, event):
        """Handle keyboard input"""
        if event.key == pygame.K_RETURN and not self.waiting:
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
            self.scroll_offset = min(self.scroll_offset + 3, max(0, len(self.messages) - 5))
        elif event.key == pygame.K_DOWN:
            self.scroll_offset = max(0, self.scroll_offset - 3)
        elif event.key == pygame.K_PAGEUP:
            self.scroll_offset = min(self.scroll_offset + 10, max(0, len(self.messages) - 5))
        elif event.key == pygame.K_PAGEDOWN:
            self.scroll_offset = max(0, self.scroll_offset - 10)
        elif event.key == pygame.K_ESCAPE:
            self.input_text = ""
            self.input_cursor = 0
        elif event.unicode and len(event.unicode) == 1 and ord(event.unicode) >= 32:
            # Regular character
            self.input_text = self.input_text[:self.input_cursor] + event.unicode + self.input_text[self.input_cursor:]
            self.input_cursor += 1
    
    def text(self, txt, font, color, x, y, right=False, center=False):
        """Helper to render text"""
        s = self.fonts[font].render(txt, True, color)
        if right:
            x -= s.get_width()
        elif center:
            x -= s.get_width() // 2
        self.screen.blit(s, (x, y))
        return s.get_width(), s.get_height()
    
    def word_wrap(self, text, font, max_width):
        """Word wrap text to fit width"""
        words = text.split(' ')
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + (' ' if current_line else '') + word
            w, _ = self.fonts[font].size(test_line)
            if w <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        
        if current_line:
            lines.append(current_line)
        
        return lines if lines else [""]
    
    def draw_message_bubble(self, msg, y, max_y):
        """Draw a chat bubble for a message. Returns new y position."""
        is_user = msg.is_user
        
        # Bubble dimensions
        bubble_margin = 40 if is_user else 10
        bubble_max_width = SCREEN_WIDTH - bubble_margin - 10
        
        # Word wrap
        lines = self.word_wrap(msg.text, 'msg', bubble_max_width - 20)
        
        # Calculate bubble size
        line_height = 15
        bubble_height = len(lines) * line_height + 12
        bubble_width = max(
            self.fonts['msg'].size(line)[0] + 20
            for line in lines
        )
        
        # Check if bubble fits
        if y - bubble_height < 40:
            return None  # Doesn't fit
        
        # Position
        y = y - bubble_height - 6
        if is_user:
            bubble_x = SCREEN_WIDTH - bubble_width - 10
        else:
            bubble_x = 10
        
        # Draw bubble
        bubble_color = C['user_bubble'] if is_user else C['bot_bubble']
        pygame.draw.rect(self.screen, bubble_color, 
                        (bubble_x, y, bubble_width, bubble_height), 
                        border_radius=8)
        
        # Draw text
        text_y = y + 6
        for line in lines:
            self.text(line, 'msg', C['text_bright'], bubble_x + 10, text_y)
            text_y += line_height
        
        # Time stamp
        time_str = msg.timestamp.strftime("%I:%M %p").lstrip('0')
        time_x = bubble_x + bubble_width - 5 if is_user else bubble_x + 5
        self.text(time_str, 'time', C['text_muted'], 
                 time_x, y - 12, right=is_user)
        
        return y
    
    def draw(self):
        """Draw the chat interface"""
        self.screen.fill(C['bg'])
        
        # Header
        pygame.draw.rect(self.screen, C['bg_card'], (0, 0, SCREEN_WIDTH, 36))
        self.text("OpenClaw", 'title', C['text_bright'], 10, 10)
        
        now = datetime.now()
        time_str = now.strftime("%I:%M %p").lstrip('0')
        self.text(time_str, 'time', C['text_dim'], SCREEN_WIDTH - 10, 12, right=True)
        
        if self.waiting:
            self.text("●●●", 'hint', C['primary'], SCREEN_WIDTH // 2, 12, center=True)
        
        pygame.draw.line(self.screen, C['divider'], (0, 36), (SCREEN_WIDTH, 36), 1)
        
        # Messages area
        msg_bottom_y = SCREEN_HEIGHT - 50
        
        # Get visible messages
        messages = list(self.messages)
        if self.scroll_offset > 0:
            messages = messages[:-self.scroll_offset] if self.scroll_offset < len(messages) else []
        
        # Draw messages from bottom up
        y = msg_bottom_y
        for msg in reversed(messages):
            new_y = self.draw_message_bubble(msg, y, 40)
            if new_y is None:
                break  # No more room
            y = new_y
        
        # Scroll indicator
        if self.scroll_offset > 0:
            self.text(f"↑ {self.scroll_offset} older", 'hint', C['warning'], 
                     SCREEN_WIDTH // 2, 42, center=True)
        
        # Input area
        input_y = SCREEN_HEIGHT - 44
        pygame.draw.line(self.screen, C['divider'], (0, input_y), (SCREEN_WIDTH, input_y), 1)
        
        input_box_y = input_y + 4
        pygame.draw.rect(self.screen, C['bg_input'], 
                        (8, input_box_y, SCREEN_WIDTH - 16, 32), 
                        border_radius=6)
        pygame.draw.rect(self.screen, C['border'], 
                        (8, input_box_y, SCREEN_WIDTH - 16, 32), 
                        width=1, border_radius=6)
        
        # Input text
        display_text = self.input_text
        cursor_offset = self.input_cursor
        
        # Scroll input if too long
        max_input_chars = 48
        if len(display_text) > max_input_chars:
            start = max(0, cursor_offset - max_input_chars + 10)
            display_text = display_text[start:start + max_input_chars]
            cursor_offset = cursor_offset - start
        
        if display_text or not self.waiting:
            self.text(display_text if display_text else "Type a message...", 
                     'input', 
                     C['text'] if display_text else C['text_muted'], 
                     16, input_box_y + 9)
        
        # Cursor
        if int(time.time() * 2) % 2 and not self.waiting:
            cursor_x = 16 + self.fonts['input'].size(display_text[:cursor_offset])[0]
            pygame.draw.rect(self.screen, C['cursor'], 
                           (cursor_x, input_box_y + 8, 2, 16))
        
        # Footer hints
        if not self.waiting:
            self.text("Enter: send  |  ↑↓: scroll  |  Esc: clear", 'hint', C['text_dim'], 
                     SCREEN_WIDTH // 2, SCREEN_HEIGHT - 8, center=True)
        else:
            self.text("Waiting for response...", 'hint', C['warning'], 
                     SCREEN_WIDTH // 2, SCREEN_HEIGHT - 8, center=True)
        
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
