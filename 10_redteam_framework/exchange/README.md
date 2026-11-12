# exchange/ — 임포트·익스포트 디렉터리

가설·평가셋·측정 결과·보고서 문서를 주고받는 작업 공간.
하위 폴더별 용도가 정해져 있고, 파일을 넣고 빼는 것만으로 임포트·익스포트가 된다.

## 구조

| 폴더 | 넣는 것 | 용도 |
| --- | --- | --- |
| `hypothesis/` | 가설 JSON (`ch10.{runner}.{condition}.{metric}` 키) | GUI 가설 탭·측정 작업의 `hypothesis` 입력으로 사용 |
| `evalset/` | 평가셋 JSON (케이스 목록) | GUI 평가 탭 평가셋 선택, `--cases` 인자 |
| `outcomes/` | Outcome JSON (`redteam-outcomes/1`) | `redteam analyze`·`report`·`viz`·`compare` 입력 |
| `reports/` | 보고서·대시보드 산출물 (md/html/svg) | 생성 결과를 모아 두는 곳 |

각 폴더에 `sample-*.json` 예시 파일이 들어 있다 — `src/data/`의 예시를 복사한 것으로,
GUI 경로 입력에 `10_redteam_framework/exchange/<폴더>/sample-*.json`을 넣으면 바로 쓸 수 있다.

## 사용 예

```bash
# 가설 파일을 작업 폴더로 복사해 GUI에서 선택
cp exchange/hypothesis/my-hypothesis.json results/

# Outcome 결과를 보관 폴더로 이동
mv results/ch10-outcomes-20250101T120000.json exchange/outcomes/

# 보고서를 산출물 폴더에 저장
python src/run/cli.py report exchange/outcomes/ch10-outcomes-....json \
  --cases exchange/evalset/cases.example.json -o exchange/reports/report.md
```

## 주의

- `settings.json`(API 키 포함 가능)은 이 폴더에 두지 않는다 — 저장소 루트에 유지, gitignore 처리됨.
- Outcome·평가셋·가설 파일에는 모델 원문·카나리 원문이 들어가지 않는 것이 원칙이다.
