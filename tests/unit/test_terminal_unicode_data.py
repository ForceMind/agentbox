from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "generate-terminal-unicode.py"
GENERATED = ROOT / "apps" / "web" / "src" / "features" / "workspace" / "terminalUnicodeWidthData.ts"


def _check(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--output", str(path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_terminal_unicode_canonical_data_recomputes_offline() -> None:
    result = _check(GENERATED)
    assert result.returncode == 0, result.stderr


def test_terminal_unicode_check_rejects_stale_canonical_digest(
    tmp_path: Path,
) -> None:
    stale = tmp_path / "terminalUnicodeWidthData.ts"
    data = GENERATED.read_text(encoding="utf-8")
    stale.write_text(
        re.sub(
            r"(TERMINAL_UNICODE_RANGE_SHA256\s*=\s*\n\s*')[a-f0-9]{64}",
            rf"\g<1>{'0' * 64}",
            data,
            count=1,
        ),
        encoding="utf-8",
    )
    result = _check(stale)
    assert result.returncode != 0
    assert "canonical range digest does not match" in result.stderr
