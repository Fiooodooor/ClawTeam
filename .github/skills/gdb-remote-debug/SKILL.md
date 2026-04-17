---
name: gdb-remote-debug
description: "Start GDB server on a remote target (Simics VM or silicon) for firmware debug. Connects via SSH and launches gdbserver with ipumgmtd application. Use when: debugging ipumgmtd firmware remotely, attaching GDB to a Simics VM, or starting remote debug sessions on silicon targets."
argument-hint: "Target IP/hostname and init app modules (e.g., '-m 0x915cf -p 0x1000')"
---

# GDB Remote Debug

Starts a GDB server on a remote target device for firmware application debugging.

## Source

Based on: VS Code tasks in `tools/.vscode/tasks.json` (Run GDB Server, Run GDB Server Silicon)

## When to Use

- Debugging ipumgmtd firmware on a Simics VM
- Attaching GDB to a running firmware application on silicon
- Remote debug sessions through SSH tunnels

## Usage

### Simics Target (localhost)

```bash
ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no \
    -p 5022 root@localhost \
    nohup gdbserver :52345 /usr/bin/ipumgmtd -m 0x915cf
```

### Silicon Target (remote IP)

```bash
ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no \
    -p 5022 root@<TARGET_IP> \
    nohup gdbserver :52345 /usr/bin/ipumgmtd -m 0x915cf -p 0x1000
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| Target IP | `localhost` | IP address or hostname of the target |
| SSH Port | `5022` | SSH port (Simics default forwarding) |
| GDB Port | `52345` | Port gdbserver listens on |
| Modules | `-m 0x915cf` | Init app module flags |

## Connecting GDB Client

After gdbserver starts, connect from your GDB client:

```
(gdb) target remote <TARGET_IP>:52345
```

Or in VS Code `launch.json`:

```json
{
    "type": "cppdbg",
    "request": "launch",
    "MIMode": "gdb",
    "miDebuggerServerAddress": "localhost:52345",
    "program": "${workspaceFolder}/build/debug/bin/ipumgmtd_mmg"
}
```
