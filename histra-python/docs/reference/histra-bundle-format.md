# Single-file simulation studies (`.histra`, container schema 1.0.0)

A `.histra` file is a ZIP64-capable archive using ZIP LZMA compression. It stores
summary curves, numerical arrays, the source HRX when available, and optional
attachments in one file. It does not contain nested NPZ archives. Identical
arrays, including repeated topology across analyses, share one stored payload.
All stored numerical bits are preserved: no rounding, quantization, change of
precision, or removal of simulation steps is performed by bundling.

The container schema is independent of the package version and the
[numerical schema](native-results-format.md). Bundling old exports preserves
their values and units, including any historical unit mistakes; it cannot repair
missing fields or results that were never exported. No additional Python runtime
dependency is required beyond the existing NumPy dependency.

## Export and read

After running the desired analyses:

```python
from histra import SimulationResults

path = session.export_bundle("results/bridge.histra")
print(SimulationResults.list_cases(path))  # analysis names, e.g. Vert, LiveLoad_1

with SimulationResults.load(path, case_id="LiveLoad_1") as result:
    displacement_mm, force_kN = result.get_pushover_curve()
    corner_displacements_cm = result.get_quad_displacement_field(step=-1)
    original_hrx = result.get_model_source()  # bytes; KeyError if unavailable
```

`SimulationResults.load_session(path)` returns a mapping of case IDs to readers;
close every reader when done. Readers share an archive handle. Listing cases and
opening readers load only the manifest; accessing an array decompresses that
array on demand. A multi-case bundle requires `case_id` for `load`; a single-case
bundle can omit it. Existing topology, spring and displacement accessors work
with both bundled and split-file results.

`session.export_analysis(..., format="histra")` writes a single-case bundle and
returns `{"bundle": path}`. `session.export_session(..., format="histra")` writes
one bundle and returns every analysis name mapped to the same bundle path.
The direct `export_bundle` API returns the path. Session exports retain the most
recent execution of each analysis. The existing `tier` and
`include_node_displacements` options also apply; use their defaults to retain
both summaries and all available dense fields.

The source HRX is embedded if `model.source_path` exists, checked against the
summary's source hash. In-memory models can be bundled without an HRX. The HRX
is the source model, while each case's mesh and spring arrays describe its
prepared export state. Reading results never extracts files or reruns a solver.

## Convert an existing study

```console
python -m histra.tools.pack_results results --output bridge.histra --model bridge.hrx
python -m histra.tools.pack_results results --output bridge.histra --model bridge.hrx --attach study_metrics.json
```

The converter discovers `*.summary.json`, `*.fields.npz` and `*.fields.h5` in the
input directory, respects declared field references, and uses their filename
stems as case IDs. Existing `*.session.json` indexes are embedded as attachments.
HDF5 input requires `h5py`. Explicit `--model` is preferred; otherwise the
converter checks the input directory and nearby `models` directories for the
source basename. A model hash mismatch aborts conversion. Arbitrary unrelated
JSON files require `--attach`; their original bytes are retained.

By default all source files remain. Add `--remove-source` only after the producer
has finished: after verification, the converter removes packed summary/field
files and obsolete session indexes whose references were all packed. It retains
HRX files and explicit attachments. Cleanup is restricted to files inside the
input directory. Cases created after discovery are outside the snapshot and
remain untouched. The converter checks source size and modification times
before publication and cleanup; this is not a lock against concurrent writers.

An existing destination requires `--overwrite`. Writing uses a sibling temporary
file; every unique numerical payload and embedded file is verified before
atomic publication. Failed writes preserve the previous destination. You can
also run `histra.verify_bundle(path)` to read and checksum all payloads later.
`result.attachment_names`, `result.get_attachment(name)` and
`result.bundle_metadata` expose embedded reports and study metadata.

## Layout for other consumers

The archive has these members:

| Member | Meaning |
|---|---|
| `manifest.json` | UTF-8 JSON: format, versions, case summaries, array descriptors and references |
| `objects/<digest>.bin` | Byte-shuffled raw array bytes, individually LZMA-compressed |
| `models/<sha256>.hrx` | Original HRX bytes, shared across cases |
| `attachments/<sha256><suffix>` | Original optional attachment bytes |

The manifest declares `format: "histra-results"`, `schema_version: "1.0.0"`,
`array_encoding: "byte-shuffle-v1"`, `compression: "ZIP_LZMA"`, creation time,
generator and `metadata`. `cases` is an object keyed by case ID. Each case has
`summary` (the native summary object or null), `arrays` (native array key to
object digest), `model_sha256` (nullable), and `curve_only`.

Each `objects[digest]` descriptor has `dtype` (NumPy `dtype.str`, including byte
order), `shape` (list of dimensions; empty for scalars) and `nbytes`. Supported
arrays have fixed-size, non-object, non-structured dtypes. Object/pickle payloads
are rejected. Native keys such as `mesh/quad_keys` and `fields/U` retain their
original names in each case's array mapping.

To encode an array, first obtain its raw C-order bytes. For item size `s` and
`n` elements, reshape the bytes to `(n, s)`, transpose to `(s, n)`, and write
those bytes in C order. Decode by reversing that operation, then interpreting
the original dtype and shape. This rearrangement groups similar bytes for
compression and is fully reversible, including NaN payloads and signed zeros.

The object digest is SHA-256 of the concatenation of:

1. Compact JSON `[dtype.str, shape]`, using separators `(',', ':')`;
2. One zero byte;
3. The original unshuffled C-order array bytes.

Empty arrays have zero payload bytes. Dtype and shape participate in the hash,
so identical bytes with different interpretations cannot share an object.
Models and attachments use SHA-256 of their original bytes. Their descriptors
contain `filename`, `member`, `sha256` and `nbytes`; models are keyed by digest,
attachments by logical filename. No absolute source path is required. Summaries
refer to the bundle basename and case ID instead of loose files. Attachment
contents and caller-supplied metadata are retained verbatim and may contain
application-specific paths.

## Compression and access tradeoffs

This format favors a small, portable study file over frequent incremental writes.
LZMA compression and complete verification can take longer than NPZ export.
Adding cases requires writing a new archive. Numerical arrays are separate
archive members, but an individual array is decoded in full: requesting one
step of a large history still decompresses that history array. Consumers should
retain frequently reused arrays in memory. This is not a solver restart format.

The ZIP container is standard, but its array encoding requires a `.histra` reader;
a generic NPZ reader or existing viewer will need an adapter. Browser consumers
need ZIP LZMA decoding as well as the reversible byte shuffle. HDF5 remains an
optional split-file export when chunked access is more useful than packaging.
VTU export remains an explicit compatibility tool; `.histra` export creates no
VTU or loose JSON/NPZ files.
