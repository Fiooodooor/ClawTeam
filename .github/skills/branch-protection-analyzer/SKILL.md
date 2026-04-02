---
name: branch-protection-analyzer
description: "Analyze GitHub branch protection rules across multiple repositories defined in a manifest/projects.xml config. Downloads manifest files via GitHub API, applies include/exclude filters, and checks if CI branch protection (eth-fw-ci-cb) is configured. Use when: auditing branch protection across a multi-repo project, checking CI gate coverage, or generating compliance reports."
argument-hint: "Path to projects.xml config file and optional GitHub token"
---

# Branch Protection Analyzer

Parses multi-project configuration files, downloads repo manifests from GitHub, and checks branch protection status across all repositories.

## Source

Based on: `tools/scripts/repo_gate_test/multi_project_analyzer.py`

## When to Use

- Auditing branch protection across a fleet of repositories
- Checking that CI gatekeeping (eth-fw-ci-cb) is enabled on all repos
- Generating compliance reports for branch protection policies
- Validating manifest-defined repos have proper CI gates

## Prerequisites

- GitHub personal access token (optional but recommended — without it, rate limit is 60 req/hour)
- `projects.xml` / YAML config file listing projects, manifests, and filters

## Configuration Format

The `projects.xml` config (actually YAML):

```yaml
projects:
  - name: "project-alpha"
    manifest_repo: "https://github.com/intel-innersource/repo-manifest"
    manifest_branch: "main"
    include_filter: "^sources/.*"
    exclude_filter: "^sources/third-party/.*"
  - name: "project-beta"
    manifest_repo: "https://github.com/intel-innersource/other-manifest"
    manifest_branch: "release"
```

## Usage

```bash
export GITHUB_TOKEN="ghp_..."
python multi_project_analyzer.py --config projects.xml
```

## Workflow

1. **Load config** — Parse `projects.xml` (YAML format) to get project list
2. **Download manifests** — For each project, fetch `default.xml` from the manifest repo via GitHub API (base64-decoded)
3. **Apply filters** — Include/exclude repos based on regex patterns
4. **Check protection** — Query GitHub API for branch protection rules on each repo
5. **Generate report** — Per-project reports with protection status

## Key Functions

- `load_projects_config(config_file)` — Parses YAML project config
- `download_manifest_file(repo_url, branch_name)` — Fetches `default.xml` from GitHub API
- Branch protection check via GitHub API: `GET /repos/{owner}/{repo}/branches/{branch}/protection`

## GitHub API Details

- Base URL: `https://api.github.com/repos/intel-innersource`
- Authentication: `Authorization: token $GITHUB_TOKEN` header
- Proxy: `http://proxy-dmz.intel.com:912`
- Rate limits: 5000 req/hr with token, 60 req/hr without

## Output

Per-project reports listing each repository with:
- Repository name and path
- Branch protection enabled/disabled
- CI gate (eth-fw-ci-cb) status
- Required reviewers count
