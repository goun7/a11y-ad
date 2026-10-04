# a11y-ad — browserless WCAG 4.1.2 accessible-name auditor

`a11y-ad` audits HTML for **missing accessible names** (WCAG 4.1.2 / "Name,
Role, Value") on every interactive element — no browser, no headless Chrome,
stdlib only. Built for CI.

## Why another accessibility tool?

Most lightweight linters check *only* `aria-label`/`<label>` and flag every
button with visible text as a critical failure. In one audit run against a
fully-labelled application, a popular scanner reported **68 "critical" HTML
accessible-name issues — 0 of them real**, because visible button text,
`aria-labelledby`, and wrapping `<label>` elements are all valid accessible
names.

`a11y-ad` resolves the name the way assistive technology does, following the
WCAG 4.1.2 resolution order:

```
aria-labelledby -> aria-label -> visible text -> <label for=id>
-> wrapping <label> -> title -> alt (input[type=image])
```

and reports only the elements that end up with **no name at all**.

## Scope (be honest about automated a11y coverage)

Automated tools in general catch roughly 30–50% of WCAG issues; manual
keyboard/screen-reader testing remains necessary. `a11y-ad` covers exactly
one failure class — missing accessible names — and does it with zero false
positives in the resolution cases above. Browser-measured checks (target
size, focus visibility, contrast, reduced motion) are out of scope for the
core; see Roadmap.

## Install

```bash
pip install a11y-ad
```

## Usage

```bash
a11y-ad index.html            # single file
a11y-ad src/                  # directory (recursive, *.html)
a11y-ad https://example.com   # URL
a11y-ad src/ --json           # machine-readable
```

Exit code is `1` when any interactive element lacks a name — use it as a CI
gate:

```yaml
# GitHub Actions example
- run: pip install a11y-ad && a11y-ad dist/
```

### JSON payload

```json
[
  {
    "target": "bad.html",
    "total": 3,
    "missing": ["line 3 <button >", "line 4 <input >"],
    "sources": {"MISSING": 2, "text": 1},
    "ok": false
  }
]
```

### Library

```python
from a11y_ad import audit, audit_file, audit_tree, fetch

r = audit('<button aria-labelledby="h1">Edit</button>')
r.ok            # True
r.elements[0]   # Element(tag='button', name='...', source='aria-labelledby')
r.missing       # elements with no accessible name
```

## Exclusions & semantics

- `<a>` without `href` and `<input type="hidden">` are not interactive → skipped.
- `aria-hidden="true"` counts as *named* (it is intentionally hidden from AT).
- Elements whose visible text lives in a translation dictionary (filled at
  runtime) will read as *statically* missing; audit the rendered DOM for the
  final word (see Roadmap).

## Security

`fetch()` refuses non-http(s) schemes and any host resolving to a loopback,
private, link-local, reserved or multicast address, so the library can be
wired into "enter your URL" scan forms without handing callers a probe into
the host network. The guard is best-effort (no DNS-rebinding defense) — for
untrusted input at scale, front it with a proxy allowlist.

## Roadmap

- `--i18n` runtime layer: apply a key/value dictionary before auditing
  (ported from the battle-tested original).
- GitHub Action wrapper.
- Browser-measured WCAG 2.2 checks (2.5.8 target size, 2.4.7 focus,
  1.4.3 contrast) as an optional `[browser]` extra (Playwright).

## Provenance

The resolver is a hardened port of an auditor written for a production
PWA, where four measurement bugs (void-tag stack shifting, early
`</span>` closure bypassing a wrapping `<label>`, missing `label[for]`
map, wrapping labels not recognized) were found via live measurement and
fixed; their regression scenarios ship as tests in this repository.

## License

Apache-2.0
