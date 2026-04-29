"""
Prometheus 메트릭을 노출하는 REST API 서버.
RPS / 레이턴시를 선행 지표로 삼아 KEDA로 스케일하기 적합.

감지되는 신호:
  exposes_metrics     = True  (/metrics, prometheus)
  uses_prometheus     = True  (prometheus_client)
  has_request_metric  = True  (http_requests_total, request_duration)
"""
import time

from flask import Flask, jsonify, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)

app = Flask(__name__)

# ── 메트릭 정의 ────────────────────────────────────────────────────────────
http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code"],
)
request_duration = Histogram(
    "request_duration_seconds",
    "HTTP request duration in seconds",
    ["endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)
requests_total = Counter(
    "requests_total",
    "Alias counter for compatibility",
)


def track(endpoint: str, status: int):
    http_requests_total.labels(
        method=request.method,
        endpoint=endpoint,
        status_code=str(status),
    ).inc()
    requests_total.inc()


# ── 엔드포인트 ─────────────────────────────────────────────────────────────
@app.route("/metrics")
def metrics():
    """Prometheus scrape endpoint."""
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/healthz")
def healthz():
    return {"status": "ok"}


@app.route("/api/items", methods=["GET"])
def list_items():
    start = time.perf_counter()
    result = {"items": ["a", "b", "c"], "count": 3}
    request_duration.labels("/api/items").observe(time.perf_counter() - start)
    track("/api/items", 200)
    return jsonify(result)


@app.route("/api/items/<item_id>", methods=["GET"])
def get_item(item_id: str):
    start = time.perf_counter()
    if item_id not in {"a", "b", "c"}:
        track("/api/items/:id", 404)
        return jsonify({"error": "not found"}), 404
    request_duration.labels("/api/items/:id").observe(time.perf_counter() - start)
    track("/api/items/:id", 200)
    return jsonify({"id": item_id})


@app.route("/api/items", methods=["POST"])
def create_item():
    start = time.perf_counter()
    body = request.get_json(silent=True) or {}
    request_duration.labels("/api/items#POST").observe(time.perf_counter() - start)
    track("/api/items#POST", 201)
    return jsonify({"created": body}), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
