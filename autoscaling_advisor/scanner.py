from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from .models import (
    AppConfig,
    AppSignals,
    HPAConfig,
    ObsConfig,
    PDBConfig,
    ProbeConfig,
    ResourceConfig,
    ScanResult,
)

_TEXT_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java", ".kt", ".rb"}
_SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", "dist", "build"}


def scan_helm_values(path: str) -> ScanResult:
    with open(path, encoding="utf-8") as f:
        v = yaml.safe_load(f) or {}

    result = ScanResult(source=path)

    hpa_v = v.get("hpa", {})
    result.hpa = HPAConfig(
        enabled=bool(hpa_v.get("enabled", False)),
        min_replicas=int(hpa_v.get("minReplicas", 0)),
        max_replicas=int(hpa_v.get("maxReplicas", 0)),
        cpu_target=int(hpa_v.get("targetCPUUtilizationPercentage", 0)),
        keda_enabled=bool(v.get("keda", {}).get("enabled", False)),
    )

    res_v = v.get("resources", {})
    req = res_v.get("requests", {})
    lim = res_v.get("limits", {})
    result.resources = ResourceConfig(
        cpu_request=str(req.get("cpu", "")),
        memory_request=str(req.get("memory", "")),
        cpu_limit=str(lim.get("cpu", "")),
        memory_limit=str(lim.get("memory", "")),
    )

    dep_v = v.get("deployment", {})
    rp = dep_v.get("readinessProbe", {})
    lp = dep_v.get("livenessProbe", {})
    result.probe = ProbeConfig(
        readiness_enabled=bool(rp),
        readiness_initial_delay=int(rp.get("initialDelaySeconds", 0)),
        readiness_period=int(rp.get("periodSeconds", 10)),
        liveness_enabled=bool(lp),
    )

    app_v = v.get("app", {})
    result.app = AppConfig(
        startup_delay_seconds=int(app_v.get("startupDelaySeconds", 0)),
        shutdown_drain_seconds=int(app_v.get("shutdownDrainSeconds", 0)),
        prestop_sleep_seconds=int(dep_v.get("preStopSleepSeconds", 0)),
        termination_grace_period=int(dep_v.get("terminationGracePeriodSeconds", 30)),
    )

    pdb_v = v.get("pdb", {})
    result.pdb = PDBConfig(
        enabled=bool(pdb_v.get("enabled", False)),
        min_available=pdb_v.get("minAvailable"),
    )

    sm_v = v.get("serviceMonitor", {})
    result.obs = ObsConfig(
        service_monitor_enabled=bool(sm_v.get("enabled", False)),
        metrics_path=str(sm_v.get("path", "/metrics")),
    )

    result.replicas = int(v.get("replicaCount", 1))
    return result


def scan_k8s_dir(path: str) -> ScanResult:
    result = ScanResult(source=path)

    for yaml_file in Path(path).glob("*.yaml"):
        try:
            with open(yaml_file, encoding="utf-8") as f:
                docs = list(yaml.safe_load_all(f))
        except Exception:
            continue

        for doc in docs:
            if not doc or not isinstance(doc, dict):
                continue
            _parse_k8s_doc(doc, result)

    return result


def _parse_k8s_doc(doc: dict, result: ScanResult) -> None:
    kind = doc.get("kind", "")

    if kind == "HorizontalPodAutoscaler":
        spec = doc.get("spec", {})
        cpu_target = 0
        for m in spec.get("metrics", []):
            if m.get("type") == "Resource":
                res = m.get("resource", {})
                if res.get("name") == "cpu":
                    cpu_target = res.get("target", {}).get("averageUtilization", 0)
        result.hpa = HPAConfig(
            enabled=True,
            min_replicas=int(spec.get("minReplicas", 0)),
            max_replicas=int(spec.get("maxReplicas", 0)),
            cpu_target=int(cpu_target),
        )

    elif kind == "Deployment":
        spec = doc.get("spec", {})
        result.replicas = int(spec.get("replicas", 1))
        pod_spec = spec.get("template", {}).get("spec", {})
        containers = pod_spec.get("containers", [])
        if containers:
            c = containers[0]
            _parse_container(c, result)
        result.app.termination_grace_period = int(pod_spec.get("terminationGracePeriodSeconds", 30))

    elif kind == "PodDisruptionBudget":
        spec = doc.get("spec", {})
        result.pdb = PDBConfig(
            enabled=True,
            min_available=spec.get("minAvailable"),
        )

    elif kind == "ServiceMonitor":
        endpoints = doc.get("spec", {}).get("endpoints", [{}])
        result.obs = ObsConfig(
            service_monitor_enabled=True,
            metrics_path=endpoints[0].get("path", "/metrics") if endpoints else "/metrics",
        )


def _parse_container(c: dict, result: ScanResult) -> None:
    res = c.get("resources", {})
    req = res.get("requests", {})
    lim = res.get("limits", {})
    result.resources = ResourceConfig(
        cpu_request=str(req.get("cpu", "")),
        memory_request=str(req.get("memory", "")),
        cpu_limit=str(lim.get("cpu", "")),
        memory_limit=str(lim.get("memory", "")),
    )

    rp = c.get("readinessProbe", {})
    lp = c.get("livenessProbe", {})
    result.probe = ProbeConfig(
        readiness_enabled=bool(rp),
        readiness_initial_delay=int(rp.get("initialDelaySeconds", 0)),
        readiness_period=int(rp.get("periodSeconds", 10)),
        liveness_enabled=bool(lp),
    )

    env = {e["name"]: str(e.get("value", "")) for e in c.get("env", []) if "name" in e}
    result.app.startup_delay_seconds = int(env.get("APP_STARTUP_DELAY_SECONDS", 0) or 0)
    result.app.shutdown_drain_seconds = int(env.get("APP_SHUTDOWN_DRAIN_SECONDS", 0) or 0)

    lifecycle = c.get("lifecycle", {})
    prestop_cmd = " ".join(lifecycle.get("preStop", {}).get("exec", {}).get("command", []))
    m = re.search(r"sleep\s+(\d+)", prestop_cmd)
    if m:
        result.app.prestop_sleep_seconds = int(m.group(1))


def enrich_with_source(app_dir: str, result: ScanResult) -> None:
    """Static-analyze app source code and populate result.signals."""
    content_parts: list[str] = []
    for root, dirs, files in os.walk(app_dir):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fname in files:
            if Path(fname).suffix in _TEXT_SUFFIXES:
                try:
                    content_parts.append(Path(root, fname).read_text(errors="ignore"))
                except Exception:
                    pass

    text = "\n".join(content_parts).lower()

    result.signals = AppSignals(
        exposes_metrics="/metrics" in text or "prometheus" in text,
        uses_prometheus=any(k in text for k in ["prometheus_client", "prom-client", "promclient"]),
        has_request_metric=any(k in text for k in [
            "http_requests_total", "request_count", "request_duration", "requests_total",
        ]),
        has_queue_metric=any(k in text for k in [
            "queue_depth", "queue_length", "backlog", "pending_jobs", "lag",
        ]),
        has_queue_integration=any(k in text for k in [
            "kafka", "rabbitmq", "sqs", "pubsub", "celery", "bullmq", "sidekiq",
        ]),
        is_background_worker=any(k in text for k in [
            "consumer", "worker.run", "job_handler", "task_processor",
        ]),
        is_cpu_heavy=any(k in text for k in [
            "cpu_heavy", "hashlib", "pbkdf2", "bcrypt", "numpy", "torch",
        ]),
    )
