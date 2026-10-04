"""a11y-ad — browserless WCAG 4.1.2 accessible-name auditor.

Core resolver ported from an auditor built for a production PWA, where it
was hardened against four measurement bugs recorded during development.
Constraint notes from that port are kept inline.
"""

from __future__ import annotations

import ipaddress
import pathlib
import socket
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple

__all__ = ["Element", "AuditResult", "audit", "audit_file", "audit_tree", "fetch"]

INTERACTIVE = ("button", "a", "input", "select", "textarea")
VOID = ("input", "img", "br", "hr", "meta", "link", "source", "area",
        "base", "col", "embed", "param", "track", "wbr")
SKIP = {"script", "style", "template"}

# Source of an accessible name, in WCAG 4.1.2 resolution order.
SRC_LABELLEDBY = "aria-labelledby"
SRC_ARIA_LABEL = "aria-label"
SRC_TEXT = "text"
SRC_LABEL_FOR = "label[for]"
SRC_WRAPPING_LABEL = "wrapping-label"
SRC_TITLE = "title"
SRC_ALT_IMAGE = "alt"
SRC_HIDDEN = "aria-hidden"
SRC_MISSING = "MISSING"


@dataclass
class Element:
    """One interactive element and its resolved accessible name."""

    tag: str
    line: int
    attrs: Dict[str, str]
    name: str
    source: str
    # Stable key so two audit passes (e.g. pre/post runtime i18n) can be
    # diffed: element order never changes when only text is injected.
    @property
    def key(self) -> Tuple[int, str, str]:
        return (self.line, self.tag,
                self.attrs.get("id") or self.attrs.get("aria-label") or "")

    def describe(self) -> str:
        hint = self.attrs.get("id") or self.attrs.get("aria-label") or ""
        return "line %d <%s %s>" % (self.line, self.tag, hint)


@dataclass
class AuditResult:
    total: int
    elements: List[Element]
    sources: Dict[str, int]
    missing: List[Element] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing


class _LabelFor(HTMLParser):
    """Collects <label for="id">text</label> bindings."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.target: Optional[str] = None
        self.acc: List[str] = []
        self.map: Dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        d = {k: (v or "") for k, v in attrs}
        if tag == "label" and d.get("for"):
            self.target = d["for"]
            self.acc = []

    def handle_endtag(self, tag):
        if tag == "label" and self.target:
            v = " ".join(x for x in self.acc if x).strip()
            if v:
                self.map[self.target] = v
            self.target = None
            self.acc = []

    def handle_data(self, data):
        if self.target:
            self.acc.append(" ".join(data.split()))


class _Parser(HTMLParser):
    """Walks the HTML and captures every interactive element with context.

    Measurement-bug notes (from the ported implementation):
      #1 wrapping <label> must be recognised at all
      #2 void tags (<input>) must NOT be pushed on the stack — they have
         no close tag and would shift the <label> frame
      #4 an `</span>` close tag must not close an open <label> early:
         end-tag matching has to check BOTH the `tag` and `kind` fields
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: List[dict] = []
        self.stack: List[dict] = []
        self.wrapping: List[dict] = []
        # generic (non-interactive) elements carrying an id, kept by
        # reference: their text accumulates during parsing, so the
        # id->text map must be resolved AFTER feed() completes.
        self.id_nodes: Dict[str, dict] = {}

    def handle_starttag(self, tag, attrs):
        d = {k: (v or "") for k, v in attrs}
        if tag in SKIP:
            return
        if tag == "label":
            c = {"kind": "label", "texts": []}
            self.wrapping.append(c)
            self.stack.append(c)
            return
        if tag in INTERACTIVE:
            n = {"tag": tag, "attrs": d, "texts": [],
                 "line": self.getpos()[0],
                 "wrapping": self.wrapping[-1] if self.wrapping else None}
            self.elements.append(n)
            if self.wrapping:
                self.wrapping[-1].setdefault(
                    "children", self.wrapping[-1].get("children", []) + [n])
            if tag in VOID:  # bug #2
                return
            self.stack.append(n)
            return
        if tag in VOID:
            alt = d.get("alt", "")
            if alt:
                for c in self.stack[-3:]:
                    c.setdefault("alts", []).append(alt)
            return
        node = {"kind": tag, "texts": [], "attrs": d}
        aid = d.get("id")
        if aid:
            self.id_nodes[aid] = node
        self.stack.append(node)

    def handle_data(self, data):
        v = " ".join(data.split())
        if not v:
            return
        # [-3:] lookback: text may live one or two inline elements deep
        # (e.g. <button><span><b>Go</b></span></button>).
        for c in self.stack[-3:]:
            c["texts"].append(v)

    def handle_endtag(self, tag):
        # bug #4: match on tag AND kind, never pop past an open <label>.
        while self.stack:
            c = self.stack.pop()
            if c.get("kind") == "label" and tag == "label":
                if self.wrapping and self.wrapping[-1] is c:
                    self.wrapping.pop()
                break
            if c.get("tag") == tag or c.get("kind") == tag:
                break


def _text_of(node: dict) -> str:
    a = " ".join(x for x in node.get("texts", []) if x)
    if node.get("alts"):
        b = " ".join(x for x in node["alts"] if x)
        a = (a + " " + b).strip()
    return a


def audit(html: str) -> AuditResult:
    """Audit an HTML document for missing WCAG 4.1.2 accessible names.

    Resolution order: aria-labelledby -> aria-label -> visible text ->
    <label for=id> -> wrapping <label> -> title -> alt (input[type=image]).
    Excluded from the audit: <a> without href, <input type=hidden>.
    """
    p = _Parser()
    p.feed(html)
    p.close()
    lf = _LabelFor()
    lf.feed(html)
    lf.close()

    # id -> accessible text, collected for EVERY element (not only
    # interactive ones): aria-labelledby may point at a heading or span.
    id_text: Dict[str, str] = {}
    for e in p.elements:
        if e["attrs"].get("id"):
            id_text[e["attrs"]["id"]] = _text_of(e)
    for aid, node in p.id_nodes.items():
        if aid not in id_text:
            id_text[aid] = _text_of(node)

    total = 0
    missing: List[Element] = []
    sources: Dict[str, int] = {}
    elements: List[Element] = []
    for e in p.elements:
        d = e["attrs"]
        if e["tag"] == "a" and not d.get("href"):
            continue
        if e["tag"] == "input" and d.get("type") == "hidden":
            continue
        total += 1
        source = SRC_MISSING
        name = ""
        if d.get("aria-hidden") == "true":
            source = SRC_HIDDEN
        elif d.get("aria-labelledby"):
            parts = [id_text.get(x.strip(), "")
                     for x in d["aria-labelledby"].split()]
            joined = " ".join(x for x in parts if x).strip()
            if joined:
                source, name = SRC_LABELLEDBY, joined
        elif d.get("aria-label"):
            source, name = SRC_ARIA_LABEL, d["aria-label"]
        elif _text_of(e):
            source, name = SRC_TEXT, _text_of(e)
        elif d.get("id") and d["id"] in lf.map:
            source, name = SRC_LABEL_FOR, lf.map[d["id"]]
        elif e.get("wrapping") is not None and _text_of(e["wrapping"]):
            source, name = SRC_WRAPPING_LABEL, _text_of(e["wrapping"])
        elif d.get("title"):
            source, name = SRC_TITLE, d["title"]
        elif (e["tag"] == "input" and d.get("type") == "image"
              and d.get("alt")):
            source, name = SRC_ALT_IMAGE, d["alt"]
        sources[source] = sources.get(source, 0) + 1
        el = Element(tag=e["tag"], line=e["line"], attrs=d,
                     name=name, source=source)
        elements.append(el)
        if source == SRC_MISSING:
            missing.append(el)
    return AuditResult(total=total, elements=elements,
                       sources=sources, missing=missing)


def audit_file(path) -> AuditResult:
    return audit(pathlib.Path(path).read_text(encoding="utf-8"))


def audit_tree(root) -> Dict[pathlib.Path, AuditResult]:
    """Audit every *.html file under a directory (recursive)."""
    root = pathlib.Path(root)
    return {p: audit_file(p) for p in sorted(root.rglob("*.html"))}


class FetchError(ValueError):
    """Raised when a URL is refused by the SSRF guard."""


def _guard_url(url: str) -> str:
    """Refuse URLs that could reach internal/private infrastructure.

    fetch() is safe on a developer CLI, but this library is also used by
    web frontends ("enter your URL" scan forms). There, an unguarded
    fetch would let a caller probe localhost, link-local metadata
    endpoints, or the private network behind the server.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise FetchError("only http(s) URLs are allowed, got %r" % parsed.scheme)
    host = parsed.hostname
    if not host:
        raise FetchError("URL without host")
    if host in ("localhost",) or host.endswith((".local", ".internal", ".home")):
        raise FetchError("refusing internal hostname %r" % host)
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise FetchError("cannot resolve host %r: %s" % (host, exc))
    seen: set = set()
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip in seen:
            continue
        seen.add(ip)
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise FetchError(
                "refusing to fetch private/reserved address %s (host %r)"
                % (ip, host))
    return url


def fetch(url: str) -> AuditResult:
    """Fetch a URL over HTTP(S) and audit the response body.

    Refuses non-http(s) schemes and any host resolving to a loopback,
    private, link-local, reserved or multicast address (SSRF guard).
    Best-effort: DNS-rebinding TOCTOU is not defended against — never
    expose fetch() to untrusted input without a proxy allowlist.
    """
    _guard_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": "a11y-ad/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return audit(r.read().decode("utf-8", errors="replace"))
