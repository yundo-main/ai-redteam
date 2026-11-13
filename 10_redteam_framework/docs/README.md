# 개발 문서

10_redteam_framework의 문서 모음. 사용자용 안내는 [../readme.md](../readme.md)에 있다.

## 사용자 문서 (`docs/`)

| 문서 | 내용 |
| --- | --- |
| [user-manual.md](user-manual.md) | GUI 사용 매뉴얼 — 설정부터 가설·측정·평가·분석·시각화 탭까지 순서대로 안내, 자주 겪는 문제 |
| [framework-flow.svg](framework-flow.svg) | 프레임워크 동작 흐름도 — GUI 탭 순서, Case→Outcome→지표→보고서 파이프라인, run→target→service→base 계층 규칙, 안전 경계, exchange 교환 구조 |
| [measurement-criteria.svg](measurement-criteria.svg) | 측정 기준 분석도 — Outcome k/n → (runner, condition) 집계 → 지표 4종 → Wilson 95% 구간 → ASR≤20%·FPR≤10% 게이트 → PASS/FAIL/측정 안 됨 흐름도 |
| [server-run.svg](server-run.svg) | 서버 실행 흐름도 — 사전 준비(Ollama·.venv) → serve 명령 → 브라우저 접속 → 끄기·문제 해결 |

## 개발 문서 (`../devdocs/`)

| 문서 | 내용 |
| --- | --- |
| [decisions.md](../devdocs/decisions.md) | 0단계 결정 기록 — 열린 질문 9건 + 10단계 결정 3건(결정·이유·버린 선택지) |
| [architecture.md](../devdocs/architecture.md) | 계층 규칙(run→target→service→base)과 안전 규칙의 코드 강제 위치 — 상시 참조용 |
| [development.md](../devdocs/development.md) | 단계별 개발 정의 — 0~10단계 할 일·산출물·완료 기준, 회귀 기준 숫자, 진행 원칙, 단계별 위험 |
| [changelog.md](../devdocs/changelog.md) | 개발 로그 — 단계 구현과 GUI 고도화 변경 이력 |
