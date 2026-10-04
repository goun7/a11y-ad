"""a11y-ad core tests — includes regression scenarios ported from the
original production-PWA implementation, where four measurement bugs were
found and fixed during development (see PLAN.md in that project).
"""

from a11y_ad import audit

# ---------------------------------------------------------------- named


def test_visible_text():
    r = audit("<button>Save</button>")
    assert r.total == 1 and r.ok
    assert r.elements[0].source == "text"
    assert r.elements[0].name == "Save"


def test_nested_inline_text():
    # text may sit two inline elements deep ([-3:] lookback)
    r = audit("<button><span><b>Go</b></span></button>")
    assert r.ok and r.elements[0].source == "text"


def test_aria_label():
    r = audit('<button aria-label="Close dialog">X</button>')
    assert r.ok
    assert r.elements[0].source == "aria-label"
    assert r.elements[0].name == "Close dialog"


def test_aria_labelledby_points_at_heading():
    # aria-labelledby may reference a NON-interactive element (a heading):
    # the id->text map must cover every element, not only interactive ones.
    html = ('<h3 id="sec1">Account settings</h3>'
            '<button aria-labelledby="sec1">Edit</button>')
    r = audit(html)
    assert r.ok
    assert r.elements[0].source == "aria-labelledby"
    assert r.elements[0].name == "Account settings"


def test_label_for():
    html = ('<input id="email" type="text">'
            '<label for="email">Your e-mail</label>')
    r = audit(html)
    assert r.ok
    assert r.elements[0].source == "label[for]"
    assert r.elements[0].name == "Your e-mail"


def test_wrapping_label():
    html = "<label>Newsletter<input type=\"checkbox\"></label>"
    r = audit(html)
    assert r.ok
    assert r.elements[0].source == "wrapping-label"


def test_title_fallback():
    r = audit('<button title="Print page"><svg></svg></button>')
    assert r.ok
    assert r.elements[0].source == "title"


def test_input_image_alt():
    r = audit('<input type="image" alt="Search" src="s.png">')
    assert r.ok
    assert r.elements[0].source == "alt"


def test_aria_hidden_counted_as_named():
    r = audit('<button aria-hidden="true">::</button>')
    assert r.ok
    assert r.elements[0].source == "aria-hidden"


# ---------------------------------------------------------------- missing


def test_missing_button():
    r = audit("<button><svg></svg></button>")
    assert not r.ok
    assert r.missing[0].tag == "button"
    assert r.missing[0].describe().startswith("line 1 <button")


def test_exclusions():
    html = ('<input type="hidden" value="x">'
            '<a id="nohref">plain anchor</a>')
    r = audit(html)
    assert r.total == 0  # both excluded


# ------------------------------------------------- ported regressions


def test_void_tag_does_not_shift_label_frame():
    # original bug #2/#3: <input> is void; if it were pushed on the
    # stack the later <label> frame would be lost and the input would
    # falsely read as missing.
    html = ('<form><input id="q" type="text"></form>'
            '<label for="q">Search term</label>')
    r = audit(html)
    assert r.ok and r.elements[0].source == "label[for]"


def test_span_close_does_not_close_label_early():
    # original bug #4: </span> inside a label must not pop the label
    # off the stack; the input after it still resolves to the wrapping
    # label text.
    html = ("<label>Accept terms<span> (required)</span>"
            "<input type=\"checkbox\"></label>")
    r = audit(html)
    assert r.ok
    assert r.elements[0].source == "wrapping-label"


def test_negative_control_text_really_counts():
    # if the auditor counted nothing, stripping the visible text would
    # not change the result — guard against vacuous green.
    good = audit("<button>Save</button>")
    bad = audit("<button></button>")
    assert good.ok and not bad.ok
    assert len(bad.missing) - len(good.missing) >= 1


def test_sources_breakdown():
    html = ('<button>A</button><button aria-label="B">x</button>'
            "<button></button>")
    r = audit(html)
    assert r.total == 3
    assert r.sources == {"text": 1, "aria-label": 1, "MISSING": 1}
