---
name: plugins
description: "Skill for the Plugins area of clawteam. 17 symbols across 5 files."
---

# Plugins

17 symbols | 5 files | Cohesion: 82%

## When to Use

- Working with code in `clawteam/`
- Understanding how test_discover_empty, discover, get_info work
- Modifying plugins-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `clawteam/plugins/manager.py` | PluginManager, discover, get_info, load_from_module, load_from_entry_point (+3) |
| `tests/test_harness.py` | test_discover_empty, test_load_nonexistent_module, test_plugin_instantiation |
| `clawteam/plugins/base.py` | on_register, HarnessPlugin, on_unregister |
| `clawteam/cli/commands.py` | plugin_list, plugin_info |
| `clawteam/plugins/ralph_loop_plugin.py` | RalphLoopPlugin |

## Entry Points

Start here when exploring this area:

- **`test_discover_empty`** (Function) — `tests/test_harness.py:176`
- **`discover`** (Function) — `clawteam/plugins/manager.py:20`
- **`get_info`** (Function) — `clawteam/plugins/manager.py:83`
- **`plugin_list`** (Function) — `clawteam/cli/commands.py:4244`
- **`plugin_info`** (Function) — `clawteam/cli/commands.py:4268`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `PluginManager` | Class | `clawteam/plugins/manager.py` | 12 |
| `RalphLoopPlugin` | Class | `clawteam/plugins/ralph_loop_plugin.py` | 16 |
| `HarnessPlugin` | Class | `clawteam/plugins/base.py` | 12 |
| `test_discover_empty` | Function | `tests/test_harness.py` | 176 |
| `discover` | Function | `clawteam/plugins/manager.py` | 20 |
| `get_info` | Function | `clawteam/plugins/manager.py` | 83 |
| `plugin_list` | Function | `clawteam/cli/commands.py` | 4244 |
| `plugin_info` | Function | `clawteam/cli/commands.py` | 4268 |
| `test_load_nonexistent_module` | Function | `tests/test_harness.py` | 182 |
| `load_from_module` | Function | `clawteam/plugins/manager.py` | 90 |
| `load_from_entry_point` | Function | `clawteam/plugins/manager.py` | 111 |
| `load_all_from_config` | Function | `clawteam/plugins/manager.py` | 125 |
| `on_register` | Function | `clawteam/plugins/base.py` | 24 |
| `test_plugin_instantiation` | Function | `tests/test_harness.py` | 332 |
| `unload` | Function | `clawteam/plugins/manager.py` | 156 |
| `on_unregister` | Function | `clawteam/plugins/base.py` | 31 |
| `_instantiate_and_register` | Function | `clawteam/plugins/manager.py` | 138 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 4 calls |

## How to Explore

1. `gitnexus_context({name: "test_discover_empty"})` — see callers and callees
2. `gitnexus_query({query: "plugins"})` — find related execution flows
3. Read key files listed above for implementation details
