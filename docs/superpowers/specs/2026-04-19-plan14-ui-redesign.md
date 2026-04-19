# Plan 14: Terminal/Hacker UI Redesign

## Overview

Full redesign of FORGE's frontend from a modern SaaS look to a Terminal/Hacker aesthetic. Pure black backgrounds, Cyan (#00d4ff) accent, monospace typography throughout, zero rounded corners, dense information layout.

**Scope:** All pages — Home, Engagement, Finding Detail, PrintReport

---

## Design System

### Colors
- Background: `#050505` (pure black)
- Surface: `#020c10` (cards, panels)
- Border: `#0a2530` (standard), `#00d4ff` (accent border)
- Accent: `#00d4ff` (cyan — primary interactive/active)
- Text primary: `#cccccc`
- Text secondary: `#555555`
- Status running: `#00d4ff`
- Status complete: `#22c55e`
- Status pending: `#555555`
- Status gate: `#f59e0b`
- Severity critical: `#ef4444`
- Severity high: `#f97316`
- Severity medium: `#f59e0b`
- Severity low: `#22c55e`
- Severity info: `#555555`

### Typography
- Font family: `'Courier New', Courier, monospace` — applied globally
- No system-ui, no Inter, no rounded fonts anywhere
- Letter spacing on labels: `1px` to `3px`
- All status/label text: UPPERCASE

### Spacing & Shape
- Border radius: `0` everywhere (no rounding)
- Card borders: `1px solid #0a2530`, left accent: `2px solid <status-color>`
- Scrollbars: styled dark (webkit)

---

## Pages

### 1. Home (Dashboard)

**Layout:** Process table — like `ps aux` or `netstat`

**Header:**
```
FORGE    [v14.0 // offensive security platform]           [+ NEW]
```
- FORGE in cyan, `letter-spacing: 3px`, `font-size: 13px`
- Subtitle in `#1a4a5a`, small
- `+ NEW` button: transparent bg, `1px solid #00d4ff40`, cyan text

**Table:**
Columns: `STATUS | TARGET | TYPE | FINDINGS | DATE | —`
- Header row: `#1a4a5a`, `9px`, `letter-spacing: 1px`, bottom border
- Each row: grid with those columns, `border-bottom: 1px solid #05181f`
- STATUS: colored dot + text (`● RUNNING` cyan, `✓ COMPLETE` green, `⊘ GATE` amber, `○ PENDING` gray)
- TARGET: `#cccccc`, monospace
- TYPE: `#555555`
- FINDINGS: orange if critical count, else `#aaa`
- DATE: `#333333`
- Action column: inline text links (`[view]`, `[launch]`) in cyan

**Footer line:** `N engagement(s) loaded_` in `#00d4ff30`

**Empty state:** `> no engagements found. run + NEW to begin_`

---

### 2. Engagement Detail

**Header:**
```
← FORGE / target.com    [STATUS]    [PDF ↓]
```
- Back arrow link in dim cyan
- Status badge: left-bordered span

**Two-column layout (60/40 split):**

**Left — Swarm Monitor:**
- Header: `SWARM MONITOR` label + agent count badge
- Event log: scrollable, each line is `[HH:MM:SS] event_type: message`
- Event type colors: `agent_started`→cyan, `finding`→orange, `error`→red, `complete`→green, `info`→`#555`
- Bottom: live blinking cursor `_` when running

**Right — Findings:**
- Header: `FINDINGS` label + count
- Table columns: `SEV | VULNERABILITY | CONF`
- SEV: colored pill (no border-radius on pill — use `[CRIT]` text instead)
- Each row clickable → Finding Detail
- Empty state: `> no findings yet_`

**Human Gate Bar** (when status === 'gate'):
- Full-width bar at bottom: amber background `#f59e0b15`, amber border top
- Text: `⚠ HUMAN GATE — review required before proceeding`
- Two buttons: `[APPROVE]` (green outline) and `[REJECT]` (red outline)

---

### 3. Finding Detail

**Header:**
```
← target.com / SQL Injection    [CRITICAL]
```

**Metadata grid** (3-column):
```
SURFACE          CLASS            VERDICT
/api/users       injection        confirmed
```
Labels in `#1a4a5a`, values in `#ccc`

**Description block:**
- Label: `DESCRIPTION`
- Body text: `#aaa`, `font-size: 11px`

**Confidence bar:**
- Label: `CONFIDENCE // 97%`
- Progress bar: `1px solid #0a2530`, inner fill in cyan

**PoC Script** (if present):
- Cyan left-bordered block, `background: #020c10`
- `PRE / CODE` tag, text `#00d4ff`, small font

**Reproduction Steps** (if present):
- Ordered list, dim text

**Exploit** (if present):
- Amber left-bordered block
- Label `EXPLOIT SCRIPT` in amber

---

### 4. Print Report

Print report keeps its current structure but uses the terminal palette for headings and labels. No interactive elements. Page breaks between findings unchanged.

---

## Implementation Notes

- Apply global CSS reset: `* { border-radius: 0 !important; font-family: 'Courier New', Courier, monospace; }`
- Use a single `terminal.css` (or update `index.css`) with CSS variables for all colors
- All existing Tailwind classes replaced or overridden — either remove Tailwind or add a terminal theme layer
- Buttons: no box-shadow, no gradient, no transition except subtle opacity on hover
- Tables use CSS grid (not `<table>`) for column layout control
- Keep all existing API calls, routing, state management — this is purely a visual change

---

## Out of Scope

- No new features
- No routing changes
- No backend changes
- Print report functional behavior unchanged
