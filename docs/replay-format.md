# Dawn of War II replay format and identifiers

This note records the parts of the `.rec` format that are supported by static
analysis of the original x86 game and by boundary checks over the five replay
samples in this repository. It intentionally labels inference and open work.
The replay is a recording of simulation messages; it is not a self-contained
database of the unit and ability names that were active when it was recorded.

The dependency-free [`tools/replay_inspect.py`](../tools/replay_inspect.py)
checks these boundaries without trying to assign names to unknown opcodes or
attribute values:

```text
python3 tools/replay_inspect.py 3v3.rec recs/*.rec
```

The five checked samples contain 38,389 sync records, 20,434 commands, and 61
chat records. The checks are structural evidence, not a guarantee that every
future build uses every field in the same way.

## File creation and the fixed header

The writer identified in the supplied `DOW2.exe` writes the first 84 bytes as
follows. Integers in this table are little endian.

| Offset | Size | Meaning | Evidence |
| ---: | ---: | --- | --- |
| `0x00` | 4 | replay format/version (`0x2850` in the analysed build) | writer at `42b1..42b259` |
| `0x04` | 4 | data/mod checksum (`0x7a0a30` in the analysed build) | writer and validator |
| `0x08` | 4 | reserved, observed zero | writer |
| `0x0c` | 8 | ASCII `DOW2_REC` | writer |
| `0x14` | 64 | 32 UTF-16LE code units containing the date/time | writer |

The validator at `42b259` compares only the first byte of the magic in the
analysed build. A parser should still require all eight bytes, as the inspector
does. The validator also compares version and checksum.

The checksum is not a simple checksum of the mod label and it is not the file
MD5. The call chain at `7a0a30` obtains a sync token through
`PropertyBagGroupManager::GetSyncToken` (`81c1c0`) and builds a CRC over
`data:maps\\pvp\\_cameras\\*.*`. This is a data identity used by the game to
reject incompatible content; it is not enough to turn a replay into a
self-contained, cross-version representation.

After the fixed header the writer emits Relic Chunky data. In the public
samples there is a 36-byte Chunky prelude at `0x54..0x77`; the first normal
chunk is `FOLDPOST` at `0x78` (120). A normal Chunky header is 28 bytes:

```text
char[8] name
u32     version
u32     payload_size
u32[3]  per-chunk metadata (currently opaque)
byte[]  payload_size bytes
```

`FOLDPOST` contains `DATADATA` at 148 and ends at 180. Another 36 bytes of
metadata follow, then the scenario description chunk starts at 216. The
observed sequence includes `DATASDSC`, `FOLDINFO`, `DATABASE`, one `FOLDGPLY`
per player/observer, and `DATAINFO` inside those player folds. `FOLDINFO`'s
declared payload ends the header region; the outer records begin there. The
36-byte gaps and some fields inside the Chunky payloads remain undocumented.

## Outer records and action commands

The stream after `FOLDINFO` is a sequence of records:

```text
u32 record_type       # 0 = simulation sync, 1 = chat
u32 payload_size
byte[payload_size] payload
```

A sync payload starts with 17 bytes:

```text
u8  marker            # 0x20
u32 tick
u32 counter           # meaning not established
u32 unknown           # changes with simulation state
u32 bundle_count
```

Each bundle has an eight-byte opaque value and a four-byte command-byte
declaration. It then has one one-byte echo of the declaration's low byte and a
sequence of commands. Empty bundles carry a zero byte after their declaration;
non-empty bundles start their first command immediately after the echo.

Each command starts with an inclusive little-endian length. The length includes
the two length bytes and the command body:

```text
u16 command_size
u8  opcode
u8  sender_and_flags
u8[4] reserved/forwarded command context (often starts with a runtime player ID)
... receiver field ...
u8  custom_type       # 0xff means no custom field
... custom length and payload ...
```

The sender byte's low seven bits are the sender slot in the engine's player-ID
convention; `0x7f` is the no-sender value. Its high bit is the command process
type (the analysed handler uses value 1 for the process form). The old parser
treated the first length byte as part of the action body, which shifted the
opcode and discarded the last payload byte. For example, the 18-byte command

```text
12 00 03 03 eb 03 00 00 10 00 77 0c 05 04 86 00 00 00
```

has opcode `3`, sender byte `3`, receiver word `0x1000770c` (entity ID
30,476), custom type `5`, and a four-byte custom value `134`.

The four bytes after the sender are copied by the serializer and should be
treated as reserved until their individual uses are established. In observed
commands they often split into a `u16` value around `1000 + sender_slot` and a
two-byte sequence. The legacy parser joined messages to actions using the low
byte of that reserved value; that is a compatibility join key, not proof that
the field is the command's semantic sender ID.

Receiver words use a second, mixed-endian convention. A single receiver is a
big-endian `u32` whose high nibble is the receiver type and whose low 28 bits
are the instance ID:

| Type nibble | Meaning |
| ---: | --- |
| 0 | player |
| 1 | entity |
| 2 | squad |

For multiple receivers, the count is tagged in big-endian form: `0x40..0x7f`
for a one-byte count, `0x8000..0xbfff` for a two-byte count, or
`0xc0000000..` for a four-byte count. The receiver words following the count
are little-endian `u32` values. This deliberate mix of big- and little-endian
fields is one reason a byte dump is easy to misread.

The custom length is one byte for values below 128. Otherwise the high length
byte has its high bit set and the following byte is the low length byte. The
generic custom type `5` is `FlagData` and is read by the simulation as a
four-byte unsigned value. This does not prove that every type-5 value is a
purchase identifier.

The old table's apparent “unit ID” byte is the low byte of the receiver word,
not a blueprint ID. For example, the body

```text
03 00 e8 03 01 00 10 00 4a 65 05 04 bf 00 00 00
```

targets entity receiver `0x10004a65` (instance 19,045); the old byte would have
shown only `0x65`. Receiver bytes `10 00 78 ad` similarly carry instance
`0x78ad` (30,893), although the old byte is only 173. In `purchases_SM.rec`,
opcode-3 commands reuse entity instance `0x4a6f` while type-5 values vary, and
opcode-50 commands target squad instance 50,000 with different custom values.
These are separate command and runtime namespaces; no name-to-blueprint
mapping is proven for any token.

## How the game assigns IDs

Several unrelated numbers were called “unit ID” in the earlier tables. They
must be kept separate.

### Blueprint and purchase values

Attribute records are `PropertyBagGroup` objects. Static analysis observes the
group type at `+0x4c` and its attribute ID at `+0x50`. The fixed DOW2 mapping
table at `0x81bc10` registers `EBPs\\` as type 0 and `SBPs\\` as type 1,
alongside 28 other path/type pairs. `SavePBG` writes an attribute path string;
it does not serialize the replay's runtime receiver ID.

The purchase command's custom value is therefore not automatically a runtime
entity ID. Some command handlers use queue slots or blueprint-related values;
the complete purchase-handler mapping is still open. The old action tables
should be read as historical observations of values in particular data sets,
not as a global ID catalogue.

### Runtime groups and receivers

The attribute/simulation group table stores groups in a vector per group type.
`CreateAndAddNewGroup` uses `vector[type].size()` before appending, and
`GetGroup(type, id)` indexes that per-type table. This is a per-type catalog or
group-table index; it must not be treated as a universal unit ID or as the
runtime squad receiver ID. An empty-group sentinel uses IDs at or above
`0x7fffffff`.

The analysed type getters identify player, entity, and squad as types 0, 1,
and 2. The observed ID bases are 1,000, 10,000, and 50,000 respectively. The
SquadFactoryImp counter starts from the squad base, ensures it is greater than
a supplied ID, and passes the result to the squad constructor. Destroying a
squad does not decrement that counter. This is the proven runtime squad-ID
sequence; constructor ID storage alone does not prove equivalent lifetime or
reuse rules for every player/entity path.

Consequently, two replays can give the same blueprint different receiver IDs
because the blueprint/table index, squad factory sequence, and command timing
are different namespaces and lifetimes.

### Why versions and mods mingle IDs

The attribute loader creates groups in archive/load order. The RB2 path makes a
first pass that creates groups in entry order and a second pass that reads their
payloads. The RBF path applies type mappings and enumerates filesystem
wildcards. The exact within-type ordering is not established here and should
not be assumed to be alphabetical. Adding a blueprint, changing archive
ordering, or changing the startup scenario changes the numeric assignment
without changing the human-readable unit name.

The replay records numeric references plus a mod/data checksum; it does not
embed the complete attribute archive needed to resolve those references. A
parser using a different game version or mod can therefore decode a valid
number as another unit, and runtime entity/squad IDs can differ even when the
same blueprint is present. Cross-version comparison requires the matching
attribute data and the replay's checksum, plus a per-session reconstruction of
runtime group creation.

## Proven versus unresolved

The following are demonstrated by the supplied executable/static analysis and
the boundary-checked samples:

* the 84-byte header, magic, version/checksum fields, Chunky framing, outer
  record framing, sync/bundle/command lengths, receiver type tags, and the
  mixed receiver endianness;
* the separation between blueprint `PropertyBagGroup` IDs, per-type
  group-table indices, and runtime squad receiver IDs; the three type bases;
  and the squad counter lifetime behavior;
* the five-sample totals reported by `replay_inspect.py`.

These remain open and should not be guessed by a parser:

* the meaning of the 36-byte prelude/gaps and all sync counter fields;
* the semantics of every opcode, receiver context, and custom type;
* the exact purchase/cancel handler mapping from blueprint/queue values to
  replay custom payloads;
* complete RB2/RBF ordering rules across all releases and mods;
* a complete reconstruction of runtime group lifetimes from every command.

The checksum and format version should be exposed to callers, and numeric IDs
should be presented with their namespace and source build rather than treated
as stable names.
