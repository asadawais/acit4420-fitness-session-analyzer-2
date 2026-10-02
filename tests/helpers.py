"""Shared builders for the tests. Nothing here reads the official data."""

from pathlib import Path

from fitness_analyzer.models import Observation, Participant, Session


SESSION_HEADER = ("session_id,participant_id,timestamp,heart_rate,skin_response,"
                  "temperature,activity_level,signal_quality")
PROFILE_HEADER = ("participant_id,name,baseline_heart_rate,baseline_skin_response,"
                  "baseline_temperature")
PROFILE_LINES = [
    "P001,Test Person,70,1.20,32.4",
    "P002,Other Person,74,1.45,32.7",
]


def make_observation(**overrides):
    """A valid observation, with any field overridden for a specific test."""
    fields = {
        "timestamp": 0,
        "heart_rate": 110,
        "skin_response": 2.0,
        "temperature": 33.0,
        "activity_level": 0.5,
        "signal_quality": 0.9,
    }
    fields.update(overrides)
    return Observation(**fields)


def make_participant():
    return Participant("P001", 70, 1.8, 32.5, name="Test Person")


def make_session(heart_rates, activity_levels=None, signal_quality=0.9):
    """A hand-built session with one row per heart rate value."""
    if activity_levels is None:
        activity_levels = [0.5] * len(heart_rates)
    observations = [
        make_observation(timestamp=index, heart_rate=rate,
                         activity_level=level, signal_quality=signal_quality)
        for index, (rate, level) in enumerate(zip(heart_rates, activity_levels))
    ]
    return Session(make_participant(), observations, session_id="FIT-2026-900")


def make_mostly_faulty_session():
    """Four usable rows out of nine, so under half are usable."""
    observations = [
        Observation(0, 104, 2.1, 33.0, 0.52, 0.93),
        Observation(1, 106, 2.2, 33.1, 0.54, 0.92),
        Observation(2, 108, 2.2, 33.0, 0.55, 0.91),
        Observation(3, 105, 2.1, 33.1, 0.53, 0.90),
        Observation(4, None, 2.2, 33.0, 0.54, 0.91),
        Observation(5, 265, 2.1, 33.1, 0.52, 0.92),
        Observation(6, 107, None, 33.0, 0.55, 0.90),
        Observation(7, 106, 2.2, 33.1, -0.30, 0.91),
        Observation(8, 105, 2.1, 33.0, 0.53, 0.20),
    ]
    return Session(make_participant(), observations, session_id="FIT-2026-901")


def session_row(session_id="FIT-2026-001", participant_id="P001", timestamp="0",
                heart_rate="80", skin_response="1.5", temperature="32.8",
                activity_level="0.3", signal_quality="0.95"):
    """One session row as the dictionary the loader passes to the parser."""
    return {
        "session_id": session_id,
        "participant_id": participant_id,
        "timestamp": timestamp,
        "heart_rate": heart_rate,
        "skin_response": skin_response,
        "temperature": temperature,
        "activity_level": activity_level,
        "signal_quality": signal_quality,
    }


def write_lines(folder, name, lines):
    """Write a CSV file into a temporary folder and return its path."""
    path = Path(folder) / name
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write("\n".join(lines) + "\n")
    return path


def write_profiles(folder, lines=None):
    return write_lines(folder, "participants.csv",
                       [PROFILE_HEADER] + (PROFILE_LINES if lines is None else lines))


def write_sessions(folder, name, lines):
    return write_lines(folder, name, [SESSION_HEADER] + lines)
