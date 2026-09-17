"""In-page link checker for README-style documents (GitHub anchors).

GitHub turns every heading into an *id* before it can be linked.  Its slugger
keeps letters, marks, digits, ``_`` and spaces, drops everything else (emoji
included) and replaces spaces with hyphens.  A heading that starts with an
emoji therefore gets an anchor with a **leading hyphen**: ``## 📥 Download`` is
``#-download``, not ``#download``.  Links written by hand usually get this
wrong, and the contents list - or the language switcher at the top of the
README - then silently does nothing when clicked.

This tool recomputes the real anchors and verifies that every ``](#anchor)``
link in the file points at one of them.

Usage (from the repository root)::

    python tools/check_readme_anchors.py             # check README.md
    python tools/check_readme_anchors.py FILE...     # check other documents
    python tools/check_readme_anchors.py --live      # also compare the local
                                                     # slugger with the anchors
                                                     # GitHub generated for the
                                                     # committed README

Exit status: 0 when every in-page link resolves, 1 otherwise.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/Kazake95/SponsorScout"

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
LINK_RE = re.compile(r"\]\(#([^)\s]+)\)")
LIVE_ID_RE = re.compile(r'id="user-content-([^"]+)"')


def github_slug(heading: str) -> str:
    """Return the anchor GitHub generates for *heading*."""
    kept = [
        ch for ch in heading
        if ch == " " or ch == "_" or unicodedata.category(ch)[0] in ("L", "M", "N")
    ]
    return "".join(kept).lower().replace(" ", "-")


def anchors(text: str) -> dict[str, int]:
    """Map every heading anchor to the line it was generated from."""
    found: dict[str, int] = {}
    for lineno, line in enumerate(text.splitlines(), start=1):
        match = HEADING_RE.match(line)
        if not match:
            continue
        base = slug = github_slug(match.group(2))
        n = 1
        while slug in found:            # GitHub suffixes repeated headings
            slug = f"{base}-{n}"
            n += 1
        found[slug] = lineno
    return found


def decode(target: str) -> str:
    """Percent-decode an anchor so it can be compared with a real id."""
    return re.sub(r"%[0-9A-Fa-f]{2}", lambda m: chr(int(m.group(0)[1:], 16)), target)


def check_text(text: str) -> tuple[int, list[tuple[int, str]], dict[str, int]]:
    """Return (links checked, broken links, anchors) for *text*."""
    found = anchors(text)
    broken: list[tuple[int, str]] = []
    checked = 0
    for lineno, target in (
        (lineno, match.group(1))
        for lineno, line in enumerate(text.splitlines(), start=1)
        for match in LINK_RE.finditer(line)
    ):
        checked += 1
        if decode(target) not in found:
            broken.append((lineno, target))
    return checked, broken, found


def check(path: Path) -> tuple[int, list[tuple[int, str]], dict[str, int]]:
    """Return (links checked, broken links, anchors) for *path*."""
    return check_text(path.read_text(encoding="utf-8"))


def pushed_text(path: Path) -> str | None:
    """Text of *path* in the last commit, or None when that is unavailable.

    GitHub renders the committed revision, so comparing the slugger with the
    live anchors only makes sense for that revision; an uncommitted edit would
    show up as a bogus mismatch.
    """
    try:
        rel = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return None
    result = subprocess.run(["git", "show", f"HEAD:{rel}"],
                            capture_output=True, cwd=ROOT)
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", "replace")


def live_anchors() -> set[str] | None:
    """Anchors GitHub generated for the pushed README, or None if offline."""
    request = urllib.request.Request(REPO_URL, headers={"User-Agent": "ss-anchor-check"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8", "replace")
    except Exception as exc:                                    # noqa: BLE001
        print(f"live check skipped: {exc}")
        return None
    return set(decoded for decoded in LIVE_ID_RE.findall(html))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path,
                        help="documents to check (default: README.md)")
    parser.add_argument("--live", action="store_true",
                        help="compare the local slugger with GitHub's anchors")
    args = parser.parse_args()

    paths = args.paths or [ROOT / "README.md"]
    status = 0
    for path in paths:
        if not path.exists():
            print(f"ERROR: missing file {path}")
            status = 2
            continue
        checked, broken, found = check(path)
        if broken:
            status = 1
        print(f"{path.name}: {len(found)} headings, {checked} in-page links, "
              f"{len(broken)} broken")
        for lineno, target in broken:
            print(f"  L{lineno} -> #{decode(target)}  (no such heading)")

    if args.live:
        live = live_anchors()
        if live:
            local: set[str] = set()
            for path in paths:
                committed = pushed_text(path)
                if committed is None:
                    print(f"  {path.name}: not committed - comparing working copy")
                    committed = path.read_text(encoding="utf-8") if path.exists() else ""
                local |= set(anchors(committed))
            missing = sorted(local - live)
            extra = sorted(live - local)
            print(f"live check: {len(live)} anchors on GitHub, "
                  f"{len(missing)} not there, {len(extra)} unknown locally")
            for slug in missing:
                print(f"  not on GitHub: {slug!r}")
            for slug in extra:
                print(f"  only on GitHub: {slug!r}")
            for path in paths:                    # GitHub serves the commit,
                committed = pushed_text(path)     # not the working copy
                if committed is None or not path.exists():
                    continue
                if committed == path.read_text(encoding="utf-8"):
                    continue
                _, stale, _ = check_text(committed)
                if stale:
                    print(f"  {path.name}: the committed revision still has "
                          f"{len(stale)} broken link(s) - commit to fix GitHub")

    print("RESULT: OK - every in-page link resolves." if not status else
          "RESULT: BROKEN LINKS - fix the targets above.")
    return status


if __name__ == "__main__":
    sys.exit(main())
