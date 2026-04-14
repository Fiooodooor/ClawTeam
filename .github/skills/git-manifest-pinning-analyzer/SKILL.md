---
name: git-manifest-pinning-analyzer
description: "Parse XML repo manifests to detect repositories pinned to fixed SHA revisions (40-char hex) and optionally revert them to branch tracking. Reads CSV input for selective updates. Use when: auditing manifest pinning, reverting emergency SHA pins back to branches, or analyzing repo manifest configurations."
argument-hint: "Path to manifest XML file and optional CSV with repos to update"
---

# Git Manifest Pinning Analyzer

Parses Google `repo` tool XML manifests to identify repositories pinned to fixed SHA commits and can revert them to branch tracking.

## Source

Based on: `tools/scripts/manifest_revert/manifest_revert.py`

## When to Use

- Auditing which repos in a manifest are pinned to SHAs vs tracking branches
- Reverting emergency SHA pins back to branch tracking after incidents
- Analyzing `default.xml` manifest configurations
- Generating reports of pinned repositories

## Core Classes

### `Repo`

```python
class Repo:
    def __init__(self, path, name, revision):
        self.path = path       # Local checkout path
        self.name = name       # Remote repository name
        self.revision = revision  # Branch name or 40-char SHA
```

### `ManifestParser`

```python
class ManifestParser:
    def __init__(self, manifest_file):
        self.manifest_file = manifest_file
        self.repos = []
    
    def parse(self):
        """Parse <project> elements from manifest XML."""
        tree = ET.parse(self.manifest_file)
        root = tree.getroot()
        for project in root.findall('project'):
            path = project.get('path')
            name = project.get('name')
            revision = project.get('revision')
            self.repos.append(Repo(path, name, revision))
    
    def is_fixed_sha(self, revision):
        """Check if revision is a 40-char hex SHA."""
        return bool(re.match(r'^[a-f0-9]{40}$', revision))
    
    def get_fixed_sha_repos(self):
        """Return repos pinned to SHAs."""
        return [r for r in self.repos if r.revision and self.is_fixed_sha(r.revision)]
    
    def update_revisions(self, repos_to_update):
        """Update manifest XML, reverting SHAs to branch names."""
```

## Usage

```bash
# Analyze manifest for pinned repos
python manifest_revert.py --manifest default.xml --report

# Revert specific repos from CSV
python manifest_revert.py --manifest default.xml --update repos_to_update.csv
```

## CSV Input Format

For selective updates, provide a CSV with repos to revert:

```csv
name,new_revision
intel-innersource/firmware/ethernet/e2000-fw-imc-boot,main
intel-innersource/firmware/ethernet/e2000-fw-nsl,develop
```

## Manifest XML Format

Standard Google `repo` manifest (`default.xml`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<manifest>
  <remote name="origin" fetch="https://github.com/" />
  <default revision="main" remote="origin" sync-j="4" />
  
  <!-- Branch tracking (good) -->
  <project path="sources/imc/boot" name="intel/fw-boot" revision="main" />
  
  <!-- SHA pinned (detected by analyzer) -->
  <project path="sources/imc/shared" name="intel/fw-shared" 
           revision="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2" />
</manifest>
```

## SHA Detection

A revision is considered a fixed SHA if it matches: `^[a-f0-9]{40}$`

This distinguishes branch names (e.g., `main`, `release/v2.0`) from commit SHAs.

## Workflow

1. **Parse** — Read `default.xml` and extract all `<project>` elements
2. **Detect** — Identify repos where `revision` is a 40-char hex SHA
3. **Report** — List pinned repos with their paths, names, and SHAs
4. **Update** (optional) — Read CSV of repos to revert, update XML in place
