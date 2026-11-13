# 사용 매뉴얼 (GUI)

이 문서는 웹 GUI(`http://127.0.0.1:8971`) 기준으로 **가설 → 측정 → 평가 → 분석 → 시각화** 흐름을 처음부터 끝까지 안내한다.
용어 뜻은 GUI의 **매뉴얼 탭 하단 인덱스**(가나다순 사전)를 참고. CLI 명령은 [../readme.md](../readme.md) 0절 참고.

## 0. 서버 실행

흐름도를 먼저 보면 이해가 빠르다: [서버 실행 흐름도(SVG)](/docs/server-run.svg)

### 0-1. 사전 준비

- **Python 3.9+** 와 저장소 클론이 필요하다.
- **측정(LLM 호출)을 하려면 Ollama**가 먼저 떠 있어야 한다:

```bash
ollama serve            # 터미널 1 — 상주 실행
ollama pull qwen2.5:3b  # 최초 1회
```

- 평가·분석·시각화·작업로그만 보는 용도라면 Ollama 없이도 된다(측정만 실패).
- graph/pyrit/garak 러너를 쓰려면 추가 패키지가 필요하다(`pip install garak pyrit langgraph langchain-ollama`, pyproject의 extras `scan`·`graph`). 설치 여부는 설정 탭 "서버·모델 환경" 카드에서 확인된다.

### 0-2. 서버 켜기

저장소 루트(`ai-redteam/`)에서:

```bash
# 포그라운드(이 터미널이 서버 — Ctrl+C로 종료)
.venv/bin/python 10_redteam_framework/src/run/cli.py serve --port 8971

# 백그라운드(터미널 닫아도 유지)
nohup .venv/bin/python 10_redteam_framework/src/run/cli.py serve --port 8971 > /tmp/redteam-server.log 2>&1 &
```

- 가상환경(`.venv`)으로 실행해야 graph·pyrit·garak 러너가 "설치됨"으로 잡힌다. 시스템 `python`로 띄우면 선택적 의존성이 빠질 수 있다.
- 포트 생략 시 기본 `8000`, GUI 기본 포트는 `8971`이다. 포트가 바쁘면 `--port`로 다른 번호를 준다.
- 브라우저에서 `http://127.0.0.1:<포트>` 접속. 기본 바인딩은 `127.0.0.1`(로컬 전용)이다. 외부 접근은 `--host 0.0.0.0 --allow-remote` 둘 다 필요하고, 이 서버엔 인증이 없으므로 교육용 로컬 전용으로만 쓴다.

### 0-3. 서버 끄기·상태 확인

```bash
# 포트로 프로세스 찾기
lsof -ti :8971

# 백그라운드 서버 종료
kill $(lsof -ti :8971)

# 로그 보기(백그라운드로 띄운 경우)
tail -f /tmp/redteam-server.log
```

- 서버를 꺼도 `results/`의 결과 파일·작업 기록·평가 로그는 디스크에 남아 재시작 후 그대로 보인다.
- "연결이 안 됨"이면 ① 서버가 실제로 떴는지(`lsof -ti :8971`) ② 포트 번호가 맞는지 ③ 브라우저 강력 새로고침 순으로 확인한다.

## 1. 설정 탭 — 처음 한 번만

1. **"서버·모델 환경"** 카드에서 현재 백엔드·엔드포인트·러너 설치 여부 확인
2. 다른 모델을 쓰려면 **"연결 설정"** 카드에서 백엔드(ollama/openai/anthropic/gemini) 선택 → 주소·모델·API 키 입력 → **설정 저장**
   - 저장은 즉시 적용되고 `10_redteam_framework/settings.json`에 영속 저장된다(재시작해도 유지)
   - API 키는 화면에 끝 4자리만 표시되고, 비워 두면 기존 키가 유지된다
3. **"LLM 연결 테스트"**로 실제 연결 확인
4. **모델 없이 전체 흐름만 보고 싶다면** → "데모 — LLM 없이 전체 흐름 체험" 카드에서 **데모 분석 실행** 클릭 (exchange/ 샘플로 가설 대조까지 바로 확인됨)

## 2. 가설 탭 — 실행 전 예측 적기 (선택)

1. 예시 파일을 보려면 **예시 불러오기** 클릭 — `exchange/hypothesis/sample-hypothesis.json` 내용이 편집창에 채워진다
2. 키 형식: `ch10.{runner}.{condition}.{asr|defense_rate|fpr}` (runner: native/graph/pyrit/garak, condition: controls_off/controls_on), 값은 0~1 숫자
3. 경로를 `10_redteam_framework/exchange/hypothesis/hypothesis-ch10.json`처럼 지정하고 **저장**
4. 이 경로를 측정 탭의 "가설 파일"이나 분석 탭의 "가설 파일"에 넣으면 판정 결과가 비교된다

## 3. 측정 탭 — 실제로 돌리기

1. **케이스 파일** 지정 (기본값은 `exchange/evalset/sample-cases.json`)
2. **러너** 선택 — native는 항상 가능, graph/pyrit/garak은 추가 패키지 필요(설정 탭에서 설치 여부 확인)
3. 필요하면 **QUICK 모드**(동작 확인용, 통계적 결론 아님), **가설 파일** 경로 입력
4. 시작 전에 바로 아래 **"측정 기준"** 카드에서 게이트 기준(ASR≤20%, FPR≤10%, Wilson 95%)을 확인
5. **측정 시작** → 오른쪽 "작업" 표에서 진행 상태 확인, 필요시 취소

측정이 끝나면 `결과 폴더`(기본 `10_redteam_framework/results`)에 타임스탬프가 붙은 Outcome·보고서·대시보드가 쌓이고, 고정 이름 최신본(`ch10-outcomes.json` 등)도 함께 갱신된다.

## 4. 평가 탭 — 평가셋·기준 확인

1. **평가셋 보기**: 파일을 선택하면 케이스 목록(유형·기대 동작·심각도·판정 기준)이 표로 나온다 — 평가셋 선택은 분석·시각화 탭과 공유되는 단일 소스다
2. **측정 기준 보기**: 집계 단위부터 게이트·verdict·가설 대조까지 정리한 M-01~M-12 기준표
3. **평가 대상·지표**: 결과 폴더·Outcome 파일을 지정하고 **지표 계산** — 텍스트로 그룹별 지표가 출력된다

## 5. 분석 탭 — 수치로 판정 보기

1. 상단에 현재 Outcome·평가셋 경로가 표시된다(평가 탭에서 고른 값)
2. **가설 파일**(선택)을 지정하면 가설 대조도 함께 나온다 — 기본값은 exchange 샘플
3. **분석 실행** → 그룹별 방어율/ASR/FPR(k/n)·게이트 verdict·미실행 건수, 가설 대조 표, controls_off→on 개선 전후 표가 표시된다

verdict가 FAIL이어도 당황할 필요 없다 — 표본이 적으면(QUICK 등) Wilson 구간 상한이 기준을 넘어 FAIL이 정상적으로 나올 수 있다. "0건 관측 = 안전"이 아니라는 원칙을 그대로 보여주는 것이다.

## 6. 시각화 탭 — 그림으로 보기

1. 분석 탭에서 고른 Outcome·평가셋·가설이 그대로 쓰인다(상단 "대상" 표시)
2. **차트 미리보기** — 대시보드(차트 5종 + 케이스별 표)를 iframe으로 바로 확인
3. **실행 비교** — 다른 Outcome 파일을 "비교할 Outcome"에 지정하면 두 실행을 나란히 비교(그룹별 방어율 차트 + 가설 대조 + 케이스 표)
4. 대시보드/보고서 HTML/MD는 새 탭 링크로도 열 수 있다

## 7. 인덱스 — 용어 찾기

가나다순 인덱스(ㄱ~ㅎ)를 눌러 바로 이동. 가설·측정·평가·분석·시각화에서 쓰는 모든 용어(그룹·게이트·Wilson 구간·QUICK·카나리 등)가 정리돼 있다. **매뉴얼** 탭 하단에 있다.

## 8. exchange/ 디렉터리 — 파일 주고받기

```
10_redteam_framework/exchange/
├── hypothesis/   가설 JSON
├── evalset/      평가셋 JSON
├── outcomes/     Outcome JSON
└── reports/      보고서·대시보드 산출물
```

각 폴더에 `sample-*.json` 예시가 있다. GUI의 모든 파일 선택 드롭다운은 이 폴더와 `src/data`·`results`를 함께 보여준다. 다른 사람과 가설·평가셋·측정 결과를 주고받을 때 이 폴더에 파일을 넣고 빼면 된다.

## 9. 자주 겪는 문제

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| graph/pyrit/garak이 "없음"으로 표시 | 서버를 가상환경이 아닌 시스템 파이썬으로 실행 | `.venv/bin/python`로 서버 재시작 |
| 측정 기준표·가설 대조가 안 보임 | 브라우저 캐시 | 강력 새로고침(Cmd+Shift+R) — 서버가 `Cache-Control: no-store`를 보내므로 이후엔 자동 갱신 |
| `/api/analyze`에서 verdict가 `—` | 게이트 기준값(max_asr/max_fpr) 미지정 | GUI는 기본 0.2/0.1을 자동으로 넣는다. 직접 API를 부를 때는 `max_asr`·`max_fpr` 쿼리를 추가 |
| garak "리포트를 찾을 수 없음" | 결과 폴더 이동 후 코드가 옛 경로를 봄 | 최신 버전은 `10_redteam_framework/results/garak` 고정 경로를 쓴다(이미 반영됨) |
| 분석했는데 FAIL만 나옴 | 표본이 적어 Wilson 상한이 기준을 넘음(특히 QUICK) | 정상 동작 — 표본을 늘리거나(비-QUICK) 원칙 문서(측정 기준표 하단 안내) 참고 |

## 10. 안전 수칙 요약

- 모델 주소는 기본 localhost만 — 외부 주소는 `REDTEAM_ALLOW_REMOTE=1`(또는 GUI "외부 주소 허용") 명시 필요
- 카나리는 `CANARY-` 접두사만, 평가 URL은 예약 도메인(`example.com`, `.invalid`, `.test` 등)만
- 보고서·대시보드엔 모델 원문 응답·입력 본문·카나리 원문이 들어가지 않는다 — 집계 수치와 케이스 ID만
- `settings.json`에 API 키가 저장될 수 있으니 공개 저장소에 올리지 않는다(`.gitignore` 처리됨)
