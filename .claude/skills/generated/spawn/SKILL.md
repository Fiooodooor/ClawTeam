---
name: spawn
description: "Skill for the Spawn area of clawteam. 131 symbols across 17 files."
---

# Spawn

131 symbols | 17 files | Cohesion: 61%

## When to Use

- Working with code in `clawteam/`
- Understanding how test_is_nanobot_command_accepts_docker_wrapper, build_resume_command, docker_wrapped_cli_name work
- Modifying spawn-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `clawteam/spawn/command_validation.py` | _docker_run_spec, docker_wrapped_cli_name, ensure_docker_workspace, ensure_docker_mount, ensure_docker_env (+19) |
| `clawteam/spawn/adapters.py` | PreparedCommand, prepare_command, _is_codex_noninteractive_command, is_nanobot_command, command_basename (+10) |
| `clawteam/spawn/wsh_backend.py` | _validate_path, _wait_for_wsh_block, _strip_ansi, _capture_block_output, _wait_for_cli_ready (+7) |
| `clawteam/spawn/tmux_backend.py` | _looks_like_codex_update_prompt, _dismiss_codex_update_prompt_if_present, inject_runtime_message, _inject_prompt_via_buffer, __init__ (+6) |
| `clawteam/cli/commands.py` | session_save, session_show, session_clear, _resolve_runtime_backend, runtime_inject (+5) |
| `tests/test_adapters.py` | test_is_nanobot_command_accepts_docker_wrapper, test_is_qwen_command, test_is_opencode_command, test_is_pi_command, test_is_interactive_cli_covers_all_known (+3) |
| `clawteam/spawn/profiles.py` | apply_profile, command_basename, _command_has_model_arg, _model_flag, _base_url_env_var (+3) |
| `clawteam/spawn/wsh_rpc.py` | WshRpcClient, is_connected, _send_request, send_input, send_signal (+3) |
| `clawteam/spawn/sessions.py` | SessionState, _sessions_root, SessionStore, save, load (+2) |
| `tests/test_spawn_backends.py` | test_build_docker_clawteam_runtime_includes_wrapper_venv_and_source, test_build_docker_clawteam_runtime_returns_none_for_non_absolute_binary, test_ensure_docker_bootstrap_script_writes_python_fallback, test_dismiss_codex_update_prompt_sends_enter, test_inject_prompt_via_buffer_uses_load_and_paste (+2) |

## Entry Points

Start here when exploring this area:

- **`test_is_nanobot_command_accepts_docker_wrapper`** (Function) — `tests/test_adapters.py:44`
- **`build_resume_command`** (Function) — `clawteam/spawn/keepalive.py:10`
- **`docker_wrapped_cli_name`** (Function) — `clawteam/spawn/command_validation.py:113`
- **`ensure_docker_workspace`** (Function) — `clawteam/spawn/command_validation.py:126`
- **`ensure_docker_mount`** (Function) — `clawteam/spawn/command_validation.py:144`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `PreparedCommand` | Class | `clawteam/spawn/adapters.py` | 22 |
| `SessionState` | Class | `clawteam/spawn/sessions.py` | 19 |
| `SessionStore` | Class | `clawteam/spawn/sessions.py` | 38 |
| `DockerClawteamRuntime` | Class | `clawteam/spawn/cli_env.py` | 57 |
| `StubRpcClient` | Class | `tests/test_spawn_backends.py` | 1459 |
| `WshRpcClient` | Class | `clawteam/spawn/wsh_rpc.py` | 12 |
| `NativeCliAdapter` | Class | `clawteam/spawn/adapters.py` | 30 |
| `test_is_nanobot_command_accepts_docker_wrapper` | Function | `tests/test_adapters.py` | 44 |
| `build_resume_command` | Function | `clawteam/spawn/keepalive.py` | 10 |
| `docker_wrapped_cli_name` | Function | `clawteam/spawn/command_validation.py` | 113 |
| `ensure_docker_workspace` | Function | `clawteam/spawn/command_validation.py` | 126 |
| `ensure_docker_mount` | Function | `clawteam/spawn/command_validation.py` | 144 |
| `ensure_docker_env` | Function | `clawteam/spawn/command_validation.py` | 161 |
| `normalize_spawn_command` | Function | `clawteam/spawn/command_validation.py` | 284 |
| `command_has_workspace_arg` | Function | `clawteam/spawn/command_validation.py` | 372 |
| `prepare_command` | Function | `clawteam/spawn/adapters.py` | 33 |
| `is_nanobot_command` | Function | `clawteam/spawn/adapters.py` | 191 |
| `test_is_qwen_command` | Function | `tests/test_adapters.py` | 21 |
| `test_is_opencode_command` | Function | `tests/test_adapters.py` | 28 |
| `test_is_pi_command` | Function | `tests/test_adapters.py` | 34 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `Node_spawn_workers → Config_path` | cross_community | 7 |
| `Node_spawn_workers → ClawTeamConfig` | cross_community | 7 |
| `Preset_generate_profile → AgentPreset` | cross_community | 7 |
| `Runtime_inject → Config_path` | cross_community | 7 |
| `Runtime_inject → ClawTeamConfig` | cross_community | 7 |
| `Update → Ensure_within_root` | cross_community | 6 |
| `Session_show → Config_path` | cross_community | 6 |
| `Session_show → ClawTeamConfig` | cross_community | 6 |
| `Lifecycle_on_exit → Config_path` | cross_community | 6 |
| `Lifecycle_on_exit → ClawTeamConfig` | cross_community | 6 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 46 calls |
| Cli | 13 calls |
| Harness | 3 calls |
| Workspace | 3 calls |
| Transport | 1 calls |
| Board | 1 calls |
| Team | 1 calls |

## How to Explore

1. `gitnexus_context({name: "test_is_nanobot_command_accepts_docker_wrapper"})` — see callers and callees
2. `gitnexus_query({query: "spawn"})` — find related execution flows
3. Read key files listed above for implementation details
