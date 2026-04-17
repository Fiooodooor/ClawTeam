---
name: header-self-containment-checker
description: "Validate that C/C++ header files are self-contained (compile standalone without implicit dependencies). Supports parallel checking, per-module compiler selection (GCC, ARM cross-compiler), CMake/Makefile include path parsing, and failure analysis. Use when: enforcing header hygiene, running header compliance checks in CI, or diagnosing include-order bugs."
argument-hint: "Module name(s) to check (e.g., atf, boot, nsl, shared) or --all"
---

# Header Self-Containment Checker

Validates that C/C++ header files compile standalone without relying on implicit include ordering or undeclared dependencies.

## Source

Based on: `tools/scripts/header_self_contained/` (9 files: `repo_check_headers.sh`, `check_header_self_contained.sh`, `parse_cmake.sh`, `parse_makefiles.sh`, `analyze_header_failures.sh`, and helpers)

## When to Use

- Enforcing header self-containment across firmware modules
- Running header compliance checks in CI pipelines
- Diagnosing include-order bugs in C/C++ projects
- Validating new headers before merge

## Prerequisites

- `WORKSPACE` environment variable must be set (via `source imc_setenv nsc`)
- Appropriate cross-compiler toolchain installed for target modules

## Supported Modules

| Module | Default Compiler | Source Path |
|--------|-----------------|-------------|
| `atf` | `aarch64-linux-gnu-gcc` | `$WORKSPACE/sources/imc/arm-tf` |
| `boot` | `gcc` | `$WORKSPACE/sources/imc/boot` |
| `infra-common` | `gcc` | `$WORKSPACE/sources/imc/infra_common` |
| `nsl` | `gcc` | `$WORKSPACE/sources/lan/nsl` |
| `physs-mmg` | `gcc` | `$WORKSPACE/sources/imc/physs/mmg` |
| `physs-mev` | `gcc` | `$WORKSPACE/sources/imc/physs/mev` |
| `shared` | `gcc` | `$WORKSPACE/sources/imc/imc_shared` |
| `userspace` | `aarch64-linux-gnu-gcc` | `$WORKSPACE/sources/imc/userspace` |
| `uboot` | `aarch64-linux-gnu-gcc` | `$WORKSPACE/sources/imc/u-boot` |
| `hifmc` | `gcc` | `$WORKSPACE/sources/imc/hifmc` |
| `hifmc_rom` | `gcc` | `$WORKSPACE/sources/imc/hifmc_rom` |
| `hif-shared` | `gcc` | `$WORKSPACE/sources/imc/hif-shared` |
| `mmg-pmu` | `gcc` | `$WORKSPACE/sources/imc/mmg_pmu` |
| `mev_hw` | `gcc` | `$WORKSPACE/sources/imc/mev_hw` |
| `mev_infra` | `gcc` | `$WORKSPACE/sources/imc/mev_infra` |

## Usage

```bash
# Check specific modules
./repo_check_headers.sh -d nsl -d shared

# Check all modules
./repo_check_headers.sh --all

# With parallel jobs
./repo_check_headers.sh -d nsl -j 8

# With failure analysis
./repo_check_headers.sh -d nsl --present-analysis
```

## Options

| Flag | Description |
|------|-------------|
| `-d <module>` | Select module to check (repeatable) |
| `--all` | Check all available modules |
| `-j <N>` | Parallel jobs (default: 4) |
| `--quiet` | Suppress verbose output |
| `--log-file <path>` | Write output to log file |
| `--output-dir <path>` | Directory for results |
| `--present-analysis` | Run `analyze_header_failures.sh` per module |
| `--report-missing-headers` | Report headers that are missing |

## How It Works

1. **Parse build system** — `parse_cmake.sh` and `parse_makefiles.sh` extract include paths (`-I` flags) from CMakeLists.txt and Makefiles
2. **Discover headers** — Finds all `.h` files in the module source tree
3. **Compile test** — For each header, generates a minimal `.c` file that only `#include`s that header, then compiles with the module's compiler and include paths
4. **Report** — Failed compilations indicate non-self-contained headers
5. **Analysis** — Optional `analyze_header_failures.sh` categorizes failures (missing includes, undefined types, etc.)

## Self-Containment Test

For each header `foo.h`, the checker creates:
```c
#include "foo.h"
```
And compiles with:
```bash
$COMPILER -fsyntax-only -c test.c $INCLUDE_FLAGS
```

A header is self-contained if this compilation succeeds without errors.

## Output

Results are written to `$OUTPUT_DIR/` with per-module reports showing:
- Total headers checked
- Pass/fail counts
- List of failing headers with compiler error messages
