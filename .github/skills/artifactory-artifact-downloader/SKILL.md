---
name: artifactory-artifact-downloader
description: "Download and extract build artifacts from Intel Artifactory with support for multi-site API keys (Oragon/IGK/IL), automatic latest-build detection, Fedora version resolution, and zstandard extraction. Use when: downloading MEV/NIC firmware build artifacts, finding latest build IDs, extracting .tar.zst artifacts, or automating artifact retrieval in CI."
argument-hint: "Artifactory key, stepping, build stream, branch, and build ID (or 'latest')"
---

# Artifactory Artifact Downloader

Downloads and extracts firmware build artifacts from Intel Artifactory, with support for automatic latest-build detection and multi-site API keys.

## Source

Based on: `tools/scripts/download_artifact/download_mev_artifact.py`

## When to Use

- Downloading MEV/NIC firmware build artifacts from Artifactory
- Finding the latest build number for a given branch/stream
- Extracting `.tar.zst` (zstandard-compressed) artifacts
- Automating artifact retrieval in CI pipelines
- Resolving Fedora versions from Artifactory folder listings

## Command-Line Options

| Flag | Long Form | Description |
|------|-----------|-------------|
| `-ao` | `--artifactory_oragon_key` | Artifactory Oragon site API key |
| `-ai` | `--artifactory-igk-key` | Artifactory IGK site API key |
| `-ail` | `--artifactory-il-key` | Artifactory Israel site API key |
| `-s` | `--stepping` | Stepping information |
| `-b` | `--build-stream` | Build stream name |
| `-m` | `--mev-build-id` | MEV build ID (use `"latest"` for auto-detect) |
| `-r` | `--mev-branch` | MEV branch name |
| `-p` | `--name-prefix` | Name prefix for the project |
| `-o` | `--output-folder` | Path to the output folder |
| `-l` | `--bid-list` | Comma-separated list of BID values |
| `-e` | `--mev-ts-erot-or-irot` | Use `"erot"` or `"irot"` for MEV TS (default: `erot`) |
| `-k` | `--kernel-version` | Kernel version (default: `5.15`) |
| `-v` | `--host-kernel-version` | Host kernel version |

## Usage Example

```bash
python download_mev_artifact.py \
  -ao "$ARTIFACTORY_KEY" \
  -s "A0" \
  -b "release" \
  -m "latest" \
  -r "main" \
  -p "mev" \
  -o "./artifacts"
```

## Workflow

1. Parse command-line arguments
2. Determine project name and file prefix from branch/prefix
3. If build ID is `"latest"`, query Artifactory API to find the latest build number
4. Construct Artifactory folder URL; detect Fedora version if applicable
5. Identify required artifact files by naming conventions
6. Download and extract (supports `.tar.gz`, `.tar.zst`)
7. Organize extracted files into the output folder
8. Handle special cases for MEV TS and Simics configurations
9. Copy files to shared location if applicable
10. Clean up temporary files

## Key Functions

- `find_latest_build()` — Queries Artifactory for the latest build number on a branch
- `find_fedora_version(url)` — Auto-detects Fedora version from folder listing
- `find_file_in_folder(folder, regex)` — Finds files matching a regex pattern
- `check_build(url)` — Lists files/folders at a build URL

## Dependencies

- `requests` — HTTP client
- `zstandard` — For `.tar.zst` extraction (auto-installed if missing)
- `argparse`, `tarfile`, `json`, `subprocess`

## Notes

- Uses Intel proxy settings for HTTP requests
- Supports multiple Artifactory sites with separate API keys
- Build number extraction uses string parsing between markers
