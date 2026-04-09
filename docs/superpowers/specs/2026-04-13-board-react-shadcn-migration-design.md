# Board Frontend Migration: React + Tailwind + shadcn

**Date:** 2026-04-13
**Status:** Approved
**Scope:** Migrate `clawteam/board/static/index.html` from vanilla JS to React + Tailwind + shadcn

## Goal

Replace the 1,244-line vanilla HTML/CSS/JS board with a React application using Vite, Tailwind CSS, and shadcn/ui components. Achieve full feature parity with the current board. Redesign the visual identity to communicate "mission control" rather than generic kanban.

The Python HTTP server (`clawteam/board/server.py`) stays unchanged as the API backend. The React app builds to `clawteam/board/static/` so the server serves it without modification (one small addition: serve `/assets/*` for bundled JS/CSS).

## Approach

**Approach A: Co-located frontend.** React source lives in `clawteam/board/frontend/`, Vite builds output to `clawteam/board/static/`. Frontend and server are one unit.

## Project Structure

```
clawteam/board/frontend/
├── package.json
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── components.json          # shadcn config
├── index.html               # Vite entry
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── lib/
│   │   ├── utils.ts         # shadcn cn() helper
│   │   └── api.ts           # fetch wrappers for mutations
│   ├── hooks/
│   │   └── use-team-stream.ts  # SSE EventSource hook
│   ├── components/
│   │   ├── ui/              # shadcn primitives (button, dialog, select, etc.)
│   │   ├── sidebar.tsx
│   │   ├── summary-bar.tsx
│   │   ├── kanban/
│   │   │   ├── board.tsx
│   │   │   ├── column.tsx
│   │   │   └── task-card.tsx
│   │   ├── peek-panel.tsx
│   │   ├── agent-registry.tsx
│   │   ├── message-stream.tsx
│   │   └── modals/
│   │       ├── inject-task.tsx
│   │       ├── set-context.tsx
│   │       ├── add-agent.tsx
│   │       └── send-message.tsx
│   └── types.ts             # TypeScript types matching API shapes
```

## Visual Identity: Mission Control

**Color system:**
- Near-black base (zinc-950 `#09090b`) with subtle warm undertones
- Status colors are the primary palette: amber (pending), blue (in progress), violet (awaiting approval), emerald (completed), cyan (verified), red (blocked)
- No single brand accent — the board "lights up" as work progresses through status stages
- Text hierarchy via zinc shades (zinc-50, zinc-400, zinc-500)

**Typography:**
- Inter for UI text
- JetBrains Mono for task IDs, timestamps, data values

**Key treatments:**
- Stat cards act like instrument gauges — large numbers, status-colored, subtle glow on non-zero values
- Kanban columns have a colored top border (status LEDs) but otherwise stay muted
- Task cards are minimal at rest, elevate on hover with faint status-colored border glow
- Peek panel uses shadcn Sheet (slides from right), keeps board visible
- Sidebar is narrow, dark, utilitarian
- Message stream uses monospace for content, type badges color-coded

**Avoids:** glassmorphism/blur, animated orbs, gradients on surfaces, over-rounded corners.

**Overall feel:** Dark, data-dense, calm. Terminal meets dashboard.

## Component Architecture & Data Flow

### State Management

No external library. Single data source (SSE stream), flat state shape. React context + useReducer.

```
SSE stream (/api/events/{team})
    |
useTeamStream(teamName) hook
    |  parses JSON, diffs against last snapshot
TeamContext provider (at App root)
    |  provides: team, members, tasks, taskSummary, messages, isConnected
Components read from context, dispatch API calls directly
```

### useTeamStream Hook

- Opens EventSource when teamName changes, closes on cleanup
- Parses each SSE data payload into typed state
- Diffs against previous payload to skip no-op renders
- Exposes isConnected boolean from onopen/onerror events

### API Layer (lib/api.ts)

Thin fetch wrappers for mutations:
- `createTask(team, {subject, owner})` — POST `/api/team/{name}/task`
- `updateTask(team, taskId, fields)` — PATCH `/api/team/{name}/task/{id}`
- `addMember(team, {name, agentType})` — POST `/api/team/{name}/member`
- `sendMessage(team, {to, content, summary})` — POST `/api/team/{name}/message`
- `fetchProxy(url)` — GET `/api/proxy?url=...`

No optimistic updates. SSE stream reflects changes within ~2s polling interval.

### Component Map

| Component | shadcn components | Notes |
|---|---|---|
| Sidebar | Select | Team picker, connection status dot |
| SummaryBar | Card | 6 stat cards with status colors |
| Board | — | @dnd-kit DndContext + SortableContext per column |
| Column | — | Drop target, header with count badge |
| TaskCard | Badge, Avatar | Draggable, click opens peek, owner assignment popover |
| PeekPanel | Sheet, Input, Textarea, Select | Slide-in editor, auto-save on blur/change |
| AgentRegistry | Card, Avatar, Badge | Member list, click opens send-message dialog |
| MessageStream | Badge, ScrollArea | Reverse-chronological, type-colored badges |
| InjectTaskDialog | Dialog, Input, Select | Create task |
| SetContextDialog | Dialog, Input, Textarea, Select | URL fetch + text input |
| AddAgentDialog | Dialog, Input, Select | Name + agent type |
| SendMessageDialog | Dialog, Textarea | Target pre-filled from agent click |

### Drag-and-Drop

- `@dnd-kit/core` for DndContext + collision detection
- `@dnd-kit/sortable` for within-column reordering and cross-column moves
- On drop: PATCH task with new status
- Ghost card: dashed border + reduced opacity

## API Response Shapes

### GET /api/overview
```json
[{
  "name": "string",
  "description": "string",
  "leader": "string",
  "members": 0,
  "tasks": 0,
  "pendingMessages": 0
}]
```

### GET /api/team/{name} and SSE /api/events/{name}
```json
{
  "team": { "name": "string", "leaderName": "string", "description": "string" },
  "members": [{
    "name": "string",
    "agentId": "string",
    "agentType": "string",
    "joinedAt": "string",
    "memberKey": "string",
    "inboxName": "string",
    "inboxCount": 0,
    "user": "string"
  }],
  "tasks": {
    "pending": [{ "id": "string", "subject": "string", "description": "string", "status": "string", "priority": "string", "owner": "string", "createdAt": "string", "blockedBy": ["string"] }],
    "in_progress": [],
    "awaiting_approval": [],
    "completed": [],
    "verified": [],
    "blocked": []
  },
  "taskSummary": {
    "pending": 0, "in_progress": 0, "awaiting_approval": 0,
    "completed": 0, "verified": 0, "blocked": 0, "total": 0
  },
  "messages": [{
    "from": "string", "to": "string", "type": "string",
    "fromLabel": "string", "toLabel": "string",
    "isBroadcast": false, "content": "string", "timestamp": "string"
  }]
}
```

## Server Integration

### Production
`npm run build` in `frontend/` outputs to `../static/`:
```
clawteam/board/static/
├── index.html
└── assets/
    ├── index-[hash].js
    └── index-[hash].css
```

Server needs one addition: serve `/assets/*` files from `static/assets/` with correct MIME types.

### Development
Two terminals:
1. `clawteam board serve` — Python API on port 8080
2. `npm run dev` — Vite on port 5173, proxy `/api/*` to `localhost:8080`

### Dependencies
- react, react-dom
- @dnd-kit/core, @dnd-kit/sortable, @dnd-kit/utilities
- tailwindcss, @tailwindcss/vite
- shadcn/ui (CLI-installed components)
- typescript, vite, @vitejs/plugin-react

## Migration Strategy

Clean replacement. The current `index.html` is renamed to `index.vanilla.html` as rollback. Once the React version reaches parity, remove it.

## Feature Parity Checklist

1. Team selection + SSE — sidebar team picker, connection status indicator, real-time data stream
2. Summary stats — 6 status cards with correct counts, live updates
3. Kanban board — 6 columns, cards with ID/subject/owner/avatar, correct placement
4. Drag-and-drop — cross-column moves, PATCH on drop, SSE reflects change
5. Peek panel — click card opens sheet, edit title/description/status/priority/assignee, auto-save
6. Agent management — registry with inbox counts, add-agent dialog, click-to-message
7. Task + context injection — task dialog, context dialog with URL proxy fetch

## Not in Scope

- No new features beyond current board
- No routing (single page)
- No authentication
- No offline support
- No test suite (add later)
