"""
Agent Skills Module — NIC Driver Porting Domain

Provides domain-specific Best Known Methods (BKMs) for each specialist agent.
Skills files contain porting patterns, API mapping guidance, and domain knowledge.

Skills Files:
- source_analysis_skills.md:  Source analysis & directory scaffolding
- api_mapping_skills.md:      Linux→FreeBSD/Windows API mapping tables
- tdd_writer_skills.md:       CppUTest TDD test patterns for ported drivers
- coder_skills.md:            Data-plane porting implementation patterns
- validation_skills.md:       Native validation, code review, performance & portability
- risk_auditor_skills.md:     Risk register audit & verification execution
"""

from pathlib import Path

SKILLS_DIR = Path(__file__).parent


def load_skill(skill_name: str) -> str:
    """
    Load a skill file by name.

    Args:
        skill_name: Name of the skill file (without extension)
                   Options: source_analysis, api_mapping, tdd_writer, coder, validation, risk_auditor

    Returns:
        Content of the skill file as string

    Raises:
        FileNotFoundError: If skill file doesn't exist
    """
    skill_file = SKILLS_DIR / f"{skill_name}_skills.md"
    if not skill_file.exists():
        raise FileNotFoundError(f"Skill file not found: {skill_file}")
    return skill_file.read_text()


def get_source_analysis_skills() -> str:
    """Load source analysis agent skills."""
    return load_skill("source_analysis")


def get_api_mapping_skills() -> str:
    """Load API mapping skills."""
    return load_skill("api_mapping")


def get_tdd_writer_skills() -> str:
    """Load TDD test writer skills."""
    return load_skill("tdd_writer")


def get_coder_skills() -> str:
    """Load coder / porting implementation skills."""
    return load_skill("coder")


def get_validation_skills() -> str:
    """Load validation, review, performance & portability skills."""
    return load_skill("validation")


def get_risk_auditor_skills() -> str:
    """Load risk auditor & verification skills."""
    return load_skill("risk_auditor")


# Backward-compatible aliases
get_data_collector_skills = get_source_analysis_skills
get_fusioner_skills = get_validation_skills


def list_available_skills() -> list:
    """List all available skill files."""
    return [f.stem.replace("_skills", "") for f in SKILLS_DIR.glob("*_skills.md")]
