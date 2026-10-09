import struct
import unittest

from tools.replay_inspect import ReplayError, parse_sync


def sync_payload(command_size=18, declared=18, trailing=b""):
    # opcode 3, sender 3, reserved bytes eb 03 00 00, one entity receiver,
    # type-5 custom value 134.
    body = bytes.fromhex("03 03 eb 03 00 00 10 00 77 0c 05 04 86 00 00 00")
    command = struct.pack("<H", command_size) + body
    return (
        b"\x20"
        + struct.pack("<IIII", 1, 0, 0, 1)
        + b"\0" * 8
        + struct.pack("<I", declared)
        + bytes([declared & 0xFF])
        + command
        + trailing
    )


def fresh_stats():
    return {"sync_records": 0, "ticks_max": 0, "bundles": 0, "commands": 0, "opcodes": {}}


class ReplayInspectorBoundaryTests(unittest.TestCase):
    def test_valid_command(self):
        stats = fresh_stats()
        parse_sync(sync_payload(), stats)
        self.assertEqual(stats["commands"], 1)

    def test_bundle_declaration_cannot_run_past_sync(self):
        with self.assertRaises(ReplayError):
            parse_sync(sync_payload(declared=19), fresh_stats())

    def test_command_cannot_run_past_bundle(self):
        with self.assertRaises(ReplayError):
            parse_sync(sync_payload(command_size=19), fresh_stats())

    def test_sync_tail_is_rejected(self):
        with self.assertRaises(ReplayError):
            parse_sync(sync_payload(trailing=b"\0"), fresh_stats())
