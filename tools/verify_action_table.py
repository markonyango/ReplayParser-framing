#!/usr/bin/env python3
"""Verify the byte examples in docs/action-table-audit.md.

This is intentionally stdlib-only and does not require a replay file. It
checks the inclusive command length, sender/process split, receiver byte
orders, and custom-type sentinel/length rules used by the documentation.
"""

from __future__ import annotations

import struct


def decode(command: bytes) -> dict:
    if len(command) < 2:
        raise ValueError("missing command length")
    size = struct.unpack_from("<H", command)[0]
    if size != len(command):
        raise ValueError(f"inclusive size {size} != {len(command)}")
    body = command[2:]
    if len(body) < 8:
        raise ValueError("command body is too short")

    opcode, flags = body[:2]
    context = body[2:6]
    offset = 6
    first = body[offset]
    if first & 0xC0 == 0:
        raw_receivers = [int.from_bytes(body[offset : offset + 4], "big")]
        offset += 4
    else:
        if first & 0xC0 == 0x40:
            count = first & 0x3F
            offset += 1
        elif first & 0xC0 == 0x80:
            count = int.from_bytes(body[offset : offset + 2], "big") & 0x3FFF
            offset += 2
        else:
            count = int.from_bytes(body[offset : offset + 4], "big") & 0x3FFFFFFF
            offset += 4
        raw_receivers = []
        for _ in range(count):
            raw_receivers.append(int.from_bytes(body[offset : offset + 4], "little"))
            offset += 4

    custom_type = body[offset]
    offset += 1
    if custom_type == 0xFF:
        if offset != len(body):
            raise ValueError("0xff custom sentinel has payload")
        custom_length = None
        custom_data = b""
    else:
        first_length = body[offset]
        offset += 1
        if first_length < 0x80:
            custom_length = first_length
        else:
            custom_length = ((first_length & 0x7F) << 8) | body[offset]
            offset += 1
        custom_data = body[offset:]
        if len(custom_data) != custom_length:
            raise ValueError("custom length does not consume body")

    return {
        "opcode": opcode,
        "sender": flags & 0x7F,
        "process": flags >> 7,
        "context": context,
        "receivers": raw_receivers,
        "custom_type": custom_type,
        "custom_length": custom_length,
        "custom_data": custom_data,
    }


single = bytes.fromhex("12 00 03 03 eb 03 00 00 10 00 77 0c 05 04 86 00 00 00")
a = decode(single)
assert (a["opcode"], a["sender"], a["process"]) == (3, 3, 0)
assert a["context"] == bytes.fromhex("eb 03 00 00")
assert a["receivers"] == [0x1000770C]
assert (a["custom_type"], a["custom_length"], a["custom_data"]) == (5, 4, bytes.fromhex("86 00 00 00"))

listed = bytes.fromhex("12 00 44 03 eb 03 00 00 42 34 12 00 10 cd ab 00 20 ff")
b = decode(listed)
assert b["receivers"] == [0x10001234, 0x2000ABCD]
assert (b["custom_type"], b["custom_length"], b["custom_data"]) == (0xFF, None, b"")

extended_data = bytes([0xCD]) * 0x1234
extended_body = bytes([0xFA, 0x81, 0, 0, 0, 0, 0x40, 7, 0x92, 0x34]) + extended_data
extended = struct.pack("<H", len(extended_body) + 2) + extended_body
c = decode(extended)
assert (c["sender"], c["process"]) == (1, 1)
assert (c["custom_type"], c["custom_length"]) == (7, 0x1234)
assert c["custom_data"] == extended_data

print("action-table examples: ok")
