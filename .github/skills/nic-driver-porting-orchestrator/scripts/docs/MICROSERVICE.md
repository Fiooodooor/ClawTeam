# NIC Driver Porting Orchestrator — Microservice Deployment Guide

## Overview

The Porting Orchestrator can run as a **REST microservice in Kubernetes**,
allowing CI pipelines or developer tools to trigger autonomous NIC driver
data-plane porting via HTTP.

```text
┌──────────────────────────────────────────────────────┐
│              CI Pipeline / Developer CLI              │
│                                                      │
│  POST /port  ──────────────────────────► ┌──────────┐│
│       │                                  │ Porting  ││
│  poll GET /port/{id}  ◄────────────────  │Orchestr. ││
│       │                                  │  (K8s)   ││
│       ▼                                  └──────────┘│
│  Retrieve porting report & artifacts                 │
└──────────────────────────────────────────────────────┘
```

## Architecture

### Option A: Always-Running Deployment (recommended for frequent use)

A single-replica `Deployment` + `Service` runs in the cluster. Clients call it
via HTTP. The pod is always warm so response is immediate.

- K8s manifests: `k8s/deployment.yaml`
- Service DNS: `porting-orchestrator.porting-orchestrator.svc.cluster.local`

### Option B: On-Demand K8s Job (for one-off porting runs)

A K8s `Job` per porting run, reads results from the pod logs or shared volume.

- Job template: `k8s/job-template.yaml`

---

## Prerequisites

1. **Container registry** — push the Docker image to your internal registry
2. **Azure Workload Identity** — the pod needs a Managed Identity (or
   `az login` session) to access Azure OpenAI
3. **Network** — the pod must reach:
   - Azure OpenAI endpoint
   - Target VM (FreeBSD/Windows) via SSH for verification phases

---

## Build & Deploy

### 1. Build the Docker image

```bash
cd .github/skills/nic-driver-porting-orchestrator/scripts
docker build -t YOUR_REGISTRY/porting-orchestrator:latest .
docker push YOUR_REGISTRY/porting-orchestrator:latest
```

### 2. Deploy to Kubernetes (Option A)

```bash
kubectl apply -f k8s/deployment.yaml

kubectl -n porting-orchestrator get pods
kubectl -n porting-orchestrator logs deployment/porting-orchestrator
```

### 3. Or use the Job template (Option B)

```bash
export DRIVER_NAME=ixgbe
export TARGET_OS=freebsd

sed "s/DRIVER_NAME/${DRIVER_NAME}/g; s/TARGET_OS/${TARGET_OS}/g" \
    k8s/job-template.yaml | kubectl apply -f -

kubectl -n porting-orchestrator wait --for=condition=complete \
    job/porting-${DRIVER_NAME} --timeout=1800s

kubectl -n porting-orchestrator logs job/porting-${DRIVER_NAME}
```

---

## API Reference

### `POST /port`

Submit a new porting job.

**Request:**

```json
{
  "driver_name": "ixgbe",
  "target_os": "freebsd",
  "source_dir": "/path/to/linux/driver",
  "connection_info": {"host": "10.0.0.5", "user": "root"}
}
```

**Response (200):**

```json
{
  "job_id": "a1b2c3d4e5f6",
  "status": "pending"
}
```

### `GET /port/{job_id}`

Poll for job status and results.

**Response (200):**

```json
{
  "job_id": "a1b2c3d4e5f6",
  "status": "completed",
  "started_at": "2026-03-23T10:00:00",
  "finished_at": "2026-03-23T10:45:23",
  "duration_seconds": 2723.0,
  "report": "# Porting Report\n...",
  "phase_status": {
    "phase0_source_analysis": "completed",
    "phase1_api_inventory": "completed",
    "phase2_tdd": "completed",
    "phase3_coder": "completed",
    "phase4_validation": "completed",
    "phase5_perf_portability": "completed",
    "phase6_risk_verification": "completed",
    "phase7_final_checklist": "completed"
  },
  "native_score": 99.2,
  "portability_score": 97.5,
  "errors": []
}
```

### `GET /health` / `GET /ready`

Kubernetes liveness and readiness probes.

---

## Integration

The microservice can be called from any CI pipeline or developer tool that
supports HTTP. Submit a porting job via `POST /port`, then poll
`GET /port/{job_id}` until status is `completed` or `failed`.

### Files

| File | Purpose |
| ---- | ------- |
| `service/app.py` | FastAPI microservice wrapping the porting pipeline |
| `service/requirements.txt` | Additional Python deps (FastAPI, uvicorn) |
| `Dockerfile` | Multi-stage Docker build |
| `k8s/deployment.yaml` | K8s Deployment + Service |
| `k8s/job-template.yaml` | Alternative: on-demand K8s Job |

---

## Configuration

### Environment variables (pod)

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `AZURE_OPENAI_ENDPOINT` | Yes | Azure OpenAI endpoint |
| `AZURE_OPENAI_DEPLOYMENT` | Yes | Model deployment name |
| `AZURE_OPENAI_API_VERSION` | No | API version (default: 2024-08-01-preview) |
| `AZURE_OPENAI_TEMPERATURE` | No | Temperature (default: 0) |
