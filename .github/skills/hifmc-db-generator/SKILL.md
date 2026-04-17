---
name: hifmc-db-generator
description: "Generate HIFMC database headers and autoload CSV files from the hifmc_db tool. Produces C header files for lib_hifmcdb and autoload configurations for NVM generator. Use when: regenerating HIFMC database headers, updating autoload configurations, or rebuilding NVM generator inputs for MMG Simics or HW targets."
argument-hint: "Action: generate-headers or generate-autoloads"
---

# HIFMC DB Generator

Generates HIFMC (Host Interface Management Controller) database headers and autoload CSV configurations from the `hifmc_db.py` tool.

## Source

Based on: VS Code tasks in `tools/.vscode/tasks.json` ((HIFMC_DB) Generate Headers, (HIFMC_DB) Generate ALs)

## When to Use

- Regenerating HIFMC database C header files after database changes
- Updating autoload (AL) CSV configurations for NVM generator
- Rebuilding NVM generator inputs for MMG Simics or hardware targets
- After modifying HIFMC database definitions

## Prerequisites

- Access to the `hifmc` workspace folder
- `hifmc_db.py` tool available in `hifmc/hifmc_db/`
- Output directories exist in `hif-shared/` and `nvm-generator-config/`

## Generate Headers

```bash
cd <hifmc_workspace>/hifmc_db
./hifmc_db.py -o ../../hif-shared/lib_hifmcdb/inc headless --generate-headers
```

Output: C header files in `hif-shared/lib_hifmcdb/inc/`

## Generate Autoloads

```bash
cd <hifmc_workspace>/hifmc_db
./hifmc_db.py -o ../../hif-shared/lib_hifmcdb/inc headless --generate-autoloads

# Copy ALs to NVM generator config for both Simics and HW targets
cp output/*.csv ../../nvm-generator-config/MMG/SIMICS/latest/FLASH_s/ALs/HIF/
cp output/*.csv ../../nvm-generator-config/MMG/HW/latest/FLASH_s/ALs/HIF/
```

Output: CSV files in `output/`, copied to:
- `nvm-generator-config/MMG/SIMICS/latest/FLASH_s/ALs/HIF/`
- `nvm-generator-config/MMG/HW/latest/FLASH_s/ALs/HIF/`

## hifmc_db.py Options

| Flag | Description |
|------|-------------|
| `-o <path>` | Output directory for generated files |
| `headless` | Run without interactive UI |
| `--generate-headers` | Generate C header files |
| `--generate-autoloads` | Generate autoload CSV configurations |
