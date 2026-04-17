---
name: security-flags-analyzer
description: "Scan build log files for security compilation flags (FORTIFY_SOURCE, stack-protector, relro, PIE, fPIC, Wformat). Use when: auditing build security posture, checking compiler hardening flags in Yocto/BitBake builds, generating security compliance reports from build logs."
argument-hint: "Path to build log directory or single log file to scan"
---

# Security Flags Analyzer

Scans build log files (`log.do_compile`) for security-related compilation flags and produces a CSV report.

## Source

Based on: `tools/scripts/compilation_flags/map_sec_flags.py`

## When to Use

- Auditing build security posture for compliance
- Checking that compiler hardening flags are applied across all compilation units
- Generating security compliance CSV reports from Yocto/BitBake build trees
- Verifying FORTIFY_SOURCE, stack protection, RELRO, and PIE flags

## Tracked Security Flags

| Flag | Purpose |
|------|---------|
| `D_FORTIFY_SOURCE=2` | Buffer overflow detection at compile/runtime |
| `relro` | Read-only relocations (GOT hardening) |
| `fstack-protector-strong` | Stack smashing protection |
| `Wformat -Wformat-security` | Format string vulnerability warnings |
| `O1` / `O2` / `O3` | Optimization levels (required for FORTIFY_SOURCE) |
| `PIE` | Position Independent Executable (ASLR support) |
| `fPIC` | Position Independent Code |

## Procedure

### Step 1 — Identify build log directory

Typically the Yocto `tmp/` build directory containing `log.do_compile` files:
```
/path/to/build/tmp/
```

### Step 2 — Run the analyzer

```python
import os
import re
import pandas as pd

LOG_DO_COMPILE = 'log.do_compile'

flags = [
    'D_FORTIFY_SOURCE=2',
    'relro',
    'fstack-protector-strong',
    'Wformat',
    'O1', 'O2', 'O3',
    'PIE',
    'fPIC'
]

build_dir = '/path/to/build/tmp'  # adjust to your build tree

log_files = []
for root, dirs, files in os.walk(build_dir):
    for file in files:
        if file.endswith(LOG_DO_COMPILE):
            log_files.append(os.path.join(root, file))

res = pd.DataFrame(columns=['log_file', 'compilation_file', 'flag'])
counter = 0
for file_path in log_files:
    with open(file_path, 'r') as log_file:
        for line in log_file:
            for flag in flags:
                if flag in line:
                    c_files = re.findall(r'/[^/]+\.[co]', line)
                    for f in c_files:
                        res.loc[counter] = [file_path, f, flag]
                        counter += 1

res.to_csv('security_flags_report.csv', index=False)
print(f"Scanned {len(log_files)} log files, found {counter} flag occurrences")
```

### Step 3 — Interpret results

- Files missing `D_FORTIFY_SOURCE=2` or `fstack-protector-strong` are high-priority remediation targets
- `PIE` should be present for all executables (not libraries — those use `fPIC`)
- `relro` (especially full RELRO with `-z relro -z now`) hardens the GOT

## Additional Tool

`map_w_args.py` in the same directory scans for warning-related flags (`-W` arguments).

## Output Format

CSV with columns: `log_file`, `compilation_file`, `flag`
