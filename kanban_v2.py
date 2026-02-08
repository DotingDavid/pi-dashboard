    def draw_kanban(self):
        """WOW Kanban v2 - Professional, polished, impressive"""
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
        
        all_columns = ['Not Started', 'Research', 'Active', 'Stuck', 'Review', 'Implement', 'Finished']
        col_colors = {
            'Not Started': (90, 95, 130), 'Research': (70, 130, 200), 
            'Active': (60, 180, 100), 'Stuck': (200, 70, 70),
            'Review': (200, 160, 50), 'Implement': (140, 90, 190), 'Finished': (50, 160, 90)
        }
        col_icons = {'Not Started': '○', 'Research': '◎', 'Active': '●', 'Stuck': '!', 
                     'Review': '◐', 'Implement': '▸', 'Finished': '✓'}
        
        # ═══════════════════════════════════════════════════════════════
        # BACKGROUND - Subtle gradient
        # ═══════════════════════════════════════════════════════════════
        for y in range(36, SCREEN_HEIGHT):
            progress = (y - 36) / (SCREEN_HEIGHT - 36)
            r = int(14 + progress * 4)
            g = int(16 + progress * 4)
            b = int(22 + progress * 8)
            pygame.draw.line(self.screen, (r, g, b), (0, y), (SCREEN_WIDTH, y))
        
        # ═══════════════════════════════════════════════════════════════
        # HEADER - Clean board tabs
        # ═══════════════════════════════════════════════════════════════
        header_y = 44
        
        # Glass header bar
        header_surf = pygame.Surface((SCREEN_WIDTH - 20, 28), pygame.SRCALPHA)
        header_surf.fill((30, 32, 45, 180))
        self.screen.blit(header_surf, (10, header_y - 4))
        pygame.draw.rect(self.screen, (50, 55, 70), (10, header_y - 4, SCREEN_WIDTH - 20, 28), width=1, border_radius=6)
        
        boards = [
            ('salon', 'Salon', (100, 150, 220)),
            ('personal', 'Personal', (120, 180, 120)),
            ('fasttrack', 'Fast Track', (255, 90, 70))
        ]
        
        tab_x = 20
        for board_id, board_name, board_color in boards:
            is_active = self.kanban_board == board_id
            
            if board_id == 'fasttrack' and is_active:
                pulse = 0.8 + 0.2 * math.sin(self.kanban_anim * 4)
                display_color = (int(255 * pulse), int(90 * pulse), int(70 * pulse))
            else:
                display_color = board_color if is_active else (90, 95, 115)
            
            tab_surf = self.fonts['msg'].render(board_name, True, display_color)
            self.screen.blit(tab_surf, (tab_x, header_y + 2))
            
            if is_active:
                pygame.draw.rect(self.screen, display_color, (tab_x, header_y + 20, tab_surf.get_width(), 2), border_radius=1)
            
            tab_x += tab_surf.get_width() + 25
        
        # Sync indicator
        sync_status = getattr(self, 'kanban_sync_status', 'live')
        sync_time = getattr(self, 'kanban_sync_time', 0)
        if sync_status == 'syncing' and time.time() - sync_time > 1:
            self.kanban_sync_status = 'live'
            sync_status = 'live'
        
        sync_colors = {'live': (80, 200, 120), 'syncing': (220, 180, 60), 'error': (220, 80, 80)}
        sync_texts = {'live': '● Synced', 'syncing': '◐ Sync...', 'error': '✗ Error'}
        sync_surf = self.fonts['status'].render(sync_texts.get(sync_status, '●'), True, sync_colors.get(sync_status, (80, 200, 120)))
        self.screen.blit(sync_surf, (SCREEN_WIDTH - sync_surf.get_width() - 20, header_y + 4))
        
        # ═══════════════════════════════════════════════════════════════
        # PROGRESS BAR - Visual flow indicator
        # ═══════════════════════════════════════════════════════════════
        progress_y = header_y + 30
        progress_h = 6
        
        total_cards = sum(len(self._get_kanban_column_cards(c)) for c in all_columns)
        if total_cards > 0:
            stage_counts = [len(self._get_kanban_column_cards(c)) for c in all_columns]
            max_count = max(stage_counts) if stage_counts else 1
            
            seg_x = 10
            seg_w = (SCREEN_WIDTH - 20) / 7
            for i, (col_name, count) in enumerate(zip(all_columns, stage_counts)):
                col_color = col_colors[col_name]
                pygame.draw.rect(self.screen, (35, 38, 50), (seg_x + i * seg_w, progress_y, seg_w - 2, progress_h), border_radius=3)
                if count > 0:
                    fill_w = max(8, (seg_w - 2) * min(1, count / max_count))
                    pygame.draw.rect(self.screen, col_color, (seg_x + i * seg_w, progress_y, fill_w, progress_h), border_radius=3)
        
        # ═══════════════════════════════════════════════════════════════
        # COLUMNS - All 7 in one row
        # ═══════════════════════════════════════════════════════════════
        cols_y = progress_y + 14
        cols_h = SCREEN_HEIGHT - cols_y - 26
        col_w = (SCREEN_WIDTH - 24) // 7
        col_gap = 3
        
        for col_idx, col_name in enumerate(all_columns):
            col_x = 12 + col_idx * col_w
            is_selected_col = col_idx == self.kanban_col
            col_color = col_colors[col_name]
            cards = self._get_kanban_column_cards(col_name)
            
            # Selected column glow
            if is_selected_col:
                glow = 0.6 + 0.4 * math.sin(self.kanban_anim * 3)
                glow_color = (int(col_color[0] * glow * 0.5), int(col_color[1] * glow * 0.5), int(col_color[2] * glow * 0.5))
                pygame.draw.rect(self.screen, glow_color, (col_x - 2, cols_y - 2, col_w - col_gap + 4, cols_h + 4), border_radius=10, width=2)
            
            # Column background
            bg_color = (32, 35, 48) if is_selected_col else (24, 27, 38)
            pygame.draw.rect(self.screen, bg_color, (col_x, cols_y, col_w - col_gap, cols_h), border_radius=8)
            
            # Column header with gradient
            header_h = 32
            pygame.draw.rect(self.screen, col_color, (col_x, cols_y, col_w - col_gap, header_h), border_top_left_radius=8, border_top_right_radius=8)
            
            # Icon + Count
            icon = col_icons[col_name]
            icon_surf = self.fonts['msg'].render(icon, True, (255, 255, 255))
            self.screen.blit(icon_surf, (col_x + 8, cols_y + 7))
            
            count_surf = self.fonts['msg'].render(str(len(cards)), True, (255, 255, 255))
            self.screen.blit(count_surf, (col_x + col_w - col_gap - count_surf.get_width() - 8, cols_y + 7))
            
            # Cards
            cards_y = cols_y + header_h + 6
            card_h = 34
            card_gap = 4
            available_h = cols_h - header_h - 12
            max_visible = available_h // (card_h + card_gap)
            
            scroll = self.kanban_scroll.get(col_idx, 0)
            visible_cards = cards[scroll:scroll + max_visible]
            
            if not cards:
                empty_surf = self.fonts['status'].render("Empty", True, (60, 65, 80))
                self.screen.blit(empty_surf, (col_x + (col_w - col_gap) // 2 - empty_surf.get_width() // 2, cards_y + 20))
            
            for card_idx, card in enumerate(visible_cards):
                actual_idx = scroll + card_idx
                is_selected_card = is_selected_col and actual_idx == self.kanban_card
                card_y_pos = cards_y + card_idx * (card_h + card_gap)
                
                is_fast = '🔥' in card.get('title', '') or card.get('fast_track', False)
                
                # Card background
                if is_selected_card:
                    pygame.draw.rect(self.screen, (55, 60, 80), (col_x + 4, card_y_pos, col_w - col_gap - 8, card_h), border_radius=6)
                    pygame.draw.rect(self.screen, col_color, (col_x + 4, card_y_pos, col_w - col_gap - 8, card_h), border_radius=6, width=2)
                elif is_fast:
                    pulse = 0.7 + 0.3 * math.sin(self.kanban_anim * 5)
                    pygame.draw.rect(self.screen, (int(55 * pulse), int(35 * pulse), int(35 * pulse)), (col_x + 4, card_y_pos, col_w - col_gap - 8, card_h), border_radius=6)
                    pygame.draw.rect(self.screen, (180, 60, 60), (col_x + 4, card_y_pos, 3, card_h), border_top_left_radius=6, border_bottom_left_radius=6)
                else:
                    pygame.draw.rect(self.screen, (38, 42, 55), (col_x + 4, card_y_pos, col_w - col_gap - 8, card_h), border_radius=6)
                
                # Card title
                title = card.get('title', 'Untitled').lstrip('🔥').strip()
                max_chars = 11
                display_title = title[:max_chars] + ('…' if len(title) > max_chars else '')
                
                text_x = col_x + 10
                if is_fast:
                    fire_pulse = 0.8 + 0.2 * math.sin(self.kanban_anim * 6 + card_idx)
                    fire_surf = self.fonts['status'].render('🔥', True, (int(255 * fire_pulse), int(120 * fire_pulse), 50))
                    self.screen.blit(fire_surf, (text_x, card_y_pos + 9))
                    text_x += 14
                
                title_color = (235, 240, 255) if is_selected_card else (175, 180, 200)
                title_surf = self.fonts['status'].render(display_title, True, title_color)
                self.screen.blit(title_surf, (text_x, card_y_pos + 10))
                
                # Priority indicator
                priority = card.get('priority', 'green')
                p_colors = {'red': (200, 60, 60), 'yellow': (200, 160, 40), 'green': (60, 160, 90)}
                if not is_fast:
                    pygame.draw.rect(self.screen, p_colors.get(priority, p_colors['green']), 
                                   (col_x + 4, card_y_pos, 3, card_h), border_top_left_radius=6, border_bottom_left_radius=6)
            
            # Scroll indicators
            if scroll > 0:
                pygame.draw.polygon(self.screen, (100, 110, 140), [
                    (col_x + (col_w - col_gap) // 2, cards_y - 6),
                    (col_x + (col_w - col_gap) // 2 - 6, cards_y - 1),
                    (col_x + (col_w - col_gap) // 2 + 6, cards_y - 1)
                ])
            if len(cards) > scroll + max_visible:
                arrow_y = cols_y + cols_h - 6
                pygame.draw.polygon(self.screen, (100, 110, 140), [
                    (col_x + (col_w - col_gap) // 2 - 6, arrow_y - 5),
                    (col_x + (col_w - col_gap) // 2 + 6, arrow_y - 5),
                    (col_x + (col_w - col_gap) // 2, arrow_y)
                ])
        
        # Detail popup
        if self.kanban_detail:
            self._draw_kanban_detail()
        
        # Floating card when holding
        if hasattr(self, 'kanban_holding') and self.kanban_holding:
            ghost_x = 12 + self.kanban_col * col_w
            ghost_y = cols_y + 50
            pulse = 0.7 + 0.3 * math.sin(self.kanban_anim * 5)
            pygame.draw.rect(self.screen, (int(80 * pulse), int(120 * pulse), int(200 * pulse)), 
                           (ghost_x + 4, ghost_y, col_w - col_gap - 8, 34), border_radius=6, width=2)
            title = self.kanban_holding.get('title', '')[:10]
            title_surf = self.fonts['status'].render(title, True, (180, 200, 240))
            self.screen.blit(title_surf, (ghost_x + 12, ghost_y + 9))
        
        # Footer
        if hasattr(self, 'kanban_holding') and self.kanban_holding:
            hint = "←→ Move  •  Space Place  •  Esc Cancel"
            hint_color = (220, 180, 80)
        else:
            hint = "←→ Column  •  ↑↓ Card  •  Space Grab  •  Enter Details  •  Tab Board"
            hint_color = (90, 95, 115)
        hint_surf = self.fonts['status'].render(hint, True, hint_color)
        self.screen.blit(hint_surf, ((SCREEN_WIDTH - hint_surf.get_width())//2, SCREEN_HEIGHT - 16))

