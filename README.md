# Documentation claim auditor

Check written promises against Python call evidence using an offline static audit.
The tool reads the root README and Markdown documents beneath any docs path
component. Source is parsed without execution. It uses no network or telemetry
and writes no files.

## Usage

Python 3.9 or newer is required.

```sh
python3 -m pip install .
instrument-recognition-claim-audit /path/to/project
python3 -m instrument_recognition_claim_audit /path/to/project --json
```

Repeat `--ignore PATH` to exclude relative path prefixes. Use `--verbose` for
inspected paths and evidence flags. The `--fail-on` threshold accepts LOW,
MEDIUM, or HIGH and defaults to HIGH. Findings at or above the threshold exit 2;
other successful audits exit 0. Usage and I/O errors exit 1. `--version` prints
0.1.0. JSON reports a verdict and findings containing identifiers, severities,
and messages.

## Rules

Matching uses paragraphs, lowercase text, expanded negative contractions,
spaces in place of hyphens, collapsed whitespace, and word boundaries.
Longer phrases take priority, with alphabetical ties. Negative spans are
removed before affirmative matching. Fenced blocks are excluded and inline
code counts.

```text
Instrument-named calls and InstrumentClassifier construction/predict pairs
supply evidence within a single module.
documented-instrument-recognition-claim-false HIGH
The same identifier has MEDIUM severity for evidence only in tests.
documented-no-instrument-recognition-claim-false HIGH
```

Imported aliases are resolved; local definitions suppress matching calls.
A paired constructor must feed its prediction receiver. Tests count separately.
Fixtures, examples, documentation source, symlinks, and invalid syntax do not
supply production evidence. Positive promises without source produce findings;
negative promises without source pass. Static indicators do not prove runtime
correctness or model quality.

## Development

```sh
python3 -m unittest discover
python3 -m build
```

Distributed under the MIT license.
