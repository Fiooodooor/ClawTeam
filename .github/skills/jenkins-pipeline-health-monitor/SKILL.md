---
name: jenkins-pipeline-health-monitor
description: "Monitor Jenkins pipeline health with Prometheus metrics, pickle-based state persistence, and database integration. Polls Jenkins every 5 minutes, exposes Gauge/Counter metrics, tracks uptime/downtime, and records events to a database. Use when: setting up Jenkins health monitoring, exporting pipeline metrics to Prometheus, or tracking CI infrastructure reliability."
argument-hint: "Jenkins pipeline URL and optional DB Fernet key for database integration"
---

# Jenkins Pipeline Health Monitor

Continuously monitors Jenkins pipeline health, exposes Prometheus metrics, and persists state for uptime/downtime tracking.

## Source

Based on: `tools/scripts/jenkins_health_agent/pipeline-sanity-checker.py`

## When to Use

- Setting up automated Jenkins pipeline health monitoring
- Exporting CI pipeline metrics to Prometheus/Grafana
- Tracking uptime/downtime of critical CI pipelines
- Recording CI infrastructure reliability data to a database

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `JENKINS_PIPELINE_URL` | CJE IL Prod01 sanity pipeline | Jenkins pipeline URL to monitor |
| `DB_FERNET_KEY` | (none) | Fernet encryption key for database credentials |

## Prometheus Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `jenkins_pipeline_success` | Gauge | 1 = pipeline healthy, 0 = failure |
| `jenkins_pipeline_checks_total` | Counter | Total number of health checks performed |
| `jenkins_pipeline_up_total` | Counter | Total successful pipeline checks |
| `jenkins_pipeline_down_total` | Counter | Total failed pipeline checks |

All metrics are labeled with `jenkins_url`.

## Architecture

```
┌─────────────────────────────────────┐
│  pipeline-sanity-checker.py         │
│                                     │
│  ┌─────────┐    ┌────────────────┐  │
│  │ Poller   │───▶│ Jenkins API    │  │
│  │ (5 min)  │    │ GET /lastBuild │  │
│  └────┬─────┘    └────────────────┘  │
│       │                              │
│  ┌────▼─────┐    ┌────────────────┐  │
│  │ Metrics  │───▶│ Prometheus     │  │
│  │ Server   │    │ :8000          │  │
│  └────┬─────┘    └────────────────┘  │
│       │                              │
│  ┌────▼─────┐    ┌────────────────┐  │
│  │ Database │───▶│ DB_Writer      │  │
│  │ Handler  │    │ (keepalive,    │  │
│  └────┬─────┘    │  downtime)     │  │
│       │          └────────────────┘  │
│  ┌────▼─────┐                        │
│  │ State    │    jenkins_health_     │
│  │ Pickle   │    state.pkl           │
│  └──────────┘    jenkins_downtime_   │
│                  state.pkl           │
└─────────────────────────────────────┘
```

## Key Components

### DatabaseHandler

Manages state persistence and database integration:

- **State files**: `jenkins_health_state.pkl` (keepalive timestamp), `jenkins_downtime_state.pkl` (active downtime ID)
- **DB Writer**: Uses `DB_Writer` from `DB_Tools` with Fernet-encrypted credentials
- **Keepalive**: Records periodic heartbeats to the database
- **Downtime tracking**: Opens/closes downtime records with start/end timestamps

### Polling Loop

```python
while True:
    # Check Jenkins pipeline status
    response = requests.get(f"{JENKINS_URL}/lastBuild/api/json", verify=False)
    build_info = response.json()
    
    if build_info['result'] == 'SUCCESS':
        pipeline_success_gauge.labels(jenkins_url=JENKINS_URL).set(1)
        pipeline_up_counter.labels(jenkins_url=JENKINS_URL).inc()
    else:
        pipeline_success_gauge.labels(jenkins_url=JENKINS_URL).set(0)
        pipeline_down_counter.labels(jenkins_url=JENKINS_URL).inc()
    
    pipeline_check_counter.labels(jenkins_url=JENKINS_URL).inc()
    time.sleep(300)  # 5 minutes
```

## Usage

```bash
# Basic run (uses default Jenkins URL)
python pipeline-sanity-checker.py

# With custom Jenkins URL
JENKINS_PIPELINE_URL="https://jenkins.example.com/job/my-pipeline/" \
  python pipeline-sanity-checker.py

# With database integration
DB_FERNET_KEY="your-fernet-key" \
  JENKINS_PIPELINE_URL="https://jenkins.example.com/job/my-pipeline/" \
  python pipeline-sanity-checker.py
```

## Dependencies

- `requests` — HTTP client for Jenkins API
- `prometheus_client` — Prometheus metric exposition
- `pickle` — State persistence
- `DB_Tools.DB_Writer` — Database integration (optional)

## Prometheus Endpoint

Metrics are exposed on `:8000` via `start_http_server(8000)`. Scrape with:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'jenkins-health'
    static_configs:
      - targets: ['localhost:8000']
```
