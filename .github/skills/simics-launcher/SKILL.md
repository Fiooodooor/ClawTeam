---
name: simics-launcher
description: "Launch Simics virtual platform for MEV, MMG, or NSC/CNIC projects with automatic UART terminal connections. Configures run-at-once mode and opens telnet sessions to IMC, HIFMC, ACC, PMU, and PHYSS UART ports. Use when: starting Simics simulation sessions, connecting to simulated UART consoles, or running firmware in the Simics virtual platform."
argument-hint: "Project type (mev|mmg|nsc) and run-at-once mode (TRUE|FALSE)"
---

# Simics Launcher

Launches Intel Simics virtual platform simulations for MEV, MMG, or NSC/CNIC projects with automatic UART terminal connections.

## Source

Based on: VS Code tasks in `tools/.vscode/tasks.json` (Run Simics app, UART connections, composite Run Simics tasks)

## When to Use

- Starting a Simics simulation session for firmware development
- Connecting to simulated UART consoles (IMC, HIFMC, ACC, PMU, PHYSS)
- Running firmware in standalone Simics virtual platform mode
- Debug sessions requiring Simics + multiple UART terminals

## Prerequisites

- `imc_setenv` sourced for the target project (mev, mmg, or nsc)
- Simics installed at `$IMC_TOOLS_ROOT/simics/simics-workspace`
- Simics workspace properly configured with target scripts

## Launch Commands

### MEV Standalone

```bash
source imc_setenv mev
cd $IMC_TOOLS_ROOT/simics/simics-workspace
./simics -e "\$run_at_once=TRUE" targets/mev/run-mev-standalone.simics
```

### MMG Standalone

```bash
source imc_setenv mmg
cd $IMC_TOOLS_ROOT/simics/simics-workspace
./simics -e "\$run_at_once=TRUE" targets/mmg/run-mmg-standalone.simics
```

### NSC/CNIC Standalone

```bash
source imc_setenv nsc
cd $IMC_TOOLS_ROOT/simics/simics-workspace
./simics -e "\$run_at_once=TRUE" targets/cnic/run-cnic-standalone.simics
```

## UART Terminal Connections

After Simics starts, connect to UART consoles via telnet:

| Console | Port | Command |
|---------|------|---------|
| IMC | 5077 | `telnet localhost 5077` |
| HIFMC | 5111 | `telnet localhost 5111` |
| ACC | 5088 | `telnet localhost 5088` |
| PMU | 5099 | `telnet localhost 5099` |
| PHYSS | 5222 | `telnet localhost 5222` |

### Wait-for-ready pattern:

```bash
until telnet localhost 5077 2>/dev/null; do
    echo 'Waiting for simics telnet to be ready'
    sleep 1
done
```

## Composite Sessions

| Session | Simics Target | UART Terminals |
|---------|---------------|----------------|
| Run Simics (MEV) | MEV standalone | IMC |
| Run Simics (MMG) | MMG standalone | IMC, HIFMC, ACC, PMU, PHYSS |
| Run Simics (NSC) | NSC/CNIC standalone | IMC |

## Run-at-Once Mode

| Value | Behavior |
|-------|----------|
| `TRUE` | Simics starts execution immediately |
| `FALSE` | Simics starts paused (manual run required) |
