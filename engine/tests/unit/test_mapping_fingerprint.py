"""The format fingerprint (interface section 3): one export layout, one 16-hex id."""

import hashlib

from intake.mapping.fingerprint import format_fingerprint


def test_fingerprint_is_sha256_of_trimmed_lowercased_headers_in_order() -> None:
    expected = hashlib.sha256(b"client id\nbirth dt").hexdigest()[:16]
    assert format_fingerprint(["  Client ID ", "Birth Dt"]) == expected
    assert len(expected) == 16


def test_case_and_spacing_do_not_change_the_fingerprint() -> None:
    assert format_fingerprint(["MBI", " Plan "]) == format_fingerprint(["mbi", "plan"])


def test_order_and_added_headers_do_change_it() -> None:
    base = format_fingerprint(["mbi", "plan"])
    assert format_fingerprint(["plan", "mbi"]) != base
    assert format_fingerprint(["mbi", "plan", "notes"]) != base


def test_empty_header_list_has_a_fingerprint() -> None:
    assert format_fingerprint([]) == hashlib.sha256(b"").hexdigest()[:16]
