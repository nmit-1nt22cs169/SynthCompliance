"""Structural validators + golden-set fidelity + TSTR evaluator."""

from .duplicate_check import check_duplicates
from .golden_fidelity import score_golden_fidelity
from .label_alignment import check_label_alignment
from .pii_leakage import check_pii_leakage
from .report import build_validation_report, run_all_validators
from .scenario_coverage import compute_scenario_coverage
from .schema_validity import check_schema_validity
from .tstr import run_tstr

__all__ = [
    "check_duplicates",
    "check_label_alignment",
    "check_pii_leakage",
    "check_schema_validity",
    "compute_scenario_coverage",
    "score_golden_fidelity",
    "build_validation_report",
    "run_all_validators",
    "run_tstr",
]
