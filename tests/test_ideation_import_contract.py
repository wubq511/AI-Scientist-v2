import ast
from dataclasses import dataclass
import importlib.util
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "ai_scientist"
ENTRY_MODULE = "ai_scientist.perform_ideation_temp_free"


@dataclass(frozen=True)
class ImportClosure:
    internal_modules: frozenset[str]
    third_party_top_levels: frozenset[str]
    unresolved_internal_modules: frozenset[str]
    dynamic_import_sites: frozenset[str]


EXPECTED_IMPORT_CLOSURE = ImportClosure(
    internal_modules=frozenset(
        {
            "ai_scientist",
            "ai_scientist.ideation",
            "ai_scientist.ideation.admission",
            "ai_scientist.ideation.canonical",
            "ai_scientist.ideation.contract",
            "ai_scientist.ideation.controller",
            "ai_scientist.ideation.deepseek",
            "ai_scientist.ideation.errors",
            "ai_scientist.ideation.evidence",
            "ai_scientist.ideation.pricing",
            "ai_scientist.ideation.resume",
            "ai_scientist.ideation.retrieval",
            "ai_scientist.ideation.run_store",
            "ai_scientist.ideation.schema",
            "ai_scientist.llm",
            "ai_scientist.perform_ideation_temp_free",
            "ai_scientist.tools",
            "ai_scientist.tools.base_tool",
            "ai_scientist.tools.semantic_scholar",
            "ai_scientist.utils.token_tracker",
        }
    ),
    third_party_top_levels=frozenset(
        {
            "anthropic",
            "backoff",
            "openai",
            "requests",
        }
    ),
    unresolved_internal_modules=frozenset(),
    dynamic_import_sites=frozenset(),
)


def _source_path(module_name: str) -> Path | None:
    if module_name == "ai_scientist":
        return PACKAGE_ROOT / "__init__.py"
    if not module_name.startswith("ai_scientist."):
        return None

    relative_parts = module_name.split(".")[1:]
    module_path = PACKAGE_ROOT.joinpath(*relative_parts).with_suffix(".py")
    if module_path.is_file():
        return module_path

    package_path = PACKAGE_ROOT.joinpath(*relative_parts, "__init__.py")
    if package_path.is_file():
        return package_path
    return None


def _package_initializers(module_name: str) -> set[str]:
    initializers = set()
    parts = module_name.split(".")
    for end in range(1, len(parts)):
        candidate = ".".join(parts[:end])
        path = _source_path(candidate)
        if path is not None and path.name == "__init__.py":
            initializers.add(candidate)
    return initializers


def _absolute_from_module(
    current_module: str, current_path: Path, imported_module: str | None, level: int
) -> str:
    if level == 0:
        return imported_module or ""

    package = (
        current_module
        if current_path.name == "__init__.py"
        else current_module.rpartition(".")[0]
    )
    relative_name = "." * level + (imported_module or "")
    return importlib.util.resolve_name(relative_name, package)


def _discover_import_closure() -> ImportClosure:
    pending: list[str] = []
    internal_modules: set[str] = set()
    scanned_internal_modules: set[str] = set()
    third_party_top_levels: set[str] = set()
    unresolved_internal_modules: set[str] = set()
    dynamic_import_sites: set[str] = set()

    def register_internal(module_name: str) -> None:
        for package_name in _package_initializers(module_name):
            if package_name not in internal_modules:
                internal_modules.add(package_name)
                pending.append(package_name)
        if _source_path(module_name) is None:
            unresolved_internal_modules.add(module_name)
        elif module_name not in internal_modules:
            internal_modules.add(module_name)
            pending.append(module_name)

    def register_import(module_name: str) -> None:
        if not module_name:
            return
        top_level = module_name.partition(".")[0]
        if top_level == "ai_scientist":
            register_internal(module_name)
            return
        if top_level not in sys.stdlib_module_names:
            third_party_top_levels.add(top_level)

    register_internal(ENTRY_MODULE)
    while pending:
        module_name = pending.pop()
        if module_name in scanned_internal_modules:
            continue
        module_path = _source_path(module_name)
        if module_path is None:
            unresolved_internal_modules.add(module_name)
            continue

        scanned_internal_modules.add(module_name)
        tree = ast.parse(
            module_path.read_text(encoding="utf-8"), filename=str(module_path)
        )
        importlib_aliases = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
            if alias.name == "importlib"
        }
        import_module_aliases = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "importlib"
            for alias in node.names
            if alias.name == "import_module"
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    register_import(alias.name)
            elif isinstance(node, ast.ImportFrom):
                imported_module = _absolute_from_module(
                    module_name, module_path, node.module, node.level
                )
                register_import(imported_module)
                for alias in node.names:
                    candidate = f"{imported_module}.{alias.name}"
                    if _source_path(candidate) is not None:
                        register_import(candidate)
            elif isinstance(node, ast.Call):
                function = node.func
                is_dynamic_import = (
                    (isinstance(function, ast.Name) and function.id == "__import__")
                    or (
                        isinstance(function, ast.Attribute)
                        and isinstance(function.value, ast.Name)
                        and function.value.id in importlib_aliases
                        and function.attr == "import_module"
                    )
                    or (
                        isinstance(function, ast.Name)
                        and function.id in import_module_aliases
                    )
                )
                if is_dynamic_import:
                    relative_path = module_path.relative_to(REPO_ROOT)
                    dynamic_import_sites.add(f"{relative_path}:{node.lineno}")

    return ImportClosure(
        internal_modules=frozenset(internal_modules),
        third_party_top_levels=frozenset(third_party_top_levels),
        unresolved_internal_modules=frozenset(unresolved_internal_modules),
        dynamic_import_sites=frozenset(dynamic_import_sites),
    )


def test_ideation_entry_import_closure_is_declared() -> None:
    assert _discover_import_closure() == EXPECTED_IMPORT_CLOSURE
