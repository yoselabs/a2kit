"""Static (AST-only) lint rules: A2K001..A2K011.

Each rule yields `LintMessage`s. No imports are executed during analysis.
Cross-tool / cross-file rules walk multiple files in `run_static_rules`.
"""

from __future__ import annotations

import ast
import difflib
from pathlib import Path
from typing import TYPE_CHECKING

from a2kit.lint._ast_helpers import (
    connection_info_subclasses,
    decorator_kwargs,
    function_has_param,
    is_a2kit_tool_decorator,
    is_tool_function,
    key_fields_value,
    local_pydantic_classes,
)
from a2kit.lint._common import LintMessage, parse_noqa, suppressed

if TYPE_CHECKING:
    from collections.abc import Iterable

A2K001 = "A2K001"
A2K002 = "A2K002"
A2K003 = "A2K003"
A2K004 = "A2K004"
A2K005 = "A2K005"
A2K006 = "A2K006"
A2K008 = "A2K008"
A2K009 = "A2K009"
A2K010 = "A2K010"
A2K011 = "A2K011"

ALL_RULES = (A2K001, A2K002, A2K003, A2K004, A2K005, A2K006, A2K008, A2K009, A2K010, A2K011)

_BUILTIN_CAPS = {"read", "write", "destructive", "expensive", "pii", "external"}
_FIXTURE_PATH_TOKENS = ("tests/", "tests\\", "examples/", "examples\\")


def _is_fixture_path(filename: str) -> bool:
    return any(token in filename for token in _FIXTURE_PATH_TOKENS)


def _msg(rule: str, filename: str, node: ast.AST, text: str) -> LintMessage:
    return LintMessage(
        rule=rule,
        filename=filename,
        line=getattr(node, "lineno", 1),
        col=getattr(node, "col_offset", 0),
        message=text,
    )


def rule_a2k001(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K001 — `@a2kit.tool(connection_param='X')` requires param X on the function."""
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not is_a2kit_tool_decorator(dec):
                continue
            cp = decorator_kwargs(dec).get("connection_param")
            if not isinstance(cp, ast.Constant) or not isinstance(cp.value, str):
                continue
            if not function_has_param(node, cp.value) and not suppressed(noqa, A2K001, node.lineno):
                yield _msg(A2K001, filename, node, f"function {node.name!r} missing connection_param {cp.value!r}")


def rule_a2k002(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K002 — Tools must not declare `-> str` return."""
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not is_tool_function(node) or node.returns is None:
            continue
        ret = node.returns
        is_str = (isinstance(ret, ast.Name) and ret.id == "str") or (isinstance(ret, ast.Constant) and ret.value == "str")
        if is_str and not suppressed(noqa, A2K002, node.lineno):
            yield _msg(A2K002, filename, node, f"tool {node.name!r} declares `-> str`; FastMCP double-serialises")


def rule_a2k003(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K003 — Tools should not return locally-defined Pydantic models."""
    if _is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    locals_ = local_pydantic_classes(tree)
    if not locals_:
        return
    for node in ast.walk(tree):
        if not is_tool_function(node) or node.returns is None:
            continue
        ret_name = node.returns.id if isinstance(node.returns, ast.Name) else None
        if ret_name in locals_ and not suppressed(noqa, A2K003, node.lineno):
            yield _msg(A2K003, filename, node, f"tool {node.name!r} returns module-local Pydantic model {ret_name!r}")


def rule_a2k004(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K004 — Tools with `connection` param should reference the canonical helper."""
    if _is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    if "connection_param_doc" in source:
        return
    for node in ast.walk(tree):
        if not is_tool_function(node) or not function_has_param(node, "connection"):
            continue
        if suppressed(noqa, A2K004, node.lineno):
            continue
        yield _msg(
            A2K004,
            filename,
            node,
            f"tool {node.name!r} has `connection` param but no a2kit.docs.connection_param_doc reference",
        )


# --------------------------------------------------------------------------- #
# A2K005 — KEY_FIELDS shape + multi-field tool param type compat (v0.4).
# --------------------------------------------------------------------------- #


def _check_key_fields_value(cls: ast.ClassDef, kf: ast.expr, filename: str, noqa: dict) -> Iterable[LintMessage]:
    if suppressed(noqa, A2K005, cls.lineno):
        return
    if not isinstance(kf, ast.Tuple):
        yield _msg(A2K005, filename, cls, f"{cls.name}.KEY_FIELDS must be a tuple of strings")
        return
    for elt in kf.elts:
        if not isinstance(elt, ast.Constant) or not isinstance(elt.value, str):
            yield _msg(A2K005, filename, cls, f"{cls.name}.KEY_FIELDS contains non-string element")
            continue
        v = elt.value
        if not v.isidentifier():
            yield _msg(A2K005, filename, cls, f"{cls.name}.KEY_FIELDS element {v!r} is not a valid identifier")
        elif v != v.lower():
            yield _msg(A2K005, filename, cls, f"{cls.name}.KEY_FIELDS element {v!r} should be lowercase")


def _store_var_to_arity(tree: ast.AST) -> dict[str, int]:
    """Best-effort: map module-local variable name → arity of its store's KEY_FIELDS.

    Recognises:
        store = ConnectionStore(config_dir, WidgetConn)
        store: ConnectionStore[WidgetConn] = ConnectionStore(config_dir, WidgetConn)
    where `WidgetConn` is a top-level `ConnectionInfo` subclass with a literal
    `KEY_FIELDS = (...)` assignment in this same module.
    """
    arity_by_class: dict[str, int] = {}
    for cls in connection_info_subclasses(tree):
        kf = key_fields_value(cls)
        if isinstance(kf, ast.Tuple):
            arity_by_class[cls.name] = len(kf.elts)

    if not arity_by_class or not isinstance(tree, ast.Module):
        return {}

    out: dict[str, int] = {}
    for stmt in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(stmt, ast.Assign):
            targets = list(stmt.targets)
            value = stmt.value
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            targets = [stmt.target]
            value = stmt.value
        else:
            continue
        if not isinstance(value, ast.Call):
            continue
        callee = value.func
        callee_name = callee.id if isinstance(callee, ast.Name) else (callee.attr if isinstance(callee, ast.Attribute) else None)
        if callee_name != "ConnectionStore":
            continue
        if not value.args:  # pragma: no cover — ConnectionStore() always takes positional args
            continue
        cls_arg = value.args[-1]
        cls_name = cls_arg.id if isinstance(cls_arg, ast.Name) else None
        if cls_name is None or cls_name not in arity_by_class:  # pragma: no cover — alt forms
            continue
        for tgt in targets:
            if isinstance(tgt, ast.Name):  # pragma: no branch — non-Name targets fall through
                out[tgt.id] = arity_by_class[cls_name]
    return out


def _annotation_acceptable_for_arity(anno: ast.expr | None, arity: int) -> bool | None:
    """Return True/False, or None if the annotation is unresolvable / opaque.

    Acceptable for arity 1: `str`.
    Acceptable for arity > 1: `tuple[...]`, BaseModel-named types, `dict[...]`.
    """
    if anno is None:
        return None
    if arity == 1:
        # `str` is the canonical single-field shape.
        if isinstance(anno, ast.Name) and anno.id == "str":
            return True
        # Anything else (tuple, model, dict) is also acceptable; we only flag
        # the known-bad case (`str` for arity > 1).
        return True
    # arity > 1
    if isinstance(anno, ast.Name):
        if anno.id == "str":
            return False
        # Bare-name model class (e.g. WidgetKey) — assume acceptable.
        return True
    if isinstance(anno, ast.Subscript):
        base = anno.value
        base_name = base.id if isinstance(base, ast.Name) else (base.attr if isinstance(base, ast.Attribute) else None)
        if base_name in {"tuple", "Tuple", "dict", "Dict"}:
            return True
        return True  # pragma: no cover — other Subscript bases also accepted
    return None  # pragma: no cover — opaque annotation


def _scan_a2k005_tool_calls(tree: ast.AST, filename: str, source: str, store_arity: dict[str, int]) -> Iterable[LintMessage]:
    """Walk @a2kit.tool decorations for connection_param arity mismatches."""
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not is_a2kit_tool_decorator(dec):
                continue
            kw = decorator_kwargs(dec)
            store_arg = kw.get("store")
            cp = kw.get("connection_param")
            if not isinstance(store_arg, ast.Name) or not isinstance(cp, ast.Constant) or not isinstance(cp.value, str):
                continue
            arity = store_arity.get(store_arg.id)
            if arity is None:
                # Unresolvable store — emit advisory only (no automatic noqa).
                if not suppressed(noqa, A2K005, node.lineno):
                    yield _msg(
                        A2K005,
                        filename,
                        node,
                        f"could not resolve store {store_arg.id!r}; check `{cp.value}` arity manually",
                    )
                continue
            param_anno = _find_param_annotation(node, cp.value)
            verdict = _annotation_acceptable_for_arity(param_anno, arity)
            if verdict is False and not suppressed(noqa, A2K005, node.lineno):
                yield _msg(
                    A2K005,
                    filename,
                    node,
                    f"tool {node.name!r}: {cp.value}: str is insufficient for KEY_FIELDS arity {arity}; "
                    "use tuple[str, ...], typed key model, or dict[str, str]",
                )


def _find_param_annotation(fn: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> ast.expr | None:
    args = list(fn.args.args) + list(fn.args.kwonlyargs) + list(fn.args.posonlyargs)
    for a in args:
        if a.arg == name:
            return a.annotation
    return None  # pragma: no cover — A2K001 catches the missing-param case


def rule_a2k005(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K005 — KEY_FIELDS shape (tuple of lowercase identifiers) + multi-field
    tool-param type compat (v0.4).
    """
    noqa = parse_noqa(source)
    for cls in connection_info_subclasses(tree):
        kf = key_fields_value(cls)
        if kf is None:
            continue
        yield from _check_key_fields_value(cls, kf, filename, noqa)
    if _is_fixture_path(filename):
        return
    store_arity = _store_var_to_arity(tree)
    yield from _scan_a2k005_tool_calls(tree, filename, source, store_arity)


def _collect_param_descriptions(tree: ast.AST) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not is_tool_function(node):
            continue
        doc = ast.get_docstring(node) or ""
        for raw in doc.splitlines():
            line = raw.strip()
            if ":" not in line:
                continue
            name, _, text = line.partition(":")
            name = name.strip()
            text = text.strip()
            if not name.isidentifier() or len(text) < 20:
                continue
            out.setdefault(name, []).append(text)
    return out


def _rule_a2k006_cross(per_file: dict[str, dict[str, list[str]]]) -> Iterable[LintMessage]:
    flat: dict[tuple[str, str], list[str]] = {}
    for filename, mapping in per_file.items():
        for name, texts in mapping.items():
            for t in texts:
                flat.setdefault((name, t), []).append(filename)
    for (name, _t), files in flat.items():
        if len(files) >= 3:
            yield LintMessage(
                rule=A2K006,
                filename=files[0],
                line=1,
                col=0,
                message=(f"param {name!r} has the same description in {len(files)} tools; consider a2kit.docs.register_param_doc"),
            )


def rule_a2k009(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K009 — Raw built-in capability string (`'write'` instead of `Cap.WRITE`)."""
    if _is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "capabilities":
                continue
            for raw in _iter_string_literals(kw.value):
                if raw.value in _BUILTIN_CAPS and not suppressed(noqa, A2K009, raw.lineno):
                    suggestion = f"Cap.{raw.value.upper()}"
                    yield _msg(
                        A2K009,
                        filename,
                        raw,
                        f"raw built-in capability string {raw.value!r}; prefer {suggestion}",
                    )


def rule_a2k011(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """A2K011 — advisory: tool returns raw `dict`/`Mapping` instead of a Pydantic model.

    Skipped under tests/ and examples/ (intentional fixtures).
    """
    if _is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not is_tool_function(node) or node.returns is None:
            continue
        ret = node.returns
        is_raw = (isinstance(ret, ast.Name) and ret.id in {"dict", "Dict", "Mapping"}) or (
            isinstance(ret, ast.Subscript) and isinstance(ret.value, ast.Name) and ret.value.id in {"dict", "Dict", "Mapping"}
        )
        if is_raw and not suppressed(noqa, A2K011, node.lineno):
            yield _msg(
                A2K011,
                filename,
                node,
                f"tool {node.name!r} returns raw dict/Mapping; prefer a Pydantic BaseModel for richer schema snapshots",
            )


def _iter_string_literals(node: ast.expr) -> Iterable[ast.Constant]:
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                yield elt


def _collect_router_names(tree: ast.AST) -> set[str]:
    """Pull names from `Router(name='...')` calls and class-level `name = '...'` assignments."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    out.add(kw.value.value)
        if isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, ast.Assign):
                    for tgt in stmt.targets:
                        if (
                            isinstance(tgt, ast.Name)
                            and tgt.id == "name"
                            and isinstance(stmt.value, ast.Constant)
                            and isinstance(stmt.value.value, str)
                        ):
                            out.add(stmt.value.value)
    return out


def _collect_tool_names(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            for kw in dec.keywords:
                if kw.arg == "tool_name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    out.add(kw.value.value)
                    break
            out.add(node.name)
            break
    return out


def _rule_a2k008_cross(per_file: dict[str, tuple[set[str], set[str]]]) -> Iterable[LintMessage]:
    all_routers: set[str] = set()
    all_tools: set[str] = set()
    first_seen: dict[str, str] = {}
    for filename, (routers, tools) in per_file.items():
        for r in routers:
            first_seen.setdefault(r, filename)
        for t in tools:
            first_seen.setdefault(t, filename)
        all_routers.update(routers)
        all_tools.update(tools)
    collisions = (all_routers & all_tools) | (all_routers & _BUILTIN_CAPS) | (all_tools & _BUILTIN_CAPS)
    for name in sorted(collisions):
        filename = first_seen.get(name, "<unknown>")
        yield LintMessage(
            rule=A2K008,
            filename=filename,
            line=1,
            col=0,
            message=f"name {name!r} collides across router/tool/capability namespaces",
        )


# --------------------------------------------------------------------------- #
# A2K010 — unknown atom in `--select` strings (project-wide).
# --------------------------------------------------------------------------- #


_SELECT_ATTRS = ("select", "default_select")


def _collect_select_strings_from_source(tree: ast.AST) -> list[tuple[ast.AST, str]]:
    """Pull `--select "<expr>"` and `default_select=...` literals from a file."""
    out: list[tuple[ast.AST, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg in _SELECT_ATTRS and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    out.append((kw.value, kw.value.value))
            # Heuristic: a list/tuple containing "--select" "<value>"
            for arg in node.args:
                if isinstance(arg, (ast.List, ast.Tuple)):
                    elts = arg.elts
                    for i, elt in enumerate(elts[:-1]):
                        nxt = elts[i + 1]
                        if (
                            isinstance(elt, ast.Constant)
                            and elt.value == "--select"
                            and isinstance(nxt, ast.Constant)
                            and isinstance(nxt.value, str)
                        ):
                            out.append((nxt, nxt.value))
        # Direct call: parse_select("...")
        if isinstance(node, ast.Call):
            callee = node.func
            cname = callee.id if isinstance(callee, ast.Name) else (callee.attr if isinstance(callee, ast.Attribute) else None)
            if cname == "parse_select" and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                out.append((node.args[0], node.args[0].value))
    return out


def _select_atoms(expr_str: str) -> list[tuple[str | None, str]] | None:
    """Tokenise a select expression into (namespace, name) atoms. Returns None on parse error."""
    try:
        from a2kit._select import parse_select  # noqa: PLC0415

        ast_node = parse_select(expr_str)
    except (ValueError, Exception):  # noqa: BLE001
        return None
    out: list[tuple[str | None, str]] = []

    def walk(node: object) -> None:
        op = getattr(node, "op", None)
        if op == "atom":
            atom = node.atom  # type: ignore[attr-defined]
            out.append((atom.namespace, atom.name))
            return
        for c in getattr(node, "children", []):
            walk(c)

    walk(ast_node)
    return out


def _scan_pyproject_select(start: Path) -> str | None:
    """Read `[tool.a2kit.runner] default_select` from the nearest pyproject.toml."""
    import tomllib  # noqa: PLC0415

    cur = start.resolve() if start.exists() else Path.cwd().resolve()
    for parent in [cur, *cur.parents]:
        candidate = parent / "pyproject.toml"
        if candidate.is_file():
            try:
                data = tomllib.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, tomllib.TOMLDecodeError):  # pragma: no cover — defensive
                return None
            return data.get("tool", {}).get("a2kit", {}).get("runner", {}).get("default_select")
    return None


def _scan_shell_select_strings(paths: list[Path]) -> list[tuple[Path, int, str]]:
    """Grep `.sh` files and Makefiles for `--select "<expr>"` literals."""
    out: list[tuple[Path, int, str]] = []
    for path in paths:
        if path.suffix not in {".sh"} and path.name != "Makefile":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover — defensive
            continue
        for lineno, raw in enumerate(text.splitlines(), start=1):
            stripped = raw.strip()
            idx = stripped.find("--select")
            if idx == -1:
                continue
            tail = stripped[idx + len("--select") :].lstrip()
            if not tail:  # pragma: no cover — `--select` always followed by something usable
                continue
            quote = tail[0]
            if quote not in {'"', "'"}:  # pragma: no cover — supported forms only
                continue
            end = tail.find(quote, 1)
            if end == -1:  # pragma: no cover — malformed quoting
                continue
            out.append((path, lineno, tail[1:end]))
    return out


def _resolve_known_atoms_from_files(per_file: dict[str, tuple[set[str], set[str]]]) -> set[str]:
    """Union of router + tool names across the linted file set."""
    routers: set[str] = set()
    tools: set[str] = set()
    for r, t in per_file.values():
        routers |= r
        tools |= t
    return routers | tools | _BUILTIN_CAPS | {"default"}


def _rule_a2k010(
    pyproject_select: str | None,
    source_findings: list[tuple[Path, ast.AST, str]],
    shell_findings: list[tuple[Path, int, str]],
    known_atoms: set[str],
    *,
    pyproject_path: Path | None = None,
) -> Iterable[LintMessage]:
    """Validate `--select` atoms against `known_atoms`. Unknown → A2K010."""
    pools = sorted(known_atoms)

    def check(atoms: list[tuple[str | None, str]] | None, filename: str, line: int, col: int) -> Iterable[LintMessage]:
        if atoms is None:
            return
        for ns, name in atoms:
            # Routers/tools live in the unified pool; namespaced cap atoms must be caps.
            target_pool = known_atoms if ns is None else known_atoms
            if name in target_pool:
                continue
            hits = difflib.get_close_matches(name, pools, n=2)
            suggestion = f" Did you mean: {', '.join(hits)}?" if hits else ""
            yield LintMessage(
                rule=A2K010,
                filename=filename,
                line=line,
                col=col,
                message=f"unknown --select atom {name!r}.{suggestion}",
            )

    if pyproject_select is not None:
        atoms = _select_atoms(pyproject_select)
        target = str(pyproject_path) if pyproject_path else "pyproject.toml"
        yield from check(atoms, target, 1, 0)

    for path, node, value in source_findings:
        atoms = _select_atoms(value)
        yield from check(atoms, str(path), getattr(node, "lineno", 1), getattr(node, "col_offset", 0))

    for path, lineno, value in shell_findings:
        atoms = _select_atoms(value)
        yield from check(atoms, str(path), lineno, 0)


# --------------------------------------------------------------------------- #
# Driver.
# --------------------------------------------------------------------------- #


_RULES_PER_FILE = (
    (A2K001, rule_a2k001),
    (A2K002, rule_a2k002),
    (A2K003, rule_a2k003),
    (A2K004, rule_a2k004),
    (A2K005, rule_a2k005),
    (A2K009, rule_a2k009),
    (A2K011, rule_a2k011),
)


def run_static_rules(paths: Iterable[Path], *, disabled: Iterable[str] = ()) -> list[LintMessage]:
    """Run all static rules on `paths`. Returns concatenated findings."""
    disabled_set = set(disabled)
    paths_list = list(paths)
    results: list[LintMessage] = []
    per_file_a2k006: dict[str, dict[str, list[str]]] = {}
    per_file_a2k008: dict[str, tuple[set[str], set[str]]] = {}
    select_findings: list[tuple[Path, ast.AST, str]] = []
    shell_findings = _scan_shell_select_strings(paths_list)

    for path in paths_list:
        if path.suffix != ".py":
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for code, rule in _RULES_PER_FILE:
            if code in disabled_set:
                continue
            results.extend(rule(tree, str(path), source))
        if A2K006 not in disabled_set:
            per_file_a2k006[str(path)] = _collect_param_descriptions(tree)
        if A2K008 not in disabled_set and not _is_fixture_path(str(path)):
            per_file_a2k008[str(path)] = (_collect_router_names(tree), _collect_tool_names(tree))
        if A2K010 not in disabled_set and not _is_fixture_path(str(path)):
            for n, value in _collect_select_strings_from_source(tree):
                select_findings.append((path, n, value))

    if A2K006 not in disabled_set:
        results.extend(_rule_a2k006_cross(per_file_a2k006))
    if A2K008 not in disabled_set:
        results.extend(_rule_a2k008_cross(per_file_a2k008))
    if A2K010 not in disabled_set:
        # Resolve known atoms from the union of linted files.
        known_atoms = _resolve_known_atoms_from_files(per_file_a2k008)
        # pyproject default_select: lint-time check.
        anchor = paths_list[0] if paths_list else Path.cwd()
        pyproject_select = _scan_pyproject_select(anchor if anchor.is_dir() else anchor.parent)
        results.extend(_rule_a2k010(pyproject_select, select_findings, shell_findings, known_atoms))
    return results
