# Release Notes

## Version 1.2.0 (2026-02-08)

### Changes

- **Ring type filtering** - Added `--ring-type` / `-r` argument to filter tests by regression ring (BAT, PIT, Nightly, WEEKLY). Defaults to BAT. Applies to both the agent CLI and the `extract_build_failed_swift_log_location` tool.

### Bug Fixes

- **Exact build number matching** - Fixed build number regex pattern to match only the exact build number (e.g., `#582` now correctly matches build 582 but not 12582 or 15582). Updated user-facing help text to reflect the actual behavior.

---

## Version 1.1.0 (2026-02-03)

### Changes

- **Azure CLI Authentication** - Switched from API key to `AzureCliCredential` for Azure OpenAI authentication. Users now authenticate via `az login` instead of configuring an API key.
- **Model Update** - Default model changed from `gpt-4o` to `gpt-4.1`
- **Report Layout** - Improved analysis report layout to be more concise and readable
- **Agent Prompts** - Several prompting optimizations to improve analysis quality

### Bug Fixes

- **browse_artifactory tool** - Fixed path handling when `output_path` directory doesn't exist. Tool now creates the directory automatically.
- **browse_artifactory docstring** - Added missing `output_file` field to Returns documentation

### Dependencies

- Added `azure-identity` package for Azure authentication

---

## Version 1.0.0 (2026-01-25)

### Initial Release

- Multi-phase AI pipeline for build failure analysis
- Data collection from CI database and Artifactory
- Specialized analyzers: FWDK, UART (IMC/HIFMC), Simics
- Fusion phase for cross-log correlation
- Executive summary generation
- Parallel analyzer execution support
