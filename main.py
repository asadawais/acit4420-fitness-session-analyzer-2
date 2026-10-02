"""Smart Fitness Session Analyzer, command line entry point.

Run from the repository root:

    python3 main.py
    python3 main.py --profiles data/participants.csv \
        --sessions data/fitness_sessions.csv data/fitness_sessions_invalid.csv \
        --output output

With no arguments the profile file and both session files in data/ are used,
and the results are written to output/.
"""

import argparse
import csv
import sys
from pathlib import Path

from fitness_analyzer.analysis import SessionAnalyzer
from fitness_analyzer.exceptions import DataFileError
from fitness_analyzer.loader import SessionLoader, load_participants
from fitness_analyzer.reporting import write_outputs


DATA_DIR = Path("data")
DEFAULT_PROFILES = DATA_DIR / "participants.csv"
DEFAULT_SESSIONS = [
    DATA_DIR / "fitness_sessions.csv",
    DATA_DIR / "fitness_sessions_invalid.csv",
]
DEFAULT_OUTPUT = Path("output")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Check fitness session CSV files, classify each session "
                    "and write a summary, a report and a list of rejected rows.")
    parser.add_argument(
        "--profiles", type=Path, default=DEFAULT_PROFILES,
        help="participant profile CSV (default: %(default)s)")
    parser.add_argument(
        "--sessions", type=Path, nargs="+", default=DEFAULT_SESSIONS,
        help="one or more session CSV files (default: both files in data/)")
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help="folder for the output files, created if missing (default: %(default)s)")
    return parser


def fail(message):
    print("Error: " + message, file=sys.stderr)
    return 1


def load_profiles(path):
    """Load participants. Returns (participants, rejected, error_message).

    Without participants nothing can be analysed, so every problem here ends
    the run with a message instead of being skipped.
    """
    name = path.as_posix()
    try:
        participants, rejected = load_participants(path)
    except FileNotFoundError:
        return None, None, "profile file not found: " + name
    except IsADirectoryError:
        return None, None, "profile path is a folder, not a file: " + name
    except PermissionError:
        return None, None, "no permission to read the profile file: " + name
    except UnicodeDecodeError as error:
        return None, None, "profile file {0} is not valid UTF-8 text ({1})".format(
            name, error.reason)
    except DataFileError as error:
        return None, None, "cannot use the profile file {0}: {1}".format(
            name, error.reason)
    except csv.Error as error:
        return None, None, "profile file {0} is not valid CSV: {1}".format(name, error)

    if not participants:
        return None, None, "no valid participants in {0}, nothing to analyse".format(name)
    return participants, rejected, None


def completion_summary(run, results, created):
    accepted = run["accepted_rows"]
    usable = run["usable_rows"]
    lines = [
        "Smart Fitness Session Analyzer",
        "Participants loaded: {0} from {1}".format(
            run["participant_count"], Path(run["profile_file"]).as_posix()),
        "Session files read:  {0} of {1}".format(
            len(run["files_read"]), len(run["session_files"])),
        "Accepted rows:       {0} ({1} usable, {2} not usable because of "
        "low signal quality)".format(accepted, usable, accepted - usable),
        "Rejected rows:       {0}".format(len(run["rejected"])),
        "Sessions analysed:   {0}".format(len(results)),
    ]
    if run["empty_session_ids"]:
        lines.append("No valid rows left:  " + ", ".join(run["empty_session_ids"]))
    if run["skipped_files"]:
        lines.append("Warnings:")
        for skipped in run["skipped_files"]:
            lines.append("  {0}: {1}".format(skipped.path.as_posix(), skipped.reason))
    lines.append("Created files:")
    for path in created:
        lines.append("  " + path.as_posix())
    return "\n".join(lines)


def main(argv=None):
    args = build_parser().parse_args(argv)

    participants, profile_rejected, error = load_profiles(args.profiles)
    if error:
        return fail(error)

    loader = SessionLoader(participants).load_files(args.sessions)
    analyzer = SessionAnalyzer()
    results = [analyzer.analyze(session) for session in loader.sessions()]

    run = {
        "profile_file": args.profiles,
        "participant_count": len(participants),
        "session_files": args.sessions,
        "files_read": loader.files_read,
        "skipped_files": loader.skipped_files,
        "accepted_rows": loader.accepted_rows,
        "usable_rows": sum(result["quality"]["usable_rows"] for result in results),
        "rejected": profile_rejected + loader.rejected,
        "empty_session_ids": loader.empty_session_ids(),
    }

    try:
        created = write_outputs(args.output, results, run)
    except PermissionError as error:
        return fail("no permission to write to {0} ({1})".format(
            args.output.as_posix(), error.strerror))
    except (FileExistsError, NotADirectoryError):
        return fail("output path {0} exists but is not a folder".format(
            args.output.as_posix()))

    print(completion_summary(run, results, created))

    if not loader.files_read:
        return fail("none of the session files could be read")
    return 0


if __name__ == "__main__":
    sys.exit(main())
