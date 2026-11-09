# 2일차 src

2일차는 설계 일차라 실습 코드가 없다. 3일차부터 쓰는 시나리오 워크시트(JSON) 형식만 여기서 미리 적어 둔다. 앞 일차를 놓친 학생도 이 형식을 알면 3일차 이후를 따라갈 수 있다.

워크시트는 아래 항목을 가진 JSON 객체이다(문서 6장의 항목과 같다).

| 키 | 내용 |
| --- | --- |
| `id`, `name` | 시나리오 ID(예: `TA-01`)와 이름 |
| `assets` | 보호 대상 자산 |
| `attacker_model` | `knowledge`, `access`, `resources` |
| `objective`, `preconditions` | 공격 목표와 전제 |
| `vector`, `steps` | 공격 벡터와 단계 |
| `success_condition` | `type`, `markers`, `evidence` (관측 가능한 성공 조건) |
| `impact` | `severity`(low/medium/high 등)와 설명 |
| `controls` | 적용할 통제 |
| `roe` | `sandbox`, `dummy_data`, `allowed_domains` 등 교전 규칙 |
