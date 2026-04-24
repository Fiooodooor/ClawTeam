<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **clawteam** (7533 symbols, 17662 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/clawteam/context` | Codebase overview, check index freshness |
| `gitnexus://repo/clawteam/clusters` | All functional areas |
| `gitnexus://repo/clawteam/processes` | All execution flows |
| `gitnexus://repo/clawteam/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |
| Work in the Site-assets area (1040 symbols) | `.claude/skills/generated/site-assets/SKILL.md` |
| Work in the Tests area (649 symbols) | `.claude/skills/generated/tests/SKILL.md` |
| Work in the Spawn area (131 symbols) | `.claude/skills/generated/spawn/SKILL.md` |
| Work in the Harness area (109 symbols) | `.claude/skills/generated/harness/SKILL.md` |
| Work in the Examples area (84 symbols) | `.claude/skills/generated/examples/SKILL.md` |
| Work in the Cli area (75 symbols) | `.claude/skills/generated/cli/SKILL.md` |
| Work in the Team area (68 symbols) | `.claude/skills/generated/team/SKILL.md` |
| Work in the Workspace area (52 symbols) | `.claude/skills/generated/workspace/SKILL.md` |
| Work in the Transport area (45 symbols) | `.claude/skills/generated/transport/SKILL.md` |
| Work in the Board area (34 symbols) | `.claude/skills/generated/board/SKILL.md` |
| Work in the Events area (29 symbols) | `.claude/skills/generated/events/SKILL.md` |
| Work in the Tools area (29 symbols) | `.claude/skills/generated/tools/SKILL.md` |
| Work in the Store area (18 symbols) | `.claude/skills/generated/store/SKILL.md` |
| Work in the Plugins area (17 symbols) | `.claude/skills/generated/plugins/SKILL.md` |
| Work in the Mcp area (14 symbols) | `.claude/skills/generated/mcp/SKILL.md` |
| Work in the Cluster_130 area (10 symbols) | `.claude/skills/generated/cluster-130/SKILL.md` |
| Work in the Templates area (7 symbols) | `.claude/skills/generated/templates/SKILL.md` |
| Work in the Cluster_131 area (4 symbols) | `.claude/skills/generated/cluster-131/SKILL.md` |

<!-- gitnexus:end -->
