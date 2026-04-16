---
name: nic-porting-kickoff-role-matrix
description: "Generate a role identity matrix and handoff plan for a NIC driver porting run."
argument-hint: "Driver, target OS, current codebase path, and constraints"
agent: ai-swarm-orchestrator
---
Create a complete kickoff package for this NIC porting request:

${input:Describe the driver, target OS, constraints, and current status}

Return exactly these sections:
1. Role Matrix (owner and backup per role)
2. Phase Plan (0-7) with success gates
3. Handoff Graph (who hands off to whom and when)
4. Risk Register Seed (top 5 risks with mitigation owners)
5. First 10 Tasks for execution order

Rules:
- Enforce TDD-first sequencing.
- Keep Linux source changes minimal.
- Prefer LinuxKPI + iflib for FreeBSD target.
- Include measurable gate thresholds for each phase.
