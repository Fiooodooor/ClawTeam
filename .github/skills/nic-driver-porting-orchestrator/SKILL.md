---
name: nic-driver-porting-orchestrator
description: "Multi-agent LangGraph pipeline that autonomously drives the entire data-plane NIC driver porting lifecycle — from Linux source analysis through fully built, tested, framework-independent code on FreeBSD, Windows, or ESXi. 8-phase pipeline: source analysis, API mapping, TDD, coding, native validation, portability validation, risk audit, and final checklist. Use when: porting NIC drivers across operating systems, analyzing Linux driver source code, generating API mapping tables, or running autonomous porting pipelines."
argument-hint: "Driver name, target OS (freebsd/windows/esxi), source directory path"
---

# NIC Driver Porting Orchestrator

Multi-agent swarm that autonomously drives the entire data-plane NIC driver porting lifecycle — from Linux source analysis through fully built, tested, framework-independent code on FreeBSD, Windows, or ESXi.

This is the **core AI component** of the `helm-ai-swarm-orchestrator` project. The Helm chart deploys multi-OS VMs (Ubuntu, FreeBSD, Windows, ESXi) with NIC passthrough; this orchestrator uses those VMs to build, test, and validate the ported driver code.

## Source

Location: `tools/debug_assistant/`
Version: 2.0.0 (2026-03-23)
Engine: LangGraph + Azure OpenAI GPT-4.1

## Integration with Parent Project

```
helm-ai-swarm-orchestrator/
├── helm/                          ← Deploys multi-OS VM testbed
│   ├── templates/
│   │   ├── ai-orchestrator-context.yaml  ← ConfigMap: system prompt + porting guide + connection-info
│   │   ├── freebsd-vm*.yaml              ← FreeBSD 15.0 + E810 NIC passthrough
│   │   ├── windows-vm*.yaml              ← Windows Server 2022 + E810 NDIS
│   │   ├── esxi-vm*.yaml                 ← ESXi 8.0 + E810 native driver
│   │   └── ubuntu-vm*.yaml               ← Ubuntu 24.04 build host
│   └── values.yaml                       ← Contains porting guide + system prompt + VM configs
│
├── tools/debug_assistant/         ← THIS ORCHESTRATOR
│   ├── agent/                     ← 8-phase LangGraph pipeline
│   │   ├── pipeline/              ← Orchestrator, state, agents
│   │   └── skills/                ← Phase-specific domain knowledge (BKMs)
│   ├── service/                   ← FastAPI REST wrapper
│   ├── tools/                     ← LangGraph agent tools (file ops, artifactory)
│   ├── docker/                    ← Container build (Python 3.11 + Azure CLI)
│   └── k8s/                       ← K8s Job template
│
└── submodules/ice/                ← Reference Linux driver source (Intel ice driver)
```

### How It Connects

1. **Helm chart** deploys VMs and creates ConfigMap `ai-orchestrator-context` with:
   - `ai--system-prompt.txt` — Agent system prompt from `values.yaml`
   - `ai--porting-guide.md` — Comprehensive porting guide from `values.yaml`
   - `ai--connection-info.yaml` — SSH endpoints for all deployed VMs
2. **Orchestrator** reads `connection-info.yaml` to SSH into target VMs for build & test
3. **Source code** comes from `submodules/ice/` (or any Linux NIC driver)

### Example with Helm-deployed VMs

```bash
python3 -m agent.analyze_build \
    -d ice -t freebsd \
    -s ../submodules/ice/src \
    -o ./artifacts/ice_port \
    -c /path/to/ai--connection-info.yaml \
    -g /path/to/ai--porting-guide.md
```

## Related Agent

This skill is the implementation backend for the **AI Swarm Orchestrator Agent** defined in:
- `.github/agents/ai-swarm-orchestrator.agent.md` — VS Code agent definition (invocable via `@ai-swarm-orchestrator`)
- `ai-swarm-orchestrator-agent.md` — Root-level canonical reference document

The agent delegates porting work to this LangGraph pipeline. The agent's mandatory directives (ToT reasoning, TDD enforcement, mechanical overrides) govern how this pipeline is invoked and validated.

## When to Use

- Porting NIC drivers from Linux to FreeBSD, Windows, or ESXi
- Analyzing Linux driver source code structure and API usage
- Generating Linux → target-OS API mapping tables
- Running autonomous multi-phase porting pipelines
- Generating porting risk assessments and checklists

## Architecture

An 8-phase LangGraph pipeline with specialist ReAct agents:

| Phase | Agent(s) | Output |
|-------|----------|--------|
| 0 | SourceAnalysisAgent | Directory layout, source inventory |
| 1 | SourceAnalysisAgent (API inventory) | Linux → target-OS mapping tables |
| 2 | TDDWriterAgent | Failing CppUTest tests (red) |
| 3 | CoderAgent | Ported driver code (green) |
| 4 | NativeValidatorAgent + CodeReviewerAgent | native_score ≥ 98 |
| 5 | PerformanceEngineerAgent + PortabilityValidatorAgent | portability_score ≥ 95 |
| 6 | RiskAuditorAgent + VerificationExecutorAgent | Zero critical open risks |
| 7 | FinalChecklistGenerator | Section 14 checklist, porting_report.md |

### Gate Thresholds

- `native_score >= 98`
- `portability_score >= 95`
- Zero critical open risks

## Setup

```bash
cd tools/debug_assistant
python3 -m venv .venv
source .venv/bin/activate
pip install -r agent-requirements.txt
cp .env.example .env
# Fill in: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT
az login  # Azure CLI auth (no API key needed)
```

## CLI Usage

```bash
python3 -m agent.analyze_build \
    --driver <DRIVER_NAME> \
    --target-os <TARGET_OS> \
    --source-dir <LINUX_SOURCE_DIR> \
    --output-dir <OUTPUT_DIR> \
    [--connection-info <YAML_FILE>] \
    [--guide <PORTING_GUIDE.md>]
```

### Arguments

| Argument | Short | Required | Description |
|----------|-------|----------|-------------|
| `--driver` | `-d` | Yes | Driver name (e.g., `ixgbe`, `ice`, `i40e`) |
| `--target-os` | `-t` | No | Target OS: `freebsd`, `windows`, `esxi` (default: `freebsd`) |
| `--source-dir` | `-s` | No | Path to Linux driver source tree |
| `--output-dir` | `-o` | Yes | Output directory for ported code and reports |
| `--connection-info` | `-c` | No | YAML with SSH connection details for target VM |
| `--guide` | `-g` | No | Path to porting guide Markdown for additional context |

### Example

```bash
python3 -m agent.analyze_build \
    -d ixgbe \
    -t freebsd \
    -s ~/src/linux/drivers/net/ethernet/intel/ixgbe \
    -o /tmp/ixgbe_port
```

## REST API

```bash
uvicorn service.app:app --host 0.0.0.0 --port 8000
```

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/port` | POST | Start a porting job (async) |
| `/port/{id}` | GET | Get job status and results |
| `/health` | GET | Health check |
| `/ready` | GET | Readiness check |

## Output

Generated in the output directory:

- `porting_report.md` — Human-readable report with Section 14 final checklist
- `porting_results.json` — Structured JSON results for all 8 phases
- `portable_core/` — Framework-independent C data-plane code
- `freebsd_adapter/` (or `windows_adapter/`) — Native OS adapter layer
- `hw/` — Hardware register definitions
- `tests/` — CppUTest test suite
- `pipeline.log` — Execution log (DEBUG level)

## Agent Skills (BKMs)

Phase-specific knowledge is in `agent/skills/`:

- `source_analysis_skills.md` — Phase 0: Linux driver structure, 3-layer architecture
- `api_mapping_skills.md` — Phase 1: Linux → FreeBSD/Windows API mappings (dma_, skb_, etc.)
- `tdd_writer_skills.md` — Phase 2: CppUTest conventions, coverage targets
- `coder_skills.md` — Phase 3: Zero-framework rule, adapter pattern, pitfalls
- `validation_skills.md` — Phases 4–5: native_score, code review, perf, portability_score
- `risk_auditor_skills.md` — Phase 6: Risk register, severity matrix, verification

## Deployment

- **Docker**: `cd docker && make build-docker` (Python 3.11 slim + Azure CLI)
- **K8s Job**: `k8s/job-template.yaml` for ephemeral on-demand runs
- **Registry**: `ger-is-registry.caas.intel.com/ipu-fw-registry/ai/debug-assistant`

## LangGraph Agent Tools

Tools available to the orchestrator agents in `tools/debug_assistant/tools/`:

| Tool | Purpose |
|------|---------|
| `browse_artifactory.py` | Browse Artifactory build artifacts |
| `download_artifactory_file.py` | Download specific artifact files |
| `extract_archive.py` | Extract tar/zip archives |
| `grep_file.py` | Search file contents with regex |
| `list_files.py` | List directory contents |
| `read_file.py` | Read file contents |
| `find_unique_errors.py` | Deduplicate error messages |
| `filter_pattern_context.py` | Extract context around pattern matches |

## Dependencies

- `langchain`, `langgraph` — Agent orchestration
- `azure-identity` — Azure OpenAI authentication (via `az login`)
- `fastapi`, `uvicorn` — REST API
- `python-dotenv`, `PyYAML` — Config loading
- Azure OpenAI `gpt-4.1` deployment

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| 2.0.0 | 2026-03-23 | Full 8-phase porting pipeline, multi-agent swarm |
| 1.2.0 | 2026-02-08 | Ring-type filtering, exact build matching |
| 1.1.0 | 2026-02-03 | Azure CLI auth, GPT-4.1 model update |
| 1.0.0 | 2026-01-25 | Initial release (build failure analysis) |
