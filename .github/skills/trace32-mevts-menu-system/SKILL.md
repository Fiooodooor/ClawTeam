---
name: trace32-mevts-menu-system
description: "Trace32 (T32) CMM debug menu system for MEVTS (Xtensa) targets. Includes DAP configuration, debugger attach, source loading, dump collection, and menu distribution scripts. Use when: setting up Trace32 debug menus for MEVTS, distributing T32 scripts to validation teams, configuring DAP for Xtensa debug, or collecting debug dumps."
argument-hint: "Action: update (copy menus to T32 install) or upload (push to ladjfs)"
---

# Trace32 MEVTS Menu System

Manages and distributes Trace32 CMM debug menus for MEVTS (Xtensa CPU) silicon debug sessions.

## Source

Based on: `tools/debug_t32/` (CMM scripts, batch files, menu definitions)

## When to Use

- Setting up Trace32 debug menus for MEVTS targets
- Distributing debug scripts to SV/EMU teams without FW git access
- Configuring DAP (Debug Access Port) for Xtensa debug
- Collecting debug dumps from MEVTS targets
- Customizing Trace32 attach and load workflows

## Prerequisites

- **Trace32** installed at `C:\T32\demo\arc\scripts` (default path)
- Windows environment for batch scripts
- Network access to `ladjfs.jer.intel.com` for uploads

## Scripts

### Menu Management

| Script | Purpose |
|--------|---------|
| `update_mevts_menu.bat` | Copy menus from local folder to T32 install path |
| `upload_mevts_instalation_to_ladjfs.bat` | Upload menus to `ladjfs.jer.intel.com/hwfw/Software/Trace32/XtensaAddon/MEVTS` |

### CMM Debug Scripts

| Script | Purpose |
|--------|---------|
| `init_subcore.cmm` | Initialize test subcore |
| `MEVTS_Menues/menues.men` | Main menu definition |
| `MEVTS_Menues/Error_print.cmm` | Error printing utility |

### Generic Utilities (`MEVTS_Menues/Generic/`)

| Script | Purpose |
|--------|---------|
| `Attach.cmm` | Attach debugger to target |
| `DAP_config.cmm` | Configure Debug Access Port |
| `GetFilePath.cmm` | File path dialog |
| `LoadSource.cmm` | Load source files into debugger |
| `ShowDebug_info.cmm` | Display debug information |
| `TitleUpdate.cmm` | Update window titles |
| `UpdateScripts.cmm` | Update script references |

### Dump Utilities (`MEVTS_Menues/Dumps/General/`)

| Script | Purpose |
|--------|---------|
| `getDump.cmm` | Retrieve debug dump from target |
| `saveAllDebugInfo.cmm` | Save all debug info to files |

## Usage

```batch
REM Copy menus to local T32 installation
update_mevts_menu.bat

REM Upload menus to shared network location (for SV/EMU teams)
upload_mevts_instalation_to_ladjfs.bat
```

## Directory Structure

```
debug_t32/
├── init_subcore.cmm
├── update_mevts_menu.bat
├── upload_mevts_instalation_to_ladjfs.bat
└── MEVTS_Menues/
    ├── menues.men
    ├── Error_print.cmm
    ├── Generic/
    │   ├── Attach.cmm
    │   ├── DAP_config.cmm
    │   ├── GetFilePath.cmm
    │   ├── LoadSource.cmm
    │   ├── ShowDebug_info.cmm
    │   ├── TitleUpdate.cmm
    │   └── UpdateScripts.cmm
    └── Dumps/General/
        ├── getDump.cmm
        └── saveAllDebugInfo.cmm
```

## Notes

- Menus assume default T32 install path `C:\T32\demo\arc\scripts`
- Upload script distributes to teams without FW git permissions (SV, EMU)
- Network share: `ladjfs.jer.intel.com\hwfw\Software\Trace32\XtensaAddon\MEVTS`
