# scalead CLI 구조 설명

이 문서는 `scalead` CLI가 어떻게 만들어졌는지 설명한다.  
코드를 처음 보는 사람이 `cli.py`부터 따라가며 구조를 이해할 수 있게 정리했다.

---

## 1. 전체 흐름

`scalead`의 실행 흐름은 단순하다.

1. CLI 인자를 받는다.
2. 입력을 스캔해서 `ScanResult`로 정규화한다.
3. 필요하면 `--source`로 소스코드 신호를 보강한다.
4. audit를 만든다.
5. 세 가지 전략을 점수화한다.
6. rich 또는 json으로 출력한다.

핵심은 입력 형식이 달라도 마지막에는 모두 같은 데이터 구조로 모인다는 점이다.

---

## 2. 엔트리포인트

관련 파일:

- [pyproject.toml](C:/Users/DGSO1/scalead-k8s/pyproject.toml)
- [autoscaling_advisor/cli.py](C:/Users/DGSO1/scalead-k8s/autoscaling_advisor/cli.py)

CLI 명령은 `pyproject.toml`에 아래처럼 등록되어 있다.

```toml
[project.scripts]
scalead = "autoscaling_advisor.cli:main"
```

그래서 사용자가 `scalead ...`를 실행하면 `cli.py`의 `main()`이 호출된다.

`main()`의 책임은 작다.

- 대상 경로가 파일인지 디렉토리인지 판단
- 적절한 스캐너 호출
- 선택적으로 소스코드 스캔 호출
- 추천 엔진 호출
- 출력 포맷 분기

즉, 실제 분석은 다른 모듈이 하고 `cli.py`는 오케스트레이션만 담당한다.

---

## 3. 왜 `ScanResult`를 중심으로 만들었는가

관련 파일:

- [autoscaling_advisor/models.py](C:/Users/DGSO1/scalead-k8s/autoscaling_advisor/models.py)

이 프로젝트의 중심 데이터 구조는 `ScanResult`다.

이 안에는 아래 정보가 들어간다.

- HPA 설정
- 리소스 request / limit
- readiness / liveness probe
- startup / shutdown 관련 앱 설정
- PDB
- observability 설정
- 소스코드에서 읽어낸 앱 신호
- replica 수

이 구조를 두는 이유는 명확하다.

- Helm values 분석과 manifest 분석을 같은 후처리 로직에 태울 수 있다.
- audit와 scoring이 입력 형식을 몰라도 된다.
- 출력도 하나의 결과 객체만 보면 된다.

즉, “입력 파싱”과 “판단 로직”을 분리한 설계다.

---

## 4. 스캐너 구조

관련 파일:

- [autoscaling_advisor/scanner.py](C:/Users/DGSO1/scalead-k8s/autoscaling_advisor/scanner.py)

`scanner.py`는 입력을 읽어서 `ScanResult`를 채운다.

### `scan_helm_values(path)`

Helm values 파일을 읽는다.

여기서는 YAML 전체를 해석하려는 것이 아니라, 추천에 필요한 키만 뽑는다.

예:

- `hpa.enabled`
- `hpa.minReplicas`
- `hpa.maxReplicas`
- `hpa.targetCPUUtilizationPercentage`
- `resources.requests.cpu`
- `deployment.readinessProbe`
- `serviceMonitor.enabled`

즉, values 파일은 “Helm 템플릿 입력값”으로 보고 필요한 필드만 추출한다.

### `scan_k8s_dir(path)`

manifest 디렉토리 안의 `*.yaml`을 순회한다.

그리고 `_parse_k8s_doc()`에서 kind별로 처리한다.

지원하는 주요 리소스는 아래와 같다.

- `Deployment`
- `HorizontalPodAutoscaler`
- `PodDisruptionBudget`
- `ServiceMonitor`

여러 파일에 흩어진 정보를 하나의 `ScanResult`로 합치는 방식이다.

### `_parse_container()`

`Deployment` 안의 첫 번째 컨테이너를 기준으로 읽는다.

여기서 읽는 내용은 다음과 같다.

- resources
- readiness / liveness probe
- 환경변수 기반 startup / shutdown 힌트
- lifecycle preStop sleep

현재 구현은 샘플 앱이 단일 컨테이너라는 가정 위에 서 있다.

---

## 5. `--source`는 무엇을 하나

관련 파일:

- [autoscaling_advisor/scanner.py](C:/Users/DGSO1/scalead-k8s/autoscaling_advisor/scanner.py)

`--source`는 소스코드를 읽어서 workload 성격을 추론하는 보조 단계다.

예:

```bash
scalead samples/values-kafka-consumer.yaml --source samples/apps/kafka-consumer
```

이때 `enrich_with_source()`가 호출된다.

이 함수는 여러 언어의 텍스트 파일을 훑고 키워드 기반으로 `AppSignals`를 채운다.

감지하려는 대표 신호는 아래와 같다.

- Prometheus 메트릭 노출
- request metric 존재
- queue metric 존재
- Kafka / RabbitMQ / Celery 같은 큐 연동
- consumer / worker 패턴
- CPU-heavy 라이브러리 사용

중요한 점은 이 단계가 정교한 AST 분석이 아니라는 점이다.  
휴리스틱 기반 키워드 매칭이기 때문에 가볍고 언어 독립적이지만, 오탐/미탐 가능성은 있다.

---

## 6. audit는 어디서 만드는가

관련 파일:

- [autoscaling_advisor/auditor.py](C:/Users/DGSO1/scalead-k8s/autoscaling_advisor/auditor.py)

`audit()`는 `ScanResult`를 읽어서 사람이 이해하기 쉬운 점검 항목 목록을 만든다.

예를 들면 아래를 점검한다.

- CPU request 유무
- memory request 유무
- HPA 활성화 여부
- CPU target이 너무 높은지
- minReplicas가 너무 낮은지
- PDB 존재 여부
- readiness / liveness probe 상태
- startup delay
- graceful shutdown 구조
- ServiceMonitor 활성화 여부
- queue / worker 신호 여부

여기서 중요한 설계 포인트는 audit와 추천을 분리한 점이다.

- audit = 현재 상태 설명
- recommendation = 어떤 전략이 더 적합한지 선택

---

## 7. 추천 엔진 구조

관련 파일:

- [autoscaling_advisor/engine.py](C:/Users/DGSO1/scalead-k8s/autoscaling_advisor/engine.py)

추천 엔진은 세 가지 전략을 각각 점수화한다.

- `Basic HPA`
- `Tuned HPA`
- `KEDA + Prometheus`

각 전략은 별도 함수로 분리되어 있다.

### `_score_basic_hpa()`

CPU 기반 기본 전략이다.

점수가 유리해지는 경우:

- HPA가 켜져 있음
- CPU request가 있음
- CPU-heavy 성격이 있음
- CPU target이 과하게 높지 않음

### `_score_tuned_hpa()`

기본은 HPA지만, 튜닝 여지가 큰 서비스에 더 적합하다고 보는 전략이다.

예:

- startup delay가 김
- minReplicas가 낮음
- CPU target이 높음
- readiness period가 김

이 전략은 점수뿐 아니라 변경 제안도 함께 만든다.

### `_score_keda()`

외부 메트릭 기반 전략이다.

점수가 유리해지는 경우:

- queue integration 감지
- request metric 감지
- queue metric 감지
- background worker 패턴 감지
- ServiceMonitor 존재
- KEDA 활성화

즉, CPU보다 더 좋은 선행 지표가 있는 서비스에 유리하다.

### `recommend()`

세 전략 점수를 모두 계산한 뒤 정렬해서 최고 점수를 고른다.  
동시에 audit도 묶어서 최종 `RecommendationResult`를 만든다.

---

## 8. 출력 구조

관련 파일:

- [autoscaling_advisor/renderer.py](C:/Users/DGSO1/scalead-k8s/autoscaling_advisor/renderer.py)

출력은 `render()`가 담당한다.

사람용 터미널 출력은 `rich`를 이용해 아래 블록으로 보여준다.

1. Header
2. Config Audit
3. 추천 전략
4. 권장 변경사항
5. 리스크
6. 전략 비교

반대로 `--format json`을 쓰면 dataclass를 그대로 JSON 직렬화해서 출력한다.  
즉, 사람용 화면과 자동화 연동용 포맷이 분리되어 있다.

---

## 9. 설계상 장점

- 입력 형식이 달라도 후처리 로직을 공유한다.
- audit 규칙과 추천 규칙을 따로 발전시킬 수 있다.
- source 분석은 선택 사항이라 점진적으로 쓸 수 있다.
- rich 출력과 json 출력이 분리돼 있다.
- 발표나 데모에서 결과를 설명하기 좋다.

---

## 10. 현재 한계

- source 분석은 휴리스틱이라 정밀 분석은 아니다.
- manifest 분석은 일부 kind 중심이다.
- 멀티 컨테이너 Pod를 깊게 보지 않는다.
- 실제 운영 메트릭은 보지 않는다.

즉, 이 도구는 “정적 분석 기반 추천기”이지, 운영 데이터 기반 예측 시스템은 아니다.

---

## 11. 처음 읽을 때 추천 순서

코드를 따라가려면 아래 순서가 가장 빠르다.

1. [autoscaling_advisor/cli.py](C:/Users/DGSO1/scalead-k8s/autoscaling_advisor/cli.py)
2. [autoscaling_advisor/models.py](C:/Users/DGSO1/scalead-k8s/autoscaling_advisor/models.py)
3. [autoscaling_advisor/scanner.py](C:/Users/DGSO1/scalead-k8s/autoscaling_advisor/scanner.py)
4. [autoscaling_advisor/auditor.py](C:/Users/DGSO1/scalead-k8s/autoscaling_advisor/auditor.py)
5. [autoscaling_advisor/engine.py](C:/Users/DGSO1/scalead-k8s/autoscaling_advisor/engine.py)
6. [autoscaling_advisor/renderer.py](C:/Users/DGSO1/scalead-k8s/autoscaling_advisor/renderer.py)

이 순서대로 보면 `입력 -> 정규화 -> 점검 -> 추천 -> 출력` 흐름이 보인다.
