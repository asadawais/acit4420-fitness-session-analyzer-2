# Smart Fitness Session Analyzer

Option A, ACIT4420 Problem-solving with scripting, assignment II.

Asad Mohammad Awais, S374979.

## What it does

The program reads a file of participant profiles and one or more files of
session measurements. It checks every row, throws out the ones that are broken
and writes down why. It then groups the good rows into sessions, compares each
session with the participant's own baseline and says what kind of session it
was: resting, moderate activity, high activity, recovering, or insufficient
data if there is not enough left to say anything.

Assignment I did the same analysis on data from a generator. Assignment II
keeps the classes and the classification from assignment I and adds reading
real CSV files, row validation, error handling and output files.

Standard library only, no installs.

## Running it

Run everything from the project folder, the one holding `main.py`.

```
python3 main.py
```

With no arguments it uses `data/participants.csv`, both session files in
`data/` and writes to `output/`. The assignment asks for the valid and the
invalid file to be loaded, so both are the default. This is the same as:

```
python3 main.py --profiles data/participants.csv --sessions data/fitness_sessions.csv data/fitness_sessions_invalid.csv --output output
```

| Option | Meaning |
|---|---|
| `--profiles` | The participant profile file |
| `--sessions` | One or more session files |
| `--output` | Folder for the results. Created if it does not exist |

`python3 main.py --help` lists the options.

To run the tests:

```
python3 -m unittest
```

If `python3` does not work on your machine, use `python`.

All paths are relative, so the program must be started from the project folder.

## Output

Each run replaces these three files in the output folder:

| File | What is in it |
|---|---|
| `analysis_summary.csv` | One row per analysed session: participant, accepted rows, usable rows, classification, averages, difference from baseline, drop from peak and the reasons |
| `analysis_report.txt` | An overview table, then a readable explanation of every session, then the sessions that had no valid rows left |
| `rejected_records.txt` | Every rejected row with file, line number, field and reason. A row with several problems gets one line per field. Session files that could not be read are listed at the end |

The program also prints a short summary:

```
Smart Fitness Session Analyzer
Participants loaded: 3 from data/participants.csv
Session files read:  2 of 2
Accepted rows:       30 (25 usable, 5 not usable because of low signal quality)
Rejected rows:       10
Sessions analysed:   6
No valid rows left:  FIT-2026-102, FIT-2026-103
Created files:
  output/analysis_summary.csv
  output/analysis_report.txt
  output/rejected_records.txt
```

**Accepted** and **usable** are not the same thing. An accepted row is well
formed. A usable row is accepted and also has good enough signal quality to be
used in the analysis. More on that below.

## Package layout

```
main.py                    command line, kept thin
fitness_analyzer/
    exceptions.py          the custom exceptions
    models.py              Participant, Observation, Session
    validation.py          ID patterns, row parsing, range and quality rules
    loader.py              reads the CSV files, groups rows into sessions
    analysis.py            statistics, recovery check, classification
    reporting.py           writes the three output files
tests/                     unit tests, one file per module
data/                      the official CSV files, not changed
```

Each module has one job. `main.py` only reads the arguments, calls the package
and handles the errors that should stop the program.

## Input files

`participants.csv`: `participant_id, name, baseline_heart_rate,
baseline_skin_response, baseline_temperature`

Session files: `session_id, participant_id, timestamp, heart_rate,
skin_response, temperature, activity_level, signal_quality`

Files are opened with `encoding="utf-8"` and `newline=""` and read with the
`csv` module. Numbers are converted to `int` (timestamp) or `float` (the
measurements). Rows are grouped by `session_id`, and each session is linked to
the `Participant` object from the profile file. A session can be spread over
more than one file.

## Validation

There are two levels, and keeping them apart was the main design decision.

**1. Rejected rows.** The row is broken and is left out completely. It is
written to `rejected_records.txt`. A row is rejected if:

| Problem | Example from the invalid file |
|---|---|
| Wrong number of columns | the row with only 7 columns |
| A required field is empty | empty `activity_level` |
| A value cannot be converted | `fast` as heart rate, `two` as timestamp |
| A participant ID does not match `P` + three digits | `001` |
| A session ID does not match `FIT-` + four digits + `-` + three digits | `FIT-26-102` |
| The participant is not in the profile file | `P999` |
| A value is outside its range | heart rate `-15`, signal quality `1.40` |
| The participant does not match earlier rows of the same session | none in the official data |
| The timestamp is already used in the same session | none in the official data |

All the problems in a row are reported, not just the first. The row in the
invalid file with skin response `-0.50`, temperature `55.0` and activity `1.30`
gets three lines in `rejected_records.txt`.

IDs are checked with `re.fullmatch`, so `P001x` or `P001` with a trailing
newline do not slip through. Regular expressions are used only for IDs. Numbers
are converted with `int()` or `float()` and then compared with the limits.

Ranges, kept from assignment I:

| Field | Allowed |
|---|---|
| `heart_rate` | 35 to 205 |
| `temperature` | 25 to 42 |
| `skin_response` | 0 or more |
| `activity_level` | 0 to 1 |
| `signal_quality` | 0 to 1 |
| `timestamp` | whole number, 0 or more |

The limits themselves are allowed, so a heart rate of exactly 35 or a signal
quality of exactly 0 is accepted. `nan` and `inf` are rejected as not finite.

Timestamps only have to be 0 or more and not repeated within a session. Gaps
are fine. When row 1 of a session is rejected, rows 0 and 2 are still accepted.
Requiring every number in sequence would let one bad row knock out the rows
after it.

When rows of one session name different participants, the first accepted row
decides who the session belongs to, and the rows that disagree are rejected.

**2. Rows that are accepted but not usable.** Poor signal quality is a
measurement problem, not a broken row, so these rows are accepted and counted,
but they are not used for the averages or the classification.

### The signal-quality rule

**A row is usable only if `signal_quality` is 0.60 or higher.** Exactly 0.60
counts as usable. Below 0.60 the row is accepted but not usable.

This is the same rule as in assignment I. There the clean scenarios had a
session mean signal quality of 0.88 to 0.93 and the poor-quality one had 0.23
to 0.40. In the official files the clean sessions sit between 0.92 and 0.98
and FIT-2026-005 between 0.25 and 0.34. The 0.60 cutoff is in a wide gap in
both cases, so I did not have to change or tune it for the new data.

A signal quality above 1 is different. That value is impossible, so the row is
rejected, not just marked unusable.

## Error handling

The program only catches errors where it can add useful context or carry on.
There are no empty `except` blocks and no `except Exception`.

| Situation | What happens | Where |
|---|---|---|
| Bad value or ID in a row | `InvalidIdentifierError` or `InvalidRecordError` is raised, caught, and the row is recorded. Reading moves on to the next row | `validation.py`, `loader.py` |
| Text that is not a number | the `ValueError` from `int()` or `float()` becomes an `InvalidRecordError` naming the field | `validation.py` |
| Unknown participant | the `KeyError` from the participant lookup becomes an `InvalidRecordError` | `validation.py` |
| Session file missing, a folder, or not readable | `FileNotFoundError`, `IsADirectoryError`, `PermissionError` are caught, the file is listed as skipped and the next file is read | `loader.py` |
| Session file with a wrong header or empty | `DataFileError`, file skipped | `loader.py` |
| Session file that is not UTF-8 | `UnicodeDecodeError` (a kind of `ValueError`), file skipped | `loader.py` |
| Broken CSV in the middle of a file | `csv.Error` is caught, the rows read so far are kept and the rest of the file is skipped | `loader.py` |
| Profile file missing or unusable | same exceptions as above, but the program stops with a clear message and exit code 1, because nothing can be analysed without participants | `main.py` |
| No session file could be read | output is still written, then the program exits with code 1 | `main.py` |
| Output folder cannot be written | `PermissionError`, or `FileExistsError`/`NotADirectoryError` if the path is a file, stops the program with a message | `main.py` |

The custom exceptions are in `exceptions.py`:

- `InvalidIdentifierError(ValueError)`, raised for an ID that does not match its pattern
- `InvalidRecordError(ValueError)`, raised for a row that cannot be accepted. It
  holds a list of `(field, reason)` pairs so one error can describe several bad
  fields
- `DataFileError`, raised when a whole file cannot be used, for example a
  missing column in the header

## Classification

The checks run in this order, and the order matters.

**1. Insufficient data.** Fewer than 4 usable rows, or fewer than half of the
accepted rows usable.

The 4 comes from assignment I, where sessions had 12 rows. The official
sessions only have 5 or 6, so I checked whether 4 still makes sense. It does,
for a concrete reason: 4 is the smallest number of rows the recovery check can
work with (a last third of at least 2 rows plus at least 2 rows before it for
the peak). With 5 or 6 rows, 4 usable rows also means at least two thirds of
the session is usable, so the 50 percent rule only matters for longer sessions.

FIT-2026-005 ends up here because all 5 of its rows have signal quality around
0.3. FIT-2026-101 ends up here because only 1 of its rows survived validation.

**2. Recovering.** The heart rate falls at least 15 bpm **and** the activity
level falls at least 0.25, measured from the peak of the session to the
average of its last third. The peak has to come before the last third. The
last third is never shorter than 2 rows, so one low final reading cannot
decide it alone.

**3. Intensity**, from the average heart rate above the participant's own
baseline.

| Result | Heart rate above baseline |
|---|---|
| Resting | under 12 bpm |
| Moderate activity | 12 to 45 |
| High activity | 45 and up |

Recovery is checked before intensity because a recovering session averages out
between moderate and high, so the average alone cannot tell them apart. Only
the fall can.

The thresholds 12, 45, 15 and 0.25 are the ones I calibrated in assignment I
from the generator data.

### Why split-half was replaced

In assignment I, recovery compared the first half of the session with the last
half. That worked with 12 rows. With 6 rows it does not. FIT-2026-004 clearly
peaks at 151 bpm and ends at 82, but its first half includes the warm-up row
of 72, which pulls the first-half average down. Split-half gives a fall of only
14.3 bpm and 0.23 activity, under both thresholds, so the session came out as
high activity.

Comparing the peak with the last third measures what recovery actually is,
coming down from a high point, and it does not depend on where the warm-up
sits. FIT-2026-004 then falls 58.0 bpm and 0.62 activity.

**FIT-2026-002 is close to the line.** From its peak of 118 to the last third
(110 and 98) it falls 14.0 bpm, against a threshold of 15. Its activity falls
0.18, against 0.25. It stays moderate activity because both values are under
the thresholds, but a slightly bigger fall in heart rate alone would not change
that, since recovery needs both.

### Results on the official data

| Session | Participant | Accepted | Usable | Result | Main reason |
|---|---|---|---|---|---|
| FIT-2026-001 | P001 | 6 | 6 | resting | 0.83 bpm above baseline |
| FIT-2026-002 | P002 | 6 | 6 | moderate activity | 28.0 bpm above baseline, fall of 14.0 bpm too small |
| FIT-2026-003 | P003 | 6 | 6 | high activity | 69.5 bpm above baseline |
| FIT-2026-004 | P001 | 6 | 6 | recovering | fell 58.0 bpm and 0.62 activity from the peak |
| FIT-2026-005 | P002 | 5 | 0 | insufficient data | all rows below signal quality 0.60 |
| FIT-2026-101 | P001 | 1 | 1 | insufficient data | 4 of its 5 rows were rejected |
| FIT-2026-102 | | 0 | 0 | not analysed | no valid rows remained |
| FIT-2026-103 | | 0 | 0 | not analysed | no valid rows remained |

The row with session ID `FIT-26-102` is rejected for its ID, so it does not
count towards FIT-2026-102.

## Classes

| Class | What it is responsible for |
|---|---|
| `Participant` | A person, their name and their three baseline values |
| `Observation` | One measurement row with its values converted to numbers |
| `Session` | A participant plus the observations from one session, in timestamp order |
| `ValidationRule` and four subclasses | One check each: missing value, impossible value, low signal quality, bad timestamp |
| `ObservationValidator` | Runs the rules over every observation in a session |
| `ProblemCollector` | Runs the field parsers for one row and collects every problem |
| `RejectedRecord`, `SkippedFile` | What went wrong with a row or a file |
| `SessionLoader` | Reads session files and builds the sessions |
| `SessionAnalyzer` | Summarises, compares with baseline and classifies |
| `SessionReport`, `DetailedSessionReport` | Turn a result into text |

Each analysis result is a dictionary with the session ID, participant,
quality counts, measurements, baseline comparison, trend, classification and
reasons.

From assignment I:

- **Composition.** A `Session` holds a `Participant` and `Observation` objects
  and the analyzer goes through them instead of copying values around.
  `ObservationValidator` holds a list of rule objects, so a new rule is one new
  subclass.
- **Encapsulation.** Baselines are read-only properties. An observation's
  validation result can only be set through `record_validation`, and lists are
  handed out as copies.
- **Inheritance.** Every rule overrides `ValidationRule.check`.
  `DetailedSessionReport` overrides `render` to add the rows that were not used.
  The report file uses the detailed version.

New in assignment II: the range rules are reused at load time. The parser
converts a row into an `Observation` and runs `ImpossibleValueRule` and
`OrderedTimestampRule` on it, so the limits are only defined in one place.

## Assumptions

- The baseline values in the profile file are correct.
- `session_id` decides which session a row belongs to, and the first accepted
  row decides the participant.
- Timestamps give the order inside a session. Rows are sorted by timestamp, so
  file order does not matter.
- A row is usable or it is not. One bad field rejects the whole row.

## Limitations

- The thresholds were calibrated on generated data and checked against six
  real sessions. That is too few to be sure about them, especially for
  recovery, where FIT-2026-002 is only 1 bpm under the threshold.
- Recovery needs a peak before the last third. A session that is still
  climbing at the end is not called recovering, even if it drops sharply in
  its final row.
- Validation checks each value on its own, not whether the values make sense
  together.
- A session spread over several files is merged, but there is no check that
  the files belong together beyond the session ID and participant.
- A `csv.Error` in the middle of a file stops reading that file. The rows
  before it are kept, but anything after it is lost.

## Declarations

The CSV files in `data/` were supplied with the assignment and I have not
changed them. Assignment I also used a supplied `data_generator.py`. This
version reads the CSV files instead, so the generator, the scripts built
around it and its data description have been removed.

I used Claude (Anthropic) as a supporting tool during parts of the project. It
was used to help clarify programming concepts, improve code structure and
documentation, assist with identifying appropriate classification thresholds
and improve the wording and organisation of the README. The implementation,
testing, interpretation of results and final design decisions were carried out
by me. I reviewed, tested and critically assessed all AI-assisted suggestions
before including them in the final work.
