"""
Cross-Phase Validation Agent for the NIC Driver Porting Swarm

Correlates results from all specialist agents across porting phases to:
- Validate that native scores and portability scores meet thresholds
- Cross-check risk register against verification results
- Ensure behavioural identity between Linux reference and ported driver
- Produce a unified validation report before final checklist
"""

import os
import sys
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage

# Import state types
from .state import PipelineState


class ValidationAgent:
    """
    Cross-phase validation agent.

    Synthesises results from all porting phases and specialist agents
    into a unified validation report, checking gate conditions.
    """

    def __init__(self, llm: AzureChatOpenAI, logger: logging.Logger):
        self.llm = llm
        self.logger = logger

    def run(self, state: PipelineState) -> PipelineState:
        """
        Run cross-phase validation.

        Checks all gate conditions and produces a validation summary
        stored in the pipeline state.
        """
        prompt = self._build_prompt(state)

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            state['substep_results'].append({
                'substep_id': 'validation.cross_phase',
                'description': 'Cross-phase validation',
                'debate_summary': response.content,
                'native_score': state.get('native_score', 0),
                'portability_score': state.get('portability_score', 0),
                'gate_passed': (
                    state.get('native_score', 0) >= 98
                    and state.get('portability_score', 0) >= 95
                ),
            })
        except Exception as e:
            self.logger.error(f"Validation failed: {e}")
            state['errors'].append(f"Cross-phase validation failed: {str(e)}")

        return state

    def _build_prompt(self, state: PipelineState) -> str:
        driver = state.get('driver_name', 'unknown')
        target_os = state.get('target_os', 'freebsd')
        ns = state.get('native_score', 0)
        ps = state.get('portability_score', 0)
        artifacts = state.get('porting_artifacts', [])
        risks = state.get('risk_register', [])
        test_results = state.get('test_results', [])
        substeps = state.get('substep_results', [])

        risk_summary = "\n".join(
            f"  - [{r.get('severity','?')}] {r.get('category','')}: {r.get('description','')}"
            for r in risks[:20]
        )

        test_summary = "\n".join(
            f"  - {t.get('test_name','?')}: {'PASS' if t.get('passed') else 'FAIL'}"
            for t in test_results[:20]
        )

        return f"""You are the Cross-Phase Validation Agent for the NIC driver porting swarm.

DRIVER: {driver}
TARGET OS: {target_os}

CURRENT SCORES:
  native_score:      {ns:.1f} (threshold: ≥ 98)
  portability_score: {ps:.1f} (threshold: ≥ 95)

PORTING ARTIFACTS: {len(artifacts)} files produced
SUBSTEPS COMPLETED: {len(substeps)}

RISK REGISTER ({len(risks)} entries):
{risk_summary if risk_summary else '  (empty)'}

TEST RESULTS ({len(test_results)} tests):
{test_summary if test_summary else '  (no tests run yet)'}

VALIDATION TASKS:
1. Verify scores meet thresholds (native ≥ 98, portability ≥ 95)
2. Check for framework leaks (iflib, linuxkpi, rte_*, DPDK) in artifacts
3. Verify all critical risks have mitigations
4. Confirm behavioural identity with Linux reference
5. Summarise gate pass/fail status

CORE PORTING PRINCIPLES:
- Correctness-first TDD
- Zero frameworks — native OS calls only
- Thin OAL seams — portable core has ZERO OS calls
- Every register write, descriptor format, offload calculation identical to Linux

Return a structured markdown validation report with:
- Gate Status (PASS/FAIL for each threshold)
- Remaining Issues
- Recommendations for any failing gates
"""


# Backward-compatible alias
FusionAgent = ValidationAgent


def create_validation_agent(llm: AzureChatOpenAI, logger: logging.Logger) -> ValidationAgent:
    """Factory function to create validation agent"""
    return ValidationAgent(llm, logger)


# Keep old name
create_fusion_agent = create_validation_agent
