#!/usr/bin/env python3
"""Inspect the stable framing of a Dawn of War II .rec file.

This intentionally does not try to name every action or attribute.  It checks
file boundaries, reports the chunk tree, and decodes the command framing that
has been verified against the public sample replays.  It is dependency free so
that it can also be used while investigating a replay from a different build.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


class ReplayError(ValueError):
    """A replay failed a structural check."""


@dataclass
class Chunk:
    name: str
    offset: int
    version: int
    size: int
    end: int
    children: list["Chunk"] = field(default_factory=list)


def u16(data: bytes, offset: int, *, endian: str = "<") -> int:
    if offset < 0 or offset + 2 > len(data):
        raise ReplayError(f"u16 outside file at 0x{offset:x}")
    return struct.unpack_from(endian + "H", data, offset)[0]


def u32(data: bytes, offset: int, *, endian: str = "<") -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ReplayError(f"u32 outside file at 0x{offset:x}")
    return struct.unpack_from(endian + "I", data, offset)[0]


def chunk_at(data: bytes, offset: int, limit: int) -> Chunk:
    # Relic Chunky uses an eight-byte name, version, size, and twelve bytes of
    # per-chunk metadata.  The size is the payload size, after those 28 bytes.
    if offset + 28 > limit:
        raise ReplayError(f"short chunk header at 0x{offset:x}")
    raw_name = data[offset : offset + 8]
    name = raw_name.rstrip(b"\0").decode("ascii", errors="replace")
    version = u32(data, offset + 8)
    size = u32(data, offset + 12)
    end = offset + 28 + size
    if end > limit:
        raise ReplayError(
            f"chunk {name!r} at 0x{offset:x} ends at 0x{end:x}, "
            f"past limit 0x{limit:x}"
        )
    chunk = Chunk(name, offset, version, size, end)
    # These are containers in the observed files.  Other chunks contain data,
    # including DATAINFO and DATABASE, and must not be recursively guessed.
    if name.startswith("FOLD"):
        child = offset + 28
        while child < end:
            chunk.children.append(chunk_at(data, child, end))
            child = chunk.children[-1].end
        if child != end:
            raise ReplayError(f"container {name!r} has an incomplete tail")
    return chunk


def header(data: bytes) -> dict[str, object]:
    if len(data) < 84:
        raise ReplayError("file is shorter than the 84-byte replay header")
    magic = data[12:20]
    if magic != b"DOW2_REC":
        raise ReplayError(f"unexpected magic {magic!r}")
    raw_date = data[20:84].decode("utf-16le", errors="replace")
    return {
        "version": u32(data, 0),
        "mod_checksum": f"0x{u32(data, 4):08x}",
        "reserved": u32(data, 8),
        "magic": magic.decode("ascii"),
        "date": raw_date.split("\0", 1)[0],
    }


def flatten(chunks: Iterable[Chunk]) -> Iterable[Chunk]:
    for chunk in chunks:
        yield chunk
        yield from flatten(chunk.children)


def decode_receiver(body: bytes, pos: int) -> tuple[list[int], int]:
    """Decode the receiver field, retaining the file's mixed byte order."""
    if pos >= len(body):
        raise ReplayError("command has no receiver/custom field")
    first = body[pos]
    if first & 0xC0 == 0x40:
        count = first & 0x3F
        pos += 1
    elif first & 0xC0 == 0x80:
        if pos + 2 > len(body):
            raise ReplayError("short two-byte receiver count")
        count = struct.unpack_from(">H", body, pos)[0] & 0x3FFF
        pos += 2
    elif first & 0xC0 == 0xC0:
        if pos + 4 > len(body):
            raise ReplayError("short four-byte receiver count")
        count = struct.unpack_from(">I", body, pos)[0] & 0x3FFFFFFF
        pos += 4
    else:
        if pos + 4 > len(body):
            raise ReplayError("short single receiver")
        return [struct.unpack_from(">I", body, pos)[0]], pos + 4

    end = pos + count * 4
    if end > len(body):
        raise ReplayError("receiver list runs past command")
    return [u32(body, p) for p in range(pos, end, 4)], end


def decode_command(body: bytes) -> dict[str, object]:
    if len(body) < 7:
        raise ReplayError("command body is too short")
    opcode = body[0]
    sender_flags = body[1]
    # body[2:6] is copied/opaque command context in the current evidence.
    receivers, pos = decode_receiver(body, 6)
    custom_type = body[pos]
    pos += 1
    custom_length = 0
    if custom_type != 0xFF:
        if pos >= len(body):
            raise ReplayError("custom field has no length")
        high = body[pos]
        pos += 1
        if high < 0x80:
            custom_length = high
        else:
            if pos >= len(body):
                raise ReplayError("two-byte custom length is truncated")
            custom_length = ((high & 0x7F) << 8) | body[pos]
            pos += 1
        if pos + custom_length != len(body):
            raise ReplayError(
                f"custom payload length {custom_length} does not fit "
                f"remaining {len(body) - pos} bytes"
            )
    elif pos != len(body):
        raise ReplayError("custom type 0xff has an unexpected payload")
    return {
        "opcode": opcode,
        "sender_flags": sender_flags,
        "sender_slot": sender_flags & 0x7F,
        "process_type": (sender_flags >> 7) & 1,
        "receivers": receivers,
        "custom_type": custom_type,
        "custom_length": custom_length,
    }


def parse_sync(payload: bytes, stats: dict[str, object]) -> None:
    if len(payload) < 17 or payload[0] != 0x20:
        raise ReplayError("sync payload has no 0x20 marker/header")
    tick, counter, unknown, bundle_count = struct.unpack_from("<IIII", payload, 1)
    stats["sync_records"] = int(stats["sync_records"]) + 1
    stats["ticks_max"] = max(int(stats["ticks_max"]), tick)
    stats["bundles"] = int(stats["bundles"]) + bundle_count
    pos = 17
    for _ in range(bundle_count):
        if pos + 12 > len(payload):
            raise ReplayError("action bundle header runs past sync payload")
        opaque = payload[pos : pos + 8]
        declared = u32(payload, pos + 8)
        pos += 12
        if pos >= len(payload):
            raise ReplayError("action bundle has no length echo")
        echo = payload[pos]
        pos += 1
        if echo != declared & 0xFF:
            raise ReplayError(
                f"bundle length echo 0x{echo:02x} != 0x{declared & 0xff:02x}"
            )
        bundle_end = pos + declared
        if bundle_end > len(payload):
            raise ReplayError("bundle command region runs past sync payload")
        consumed = 0
        while consumed < declared:
            if pos + 2 > bundle_end:
                raise ReplayError("command length runs past sync payload")
            command_length = u16(payload, pos)
            if command_length < 2 or pos + command_length > bundle_end:
                raise ReplayError(f"invalid command length {command_length}")
            command = decode_command(payload[pos + 2 : pos + command_length])
            stats["commands"] = int(stats["commands"]) + 1
            opcodes = stats["opcodes"]
            assert isinstance(opcodes, dict)
            key = str(command["opcode"])
            opcodes[key] = int(opcodes.get(key, 0)) + 1
            pos += command_length
            consumed += command_length
        if consumed != declared:
            raise ReplayError("bundle command lengths do not sum to declaration")
        if pos != bundle_end:
            raise ReplayError("bundle command region has an unconsumed tail")
        # Empty bundles carry a zero byte after their declaration.  Non-empty
        # bundles do not have a per-command terminator; the next bundle starts
        # immediately after the last command.  This is the boundary that the
        # old parser's unconditional seek skipped.
    if pos != len(payload):
        raise ReplayError("sync payload has an unconsumed tail")


def inspect(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    result: dict[str, object] = {
        "file": str(path),
        "size": len(data),
        "header": header(data),
        "chunks": [],
        "sync_records": 0,
        "chat_records": 0,
        "bundles": 0,
        "commands": 0,
        "ticks_max": 0,
        "opcodes": {},
    }
    # The 36-byte Relic Chunky prelude is not a normal chunk.  The first
    # actual chunk starts at 0x78, followed by a 36-byte metadata gap before
    # DATASDSC at 0xd8.  This is stable in the supplied public samples.
    # This is the supported layout for the analysed writer.  Validate the
    # recognizable chunks around the opaque 36-byte gaps rather than silently
    # treating an arbitrary offset as a replay.
    first = chunk_at(data, 120, len(data))
    if first.name != "FOLDPOST" or first.end != 180:
        raise ReplayError("unsupported Chunky prelude/FOLDPOST layout")
    if not first.children or first.children[0].name != "DATADATA":
        raise ReplayError("FOLDPOST does not contain DATADATA")
    scenario = chunk_at(data, first.end + 36, len(data))
    if scenario.offset != 216 or scenario.name != "DATASDSC":
        raise ReplayError("unsupported scenario Chunky layout")
    foldinfo = chunk_at(data, scenario.end, len(data))
    if foldinfo.name != "FOLDINFO":
        raise ReplayError(
            f"expected FOLDINFO after scenario chunk, got {foldinfo.name!r}"
        )
    chunks = [first, scenario, foldinfo]
    stream_start = foldinfo.end
    result["chunks"] = [
        {"name": c.name, "offset": c.offset, "version": c.version, "size": c.size, "end": c.end}
        for c in flatten(chunks)
    ]
    pos = stream_start
    while pos < len(data):
        if pos + 8 > len(data):
            raise ReplayError(f"short outer record at 0x{pos:x}")
        record_type, payload_length = struct.unpack_from("<II", data, pos)
        payload_start = pos + 8
        payload_end = payload_start + payload_length
        if payload_end > len(data):
            raise ReplayError(f"outer record at 0x{pos:x} runs past EOF")
        payload = data[payload_start:payload_end]
        if record_type == 0:
            parse_sync(payload, result)
        elif record_type == 1:
            result["chat_records"] = int(result["chat_records"]) + 1
        else:
            raise ReplayError(f"unknown outer record type {record_type} at 0x{pos:x}")
        pos = payload_end
    if pos != len(data):
        raise ReplayError("record stream does not end at EOF")
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replay", type=Path, nargs="+")
    args = parser.parse_args(argv)
    for path in args.replay:
        try:
            print(json.dumps(inspect(path), sort_keys=True))
        except (OSError, ReplayError, struct.error) as exc:
            print(f"{path}: {exc}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
