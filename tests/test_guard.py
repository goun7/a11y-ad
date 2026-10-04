"""SSRF guard tests — fetch() must refuse internal/private targets."""

import pytest

from a11y_ad import FetchError
from a11y_ad.core import _guard_url


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.com/x.html",
    "javascript:alert(1)",
    "http://localhost/x",
    "http://localhost:8080/admin",
    "http://127.0.0.1/x",
    "http://0.0.0.0/x",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.1/x",
    "http://192.168.1.10/x",
    "http://172.16.0.5/x",
    "http://[::1]/x",
    "http://metadata.internal/x",
    "http://printer.local/x",
])
def test_guard_refuses_internal_targets(url):
    with pytest.raises(FetchError):
        _guard_url(url)


def test_guard_accepts_public_url():
    assert _guard_url("https://example.com/") == "https://example.com/"


def test_guard_rejects_unresolvable_host():
    with pytest.raises(FetchError):
        _guard_url("https://this-host-does-not-exist-a11y-ad.invalid/")
