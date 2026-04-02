---
name: coverity-ci-integrator
description: "Run Coverity static analysis in CI pipelines with multi-compiler support (ARM, NSC, Xtensa, Python). Handles cov-configure, cov-build, cov-analyze, cov-commit-defects cycle with CodeXM custom checkers. Use when: setting up Coverity CI jobs, debugging Coverity scan failures, creating Coverity reports, or configuring compiler templates."
argument-hint: "Compiler config type (arm|nsc|xtensa|python) and project/stream names"
---

# Coverity CI Integrator

Runs the full Coverity static analysis lifecycle in CI: configure compilers, build, analyze, and commit results to the Coverity server.

## Source

Based on: `tools/scripts/coverity/` (7 files: `run_coverity.sh`, `create_coverity_report.py`, `get_coverity_run_issues.py`, `install_coverity_for_local_runs.sh`, plus compiler configs)

## When to Use

- Setting up Coverity in a CI/CD pipeline
- Debugging Coverity scan/build failures
- Generating defect reports from Coverity runs
- Configuring Coverity for cross-compilation (ARM, Xtensa, NSC)
- Installing Coverity tools for local development runs

## Parameters

`run_coverity.sh` takes 12 positional parameters:

| # | Parameter | Description |
|---|-----------|-------------|
| 1 | `build_command` | Shell command to build the project |
| 2 | `project_name` | Coverity project name |
| 3 | `stream_name` | Coverity stream name |
| 4 | `project_dir` | Path to project source |
| 5 | `build_name` | Build identifier |
| 6 | `output_dir_log` | Directory for log output |
| 7 | `pipeline_build_url` | CI pipeline URL for traceability |
| 8 | `build_user_name` | Committer name |
| 9 | `build_user_mail` | Committer email |
| 10 | `config_type` | Compiler config: `arm`, `nsc`, `xtensa`, or `python` |
| 11 | `custom_checkers_dir` | Directory with `.cxm` CodeXM custom checkers |
| 12 | `additional_coverity_excludes` | Regex paths to exclude from analysis |

## Compiler Configurations

### ARM
```bash
cov-configure --template --config mev-coverity-config.xml --compiler arm --comptype armcc
cov-configure --template --config mev-coverity-config.xml --compiler aarch64-intel-linux-gcc --comptype gcc
cov-configure --template --config mev-coverity-config.xml --compiler aarch64-intel-linux-cpp --comptype g++
```

### NSC
```bash
cov-configure --template --config mev-coverity-config.xml --compiler arm --comptype armcc
cov-configure --template --config mev-coverity-config.xml --compiler aarch64-none-elf-gcc --comptype gcc
# Requires: /opt/arm-toolchain/arm-gnu-toolchain-14.2.rel1-x86_64-aarch64-none-elf/bin in PATH
```

### Xtensa
```bash
cov-configure --template --config xtensa-coverity.xml --compiler xt-clang --comptype xtclang
```

### Python
```bash
cov-configure --template --config python-coverity.xml --python
```

## Coverity Analysis Lifecycle

```bash
# 1. Configure compilers (see above)

# 2. Build with Coverity instrumentation
cov-build --config $config_file --dir cov-$stream $build_command

# 3. Analyze with custom checkers
cov-analyze --dir cov-$stream \
  --config $config_file \
  --strip-path $projectdir \
  --all \
  --disable-parse-warnings \
  --allow-unmerged-emits \
  $codexm_files \
  2>&1 | tee $output_dir_log/cov-results/cov-analyze-output.txt

# 4. Commit defects to server
cov-commit-defects --dir cov-$stream \
  --url $COV_SERVER \
  --stream $stream \
  --ssl \
  --scm git
```

## Server

- Production: `https://coverity.devtools.intel.com/prod8`
- Exclude paths default: `/usr/share/.*|/opt/Xtensa_Explorer/.*`

## Companion Scripts

- **`create_coverity_report.py`** — Generates HTML/CSV reports from Coverity results
- **`get_coverity_run_issues.py`** — Queries the Coverity server API for issues from a specific run
- **`install_coverity_for_local_runs.sh`** — Downloads and installs Coverity analysis tools locally

## Troubleshooting

- If `cov-build` captures no files: check compiler config matches the actual compiler used
- If `kwadmin load` fails: retry up to 5 times with 30s delays (built into script)
- Disk space: check with `df -h /srv` before analysis — Coverity intermediate files can be large
