"""a11y-ad — browserless WCAG 4.1.2 accessible-name auditor."""

from .core import (AuditResult, Element, FetchError, audit, audit_file,
                   audit_tree, fetch)

__version__ = "0.1.0"

__all__ = [
    "AuditResult", "Element", "FetchError", "audit", "audit_file",
    "audit_tree", "fetch", "__version__",
]
