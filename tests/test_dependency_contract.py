from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[1]
EXACT_REQUIREMENT = re.compile(
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[A-Za-z0-9][A-Za-z0-9._+-]*)"
)

# The ideation-only runtime import closure is pure standard library (ticket 13):
# the canonical runtime contract intentionally pins no packages.
EXPECTED_RUNTIME_PACKAGES = frozenset()
EXPECTED_DEVELOPMENT_PACKAGES = frozenset(
    {
        "black",
        "httpx",
        "pytest",
    }
)
EXPECTED_RETAINED_UPSTREAM_PACKAGES = frozenset(
    {
        "anthropic",
        "backoff",
        "boto3",
        "botocore",
        "coolname",
        "dataclasses-json",
        "datasets",
        "funcy",
        "genson",
        "humanize",
        "jsonschema",
        "matplotlib",
        "numpy",
        "omegaconf",
        "openai",
        "pymupdf4llm",
        "pypdf",
        "python-igraph",
        "requests",
        "rich",
        "seaborn",
        "shutup",
        "tqdm",
        "transformers",
        "wandb",
    }
)


def _canonical_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _read_exact_requirements(filename: str) -> dict[str, str]:
    requirements = {}
    for line_number, raw_line in enumerate(
        (REPO_ROOT / filename).read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = EXACT_REQUIREMENT.fullmatch(line)
        assert match is not None, f"{filename}:{line_number} is not exactly pinned"
        package_name = _canonical_package_name(match.group("name"))
        assert package_name not in requirements, f"duplicate package: {package_name}"
        requirements[package_name] = match.group("version")
    return requirements


def test_dependency_roles_are_precisely_pinned_and_disjoint() -> None:
    observed_roles = {
        "runtime": frozenset(_read_exact_requirements("requirements.txt")),
        "development": frozenset(_read_exact_requirements("requirements-dev.txt")),
        "retained_upstream": frozenset(
            _read_exact_requirements("requirements-upstream.txt")
        ),
    }
    expected_roles = {
        "runtime": EXPECTED_RUNTIME_PACKAGES,
        "development": EXPECTED_DEVELOPMENT_PACKAGES,
        "retained_upstream": EXPECTED_RETAINED_UPSTREAM_PACKAGES,
    }

    all_packages = [
        package for packages in observed_roles.values() for package in packages
    ]
    roles_are_disjoint = len(all_packages) == len(set(all_packages))
    assert (observed_roles, roles_are_disjoint) == (expected_roles, True)
