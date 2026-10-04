"""CLI: `a11y-ad <file.html | directory | URL> ... [--json]`

Exit codes (CI-friendly):
    0 — every interactive element has an accessible name
    1 — at least one missing name (or audit error)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Tuple

from .core import AuditResult, audit_file, audit_tree, fetch


def _collect(targets: List[str]) -> List[Tuple[str, AuditResult]]:
    out: List[Tuple[str, AuditResult]] = []
    for t in targets:
        if t.startswith(("http://", "https://")):
            out.append((t, fetch(t)))
            continue
        p = Path(t)
        if p.is_dir():
            for path, res in audit_tree(p).items():
                out.append((str(path), res))
        else:
            out.append((str(p), audit_file(p)))
    return out


def _summary(label: str, res: AuditResult) -> str:
    srcs = ", ".join("%s=%d" % kv for kv in sorted(res.sources.items()))
    lines = ["%s: %d interactive element(s), %d without accessible name [%s]"
             % (label, res.total, len(res.missing), srcs)]
    lines += ["  MISSING " + e.describe() for e in res.missing[:10]]
    if len(res.missing) > 10:
        lines.append("  ... and %d more" % (len(res.missing) - 10))
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="a11y-ad",
        description="Browserless WCAG 4.1.2 accessible-name auditor.")
    ap.add_argument("targets", nargs="+",
                    help="HTML file, directory (recursive *.html) or URL")
    ap.add_argument("--json", action="store_true",
                    help="machine-readable JSON output")
    args = ap.parse_args(argv)

    try:
        results = _collect(args.targets)
    except Exception as exc:  # noqa: BLE001 — CLI boundary
        print("error: %s" % exc, file=sys.stderr)
        return 1

    if args.json:
        payload = [{
            "target": label,
            "total": r.total,
            "missing": [e.describe() for e in r.missing],
            "sources": r.sources,
            "ok": r.ok,
        } for label, r in results]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for label, r in results:
            print(_summary(label, r))

    return 0 if all(r.ok for _, r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
