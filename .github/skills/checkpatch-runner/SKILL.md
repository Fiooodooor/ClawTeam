---
name: checkpatch-runner
description: "Run Linux kernel checkpatch.pl style checker against firmware source files for MEV, MMG, or FW-ROW (NSC) projects. Enforces coding style with project-specific ignore lists. Use when: checking code style compliance before commit, running checkpatch in CI, or validating firmware source files against kernel coding standards."
argument-hint: "Project type (mev|mmg|nsc) and file path(s) to check"
---

# Checkpatch Runner

Runs the Linux kernel `checkpatch.pl` style checker against firmware source files with project-specific configurations and ignore lists.

## Source

Based on: VS Code tasks in `tools/.vscode/tasks.json` (MEV Checkpatch, MMG Checkpatch, FW-ROW Checkpatch)

## When to Use

- Checking code style compliance before committing changes
- Running style checks in CI pipelines
- Validating firmware source files against Linux kernel coding standards
- Pre-push code quality gate

## Prerequisites

- `imc_setenv` sourced for the target project
- Checkpatch.pl script available at the project-specific path

## Script Locations

| Project | Script Path |
|---------|-------------|
| MEV | `$IMC_TOOLS_ROOT/CI_Tools/checkpatch/MEV-TS-Linux/checkpatch.pl` |
| MMG | `$IMC_TOOLS_ROOT/CI_Tools/checkpatch/MMG/checkpatch.pl` |
| FW-ROW (NSC) | `$IMC_CI_CONFIG_TOOLS_DIR/ci_project_scripts/common/checkpatch/checkpatch.pl` |

## Usage

```bash
# MEV
source imc_setenv mev
$IMC_TOOLS_ROOT/CI_Tools/checkpatch/MEV-TS-Linux/checkpatch.pl \
    --show-types --strict --file <FILE_PATH> \
    --root /var/linux-worldread \
    --ignore ,GERRIT_CHANGE_ID,FILE_PATH_CHANGES,...

# MMG
source imc_setenv mmg
$IMC_TOOLS_ROOT/CI_Tools/checkpatch/MMG/checkpatch.pl \
    --show-types --strict --file <FILE_PATH> \
    --root /var/linux-worldread \
    --ignore ,GERRIT_CHANGE_ID,FILE_PATH_CHANGES,...

# NSC / FW-ROW
source imc_setenv nsc
$IMC_CI_CONFIG_TOOLS_DIR/ci_project_scripts/common/checkpatch/checkpatch.pl \
    --show-types --strict --file <FILE_PATH> \
    --root /var/linux-worldread \
    --ignore ,GERRIT_CHANGE_ID,FILE_PATH_CHANGES,...
```

## Ignored Check Types

All project variants share the same ignore list:

| Ignored Type | Reason |
|-------------|--------|
| `GERRIT_CHANGE_ID` | Not applicable outside Gerrit |
| `FILE_PATH_CHANGES` | Expected in firmware repos |
| `GIT_COMMIT_ID` | Not enforced |
| `REDUNDANT_CODE` | False positives in firmware |
| `SPDX_LICENSE_TAG` | Project uses different license format |
| `VOLATILE` | Legitimate use in hardware register access |
| `PREFER_KERNEL_TYPES` | Firmware uses standard C types |
| `MISSING_SIGN_OFF` | Sign-off not required in all workflows |
| `COMMIT_MESSAGE` | Checked separately by commit-message-validator |
| `NO_AUTHOR_SIGN_OFF` | Not enforced |
| `BAD_SIGN_OFF` | Not enforced |
| `CONSTANT_COMPARISON` | Style preference |
| `DIFF_IN_COMMIT_MSG` | N/A for file checks |
| `NOT_UNIFIED_DIFF` | N/A for file checks |
| `PREFER_ALIGNED` | Style preference |
| `CAMELCASE` | Legitimate in firmware APIs |
| `EMBEDDED_FUNCTION_NAME` | Legitimate in debug macros |
| `UNDOCUMENTED_DT_STRING` | No device tree usage |
| `UNNECESSARY_PARENTHESES` | Clarity preference in firmware |
| `NEW_TYPEDEFS` | Allowed in firmware code |

## Flags

| Flag | Purpose |
|------|---------|
| `--show-types` | Show the check type name with each message |
| `--strict` | Enable stricter checks |
| `--file` | Check a specific file (not a patch) |
| `--root` | Set the root directory for includes resolution |
| `--ignore` | Comma-separated list of check types to skip |
