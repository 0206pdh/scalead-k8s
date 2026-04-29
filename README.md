# autoscaling-advisor

K8s에 배포하기 전, **Helm values 파일** 또는 **k8s 매니페스트 디렉토리**를 정적으로 분석해서 오토스케일링 전략을 추천하는 CLI다.

클러스터 접근 없이 로컬에서 실행한다. 실서비스 도입 전 의사결정 후보를 좁히는 게 목적이다.

---

## 설치

Python **3.10 이상**이 필요하다.

### pip

```bash
pip install autoscaling-advisor
```

### pipx (CLI 도구 권장)

```bash
pipx install autoscaling-advisor
```

`pipx`가 없으면:

```bash
pip install pipx
pipx ensurepath   # PATH 자동 등록, 이후 터미널 재시작
```

### 설치 확인

```bash
scalead --help
```

```
Usage: scalead [OPTIONS] TARGET

  K8s 오토스케일링 정책 어드바이저

  TARGET: Helm values 파일(.yaml) 또는 k8s 매니페스트 디렉토리

Options:
  -s, --source DIR          앱 소스 디렉토리 (선택)
  -f, --format [rich|json]  출력 형식 (기본: rich)
  -h, --help                Show this message and exit.
```

### Windows에서 `scalead`를 못 찾는 경우

**pipx 사용 시** — `pipx ensurepath` 실행 후 터미널 재시작.

**pip 사용 시** — Scripts 경로 확인 후 PATH 추가.

```powershell
python -m site --user-base
# 출력 예: C:\Users\사용자명\AppData\Roaming\Python\Python311
# → 이 경로\Scripts 를 PATH에 추가
```

**어느 방법도 안 될 때** — 모듈 직접 실행.

```bash
python -m autoscaling_advisor.cli values.yaml
```

### 개발자 셋업

```bash
git clone https://github.com/0206pdh/scalead-k8s.git
cd scalead-k8s

python -m venv .venv
source .venv/bin/activate        # macOS/Linux
.venv\Scripts\Activate.ps1       # Windows PowerShell

pip install -e .
scalead --help
```

---

## 빠른 시작

```bash
# Helm values 파일 분석
scalead values.yaml

# k8s 매니페스트 디렉토리 분석
scalead k8s/manifests/

# 앱 소스 코드도 함께 분석 (메트릭/큐 감지 정확도 향상)
scalead values.yaml --source ./app

# JSON 출력 (파이프라인 연동용)
scalead values.yaml --format json
```

---

## 출력 구조

실행하면 세 섹션이 순서대로 출력된다.

### 1. Config Audit

현재 설정에서 발견한 문제와 상태를 항목별로 나열한다.

```
                              Config Audit
┌────────────────────────┬─────┬───────────────────────────────────────┐
│ 항목                   │     │ 내용                                  │
├────────────────────────┼─────┼───────────────────────────────────────┤
│ CPU Request            │  ✓  │ 200m                                  │
│ Memory Request         │  ✓  │ 256Mi                                 │
│ HPA                    │  ✓  │ min=2  max=6                          │
│ CPU Target             │  ℹ  │ 70% — 적정 수준                       │
│ Min Replicas           │  ℹ  │ 2 — 스파이크 대비 3 이상 권장         │
│ PodDisruptionBudget    │  ✓  │ minAvailable=1                        │
│ Readiness Probe        │  ✓  │ delay=3s  period=5s                   │
│ Startup Delay          │  ⚠  │ 8s — 느린 시작은 스파이크 취약성 증가 │
│ Graceful Shutdown      │  ✓  │ preStop=10s  drain=12s  grace=30s     │
└────────────────────────┴─────┴───────────────────────────────────────┘
```

| 아이콘 | 의미 |
|--------|------|
| `✓` | 정상 |
| `⚠` | 경고 — 개선 여지 있음 |
| `✗` | 오류 — 오토스케일링이 동작하지 않을 수 있음 |
| `ℹ` | 정보 — 참고 사항 |

### 2. 추천 전략

가장 높은 점수의 전략과 추천 이유, 권장 변경사항을 보여준다.

```
┌───────────────────────────────── 추천 전략 ─────────────────────────────────┐
│  Tuned HPA  score 89/100                                                    │
│                                                                             │
│    • 시작 지연 8s — 튜닝 여지 큼                                            │
│    • minReplicas=2 — 사전 용량 확보 가능                                    │
│    • CPU target 70% — 낮추면 더 일찍 scale-out                              │
└─────────────────────────────────────────────────────────────────────────────┘
권장 변경사항
  • app.startupDelaySeconds  8 → 3  # 빠른 시작으로 scale-out 효율 향상
  • hpa.minReplicas  2 → 3          # 스파이크 전 헤드룸 확보
  • hpa.targetCPUUtilizationPercentage  70 → 60  # scale-out 조기 발동
```

### 3. 전략 비교

```
전략 비교
  ★ Tuned HPA               89   █████████░
    Basic HPA               65   ██████░░░░
    KEDA + Prometheus       15   ██░░░░░░░░
```

---

## 입력 형식

### Helm values 파일

읽는 키:

| values 키 | 설명 |
|-----------|------|
| `hpa.enabled` | HPA 활성화 여부 |
| `hpa.minReplicas` | 최소 레플리카 수 |
| `hpa.maxReplicas` | 최대 레플리카 수 |
| `hpa.targetCPUUtilizationPercentage` | CPU 스케일링 임계값 |
| `resources.requests.cpu` | CPU request — HPA 동작에 필수 |
| `resources.requests.memory` | Memory request |
| `resources.limits.cpu` | CPU limit |
| `deployment.readinessProbe` | Readiness probe 설정 |
| `deployment.livenessProbe` | Liveness probe 설정 |
| `deployment.preStopSleepSeconds` | Graceful shutdown preStop sleep |
| `deployment.terminationGracePeriodSeconds` | 강제 종료 대기 시간 |
| `app.startupDelaySeconds` | 앱 시작 지연 |
| `app.shutdownDrainSeconds` | 커넥션 drain 대기 |
| `pdb.enabled` | PodDisruptionBudget 활성화 |
| `pdb.minAvailable` | 최소 가용 파드 수 |
| `serviceMonitor.enabled` | Prometheus ServiceMonitor 활성화 |
| `keda.enabled` | KEDA 활성화 여부 |

> **주의:** 환경별 override 파일은 base values를 상속하지 않는다. 단독 분석 시 누락 필드는 기본값으로 처리된다.

### k8s 매니페스트 디렉토리

`Deployment`, `HorizontalPodAutoscaler`, `PodDisruptionBudget`, `ServiceMonitor` YAML 파일을 자동으로 탐색한다.

### 앱 소스 (`--source`)

소스 코드를 정적 분석해서 메트릭 노출 여부, 큐 연동, 워크로드 특성을 감지한다.

지원 확장자: `.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.go`, `.java`, `.kt`, `.rb`

| 감지 항목 | 판단 키워드 |
|-----------|-------------|
| Prometheus 메트릭 노출 | `/metrics`, `prometheus` |
| Prometheus 클라이언트 | `prometheus_client`, `prom-client` |
| Request 메트릭 | `http_requests_total`, `request_count` |
| Queue depth 메트릭 | `queue_depth`, `queue_length`, `backlog` |
| 큐 연동 | `kafka`, `rabbitmq`, `sqs`, `celery`, `bullmq` |
| Background worker | `consumer`, `worker.run`, `job_handler` |
| CPU-heavy 경로 | `hashlib`, `pbkdf2`, `bcrypt`, `numpy`, `torch` |

---

## 추천 전략

### Basic HPA

CPU utilization 기반 기본 HPA. 설정이 단순하고 steady 트래픽에 적합하다.

**적합한 상황:** CPU-heavy 워크로드, 예측 가능한 트래픽, 비용 민감도 높음

**한계:** CPU 사용률은 트래픽이 몰린 이후에야 올라간다. 스파이크가 짧고 급격하면 scale-out 전에 이미 지연이 발생한다.

---

### Tuned HPA

Basic HPA와 동일하게 CPU 기반이지만, 파라미터를 조정해서 반응 속도를 높인다.

- `minReplicas` ↑ — 스파이크 전 사전 용량 확보
- `targetCPUUtilizationPercentage` ↓ — 더 일찍 scale-out 발동
- `readinessProbe.periodSeconds` ↓ — 새 파드 워밍업 단축
- `startupDelaySeconds` ↓ — 파드 준비 시간 단축

**적합한 상황:** 스파이크/버스트 트래픽, 튜닝 여지가 있는 경우

**한계:** maxReplicas와 파드 시작 시간에 묶인다. 선행 지표가 있다면 KEDA가 더 효과적이다.

---

### KEDA + Prometheus

CPU 사용률보다 더 빠른 신호(RPS, 큐 깊이, 동시접속)로 스케일링한다.

**적합한 상황:**
- Kafka consumer — lag 기반 스케일링
- API 서버 — RPS, 동시 접속 수 기반
- 배치 워커 — 큐 깊이가 0이 되면 0으로 scale-down

**준비 요건:**
1. 클러스터에 KEDA operator 설치
2. 앱이 `/metrics`를 통해 Prometheus 메트릭 노출
3. `ScaledObject` 매니페스트 작성 (이 도구 범위 밖)

---

## Audit 항목 상세

### CPU Request

HPA CPU utilization 메트릭은 `resources.requests.cpu`를 분모로 계산한다. 미설정 시 HPA가 CPU 메트릭을 수집하지 못한다.

### CPU Target

`targetCPUUtilizationPercentage` > 75% 이면 경고. 스파이크 트래픽에는 60% 이하를 권장한다.

### Readiness Probe

미설정 시 준비되지 않은 파드에 트래픽이 전달된다. `initialDelaySeconds` > 10s 이면 새 파드 워밍업이 느려진다.

### Graceful Shutdown

`preStop` 없으면 파드 삭제 시 커넥션이 즉시 끊긴다. `preStop + drain < grace` 조건을 만족해야 drain이 완료된다.

```yaml
deployment:
  preStopSleepSeconds: 10           # 라우팅 테이블 갱신 대기
  terminationGracePeriodSeconds: 30 # preStop + drain 보다 반드시 커야 함
app:
  shutdownDrainSeconds: 12
```

### PodDisruptionBudget

미설정 시 롤링 업데이트 중 전체 파드가 동시에 내려갈 수 있다.

---

## 모듈 구조

```
autoscaling_advisor/
├── cli.py        엔트리포인트 (click)
├── models.py     데이터 구조 (dataclass)
├── scanner.py    Helm values / k8s 매니페스트 파싱, 소스 정적 분석
├── auditor.py    설정 감사 체크리스트
├── engine.py     전략별 점수 계산 및 변경 제안
└── renderer.py   rich 기반 터미널 출력
```

---

## 한계

- **정적 분석만 수행한다.** 런타임 메트릭, 실제 트래픽 패턴, 클러스터 상태를 보지 않는다.
- **Helm values 병합을 지원하지 않는다.** 환경별 override 파일 단독 분석 시 누락 필드가 생긴다.
- **KEDA ScaledObject를 생성하지 않는다.** KEDA 전략 추천 시 `ScaledObject` 작성은 별도 작업이다.
- **점수는 휴리스틱이다.** 실서비스 도입 전에는 부하 테스트와 병행해야 한다.

---

## 릴리즈

`v*` 태그를 push하면 GitHub Actions가 자동으로 PyPI에 배포한다.

### 최초 1회 — PyPI Trusted Publisher 설정

1. [pypi.org](https://pypi.org) 로그인
2. **Account settings → Publishing → Add a new pending publisher**
3. 입력:

| 항목 | 값 |
|------|----|
| PyPI Project Name | `autoscaling-advisor` |
| Owner | `0206pdh` |
| Repository name | `scalead-k8s` |
| Workflow filename | `release.yml` |
| Environment name | `pypi` |

4. GitHub **Settings → Environments → New environment** → 이름 `pypi` 로 생성

### 버전 올리기

1. `pyproject.toml` 버전 수정

```toml
version = "0.2.0"
```

2. 커밋 + 태그 push

```bash
git add pyproject.toml
git commit -m "release: v0.2.0"
git tag v0.2.0
git push origin main v0.2.0
```

워크플로우 완료 후 자동으로 만들어지는 것:
- PyPI 패키지 (`pip install autoscaling-advisor==0.2.0`)
- GitHub Release + wheel/sdist 첨부

### 로컬 빌드 테스트

```bash
pip install build
python -m build
pip install dist/autoscaling_advisor-0.2.0-py3-none-any.whl
scalead --help
```
