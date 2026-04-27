# Board + ClawTeam: End-to-End Usage Flow

How the ClawTeam CLI and the Board Web UI fit together, in the order a user actually touches them.

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Create a team (one-time)                                     │
│     $ clawteam team create my-swarm --description "..."          │
│     → writes config.json under .clawteam/teams/my-swarm/         │
├─────────────────────────────────────────────────────────────────┤
│  2. Add members (defines agent identities; not yet running)      │
│     $ clawteam team add my-swarm leader  --agent-type general    │
│     $ clawteam team add my-swarm coder-1 --agent-type coder      │
│     → appends members to config.json                             │
├─────────────────────────────────────────────────────────────────┤
│  3. Start the board (long-running monitoring UI)                 │
│     $ clawteam board serve --port 8080                           │
│     → open http://localhost:8080                                 │
├─────────────────────────────────────────────────────────────────┤
│  4. Spawn agents (they start running inside tmux)                │
│     $ clawteam launch my-swarm                                   │
│        or  clawteam spawn leader --team my-swarm --task "..."    │
│     → each member gets a tmux window running Claude Code         │
│     → only now are agents actually "online" — board badge        │
│       flips from "No agents" to "N/M online"                     │
├─────────────────────────────────────────────────────────────────┤
│  5. Human-in-the-loop collaboration (via the board)              │
│     • Inject Task     → new task for the swarm                   │
│     • Drag card       → change status (pending → in_progress)    │
│     • Click card      → peek panel; edit assignee / description  │
│     • Send Message    → push into a specific agent's inbox       │
│     • Set Context     → broadcast context to the whole team      │
│                                                                  │
│     Meanwhile, agents run autonomously in tmux: they execute     │
│     work, message each other, update task status.                │
│     The board SSE stream polls .clawteam/ every 2 s and          │
│     reflects changes live.                                       │
├─────────────────────────────────────────────────────────────────┤
│  6. Observe / shut down                                          │
│     $ clawteam board attach my-swarm      # attach to the tmux   │
│     $ clawteam lifecycle shutdown my-swarm                        │
└─────────────────────────────────────────────────────────────────┘
```

## Liveness signals on the board

Two independent indicators, do not confuse them:

| Indicator | Meaning |
|-----------|---------|
| Sidebar **"Stream live"** pill | The browser's SSE connection to the board server is up. Says nothing about agents. |
| Header **"N/M online"** badge | How many team members have a live tmux window. `No agents` = nothing is actually running — tasks you inject will sit untouched until you run `clawteam launch <team>`. |

## Data locations

- `.clawteam/teams/<team>/config.json` — team + member definitions
- `.clawteam/teams/<team>/inboxes/` — per-agent mailboxes
- `.clawteam/tasks/` — task store
- tmux session naming: `clawteam-<team_name>`, one window per member
