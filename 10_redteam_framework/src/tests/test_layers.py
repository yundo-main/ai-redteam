"""계층 규칙 테스트: run → target → service → base 단방향 import 만 허용 (development.md 원칙 3)"""
import re
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
ORDER = {"base": 0, "service": 1, "target": 2, "run": 3}


def _imports(path):
    """파일의 `from X import` / `import X` 최상위 모듈을 뽑는다."""
    mods = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(?:from|import)\s+([a-zA-Z_][\w]*)", line)
        if m and m.group(1) in ORDER:
            mods.add(m.group(1))
    return mods


class TestLayers(unittest.TestCase):
    def test_direction(self):
        problems = []
        for py in SRC.rglob("*.py"):
            if "tests" in py.parts or "__pycache__" in py.parts:
                continue
            own = next((p for p in py.relative_to(SRC).parts if p in ORDER), None)
            if own is None:
                continue
            for dep in _imports(py):
                if ORDER[dep] > ORDER[own]:          # 아래 계층이 위 계층을 import 하면 위반
                    problems.append(f"{py.relative_to(SRC)}: {own} -> {dep}")
        self.assertEqual(problems, [])

    def test_base_has_no_upper_imports(self):
        # base 는 같은 패키지(base.*)끼리만 import 할 수 있다 — run/target/service import 금지
        for py in (SRC / "base").glob("*.py"):
            self.assertFalse(_imports(py) & {"run", "target", "service"}, py.name)


if __name__ == "__main__":
    unittest.main()
