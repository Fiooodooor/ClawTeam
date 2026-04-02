"""
Pipeline State Schema — Multi-Agent Swarm Orchestrator for NIC Driver Porting

Defines the typed state that flows through all porting pipeline phases (0–7)
plus Sections 12–14 (Testing, Risk Register, Final Validation).

Uses TypedDict for clear type hints and LangGraph compatibility.
LangGraph uses Annotated types for state reducers (how to merge updates).
"""

from typing import TypedDict, Dict, List, Optional, Any, Annotated
from langchain_core.messages import BaseMessage


def merge_dicts(left: Dict, right: Dict) -> Dict:
    """Merge two dictionaries, right takes precedence"""
    result = left.copy()
    result.update(right)
    return result


def merge_lists(left: List, right: List) -> List:
    """Concatenate two lists"""
    return left + right


# ---------------------------------------------------------------------------
# Phase 0: Core Layout & Build Skeletons
# ---------------------------------------------------------------------------

class DirectoryLayout(TypedDict, total=False):
    """Driver directory layout produced by Phase 0"""
    core_dir: str           # portable_nic_core (zero OS calls)
    os_adapters: Dict[str, str]  # {os_name: adapter_dir_path}
    tests_dir: str          # CppUTest / native mocks
    docs_dir: str
    build_system: str       # Makefile.multi / Kbuild / meson.build


class SourceAnalysis(TypedDict, total=False):
    """Analysis of the reference Linux driver source"""
    driver_name: str
    source_dir: str         # path to reference Linux driver source
    dataplane_files: List[str]   # files containing TX/RX/DMA/interrupt logic
    excluded_files: List[str]    # PHY, firmware, config — not part of port
    linux_apis_found: List[str]  # linux-specific API calls discovered
    descriptor_formats: List[str]  # TX/RX descriptor struct names
    offload_features: List[str]  # TSO, checksum, RSS, VLAN


# ---------------------------------------------------------------------------
# Phase 1: API Inventory & Native Mapping Tables
# ---------------------------------------------------------------------------

class APIMapping(TypedDict, total=False):
    """Single Linux→target-OS API mapping entry"""
    linux_api: str
    target_api: str
    target_os: str
    category: str       # dma, packet_buffer, tx_rx, interrupt, offload
    notes: str
    tdd_tested: bool


# ---------------------------------------------------------------------------
# Phase 2–5: Porting Implementation Cycle
# ---------------------------------------------------------------------------

class PortingArtifact(TypedDict, total=False):
    """A single code artifact produced during porting"""
    file_path: str
    artifact_type: str    # source, header, test, makefile
    description: str
    native_score: float   # 0–100: % of native OS calls (target ≥ 98)
    portability_score: float  # 0–100 (target ≥ 95)
    build_ok: bool
    tests_passed: bool


class SubstepResult(TypedDict, total=False):
    """Result of a single porting sub-step through the specialist agent chain"""
    substep_id: str       # e.g. "phase3.substep2"
    description: str
    tdd_tests_written: List[str]
    code_files_modified: List[str]
    native_score: float
    portability_score: float
    build_ok: bool
    tests_passed: bool
    review_passed: bool
    risk_findings: List[Dict[str, Any]]
    debate_summary: str   # multi-agent debate summary
    gate_passed: bool     # all gates met


# ---------------------------------------------------------------------------
# Section 12: Testing & Verification
# ---------------------------------------------------------------------------

class TestResult(TypedDict, total=False):
    """Result from a build/test verification run"""
    test_name: str
    target_os: str
    passed: bool
    output: str           # dmesg / ethtool / iperf3 captured output
    duration_seconds: float


# ---------------------------------------------------------------------------
# Section 13: Risk Register
# ---------------------------------------------------------------------------

class RiskEntry(TypedDict, total=False):
    """Single risk register entry"""
    risk_id: str
    severity: str         # critical, high, medium, low
    category: str         # framework_leak, dma_mismatch, endian, etc.
    description: str
    mitigation: str
    status: str           # open, mitigated, accepted
    detected_at: str      # phase/substep where detected


# ---------------------------------------------------------------------------
# Main Pipeline State
# ---------------------------------------------------------------------------

class PipelineState(TypedDict, total=False):
    """
    Complete pipeline state flowing through all porting phases (0–7 + 12–14).

    This state is passed between all specialist worker agents in the LangGraph
    pipeline.  Each phase reads from previous outputs and writes its own.

    Agent chain per sub-step:
      TDD Writer → Coder → Native Validator → Reviewer →
      Performance Engineer → Portability Validator → Risk Auditor →
      Verification Executor → Supervisor gate
    """
    # Input parameters
    driver_name: str          # e.g. "ixgbe", "ice", "mynic_native"
    target_os: str            # primary target: "freebsd" (default)
    secondary_targets: List[str]  # ["windows", "illumos", "netbsd", "rtos"]
    source_dir: str           # path to reference Linux driver source
    output_dir: str           # path to output artifacts

    # Connection info (SSH to VMs)
    connection_info: Dict[str, Any]  # parsed from connection-info YAML

    # Message history for agent conversations
    messages: Annotated[List[BaseMessage], merge_lists]

    # Phase 0: Core Layout & Source Analysis
    directory_layout: DirectoryLayout
    source_analysis: SourceAnalysis

    # Phase 1: API Inventory
    api_mappings: List[APIMapping]

    # Phases 2–5: Porting sub-step results (accumulated)
    substep_results: Annotated[List[SubstepResult], merge_lists]
    porting_artifacts: Annotated[List[PortingArtifact], merge_lists]

    # Section 12: Test results
    test_results: Annotated[List[TestResult], merge_lists]

    # Section 13: Living risk register
    risk_register: Annotated[List[RiskEntry], merge_lists]

    # Scores (latest gate values)
    native_score: float       # target ≥ 98
    portability_score: float  # target ≥ 95

    # Phase 7 / Section 14: Final Validation
    final_checklist: Dict[str, bool]  # checklist item → pass/fail
    final_report_path: str

    # Pipeline control
    errors: Annotated[List[str], merge_lists]
    should_continue: bool
    current_phase: str
    phase_status: Annotated[Dict[str, str], merge_dicts]


def create_initial_state(
    driver_name: str,
    target_os: str = "freebsd",
    output_dir: str = "./artifacts",
    source_dir: str = "",
    connection_info: Optional[Dict[str, Any]] = None,
) -> PipelineState:
    """Create initial pipeline state for a driver porting run"""
    return PipelineState(
        driver_name=driver_name,
        target_os=target_os,
        secondary_targets=[],
        source_dir=source_dir,
        output_dir=output_dir,
        connection_info=connection_info or {},
        messages=[],
        directory_layout={},
        source_analysis={},
        api_mappings=[],
        substep_results=[],
        porting_artifacts=[],
        test_results=[],
        risk_register=[],
        native_score=0.0,
        portability_score=0.0,
        final_checklist={},
        final_report_path="",
        errors=[],
        should_continue=True,
        current_phase="init",
        phase_status={},
    )
