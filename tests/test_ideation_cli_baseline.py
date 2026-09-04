import hashlib
import os
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY_SCRIPT = REPO_ROOT / "ai_scientist" / "perform_ideation_temp_free.py"
BASELINE_HELP_SHA256 = (
    "50fef55ef59bf21cb13809e7934f3ac71dfb21cb27a8649e665ea3c6a572b7f0"
)


def test_ideation_cli_help_matches_compatible_baseline() -> None:
    environment = os.environ.copy()
    environment["COLUMNS"] = "80"
    environment["S2_API_KEY"] = "baseline-smoke"

    completed = subprocess.run(
        [sys.executable, str(ENTRY_SCRIPT), "--help"],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        check=False,
    )

    observed = (
        completed.returncode,
        completed.stderr,
        hashlib.sha256(completed.stdout).hexdigest(),
    )
    expected = (0, b"", BASELINE_HELP_SHA256)
    assert observed == expected, completed.stdout.decode("utf-8", errors="replace")
