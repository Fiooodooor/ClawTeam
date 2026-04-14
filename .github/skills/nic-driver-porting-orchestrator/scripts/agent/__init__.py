"""
Multi-Agent Swarm Orchestrator for NIC Driver Porting

This package contains the LangGraph-based multi-agent swarm that autonomously
drives the entire NIC data-plane porting pipeline — producing complete, fully
ported, buildable, testable, framework-independent driver code.

The swarm uses:
- LangGraph StateGraph for multi-phase pipeline orchestration
- Specialist worker agents (TDD Writer, Coder, Native Validator,
  Code Reviewer, Performance Engineer, Portability Validator,
  Risk Auditor, Verification Executor)
- ReAct agent pattern with self-critique and conditional gates
- Azure OpenAI GPT-4.1 as the decision-making LLM
- SSH access to target OS VMs for build & test verification
"""

__version__ = "2.0.0"
__release_date__ = "2026-03-23"
__description__ = "Multi-agent swarm orchestrator for autonomous NIC driver data-plane porting"
