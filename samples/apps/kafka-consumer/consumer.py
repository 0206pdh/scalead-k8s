"""
Kafka 토픽을 소비하는 주문 처리 워커.
큐 깊이(lag)가 CPU보다 훨씬 좋은 선행 지표 → KEDA ScaledObject 권장.

감지되는 신호:
  has_queue_integration = True  (kafka)
  has_queue_metric      = True  (queue_depth, lag)
  has_request_metric    = True  (requests_total)
  exposes_metrics       = True  (prometheus, /metrics)
  uses_prometheus       = True  (prometheus_client)
  is_background_worker  = True  (consumer, task_processor)
"""
import json
import logging
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from kafka import KafkaConsumer
from kafka.errors import KafkaError
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    generate_latest,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Prometheus 메트릭 ────────────────────────────────────────────────────
queue_depth = Gauge(
    "queue_depth",
    "Estimated number of unprocessed messages in the Kafka topic",
)
lag = Gauge(
    "lag",
    "Consumer group lag (messages behind the latest offset)",
    ["topic", "partition"],
)
requests_total = Counter(
    "requests_total",
    "Total messages successfully processed",
    ["topic"],
)
processing_errors = Counter(
    "processing_errors_total",
    "Messages that failed processing",
    ["topic", "reason"],
)

KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "kafka:9092")
KAFKA_TOPIC   = os.getenv("KAFKA_TOPIC", "orders")
KAFKA_GROUP   = os.getenv("KAFKA_GROUP", "order-processor")


# ── 메시지 처리 ──────────────────────────────────────────────────────────
def task_processor(message) -> dict:
    """개별 메시지 파싱 및 처리."""
    payload = json.loads(message.value)
    order_id = payload.get("order_id")
    logger.info("Processing order %s", order_id)
    time.sleep(0.05)  # 처리 시뮬레이션
    return {"order_id": order_id, "status": "processed"}


# ── 메인 루프 ────────────────────────────────────────────────────────────
def worker_run():
    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BROKERS.split(","),
        group_id=KAFKA_GROUP,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda b: b,
    )
    logger.info("Consumer started: topic=%s group=%s", KAFKA_TOPIC, KAFKA_GROUP)

    for message in consumer:
        queue_depth.dec()
        lag.labels(topic=message.topic, partition=str(message.partition)).set(
            message.offset
        )
        try:
            task_processor(message)
            requests_total.labels(topic=message.topic).inc()
            consumer.commit()
        except (json.JSONDecodeError, KeyError) as exc:
            processing_errors.labels(topic=message.topic, reason=type(exc).__name__).inc()
            logger.warning("Failed to process message: %s", exc)


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
    worker_run()
