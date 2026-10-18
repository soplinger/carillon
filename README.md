# Carillon

**Offline change-ringing method checker.** Write a method as plain-text place notation, then check that it is true, trace each bell, and estimate how long a peal will take.

Carillon reads a small method file, expands the lead into rows, and reports whether one plain course contains any repeated row (a *false* method). It also shows how much of the stage's permutation space the course covers, traces where a chosen bell goes, and estimates ringing time. It runs entirely offline, uses only the Python 3 standard library, and needs no accounts or API keys.

## Features

- **Method files** with `name`, `stage` and `lead` keys, `#` comments, and both LF and CRLF line endings.
- **Place notation parsing** with `x` or `-` for plain changes, digit runs such as `16` for places, and bells 10–12 written as `0`, `E` and `T`.
- **Exact row generation** for stages 2 to 12, with odd-stage implicit places handled correctly.
- **Truth check**: finds every repeated row in one plain course, reports each pair by row index, and exits non-zero when the method is false, so it works as a CI gate.
- **Line-numbered errors** for bad keys, duplicate keys, bad stages, unknown characters, unordered places, and impossible changes. Errors go to stderr with exit code 2.
- **Summary** with lead length, course length in changes and leads, truth, and extent (distinct rows reached out of stage! possible).
- **JSON output** for `summary --json`, for scripts and dashboards.
- **Explain** each change of the first lead, with the row before and after and the places it makes.
- **Row listing** of a full plain course, with lead-end and course-end markers.
- **Bell path tracing** that shows one bell's position in every row as an ASCII blue line, plus how many rows it spends in each position.
- **Ringing time estimate** from a change count and seconds per change, giving courses rung and a `m:ss` or `h:mm:ss` duration with exact fractions.
- **Inline notation expansion** with `change`, which prints the rows produced by any place notation without a file.

## Quick start

The repository includes a four-bell example, `examples/demo-minor.method`:

```text
# Four-bell example: a lead of two changes, written as place notation.
name = Four-bell demo
stage = 4
lead = x14
```

Run the checker on it:

```bash
python3 carillon.py check examples/demo-minor.method
```

Expected output:

```text
examples/demo-minor.method: Four-bell demo (stage 4) is valid
course: 8 changes
TRUE: no row repeats within the plain course
```

Get the summary, then trace bell 2:

```bash
python3 carillon.py summary examples/demo-minor.method
python3 carillon.py path examples/demo-minor.method 2
```

Expected summary:

```text
Four-bell demo (stage 4)
  lead:    2 changes
  course:  8 changes (4 leads)
  truth:   TRUE
  extent:  8 of 24 rows (33.33%)
```

Expand notation without a file:

```bash
python3 carillon.py change 4 x14
```

## How to run

Requires Python 3.8 or newer. Run the commands from the repository root:

| Command | What it does |
| --- | --- |
| `check FILE` | Validate the file and test truth. Exit 0 if true, 1 if false, 2 on input errors. |
| `summary FILE [--json]` | Print course length, truth and extent. |
| `explain FILE` | Show each change of the first lead with the rows it connects. |
| `rows FILE` | Print every row of one plain course. |
| `path FILE BELL` | Trace one bell through the course. |
| `time FILE [--changes N] [--per-change SECONDS]` | Estimate ringing time for N changes (default 5000, 3 s per change). |
| `change STAGE NOTATION` | Expand inline place notation into rows from rounds. |

Method file format:

- `stage` is a whole number from 2 to 12. `lead` is place notation for one lead.
- `x` or `-` is a plain change. A run of place digits such as `16` is one change. Spaces, commas and dots are optional separators.
- Places must be listed in ascending order and must not exceed the stage. On an even stage, every position not listed as a place must pair with a neighbour.

## How to test

The tests use only `unittest`, so they run without installing anything:

```bash
python3 -m unittest discover -s tests -v
```

If pytest is installed, `python3 -m pytest` also collects and runs the same tests.

The suite covers change permutations, place notation parsing, method file errors with line numbers, plain course generation, falseness detection, summary numbers, duration formatting, and the CLI exit codes and output.

## Limits

- Carillon checks truth within one plain course only. It does not check falseness between two different methods, and it does not handle surprise or treble-dodging compositions.
- Ringing time is a simple `changes × seconds per blow` estimate, not a model of a specific bell ring.

## Layout

```text
carillon.py              the program (single file, standard library only)
examples/demo-minor.method   four-bell example used in the quick start
tests/test_carillon.py   unit and CLI tests
```
