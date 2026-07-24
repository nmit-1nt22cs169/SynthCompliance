"""Fixed user roster (50) and asset list (200) for closed-world generation."""

from __future__ import annotations

ROLES = (
    "finance_analyst",
    "senior_accountant",
    "controller",
    "cfo_delegate",
    "engineer",
    "sre",
    "admin",
    "iam_admin",
    "support_agent",
    "privacy_officer",
    "dpo",
    "sales_rep",
    "hr_specialist",
    "vendor_manager",
    "auditor",
    "contractor",
)

# Spending / approval limits by role (SOX realism)
ROLE_LIMITS: dict[str, dict[str, float | int]] = {
    "finance_analyst": {"approve_max": 5_000, "create_je": True},
    "senior_accountant": {"approve_max": 25_000, "create_je": True},
    "controller": {"approve_max": 250_000, "create_je": True},
    "cfo_delegate": {"approve_max": 1_000_000, "create_je": True},
    "engineer": {"approve_max": 0, "create_je": False},
    "sre": {"approve_max": 0, "create_je": False},
    "admin": {"approve_max": 0, "create_je": False},
    "iam_admin": {"approve_max": 0, "create_je": False},
    "support_agent": {"approve_max": 0, "create_je": False},
    "privacy_officer": {"approve_max": 0, "create_je": False},
    "dpo": {"approve_max": 0, "create_je": False},
    "sales_rep": {"approve_max": 1_000, "create_je": False},
    "hr_specialist": {"approve_max": 0, "create_je": False},
    "vendor_manager": {"approve_max": 50_000, "create_je": False},
    "auditor": {"approve_max": 0, "create_je": False},
    "contractor": {"approve_max": 0, "create_je": False},
}

USER_ROSTER: list[dict[str, str]] = []
for i in range(50):
    role = ROLES[i % len(ROLES)]
    USER_ROSTER.append(
        {
            "user_id": f"u_{1000 + i:04d}",
            "role": role,
        }
    )

SYSTEMS = (
    "ledger-svc",
    "iam-core",
    "crm-core",
    "privacy-hub",
    "deploy-pipeline",
    "hr-core",
    "vendor-master",
    "change-mgmt",
    "consent-svc",
    "transfer-gateway",
)

_RESOURCE_TEMPLATES = [
    "finance/ledger/q{q}_close",
    "finance/invoices/{n}",
    "finance/journal/{n}",
    "finance/accruals/{n}",
    "iam/roles/admin_grants",
    "iam/users/{n}/permissions",
    "iam/policies/access_review",
    "iam/sessions/{n}",
    "customer_pii/records/{n}",
    "customer_pii/exports/{n}",
    "support/tickets/{n}",
    "dsar/requests/{n}",
    "privacy/consent_records/{n}",
    "privacy/erasure/{n}",
    "deploy/config/prod_gateway",
    "deploy/config/billing_worker",
    "deploy/releases/{n}",
    "change/tickets/{n}",
    "hr/employee_records/{n}",
    "hr/payroll/{n}",
    "vendor/master/{n}",
    "vendor/bank_details/{n}",
    "audit/trail/{n}",
    "transfer/cross_border/{n}",
    "breach/incidents/{n}",
]


def _build_assets(n: int = 200) -> list[dict[str, str]]:
    assets: list[dict[str, str]] = []
    for i in range(n):
        tmpl = _RESOURCE_TEMPLATES[i % len(_RESOURCE_TEMPLATES)]
        resource = tmpl.format(q=(i % 4) + 1, n=10000 + i)
        system = SYSTEMS[i % len(SYSTEMS)]
        assets.append(
            {
                "resource_id": f"res_{i:04d}",
                "resource": resource,
                "system": system,
            }
        )
    return assets


ASSET_LIST = _build_assets(200)

assert len(USER_ROSTER) == 50
assert len(ASSET_LIST) == 200
