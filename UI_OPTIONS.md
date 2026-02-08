# Task Panel UI Options

Based on research from Linear, Superhuman, Things 3, and small-screen dashboard designs.

---

## 🎨 Option 1: "Linear Focus"

**Inspired by:** Linear app (best keyboard UX in the industry)

**Philosophy:** Professional, clean, teaches shortcuts as you use it

### Visual Style
- Monochrome grays + ONE blue accent color
- Bold task names, muted metadata
- Priority = colored left border only (no icons)
- Selected = subtle blue glow, no heavy borders

### Layout
```
┌──────────────────────────────────────────────────────────┐
│ 📥 Inbox    🏪 Salon    ⏰ Today    ⚠️ Overdue     [1-4] │
├──────────────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────────────────┐ │
│ │ ○ Warm oil in hot towel machine...     Nov 7    [D] │ │
│ │   ↳ 2 subtasks                                      │ │
│ └──────────────────────────────────────────────────────┘ │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ ◉ MAC USA                               Nov 8    [A] │ │
│ │   "Follow up on supplier"                      💬 2 │ │
│ └──────────────────────────────────────────────────────┘ │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ ○ Make Badges                      🔄   Nov 9       │ │
│ └──────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────┤
│           ↑↓ Navigate   Space Done   / Search            │
└──────────────────────────────────────────────────────────┘
```

### Key Elements
- [D] = David, [A] = Austin (assignee initials in colored circle)
- 💬 2 = comment count badge
- 🔄 = recurring task indicator
- Description preview as smaller gray text below title

### Keyboard Shortcuts
| Key | Action |
|-----|--------|
| 1-4 | Switch project/filter |
| ↑↓ | Navigate tasks |
| Space | Complete task |
| Enter | Expand/Edit |
| n | New task |
| Tab | Cycle date filters |

### Why It Works
- Information dense - more tasks visible
- Professional look for serious work
- You learn shortcuts naturally over time
- Linear's genius: shortcuts appear contextually

---

## 🎨 Option 2: "Superhuman Speed"

**Inspired by:** Superhuman email (the $30/month email app power users love)

**Philosophy:** Maximum speed, zero clutter, every pixel earns its place

### Visual Style
- Pure black background (#0a0a0a)
- High contrast white text
- NO decorative elements
- Single accent color for selection only
- Thin, elegant typography

### Layout
```
┌──────────────────────────────────────────────────────────┐
│  ⌘K Search...                              ● Synced     │
├──────────────────────────────────────────────────────────┤
│  1 INBOX        2 SALON        3 TODAY        4 OVERDUE │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  → Warm oil in hot towel machine          D    Nov 7    │
│    Follow up on supplier contact                        │
│                                                          │
│    MAC USA                                 A    Nov 8    │
│                                                          │
│    Make Badges                            🔄   Nov 9    │
│                                                          │
│    Training                                    Nov 12   │
│                                                          │
│    1-on-1's                                    Nov 18   │
│                                                          │
├──────────────────────────────────────────────────────────┤
│  j/k move   x done   e edit   ? help                    │
└──────────────────────────────────────────────────────────┘
```

### Key Elements
- Command bar at top (⌘K to search anything)
- NO card borders - just rows with subtle separators
- Arrow (→) shows current selection
- Assignee as single letter, right-aligned
- Vim-style navigation (j/k)

### Keyboard Shortcuts
| Key | Action |
|-----|--------|
| 1-4 | Switch category instantly |
| j/k | Move up/down (vim style) |
| x | Mark done |
| e | Edit task |
| ⌘K | Command palette (search anything) |
| ? | Show all shortcuts |

### Why It Works
- Superhuman users report 4+ hours saved per week
- No mouse needed - ever
- Feels like flying through tasks
- Dark theme reduces eye strain
- Command palette means you never need to memorize

---

## 🎨 Option 3: "Things Minimal"

**Inspired by:** Things 3 (Apple Design Award winner)

**Philosophy:** Beautiful simplicity, focus on ONE thing at a time

### Visual Style
- Soft dark gray background (not pure black)
- Generous whitespace / padding
- Rounded, friendly elements
- Subtle shadows for depth
- Calming color palette

### Layout
```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│     Inbox                              34 tasks    ●     │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                                                          │
│     ┌────────────────────────────────────────────────┐   │
│     │  ○  Warm oil in hot towel machine              │   │
│     │      Nov 7 · David · 🔄                        │   │
│     │                                                │   │
│     │      "Remember to check temperature first"     │   │
│     │                                                │   │
│     │      ▸ 2 subtasks                              │   │
│     └────────────────────────────────────────────────┘   │
│                                                          │
│     ┌────────────────────────────────────────────────┐   │
│     │  ○  MAC USA                                    │   │
│     │      Nov 8 · Austin                            │   │
│     └────────────────────────────────────────────────┘   │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                    ← Inbox   Salon →                     │
└──────────────────────────────────────────────────────────┘
```

### Key Elements
- ONE expanded "focus" card at a time
- Other tasks shown as compact rows
- Swipe-style navigation hint at bottom
- Metadata on second line (date · assignee · icons)
- Full description visible on focused task

### Keyboard Shortcuts
| Key | Action |
|-----|--------|
| ←→ | Switch projects |
| ↑↓ | Navigate tasks |
| Space | Complete |
| Enter | Focus/Expand task |
| Esc | Collapse to list |
| n | New task |

### Why It Works
- Apple Design Award winner for a reason
- Reduces overwhelm - see one thing fully
- Beautiful = you want to use it
- Gentle on the eyes for long sessions
- "Zen mode" for task management

---

## 📊 Comparison Summary

| Aspect | Linear Focus | Superhuman Speed | Things Minimal |
|--------|--------------|------------------|----------------|
| Density | High | Very High | Low |
| Learning Curve | Medium | Higher | Easy |
| Visual Style | Professional | Hacker/Power | Beautiful/Calm |
| Best For | Daily work | Speed demons | Focus sessions |
| Tasks Visible | 6-8 | 8-10 | 3-4 |
| Vibe | "Get stuff done" | "I am speed" | "One thing at a time" |

---

## My Recommendation

For your use case (800x480 Pi screen, salon + personal tasks, shared with Austin):

**Option 1 (Linear Focus)** is probably the best fit because:
1. Good information density for small screen
2. Project tabs work perfectly for Inbox vs Salon
3. Professional look matches business use
4. Assignee initials solve the "whose task?" problem
5. Not too minimal (you need to see multiple tasks)
6. Not too dense (still readable on small screen)

But if you want to feel like a power user: **Option 2**
If you want something calming and beautiful: **Option 3**

What speaks to you?
