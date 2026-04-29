"""
Celery 기반 비동기 작업 처리 워커.
Redis 브로커의 pending_jobs 수로 KEDA 스케일 → CPU HPA보다 훨씬 빠른 반응.

감지되는 신호:
  has_queue_integration = True  (celery)
  has_queue_metric      = True  (pending_jobs, backlog)
  has_request_metric    = True  (requests_total)
  exposes_metrics       = True  (prometheus, /metrics)
  uses_prometheus       = True  (prometheus_client)
  is_background_worker  = True  (task_processor, job_handler)
"""
import logging
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from celery import Celery
from celery.signals import task_postrun, task_prerun
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BROKER_URL  = os.getenv("BROKER_URL", "redis://redis:6379/0")
BACKEND_URL = os.getenv("BACKEND_URL", "redis://redis:6379/1")

app = Celery("worker", broker=BROKER_URL, backend=BACKEND_URL)
app.conf.task_serializer   = "json"
app.conf.result_serializer = "json"
app.conf.accept_content    = ["json"]

# ── Prometheus 메트릭 ────────────────────────────────────────────────────
pending_jobs = Gauge(
    "pending_jobs",
    "Number of tasks currently queued in the broker (backlog)",
)
backlog = Gauge(
    "backlog",
    "Alias: unacked + queued tasks",
)
requests_total = Counter(
    "requests_total",
    "Total tasks successfully completed",
    ["task_name"],
)
task_duration = Histogram(
    "task_duration_seconds",
    "Time spent processing a single task",
    ["task_name"],
)
task_failures = Counter(
    "task_failures_total",
    "Tasks that raised an exception",
    ["task_name", "exception"],
)


@task_prerun.connect
def on_task_start(task_id, task, *args, **kwargs):
    pending_jobs.dec()
    backlog.dec()


@task_postrun.connect
def on_task_done(task_id, task, retval, state, *args, **kwargs):
    if state == "SUCCESS":
        requests_total.labels(task_name=task.name).inc()


# ── 태스크 정의 ───────────────────────────────────────────────────────────
@app.task(bind=True, max_retries=3)
def task_processor(self, payload: dict) -> dict:
    """범용 페이로드 처리 태스크."""
    start = time.perf_counter()
    try:
        task_id   = payload.get("id", "unknown")
        task_type = payload.get("type", "generic")
        logger.info("Processing task %s (type=%s)", task_id, task_type)
        time.sleep(0.1)  # 처리 시뮬레이션
        elapsed = time.perf_counter() - start
        task_duration.labels(task_name="task_processor").observe(elapsed)
        return {"id": task_id, "status": "done", "elapsed_ms": round(elapsed * 1000)}
    except Exception as exc:
        task_failures.labels(task_name="task_processor", exception=type(exc).__name__).inc()
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@app.task
def job_handler(event: dict) -> None:
    """이벤트를 받아 적절한 태스크로 라우팅."""
    event_type = event.get("type")
    if event_type == "process":
        task_processor.delay(event.get("payload", {}))
    else:
        logger.warning("Unknown event type: %s", event_type)


# ── /metrics HTTP 서버 ───────────────────────────────────────────────────
class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            body = generate_latest()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    metrics_server = HTTPServer(("0.0.0.0", 9090), MetricsHandler)
    Thread(target=metrics_server.serve_forever, daemon=True).start()
    logger.info("Metrics server listening on :9090/metrics")
    app.worker_main(["worker", "--loglevel=info", "--concurrency=4"])
