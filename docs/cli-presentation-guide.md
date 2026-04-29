# scalead CLI 발표자료 정리 가이드

이 문서는 `scalead` CLI를 발표자료에 넣을 때, **무엇을 보여주고 어떤 메시지로 설명할지** 빠르게 정리하기 위한 문서다.  
목표는 "CLI를 만들었다"가 아니라 **배포 전에 오토스케일링 전략을 빠르게 점검하고 추천까지 받는 도구를 만들었다**는 점을 전달하는 것이다.

---

## 1. 발표에서 먼저 잡아야 할 한 줄

발표 첫 설명은 아래 한 줄로 정리하는 편이 가장 깔끔하다.

> scalead는 Helm values나 Kubernetes 매니페스트를 정적으로 분석해서, 서비스에 맞는 오토스케일링 전략(HPA, Tuned HPA, KEDA)을 추천하는 CLI다.

조금 더 짧게 줄이면 아래 버전도 좋다.

> scalead는 K8s 배포 전에 오토스케일링 설정을 미리 점검해 주는 CLI다.

---

## 2. 발표자료에 넣기 좋은 전체 흐름

슬라이드는 아래 순서로 가는 것이 자연스럽다.

1. 문제 정의
2. CLI 소개
3. 입력과 출력 구조
4. 추천 전략 예시
5. 데모
6. 기대 효과

각 장표에서 전달할 메시지는 아래처럼 잡으면 된다.

### 문제 정의 슬라이드

- K8s 오토스케일링은 설정값이 많아서 처음부터 맞추기 어렵다.
- CPU 기반 HPA만으로 충분한지, KEDA가 필요한지 판단이 어렵다.
- 배포 전에 values.yaml이나 manifest만 보고도 빠르게 1차 점검할 수 있으면 좋다.

발표 멘트 예시:

> 실제로는 서비스 코드를 다 띄워 보기 전까지 어떤 스케일링 전략이 맞는지 감으로 정하는 경우가 많았습니다. 그래서 배포 전에 설정 파일과 소스 코드만 보고도 1차 추천을 해 주는 CLI를 만들었습니다.

### CLI 소개 슬라이드

- 이름: `scalead`
- 역할: 정적 분석 기반 오토스케일링 전략 추천
- 입력: Helm values 파일 또는 K8s 매니페스트 디렉토리
- 선택 입력: 애플리케이션 소스 디렉토리 (`--source`)
- 출력: Audit 결과, 추천 전략, 변경 제안, 전략 비교 점수

넣기 좋은 명령어:

```bash
scalead values.yaml
scalead values.yaml --source ./app
scalead k8s/manifests/
scalead values.yaml --format json
```

### 입력/출력 구조 슬라이드

발표자료에는 출력 전체를 다 넣기보다, 아래 3개만 잘라서 보여주는 편이 낫다.

1. `Config Audit`
2. `추천 전략`
3. `권장 변경사항`

핵심 메시지:

- 단순히 "된다/안 된다"가 아니라 현재 설정 상태를 항목별로 보여준다.
- 최종적으로는 어떤 전략이 더 적합한지 점수와 이유로 추천한다.
- 필요한 경우 values에서 무엇을 바꿔야 하는지 변경안까지 제시한다.

---

## 3. 이 프로젝트 기준으로 발표에 쓰기 좋은 샘플

현재 저장소의 샘플은 발표 흐름에 맞게 이미 잘 나뉘어 있다.

### 가장 무난한 데모 1: CPU-heavy 앱

명령어:

```bash
python -m autoscaling_advisor.cli samples/values-cpu-heavy.yaml --format json
```

전달 포인트:

- 추천 결과: `Basic HPA`
- 의미: CPU 부하 중심 워크로드는 CPU 기반 HPA가 자연스럽다.
- 메시지: 모든 서비스에 KEDA가 필요한 것이 아니라, 워크로드 특성에 따라 기본 HPA가 더 적절할 수 있다.

발표 멘트 예시:

> CPU 집약적인 서비스는 굳이 복잡한 이벤트 기반 스케일링까지 가지 않아도 기본 HPA가 합리적이라고 판단합니다.

### 가장 보여주기 좋은 데모 2: Metrics API

명령어:

```bash
python -m autoscaling_advisor.cli samples/values-metrics-api.yaml --source samples/apps/api-with-metrics --format json
```

전달 포인트:

- 추천 결과: `KEDA + Prometheus`
- 이유: `/metrics` 노출, Prometheus 사용, request metric 감지
- 메시지: 소스 코드까지 같이 보면 CPU 사용률보다 더 선행적인 신호로 스케일링할 수 있다.

발표 멘트 예시:

> 단순 values만 보면 HPA로 끝날 수 있지만, 소스까지 같이 보면 request metric을 노출하고 있어서 KEDA 기반 전략이 더 적합하다고 판단합니다.

### 임팩트 있는 데모 3: Kafka Consumer

명령어:

```bash
python -m autoscaling_advisor.cli samples/values-kafka-consumer.yaml --source samples/apps/kafka-consumer --format json
```

전달 포인트:

- 추천 결과: `KEDA + Prometheus`
- 점수: `100`
- 이유: queue integration, queue depth metric, background worker 패턴 감지
- 메시지: 큐 기반 워커는 CPU보다 backlog나 lag가 더 직접적인 스케일링 신호다.

발표 멘트 예시:

> Kafka consumer 같은 워커는 CPU 사용률보다 queue lag나 depth가 더 중요한 신호라서, CLI가 KEDA를 강하게 추천합니다.

---

## 4. 발표자료 장표별로 바로 넣을 수 있는 문안

### 장표 1. 프로젝트 한 줄 소개

> scalead는 K8s 배포 전에 values.yaml, manifest, 소스 코드를 정적으로 분석해서 오토스케일링 전략을 추천하는 CLI입니다.

### 장표 2. 왜 만들었는가

- HPA 설정만 있다고 해서 실제 트래픽 패턴에 맞는 것은 아니다.
- CPU 기반 스케일링이 맞는지, 이벤트 기반 스케일링이 필요한지 초기에 판단하기 어렵다.
- 운영 전에 빠르게 위험 요소와 개선 포인트를 확인할 필요가 있다.

### 장표 3. 어떻게 동작하는가

- Helm values 또는 K8s manifest를 읽는다.
- HPA, resource request, probe, PDB, shutdown 설정을 audit 한다.
- `--source`가 있으면 메트릭 노출, Prometheus 사용, queue 연동 여부를 추가 분석한다.
- 최종적으로 `Basic HPA`, `Tuned HPA`, `KEDA + Prometheus` 중 하나를 추천한다.

### 장표 4. 결과 화면에서 봐야 할 것

- Audit: 현재 설정 상태와 위험 요소
- Recommendation: 가장 적합한 전략과 이유
- Changes: 바로 수정할 수 있는 제안값
- Comparison: 다른 전략과의 점수 차이

### 장표 5. 데모에서 강조할 것

- 단순 lint가 아니라 **전략 추천**까지 한다.
- 인프라 설정만이 아니라 **애플리케이션 신호**까지 반영한다.
- 서비스 유형에 따라 추천 결과가 달라진다.

### 장표 6. 기대 효과

- 배포 전 오토스케일링 설정 검토 시간 단축
- 잘못된 HPA 기본값 사용 위험 감소
- KEDA 도입이 필요한 서비스 후보를 조기 식별

---

## 5. 추천 데모 시나리오

발표 시간이 짧으면 아래 순서가 가장 안정적이다.

### 3분 버전

1. `scalead`가 무엇인지 한 줄 소개
2. `values-cpu-heavy.yaml` 실행 결과로 Basic HPA 사례 소개
3. `values-metrics-api.yaml --source ...` 결과로 KEDA 추천 사례 소개
4. "설정만이 아니라 코드 신호까지 본다"로 마무리

### 5분 버전

1. 문제 정의
2. CLI 입력/출력 구조 설명
3. CPU-heavy 예시로 Basic HPA 추천
4. Metrics API 예시로 `--source` 유무 차이 설명
5. Kafka Consumer 예시로 큐 기반 워커에는 KEDA가 적합함을 강조
6. 기대 효과 정리

### 라이브 데모 대신 스크린샷만 넣을 때

아래 3개 화면만 캡처해도 충분하다.

1. `scalead --help`
2. CPU-heavy 결과 화면
3. Kafka Consumer 또는 Metrics API 결과 화면

---

## 6. 발표자료에 넣기 좋은 비교 포인트

### 기존 방식

- values.yaml을 사람이 직접 읽고 감으로 판단
- CPU 기준 HPA만 우선 적용
- 큐 기반 워커나 메트릭 기반 서비스 특성을 놓치기 쉬움

### scalead 사용 방식

- 설정 파일을 자동 audit
- 소스 코드까지 포함해 workload 신호 분석
- HPA와 KEDA 중 더 적합한 전략 추천
- 수정 포인트까지 함께 제안

한 줄 비교 문구:

> 사람이 설정을 읽고 추측하던 과정을, CLI가 구조화된 점검과 추천으로 바꿔 준다.

---

## 7. 발표자료에 넣을 때 주의할 점

- "자동으로 완벽한 스케일링을 보장한다"처럼 말하면 과장이다.
- 정확한 표현은 "배포 전 1차 의사결정을 돕는 추천 도구"에 가깝다.
- KEDA 추천은 메트릭 노출, 큐 연동, 워커 패턴 같은 신호를 기반으로 한다고 설명하는 편이 신뢰도가 높다.
- JSON 출력은 "CI/CD 연동 가능성" 정도로 짧게만 언급하면 충분하다.

추천 표현:

> 운영 결정을 완전히 대체하는 도구가 아니라, 초기 설정 검토와 전략 선택을 빠르게 도와주는 CLI입니다.

---

## 8. 발표 마지막 정리 문구

마무리 슬라이드에는 아래 문장 중 하나를 쓰면 된다.

> scalead는 K8s 오토스케일링 설정을 사람이 감으로 맞추는 구간을 줄이고, 서비스 특성에 맞는 전략을 더 빠르게 고를 수 있게 해 주는 CLI입니다.

또는

> 이 프로젝트의 핵심은 배포 전에 설정과 코드를 함께 보고, HPA와 KEDA 사이의 선택을 더 근거 있게 만들었다는 점입니다.

---

## 9. 발표 준비 체크리스트

- `scalead --help` 화면 캡처
- `samples/values-cpu-heavy.yaml` 결과 캡처
- `samples/values-metrics-api.yaml --source samples/apps/api-with-metrics` 결과 캡처
- 필요하면 `samples/values-kafka-consumer.yaml --source samples/apps/kafka-consumer` 결과 캡처
- 장표 첫 문장에 "정적 분석 기반 오토스케일링 전략 추천 CLI" 문구 반영
- 장표 마지막에 "배포 전 1차 의사결정 지원" 메시지 반영
