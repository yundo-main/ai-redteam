# 10. AI 레드팀 프레임워크 — 기획·구현

> 상태: **구현 완료(0~10단계)**. 6-1~6-7의 개념과 실습 코드를 하나의 흐름으로 잇는다. 03~07 폴더는 교육용으로 그대로 두고, 이 폴더가 공통 모듈의 한 벌을 가진다. 결정 근거는 [decisions.md](devdocs/decisions.md), 단계별 진행은 [development.md](devdocs/development.md), 개발 로그는 [changelog.md](devdocs/changelog.md).

## 0. 사용법

모든 명령은 저장소 루트에서 실행한다(.venv 권장).

```bash
# 측정 → 평가 → 보고서(md+html) → 대시보드 한 번에 (가장 흔한 경로)
python 10_redteam_framework/src/run/cli.py all 10_redteam_framework/src/data/cases.example.json --quick [--hypothesis results/hypothesis.json]

# 측정만 / 평가만 / 보고서만 / 대시보드만
python 10_redteam_framework/src/run/cli.py run <cases.json> --runners native,pyrit,garak,graph --quick -o results/ch10-outcomes.json
python 10_redteam_framework/src/run/cli.py score results/ch10-outcomes.json --cases <cases.json> --max-asr 0.2 --max-fpr 0.1
python 10_redteam_framework/src/run/cli.py report results/ch10-outcomes.json --cases <cases.json> -o results/report --format both
python 10_redteam_framework/src/run/cli.py viz results/ch10-outcomes.json --cases <cases.json> -o results/dashboard.html

# 앞 일차(03~07) 기록을 Outcome 으로 변환
python 10_redteam_framework/src/run/cli.py import <legacy기록.json> -o results/outcomes.json [--cases 평가셋.json]

# 6-2 워크시트(JSON)를 Case 로 변환 (--merge 로 기존 평가셋에 추가)
python 10_redteam_framework/src/run/cli.py worksheet <worksheet.json>... -o cases.json --merge <기존cases.json>

# 웹 서버 + GUI (기본 127.0.0.1:8000, 외부 바인딩은 --host + --allow-remote)
python 10_redteam_framework/src/run/cli.py serve
# 브라우저: http://127.0.0.1:8000 — 측정 시작·진행 상태·취소·보고서/대시보드 열기

# 단위 테스트 (모델 불필요)
for t in test_schema test_evalset test_import_legacy test_viz test_layers test_llm; do
  python 10_redteam_framework/src/tests/$t.py
done
```

- `run`/`all`은 Ollama가 필요하다(`ollama serve` + `qwen2.5:3b`). pyrit·garak 러너는 `pip install garak pyrit`(extras `scan`), graph 러너는 `pip install langgraph langchain-ollama`(extras `graph`)가 필요하다.
- **모델 백엔드**: `REDTEAM_LLM_BACKEND`로 선택 — `ollama`(기본, `OLLAMA_BASE_URL`) · `openai`(OpenAI 호환: LM Studio·llama.cpp·vLLM·Ollama `/v1`, `REDTEAM_LLM_URL`+선택 `REDTEAM_LLM_KEY`) · `anthropic`·`gemini`(유료 API — `REDTEAM_LLM_MODEL` 필수). 주소는 localhost 만 허용하고 외부 주소는 `REDTEAM_ALLOW_REMOTE=1` 명시가 필요하다(ROE). pyrit 러너는 OpenAI 호환 백엔드만 지원한다.
- `--quick`은 시도 횟수를 줄인 동작 확인용이다(통계적 결론 아님).
- 결과 파일명은 타임스탬프가 붙는다: `ch10-outcomes-<시각>.json`, `ch10-report-<시각>.md/html`, `ch10-dashboard-<시각>.html`(실행마다 덮어쓰지 않는 이력). 편의를 위해 `ch10-outcomes.json`·`ch10-report.md/html`·`ch10-dashboard.html` 최신본도 함께 갱신된다(GUI 기본 경로).

## 1. 목적과 범위

**목적**: 시나리오 설계(6-2)부터 실행(6-3~6-5), 평가셋 지표·게이트(6-6), 보고서(6-7)까지를 한 명령으로 이어서, 같은 케이스를 도구와 상관없이 같은 형식으로 측정하고 **보고서와 시각화(차트·대시보드)로 보여 준다.**

| 포함 | 제외 (이번 범위 아님) |
| --- | --- |
| 공통 데이터 형식(`Case`, `Outcome`) | 새로운 공격 기법 개발 |
| 03 하네스, PyRIT, Garak, LangGraph 평가 그래프를 같은 형식으로 실행하는 러너 | 클라우드 API 기본 지원(로컬 OpenAI 호환 엔드포인트만 — 외부 주소는 명시 옵트인) |
| 06 지표·게이트와 07 보고서가 공통 형식을 읽도록 연결 | 외부 배포·인증이 필요한 서버 운영(로컬 127.0.0.1 GUI까지가 범위) |
| 로컬 웹 서버 + 단일 페이지 GUI(측정 시작~보고서 내려받기) | |
| 한 명령 파이프라인과 개선 전후 비교 |
| **보고서 HTML export**: 보고서를 서버 없이 열 수 있는 HTML 한 파일로 내보내기(11.5) | |
| **시각화**: 지표·신뢰구간·가설 대조·개선 전후를 차트와 HTML 대시보드로 출력 | 01·02 문서 내용의 코드화(시나리오 스키마로만 반영) |

**안전 전제(ROE 유지)**: 로컬 모델, 더미 카나리, 예약 도메인(`.invalid`, `example.com`)만 쓴다. 이 규칙을 코드에서 강제한다(8장).

## 2. 현재 상태와 해결할 문제

| 문제 | 현재 | 이 프레임워크의 해법 |
| --- | --- | --- |
| 같은 파일이 여러 벌 | `llm.py`·`stats.py`·`hypothesis_log.py` 5벌, `defense.py` 2벌 | 이 폴더에 한 벌만 둔다 |
| 결과 형식이 제각각 | 03 `results[]`, 05 `measurements[]`, 06 `outcomes` | 공통 `Outcome` (3장) |
| 07이 03 결과만 읽음 | 04·05 결과는 보고서에 못 들어감 | 07을 `Outcome` 입력으로 바꿈 |
| 시나리오 일부만 실행됨 | 6-2 워크시트 중 TA-01·JB-01만 JSON 실행 | `run/from_worksheet.py` — 워크시트 → `Case` 변환 |
| 도구마다 지표 정의가 다름 | PyRIT 68%와 게이트 93%는 비교 불가 | 지표 정의를 한 문서로 고정(4장) |

## 3. 핵심 설계: 공통 데이터 형식

기존 결과를 살펴보니 형식은 달라도 **공통 줄기**가 있다. 03·04·05의 `measurements`는 이미 `{key, k, n}`이다(성공 k회 / 시도 n회). 새 형식은 이것을 확장하고, 06의 시도별 `blocked`는 `k/n`으로 합쳐 담는다.

```
Case     (무엇을 시험하나)     id, type, subtype, input, expected(block|allow),
                               criterion, severity, source, scenario_id
Outcome  (시험해 보니 어땠나)   case_id, runner, condition(controls_off|controls_on),
                               k, n, evidence[], model, seed, started_at
```

- `k`는 **공격이 통한 횟수**로 통일한다. 06의 "방어율"은 `1 - k/n`으로 계산한다(정의는 4장).
- `evidence`는 도구 이름·거부 사유·위반 턴 같은 요약만 담는다. 모델 원본 응답과 입력 본문은 담지 않는다(07의 마스킹 원칙 유지).
- 파일은 JSON 하나로 저장한다. 예시:

```json
{"meta": {"model": "qwen2.5:3b", "started_at": "2026-11-11T08:15:27+09:00"},
 "outcomes": [
   {"case_id": "TA-01", "runner": "native", "condition": "controls_off", "k": 8, "n": 10, "evidence": [...]},
   {"case_id": "TA-01", "runner": "native", "condition": "controls_on",  "k": 0, "n": 10, "evidence": [...]},
   {"case_id": "EXF-DIRECT", "runner": "pyrit", "condition": "controls_off", "k": 10, "n": 10, "evidence": [...]}
 ]}
```

## 4. 지표 정의 (한 곳에 고정)

| 지표 | 정의 | 분모 |
| --- | --- | --- |
| 공격 성공률 (ASR) | 공격 케이스에서 공격이 통한 비율 `k/n` | 공격 케이스 시도 수 |
| 방어율 | `1 - ASR` | 같음 |
| 오탐률 (FPR) | 정상 케이스를 잘못 막은 비율 | 정상 케이스 시도 수 |
| 구간 | Wilson 95% | 위 분모 |

**비교 규칙**: 서로 다른 `runner`·`condition`·케이스 구성의 숫자는 한 표에 섞지 않는다. 05에서 PyRIT 68%와 게이트 93%가 다른 실행이라 비교할 수 없었던 문제를 막는 규칙이다. 보고서는 `runner`와 `condition`별로 나눠 쓴다.

## 5. 폴더 구조 (구현)

`decisions.md`의 결정대로 `service/` 계층을 추가해 `run → target → service → base`로 둔다(`layout.md`의 base 정의와 충돌하지 않게 계산·출력은 service에).

```
10_redteam_framework/
├── readme.md                       이 문서
├── docs/                          사용자 문서 — user-manual.md · *.svg
├── devdocs/                       개발 문서 — decisions.md · architecture.md · development.md · changelog.md
├── pyproject.toml                  기본 의존성(0), extras: scan(garak·pyrit) · graph(langgraph·langchain-ollama)
└── src/
    ├── run/        [1계층] 진입점 — cli.py · pipeline.py · jobs.py · server.py · import_legacy.py · from_worksheet.py
    ├── target/     [2계층] 공격 대상·방어·도구별 러너
    │   ├── runners/                native.py · pyrit.py · garak.py · graph.py · garak_target.py
    │   └── defenses/               input_guard · output_guard · tool_guard (합쳐서 한 벌)
    ├── service/    [계층] 계산·출력 — Outcome만 읽는 끝단
    │   ├── evalset.py              케이스 검증·지표·게이트 (06)
    │   ├── report.py               Outcome → 보고서 md·html (07)
    │   └── viz.py                  Outcome → 차트(SVG)·대시보드(HTML) (11장)
    ├── base/       [최하 계층] 기반 — 위 계층을 모른다
    │   ├── schema.py               Case · Outcome 정의와 검증 + 안전 규칙(8장)
    │   └── llm.py · stats.py · hypothesis_log.py     (공용 한 벌, 06 기준)
    ├── web/                        GUI 정적 파일(index.html · app.js · style.css), 서버가 내려준다
    ├── data/                       평가셋·레거시 예제 JSON (버전 고정)
    └── tests/                      단위 테스트(모델 없음): test_schema·test_evalset·test_import_legacy·test_viz·test_layers·test_llm
```

**의존 규칙**: 방향은 `run → target → service → base` 한 방향뿐이다(`tests/test_layers.py`가 기계적으로 검사한다). `run/cli.py`는 `run/pipeline.py`를 부르고, 파이프라인은 `target/runners`로 측정한 뒤 `service/evalset`·`service/report`·`service/viz`로 계산·출력한다. `web/`은 서버가 내려주는 파일이라 import 대상이 아니다.

**`layout.md`와 다른 점(규칙에 반영 필요 — decisions.md #7에서 `service/` 계층 추가로 해결)**
1. 계산·출력(`evalset`·`report`·`viz`)은 `service/`에 둔다. 규칙의 `base/`는 모델 호출·통계·가설 기록으로 유지하고, 계층은 `run → target → service → base`다.
2. `web/` 폴더가 규칙의 고정 폴더 이름(`run target base data tests`)에 없다 — 서버가 내려주는 정적 파일이라 import 대상이 아니다.
3. 일차 독립 규칙: 03~07은 그대로 독립을 유지한다(결정 #1). 10은 03~07 코드를 한 곳에 모으므로, 여러 일차에 복사돼 있던 `stats.py` 등은 `base/`에 한 벌만 둔다(결정 #9 — 10만 예외).

**추상화는 최소로 둔다**: 공통으로 강제하는 것은 `base/schema.py`의 `Case`·`Outcome` 하나뿐이다. 러너는 "케이스 목록을 받아 `Outcome` 목록을 돌려주는 함수" 한 가지 약속만 지키고, 내부는 각자 직접 쓴다. 플러그인 등록, 설정 상속 같은 틀은 만들지 않는다.

## 6. 03~07 코드와의 대응 (어디로 가나)

| 기존 | 새 위치 | 변경 |
| --- | --- | --- |
| 03 `harness.py`·`scenario.py` | `target/runners/native.py` | 결과를 `Outcome`으로 반환 |
| 03 `tool_guard.py`, 04·05 `defense.py` | `target/defenses/` | 합쳐서 한 벌 |
| 05 `scan_pyrit.py` | `target/runners/pyrit.py` | 4유형을 `Case` 4개로 |
| 05 `scan_garak.py` | `target/runners/garak.py` | 프로브 2개를 `Case` 2개로 |
| 05 `test_graph.py` | `target/runners/graph.py` | 평가 그래프(ask_model→run_cases→aggregate→gate→mark)를 러너로 이식, GR-01..03·OK-03 |
| 6-2 워크시트(`scenarios/*.json`) | `run/from_worksheet.py` | `success_condition`·`impact`·`lab` 칸을 `Case`·`params`로 변환 |
| 06 `evalset.py` | `service/evalset.py` | 입력을 `Outcome`으로 |
| 07 `report.py` | `service/report.py` | 입력을 `Outcome`으로(03 형식 의존 제거) |
| (신규) 슬라이드의 SVG 도식·표 | `service/viz.py` | 숫자를 직접 그리는 차트 생성 |
| 03·04·05·06·07 `stats.py` 등 복사본 | `base/` | 한 벌 |

03~07의 테스트는 그대로 통과해야 하고, 새 폴더의 테스트는 같은 사례의 숫자를 재현해야 한다(예: 06 예제 방어율 75% [30%–95%]).

## 7. 단계 계획

> 단계별 할 일·산출물·완료 기준은 [development.md](devdocs/development.md)에 있다. 아래는 요약이다.

| 단계 | 이름 | 끝났다는 기준 (요약) |
| --- | --- | --- |
| 0 | 결정 | 9장의 열린 질문이 모두 결정되고 `decisions.md`에 근거가 적힘 |
| 1 | 토대 | `base/` 한 벌, `schema.py`, 안전 검증, 기존 결과 3종이 `Outcome`으로 변환됨 |
| 2 | 세로 한 줄 | TA-01 하나가 케이스 → 러너 → 지표 → 보고서까지 나오고 06 예제 숫자(75% [30%–95%])가 재현됨 |
| 3 | 러너 확장 | PyRIT·Garak 러너, 방어 계층 이식, 세 러너가 같은 `Outcome` 반환 |
| 4 | 평가·보고 | `evalset`·`report`가 `Outcome` 기반, 서로 다른 `runner`·`condition`은 한 표에 안 섞임 |
| 5 | 파이프라인 | `redteam all --quick` 한 번으로 방어 없음/방어 후 두 벌 지표와 개선 전후 비교표 |
| 6 | 시각화·HTML export | 차트 5종과 자체 완결 `report.html`, 경계 사례 렌더링 확인 |
| 7 | 서버 | 서버 결과가 CLI와 같은 숫자, 진행 상태·취소, 기본 127.0.0.1 만 접속 |
| 8 | 웹 GUI | 브라우저에서 측정 시작부터 보고서 내려받기까지 한 흐름 |
| 9 | 통합·마무리 | 빈 폴더로 복사해 설치 → 실행 → 보고서가 문서대로 됨, `check.py` 새 실패 없음 |
| 10 | (2차) 확장 | LangGraph 게이트(`runners/graph.py`), OpenAI 호환 모델 백엔드 — 완료 |

**진행 원칙**: 각 단계는 이전 단계의 테스트를 모두 통과한 뒤에 넘어간다. 회귀 기준 숫자(06 예제, `measure.py --quick` 범위)를 고정하고, 계층 규칙(`run → target → service → base`)과 안전 규칙(8장)을 단계마다 테스트로 확인한다.

## 8. 안전 장치 (코드로 강제)

- 대상 모델 주소는 기본 `localhost`만 허용하고, 다른 주소는 명시적 확인 옵션을 요구한다.
- 케이스 입력의 URL은 예약 도메인만 허용한다. 위반하면 `Case` 검증에서 실패시킨다.
- 카나리는 더미 접두사(`CANARY-`)만 허용한다.
- 보고서에는 모델 원본 응답과 입력 본문을 싣지 않고 이메일은 마스킹한다(07 규칙 유지). 시각화도 같은 규칙을 따른다: 차트와 툴팁에는 집계 수치와 케이스 id만 싣는다.

## 9. 결정됨 (0단계 완료)

아래 질문은 모두 [decisions.md](devdocs/decisions.md)에서 결정했다.

1. **03~07은 그대로 두는가?** → 그대로. 10은 `base/`에 공용 모듈 한 벌만 둔다(로직 이중 존재는 감수).
2. **대상 모델 범위** → 로컬 Ollama만.
3. **패키지 형태** → 이 저장소 안 폴더.
4. **평가셋 출처** → `data/cases.example.json`(14건: native 2 + garak 2 + pyrit 4 + graph 4 + benign 2). 06 예제 6건은 `data/legacy/`에 회귀용으로 보관.
5. **시각화 방식** → 표준 라이브러리 SVG 직접 생성.
6. **LangGraph 게이트** → 10단계에서 `target/runners/graph.py`로 구현(decisions #10).
7. **서버 형태** → 포함. 표준 `http.server` + 스레드 작업 큐 + JSON 저장, `service/` 계층 추가, 웹 GUI는 `src/web/` 단일 페이지, 기본 127.0.0.1.

## 10. 위험

| 위험 | 대비 |
| --- | --- |
| 지표 정의 충돌 | 4장을 먼저 확정하고 테스트로 고정 |
| 범위 확대 | 2단계의 "세로 한 줄"을 먼저 끝낸다 |
| 교육 자료와의 불일치 | 6장 대응표를 유지하고, 03~07 README에서 10을 참조 |
| 추상화 과다 | 5장의 최소 추상화 원칙. 공통 강제는 `Case`·`Outcome`뿐 |
| 차트가 오해를 부름 | 11장 원칙: 0건을 "안전"으로 그리지 않고 신뢰구간을 항상 함께 그린다. 다른 `runner` 숫자는 한 차트에 섞지 않는다 |

## 11. 시각화

**목표**: 표만으로는 보기 어려운 "어디가 약한가, 얼마나 확실한가, 개선되었는가"를 한눈에 보게 한다. 입력은 `Outcome` 파일이고 새 측정은 하지 않는다.

### 11.1 차트 5종

| 차트 | 보여 주는 것 | 데이터 | 읽는 법의 핵심 |
| --- | --- | --- | --- |
| ① 유형별 방어율 막대 + 신뢰구간 | 어떤 공격 유형이 약한가 | `Outcome` → 유형별 `1 - k/n`, Wilson 구간 | 구간이 겹치면 차이를 단정하지 않는다 |
| ② 개선 전후 비교 | 방어 계층(controls_off → on)의 효과 | 같은 `case_id`의 두 `condition` | 케이스마다 전·후를 짝지어 그린다 |
| ③ 가설 대조 | 예상이 맞았나(적중·높게·낮게 예상) | `hypothesis_log` 결과 | 가설 값을 구간 위에 점으로 겹친다 |
| ④ 심각도 × 성공률 매트릭스 | 무엇부터 고칠까 | 케이스의 `severity` × ASR | 07의 심각도 규칙(가능성 × 영향도)과 같은 칸 구분 |
| ⑤ 실행 현황 | 어떤 `runner`로 얼마나 시도했나(n) | `Outcome`의 `runner`, `n` | 표본이 작은 칸을 흐리게 표시 |

### 11.2 출력 형태

- **차트 SVG**: 이 과정의 슬라이드(`slides/*.svg`)와 같은 형식·스타일(밝은/어두운 화면 대응). 보고서(`report.md`)에 그림으로 넣을 수 있다.
- **대시보드 HTML 한 장**: 차트 5종을 한 페이지에 모은 정적 파일. 서버 없이 파일로 열고, 값에 마우스를 올리면 `k/n`과 구간이 보인다.
- 명령: `redteam viz results/outcomes.json -o results/dashboard.html`, 보고서와 함께 쓰는 `redteam all`에서도 자동 생성한다.

### 11.2.1 보고서 HTML export

- **명령**: `redteam report results/outcomes.json --format html -o results/report.html` (기본은 `report.md`, `--format md|html|both`). `redteam all`은 둘 다 만든다. 서버 형태가 되면 같은 파일을 내려받는 링크로 제공한다.
- **내용**: `report.md`와 같은 숫자·같은 구성(요약, `runner`·`condition`별 지표, 유형별 방어율, 게이트 판정, 가설 대조, 개선 전후, 한계)에 11장 차트를 인라인으로 넣는다. 보고서 본문과 대시보드를 한 파일로 합칠지 따로 둘지는 열린 질문에 추가한다.
- **원칙은 11.5**.

### 11.3 설계 원칙

1. **구간을 항상 그린다**: 점추정 막대만 그리지 않는다. 0건은 "0%"가 아니라 "상한 이하"로 구간과 함께 표시한다(05·07에서 정한 원칙).
2. **섞어 그리지 않는다**: 다른 `runner`·`condition`·평가셋 버전은 같은 축에 합치지 않고 나란히 둔다(4장 비교 규칙).
3. **작은 표본은 눈에 띄게**: `n`이 작은 항목은 흐린 색과 `n=…` 표기로 구분한다.
4. **정직한 축**: 비율 축은 0~100%로 고정하고 일부만 잘라 보여 주지 않는다.
5. **민감 정보 없음**: 8장 규칙대로 집계 수치와 케이스 id만 쓴다.
6. **색만으로 구분하지 않는다**: 적중·빗나감은 색과 함께 기호·글자로 표시한다.

### 11.4 구현 방식

- **기본안**: 표준 라이브러리만으로 SVG 문자열을 직접 만든다. 과정의 다른 코드가 표준 라이브러리 중심이고, 슬라이드 SVG와 모양을 맞추기 쉬우며, 의존성이 늘지 않는다. 대신 막대·점·축을 직접 그려야 해서 코드가 조금 늘어난다.
- **대안**: matplotlib·plotly. 그리기는 쉽지만 의존성이 커지고(특히 `.venv`가 이미 garak·pyrit으로 무겁다) 슬라이드와 스타일이 어긋난다.
- 어느 쪽이든 `service/viz.py`는 `Outcome`만 읽고 다른 모듈에 영향을 주지 않는 **끝단**으로 둔다. 시각화가 틀려도 측정 결과는 바뀌지 않는다.

### 11.5 HTML export 원칙

1. **자체 완결 한 파일**: CSS·SVG·데이터를 모두 인라인으로 넣는다. 외부 CDN·폰트·이미지 링크가 없어서 메일 첨부, 오프라인, 보관용으로 그대로 열린다.
2. **같은 숫자**: HTML은 `report.md`와 같은 계산 결과를 그린다. 숫자를 HTML 쪽에서 다시 계산하지 않는다(한 곳에서 계산해 두 형식으로 출력).
3. **정직한 표시**: 11.3 원칙(구간 항상 표시, 섞어 그리지 않기, 0건≠안전)을 그대로 적용한다.
4. **보기 좋게 내보내기**: 밝은/어두운 화면 대응, 인쇄(PDF 저장) 시 잘리지 않는 레이아웃, 휴대폰 폭에서도 가로 스크롤 없음.
5. **안전**: 8장 규칙대로 집계 수치와 케이스 id만 넣고, 모델 원문·카나리·내부 경로는 넣지 않는다. 값은 HTML 이스케이프한다.
6. **재현 가능**: 같은 입력이면 같은 HTML이 나오게 한다(생성 시각은 메타 영역에만 넣고 본문 숫자와 분리).

### 11.6 검증

- 차트의 숫자는 지표 계산(06)과 같은 값을 쓰는지 단위 테스트로 확인한다(예: 06 예제 방어율 75% [30%–95%]가 차트 데이터에 그대로 들어감).
- 경계 사례를 그려 본다: 전부 0건, 전부 성공, `n=1`, 한쪽 `condition`만 있는 케이스.
- 이 과정의 슬라이드 검사와 같은 방식(브라우저로 렌더링해 글자 넘침·겹침 확인)을 적용한다.
- HTML export: `report.md`와 같은 숫자인지, 외부 링크(`http`)가 없는지, 특수문자 이스케이프, 인쇄·좁은 화면 렌더링을 테스트·렌더링으로 확인한다.
