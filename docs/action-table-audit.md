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
field table is therefore corrected at the wire level. Nine rows have positive
purchase/ability/building handler context, opcodes 44 and 61 have
build-local movement/selected-squad construction evidence, and opcode 43 has
partial stop/cancel-like evidence. The remaining 15 rows have no recovered
name-level handler proof; all names remain version-scoped annotations.

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
base convention. The four context bytes are wire-raw, but their command-issue
origin is partly recovered. `CommandIssueProxy` construction at `0xaf318f`
creates the first reserved `u16` through a virtual identity getter and the
second through a per-proxy counter; the issue method copies both words, calls
`WorldCommand::SetReserved`, and increments that counter. The getter's exact
game semantic name and any absolute counter limit remain unresolved.

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

A strict scan of all **30,373 commands** in the six-file audit corpus found
`u16_le(body[2..4]) == 1000 + (body[1] & 0x7f)` for every command. The next
reserved `u16` generally starts at zero and increases per sender, but
`recs/1.rec` has one sender stream reset from 1037 to zero. The serializer
only copies these four bytes. The native origin explains the observed pair as
identity-getter output plus per-proxy sequence state, while the supplied
evidence proves no 65,536-command limit or wraparound rule.

The relevant imports are `WorldCommand` constructor `0xf880dc` and
`SetReserved` `0xf880e4`. The setter xrefs are `0x41ed42` (reader-side
reconstruction) and `0xaf3138` (command-issue proxy); `0x985cf7` is a
constructor call and must not be used as a setter xref. The RTTI at
`0xaf318f` identifies the proxy as `CommandIssueProxy`, and its issue method
reads the virtual identity result into the first word, reads/increments the
16-bit counter for the second, then stores the four-byte reserved value.

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
| 5 | Cancel unit or wargear | `(5,4)` | type-5 `u32` shape observed; native cancellation queue-key handling is proven, but no direct opcode-5-to-key field cross-reference was recovered |
| 9 | Attack from placeable object | `(1,3)` | shape observed; gameplay label unverified |
| 11 | Set rally point | `(1,3)`, `(1,13)` | shapes observed; gameplay label unverified |
| 15 | Upgrade building | `(5,4)` | shape observed; gameplay label unverified |
| 23 | Exit building | `none` | opcode observed; gameplay label unverified |
| 43 | Stop move | `none`, `(1,1)` | shapes observed; gameplay label unverified |
| 44 | Move | `(1,3)`, `(1,5)`, `(1,13)`, `(3,26)`, `(6,17)`, `(8,30)`, `(18,17)` | native construction is movement-shaped; see dispatch audit; label is build-local |
| 47 | Capture point | `(1,5)` | shape observed; gameplay label unverified |
| 48 | Attack | `(1,3)`, `(1,5)`, `(1,13)` | shapes observed; gameplay label unverified |
| 49 | Reinforce unit | `(5,4)` | shape observed; gameplay label unverified |
| 50 | Purchase wargear | `(5,4)` | shape observed; purchase label unverified |
| 51 | Cancel wargear purchase | `(5,4)` | type-5 `u32` shape observed; native cancellation queue-key handling is proven, but no direct opcode-51-to-key field cross-reference was recovered |
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
* old rows 4--7 are one four-byte reserved context value. Its identity-getter
  plus per-proxy-counter origin is now proven, but the getter's game semantic
  name remains unresolved; and
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

## Archive and semantic audit corrections

The archive audit checked the six replay identities against the pinned DOW2 and
SimEngine builds. It supports several context labels while keeping the actual
attribute name lookup unresolved:

* Opcodes 3, 5, 15, 49, 50, and 51 all use the observed type-5/length-4
  envelope in the corpus. Their payload is a full little-endian `u32`; it is
  not a one-byte item ID. The Tyranid sample `05 01 00 00` is `261`, and the
  Space Marine/Ordo Malleus tier sample `be 01 00 00` is `446`, not `190`.
  The purchase, upgrade, reinforce, and cancellation contexts are repeatable
  sample contexts, but no supplied archive proves a universal name-to-value
  table for them.
* Opcode 53 uses the observed type-25/26/27/28 forms and opcode 85 uses the
  observed type-25/26/27/28/29 forms. DOW2 readers at `0x814350` and
  `0x814400` branch on custom tags 25 and 26 and then consume command-owned
  payload pointers and lengths. This confirms tag selectors and packed-reader
  boundaries, while the ability names remain context labels.
* Opcode 78's type-15/length-35 payload is emitted for a base receiver. The
  type-15 writer at `0x941440` calls `0x812a40`; that helper serializes the
  observed 35-byte form as `4 + 12 + 12 + 1 + 4 + 2` bytes (the last two
  pieces are variable-width packed entity/squad fields in the generic helper).
  The replay samples additionally show two visible float triples and a
  seven-byte tail. The geometry layout is proven by repeated samples; the
  leading and tail fields and the displayed building name are not.

* The runtime cancellation handlers at `0x437d32` and `0x43834c` walk a
  twelve-byte command queue, pass each stored `u32` key through `0x41ea96`,
  notify `WorldCommandManager::NotifyCommandCancel`, destroy the command, and
  compact the queue. This proves a runtime queue-key/cancellation mechanism.
  The available callers do not directly establish that opcode 5 or 51's
  custom type-5 `u32` is that key, so the replay-to-handler association stays
  unresolved.

The archive names and old “Item ID” table are therefore useful annotations,
not proof that the integer is comparable between builds. A name-to-ID claim
requires the exact attribute archive and catalog/load order that created the
replay. The available SGA overlays do not provide that proof.

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

## Native command-construction audit

The generic serializer cannot name an action, but the analysed DOW2 executable
also contains callers that construct commands with literal opcode arguments.
Those callers are stronger evidence than a replay-only correlation. They show
which engine path emits a byte and which target/codec objects are assembled;
they still do not make the byte a stable enum across builds.

| opcode | construction evidence in the analysed DOW2 build | conclusion for the old label |
| ---: | --- | --- |
| 23 | `0xa7515e..0xa752ba` and `0xaf4913..0xaf49fb` call `WorldDoCommandEntities`/`WorldDoCommandEntity` with `SingleTargetData` or `DualTargetData`; target fields are reset from squad/entity values. | **Corrected:** this is a target-bearing entity command in this build. The supplied call paths contain no building/vehicle-specific method proving “exit building”. |
| 43 | `0x8d13ae` emits the byte for either the owner squad or entity after clearing an owner-pointer queue; `0x96b921` emits it after opcode `0x2a` and immediately changes entity state. Additional squad callers occur at `0x9dc409`, `0x9e6334`, `0xa71e7a`, and `0xb75e54`. | **Partly confirmed:** a stop/cancel-like command path is native-confirmed, but no exported symbol names the byte “stop move”; keep the old name as build-local. |
| 44 | At `0x7eab49..0x7eabd1`, the caller prepares a `Vector3f`, invokes imported `GetSquadStateProcessor` and `SquadStateProcessor::DefaultCommand`, then pushes squad, player, `false`, and literal `0x2c` into `WorldDoCommandSquad`; a returned command is queued with the same vector. Other callers occur at `0xa7003f` and `0x9de480`. | **Confirmed in this build as the squad movement/default-position order for this path.** Other 0x2c call sites may represent different state paths; the opcode remains version-specific. |
| 48 | `0x985f20`, `0x9a81f8`, `0x9cadf7`, `0x9dc3cb`, `0xa10fd5`, `0xa7024b`, and `0xb7081d` emit the byte through squad constructors. The surrounding paths build target data or squad groups, but no native name “attack” is retained. | **Wire and target context confirmed; gameplay name remains unverified.** |
| 52 | `0x9395c6` emits the byte after constructing a squad group and `FlagTargetBoolData`; the follow-up codec writer at `0x941340` writes custom tag `7`. Similar target paths occur at `0xa0e515` and `0xa6ffcd`. | **Corrected:** target-plus-flag construction is confirmed; “attack move” is not proven by the stripped symbols. |
| 56 | `0x9ca599`, `0x9dbbf5`, and `0xaf4cf4` emit the byte after constructing target data from entity/squad objects. | **Corrected:** entity/squad target context is confirmed; no vehicle/building transition call is present in the searched callers. |
| 58 | `0xaf4b2c`, `0xaf4b89`, `0xaf4be4`, and `0xaf4c1b` emit the byte for squad groups after `DualTargetData`/`SingleTargetData` construction. | **Corrected:** squad target context is confirmed; “exit vehicle” is not proven by these callers. |
| 61 | `0xb5f0e7` checks input key `0x85`, filters eligible squads, and emits the byte with `WorldDoCommandSquads`; target/squad paths also occur at `0x9de5f2` and `0x9e04ac`. | **Strong build-local support for a retreat/selected-squad command**, but the stripped binary has no semantic method name; preserve the numeric opcode and raw fields. |
| 70 | `0xb70cd3` filters squads by property/state predicates and emits the byte with `WorldDoCommandSquads`. | **Corrected:** filtered squad command is confirmed; no force-melee operation is identified in the recovered call path. |
| 71 | `0xb76ae1` checks `SquadController::QI(..., 8)` and a state helper for each squad before emitting the byte with `WorldDoCommandSquads`. | **Corrected:** a squad-state toggle-like path is confirmed; “toggle stance” is a context label, not a recovered enum name. |

This audit searched the direct `WorldDoCommand*` imports, the
`WorldCommand::DoCommand`/`BaseState::ProcessCommand` call chain, and the
`WorldCommandWriteStream::SetCustomData` callers in the pinned DOW2 build.
The game passes the opcode into generic constructors, then dispatches through
virtual controller/state methods. No complete switch mapping byte values to
human names survived in the supplied symbols or disassembly. The table above
therefore records positive constructor evidence where available and states the
exact boundary where semantic recovery stops; it does not turn an unresolved
label into a universal “unknown” claim for every other game or mod version.
