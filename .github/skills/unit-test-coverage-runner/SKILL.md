---
name: unit-test-coverage-runner
description: "Run Ceedling unit tests with Bullseye code coverage on Linux. Handles coverage instrumentation (cov01), test selection, HTML report generation (bullshtml), and COVFILE management. Use when: running unit tests with coverage, generating HTML coverage reports, configuring Ceedling test projects, or troubleshooting Bullseye coverage setup."
argument-hint: "Running directory path, relative path to root, YML project file, and optional test name"
---

# Unit Test Coverage Runner

Runs Ceedling-based unit tests with Bullseye code coverage instrumentation on Linux, producing HTML coverage reports.

## Source

Based on: `tools/scripts/unit_test/` (5 files: `common_run_utest_linux.sh`, `common_run_utest_windows.bat`, `run_fuzz_test.sh`, and helpers)

## When to Use

- Running unit tests with code coverage metrics
- Generating HTML coverage reports via Bullseye
- Selecting and running individual test suites
- CI pipeline unit test + coverage stages
- Troubleshooting Bullseye coverage instrumentation

## Prerequisites

- **Ceedling** installed and accessible in PATH
- **BullseyeCoverage** installed at `/opt/BullseyeCoverage/`
- YML project file for Ceedling configuration

## Parameters

| # | Parameter | Description |
|---|-----------|-------------|
| 1 | `RUNNING_DIRECTORY_PATH` | Directory containing the test project |
| 2 | `RELATIVE_PATH_TO_ROOT` | Relative path from running dir to workspace root |
| 3 | `YML_PROJECT_FILE` | Ceedling YAML project file name |
| 4 | `TEST_NAME` | Specific test to run (empty = all tests) |

## Usage

```bash
# Run all tests with coverage
./common_run_utest_linux.sh ./tests ../.. project.yml ""

# Run specific test
./common_run_utest_linux.sh ./tests ../.. project.yml test_module_name

# Disable coverage
APPLY_COVERAGE=no ./common_run_utest_linux.sh ./tests ../.. project.yml ""
```

## Workflow

```bash
# 1. Setup
export CEEDLING_MAIN_PROJECT_FILE=$RUNNING_DIR/$YML_PROJECT_FILE
export COVFILE=$RUNNING_DIR/build/test.cov
PATH=/opt/BullseyeCoverage/bin:$PATH

# 2. Clean previous build
rm -rf $RUNNING_DIR/build

# 3. Enable Bullseye instrumentation
cov01 -1    # Turn on coverage instrumentation

# 4. Run tests
ceedling test:all --logging --trace
# or for specific test:
ceedling test:$TEST_NAME --logging --trace

# 5. Generate HTML report
covselect --import $COVFILE    # Import coverage data
bullshtml.sh $HTML_REPORT_DIR  # Generate HTML report

# 6. Disable instrumentation
cov01 --off
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APPLY_COVERAGE` | `yes` | Set to `no` to skip coverage |
| `COVFILE` | `$RUNNING_DIR/build/test.cov` | Path to Bullseye coverage file |
| `ETH_FW_COMPILER` | `covc` | Compiler wrapper for coverage |

## Coverage Reports

HTML reports are generated at `$RUNNING_DIRECTORY_PATH/build/html_report/` using Bullseye's `bullshtml.sh` tool.

## Additional Scripts

- **`run_fuzz_test.sh`** — Runs fuzz testing (separate from unit test coverage)
- **`common_run_utest_windows.bat`** — Windows equivalent using same Ceedling/Bullseye workflow

## Troubleshooting

- **`cov01 failed`**: Check Bullseye license at `/opt/BullseyeCoverage/`
- **No coverage data**: Ensure `APPLY_COVERAGE=yes` and `cov01 -1` succeeded before test run
- **Missing tests**: Verify `CEEDLING_MAIN_PROJECT_FILE` points to correct YML
