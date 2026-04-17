---
name: multi-repo-rebase-orchestrator
description: "Interactive multi-repository sync and rebase tool for repo-managed projects. Handles local change detection (stash or pause), parallel repo sync, and dev branch rebasing onto trunk. Supports mmg/nsc/mev project types. Use when: rebasing development branches across multiple repos, syncing multi-repo workspaces, or resolving rebase conflicts interactively."
argument-hint: "Project type (mmg|nsc|mev) or no argument for default (mmg)"
---

# Multi-Repo Rebase Orchestrator

Interactive tool for syncing and rebasing development branches across multiple repositories managed by Google's `repo` tool.

## Source

All scripts are bundled in `scripts/` within this skill directory:

| File | Description |
|------|-------------|
| `scripts/repo_sync_and_rebase.sh` | Main orchestrator — interactive sync + rebase workflow |
| `scripts/repos.conf` | Per-project repository list (one path per line) |
| `scripts/repo` | Google `repo` launcher v2.4 — bootstrapper for multi-repo manifest workspaces |

## When to Use

- Rebasing development branches onto updated trunk across multiple repos
- Syncing a multi-repo workspace before starting new work
- Handling local changes gracefully during sync (stash or pause)
- Working with mmg/nsc/mev project configurations

## Prerequisites

- `IMC_TOOLS_ROOT` environment variable set
- `repo` tool available on `$PATH` (a bundled copy is included — see below)
- `repos.conf` configuration file at `$IMC_TOOLS_ROOT/scripts/repo_rebase_tool/repos.conf`

### Bundled `repo` Launcher

The `scripts/repo` file is Google's standalone `repo` launcher (v2.4, Apache-2.0). It is **not** a general git clone tool — it bootstraps the full `git-repo` multi-repository management system by downloading it from `gerrit.googlesource.com/git-repo` into a local `.repo/` directory, with GPG signature verification.

Requires: Python 3.6+, Git 1.7.2+. Supports `REPO_URL` / `REPO_REV` env vars for internal mirror overrides.

```bash
# Install system-wide
install -m 755 scripts/repo /usr/local/bin/repo

# Or add to PATH for the current session
export PATH="$(dirname "$(realpath scripts/repo)"):$PATH"

# Then initialize a manifest workspace
repo init -u <MANIFEST_URL> -b <BRANCH>
repo sync -j8
```

## Usage

```bash
# Default (mmg project)
./repo_sync_and_rebase.sh

# Specific project
./repo_sync_and_rebase.sh nsc
./repo_sync_and_rebase.sh mev

# Show help
./repo_sync_and_rebase.sh --help
```

## Workflow

### Step 1 — Select repositories

Choose between:
- **Config file**: Read repos from `repos.conf` (pre-configured list)
- **Interactive selection**: Pick from `repo list` output (only `sources/` prefixed repos)

### Step 2 — Handle local changes

For each repo, the script checks for uncommitted modifications:
- Detects `modified:` status (excluding `new commits` and `modified content` submodule noise)
- Offers to **stash** changes or **pause** for manual intervention

### Step 3 — Sync

```bash
repo sync -j72  # Parallel sync with 72 jobs
```

### Step 4 — Rebase

For each selected repo:
1. Navigate to the repo directory
2. Identify the current dev branch
3. Rebase onto the updated trunk branch
4. Report success or conflict

## Configuration File (`repos.conf`)

One repo path per line, comments with `#`:
```
sources/imc/boot
sources/imc/imc_shared
sources/lan/nsl
# sources/imc/arm-tf  (disabled)
```

## Color-Coded Output

| Color | Meaning |
|-------|---------|
| Blue | Informational messages |
| Green | Success |
| Yellow | Warnings (local changes detected) |
| Red | Errors (rebase conflicts, missing config) |

## Troubleshooting

- **Rebase conflicts**: The script will pause and let you resolve manually
- **`IMC_TOOLS_ROOT` not set**: Run `source imc_setenv` first
- **`repos.conf` not found**: Create it at `$IMC_TOOLS_ROOT/scripts/repo_rebase_tool/repos.conf`
