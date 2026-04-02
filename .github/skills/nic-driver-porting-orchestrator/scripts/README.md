# NIC Driver Porting Orchestrator

Multi-agent swarm that autonomously drives the entire data-plane NIC driver porting lifecycle — from Linux source analysis through fully built, tested, framework-independent code on FreeBSD, Windows, or ESXi.

## Architecture

An 8-phase LangGraph pipeline with specialist ReAct agents:

| Phase | Agent(s) | Output |
| ----- | -------- | ------ |
| 0 | SourceAnalysisAgent | Directory layout, source inventory |
| 1 | SourceAnalysisAgent (API inventory) | Linux → target-OS mapping tables |
| 2 | TDDWriterAgent | Failing CppUTest tests (red) |
| 3 | CoderAgent | Ported driver code (green) |
| 4 | NativeValidatorAgent + CodeReviewerAgent | native_score ≥ 98 |
| 5 | PerformanceEngineerAgent + PortabilityValidatorAgent | portability_score ≥ 95 |
| 6 | RiskAuditorAgent + VerificationExecutorAgent | Zero critical open risks |
| 7 | FinalChecklistGenerator | Section 14 checklist, porting_report.md |

## Setup

1. **Create virtual environment:**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies:**

   ```bash
   pip install -r agent-requirements.txt
   ```

3. **Configure environment:**

   Copy `.env.example` to `.env` and fill in the required values:

   ```bash
   cp .env.example .env
   ```

   Required variables:
   - `AZURE_OPENAI_ENDPOINT` — Azure OpenAI endpoint URL
   - `AZURE_OPENAI_DEPLOYMENT` — Model deployment name (e.g. `gpt-4.1`)

   Authentication: Run `az login` to authenticate with Azure (no API key needed).

## Usage

```bash
python3 -m agent.analyze_build \
    --driver <DRIVER_NAME> \
    --target-os <TARGET_OS> \
    --source-dir <LINUX_SOURCE_DIR> \
    --output-dir <OUTPUT_DIR> \
    [--connection-info <YAML_FILE>]
```

### Arguments

| Argument | Short | Required | Description |
| -------- | ----- | -------- | ----------- |
| `--driver` | `-d` | Yes | Driver name (e.g. `ixgbe`, `ice`, `i40e`) |
| `--target-os` | `-t` | No | Target OS (default: `freebsd`). Options: `freebsd`, `windows`, `esxi` |
| `--source-dir` | `-s` | No | Path to Linux driver source tree |
| `--output-dir` | `-o` | Yes | Output directory for ported code and reports |
| `--connection-info` | `-c` | No | YAML file with SSH connection details for target VM |
| `--guide` | `-g` | No | Path to porting guide Markdown for additional context |
| `--version` | `-V` | No | Show version and exit |

### Example

```bash
python3 -m agent.analyze_build \
    -d ixgbe \
    -t freebsd \
    -s ~/src/linux/drivers/net/ethernet/intel/ixgbe \
    -o /tmp/ixgbe_port
```

## Output

The tool generates in the output directory:

- `porting_report.md` — Human-readable report with Section 14 final checklist
- `porting_results.json` — Structured JSON results for all 8 phases
- `portable_core/` — Framework-independent C data-plane code
- `freebsd_adapter/` (or `windows_adapter/`) — Native OS adapter layer
- `hw/` — Hardware register definitions
- `tests/` — CppUTest test suite
- `pipeline.log` — Execution log (DEBUG level)

## REST API

Start the service:

```bash
uvicorn service.app:app --host 0.0.0.0 --port 8000
```

| Endpoint | Method | Description |
| -------- | ------ | ----------- |
| `/port` | POST | Submit a porting job |
| `/port/{job_id}` | GET | Poll job status and results |
| `/health` | GET | Liveness probe |
| `/ready` | GET | Readiness probe |

## Documentation

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for design details.

## License

Intel Proprietary
