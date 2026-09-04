import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "scripts" / "with-project-env"
SETUP_WIZARD = REPO_ROOT / "scripts" / "setup-project-env"
ENV_KEY = "DEEPSEEK_API_KEY"


def _copy_launcher(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    launcher = scripts / LAUNCHER.name
    shutil.copyfile(LAUNCHER, launcher)
    launcher.chmod(0o755)
    return repo, launcher


def _write_env(repo: Path, contents: str, mode: int = 0o600) -> Path:
    env_path = repo / ".env"
    env_path.write_text(contents, encoding="utf-8")
    env_path.chmod(mode)
    return env_path


def _run_launcher(launcher: Path, *command: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop(ENV_KEY, None)
    return subprocess.run(
        [str(launcher), *command],
        cwd=launcher.parents[1],
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )


def test_launcher_injects_key_only_through_child_environment(tmp_path: Path) -> None:
    repo, launcher = _copy_launcher(tmp_path)
    secret = "".join(("fixture", "-", "credential", "-", "value"))
    _write_env(repo, f"# local only\n{ENV_KEY}={secret}\n")
    child_program = (
        "import os,sys; "
        "expected=''.join(('fixture','-','credential','-','value')); "
        f"assert os.environ[{ENV_KEY!r}] == expected; "
        "assert sys.argv[1:] == ['visible-argument']; "
        "print('child-ok')"
    )

    completed = _run_launcher(
        launcher,
        "--",
        sys.executable,
        "-c",
        child_program,
        "visible-argument",
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "child-ok\n"
    assert completed.stderr == ""
    assert secret not in "\0".join(completed.args)
    assert secret not in completed.stdout + completed.stderr
    assert sorted(path.name for path in repo.iterdir()) == [".env", "scripts"]


def test_launcher_replaces_an_inherited_key_with_project_value(tmp_path: Path) -> None:
    repo, launcher = _copy_launcher(tmp_path)
    project_value = "project-value"
    inherited_value = "inherited-value"
    _write_env(repo, f"{ENV_KEY}={project_value}\n")
    environment = os.environ.copy()
    environment[ENV_KEY] = inherited_value

    completed = subprocess.run(
        [
            str(launcher),
            sys.executable,
            "-c",
            f"import os; assert os.environ[{ENV_KEY!r}] == 'project-value'",
        ],
        cwd=repo,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert inherited_value not in completed.stdout + completed.stderr
    assert project_value not in completed.stdout + completed.stderr


def test_launcher_requires_a_command_without_reading_the_env_file(
    tmp_path: Path,
) -> None:
    _, launcher = _copy_launcher(tmp_path)

    completed = _run_launcher(launcher)

    assert completed.returncode == 2
    assert completed.stderr == (
        "usage: scripts/with-project-env [--] COMMAND [ARG ...]\n"
    )


def test_launcher_reports_a_missing_project_env_without_exposing_parent_key(
    tmp_path: Path,
) -> None:
    repo, launcher = _copy_launcher(tmp_path)
    inherited_value = "parent-only-value"
    environment = os.environ.copy()
    environment[ENV_KEY] = inherited_value

    completed = subprocess.run(
        [str(launcher), sys.executable, "-c", "pass"],
        cwd=repo,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 2
    assert "project .env is missing" in completed.stderr
    assert inherited_value not in completed.stdout + completed.stderr


def test_launcher_requires_exact_owner_only_permissions(tmp_path: Path) -> None:
    repo, launcher = _copy_launcher(tmp_path)
    secret = "permission-fixture"
    _write_env(repo, f"{ENV_KEY}={secret}\n", mode=0o644)

    completed = _run_launcher(launcher, sys.executable, "-c", "pass")

    assert completed.returncode == 2
    assert "must have mode 600; observed 644" in completed.stderr
    assert secret not in completed.stderr


@pytest.mark.parametrize(
    ("contents", "expected_error"),
    [
        ("", f"does not define {ENV_KEY}"),
        (f"{ENV_KEY}=\n", f"contains an empty {ENV_KEY}"),
        (f"{ENV_KEY}=first\n{ENV_KEY}=second\n", f"repeats {ENV_KEY}"),
        ("UNSUPPORTED=value\n", "unsupported entry at line 1"),
        (f"export {ENV_KEY}=value\n", "unsupported entry at line 1"),
        (f"{ENV_KEY}='quoted'\n", "without quotes"),
        (f"{ENV_KEY}=has space\n", f"contains whitespace in {ENV_KEY}"),
        (f"{ENV_KEY}=value\r\n", "unsupported control characters"),
    ],
)
def test_launcher_rejects_ambiguous_or_unsafe_env_syntax(
    tmp_path: Path, contents: str, expected_error: str
) -> None:
    repo, launcher = _copy_launcher(tmp_path)
    _write_env(repo, contents)

    completed = _run_launcher(launcher, sys.executable, "-c", "pass")

    assert completed.returncode == 2
    assert expected_error in completed.stderr
    if contents:
        assert contents not in completed.stderr


def test_launcher_rejects_a_symlinked_env_file(tmp_path: Path) -> None:
    repo, launcher = _copy_launcher(tmp_path)
    target = tmp_path / "credential-target"
    target.write_text(f"{ENV_KEY}=symlink-fixture\n", encoding="utf-8")
    target.chmod(0o600)
    (repo / ".env").symlink_to(target)

    completed = _run_launcher(launcher, sys.executable, "-c", "pass")

    assert completed.returncode == 2
    assert "must not be a symbolic link" in completed.stderr
    assert "symlink-fixture" not in completed.stderr


def test_project_env_artifacts_have_safe_repository_contract() -> None:
    example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    wizard = SETUP_WIZARD.read_text(encoding="utf-8")
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", ".env"],
        cwd=REPO_ROOT,
        check=False,
    )

    assert example.endswith(f"{ENV_KEY}=\n")
    assert ignored.returncode == 0
    assert stat.S_IMODE(LAUNCHER.stat().st_mode) == 0o755
    assert stat.S_IMODE(SETUP_WIZARD.stat().st_mode) == 0o755
    assert "Generated by the /wizard skill." in wizard
    assert f'ask_secret {ENV_KEY} "Paste the API key:' in wizard
    assert f'write_env {ENV_KEY} "${ENV_KEY}"' in wizard
    assert 'chmod 600 "$ENV_FILE"' in wizard
    assert '[[ -f "$ENV_FILE" && ! -O "$ENV_FILE" ]]' in wizard
    assert f"ask {ENV_KEY} " not in wizard
