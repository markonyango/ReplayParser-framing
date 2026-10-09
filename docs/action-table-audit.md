# Action table audit

This note audits every opcode label in the original README against the
recoverable replay writer/reader evidence. The executable and disassembly used
for the static analysis are not part of this repository, so addresses below
identify the analysed build and are not universal offsets for every release.
The evidence establishes the command envelope and several generic codecs. It
does not establish a complete opcode-to-gameplay enum.

Disposition summary: all 27 original rows have a structurally valid opcode
number, 25 occur in the six-file corpus, and 2 (1 and 98) do not occur there.
The generic writer confirms the opcode byte and envelope fields, but confirms
none of the 27 old gameplay names as a universal semantic enum. The fixed
field table is therefore corrected at the wire level; the named examples are
retained as historical, unverified observations.

## Correct wire model

The old table treated a command as a fixed 19-byte structure. The writer emits
an inclusive little-endian `u16` length followed by a variable command body:

```text
u16 command_size                 # includes these two bytes
u8  opcode                       # body offset 0
u8  sender_and_process_flags     # body offset 1
u8[4] reserved_command_context   # body offsets 2..5, copied verbatim
... receiver field ...
u8  custom_type                  # 0xff means no custom payload
... custom length and payload ...
```

The sender byte uses `sender = flags & 0x7f` and
`process = (flags >> 7) & 1`. Static analysis ties the high bit to the
serialized command process field (`WorldCommand::GetCommandProcessType` and
`WorldCommand::IsQueued`), while the low seven bits follow the engine's player
base convention. The four context bytes are reserved: samples often show a
little-endian value near `1000 + sender` followed by a sequence value, but
that pattern is not a proven semantic split.

A single receiver is a big-endian packed word:

```text
(receiver_type << 28) | instance_id
```

The observed receiver types are 0=player, 1=entity, and 2=squad. A receiver
list starts with a tagged big-endian count (`0x40..`, `0x8000..`, or
`0xc0000000..`) and stores each packed receiver word little endian. The type
nibble and the low 28-bit instance ID are runtime receiver fields; neither is
an attribute blueprint ID.

For a custom type other than `0xff`, a length below `0x80` is one byte. A
length with the high bit set uses two bytes:
`((first & 0x7f) << 8) | second`. Type 5 is proven to be a four-byte unsigned
data path in the generic simulation helper, but the value's gameplay meaning
still depends on the opcode and build. Unknown custom tags and their payloads
must remain opaque.

The generic writer/reader evidence is in the analysed DOW2 build at virtual
addresses `0x41e8da..0x41ed80` (command writer/reader), `0x41e61b` and
`0x41e5c8` (receiver helpers), and `0x41ebcc` (decoder path). The command
object offsets recovered from the constructors are `+0x00` opcode, `+0x04`
process value, `+0x0c` sender pointer, `+0x10` receiver storage, `+0x40`
custom payload, `+0x44` payload length, `+0x48` custom type, and `+0x49`
trusted state. The trusted state is not serialized.

The native evidence was taken from `DOW2.exe` SHA-256
`4ce6423d3d97528a784ede2a16bb9b671aac221fdde1fddee5bd060cfd38a50e` and
`SimEngine.dll` SHA-256
`a6d503cefe9085e9ee5ca707c8621e8855243b272fb93d6506e9f628a8c89af4`.
The more precise writer field sites are `0x41e94a` (opcode), `0x41e95b`
(process), `0x41e961`/`0x41e97a` (sender and flag), `0x41e98e` (reserved),
`0x41e9d3` (receivers), `0x41e9d8` (custom type), and `0x41e9f0` (custom
length). These addresses identify one analysed x86 build, not a stable public
ABI.

## Worked byte examples

This 18-byte command is a recorded opcode-3 command:

```text
12 00 03 03 eb 03 00 00 10 00 77 0c 05 04 86 00 00 00
```

The length is `0x12`; the body is the remaining 16 bytes. It decodes as:

| field | value |
| --- | --- |
| opcode | `3` |
| sender/process | sender slot `3`, process `0` |
| reserved context | `eb 03 00 00` (raw) |
| receiver | packed `0x1000770c`; type `1`, instance `30476` |
| custom | type `5`, length `4`, raw value `86 00 00 00` (`134` little endian) |

The old “unit ID” byte would have exposed only `0x0c`, the low byte of the
runtime receiver instance. That is why the same apparent unit ID changes
across sessions and versions.

A strict scan of all 20,434 commands in the five checked-in replays found
`u16_le(body[2..4]) == 1000 + (body[1] & 0x7f)` for every command. The next
reserved `u16` generally starts at zero and increases per sender, but one
sample resets from 1037 to zero. The serializer only copies these four bytes;
the supplied evidence proves no 65,536-command limit or wraparound rule.

This synthetic 18-byte command exercises a two-receiver list and the no-custom
sentinel:

```text
12 00 44 03 eb 03 00 00 42 34 12 00 10 cd ab 00 20 ff
```

The `0x42` count tag means two receivers. Their little-endian words decode to
`0x10001234` (type 1, instance `0x1234`) and `0x2000abcd` (type 2, instance
`0xabcd`). The final `0xff` is a custom-type sentinel with no length or
payload. The list count, receiver endianness, and sentinel are structural
facts; the opcode's gameplay name is not inferred here.

The worked examples are checked without external dependencies by running
`python3 tools/verify_action_table.py`.

## Verdict for every original opcode row

The “observed shapes” column comes from the six-file inventory (five checked
samples plus the local sixth replay). `none` means custom type `0xff`. A shape
proves only the generic payload contract, not the old gameplay label.

| opcode | Original README label | Observed shapes | Disposition |
| ---: | --- | --- | --- |
| 1 | Ability on placeable object | not observed | label unverified; no handler proof in supplied evidence |
| 3 | Build unit | `(5,4)` | opcode and type-5/length-4 shape observed; gameplay label unverified |
| 5 | Cancel unit or wargear | `(5,4)` | shape observed; cancellation label unverified |
| 9 | Attack from placeable object | `(1,3)` | shape observed; gameplay label unverified |
| 11 | Set rally point | `(1,3)`, `(1,13)` | shapes observed; gameplay label unverified |
| 15 | Upgrade building | `(5,4)` | shape observed; gameplay label unverified |
| 23 | Exit building | `none` | opcode observed; gameplay label unverified |
| 43 | Stop move | `none`, `(1,1)` | shapes observed; gameplay label unverified |
| 44 | Move | `(1,3)`, `(1,5)`, `(1,13)`, `(3,26)`, `(6,17)`, `(8,30)`, `(18,17)` | shapes observed; gameplay label unverified |
| 47 | Capture point | `(1,5)` | shape observed; gameplay label unverified |
| 48 | Attack | `(1,3)`, `(1,5)`, `(1,13)` | shapes observed; gameplay label unverified |
| 49 | Reinforce unit | `(5,4)` | shape observed; gameplay label unverified |
| 50 | Purchase wargear | `(5,4)` | shape observed; purchase label unverified |
| 51 | Cancel wargear purchase | `(5,4)` | shape observed; cancellation label unverified |
| 52 | Attack move | `(1,13)`, `(6,17)`, `(19,30)` | shapes observed; gameplay label unverified |
| 53 | Ability on unit | `(1,3)`, `(1,5)`, `(1,13)`, `(25,5)`, `(26,9)`, `(26,11)`, `(26,19)`, `(27,32)`, `(28,13)`, `(28,23)`, `(28,71)` | shapes observed; gameplay label unverified |
| 56 | Enter building or vehicle | `(1,3)`, `(1,5)` | shapes observed; gameplay label unverified |
| 58 | Exit vehicle | `none` | opcode observed in sixth replay; gameplay label unverified |
| 61 | Retreat | `none`, `(1,5)` | shapes observed; gameplay label unverified |
| 70 | Force melee | `(1,1)`, `(1,3)`, `(1,5)` | shapes observed; gameplay label unverified |
| 71 | Toggle stance | `(5,4)` | shape observed; gameplay label unverified |
| 78 | Place building | `(15,35)` | shape observed; gameplay label unverified |
| 85 | Global ability | `(25,5)`, `(26,9)`, `(26,19)`, `(27,32)`, `(28,59)`, `(28,71)`, `(29,40)`, `(29,88)` | shapes observed; gameplay label unverified |
| 89 | Unknown | `(16,35)` | opcode and shape observed; no gameplay label claimed |
| 94 | Unknown, source `0x0` | `(39,16)` | opcode and shape observed; source-byte claim unverified |
| 96 | Unknown, source `0x0` | `(12,14)` | opcode and shape observed; source-byte claim unverified |
| 98 | Unknown | not observed | no semantic or corpus evidence |

This is a conservative disposition: the replay corpus demonstrates that the
opcode bytes occur with the listed shape pairs, while the old names came from
small hand-labelled examples. Static generic command dispatch does not recover
a complete opcode switch, and no supplied attribute archive establishes a
global name map. The labels should therefore be retained as historical
hypotheses, not emitted as confirmed parser semantics.

## Why the old fixed rows fail

The old rows 1--19 were shifted by treating the first byte of the wire length
as an action field. After the inclusive `u16`, only the opcode and sender byte
have fixed positions. The next four bytes are copied reserved context; the
receiver field has one of four widths (single receiver or three count widths),
and the custom field is variable length. Consequently:

* old row 2 is the wire opcode and is structurally confirmed;
* old row 3 is the sender/process flags byte, not a player-location ID;
* old rows 4--7 are one four-byte reserved context value, not independently
  confirmed player ID/counter fields; and
* old rows 8 onward cannot be assigned fixed meanings because receiver count,
  receiver list width, custom tag, and custom length vary by command.

The large named examples below this audit are preserved as historical sample
observations. Their names and values should be read through the corrected wire
layout above; rows whose original byte columns do not match the command length
are incomplete examples, not proof of a different format.

The old `(custom_type, custom_length)` observations that survive strict
decoding are `(1,1)`, `(1,3)`, `(1,5)`, `(1,13)`, `(3,26)`, `(5,4)`, `(6,17)`,
`(8,30)`, `(12,14)`, `(15,35)`, `(16,35)`, `(18,17)`, `(19,30)`, `(25,5)`,
`(26,9)`, `(26,11)`, `(26,19)`, `(27,32)`, `(28,13)`, `(28,23)`, `(28,59)`,
`(28,71)`, `(29,40)`, `(29,88)`, and `(39,16)`. The old `(12,4)` and
`(32,84)` claims were not reproduced as strict custom type/length pairs in
the six-file corpus and remain incomplete observations.

## Evidence limits

The analysed writer proves the byte-level envelope and generic codecs. It does
not prove that a type-5 value is always a blueprint, purchase, wargear, or
unit ID, nor that a receiver instance is stable across recordings. Runtime
receiver IDs, queue values, and attribute blueprint/group indices are separate
namespaces. Matching a name across game or mod versions requires the replay's
data checksum and the matching attribute data, plus reconstruction of the
session's runtime group creation order.

See the command-codec research for the broader custom-tag dispatch inventory
and the replay-format research for runtime ID allocation evidence when those
documents are available in the repository.
