"""Reading the participant and session CSV files.

Every file is opened with encoding="utf-8" and newline="" and read with the
csv module. Bad rows are recorded as RejectedRecord objects and reading moves
on to the next row. Problems that make a whole session file unusable are
recorded and the loader moves on to the next file. The profile file is
different: without participants nothing can be analysed, so its errors are
left for the caller to stop on.
"""

import csv
from pathlib import Path

from .exceptions import DataFileError, InvalidRecordError
from .models import Session
from .validation import (
    PARTICIPANT_COLUMNS,
    SESSION_COLUMNS,
    SESSION_ID_PATTERN,
    parse_participant_row,
    parse_session_row,
)


class RejectedRecord:
    """One row that could not be accepted, and why."""

    def __init__(self, source, line, problems, session_id=None):
        self.source = Path(source)
        self.line = line
        self.problems = list(problems)
        # Only set when the row's session ID itself was valid, so a session
        # whose rows were all rejected can still be named in the report.
        self.session_id = session_id

    def __repr__(self):
        return "RejectedRecord({0}, line {1}, {2})".format(
            self.source.as_posix(), self.line, self.problems)


class SkippedFile:
    """A session file that could not be read, or was only partly read."""

    def __init__(self, path, reason):
        self.path = Path(path)
        self.reason = reason

    def __repr__(self):
        return "SkippedFile({0}, {1!r})".format(self.path.as_posix(), self.reason)


def read_rows(path, required_columns):
    """Yield (line_number, header, values) for every non-blank data row.

    Raises DataFileError if the file is empty or the header lacks a required
    column. FileNotFoundError, PermissionError, UnicodeDecodeError and
    csv.Error are left to the caller, which knows whether to stop or skip.
    """
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header is None:
            raise DataFileError(path, "the file is empty")

        header = [name.strip() for name in header]
        # Spreadsheet programs sometimes save a byte order mark in front.
        header[0] = header[0].lstrip("﻿")
        missing = [column for column in required_columns if column not in header]
        if missing:
            raise DataFileError(
                path, "the header is missing column(s): " + ", ".join(missing))

        for values in reader:
            if not any(value.strip() for value in values):
                continue
            yield reader.line_num, header, values


def row_to_dict(header, values):
    """Pair values with column names. The column count must match exactly."""
    if len(values) != len(header):
        raise InvalidRecordError.single(
            "row", "has {0} columns, expected {1}".format(len(values), len(header)))
    return dict(zip(header, values))


def session_id_hint(header, values):
    """The row's session ID if it is present and valid, otherwise None."""
    if "session_id" not in header:
        return None
    index = header.index("session_id")
    if index >= len(values):
        return None
    text = values[index].strip()
    if SESSION_ID_PATTERN.fullmatch(text):
        return text
    return None


def load_participants(path):
    """Read the profile file into {participant_id: Participant}.

    Returns (participants, rejected_records). File errors are not caught here.
    """
    participants = {}
    rejected = []
    for line, header, values in read_rows(path, PARTICIPANT_COLUMNS):
        try:
            participant = parse_participant_row(row_to_dict(header, values))
            if participant.participant_id in participants:
                raise InvalidRecordError.single(
                    "participant_id",
                    "duplicate participant {0}, the first row for it is kept".format(
                        participant.participant_id))
        except InvalidRecordError as error:
            rejected.append(RejectedRecord(path, line, error.problems))
        else:
            participants[participant.participant_id] = participant
    return participants, rejected


class _SessionDraft:
    """Accepted rows for one session_id, collected before the Session is built."""

    def __init__(self, session_id, participant, source, line):
        self.session_id = session_id
        self.participant = participant
        self.first_row = (Path(source), line)
        self.observations = []
        self.timestamp_rows = {}
        self.sources = []

    def add(self, participant, observation, source, line):
        """Add one row, or raise InvalidRecordError if it conflicts."""
        source = Path(source)
        if participant.participant_id != self.participant.participant_id:
            first_source, first_line = self.first_row
            raise InvalidRecordError.single(
                "participant_id",
                "{0} conflicts with session {1}, which already belongs to {2} "
                "(from {3} line {4})".format(
                    participant.participant_id, self.session_id,
                    self.participant.participant_id, first_source.name, first_line))

        if observation.timestamp in self.timestamp_rows:
            first_source, first_line = self.timestamp_rows[observation.timestamp]
            raise InvalidRecordError.single(
                "timestamp",
                "duplicate timestamp {0} in session {1}, already used by "
                "{2} line {3}".format(
                    observation.timestamp, self.session_id,
                    first_source.name, first_line))

        self.timestamp_rows[observation.timestamp] = (source, line)
        self.observations.append(observation)
        if source not in self.sources:
            self.sources.append(source)

    def build(self):
        return Session(self.participant, self.observations,
                       session_id=self.session_id, sources=self.sources)


class SessionLoader:
    """Reads one or more session files and groups accepted rows by session_id."""

    def __init__(self, participants):
        self.participants = participants
        self.rejected = []
        self.skipped_files = []
        self.files_read = []
        self.accepted_rows = 0
        self._drafts = {}

    def load_files(self, paths):
        for path in paths:
            self.load_file(path)
        return self

    def load_file(self, path):
        """Read one session file. File problems are recorded, not raised."""
        path = Path(path)
        last_line = 1
        try:
            for line, header, values in read_rows(path, SESSION_COLUMNS):
                last_line = line
                self._accept_row(path, line, header, values)
        except FileNotFoundError:
            self.skipped_files.append(SkippedFile(path, "file not found"))
        except IsADirectoryError:
            self.skipped_files.append(SkippedFile(path, "is a folder, not a file"))
        except PermissionError:
            self.skipped_files.append(SkippedFile(path, "permission denied"))
        except UnicodeDecodeError as error:
            self.skipped_files.append(SkippedFile(
                path, "not valid UTF-8 text ({0})".format(error.reason)))
        except DataFileError as error:
            self.skipped_files.append(SkippedFile(path, error.reason))
        except csv.Error as error:
            # Rows before the broken line have already been accepted and are kept.
            self.files_read.append(path)
            self.skipped_files.append(SkippedFile(
                path, "CSV format error after line {0} ({1}), the rest of the "
                "file was not read".format(last_line, error)))
        else:
            self.files_read.append(path)

    def _accept_row(self, path, line, header, values):
        try:
            row = row_to_dict(header, values)
            session_id, participant, observation = parse_session_row(
                row, self.participants)
            draft = self._drafts.get(session_id)
            if draft is None:
                draft = _SessionDraft(session_id, participant, path, line)
                self._drafts[session_id] = draft
            draft.add(participant, observation, path, line)
        except InvalidRecordError as error:
            self.rejected.append(RejectedRecord(
                path, line, error.problems, session_id_hint(header, values)))
        else:
            self.accepted_rows += 1

    def sessions(self):
        """The built sessions, ordered by session ID."""
        return [self._drafts[key].build() for key in sorted(self._drafts)]

    def empty_session_ids(self):
        """Valid session IDs that appeared only in rejected rows."""
        seen = {record.session_id for record in self.rejected if record.session_id}
        return sorted(seen - set(self._drafts))
