"""Helpers for asserting on generated HCL text.

Generated Terraform aligns ``=`` signs the way ``terraform fmt`` does, so an attribute
such as ``default = true`` is rendered as ``default     = true`` inside a block. Content
assertions use :func:`unaligned` so they check *what* is generated, while
``tests/test_hcl_format.py`` checks the alignment itself.
"""

import re

_ALIGNED_ATTRIBUTE = re.compile(r"(?m)^([ \t]*[^\s=]+?) {2,}= ")


def unaligned(text: str) -> str:
    """Collapse the alignment padding before ``=`` in rendered HCL attribute lines."""
    return _ALIGNED_ATTRIBUTE.sub(r"\1 = ", text)
