---
name: nic-phase-5-gates
description: "Phase 5: Run all verification gates and produce APPROVED/BLOCKED verdict."
argument-hint: "Driver name, artifacts path"
agent: nic-porting-director
---
Execute Phase 5 — Build & Verification Gates for this driver:

${input:Driver name and path to porting artifacts}

Phase 5 gate checks (GroupChat debate pattern):
1. Native Validation → nic-native-validator
   - native_score = (native_calls / total_calls) × 100, target >= 98.0
   - Banned pattern scan: sk_buff, napi, rte_, linuxkpi, net_device, netif_, NAPI_
2. Code Review → nic-code-reviewer
   - Minimal-touch compliance, #ifdef hygiene, bisect-safety
3. Performance Validation → nic-performance-engineer
   - Zero-copy path verification, regression budget < 5% throughput / < 10% latency
4. Portability Validation → nic-portability-engineer
   - portability_score >= 95.0, cross-compile matrix clean
5. Risk Audit → nic-porting-risk-auditor
   - critical_risks = 0, all R-01 through R-12 categories assessed
6. Build Gate → nic-build-ci-engineer
   - build_status = green on Linux + FreeBSD (amd64 + aarch64)
7. Test Execution → nic-verification-engineer
   - test_pass_rate = 100%

Final verdict: APPROVED (all metrics green) or BLOCKED (with specific blockers).
Debate protocol: up to 5 rounds, vote >= 3/4 approve required.
