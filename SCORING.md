# scalead 추천 기준 상세 설명

scalead는 Helm values 또는 K8s 매니페스트를 정적 분석해 **세 가지 전략 중 하나를 추천**한다.  
이 문서는 각 전략의 점수 계산 방식과, 각 임계값을 그 수치로 설정한 이유를 설명한다.

---

## 목차

1. [전략 개요](#1-전략-개요)
2. [점수 체계 구조](#2-점수-체계-구조)
3. [Basic HPA 채점 기준](#3-basic-hpa-채점-기준)
4. [Tuned HPA 채점 기준](#4-tuned-hpa-채점-기준)
5. [KEDA + Prometheus 채점 기준](#5-keda--prometheus-채점-기준)
6. [감사(Audit) 항목 기준](#6-감사audit-항목-기준)
7. [전략 선택 흐름 요약](#7-전략-선택-흐름-요약)

---

## 점수는 "취약성 탐지"이지 "트래픽 예측"이 아니다

이 도구는 YAML 설정만 보고 점수를 매긴다. **실제 트래픽 데이터는 전혀 보지 않는다.**

Tuned HPA가 높은 점수를 받고 "minReplicas를 3으로 올리세요", "CPU target을 60%로 낮추세요"라고 제안할 때, 이것은 두 가지 의미 중 하나가 **아니다:**

- ~~스파이크 트래픽이 올 것이다~~
- ~~지금 설정이 반드시 문제를 일으킨다~~

실제 의미는 이것이다:

> **"현재 설정은 스파이크가 왔을 때 대응이 느린 구조다. 스파이크가 실제로 오는지는 메트릭을 봐야 한다."**

### 도구가 알 수 있는 것 vs 없는 것

| | 도구가 아는 것 | 도구가 모르는 것 |
|---|---|---|
| 설정 | minReplicas, CPU target, probe 주기 | 이 설정이 실제로 문제를 일으킨 적 있는지 |
| 앱 특성 | 소스코드의 키워드 (kafka, prometheus...) | 실제 초당 요청 수, CPU 사용률 분포 |
| 리스크 구조 | preStop+drain ≥ grace 이면 위험한 구조 | 실제로 커넥션이 끊긴 적 있는지 |
| 스케일링 | CPU target 80%는 헤드룸이 적은 구조 | 실제 p95 CPU가 얼마인지 |

### 추천을 적용하기 전에 확인해야 할 메트릭

```
# CPU target 조정 전 — 실제 CPU 사용률 분포 확인
histogram_quantile(0.95, rate(container_cpu_usage_seconds_total[5m]))

# minReplicas 조정 전 — HPA scale-out 이벤트 빈도 확인
kube_horizontalpodautoscaler_status_desired_replicas

# startupDelay 단축 전 — Pod Ready 소요 시간 실측
kube_pod_status_ready 의 타임스탬프 vs pod 생성 시각 차이
```

**메트릭 기반 판단 예시:**

| 관측값 | 판단 |
|---|---|
| CPU p95 = 35%, 항상 steady | target 낮출 이유 없음, Tuned HPA 제안 무시해도 됨 |
| CPU p95 = 78%, 점심마다 스파이크 | target 60~65%로 낮추는 게 실질적 효과 있음 |
| HPA scale-out이 월 1회 미만 | minReplicas 올리면 비용만 증가 |
| HPA scale-out이 매일 발생, Pod Ready 40초 | startupDelay 단축 + minReplicas 증가 모두 효과적 |

---

## 1. 전략 개요

| 전략 | 한 줄 요약 | 적합한 상황 |
|---|---|---|
| **Basic HPA** | CPU 사용률 기반 수평 스케일링 | 단순 웹/API 서버, 이미 안정적으로 설정된 서비스 |
| **Tuned HPA** | Basic HPA이지만 설정 개선 여지가 큰 서비스 | HPA는 켜져 있지만 임계값·probe·startup이 느슨한 경우 |
| **KEDA + Prometheus** | 외부 메트릭(큐 깊이, RPS 등) 기반 스케일링 | Kafka consumer, 메트릭 엔드포인트 노출 서비스, Background worker |

> **왜 세 가지인가?**  
> CPU 기반 HPA는 진입 장벽이 낮지만 "반응형"이다 — 이미 CPU가 올라간 뒤에야 스케일한다.  
> Tuned HPA는 설정을 조여 반응 속도를 높이는 중간 단계다.  
> KEDA는 "선행 지표(leading indicator)"로 스케일할 수 있어, CPU가 오르기 전에 미리 Pod를 늘릴 수 있다.

---

## 2. 점수 체계 구조

각 전략은 **기본 점수(base score)** 에서 시작해 설정 항목에 따라 가감산된다.  
최종 점수는 `0~100`으로 클램핑되며, 세 전략 중 **가장 높은 점수의 전략이 추천**된다.

```
최종 점수 = clamp(base + Σ가산 - Σ감산, 0, 100)
```

점수는 "이 전략이 현재 설정에 얼마나 잘 맞는가"를 나타낸다.  
Tuned HPA는 **개선 여지가 클수록 점수가 높아지는** 구조여서, 느슨한 설정일수록 Tuned HPA가 선택된다.

---

## 3. Basic HPA 채점 기준

**기본 점수: 50**

### 3-1. CPU Request 존재 여부 (+10 / -20)

| 조건 | 점수 변화 |
|---|---|
| CPU request 설정됨 | +10 |
| CPU request 없음 | -20 |

**이유:**  
Kubernetes HPA의 CPU 메트릭은 `실제 CPU 사용량 / CPU request`로 계산된다.  
CPU request가 없으면 분모가 없어 HPA가 스케일 판단 자체를 할 수 없다.  
이 경우 HPA를 켜 놔도 동작하지 않으므로 감점 폭이 크다.

### 3-2. CPU-heavy 워크로드 신호 (+15)

| 조건 | 점수 변화 |
|---|---|
| 소스코드에서 CPU-heavy 패턴 감지 (`hashlib`, `bcrypt`, `numpy`, `torch` 등) | +15 |

**이유:**  
CPU 집약적 연산(암호화, ML 추론, 수치 계산)은 트래픽이 늘면 CPU 사용률이 거의 선형으로 증가한다.  
따라서 CPU를 선행 지표로 쓰는 Basic HPA가 자연스럽게 맞아떨어진다.

### 3-3. CPU 목표치 ≤ 70% (+10)

| 조건 | 점수 변화 |
|---|---|
| `targetCPUUtilizationPercentage` ≤ 70 | +10 |

**이유:**  
HPA가 스케일아웃을 결정해서 새 Pod가 Ready 상태가 되기까지 보통 **30~90초**가 걸린다  
(이미지 풀 + 컨테이너 기동 + readinessProbe 통과).  
그 시간 동안 기존 Pod들이 트래픽을 처리해야 하므로 **여유 용량(headroom)** 이 필요하다.

70%에서 스케일아웃을 시작하면 30%의 버퍼가 생긴다.  
80~90%에서 시작하면 새 Pod가 뜨기 전에 이미 CPU가 포화될 수 있다.

### 3-4. minReplicas ≥ 2 (+5)

| 조건 | 점수 변화 |
|---|---|
| `minReplicas` ≥ 2 | +5 |

**이유:**  
Pod가 1개면 그 Pod가 죽는 순간 서비스가 완전히 중단된다.  
2개 이상이면 한 Pod가 내려가도 나머지 Pod가 트래픽을 이어받을 수 있다.  
이는 HA(고가용성)의 최소 조건이다.

### 3-5. 시작 지연 > 5초 (-10)

| 조건 | 점수 변화 |
|---|---|
| `app.startupDelaySeconds` > 5 | -10 |

**이유:**  
스케일아웃 요청 → 새 Pod Ready 사이에 startupDelay만큼 시간이 추가된다.  
시작이 느리면 스파이크 트래픽에 대한 실질적인 반응 속도가 떨어지고,  
그 시간 동안 기존 Pod들이 과부하를 더 오래 받는다.  
5초는 빠른 웹 서버 기준으로, 이를 초과하면 "느린 시작"으로 분류한다.

### 3-6. ServiceMonitor / 메트릭 노출 감지 (-5)

| 조건 | 점수 변화 |
|---|---|
| ServiceMonitor 활성화 또는 소스코드에서 `/metrics` 노출 감지 | -5 |

**이유:**  
Prometheus 메트릭이 있으면 CPU보다 정밀한 지표(RPS, 큐 깊이 등)로 스케일할 수 있다.  
이 경우 Basic HPA보다 KEDA가 더 나은 선택이므로 Basic HPA 점수를 소폭 낮춘다.

---

## 4. Tuned HPA 채점 기준

**기본 점수: 55**

Tuned HPA의 핵심 철학: **"고칠 수 있는 것이 많을수록 이 전략의 가치가 크다."**  
각 항목은 "지금 설정이 최적이 아님 → 개선하면 효과가 크다"는 신호를 감지할 때 점수를 올린다.

### 4-1. HPA 미활성화 (-40)

**이유:** Tuned HPA는 HPA 자체가 있어야 의미가 있다. 없으면 큰 감점.

### 4-2. CPU Request 없음 (-15)

**이유:** Basic HPA와 동일. HPA가 CPU 메트릭을 읽을 수 없다.

### 4-3. 시작 지연 > 5초 (+12, 개선 Change 제안)

| 조건 | 점수 변화 | 제안 |
|---|---|---|
| `app.startupDelaySeconds` > 5 | +12 | startupDelaySeconds를 3으로 줄이도록 제안 |

**이유:**  
시작이 느리다는 것은 **"튜닝해서 빠르게 만들 수 있다"** 는 의미다.  
3초는 일반적인 JVM/Node.js 앱이 달성 가능한 목표값으로,  
lazy initialization, connection pool 사전 워밍 등으로 접근할 수 있다.

### 4-4. minReplicas < 3 (+12, 개선 Change 제안)

| 조건 | 점수 변화 | 제안 |
|---|---|---|
| `minReplicas` < 3 | +12 | `min(현재값+1, 3)` 이상으로 올리도록 제안 |

**이유:**  
minReplicas=2일 때 **롤링 업데이트 중** 문제가 생길 수 있다.  
Kubernetes 기본 롤링 업데이트(maxUnavailable=1)는 Pod를 하나씩 교체하는데,  
2개 중 1개가 교체 중이면 1개만 트래픽을 처리하게 된다.  
minReplicas=3이면 교체 중에도 2개가 살아 있어 더 안전하다.  
또한 갑작스러운 트래픽 스파이크를 "사전 용량"으로 흡수할 수 있다.

### 4-5. CPU 목표치 > 65% (+10, 개선 Change 제안)

| 조건 | 점수 변화 | 제안 |
|---|---|---|
| `targetCPUUtilizationPercentage` > 65 | +10 | 60%로 낮추도록 제안 |

**이유:**  
65%는 70%보다 더 이른 스케일아웃을 유도하는 임계값이다.  
Tuned HPA는 "조금 더 공격적으로 미리 스케일"하는 것을 목표로 하므로,  
70%보다 낮은 65%를 기준으로 "개선 여지 있음"을 판단한다.  
제안값 60%는 여유 헤드룸을 40%까지 확보해 스파이크 대응력을 높인다.

### 4-6. Readiness probe period > 5초 (+8, 개선 Change 제안)

| 조건 | 점수 변화 | 제안 |
|---|---|---|
| `readinessProbe.periodSeconds` > 5 | +8 | 3초로 줄이도록 제안 |

**이유:**  
새 Pod가 뜬 뒤 실제로 Ready 상태가 되기까지 `periodSeconds`만큼의 추가 대기가 발생한다.  
period=10이면 새 Pod가 실제로 준비됐어도 최대 10초 더 기다려야 트래픽을 받는다.  
period=3이면 이 레이턴시를 3분의 1로 줄여 스케일아웃 효과가 더 빨리 나타난다.

### 4-7. Readiness initialDelay > 5초 (개선 Change 제안만)

| 조건 | 점수 변화 | 제안 |
|---|---|---|
| `readinessProbe.initialDelaySeconds` > 5 | 점수 변화 없음 | 2초로 줄이도록 제안 |

**이유:**  
initialDelay는 앱이 뜨자마자 probe가 실행되어 false positive 실패가 나는 것을 방지한다.  
그러나 너무 크면 Pod가 실제로 준비됐음에도 오래 unready 상태로 있는다.  
점수에는 반영하지 않고 Change 제안만 하는 이유는,  
이 값은 앱마다 다르며 낮추는 게 항상 안전하지 않기 때문이다.

### 4-8. PDB 없음 (-5)

| 조건 | 점수 변화 |
|---|---|
| `pdb.enabled` = false | -5 |

**이유:**  
PDB(PodDisruptionBudget)가 없으면 노드 유지보수(drain) 시 모든 Pod가 동시에 내려갈 수 있다.  
롤링 업데이트와 오토스케일링이 함께 작동하는 환경에서는 PDB가 필수 안전망이다.

---

## 5. KEDA + Prometheus 채점 기준

**기본 점수: 35**

KEDA는 CPU 이외의 외부 메트릭으로 스케일하므로, **메트릭/큐 신호가 없으면 쓸 이유가 없다.**  
따라서 기본 점수가 낮고, 신호를 감지할수록 급격히 올라간다.

### 신호별 가산점

| 신호 | 감지 방법 | 점수 |
|---|---|---|
| 큐 연동 (Kafka, RabbitMQ, SQS 등) | 소스코드 키워드 분석 | +30 |
| Prometheus 메트릭 노출 | `/metrics` 또는 `prometheus` 키워드 | +20 |
| 요청 메트릭 (`http_requests_total` 등) | 소스코드 키워드 분석 | +15 |
| 큐 깊이 메트릭 (`queue_depth` 등) | 소스코드 키워드 분석 | +20 |
| Background worker 패턴 | `consumer`, `worker.run` 등 | +25 |
| ServiceMonitor 활성화 | YAML 설정 | +10 |
| KEDA 이미 차트에 활성화 | YAML 설정 | +10 |

### 메트릭/큐 신호 없음 (-20)

**이유:**  
KEDA는 트리거 소스 없이는 동작할 수 없다.  
신호가 없다는 것은 "KEDA를 써도 기존 HPA보다 나을 게 없다"는 뜻이므로 큰 감점을 준다.

### 왜 큐 연동이 +30으로 가장 크나?

큐 기반 워크로드는 **큐 깊이(queue depth)** 가 처리 속도보다 빠르게 쌓이는 패턴이다.  
CPU는 이미 과부하가 걸린 뒤에야 올라가지만,  
큐 깊이는 과부하가 오기 **전에** 이미 신호를 준다.  
KEDA는 이 선행 지표로 스케일할 수 있어 CPU HPA 대비 훨씬 빠른 반응이 가능하다.

### 소스코드 분석(`--source`)을 쓰면 KEDA 점수가 크게 달라진다

YAML만 분석하면 큐/메트릭 신호를 알 수 없어 KEDA가 불리하다.  
`--source ./app` 옵션으로 소스 디렉토리를 넘기면 코드에서 키워드를 찾아 점수에 반영한다.

```bash
scalead values.yaml --source ./app
```

---

## 6. 감사(Audit) 항목 기준

감사는 점수와 별개로 **운영 안전성** 을 체크한다. 전략 선택에 직접 영향을 주지 않지만, 실제 배포 전 반드시 검토해야 할 항목들이다.

### 6-1. CPU Request

| 상태 | 기준 | 이유 |
|---|---|---|
| ok | 설정됨 | HPA CPU 메트릭 정상 동작 |
| error | 없음 | HPA가 CPU를 메트릭으로 쓸 수 없음 |

### 6-2. Memory Request

| 상태 | 기준 | 이유 |
|---|---|---|
| ok | 설정됨 | 메모리 기반 HPA 사용 가능 |
| warn | 없음 | OOM 위험 예측 불가, VPA와 연동 불가 |

### 6-3. CPU Limit

| 상태 | 기준 | 이유 |
|---|---|---|
| ok | 설정됨 | CPU throttling으로 비용 통제 가능 |
| info | 없음 | Throttling 없이 버스트 가능, 노드 자원 경쟁 가능성 |

> CPU limit은 **양날의 검**이다. 설정하면 비용 예측이 쉽지만 throttling으로 레이턴시가 올라갈 수 있다.  
> Java/Go처럼 CPU를 순간적으로 많이 쓰는 앱은 limit 없이 버스트를 허용하는 게 나을 수 있다.  
> 따라서 warn이 아닌 info로 분류한다.

### 6-4. HPA 활성화 여부

| 상태 | 기준 |
|---|---|
| ok | enabled: true |
| error | enabled: false — 수평 스케일링 없음 |

### 6-5. CPU Target (임계값)

| 상태 | 기준 | 이유 |
|---|---|---|
| ok | ≤ 60% | 스파이크 대응 헤드룸 충분 |
| info | 61~75% | 적정 수준, 트래픽 패턴에 따라 조정 가능 |
| warn | > 75% | 스케일아웃 발동이 너무 늦음, 포화 위험 |

**75% 기준 이유:**  
75%에서는 헤드룸이 25%뿐이다.  
스케일아웃 소요 시간(30~90초) 동안 트래픽이 조금만 더 몰려도 100%에 도달해 응답 지연이 발생한다.

### 6-6. Min Replicas

| 상태 | 기준 | 이유 |
|---|---|---|
| warn | < 2 | 단일 Pod — HA 보장 불가, Pod 재시작 시 서비스 중단 |
| info | 2 | 최소 HA이지만 롤링 업데이트 중 취약 |
| ok | ≥ 3 | 롤링 업데이트 중에도 2개 이상 유지 가능 |

### 6-7. Scale Range (max/min 비율)

| 상태 | 기준 | 이유 |
|---|---|---|
| ok | max/min ≤ 5 | 예측 가능한 비용 범위 |
| warn | max/min > 5 | 비용 폭발 가능성, HPA 버그 시 수십 배 스케일 위험 |

**5배 기준 이유:**  
min=2, max=10이면 5배다. 이 이상이면 오토스케일러가 오작동했을 때 예상치 못한 비용이 발생한다.  
또한 스케일인 시 Pod 제거 속도보다 스케일아웃 속도가 훨씬 빠르므로,  
범위가 넓을수록 비용 스파이크가 클 수 있다.

### 6-8. PodDisruptionBudget

| 상태 | 기준 | 이유 |
|---|---|---|
| ok | 설정됨 | 노드 drain/업그레이드 중 가용성 보호 |
| warn | 없음 | `kubectl drain` 시 모든 Pod 동시 삭제 가능 |

### 6-9. Readiness Probe

| 상태 | 기준 | 이유 |
|---|---|---|
| ok | initialDelay ≤ 10s | 신규 Pod가 빠르게 트래픽 수신 |
| warn | initialDelay > 10s | 너무 오래 unready 상태 유지 → 스케일아웃 효과 지연 |
| error | 미설정 | 준비 안 된 Pod에 트래픽 라우팅 → 500 에러 가능 |

### 6-10. Liveness Probe

| 상태 | 기준 | 이유 |
|---|---|---|
| ok | 설정됨 | 데드락/무한루프 Pod 자동 재시작 |
| warn | 미설정 | 응답은 없지만 살아있는 좀비 Pod 발생 가능 |

### 6-11. Startup Delay

| 상태 | 기준 | 이유 |
|---|---|---|
| ok | 0 < delay ≤ 5s | 빠른 시작 |
| warn | > 5s | 스케일아웃 속도 제한, 스파이크 취약성 증가 |

### 6-12. Graceful Shutdown

| 상태 | 조건 | 이유 |
|---|---|---|
| ok | `preStop + drain < grace` | SIGKILL 전에 drain 완료 가능 |
| warn | `preStop + drain ≥ grace` | SIGKILL이 drain 완료 전에 발생 → 처리 중 요청 유실 |
| warn | preStop 없음 | Pod 삭제 즉시 커넥션 끊김 |

**수식 설명:**
```
terminationGracePeriodSeconds = 전체 허용 시간
preStopSleepSeconds           = 연결 드레인 대기 (kube-proxy 업데이트 대기 포함)
shutdownDrainSeconds          = 앱 레벨 종료 처리 시간

조건: preStop + drain < grace  →  SIGKILL 전에 모두 완료
```

일반적으로 권장하는 설정:
```
preStop: 5~10s   (kube-proxy 전파 시간 커버)
drain:   5~15s   (앱이 처리 중인 요청 마무리)
grace:   preStop + drain + 5s 여유
```

---

## 7. 전략 선택 흐름 요약

```
서비스 분석
    │
    ├─ 소스코드에서 큐/메트릭 신호 발견?
    │       YES → KEDA 점수 급상승 → KEDA 추천 가능성 높음
    │       NO  → KEDA 기본 점수 낮음
    │
    ├─ HPA가 꺼져 있거나 CPU request 없음?
    │       → basic-hpa, tuned-hpa 모두 큰 감점
    │       → "HPA 활성화 + CPU request 설정" 이 선행 과제
    │
    ├─ HPA 켜짐, 설정이 느슨함 (high target / low min / slow probe)?
    │       → Tuned HPA 점수 상승 → 개선 Change 목록 제공
    │
    └─ HPA 켜짐, 설정이 이미 최적화됨?
            → Basic HPA 점수 우세 → "유지" 권장
```

---

## 부록: 빠른 참조표

| 항목 | 위험 구간 | 권장값 |
|---|---|---|
| CPU target | > 75% | 60~70% |
| minReplicas | < 2 | ≥ 3 |
| max/min 비율 | > 5× | ≤ 5× |
| readiness initialDelay | > 10s | ≤ 5s |
| readiness period | > 5s | 3s |
| preStop | 없음 | 5~10s |
| preStop + drain vs grace | ≥ grace | grace보다 5s 이상 작게 |
| startupDelay | > 5s | ≤ 3s |
