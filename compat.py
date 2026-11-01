"""Compatibility helpers for Apple's Python 3.9."""
import datetime
import re


def iso_timestamp(value):
    # Python 3.9 accepts millisecond/microsecond precision, unlike newer Pythons
    # which also accept Go's arbitrary-length RFC3339 fractional seconds.
    text = str(value).replace('Z', '+00:00')
    text = re.sub(r'\.(\d+)', lambda m: '.' + m.group(1)[:6].ljust(6, '0'), text)
    return datetime.datetime.fromisoformat(text).timestamp()
