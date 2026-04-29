from __future__ import annotations

from .models import AuditItem, ScanResult


def audit(scan: ScanResult) -> list[AuditItem]:
    items: list[AuditItem] = []

    def add(check: str, status: str, detail: str) -> None:
        items.append(AuditItem(check=check, status=status, detail=detail))

    # ── Resource requests ────────────────────────────────────────────────
    if scan.resources.cpu_request:
        add("CPU Request", "ok", scan.resources.cpu_request)
    else:
        add("CPU Request", "error", "없음 — HPA CPU 메트릭이 동작하지 않습니다")

    if scan.resources.memory_request:
        add("Memory Request", "ok", scan.resources.memory_request)
    else:
        add("Memory Request", "warn", "없음 — 메모리 기반 HPA 사용 불가")

    if not scan.resources.cpu_limit:
        add("CPU Limit", "info", "미설정 — CPU throttling 없음 (버스트 허용)")
    else:
        add("CPU Limit", "ok", scan.resources.cpu_limit)

    # ── HPA ─────────────────────────────────────────────────────────────
    if scan.hpa.enabled:
        add("HPA", "ok", f"min={scan.hpa.min_replicas}  max={scan.hpa.max_replicas}")

        if scan.hpa.cpu_target > 75:
            add(
                "CPU Target",
                "warn",
                f"{scan.hpa.cpu_target}% — 높음. 스파이크 트래픽에서 scale-out이 늦게 발동됩니다",
            )
        elif scan.hpa.cpu_target <= 60:
            add("CPU Target", "ok", f"{scan.hpa.cpu_target}% — 충분한 헤드룸")
        else:
            add("CPU Target", "info", f"{scan.hpa.cpu_target}% — 적정 수준")

        if scan.hpa.min_replicas < 2:
            add("Min Replicas", "warn", f"{scan.hpa.min_replicas} — 단일 레플리카로 HA 미보장")
        elif scan.hpa.min_replicas < 3:
            add(
                "Min Replicas",
                "info",
                f"{scan.hpa.min_replicas} — 스파이크 대비 3 이상 권장",
            )
        else:
            add("Min Replicas", "ok", f"{scan.hpa.min_replicas} — 사전 용량 확보됨")

        ratio = scan.hpa.max_replicas / max(scan.hpa.min_replicas, 1)
        if ratio > 5:
            add(
                "Scale Range",
                "warn",
                f"{scan.hpa.min_replicas}→{scan.hpa.max_replicas} (×{ratio:.0f}) — 범위가 너무 넓으면 비용 폭발 위험",
            )
        else:
            add(
                "Scale Range",
                "ok",
                f"{scan.hpa.min_replicas}→{scan.hpa.max_replicas} (×{ratio:.0f})",
            )
    else:
        add("HPA", "error", "비활성화 — 수평 오토스케일링 없음")

    # ── PDB ─────────────────────────────────────────────────────────────
    if scan.pdb.enabled:
        add("PodDisruptionBudget", "ok", f"minAvailable={scan.pdb.min_available}")
    else:
        add("PodDisruptionBudget", "warn", "미설정 — 롤링 업데이트 중 전체 장애 가능")

    # ── Probes ───────────────────────────────────────────────────────────
    if scan.probe.readiness_enabled:
        delay = scan.probe.readiness_initial_delay
        period = scan.probe.readiness_period
        if delay > 10:
            add(
                "Readiness Probe",
                "warn",
                f"initialDelay={delay}s 너무 느림 — 새 Pod이 오래 unready 상태 유지",
            )
        else:
            add("Readiness Probe", "ok", f"delay={delay}s  period={period}s")
    else:
        add("Readiness Probe", "error", "미설정 — 준비되지 않은 Pod에 트래픽 전달됨")

    if scan.probe.liveness_enabled:
        add("Liveness Probe", "ok", "설정됨")
    else:
        add("Liveness Probe", "warn", "미설정 — 데드락 Pod 미감지")

    # ── Startup / graceful shutdown ──────────────────────────────────────
    if scan.app.startup_delay_seconds > 0:
        if scan.app.startup_delay_seconds > 5:
            add(
                "Startup Delay",
                "warn",
                f"{scan.app.startup_delay_seconds}s — 느린 시작은 스파이크 취약성 증가",
            )
        else:
            add("Startup Delay", "ok", f"{scan.app.startup_delay_seconds}s")

    prestop = scan.app.prestop_sleep_seconds
    drain = scan.app.shutdown_drain_seconds
    grace = scan.app.termination_grace_period

    if prestop > 0:
        if prestop + drain >= grace:
            add(
                "Graceful Shutdown",
                "warn",
                f"preStop({prestop}s) + drain({drain}s) ≥ grace({grace}s) — SIGKILL이 drain 완료 전에 발생",
            )
        else:
            add(
                "Graceful Shutdown",
                "ok",
                f"preStop={prestop}s  drain={drain}s  grace={grace}s",
            )
    else:
        add("Graceful Shutdown", "warn", "preStop 없음 — Pod 삭제 시 커넥션 즉시 끊김")

    # ── Observability ───────────────────────────────────────────────────
    if scan.obs.service_monitor_enabled:
        add("ServiceMonitor", "ok", f"{scan.obs.metrics_path} Prometheus 스크래핑 활성")
    else:
        add("ServiceMonitor", "info", "비활성 — Prometheus 메트릭 수집 없음")

    if scan.hpa.keda_enabled:
        add("KEDA", "ok", "활성화됨")

    # ── App source signals (optional) ────────────────────────────────────
    s = scan.signals
    if s.exposes_metrics:
        add("App Metrics", "ok", "/metrics 엔드포인트 감지됨")
    if s.has_queue_integration:
        add("Queue Integration", "info", "큐 연동 감지 (Kafka/RabbitMQ/SQS 등)")
    if s.is_background_worker:
        add("Background Worker", "info", "Consumer/Worker 패턴 감지 — KEDA 고려")

    return items
