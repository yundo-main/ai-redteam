"""공통 데이터 형식: Case(무엇을 시험하나)와 Outcome(시험해 보니 어땠나) + 안전 검증 (표준 라이브러리만 사용)

readme.md 3장·8장의 형식과 규칙을 코드로 고정한다. 이 모듈이 10 프레임워크가 강제하는 유일한 공통 추상화다.

Case    : id, type, subtype, input, expected("block"|"allow"), criterion, severity, source, scenario_id
          + 선택 params(dict): 러너별 추가 입력(문서, 턴, 마커 등)
Outcome : case_id, runner, condition("controls_off"|"controls_on"), k, n, evidence[], model, seed, started_at
          k = 공격이 통한 횟수. expected=allow(정상) 케이스에서는 k = 잘못 막은(오탐) 횟수로 통일한다.

결과 파일 형식: {"format": "redteam-outcomes/1", "meta": {...}, "outcomes": [...]}
안전 규칙(8장): 입력 안 URL은 예약 도메인만, 카나리 증거는 CANARY- 접두사만, 모델 주소는 localhost 만.
"""
import json
import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

FORMAT = "redteam-outcomes/1"
CONDITIONS = ("controls_off", "controls_on")
SEVERITIES = ("low", "medium", "high")
EXPECTED = ("block", "allow")

# 예약 도메인(10장 ROE): 실제 외부로 나가는 주소를 평가셋에 둘 수 없게 한다
RESERVED_HOSTS = {"example.com", "example.org", "example.net", "localhost"}
RESERVED_TLDS = (".invalid", ".test", ".example", ".localhost")
_URL = re.compile(r"https?://[^\s)\]>\"']+", re.I)
CANARY_PREFIX = "CANARY-"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class CaseError(ValueError):
    pass


@dataclass
class Case:
    id: str
    type: str
    subtype: str
    input: str
    expected: str
    criterion: str
    severity: str
    source: str
    scenario_id: str = ""
    params: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d):
        missing = [k for k in ("id", "type", "subtype", "input", "expected", "criterion", "severity", "source") if k not in d]
        if missing:
            raise CaseError(f"케이스 '{d.get('id', '?')}' 필수 칸 없음: {missing}")
        return cls(**{k: d[k] for k in ("id", "type", "subtype", "input", "expected", "criterion", "severity", "source", "scenario_id", "params") if k in d})


@dataclass
class Outcome:
    case_id: str
    runner: str
    condition: str
    k: int
    n: int
    evidence: list = field(default_factory=list)
    model: str = ""
    seed: int | None = None
    started_at: str = ""

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if v not in (None, "", [])}

    @classmethod
    def from_dict(cls, d):
        for k in ("case_id", "runner", "condition", "k", "n"):
            if k not in d:
                raise CaseError(f"Outcome 필수 칸 없음: {k}")
        o = cls(**{k: d.get(k) for k in ("case_id", "runner", "condition", "k", "n", "evidence", "model", "seed", "started_at")})
        if o.condition not in CONDITIONS:
            raise CaseError(f"{o.case_id}: condition 은 {CONDITIONS} 중 하나")
        if not (0 <= o.k <= o.n) or o.n <= 0:
            raise CaseError(f"{o.case_id}: 0 <= k <= n, n > 0 이어야 한다 (k={o.k}, n={o.n})")
        return o


# ---------------------------------------------------------------------------
# 안전 검증 (readme 8장)
# ---------------------------------------------------------------------------
def _host_ok(host):
    host = (host or "").lower().rstrip(".")
    if host.endswith(RESERVED_TLDS):
        return True
    return any(host == d or host.endswith("." + d) for d in RESERVED_HOSTS)


def check_input_urls(text, where=""):
    """입력 안의 모든 URL 호스트가 예약 도메인인지 확인. 위반 URL 목록을 돌려준다."""
    bad = []
    for m in _URL.finditer(text or ""):
        host = (urlparse(m.group(0)).hostname or "").lower()
        if not _host_ok(host):
            bad.append(m.group(0))
    return bad


def check_canary(text, where=""):
    """카나리로 쓸 문자열이 CANARY- 접두사로 시작하는지. 위반하면 CaseError."""
    if text and not str(text).startswith(CANARY_PREFIX):
        raise CaseError(f"{where}: 카나리는 '{CANARY_PREFIX}' 접두사만 허용한다 (받은 값: {text!r})")


def check_endpoint(url):
    """모델 주소가 localhost 계열인지 확인. 외부 주소는 REDTEAM_ALLOW_REMOTE=1 명시가 있어야 한다."""
    host = (urlparse(url).hostname or "").lower()
    if host in LOCAL_HOSTS:
        return
    if os.environ.get("REDTEAM_ALLOW_REMOTE") == "1":
        return
    raise CaseError(f"모델 주소는 localhost 만 허용한다: {url} (외부 주소는 ROE 위반. 꼭 필요하면 REDTEAM_ALLOW_REMOTE=1 명시)")


def validate_case(c: Case):
    """케이스 하나를 검증한다. 문제 목록(빈 리스트면 정상)을 돌려준다."""
    problems = []
    if c.expected not in EXPECTED:
        problems.append(f"{c.id}: expected 는 {EXPECTED} 중 하나")
    if c.severity not in SEVERITIES:
        problems.append(f"{c.id}: severity 는 {SEVERITIES} 중 하나")
    bad = check_input_urls(c.input, c.id)
    if bad:
        problems.append(f"{c.id}: 예약 도메인이 아닌 URL {bad}")
    for key in ("canary", "marker"):
        v = c.params.get(key)
        if v is not None:
            try:
                check_canary(v, f"{c.id}.params.{key}")
            except CaseError as e:
                problems.append(str(e))
    return problems


def load_cases(path):
    """케이스 JSON({"cases": [...]})을 읽고 검증한다."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)["cases"]
    cases, problems = [], []
    for d in raw:
        try:
            c = Case.from_dict(d)
            problems += validate_case(c)
            cases.append(c)
        except (CaseError, KeyError, TypeError) as e:
            problems.append(str(e))
    if problems:
        raise CaseError("케이스 파일 오류:\n  " + "\n  ".join(problems))
    if not any(c.expected == "block" for c in cases):
        raise CaseError("공격 케이스(expected=block)가 없다")
    if not any(c.expected == "allow" for c in cases):
        raise CaseError("정상 케이스(expected=allow)가 없다 — 다 막는 설정이 최고로 평가된다")
    return cases


def load_outcomes(path):
    """Outcome 파일({"format","meta","outcomes"})을 읽고 검증한다."""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if doc.get("format") != FORMAT:
        raise CaseError(f"{path}: 형식이 {FORMAT} 이 아니다 (format={doc.get('format')!r})")
    outcomes = [Outcome.from_dict(d) for d in doc.get("outcomes", [])]
    return doc.get("meta", {}), outcomes


def save_outcomes(path, outcomes, meta=None):
    """Outcome 목록을 형식 JSON으로 저장한다(원자적 쓰기)."""
    import datetime
    doc = {"format": FORMAT,
           "meta": {"started_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), **(meta or {})},
           "outcomes": [o.to_dict() for o in outcomes]}
    from base import hypothesis_log as hyp
    hyp.safe_write(path, json.dumps(doc, ensure_ascii=False, indent=2))
