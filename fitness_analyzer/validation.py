"""Validation for CSV rows and for individual observations.

Two levels are kept apart on purpose:

- A malformed row (bad ID, missing field, text that is not a number, value
  outside the physical range, unknown participant) is rejected while loading
  and written to rejected_records.txt. parse_session_row and
  parse_participant_row handle this level.
- A row that is well formed but measured with poor signal quality is accepted,
  but not used for the analysis. The ValidationRule classes, run by
  ObservationValidator, handle this level.

Each rule returns a list of (field, reason) pairs. An empty list means the
observation passed that rule.
"""

import math
import re

from .exceptions import InvalidIdentifierError, InvalidRecordError
from .models import Observation, Participant


# Below this the device does not trust its own reading. In the official data
# the clean sessions sit between 0.92 and 0.98 and FIT-2026-005 between 0.25
# and 0.34. Assignment I saw the same split (0.88 to 0.93 against 0.23 to 0.40),
# so 0.60 sits in a wide gap and was not tuned to the new files.
MINIMUM_SIGNAL_QUALITY = 0.60

# Physical limits, kept from Assignment I.
HEART_RATE_RANGE = (35, 205)
TEMPERATURE_RANGE = (25.0, 42.0)
ACTIVITY_LEVEL_RANGE = (0.0, 1.0)
SIGNAL_QUALITY_RANGE = (0.0, 1.0)
SKIN_RESPONSE_MINIMUM = 0.0

# Identifiers are the only thing checked with regular expressions.
PARTICIPANT_ID_PATTERN = re.compile(r"P\d{3}")
SESSION_ID_PATTERN = re.compile(r"FIT-\d{4}-\d{3}")

PARTICIPANT_COLUMNS = (
    "participant_id",
    "name",
    "baseline_heart_rate",
    "baseline_skin_response",
    "baseline_temperature",
)

MEASUREMENT_FIELDS = (
    "heart_rate",
    "skin_response",
    "temperature",
    "activity_level",
    "signal_quality",
)

SESSION_COLUMNS = ("session_id", "participant_id", "timestamp") + MEASUREMENT_FIELDS


def show_number(value):
    """Print a number without trailing zeros, so 55.0 reads as 55."""
    if isinstance(value, float):
        return "{0:g}".format(value)
    return str(value)


def is_number(value):
    # bool is a subclass of int in Python, so exclude it explicitly.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def range_problem(field, value, lower, upper):
    """A (field, reason) pair when value is outside lower to upper, else None."""
    if value < lower or value > upper:
        return (field, "{0} is outside the range {1} to {2}".format(
            show_number(value), show_number(lower), show_number(upper)))
    return None


class ValidationRule:
    """Base class for validation rules. Subclasses override check."""

    def __init__(self, name):
        self.name = name

    def check(self, observation):
        raise NotImplementedError("each rule must implement check")

    def __repr__(self):
        return "{0}(name={1!r})".format(type(self).__name__, self.name)


class MissingValueRule(ValidationRule):
    """Reject observations where a required field is absent or not numeric."""

    REQUIRED_FIELDS = MEASUREMENT_FIELDS

    def __init__(self):
        super().__init__("missing value")

    def check(self, observation):
        problems = []
        for field in self.REQUIRED_FIELDS:
            value = getattr(observation, field, None)
            if value is None:
                problems.append((field, "is missing"))
            elif not is_number(value):
                problems.append((field, "is not a number"))
            elif isinstance(value, float) and math.isnan(value):
                # NaN compares false against everything, so the range check
                # below would let it through. It has to be caught here.
                problems.append((field, "is not a number"))
        return problems


class ImpossibleValueRule(ValidationRule):
    """Reject observations holding values outside the physical ranges."""

    def __init__(self):
        super().__init__("impossible value")

    def check(self, observation):
        problems = []

        checks = (
            ("heart_rate", observation.heart_rate, HEART_RATE_RANGE),
            ("temperature", observation.temperature, TEMPERATURE_RANGE),
            ("activity_level", observation.activity_level, ACTIVITY_LEVEL_RANGE),
            ("signal_quality", observation.signal_quality, SIGNAL_QUALITY_RANGE),
        )

        for field, value, (lower, upper) in checks:
            # Missing fields are skipped, MissingValueRule already flagged them.
            if not is_number(value):
                continue
            problem = range_problem(field, value, lower, upper)
            if problem:
                problems.append(problem)

        skin = observation.skin_response
        if is_number(skin) and skin < SKIN_RESPONSE_MINIMUM:
            problems.append(("skin_response", "{0} is below {1}".format(
                show_number(skin), show_number(SKIN_RESPONSE_MINIMUM))))

        return problems


class SignalQualityRule(ValidationRule):
    """Flag observations the device reported low confidence in.

    A value exactly at the minimum is usable.
    """

    def __init__(self, minimum=MINIMUM_SIGNAL_QUALITY):
        super().__init__("low signal quality")
        self.minimum = minimum

    def check(self, observation):
        quality = observation.signal_quality
        if not is_number(quality):
            return []
        if quality < self.minimum:
            return [("signal_quality", "{0} is below the usable minimum of {1}".format(
                show_number(quality), show_number(self.minimum)))]
        return []


class OrderedTimestampRule(ValidationRule):
    """Reject observations without a usable position in the session.

    Only a whole number of 0 or more is required. Gaps are allowed, since a
    rejected row leaves one behind. Duplicates are caught by the loader,
    because they can only be seen across rows.
    """

    def __init__(self):
        super().__init__("bad timestamp")

    def check(self, observation):
        timestamp = observation.timestamp
        if not isinstance(timestamp, int) or isinstance(timestamp, bool):
            return [("timestamp", "is missing or not a whole number")]
        if timestamp < 0:
            return [("timestamp", "{0} is negative".format(timestamp))]
        return []


class ObservationValidator:
    """Runs a collection of rules over every observation in a session.

    Rows loaded from CSV have already passed the range and timestamp rules,
    so for them only the signal quality rule can still fire. The other rules
    stay in the default list so a hand-built Observation is checked the same
    way.
    """

    def __init__(self, rules=None):
        if rules is None:
            rules = [
                MissingValueRule(),
                ImpossibleValueRule(),
                SignalQualityRule(),
                OrderedTimestampRule(),
            ]
        self.rules = list(rules)

    def validate_observation(self, observation):
        """Return (rule name, field, reason) for every problem found."""
        found = []
        for rule in self.rules:
            for field, reason in rule.check(observation):
                found.append((rule.name, field, reason))
        observation.record_validation(
            [(field, reason) for _, field, reason in found])
        return found

    def validate_session(self, session):
        """Validate every observation and return a summary dictionary."""
        problem_counts = {}
        for observation in session.observations:
            # Count each rule once per row, even if it found several fields.
            rule_names = {name for name, _, _ in self.validate_observation(observation)}
            for name in rule_names:
                problem_counts[name] = problem_counts.get(name, 0) + 1

        usable = len(session.usable_observations())
        total = session.total_count

        return {
            "total_rows": total,
            "usable_rows": usable,
            "unusable_rows": total - usable,
            "usable_ratio": round(usable / total, 3) if total else 0.0,
            "problem_counts": problem_counts,
        }


# --- Row level: turning CSV text into checked values -----------------------

def check_participant_id(text):
    if PARTICIPANT_ID_PATTERN.fullmatch(text) is None:
        raise InvalidIdentifierError(
            "participant_id", text, "P followed by three digits, like P001")
    return text


def check_session_id(text):
    if SESSION_ID_PATTERN.fullmatch(text) is None:
        raise InvalidIdentifierError(
            "session_id", text, "FIT-, four digits, -, three digits, like FIT-2026-001")
    return text


def required_text(row, field):
    """The stripped text of one field, which must not be empty."""
    text = (row.get(field) or "").strip()
    if not text:
        raise InvalidRecordError.single(field, "is empty")
    return text


def parse_identifier(row, field, check):
    return check(required_text(row, field))


def parse_float(row, field):
    text = required_text(row, field)
    try:
        value = float(text)
    except ValueError:
        raise InvalidRecordError.single(
            field, "{0!r} is not a number".format(text)) from None
    if not math.isfinite(value):
        raise InvalidRecordError.single(
            field, "{0!r} is not a finite number".format(text))
    return value


def parse_int(row, field):
    text = required_text(row, field)
    try:
        return int(text)
    except ValueError:
        raise InvalidRecordError.single(
            field, "{0!r} is not a whole number".format(text)) from None


def find_participant(participants, participant_id):
    try:
        return participants[participant_id]
    except KeyError:
        raise InvalidRecordError.single(
            "participant_id",
            "unknown participant {0}, not in the profile file".format(participant_id),
        ) from None


class ProblemCollector:
    """Runs field parsers and gathers their errors instead of stopping at the
    first one, so a row with several bad values lists all of them."""

    def __init__(self):
        self.problems = []

    def take(self, function, *args):
        try:
            return function(*args)
        except InvalidIdentifierError as error:
            self.problems.append((error.field, str(error)))
        except InvalidRecordError as error:
            self.problems.extend(error.problems)
        return None

    def add(self, problems):
        self.problems.extend(problem for problem in problems if problem)

    def raise_if_any(self):
        if self.problems:
            raise InvalidRecordError(self.problems)


def parse_participant_row(row):
    """Build a Participant from one profile row, or raise InvalidRecordError."""
    collect = ProblemCollector()
    participant_id = collect.take(
        parse_identifier, row, "participant_id", check_participant_id)
    name = collect.take(required_text, row, "name")
    heart_rate = collect.take(parse_float, row, "baseline_heart_rate")
    skin_response = collect.take(parse_float, row, "baseline_skin_response")
    temperature = collect.take(parse_float, row, "baseline_temperature")

    if heart_rate is not None:
        collect.add([range_problem("baseline_heart_rate", heart_rate, *HEART_RATE_RANGE)])
    if temperature is not None:
        collect.add([range_problem("baseline_temperature", temperature, *TEMPERATURE_RANGE)])
    if skin_response is not None and skin_response < SKIN_RESPONSE_MINIMUM:
        collect.add([("baseline_skin_response", "{0} is below {1}".format(
            show_number(skin_response), show_number(SKIN_RESPONSE_MINIMUM)))])

    collect.raise_if_any()
    return Participant(participant_id, heart_rate, skin_response, temperature,
                       name=name)


def parse_session_row(row, participants):
    """Check one session row and convert it.

    Returns (session_id, participant, observation), or raises
    InvalidRecordError listing every problem in the row.
    """
    collect = ProblemCollector()
    session_id = collect.take(parse_identifier, row, "session_id", check_session_id)
    participant_id = collect.take(
        parse_identifier, row, "participant_id", check_participant_id)
    participant = None
    if participant_id is not None:
        participant = collect.take(find_participant, participants, participant_id)

    timestamp = collect.take(parse_int, row, "timestamp")
    values = {field: collect.take(parse_float, row, field)
              for field in MEASUREMENT_FIELDS}
    observation = Observation(timestamp=timestamp, **values)

    # Range checks reuse the Assignment I rules. They skip fields that failed
    # to convert, so nothing is reported twice.
    collect.add(ImpossibleValueRule().check(observation))
    if timestamp is not None:
        collect.add(OrderedTimestampRule().check(observation))

    collect.raise_if_any()
    return session_id, participant, observation
