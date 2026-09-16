"""Dev<->app sync checker for the standalone job-search algorithms.

The scanning algorithms are first built and tuned as standalone scripts in
``extra_for_dev_purpose(do not delete)/main_job_search_algorithms/`` and then
implemented in the application package.  This tool reports how the two copies
have drifted apart, so an update made in the dev script can never be silently
missing from the app (which would make the app miss jobs).

Usage (from the repository root)::

    python tools/check_dev_sync.py            # report
    python tools/check_dev_sync.py --strict   # exit 1 on unimplemented code

What the report means
---------------------
* **app-only lines / symbols** - application integration hooks (progress
  callbacks, cooperative cancellation, writable log paths, ...).  Expected.
* **shared symbol with "-" lines** - the app no longer contains lines the dev
  script has.  Either an intentional rewrite, or a dev update that was never
  implemented.  Review the shown hunk.
* **dev-only symbol** - exists in the dev script but not in the app.  Must be
  listed in :data:`ALLOWLIST` (with the reason) or it is a real gap.

Exit status: 0 normally, 1 with ``--strict`` when a real gap is detected.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEV_DIR = ROOT / "extra_for_dev_purpose(do not delete)" / "main_job_search_algorithms"

PAIRS: list[tuple[str, Path, Path]] = [
    ("ATS",
     DEV_DIR / "ats_portal_scanner.py",
     ROOT / "sponsorscout" / "scanning" / "ats" / "ats_scanner.py"),
    ("Career",
     DEV_DIR / "career_scanner.py",
     ROOT / "sponsorscout" / "scanning" / "career" / "career_scanner.py"),
]

# The JD-evidence detector is the single source of truth for what counts as
# sponsorship / relocation / Blue-Card evidence, and it lives inside the dev
# scripts as a class rather than in a file of its own - so it needs a
# class-to-class comparison against the app's shared module.
CLASS_PAIRS: list[tuple[str, Path, str, Path, str]] = [
    ("JD detector",
     DEV_DIR / "ats_portal_scanner.py", "JDSupportDetector",
     ROOT / "sponsorscout" / "scanning" / "jd_support.py", "JDSupportDetector"),
]

# Dev-only symbols that are intentionally not duplicated in the app copy,
# mapped to the reason.  Anything else found is treated as a real gap.
ALLOWLIST: dict[str, dict[str, str]] = {
    "ATS": {
        "JDSupportDetector":
            "shared with the app via sponsorscout/scanning/jd_support.py",
    },
    "Career": {},
    "JD detector": {},
}

# Dev-only symbols that are just the standalone script's own CLI entry point.
ENTRYPOINT_ONLY = {"main", "cli", "_parse_args", "build_arg_parser"}

# Drift hunks (shared symbols that no longer contain every dev line) that have
# been reviewed and are known to be intentional application hooks rather than
# lost algorithm logic.  Anything not listed here is reported as "review this",
# and ``--strict`` fails on it - which is the point: a dev-script update must be
# either implemented or explained here.
DRIFT_ALLOWLIST: dict[str, dict[str, str]] = {
    "ATS": {
        "ATSScanner":
            "inline Blue-Card logic moved to the shared classifier in "
            "sponsorscout/scanning/jd_support.py (verified identical)",
        "ATSScanner.classify_support":
            "Blue-Card detection delegated to jd_support.detect_blue_card() "
            "so ATS and career scanning share one classifier",
        "print":
            "standalone print shim replaced by the app's scan-log _notify()",
        "ATSScanner.__init__":
            "signature line wrapping only (same parameters)",
    },
    "Career": {
        "CareerPortalScanner":
            "host-adaptive max_workers + shared lean BROWSER_ARGS "
            "(superset of the dev flags: no-sandbox, dev-shm, http2, certs)",
        "CareerPortalScanner.__init__":
            "max_workers default None -> sized per host via "
            "recommended_workers('browser')",
        "CareerPortalScanner.execute_crawler":
            "browser launched with the shared BROWSER_ARGS from "
            "sponsorscout/scanning/common.py",
    },
    "JD detector": {},
}


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8-sig").splitlines()


def symbols(path: Path) -> dict[str, tuple[str, ast.AST]]:
    """Return {name: (kind, node)} for top-level defs/classes and methods."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    out: dict[str, tuple[str, ast.AST]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = ("def", node)
        elif isinstance(node, ast.ClassDef):
            out[node.name] = ("class", node)
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[f"{node.name}.{sub.name}"] = ("method", sub)
    return out


def segment(lines: list[str], node: ast.AST) -> list[str]:
    return lines[node.lineno - 1: node.end_lineno]


# Lines that carry no meaning on their own; ignored when reporting which dev
# lines the app copy no longer contains (avoids trivia such as ")").
_TRIVIAL = {"", ")", "]", "}", "(", "[", "{", "):", "],", "},", '"""',
            "'''", "else:", "try:", "pass"}

MAX_SHOWN = 12  # lines shown per drifted symbol


def removed_lines(dev_seg: list[str], app_seg: list[str]) -> list[str]:
    """Dev lines (normalised) that do not occur anywhere in the app segment.

    Comparison is whitespace-insensitive in two steps so that reformatting -
    re-wrapped parameter lists, re-indented blocks - is not reported as lost
    logic: first line-by-line, then against the whole segment with all
    whitespace stripped.
    """
    app_norm = {ln.strip() for ln in app_seg}
    app_stream = re.sub(r"\s+", "", "".join(app_seg))
    out: list[str] = []
    for ln in dev_seg:
        stripped = ln.strip()
        if stripped in _TRIVIAL or stripped in app_norm:
            continue
        reduced = re.sub(r"\s+", "", stripped)
        # Long enough to be unambiguous: present in the app copy, just wrapped.
        if len(reduced) >= 12 and reduced in app_stream:
            continue
        out.append(stripped)
    return out


def file_version(path: Path) -> str:
    """Best-effort extraction of a ``__version__`` constant from a source file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except SyntaxError:
        return "?"
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if getattr(target, "id", "") == "__version__":
                    value = node.value
                    if isinstance(value, ast.Constant):
                        return str(value.value)
    return "-"


def find_class(path: Path, name: str) -> ast.ClassDef | None:
    """Return the named top-level class definition, or None."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def class_members(cls: ast.ClassDef) -> dict[str, ast.AST]:
    """Return {member_name: node} for a class's methods and class attributes.

    ``__init__`` is included: a constructor that stops initialising a field the
    detector later reads is exactly the kind of drift this tool must surface.
    """
    out: dict[str, ast.AST] = {}
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out[node.target.id] = node
    return out


_CONST_NAME_OK = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


def module_constants(path: Path) -> dict[str, list[str]]:
    """Return {CONSTANT_NAME: source_lines} for module-level CONSTANTS.

    The detector's behaviour is defined as much by these tables (visa /
    relocation concepts, negation markers, ...) as by its methods, so they are
    compared alongside the class body.
    """
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    out: dict[str, list[str]] = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            name = getattr(target, "id", "")
            if not name or set(name) - _CONST_NAME_OK or name.startswith("_"):
                continue
            out[name] = lines[node.lineno - 1: node.end_lineno]
    return out


def analyse(label: str, dev_path: Path, app_path: Path) -> dict:
    """Compare one dev/app pair and describe the drift."""
    dev_lines = read_lines(dev_path)
    app_lines = read_lines(app_path)
    dev_syms = symbols(dev_path)
    app_syms = symbols(app_path)

    missing = sorted(set(dev_syms) - set(app_syms))
    added = sorted(set(app_syms) - set(dev_syms))
    allow = ALLOWLIST.get(label, {})

    # A member of an allowlisted class is shared along with the class (e.g.
    # JDSupportDetector.detect lives in jd_support.py), so it is allowlisted
    # with the same reason rather than reported as a gap.
    def reason_for(name: str) -> str | None:
        if name in allow:
            return allow[name]
        owner = name.split(".", 1)[0]
        if owner in allow:
            return allow[owner]
        return None

    allowlisted = {n: reason_for(n) for n in missing if reason_for(n)}
    entrypoint = [n for n in missing if n in ENTRYPOINT_ONLY]
    gaps = [n for n in missing if not reason_for(n) and n not in ENTRYPOINT_ONLY]

    drifted: dict[str, list[str]] = {}
    for name in sorted(set(dev_syms) & set(app_syms)):
        removed = removed_lines(segment(dev_lines, dev_syms[name][1]),
                                segment(app_lines, app_syms[name][1]))
        if removed:
            drifted[name] = removed

    return {
        "label": label,
        "dev_path": dev_path,
        "app_path": app_path,
        "dev_symbols": len(dev_syms),
        "app_symbols": len(app_syms),
        "gaps": gaps,
        "allowlisted": allowlisted,
        "entrypoint": entrypoint,
        "added": added,
        "drifted": drifted,
        "dev_version": file_version(dev_path),
        "app_version": file_version(app_path),
    }


def analyse_class(label: str, dev_path: Path, dev_class: str,
                  app_path: Path, app_class: str) -> dict:
    """Compare one class (plus the module constants it reads) across files."""
    dev_lines = read_lines(dev_path)
    app_lines = read_lines(app_path)
    dev_cls = find_class(dev_path, dev_class)
    app_cls = find_class(app_path, app_class)
    if dev_cls is None or app_cls is None:
        return {
            "label": label, "dev_path": dev_path, "app_path": app_path,
            "dev_symbols": 0, "app_symbols": 0,
            "gaps": [f"{dev_class} (class not found in "
                     f"{'dev' if dev_cls is None else 'app'} file)"],
            "allowlisted": {}, "entrypoint": [], "added": [], "drifted": {},
            "dev_version": file_version(dev_path),
            "app_version": file_version(app_path),
        }

    dev_members = class_members(dev_cls)
    app_members = class_members(app_cls)
    missing = sorted(set(dev_members) - set(app_members))
    added = sorted(set(app_members) - set(dev_members))

    gaps = list(missing)
    drifted: dict[str, list[str]] = {}
    for name in sorted(set(dev_members) & set(app_members)):
        removed = removed_lines(segment(dev_lines, dev_members[name]),
                                segment(app_lines, app_members[name]))
        if removed:
            drifted[name] = removed

    # Module-level constants the class reads must match too (the dictionaries
    # that define what counts as sponsorship evidence live outside the class).
    dev_consts = module_constants(dev_path)
    app_consts = module_constants(app_path)
    referenced = sorted({n.id for n in ast.walk(dev_cls)
                         if isinstance(n, ast.Name)} & set(dev_consts))
    for name in referenced:
        if name not in app_consts:
            gaps.append(f"constant {name} missing from the app module")
        elif app_consts[name] != dev_consts[name]:
            drifted[f"const {name}"] = [ln for ln in dev_consts[name]
                                        if ln not in set(app_consts[name])
                                        and ln not in _TRIVIAL]

    return {
        "label": label,
        "dev_path": dev_path,
        "app_path": app_path,
        "dev_symbols": len(dev_members) + len(referenced),
        "app_symbols": len(app_members) + len(referenced),
        "gaps": gaps,
        "allowlisted": {},
        "entrypoint": [],
        "added": added,
        "drifted": drifted,
        "dev_version": file_version(dev_path),
        "app_version": file_version(app_path),
    }


def report(entry: dict) -> None:
    """Print the drift report for one dev/app pair."""
    bar = "=" * 74
    print(bar)
    print(f"{entry['label']}: {entry['dev_path'].name}  ->  "
          f"{entry['app_path'].relative_to(ROOT).as_posix()}")
    print(bar)
    print(f"symbols: dev={entry['dev_symbols']}  app={entry['app_symbols']}  "
          f"|  versions: dev={entry['dev_version']} app={entry['app_version']}")

    if entry["gaps"]:
        print(f"\n!! dev-only symbols NOT implemented in the app "
              f"({len(entry['gaps'])}) - real gaps:")
        for name in entry["gaps"]:
            print(f"   !! {name}")
    else:
        print("\nOK  every dev symbol is implemented in the app "
              "(or explicitly allowlisted)")

    if entry["allowlisted"]:
        print(f"\nallowlisted dev-only symbols ({len(entry['allowlisted'])}):")
        for name, why in entry["allowlisted"].items():
            print(f"   - {name}  [{why}]")

    if entry["entrypoint"]:
        print(f"\nstandalone entry point ({len(entry['entrypoint'])}): "
              f"{', '.join(entry['entrypoint'])}")

    if entry["added"]:
        preview = ", ".join(entry["added"][:8])
        more = "" if len(entry["added"]) <= 8 else f" (+{len(entry['added']) - 8} more)"
        print(f"\napp-only symbols ({len(entry['added'])}; integration hooks, "
              f"expected):\n   + {preview}{more}")

    if entry["drifted"]:
        allow_drift = DRIFT_ALLOWLIST.get(entry["label"], {})
        expected = {n: r for n, r in allow_drift.items() if n in entry["drifted"]}
        review = {n: v for n, v in entry["drifted"].items() if n not in allow_drift}
        entry["expected_drift"] = expected
        entry["unreviewed_drift"] = review

        if expected:
            print(f"\nexpected drift ({len(expected)}; documented, verified as "
                  f"intentional app hooks):")
            for name, why in expected.items():
                print(f"   = {name}  [{why}]")

        if review:
            print(f"\nshared symbols containing dev lines absent from the app "
                  f"({len(review)}) - REVIEW EACH HUNK:")
            for name, removed in review.items():
                print(f"   ~ {name}  (-{len(removed)} dev line(s))")
                for line in removed[:MAX_SHOWN]:
                    print(f"        {line}")
                if len(removed) > MAX_SHOWN:
                    print(f"        ... {len(removed) - MAX_SHOWN} more")
        else:
            print("\nOK  every shared symbol line is present in the app "
                  "(or the difference is documented as intentional)")
    else:
        print("\nOK  every shared symbol line is present in the app")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 if a dev symbol is missing from the app, "
                             "or if a symbol drift hunk is undocumented")
    args = parser.parse_args()

    missing_files = [p for _, dev, app in PAIRS for p in (dev, app)
                     if not p.exists()]
    missing_files += [p for _, dev, _dc, app, _ac in CLASS_PAIRS
                      for p in (dev, app) if not p.exists()]
    if missing_files:
        for path in sorted(set(missing_files)):
            print(f"ERROR: missing file {path}")
        return 2

    entries = [analyse(label, dev, app) for label, dev, app in PAIRS]
    entries += [analyse_class(label, dev, dev_cls, app, app_cls)
                for label, dev, dev_cls, app, app_cls in CLASS_PAIRS]
    for entry in entries:
        report(entry)

    gaps = sum(len(e["gaps"]) for e in entries)
    expected_drift = sum(len(e.get("expected_drift", {})) for e in entries)
    unreviewed = sum(len(e.get("unreviewed_drift", {})) for e in entries)
    print("-" * 74)
    if gaps:
        print(f"RESULT: DRIFT - {gaps} dev-only symbol(s) not implemented. "
              f"Implement them in the app, or add them to ALLOWLIST with a "
              f"reason.")
    else:
        print("RESULT: IN SYNC - no dev-only implementation is missing.")
    if unreviewed:
        print(f"ACTION NEEDED: {unreviewed} shared symbol(s) contain dev lines "
              f"the app no longer has and are NOT documented in "
              f"DRIFT_ALLOWLIST. Review the hunks above; implement the change "
              f"or document why it is intentional.")
    if expected_drift:
        print(f"NOTE: {expected_drift} reviewed drift hunk(s) documented as "
              f"intentional application hooks.")
    print("Hint: also run the test suite - "
          "python -m pytest sponsorscout/tests -q")

    return 1 if (args.strict and (gaps or unreviewed)) else 0


if __name__ == "__main__":
    sys.exit(main())
