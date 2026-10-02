"""Summary statistics, recovery detection and session classification."""

import statistics

from .validation import ObservationValidator


# A session needs enough usable rows to be summarised at all, and enough of its
# accepted rows must be usable for the summary to be representative.
# Four is the smallest count the recovery check can work with: a last third of
# at least two rows, plus at least two rows before it for the peak. With the
# five or six rows per session in the official data, four usable rows also
# means at least two thirds of the session is usable, so the ratio rule only
# matters for longer sessions.
MINIMUM_USABLE_ROWS = 4
MINIMUM_USABLE_RATIO = 0.5

# Heart rate above the participant's own baseline, in beats per minute.
# Calibrated in Assignment I: resting 0.8 to 3.2, moderate 25.7 to 30.2,
# high 54.5 to 61.4. The official sessions give 0.8, 28.0 and 69.5.
RESTING_CEILING = 12.0
MODERATE_CEILING = 45.0

# A recovering session falls from a peak to a clearly lower end. The drop is
# the peak minus the mean of the last third of the session, and the peak must
# come before that last third. Both heart rate and activity must drop, since
# either alone is noisier. The thresholds are kept from Assignment I.
# FIT-2026-004 drops 58.0 bpm and 0.62 activity. FIT-2026-002 drops 14.0 bpm
# and 0.18 activity, close to the heart rate threshold but under both.
RECOVERY_HEART_RATE_DROP = 15.0
RECOVERY_ACTIVITY_DROP = 0.25

# The last third is never shorter than two rows, so one noisy final reading
# cannot decide it alone.
MINIMUM_LAST_THIRD = 2

RESTING = "resting"
MODERATE = "moderate activity"
HIGH = "high activity"
RECOVERING = "recovering"
INSUFFICIENT = "insufficient data"


def average(values):
    """Mean of a list of numbers, or None when the list is empty."""
    if not values:
        return None
    return round(statistics.mean(values), 2)


def minimum_and_maximum(values):
    """Smallest and largest value, or (None, None) when the list is empty."""
    if not values:
        return (None, None)
    return (min(values), max(values))


def summarise(values):
    """Average, minimum, maximum and count for one measurement field."""
    lowest, highest = minimum_and_maximum(values)
    return {
        "average": average(values),
        "minimum": lowest,
        "maximum": highest,
        "count": len(values),
    }


def last_third_size(count):
    """How many values at the end count as the last third."""
    return max(MINIMUM_LAST_THIRD, count // 3)


def peak_before_last_third(values):
    """True when the highest value comes before the last third.

    Needs at least MINIMUM_USABLE_ROWS values, otherwise returns False.
    """
    if len(values) < MINIMUM_USABLE_ROWS:
        return False
    peak_index = values.index(max(values))
    return peak_index < len(values) - last_third_size(len(values))


def peak_to_end_drop(values):
    """Peak minus the mean of the last third. Positive means it declined.

    Returns None when there are too few values, or when the peak is inside
    the last third, since then the session did not come down from it.
    """
    if not peak_before_last_third(values):
        return None
    tail = values[-last_third_size(len(values)):]
    return round(max(values) - statistics.mean(tail), 3)


def percentage(part, whole):
    """Part of whole as a percentage, rounded to one decimal."""
    if not whole:
        return 0.0
    return round(100.0 * part / whole, 1)


class SessionAnalyzer:
    """Validates a session, summarises it and classifies its intensity."""

    def __init__(self, validator=None):
        self.validator = validator or ObservationValidator()

    def analyze(self, session):
        """Return a structured dictionary describing one session."""
        quality = self.validator.validate_session(session)
        usable = session.usable_observations()
        participant = session.participant

        heart_rates = [o.heart_rate for o in usable]
        activity_levels = [o.activity_level for o in usable]
        temperatures = [o.temperature for o in usable]
        skin_responses = [o.skin_response for o in usable]

        measurements = {
            "heart_rate": summarise(heart_rates),
            "activity_level": summarise(activity_levels),
            "temperature": summarise(temperatures),
            "skin_response": summarise(skin_responses),
        }

        comparison = self._compare_with_baseline(participant, measurements)
        trend = self._describe_trend(heart_rates, activity_levels)
        classification, reasons = self._classify(quality, comparison, trend)

        return {
            "session_id": session.session_id,
            "sources": list(session.sources),
            "participant_id": participant.participant_id,
            "participant_name": participant.name,
            "baselines": {
                "heart_rate": participant.baseline_heart_rate,
                "skin_response": participant.baseline_skin_response,
                "temperature": participant.baseline_temperature,
            },
            "quality": quality,
            "measurements": measurements,
            "comparison": comparison,
            "trend": trend,
            "classification": classification,
            "reasons": reasons,
            "unusable_detail": [
                {"timestamp": o.timestamp, "problems": o.problems}
                for o in session.rejected_observations()
            ],
        }

    def _compare_with_baseline(self, participant, measurements):
        """How far the session sat above the participant's own references."""
        def difference(method, value):
            if value is None:
                return None
            return round(method(value), 2)

        return {
            "heart_rate_above_baseline": difference(
                participant.heart_rate_above_baseline,
                measurements["heart_rate"]["average"],
            ),
            "temperature_above_baseline": difference(
                participant.temperature_above_baseline,
                measurements["temperature"]["average"],
            ),
            "skin_response_above_baseline": difference(
                participant.skin_response_above_baseline,
                measurements["skin_response"]["average"],
            ),
        }

    def _describe_trend(self, heart_rates, activity_levels):
        """Fall in heart rate and activity from the peak to the last third."""
        heart_rate_drop = peak_to_end_drop(heart_rates)
        activity_drop = peak_to_end_drop(activity_levels)

        declining = (
            heart_rate_drop is not None
            and activity_drop is not None
            and heart_rate_drop >= RECOVERY_HEART_RATE_DROP
            and activity_drop >= RECOVERY_ACTIVITY_DROP
        )

        return {
            "heart_rate_drop": heart_rate_drop,
            "activity_drop": activity_drop,
            "is_declining": declining,
        }

    def _classify(self, quality, comparison, trend):
        """Decide the session type and explain the decision.

        Order matters. Recovering sessions average between moderate and high,
        so checking intensity first would hide them.
        """
        reasons = []

        usable = quality["usable_rows"]
        if usable < MINIMUM_USABLE_ROWS:
            reasons.append(
                "only {0} of {1} rows were usable, at least {2} are needed".format(
                    usable, quality["total_rows"], MINIMUM_USABLE_ROWS
                )
            )
            reasons.extend(self._unusable_reasons(quality))
            return INSUFFICIENT, reasons

        if quality["usable_ratio"] < MINIMUM_USABLE_RATIO:
            reasons.append(
                "only {0}% of rows were usable".format(
                    percentage(usable, quality["total_rows"])
                )
            )
            reasons.extend(self._unusable_reasons(quality))
            return INSUFFICIENT, reasons

        elevation = comparison["heart_rate_above_baseline"]
        if elevation is None:
            reasons.append("no usable heart rate measurements")
            return INSUFFICIENT, reasons

        if trend["is_declining"]:
            reasons.append(
                "heart rate fell {0} bpm and activity fell {1} from the peak "
                "to the last third of the session".format(
                    trend["heart_rate_drop"], trend["activity_drop"]
                )
            )
            return RECOVERING, reasons

        reasons.append(
            "heart rate averaged {0} bpm above the personal baseline".format(elevation)
        )
        reasons.append(self._no_recovery_reason(trend))

        if elevation < RESTING_CEILING:
            return RESTING, reasons
        if elevation < MODERATE_CEILING:
            return MODERATE, reasons
        return HIGH, reasons

    @staticmethod
    def _unusable_reasons(quality):
        """One line per rule that made rows unusable, with its row count."""
        return [
            "{0} row(s) had {1}".format(count, name)
            for name, count in sorted(quality["problem_counts"].items())
        ]

    @staticmethod
    def _no_recovery_reason(trend):
        """Explain why a session with enough data was not called recovering."""
        heart_rate_drop = trend["heart_rate_drop"]
        if heart_rate_drop is None:
            return "not recovering, heart rate peaked in the last third of the session"

        activity_drop = trend["activity_drop"]
        activity_text = (
            "activity peaked in the last third" if activity_drop is None
            else "activity fell {0}".format(activity_drop)
        )
        return (
            "not recovering, from the peak to the last third heart rate fell "
            "{0} bpm and {1}, recovery needs at least {2} bpm and {3}".format(
                heart_rate_drop, activity_text,
                RECOVERY_HEART_RATE_DROP, RECOVERY_ACTIVITY_DROP)
        )
