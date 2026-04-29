from __future__ import annotations

from .auditor import audit
from .models import Change, RecommendationResult, ScanResult, StrategyCandidate


def _clamp(v: int) -> int:
    return max(0, min(100, v))


def _score_basic_hpa(s: ScanResult) -> StrategyCandidate:
    score = 50
    reasons: list[str] = []
    risks: list[str] = []
    changes: list[Change] = []

    if not s.hpa.enabled:
        score -= 40
        risks.append("HPA 비활성화")
    if not s.resources.cpu_request:
        score -= 20
        risks.append("CPU request 없음 — HPA CPU 메트릭 동작 안 함")
    else:
        score += 10

    if s.signals.is_cpu_heavy:
        score += 15
        reasons.append("CPU-heavy 워크로드 감지")
    if s.hpa.cpu_target and s.hpa.cpu_target <= 70:
        score += 10
    if s.hpa.min_replicas >= 2:
        score += 5

    if s.app.startup_delay_seconds > 5:
        score -= 10
        risks.append(f"시작 지연 {s.app.startup_delay_seconds}s — scale-out 속도 제한")

    if s.obs.service_monitor_enabled or s.signals.exposes_metrics:
        score -= 5  # 메트릭이 있으면 basic보다 더 나은 전략이 있음

    if s.hpa.cpu_target > 70:
        changes.append(Change(
            "hpa.targetCPUUtilizationPercentage",
            s.hpa.cpu_target, 70,
            "scale-out 발동 임계점 낮추기",
        ))

    return StrategyCandidate(
        name="basic-hpa",
        display_name="Basic HPA",
        score=_clamp(score),
        reasons=reasons,
        risks=risks,
        changes=changes,
    )


def _score_tuned_hpa(s: ScanResult) -> StrategyCandidate:
    score = 55
    reasons: list[str] = []
    risks: list[str] = []
    changes: list[Change] = []

    if not s.hpa.enabled:
        score -= 40
        risks.append("HPA 비활성화")
    if not s.resources.cpu_request:
        score -= 15
        risks.append("CPU request 없음")

    if s.app.startup_delay_seconds > 5:
        score += 12
        reasons.append(f"시작 지연 {s.app.startup_delay_seconds}s — 튜닝 여지 큼")
        changes.append(Change(
            "app.startupDelaySeconds",
            s.app.startup_delay_seconds, 3,
            "빠른 시작으로 scale-out 효율 향상",
        ))

    if s.hpa.min_replicas < 3:
        score += 12
        reasons.append(f"minReplicas={s.hpa.min_replicas} — 사전 용량 확보 가능")
        new_min = max(3, s.hpa.min_replicas + 1)
        changes.append(Change(
            "hpa.minReplicas",
            s.hpa.min_replicas, new_min,
            "스파이크 전 헤드룸 확보",
        ))

    if s.hpa.cpu_target > 65:
        score += 10
        reasons.append(f"CPU target {s.hpa.cpu_target}% — 낮추면 더 일찍 scale-out")
        changes.append(Change(
            "hpa.targetCPUUtilizationPercentage",
            s.hpa.cpu_target, 60,
            "scale-out 조기 발동",
        ))

    if s.probe.readiness_period > 5:
        score += 8
        changes.append(Change(
            "deployment.readinessProbe.periodSeconds",
            s.probe.readiness_period, 3,
            "빠른 readiness 체크 → 빠른 워밍업",
        ))

    if s.probe.readiness_initial_delay > 5:
        changes.append(Change(
            "deployment.readinessProbe.initialDelaySeconds",
            s.probe.readiness_initial_delay, 2,
            "초기 대기 단축",
        ))

    if not s.pdb.enabled:
        score -= 5
        risks.append("PDB 없음 — 롤아웃 중 HA 미보장")

    return StrategyCandidate(
        name="tuned-hpa",
        display_name="Tuned HPA",
        score=_clamp(score),
        reasons=reasons,
        risks=risks,
        changes=changes,
    )


def _score_keda(s: ScanResult) -> StrategyCandidate:
    score = 35
    reasons: list[str] = []
    risks: list[str] = []
    changes: list[Change] = []

    if s.signals.has_queue_integration:
        score += 30
        reasons.append("큐 연동 감지 — KEDA 큐 스케일러 최적")
    if s.signals.exposes_metrics:
        score += 20
        reasons.append("Prometheus 메트릭 노출 — RPS/동시접속 기반 스케일링 가능")
    if s.signals.has_request_metric:
        score += 15
        reasons.append("요청 메트릭 감지 — scale-out 선행 지표 활용 가능")
    if s.signals.has_queue_metric:
        score += 20
        reasons.append("Queue depth 메트릭 감지 — KEDA 트리거 직접 연결 가능")
    if s.signals.is_background_worker:
        score += 25
        reasons.append("Background worker 패턴 — KEDA가 자연스러운 선택")
    if s.obs.service_monitor_enabled:
        score += 10
        reasons.append("ServiceMonitor 이미 설정됨")

    if not s.signals.exposes_metrics and not s.signals.has_queue_integration:
        score -= 20
        risks.append("메트릭 엔드포인트/큐 연동 미감지 — KEDA 트리거 소스 필요")

    if s.hpa.keda_enabled:
        score += 10
        reasons.append("KEDA 이미 차트에 활성화됨")
    else:
        changes.append(Change("keda.enabled", False, True, "KEDA CRD 활성화"))

    if not s.signals.exposes_metrics:
        changes.append(Change(
            "serviceMonitor.enabled", False, True,
            "/metrics 노출 후 ServiceMonitor 활성화 필요",
        ))

    return StrategyCandidate(
        name="keda-prometheus",
        display_name="KEDA + Prometheus",
        score=_clamp(score),
        reasons=reasons,
        risks=risks,
        changes=changes,
    )


def recommend(scan: ScanResult) -> RecommendationResult:
    candidates = sorted(
        [_score_basic_hpa(scan), _score_tuned_hpa(scan), _score_keda(scan)],
        key=lambda c: c.score,
        reverse=True,
    )
    return RecommendationResult(
        best=candidates[0],
        candidates=candidates,
        audit=audit(scan),
        scan=scan,
    )
