# WorldCommand custom data

This note narrows the part of a replay command after the receiver field. It is
based on the exported `SimEngine.dll` methods and the call sites in the
analysed `DOW2.exe`; the binaries and disassembly are deliberately not checked
into this repository. The command's `custom_type` byte is a gameplay command
namespace. It is separate from the internal data-kind byte used by
`SimCommandData` and from attribute blueprint/group IDs.

The framing is described in [`replay-format.md`](replay-format.md). The
dependency-free [`tools/replay_command_inventory.py`](../tools/replay_command_inventory.py)
reports opcode, custom type, payload length, and receiver-kind combinations
without publishing payloads. For the five checked samples it observes custom
types including 1, 3, 5, 6, 8, 12, 15, 16, 18, 19, 25--29, and 39. Those are
observations, not a complete enum: an absent type may simply not occur in the
sample corpus.

## Wire facts

`WorldCommandWriteStream` writes the following fields in order:

* The command opcode is one byte. The sender/flags byte is one byte. The
  serializer obtains the sender's player ID and subtracts the engine's player
  base; a null sender becomes `0x7f`. The high bit is the command process type.
* `WorldCommand::GetReserved()` returns four bytes and the serializer copies
  all four bytes verbatim. Their observed `u16`-plus-sequence pattern is useful
  for correlation, but their semantics are not established.
* A single receiver is emitted as a packed **big-endian** word
  `(receiver_type << 28) | instance_id`. A receiver list has a tagged count in
  big endian, followed by each packed receiver word in **little endian**. The
  receiver decoder masks the type to two bits in this build. Types 0, 1, and 2
  are player, entity, and squad; the type is not an attribute blueprint ID.
* `custom_type` is `0xff` for no custom data. Otherwise the length is one byte
  for values below `0x80`, or two bytes where the first byte has its high bit
  set and carries length bits 14..8. Payload bytes are copied exactly. The
  serializer does not write the `trusted` flag.

The sender high bit is backed by a native field rather than inferred solely
from replay bytes: `WorldCommand::GetCommandProcessType` returns object offset
`+0x04`, and `WorldCommand::IsQueued` returns true exactly when that field is
`1`. The writer emits that same value as the sender byte's high bit. This is
the evidence for the commonly called *queue/process flag*; other queue state
is held by `WorldCommandQueue` and is not serialized in this command body.

The static writer/reader evidence is at DOW2 virtual addresses `0x41e8da`
through `0x41ed80`, receiver helpers `0x41e61b` and `0x41e5c8`, and the
decoder path beginning at `0x41ebcc`. The corresponding SimEngine exports are
`WorldCommand::SetCustomDataRaw`, `SimCommandData::GetUnsignedFromCustom`, and
`SimCommandData::GetTargetFromCustom`.

## SimCommandData codec

SimEngine's `SimCommandData` helpers make a useful distinction that was
missing from the old action tables:

1. A **custom type** selects a command handler's data contract. In the
   analysed build, `GetUnsignedFromCustom` switches on custom types 5 through
   9. Type 5 takes a four-byte unsigned value directly; this is independently
   visible in replay samples where type 5 has length four and little-endian
   values such as `bf 00 00 00`. The remaining cases pass through typed
   unpackers and are not globally meaningful without the calling opcode.
2. `GetTargetFromCustom` has a separate switch for target-bearing custom types
   (the call site explicitly special-cases types 25 and 26). Its result is a
   `Target` structure, not a receiver word. A target may therefore identify a
   location or another simulation object while the command receiver identifies
   the controller that receives the command. The complete gameplay meaning of
   each target case is not established by the generic helper alone.
3. The typed `SimCommandData` classes expose pack/unpack methods. Their static
   call sequences establish the following payload composition, with primitive
   values written in the engine's little-endian stream format:

   | class | pack sequence proven by call sites |
   | --- | --- |
   | `SingleTargetData` | one generic target |
   | `SingleTargetBoolData` | one generic target, then one bool byte |
   | `DualTargetData` | two generic targets |
   | `DualTargetBoolData` | two generic targets, then one bool byte |
   | `FlagData` | one four-byte value |
   | `FlagTargetData` | one generic target, then one four-byte value |
   | `FlagTargetBoolData` | one generic target, one four-byte value, one bool byte |
   | `FlagDualTargetData` | two generic targets, then one four-byte value |
   | `FlagPositionData` | one four-byte value, then a position (12 bytes for the plain position path; a 3-byte compact path is selected for a non-null simulation object) |
   | `SquadCustomData` | squad pointer/identity packer, with the exact object identity resolved by the squad manager |

   The generic data-kind byte used by the packer has values 2 through 5 for
   target, position, entity, and squad paths. Its high bit carries a boolean
   flag. This byte is internal to the `SimCommandData` codec; it must not be
   confused with the command `custom_type` byte. The target path carries three
   primitive words (the disassembly copies two words and a third word); the
   position path carries three 32-bit words in the plain form. The entity and
   squad paths resolve through the world manager, so a replay-only decoder
   should retain their raw bytes unless it has the matching simulation state.

The exported functions and RVAs provide reproducible anchors for this table:

```text
SimCommandData::GetUnsignedFromCustom    0x10021c70
SimCommandData::GetTargetFromCustom      0x10021e00
SingleTargetData::Pack/Unpack             0x10021440 / 0x10021450
SingleTargetBoolData::Pack/Unpack         0x100214a0 / 0x100214e0
DualTargetData::Pack/Unpack                0x10021580 / 0x100215a0
DualTargetBoolData::Pack/Unpack            0x100215c0 / 0x10021610
FlagData::Pack/Unpack                      0x10021660 / 0x10021690
FlagTargetData::Pack/Unpack                0x10021700 / 0x10021740
FlagTargetBoolData::Pack/Unpack            0x100217c0 / 0x10021820
FlagDualTargetData::Pack/Unpack            0x100218e0 / 0x10021930
FlagPositionData::Pack/Unpack              0x10021ad0 / 0x10021b30
SquadCustomData::Pack/Unpack               0x10021ba0 / 0x10021c20
```

## What replay samples establish

The inventory shows stable, contextual patterns rather than a global ID table.
In `purchases_SM.rec`, opcode 3 repeatedly targets entity instance `19055`
(`0x10004a6f`) while its type-5 payload values vary (219, 221, 216, 215,
217). Opcode 50 targets squad instance `50000` (`0x2000c350`) with a type-5
value of 407. This proves that a type-5 u32 is a command-specific token; it is
not a universally comparable blueprint ID. The same numeric token can only be
named after following the opcode's gameplay handler and the corresponding
version's attribute tables.

The supplied static evidence does **not** prove a complete purchase or ability
name map, a queue flag enum, or the meaning of every opcode. In particular,
the command process bit and the receiver list are wire facts, while queueing,
purchase tokens, ability selection, positions, and target semantics remain
opcode- and version-specific. A safe parser should preserve the opcode,
reserved bytes, custom type, custom length, raw payload, receiver type, and
receiver instance even when it cannot assign a gameplay name.
