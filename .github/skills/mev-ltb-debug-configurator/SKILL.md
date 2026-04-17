---
name: mev-ltb-debug-configurator
description: "Automated MEV/MEVTS silicon debug environment setup using LTB (Lauterbach Trace32) configuration, FTDI device communication, DAP access port configuration, and CPU boot resume. Use when: setting up silicon debug sessions, configuring Trace32 for MEV/MEVTS hardware, automating LTB attach workflows, or resuming CPU boot after ROM halt."
argument-hint: "Project variant: mev or mev_ts"
---

# MEV LTB Debug Configurator

Automates the silicon debug environment setup for MEV/MEVTS projects: configures LTB (Lauterbach Trace32), FTDI devices, and resumes CPU boot to the ROM entry point.

## Source

Based on: `tools/debug_ltb_conf_scripts/` (5 files: `CfgDebugEnv.py`, `MEV_LTB_Debug.py`, `Configure_LTB.py`, `Resume_boot.py`, `t32api64.dll`)

## When to Use

- Setting up silicon debug sessions for MEV or MEVTS hardware
- Configuring Trace32 debugger via remote API for DAP access
- Automating LTB attach on A0 hardware
- Resuming CPU boot after halting at ROM entry

## Prerequisites

- **FTDI driver**: `pip install ftd2xx`
- **Trace32** installed (default: `C:\T32\`)
- **Intel-internal libraries**: `mtevans`, `ipccli`
- **Credentials**: Must be cached for unit unlock (see wiki)
- **Windows** environment (uses `t32api64.dll`)

## Usage

```bash
# MEV project
py CfgDebugEnv.py mev

# MEVTS on A0 hardware
py CfgDebugEnv.py mev_ts
```

## Three-Stage Workflow

### Stage 1 — Configure Environment (`MEV_LTB_Debug.py`)

- Communicates with FTDI devices via `ftd2xx` library
- Uses `mtevans.get_sv()` + `ipccli` for silicon register access
- For MEVTS A0: disables `erot_preset = 0` bit in `fuse_forse2` register
- Unlocks device via credentials

### Stage 2 — Configure Trace32 (`Configure_LTB.py`)

- Uses T32 Remote API (`t32api64.dll`)
- Loads CMM scripts via remote API calls
- Configures DAP (Debug Access Port) on ports 20000, 20010
- Attaches debugger to target CPU

### Stage 3 — Resume CPU (`Resume_boot.py`)

- Sets `tap_ctrl.resume0 = 1` and `resume1 = 1` flags
- CPU halts at Boot ROM first instruction (proof of success)
- Uses `ipc.unlock()` and `get_sv()` for register access

## Project Variants

| Variant | Parameter | Extra Steps |
|---------|-----------|-------------|
| MEV | `mev` | Standard LTB attach |
| MEVTS (A0 HW) | `mev_ts` | Disables erot_preset in fuse_forse2 register |

## Notes

- Windows-only (Trace32 Remote API DLL)
- Requires Intel-internal `mtevans` and `ipccli` libraries
- Credential caching recommended to avoid repeated unlock prompts
- Wiki: `https://wiki.ith.intel.com/pages/viewpage.action?pageId=2059015057`
