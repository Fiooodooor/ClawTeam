---
name: workspace
description: "Skill for the Workspace area of clawteam. 52 symbols across 13 files."
---

# Workspace

52 symbols | 13 files | Cohesion: 54%

## When to Use

- Working with code in `clawteam/`
- Understanding how is_git_repo, repo_root, current_branch work
- Modifying workspace-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `clawteam/workspace/manager.py` | __init__, checkpoint, merge_workspace, get_workspace, _find (+9) |
| `clawteam/workspace/git.py` | GitError, _run, is_git_repo, repo_root, current_branch (+7) |
| `clawteam/cli/commands.py` | workspace_checkpoint, workspace_merge, workspace_status, context_diff, workspace_cleanup |
| `clawteam/workspace/context.py` | _ws_manager, _agent_branch, _base_branch, agent_diff, agent_summary |
| `clawteam/workspace/conflicts.py` | _changed_lines, _compute_severity, check_conflicts, suggest_rebase |
| `clawteam/events/types.py` | BeforeWorkspaceMerge, TeamShutdown, AfterWorkspaceCleanup |
| `clawteam/mcp/tools/workspace.py` | workspace_agent_diff, workspace_agent_summary |
| `clawteam/workspace/models.py` | WorkspaceInfo, WorkspaceRegistry |
| `clawteam/workspace/__init__.py` | get_workspace_manager |
| `tests/test_workspace_manager.py` | test_create_workspace_deletes_stale_branch_even_when_worktree_missing |

## Entry Points

Start here when exploring this area:

- **`is_git_repo`** (Function) — `clawteam/workspace/git.py:25`
- **`repo_root`** (Function) — `clawteam/workspace/git.py:34`
- **`current_branch`** (Function) — `clawteam/workspace/git.py:39`
- **`create_worktree`** (Function) — `clawteam/workspace/git.py:47`
- **`list_worktrees`** (Function) — `clawteam/workspace/git.py:106`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `GitError` | Class | `clawteam/workspace/git.py` | 8 |
| `BeforeWorkspaceMerge` | Class | `clawteam/events/types.py` | 114 |
| `WorkspaceManager` | Class | `clawteam/workspace/manager.py` | 52 |
| `TeamShutdown` | Class | `clawteam/events/types.py` | 140 |
| `WorkspaceInfo` | Class | `clawteam/workspace/models.py` | 7 |
| `WorkspaceRegistry` | Class | `clawteam/workspace/models.py` | 20 |
| `AfterWorkspaceCleanup` | Class | `clawteam/events/types.py` | 122 |
| `is_git_repo` | Function | `clawteam/workspace/git.py` | 25 |
| `repo_root` | Function | `clawteam/workspace/git.py` | 34 |
| `current_branch` | Function | `clawteam/workspace/git.py` | 39 |
| `create_worktree` | Function | `clawteam/workspace/git.py` | 47 |
| `list_worktrees` | Function | `clawteam/workspace/git.py` | 106 |
| `diff_stat` | Function | `clawteam/workspace/git.py` | 124 |
| `checkpoint` | Function | `clawteam/workspace/manager.py` | 181 |
| `merge_workspace` | Function | `clawteam/workspace/manager.py` | 251 |
| `get_workspace` | Function | `clawteam/workspace/manager.py` | 291 |
| `commit_all` | Function | `clawteam/workspace/git.py` | 70 |
| `merge_branch` | Function | `clawteam/workspace/git.py` | 85 |
| `get_workspace_manager` | Function | `clawteam/workspace/__init__.py` | 9 |
| `workspace_checkpoint` | Function | `clawteam/cli/commands.py` | 3630 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Check_conflicts → Config_path` | cross_community | 10 |
| `Check_conflicts → ClawTeamConfig` | cross_community | 10 |
| `Cleanup_team → Config_path` | cross_community | 8 |
| `Node_package_patches → Config_path` | cross_community | 8 |
| `Node_package_patches → ClawTeamConfig` | cross_community | 8 |
| `Node_package_patches → Config_path` | cross_community | 8 |
| `Node_package_patches → ClawTeamConfig` | cross_community | 8 |
| `Cleanup_team → Ensure_within_root` | cross_community | 7 |
| `Cleanup_team → Validate_identifier` | cross_community | 7 |
| `Cleanup_team → WorkspaceRegistry` | cross_community | 7 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 17 calls |
| Cli | 3 calls |
| Examples | 2 calls |
| Tools | 1 calls |

## How to Explore

1. `gitnexus_context({name: "is_git_repo"})` — see callers and callees
2. `gitnexus_query({query: "workspace"})` — find related execution flows
3. Read key files listed above for implementation details
