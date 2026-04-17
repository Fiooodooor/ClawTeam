---
name: klocwork-ci-integrator
description: "Run Klocwork static analysis in CI pipelines with kwinject/kwbuildproject/kwadmin load cycle. Supports MEV NSL and general projects, license server configuration, and result querying. Use when: setting up Klocwork CI jobs, running local Klocwork analysis, querying Klocwork server for issues, or generating Klocwork reports."
argument-hint: "Project name, project directory, build name, and MEV project type"
---

# Klocwork CI Integrator

Runs the full Klocwork static analysis lifecycle in CI: inject build commands, analyze, and upload results to the Klocwork server.

## Source

Based on: `tools/scripts/klocwork/` (12 files: `run_kw.sh`, `install_kw.sh`, `kwquery.py`, `parse_create_kw_report.py`, `run_kw_locally.sh`, and configs)

## When to Use

- Setting up Klocwork in a CI/CD pipeline
- Running Klocwork analysis locally for pre-commit checks
- Querying Klocwork server for existing issues
- Generating Klocwork defect reports
- Installing Klocwork tools on build agents

## Parameters (`run_kw.sh`)

| # | Parameter | Description |
|---|-----------|-------------|
| 1 | `project_name` | Klocwork project name (e.g., `MEV_NSL`) |
| 2 | `project_dir` | Path to project source directory |
| 3 | `build_name` | Build identifier for this run |
| 4 | `project_to_link` | Project to link results to |
| 5 | `output_dir_log` | Directory for log output |
| 6 | `mev_project` | MEV project variant (e.g., `MEV_TS`, optional) |

## Server Configuration

| Setting | Value |
|---------|-------|
| KW Server | `gkvkw004.igk.intel.com:8080` |
| License Server | `klocwork05p.elic.intel.com:7500` |
| Sync Server | `klocwork-igk2.devtools.intel.com` |
| Auth Token | `~/klocwork/ltoken` |

## Klocwork Analysis Lifecycle

```bash
# 1. Sync with server
kwxsync --url "https://$KW_SYNC_SERVER:$KW_SERVER_PORT" $project
kwdeploy sync --url "https://$KW_SERVER:$KW_SERVER_PORT"

# 2. Inject build commands
# For MEV_NSL projects:
kwinject --output kwinject.out sh build/nsl_build_release_imc.sh
kwinject --output kwinject.out sh build/nsl_build_release_imc_llvm.sh
# For MEV_TS variant:
kwinject --output kwinject.out sh build/nsl_build_release_imc.sh -t mev_ts
# For other projects:
kwinject --output kwinject.out sh mev_imc_build_all.sh

# 3. Build analysis database
kwbuildproject kwinject.out \
  --project $project \
  --host $KW_SERVER --port $KW_SERVER_PORT --ssl \
  --license-host $KW_LICENSE_SERVER --license-port $KW_LICENSE_SERVER_PORT \
  --tables-directory "KW" \
  --force -j auto

# 4. Upload results (with retry)
for i in 1 2 3 4 5; do
  kwadmin --host $KW_SERVER --port $KW_SERVER_PORT --ssl \
    load $project KW --name "$build_name" --force
  [ $? -eq 0 ] && break
  sleep 30
done
```

## Companion Scripts

- **`install_kw.sh`** — Downloads and installs Klocwork tools on build agents
- **`kwquery.py`** — Queries the Klocwork server API for issues by project/build
- **`parse_create_kw_report.py`** — Generates formatted defect reports from query results
- **`run_kw_locally.sh`** — Runs Klocwork analysis locally without server upload

## Usage

```bash
# CI pipeline run
./run_kw.sh MEV_NSL /path/to/project "build-123" MEV_NSL /logs MEV_TS

# Local analysis
./run_kw_locally.sh /path/to/project

# Query issues
python kwquery.py --project MEV_NSL --build "build-123"
```

## Troubleshooting

- **`kwadmin load` fails**: Script retries 5 times with 30s delays; check server connectivity
- **License errors**: Verify `~/klocwork/ltoken` exists and is valid
- **No issues captured**: Ensure `kwinject` wraps the actual build command
