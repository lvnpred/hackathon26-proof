"""The test helper that reads PDF text must not depend on what the compressed bytes happen to be."""

from __future__ import annotations

import zlib

from conftest import pdf_text


def _stream(data: bytes) -> bytes:
    return b"<</Filter /FlateDecode /Length %d>>\nstream\n" % len(data) + data + b"\nendstream\n"


def _compressed_ending_in(last: bytes) -> bytes:
    """Search for a content stream whose compressed form ends in the given byte."""
    for n in range(10_000):
        data = zlib.compress(f"BT (Resolved by demo user {n}) Tj ET".encode())
        if data.endswith(last):
            return data
    raise AssertionError("no sample found")


def test_reads_a_stream_whose_compressed_bytes_end_in_a_carriage_return():
    # A trailing 0x0D used to be eaten as part of "\r\nendstream", which broke inflation (~1 in 256 streams).
    data = _compressed_ending_in(b"\r")
    assert pdf_text(_stream(data)).startswith("Resolved by demo user")


def test_reads_every_stream_in_order():
    first, second = zlib.compress(b"BT (one) Tj ET"), zlib.compress(b"BT (two) Tj ET")
    assert pdf_text(_stream(first) + _stream(second)) == "one\ntwo"
