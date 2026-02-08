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
        # FAST TRACK ROW - Always visible at top
        # ═══════════════════════════════════════════════════════════════
        ft_y = header_y + header_h + 6
        ft_h = 50
        
        # Collect all fast track items from current board
        ft_cards = []
        for col_name in all_columns:
            for card in self._get_kanban_column_cards(col_name):
                if '🔥' in card.get('title', '') or card.get('fast_track', False):
                    card['_from_column'] = col_name
                    ft_cards.append(card)
        
        # Fast track container with pulsing border
        pulse = 0.6 + 0.4 * math.sin(self.kanban_anim * 3)
        ft_border = (int(200 * pulse), int(60 * pulse), int(60 * pulse))
        pygame.draw.rect(self.screen, (35, 25, 25), (10, ft_y, SCREEN_WIDTH - 20, ft_h), border_radius=8)
        pygame.draw.rect(self.screen, ft_border, (10, ft_y, SCREEN_WIDTH - 20, ft_h), width=2, border_radius=8)
        
        # Fast track label
        ft_label = self.fonts['status'].render('🔥 FAST TRACK', True, (255, 100, 80))
        self.screen.blit(ft_label, (18, ft_y + 4))
        
        # Fast track cards - horizontal layout
        if ft_cards:
            ft_card_w = 130
            ft_card_h = 28
            ft_cards_x = 18
            ft_cards_y = ft_y + 20
            max_ft_visible = (SCREEN_WIDTH - 40) // (ft_card_w + 6)
            
            for i, card in enumerate(ft_cards[:max_ft_visible]):
                is_selected = self.kanban_in_fasttrack and i == self.kanban_ft_card
                card_x = ft_cards_x + i * (ft_card_w + 6)
                
                # Card background
                if is_selected:
                    pygame.draw.rect(self.screen, (70, 45, 45), (card_x, ft_cards_y, ft_card_w, ft_card_h), border_radius=5)
                    pygame.draw.rect(self.screen, (255, 100, 80), (card_x, ft_cards_y, ft_card_w, ft_card_h), border_radius=5, width=2)
                else:
                    pygame.draw.rect(self.screen, (50, 35, 35), (card_x, ft_cards_y, ft_card_w, ft_card_h), border_radius=5)
                
                # Fire icon
                fire_pulse = 0.8 + 0.2 * math.sin(self.kanban_anim * 5 + i)
                fire_surf = self.fonts['status'].render('🔥', True, (int(255 * fire_pulse), int(100 * fire_pulse), 50))
                self.screen.blit(fire_surf, (card_x + 4, ft_cards_y + 7))
                
                # Title
                title = card.get('title', '').lstrip('🔥').strip()[:14]
                if len(card.get('title', '').lstrip('🔥').strip()) > 14:
                    title += '…'
                title_color = (255, 220, 200) if is_selected else (200, 160, 150)
                title_surf = self.fonts['status'].render(title, True, title_color)
                self.screen.blit(title_surf, (card_x + 18, ft_cards_y + 8))
            
            # Show count if more
            if len(ft_cards) > max_ft_visible:
                more_text = f"+{len(ft_cards) - max_ft_visible}"
                more_surf = self.fonts['status'].render(more_text, True, (180, 100, 80))
                self.screen.blit(more_surf, (SCREEN_WIDTH - 40, ft_cards_y + 8))
        else:
            # No fast track items
            empty_surf = self.fonts['status'].render('No urgent items', True, (80, 60, 60))
            self.screen.blit(empty_surf, (SCREEN_WIDTH // 2 - empty_surf.get_width() // 2, ft_y + 22))
        
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

