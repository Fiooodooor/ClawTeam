"""
Specialist Worker Agents for the NIC Driver Porting Swarm

Each sub-step in the porting pipeline flows through these specialist agents:
  TDD Writer → Coder → Native Validator → Reviewer →
  Performance Engineer → Portability Validator → Risk Auditor →
  Verification Executor → Supervisor gate

Uses LangGraph's create_react_agent for tool orchestration.
"""

import os
import sys
import json
import logging
from abc import ABC
from typing import Dict, Any, Optional, List

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from .callbacks import ToolCallLogger
from .state import PipelineState

# Import tools from tools directory
TOOLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'tools')
sys.path.insert(0, TOOLS_DIR)

from read_file import read_file
from grep_file import grep_file
from list_files import list_files

# Common code-analysis tools available to all specialist agents
PORTING_TOOLS = [
    read_file,
    grep_file,
    list_files,
]

# Maximum LangGraph iterations per agent
MAX_ITERATIONS = 70


class _PortingAgent(ABC):
    """
    Base class for specialist porting worker agents.

    Subclasses override AGENT_NAME and ROLE_DESCRIPTION.
    """

    AGENT_NAME = "base"
    ROLE_DESCRIPTION = "specialist worker"

    def __init__(self, llm: AzureChatOpenAI, logger: logging.Logger):
        self.llm = llm
        self.logger = logger

        self.agent = create_react_agent(
            model=llm,
            tools=PORTING_TOOLS,
            prompt=self._system_prompt(),
        )

    def _system_prompt(self) -> str:
        return f"""You are the **{self.ROLE_DESCRIPTION}** in a multi-agent NIC driver porting swarm.

CORE PORTING PRINCIPLES (never violate):
1. Correctness-first TDD — every ported function has a failing test first.
2. Maximum performance + portability + minimal divergence from the Linux reference.
3. Zero frameworks — no iflib, linuxkpi, rte_*, DPDK.
4. Native-only OS calls — FreeBSD: ifnet(9), bus_dma(9), mbuf(9), pci(9),
   taskqueue(9), MSI-X.  Windows: NDIS Miniport*.
5. Thin OAL seams — portable NIC core has ZERO OS calls.

FRAMEWORK DETECTION (instant rejection):
Any detection of iflib, linuxkpi, rte_*, DPDK, or any framework call triggers
immediate rejection and auto-fix with the pure native equivalent.

Work autonomously. Produce structured JSON output for downstream agents."""

    def run(self, state: PipelineState) -> PipelineState:
        """Execute this agent's phase and update pipeline state."""
        driver = state.get('driver_name', 'unknown')
        target_os = state.get('target_os', 'freebsd')

        prompt = self._task_prompt(state)

        try:
            result = self.agent.invoke(
                {"messages": [HumanMessage(content=prompt)]},
                {"recursion_limit": MAX_ITERATIONS,
                 "callbacks": [ToolCallLogger(self.logger, self.AGENT_NAME)]},
            )
            final = result["messages"][-1]
            self._process_result(state, final.content)
        except Exception as e:
            self.logger.error(f"{self.AGENT_NAME} failed: {e}")
            state['errors'].append(f"{self.AGENT_NAME} failed: {str(e)}")

        return state

    def _task_prompt(self, state: PipelineState) -> str:
        """Subclasses override to provide the task-specific prompt."""
        return f"Execute {self.ROLE_DESCRIPTION} for driver {state.get('driver_name')}"

    def _process_result(self, state: PipelineState, content: str):
        """Subclasses override to parse result and update state."""
        pass


# =====================================================================
# Specialist Agent Implementations
# =====================================================================

class TDDWriterAgent(_PortingAgent):
    """Phase 2: Write failing tests first (TDD red phase)."""
    AGENT_NAME = "tdd_writer"
    ROLE_DESCRIPTION = "TDD Test Writer"

    def _task_prompt(self, state: PipelineState) -> str:
        driver = state.get('driver_name', 'unknown')
        target_os = state.get('target_os', 'freebsd')
        mappings = state.get('api_mappings', [])
        layout = state.get('directory_layout', {})
        tests_dir = layout.get('tests_dir', f'./artifacts/{driver}/tests')

        mapping_summary = "\n".join(
            f"  - {m.get('linux_api','')} → {m.get('target_api','')} ({m.get('category','')})"
            for m in mappings[:30]
        )
        return f"""Write failing TDD tests for driver: {driver} targeting {target_os}.
Tests directory: {tests_dir}

API Mappings to test:
{mapping_summary}

REQUIREMENTS:
- Write CppUTest-style native mock tests for each mapped API
- Tests MUST fail initially (red phase) — they test functions not yet implemented
- Use native {target_os} types in test mocks (struct mbuf *, bus_dma_tag_t, etc.)
- Cover: TX ring push, RX ring poll, DMA map/unmap, interrupt handler, RSS, TSO
- Zero framework calls in tests

Return JSON:
{{
  "tests_written": ["<file1>", ...],
  "test_count": <N>,
  "categories_covered": ["dma", "tx_rx", "interrupt", ...]
}}"""

    def _process_result(self, state: PipelineState, content: str):
        from .json_utils import parse_llm_json_response
        parsed = parse_llm_json_response(content, self.logger)
        if parsed and 'tests_written' in parsed:
            state['substep_results'].append({
                'substep_id': 'phase2.tdd',
                'description': 'TDD failing tests written',
                'tdd_tests_written': parsed.get('tests_written', []),
                'code_files_modified': [],
                'gate_passed': True,
            })


class CoderAgent(_PortingAgent):
    """Phase 3: Implement the ported driver code to make tests pass."""
    AGENT_NAME = "coder"
    ROLE_DESCRIPTION = "Coder (Driver Implementation)"

    def _task_prompt(self, state: PipelineState) -> str:
        driver = state.get('driver_name', 'unknown')
        target_os = state.get('target_os', 'freebsd')
        layout = state.get('directory_layout', {})
        core_dir = layout.get('core_dir', f'./artifacts/{driver}/core')
        adapter_dir = layout.get('os_adapters', {}).get(target_os, f'./artifacts/{driver}/os/{target_os}')
        source = state.get('source_analysis', {})
        dp_files = source.get('dataplane_files', [])

        return f"""Implement the ported driver code for: {driver} targeting {target_os}.

Architecture:
- Portable core (zero OS calls): {core_dir}
- Native {target_os} adapter: {adapter_dir}

Source dataplane files to port: {', '.join(dp_files[:10])}

IMPLEMENTATION RULES:
- Portable core: ZERO #include <linux/*>, ZERO sk_buff, ZERO net_device, ZERO napi
- {target_os} adapter: ONLY native OS APIs (ifnet, mbuf, bus_dma, taskqueue, pci, MSI-X)
- Keep every register write, descriptor format, and offload calculation identical to Linux
- The code must compile as a standard {target_os} kernel module

Return JSON:
{{
  "artifacts": [
    {{"file_path": "<path>", "artifact_type": "source|header|makefile", "description": "..."}}
  ],
  "files_created": <count>
}}"""

    def _process_result(self, state: PipelineState, content: str):
        from .json_utils import parse_llm_json_response
        parsed = parse_llm_json_response(content, self.logger)
        if parsed and 'artifacts' in parsed:
            for art in parsed['artifacts']:
                state['porting_artifacts'].append(art)


class NativeValidatorAgent(_PortingAgent):
    """Phase 4: Validate that all code uses only native OS APIs."""
    AGENT_NAME = "native_validator"
    ROLE_DESCRIPTION = "Native Validator"

    def _task_prompt(self, state: PipelineState) -> str:
        driver = state.get('driver_name', 'unknown')
        target_os = state.get('target_os', 'freebsd')
        artifacts = state.get('porting_artifacts', [])
        files = [a.get('file_path', '') for a in artifacts]

        return f"""Validate native API compliance for driver: {driver} on {target_os}.

Files to validate: {', '.join(files[:20])}

VALIDATION CHECKS:
1. Grep for BANNED patterns: sk_buff, net_device, napi_, netif_, dma_map_single (Linux),
   iflib, linuxkpi, rte_, DPDK (frameworks)
2. Verify portable core has ZERO OS-specific includes
3. Verify adapter uses ONLY native {target_os} APIs
4. Compute native_score = (native_calls / total_os_calls) * 100
5. Flag any violations for auto-fix

THRESHOLD: native_score must be ≥ 98

Return JSON:
{{
  "native_score": <float>,
  "violations": [{{"file": "...", "line": N, "pattern": "...", "fix": "..."}}],
  "total_os_calls": <N>,
  "native_calls": <N>
}}"""

    def _process_result(self, state: PipelineState, content: str):
        from .json_utils import parse_llm_json_response
        parsed = parse_llm_json_response(content, self.logger)
        if parsed:
            state['native_score'] = parsed.get('native_score', 0)


class CodeReviewerAgent(_PortingAgent):
    """Phase 4: Review ported code for correctness and style."""
    AGENT_NAME = "code_reviewer"
    ROLE_DESCRIPTION = "Code Reviewer"

    def _task_prompt(self, state: PipelineState) -> str:
        driver = state.get('driver_name', 'unknown')
        artifacts = state.get('porting_artifacts', [])
        return f"""Review ported driver code for: {driver}

Artifacts to review: {len(artifacts)} files

REVIEW CRITERIA:
1. Behavioural identity with Linux reference (same descriptor formats, ring arithmetic)
2. Correct DMA mapping lifecycle (map → sync → unmap)
3. Interrupt handler correctness (MSI-X, moderation)
4. Memory ownership rules (adapter allocates, core reads/writes)
5. Error handling and resource cleanup
6. No framework leaks

Return JSON:
{{
  "review_passed": true/false,
  "findings": [{{"severity": "...", "file": "...", "description": "..."}}],
  "summary": "..."
}}"""

    def _process_result(self, state: PipelineState, content: str):
        from .json_utils import parse_llm_json_response
        parsed = parse_llm_json_response(content, self.logger)
        if parsed:
            state['substep_results'].append({
                'substep_id': 'phase4.review',
                'description': 'Code review',
                'review_passed': parsed.get('review_passed', False),
                'gate_passed': parsed.get('review_passed', False),
            })


class PerformanceEngineerAgent(_PortingAgent):
    """Phase 5: Validate zero-overhead design and hot-path performance."""
    AGENT_NAME = "perf_engineer"
    ROLE_DESCRIPTION = "Performance Engineer"

    def _task_prompt(self, state: PipelineState) -> str:
        driver = state.get('driver_name', 'unknown')
        return f"""Analyse performance characteristics of ported driver: {driver}

PERFORMANCE CHECKS:
1. Hot-path analysis: TX submit and RX poll must have zero unnecessary copies
2. DMA sync patterns: verify PREWRITE/POSTREAD placement
3. Interrupt moderation: verify adaptive coalescing
4. Ring size and batch processing
5. Cache-line alignment of descriptor structures
6. Zero-copy verification

Return JSON:
{{
  "perf_score": <float 0-100>,
  "hot_path_clean": true/false,
  "findings": [{{"area": "...", "issue": "...", "recommendation": "..."}}],
  "zero_copy_verified": true/false
}}"""

    def _process_result(self, state: PipelineState, content: str):
        from .json_utils import parse_llm_json_response
        parsed = parse_llm_json_response(content, self.logger)
        # Performance findings feed into substep results
        if parsed:
            state['substep_results'].append({
                'substep_id': 'phase5.performance',
                'description': 'Performance analysis',
                'gate_passed': parsed.get('hot_path_clean', False),
            })


class PortabilityValidatorAgent(_PortingAgent):
    """Phase 5: Validate cross-OS portability of the portable core."""
    AGENT_NAME = "portability_validator"
    ROLE_DESCRIPTION = "Portability Validator"

    def _task_prompt(self, state: PipelineState) -> str:
        driver = state.get('driver_name', 'unknown')
        layout = state.get('directory_layout', {})
        core_dir = layout.get('core_dir', '')
        return f"""Validate portability of the portable NIC core for driver: {driver}
Core directory: {core_dir}

PORTABILITY CHECKS:
1. Zero OS-specific includes in core/ (no linux/*, sys/*, windows.h)
2. Only portable types (uint32_t, uint64_t, void*, struct nic_packet, etc.)
3. No direct memory allocation in core (adapter provides buffers)
4. No direct I/O in core (register access via portable macros)
5. Compile-time portability (would compile on any OS or user-space)
6. Compute portability_score = (portable_lines / total_core_lines) * 100

THRESHOLD: portability_score must be ≥ 95

Return JSON:
{{
  "portability_score": <float>,
  "os_specific_leaks": [{{"file": "...", "line": N, "offending_code": "..."}}],
  "total_core_lines": <N>,
  "portable_lines": <N>
}}"""

    def _process_result(self, state: PipelineState, content: str):
        from .json_utils import parse_llm_json_response
        parsed = parse_llm_json_response(content, self.logger)
        if parsed:
            state['portability_score'] = parsed.get('portability_score', 0)


class RiskAuditorAgent(_PortingAgent):
    """Phase 6: Audit the living risk register."""
    AGENT_NAME = "risk_auditor"
    ROLE_DESCRIPTION = "Risk Auditor"

    def _task_prompt(self, state: PipelineState) -> str:
        driver = state.get('driver_name', 'unknown')
        current_risks = state.get('risk_register', [])
        ns = state.get('native_score', 0)
        ps = state.get('portability_score', 0)

        return f"""Audit the risk register for driver porting: {driver}
Current native_score: {ns:.1f} | portability_score: {ps:.1f}
Existing risks: {len(current_risks)}

RISK CATEGORIES TO CHECK:
1. framework_leak — any iflib/linuxkpi/DPDK remnants
2. dma_mismatch — DMA mapping lifecycle errors
3. endian — byte-order assumptions in descriptor formats
4. interrupt_race — race conditions in interrupt/taskqueue paths
5. memory_leak — unfreed DMA mappings or mbufs
6. build_failure — missing includes or link errors
7. behavioral_divergence — logic differs from Linux reference

For each risk found, assign severity (critical/high/medium/low) and mitigation.

Return JSON:
{{
  "risks": [
    {{
      "risk_id": "R001",
      "severity": "critical|high|medium|low",
      "category": "...",
      "description": "...",
      "mitigation": "...",
      "status": "open|mitigated"
    }}
  ],
  "critical_count": <N>,
  "summary": "..."
}}"""

    def _process_result(self, state: PipelineState, content: str):
        from .json_utils import parse_llm_json_response
        parsed = parse_llm_json_response(content, self.logger)
        if parsed and 'risks' in parsed:
            for risk in parsed['risks']:
                risk['detected_at'] = 'phase6'
                state['risk_register'].append(risk)


class VerificationExecutorAgent(_PortingAgent):
    """Phase 6: Execute build & test verification on target VMs."""
    AGENT_NAME = "verification_executor"
    ROLE_DESCRIPTION = "Verification Executor"

    def _task_prompt(self, state: PipelineState) -> str:
        driver = state.get('driver_name', 'unknown')
        target_os = state.get('target_os', 'freebsd')
        conn = state.get('connection_info', {})

        return f"""Execute build and test verification for driver: {driver} on {target_os}.
Connection info available: {bool(conn)}

VERIFICATION STEPS:
1. Build the kernel module (kldload-ready for FreeBSD)
2. Run the TDD test suite — all tests must pass
3. If SSH to VM is available:
   - Copy artifacts to target VM
   - Build on target
   - Load module: kldload {driver}
   - Capture: dmesg | tail -50
   - Capture: ifconfig / ethtool equivalent
   - Run iperf3 if network is reachable
4. Compare Linux vs {target_os} behaviour

Return JSON:
{{
  "build_ok": true/false,
  "tests_passed": true/false,
  "test_results": [
    {{"test_name": "...", "target_os": "{target_os}", "passed": true/false, "output": "..."}}
  ],
  "verification_summary": "..."
}}"""

    def _process_result(self, state: PipelineState, content: str):
        from .json_utils import parse_llm_json_response
        parsed = parse_llm_json_response(content, self.logger)
        if parsed:
            for tr in parsed.get('test_results', []):
                state['test_results'].append(tr)
            state['substep_results'].append({
                'substep_id': 'phase6.verification',
                'description': 'Build & test verification',
                'build_ok': parsed.get('build_ok', False),
                'tests_passed': parsed.get('tests_passed', False),
                'gate_passed': parsed.get('build_ok', False) and parsed.get('tests_passed', False),
            })


# =====================================================================
# Backward-compatible aliases (old analyzer names)
# =====================================================================
FwdkAnalyzer = TDDWriterAgent
UartAnalyzer = CoderAgent
SimicsAnalyzer = NativeValidatorAgent
