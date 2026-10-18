from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

class Severity(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"

class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"

@dataclass(frozen=True, slots=True)
class RuleSpec:
    rule_id: str
    name: str
    group: str
    category: str
    validation_logic: str
    severity: Severity
    required_metrics: tuple[str, ...]
    description: str
    business_purpose: str
    formula: str
    threshold: str
    recommendation: str
    risk_impact: str

@dataclass(frozen=True, slots=True)
class RuleResult:
    rule_id: str
    status: Status
    severity: Severity
    company: str
    year: int
    message: str
    observed: dict[str, Any] = field(default_factory=dict)
