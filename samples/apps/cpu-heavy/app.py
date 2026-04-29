"""
암호화·해시 연산 중심 API 서버.
CPU 사용률이 요청 수에 비례해 올라가므로 CPU HPA가 자연스러운 선택.

감지되는 신호:
  is_cpu_heavy = True  (hashlib, pbkdf2, bcrypt)
"""
import hashlib
import time

import bcrypt
from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route("/healthz")
def healthz():
    return {"status": "ok"}


@app.route("/hash/bcrypt", methods=["POST"])
def hash_bcrypt():
    """bcrypt는 CPU를 의도적으로 많이 쓰는 단방향 해시."""
    password = request.json["password"].encode()
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password, salt)
    return jsonify({"hash": hashed.decode()})


@app.route("/hash/sha256", methods=["POST"])
def hash_sha256():
    data = request.json["data"].encode()
    digest = hashlib.sha256(data).hexdigest()
    return jsonify({"sha256": digest})


@app.route("/hash/pbkdf2", methods=["POST"])
def hash_pbkdf2():
    """pbkdf2_hmac: iterations 수만큼 CPU 연산 반복."""
    password = request.json["password"].encode()
    salt = request.json.get("salt", "static-salt").encode()
    iterations = int(request.json.get("iterations", 200_000))
    dk = hashlib.pbkdf2_hmac("sha256", password, salt, iterations)
    return jsonify({"key": dk.hex(), "iterations": iterations})


@app.route("/verify/bcrypt", methods=["POST"])
def verify_bcrypt():
    password = request.json["password"].encode()
    hashed = request.json["hash"].encode()
    ok = bcrypt.checkpw(password, hashed)
    return jsonify({"valid": ok})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
