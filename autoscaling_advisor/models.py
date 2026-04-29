from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

Severity = Literal["ok", "warn", "error", "info"]
Strategy = Literal["basic-hpa", "tuned-hpa", "keda-prometheus"]


@dataclass
class HPAConfig:
    enabled: bool = False
    min_replicas: int = 0
    max_replicas: int = 0
    cpu_target: int = 0
    keda_enabled: bool = False


@dataclass
class ResourceConfig:
    cpu_request: str = ""
    memory_request: str = ""
    cpu_limit: str = ""
    memory_limit: str = ""


@dataclass
class ProbeConfig:
    readiness_enabled: bool = False
    readiness_initial_delay: int = 0
    readiness_period: int = 10
    liveness_enabled: bool = False


@dataclass
class AppConfig:
    startup_delay_seconds: int = 0
    shutdown_drain_seconds: int = 0
    prestop_sleep_seconds: int = 0
    termination_grace_period: int = 30


@dataclass
class PDBConfig:
    enabled: bool = False
    min_available: Optional[int] = None


@dataclass
class ObsConfig:
    service_monitor_enabled: bool = False
    metrics_path: str = "/metrics"


@dataclass
class AppSignals:
    exposes_metrics: bool = False
    uses_prometheus: bool = False
    has_request_metric: bool = False
    has_queue_metric: bool = False
    has_queue_integration: bool = False
    is_background_worker: bool = False
    is_cpu_heavy: bool = False


@dataclass
class ScanResult:
    source: str
    hpa: HPAConfig = field(default_factory=HPAConfig)
    resources: ResourceConfig = field(default_factory=ResourceConfig)
    probe: ProbeConfig = field(default_factory=ProbeConfig)
    app: AppConfig = field(default_factory=AppConfig)
    pdb: PDBConfig = field(default_factory=PDBConfig)
    obs: ObsConfig = field(default_factory=ObsConfig)
    signals: AppSignals = field(default_factory=AppSignals)
    replicas: int = 1


@dataclass
class AuditItem:
    check: str
    status: Severity
    detail: str


@dataclass
class Change:
    path: str
    old: object
    new: object
    reason: str


@dataclass
class StrategyCandidate:
    name: Strategy
    display_name: str
    score: int
    reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)


@dataclass
class RecommendationResult:
    best: StrategyCandidate
    candidates: list[StrategyCandidate]
    audit: list[AuditItem]
    scan: ScanResult
