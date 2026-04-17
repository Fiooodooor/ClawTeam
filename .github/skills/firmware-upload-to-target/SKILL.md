---
name: firmware-upload-to-target
description: "Upload firmware libraries and applications from the build tree to a target device over SSH/SCP. Packages .so files into tarballs, transfers via SCP, and extracts on the target. Supports MEV Infra, Infra Common, and Init App (ipumgmtd) uploads. Use when: deploying firmware builds to Simics or silicon targets, uploading shared libraries for debug, or deploying ipumgmtd app variants."
argument-hint: "Target hostname/IP, project type (mmg|mev), and optional ipumgmtd variant"
---

# Firmware Upload to Target

Packages and uploads firmware libraries (.so files) and applications from the build tree to a remote target device over SSH.

## Source

Based on: VS Code tasks in `tools/.vscode/tasks.json` (Upload Infra, Upload Infra Common, Upload Init App, Upload All)

## When to Use

- Deploying freshly built firmware libraries to a Simics VM or silicon target
- Uploading MEV shared libraries for debug/testing
- Deploying ipumgmtd application variants (mmg, mmg_anvm, mev, mev_anvm)
- Replacing system libraries on a running target for rapid iteration

## Prerequisites

- `imc_setenv` sourced (provides `$MEV_INFRA_PATH`, `$IMC_INFRA_COMMON_LINUX_DIR`, etc.)
- SSH access to target on port 5022 (Simics default) or standard port
- Build completed (libraries exist in build tree)

## Workflows

### Upload Infra Libraries

```bash
source imc_setenv mmg
SCP_PARAMS="-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -r -P 5022"
SSH_PARAMS="-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -p 5022"
HOST_NAME=localhost  # or target IP

TEMP_DIR=$(mktemp -d)
find $MEV_INFRA_PATH -name "*.so*" -exec cp -P {} $TEMP_DIR \;
tar -czvf my_libs.tar.gz -C $TEMP_DIR .
scp $SCP_PARAMS my_libs.tar.gz root@$HOST_NAME:/tmp
ssh $SSH_PARAMS root@$HOST_NAME 'tar -xzvf /tmp/my_libs.tar.gz -C /usr/lib'
rm -rf $TEMP_DIR
```

### Upload Infra Common Libraries

Same workflow but using `$IMC_INFRA_COMMON_LINUX_DIR` as source.

### Upload Init App (ipumgmtd)

```bash
BUILD_DIR=$IMC_USERSPACE_DIR/build/mev_imc_ipumgmtd/$PROJ_NAME/debug/build/
# Upload libraries from build
find $BUILD_DIR/usr/local/lib/ -name "*.so*" -exec cp -P {} $TEMP_DIR \;
# Upload the application binary
scp $SCP_PARAMS $BUILD_DIR/debug/bin/ipumgmtd_<variant> root@$HOST_NAME:/usr/bin
```

### Upload All (sequential)

Runs Upload Infra → Upload Infra Common → Upload Init App in sequence.

## ipumgmtd Variants

| Variant | Description |
|---------|-------------|
| `mmg` | MMG standard |
| `mmg_anvm` | MMG with ANVM |
| `mev` | MEV standard |
| `mev_anvm` | MEV with ANVM |

## SSH Parameters

Default connection uses port 5022 (Simics forwarded port) with:
- `UserKnownHostsFile=/dev/null` — Skip host key caching
- `StrictHostKeyChecking=no` — Accept any host key (dev/test environment)
