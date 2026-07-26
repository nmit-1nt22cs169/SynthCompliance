"""Deterministic scenario engine — always works offline for demo reliability."""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from synthcompliance_taxonomy.controls import TAXONOMY, controls_for_packs
from synthcompliance_taxonomy.roster import ASSET_LIST, ROLE_LIMITS, USER_ROSTER

# Train oversampled targets (±3%)
TRAIN_TARGETS = {
    "normal": 0.60,
    "suspicious": 0.15,
    "violation": 0.20,
    "false_positive": 0.05,
}

EVAL_TARGETS = {
    "normal": 0.92,
    "suspicious": 0.06,
    "violation": 0.008,
    "false_positive": 0.012,
}

EXPLANATIONS = {
    "segregation_of_duties": "User {uid} both created and approved {resource}, violating maker-checker separation under {cid}.",
    "privileged_access_misuse": "Privileged account {uid} ({role}) misused elevated access on {resource} ({cid}).",
    "change_without_approval": "Change to {resource} deployed by {uid} without a recorded approval step ({cid}).",
    "journal_entry_override": "Journal entry override on {resource} by {uid} bypassed standard JE controls ({cid}).",
    "period_close_breach": "Period-close control breach on {resource} during quarter-end pressure window ({cid}).",
    "vendor_master_tamper": "Unauthorized vendor-master modification on {resource} by {uid} ({cid}).",
    "audit_trail_gap": "Audit trail gap detected for action on {resource}; required logging missing ({cid}).",
    "access_lifecycle_breach": "Access lifecycle breach: {uid} retained or gained access to {resource} improperly ({cid}).",
    "late_dsar": "DSAR on {resource} fulfilled after the 30-day window with no extension justification ({cid}).",
    "erasure_failure": "Right-to-erasure request failed for {resource}; residual PII retained ({cid}).",
    "unlawful_basis": "Processing of {resource} by {uid} lacked a lawful basis under Art. 6 ({cid}).",
    "purpose_limitation_breach": "Data from {resource} reused beyond stated purpose by {uid} ({cid}).",
    "data_minimisation_breach": "Excessive personal data collected/exported via {resource} ({cid}).",
    "cross_border_transfer": "Cross-border transfer of {resource} without adequate Art. 44-49 safeguards ({cid}).",
    "breach_notification_late": "Personal-data breach notification for {resource} exceeded the 72-hour threshold ({cid}).",
    "consent_lifecycle_breach": "Consent record for {resource} was expired/withdrawn when {uid} processed it ({cid}).",
}

ACTION_FOR_TYPE = {
    "segregation_of_duties": "APPROVE",
    "privileged_access_misuse": "UPDATE",
    "change_without_approval": "UPDATE",
    "journal_entry_override": "CREATE",
    "period_close_breach": "APPROVE",
    "vendor_master_tamper": "UPDATE",
    "audit_trail_gap": "DELETE",
    "access_lifecycle_breach": "READ",
    "late_dsar": "EXPORT",
    "erasure_failure": "DELETE",
    "unlawful_basis": "READ",
    "purpose_limitation_breach": "EXPORT",
    "data_minimisation_breach": "EXPORT",
    "cross_border_transfer": "EXPORT",
    "breach_notification_late": "CREATE",
    "consent_lifecycle_breach": "UPDATE",
}


def _rng(seed: str) -> random.Random:
    h = int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16)
    return random.Random(h)


def _quarter_end(rng: random.Random) -> datetime:
    anchors = [
        datetime(2026, 3, 27, 18, 0, tzinfo=timezone.utc),
        datetime(2026, 6, 26, 17, 30, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 19, 0, tzinfo=timezone.utc),
        datetime(2026, 12, 29, 16, 45, tzinfo=timezone.utc),
    ]
    base = rng.choice(anchors)
    return base + timedelta(hours=rng.randint(0, 36), minutes=rng.randint(0, 59))


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class ScenarioEngine:
    """Turns a request (packs, control classes, scenario mix, n_logs) into a concrete generation
    plan: how many logs of each scenario class (normal/suspicious/violation/false_positive), and
    how those violation slots split across violation_types. Seeded from `seed:mode:n_logs` so the
    same request reproduces the same corpus."""

    def __init__(
        self,
        *,
        packs: list[str],
        control_classes: list[str] | None,
        scenario_mix: dict[str, float] | None,
        n_logs: int,
        industry: str = "financial_services",
        seed: str = "demo",
        mode: str = "train",  # train | eval
    ) -> None:
        self.packs = [p.upper() for p in packs]
        self.available = controls_for_packs(self.packs)
        if control_classes:
            allowed = set(control_classes)
            self.available = [c for c in self.available if c["violation_type"] in allowed]
        if not self.available:
            self.available = controls_for_packs(self.packs) or list(TAXONOMY.values())
        self.mix = scenario_mix or (TRAIN_TARGETS if mode == "train" else EVAL_TARGETS)
        self.n_logs = max(n_logs, 20)
        self.industry = industry
        self.seed = seed
        self.mode = mode
        self.rng = _rng(f"{seed}:{mode}:{n_logs}")

    def allocate_counts(self) -> dict[str, int]:
        """Allocate scenario class counts from mix (sum≈n_logs)."""
        keys = ["normal", "suspicious", "violation", "false_positive"]
        raw = {k: self.mix.get(k, 0) for k in keys}
        s = sum(raw.values()) or 1
        counts = {k: int(round(self.n_logs * (v / s))) for k, v in raw.items()}
        # fix rounding
        drift = self.n_logs - sum(counts.values())
        counts["normal"] += drift
        # enforce ≥15 per selected violation_type when train+violation budget allows
        return counts

    def compose_plan(self) -> dict[str, Any]:
        """Spread allocate_counts()'s violation budget across the available violation_types —
        round-robin once each type has at least 1 (if the budget covers all types), or a first-N
        subset otherwise — then package everything generate_corpus() needs to build the corpus."""
        counts = self.allocate_counts()
        v_budget = counts["violation"]
        types = [c["violation_type"] for c in self.available]
        per_type: dict[str, int] = {t: 0 for t in types}
        if types and v_budget > 0:
            if v_budget >= len(types):
                for t in types:
                    per_type[t] = 1
                remaining = v_budget - len(types)
                i = 0
                while remaining > 0:
                    per_type[types[i % len(types)]] += 1
                    remaining -= 1
                    i += 1
            else:
                focus = types
                base = max(1, v_budget // max(len(focus), 1))
                for t in focus[:v_budget]:
                    per_type[t] = 1
                remaining = v_budget - sum(per_type.values())
                i = 0
                while remaining > 0 and focus:
                    per_type[focus[i % len(focus)]] += 1
                    remaining -= 1
                    i += 1
        return {
            "mode": self.mode,
            "n_logs": self.n_logs,
            "scenario_counts": counts,
            "violation_type_counts": per_type,
            "packs": self.packs,
            "industry": self.industry,
            "false_positive_count": counts["false_positive"],
            "suspicious_count": counts["suspicious"],
        }
