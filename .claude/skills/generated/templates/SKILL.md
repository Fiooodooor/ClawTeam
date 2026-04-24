---
name: templates
description: "Skill for the Templates area of clawteam. 7 symbols across 2 files."
---

# Templates

7 symbols | 2 files | Cohesion: 82%

## When to Use

- Working with code in `clawteam/`
- Understanding how test_agent_def_defaults, test_task_def, test_template_def_defaults work
- Modifying templates-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `clawteam/templates/__init__.py` | AgentDef, TaskDef, TemplateDef, _parse_toml |
| `tests/test_templates.py` | test_agent_def_defaults, test_task_def, test_template_def_defaults |

## Entry Points

Start here when exploring this area:

- **`test_agent_def_defaults`** (Function) — `tests/test_templates.py:46`
- **`test_task_def`** (Function) — `tests/test_templates.py:52`
- **`test_template_def_defaults`** (Function) — `tests/test_templates.py:56`
- **`AgentDef`** (Class) — `clawteam/templates/__init__.py:23`
- **`TaskDef`** (Class) — `clawteam/templates/__init__.py:30`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `AgentDef` | Class | `clawteam/templates/__init__.py` | 23 |
| `TaskDef` | Class | `clawteam/templates/__init__.py` | 30 |
| `TemplateDef` | Class | `clawteam/templates/__init__.py` | 36 |
| `test_agent_def_defaults` | Function | `tests/test_templates.py` | 46 |
| `test_task_def` | Function | `tests/test_templates.py` | 52 |
| `test_template_def_defaults` | Function | `tests/test_templates.py` | 56 |
| `_parse_toml` | Function | `clawteam/templates/__init__.py` | 74 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Launch_team → FakeResponse` | cross_community | 5 |
| `Launch_team → AgentDef` | cross_community | 4 |
| `Launch_team → TaskDef` | cross_community | 4 |
| `Launch_team → TemplateDef` | cross_community | 4 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Transport | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_agent_def_defaults"})` — see callers and callees
2. `gitnexus_query({query: "templates"})` — find related execution flows
3. Read key files listed above for implementation details
