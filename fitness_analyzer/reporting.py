"""Text and CSV output built from analysis result dictionaries.

Three files are written to the output folder and replaced on every run:
analysis_summary.csv, analysis_report.txt and rejected_records.txt.
"""

import csv
from pathlib import Path


LINE_WIDTH = 66


def format_value(value, digits=2, missing="n/a"):
    """Render a number for the report, or a placeholder when it is None."""
    if value is None:
        return missing
    if isinstance(value, float):
        return "{0:.{1}f}".format(value, digits)
    return str(value)


def format_measurement_row(name, summary):
    """One row of the measurement table."""
    return "  {0:<16}{1:>10}{2:>10}{3:>10}".format(
        name,
        format_value(summary["average"]),
        format_value(summary["minimum"]),
        format_value(summary["maximum"]),
    )


def format_heading(text):
    return "\n" + text + "\n" + "-" * LINE_WIDTH


class SessionReport:
    """Standard report for one analysed session."""

    def __init__(self, result):
        self.result = result

    def title(self):
        name = self.result.get("participant_name")
        participant = self.result["participant_id"]
        if name:
            participant = "{0}, {1}".format(participant, name)
        return "{0} (participant {1})".format(self.result["session_id"], participant)

    def render(self):
        """Return the report as a single string."""
        parts = [
            "=" * LINE_WIDTH,
            self.title(),
            "=" * LINE_WIDTH,
            self._source_line(),
            self._classification_block(),
            self._quality_block(),
            self._measurement_block(),
            self._comparison_block(),
        ]
        return "\n".join(part for part in parts if part)

    def _source_line(self):
        sources = self.result.get("sources") or []
        if not sources:
            return ""
        return "Read from: " + ", ".join(Path(path).as_posix() for path in sources)

    def _classification_block(self):
        lines = ["Classification: " + self.result["classification"].upper()]
        for reason in self.result["reasons"]:
            lines.append("  because " + reason)
        return "\n".join(lines)

    def _quality_block(self):
        quality = self.result["quality"]
        lines = [format_heading("Data quality")]
        lines.append("  {0} of {1} accepted rows usable ({2}%)".format(
            quality["usable_rows"],
            quality["total_rows"],
            round(quality["usable_ratio"] * 100, 1),
        ))
        if quality["problem_counts"]:
            lines.append("  Why rows were not used:")
            for problem, count in sorted(quality["problem_counts"].items()):
                lines.append("    {0:<40}{1:>3}".format(problem, count))
        return "\n".join(lines)

    def _measurement_block(self):
        if self.result["quality"]["usable_rows"] == 0:
            return format_heading("Measurements") + "\n  no usable rows to summarise"

        lines = [format_heading("Measurements (usable rows only)")]
        lines.append("  {0:<16}{1:>10}{2:>10}{3:>10}".format(
            "field", "average", "minimum", "maximum"))
        for name, summary in self.result["measurements"].items():
            lines.append(format_measurement_row(name, summary))
        return "\n".join(lines)

    def _comparison_block(self):
        comparison = self.result["comparison"]
        if comparison["heart_rate_above_baseline"] is None:
            return ""

        baselines = self.result["baselines"]
        trend = self.result["trend"]
        lines = [format_heading("Compared with personal baseline")]
        lines.append("  heart rate      {0} bpm above baseline of {1}".format(
            format_value(comparison["heart_rate_above_baseline"], 1),
            format_value(baselines["heart_rate"], 0),
        ))
        lines.append("  temperature     {0} C above baseline of {1}".format(
            format_value(comparison["temperature_above_baseline"], 2),
            format_value(baselines["temperature"], 2),
        ))
        lines.append("  skin response   {0} above baseline of {1}".format(
            format_value(comparison["skin_response_above_baseline"], 2),
            format_value(baselines["skin_response"], 2),
        ))
        if trend["heart_rate_drop"] is None:
            lines.append("  peak to end     not measured, needs a peak before the last third")
        else:
            lines.append("  peak to end     heart rate fell {0} bpm, activity fell {1}".format(
                format_value(trend["heart_rate_drop"], 1),
                format_value(trend["activity_drop"], 3, missing="n/a (peaked late)"),
            ))
        return "\n".join(lines)


class DetailedSessionReport(SessionReport):
    """Adds a per-row breakdown of every observation that was not usable.

    Overrides render. The file report uses this version, so anyone reading it
    can see which accepted rows were left out of the analysis and why.
    """

    def render(self):
        """Extend the standard report with the list of unusable rows."""
        standard = super().render()
        detail = self._unusable_row_block()
        if not detail:
            return standard
        return standard + "\n" + detail

    def _unusable_row_block(self):
        unusable = self.result.get("unusable_detail", [])
        if not unusable:
            return ""

        lines = [format_heading("Rows not used")]
        for row in unusable:
            lines.append("  timestamp {0}".format(row["timestamp"]))
            for field, reason in row["problems"]:
                lines.append("    - {0} {1}".format(field, reason))
        return "\n".join(lines)


def render_all(results, detailed=False):
    """Render a list of analysis results into one string."""
    report_class = DetailedSessionReport if detailed else SessionReport
    return "\n\n".join(report_class(result).render() for result in results)


def summary_table(results):
    """A one line per session overview, placed at the top of the report."""
    width = LINE_WIDTH
    lines = ["{0:<16}{1:<10}{2:<22}{3:>9}{4:>9}".format(
        "session", "person", "classification", "accepted", "usable")]
    lines.append("-" * width)
    for result in results:
        quality = result["quality"]
        lines.append("{0:<16}{1:<10}{2:<22}{3:>9}{4:>9}".format(
            result["session_id"],
            result["participant_id"],
            result["classification"],
            quality["total_rows"],
            quality["usable_rows"],
        ))
    return "\n".join(lines)


# --- Output files ---------------------------------------------------------

SUMMARY_FILE = "analysis_summary.csv"
REPORT_FILE = "analysis_report.txt"
REJECTED_FILE = "rejected_records.txt"

SUMMARY_COLUMNS = (
    "session_id",
    "participant_id",
    "participant_name",
    "source_files",
    "accepted_rows",
    "usable_rows",
    "classification",
    "mean_heart_rate",
    "heart_rate_above_baseline",
    "mean_temperature",
    "temperature_above_baseline",
    "mean_skin_response",
    "skin_response_above_baseline",
    "mean_activity_level",
    "heart_rate_drop_from_peak",
    "activity_drop_from_peak",
    "reasons",
)


def csv_value(value):
    """Empty cell for a value that could not be calculated."""
    return "" if value is None else value


def summary_row(result):
    """One analysis_summary.csv row for one session."""
    measurements = result["measurements"]
    comparison = result["comparison"]
    trend = result["trend"]
    row = {
        "session_id": result["session_id"],
        "participant_id": result["participant_id"],
        "participant_name": result.get("participant_name", ""),
        "source_files": ";".join(
            Path(path).as_posix() for path in result.get("sources", [])),
        "accepted_rows": result["quality"]["total_rows"],
        "usable_rows": result["quality"]["usable_rows"],
        "classification": result["classification"],
        "mean_heart_rate": measurements["heart_rate"]["average"],
        "heart_rate_above_baseline": comparison["heart_rate_above_baseline"],
        "mean_temperature": measurements["temperature"]["average"],
        "temperature_above_baseline": comparison["temperature_above_baseline"],
        "mean_skin_response": measurements["skin_response"]["average"],
        "skin_response_above_baseline": comparison["skin_response_above_baseline"],
        "mean_activity_level": measurements["activity_level"]["average"],
        "heart_rate_drop_from_peak": trend["heart_rate_drop"],
        "activity_drop_from_peak": trend["activity_drop"],
        "reasons": "; ".join(result["reasons"]),
    }
    return {key: csv_value(value) for key, value in row.items()}


def write_summary_csv(path, results):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        for result in results:
            writer.writerow(summary_row(result))


def render_report(results, run):
    """The full analysis_report.txt text.

    run is the dictionary main.py builds with the load counts, the rejected
    records and the sessions that had no valid rows left.
    """
    rejected_by_session = {}
    for record in run["rejected"]:
        if record.session_id:
            rejected_by_session[record.session_id] = (
                rejected_by_session.get(record.session_id, 0) + 1)

    parts = [
        "=" * LINE_WIDTH,
        "Smart Fitness Session Analyzer report",
        "=" * LINE_WIDTH,
        "Profile file:   " + Path(run["profile_file"]).as_posix(),
        "Session files:  " + (", ".join(
            Path(path).as_posix() for path in run["files_read"]) or "none"),
        "Accepted rows:  {0} ({1} usable)".format(
            run["accepted_rows"], run["usable_rows"]),
        "Rejected rows:  {0} (see {1})".format(len(run["rejected"]), REJECTED_FILE),
        "",
        "Rows with signal quality below the minimum are accepted but not used",
        "for the analysis. Sessions need at least 4 usable rows.",
        "",
        summary_table(results) if results else "No sessions could be analysed.",
    ]

    if run["skipped_files"]:
        parts.append(format_heading("Files that were not read in full"))
        for skipped in run["skipped_files"]:
            parts.append("  {0}: {1}".format(skipped.path.as_posix(), skipped.reason))

    for result in results:
        parts.append("")
        parts.append(DetailedSessionReport(result).render())

    if run["empty_session_ids"]:
        parts.append("")
        parts.append("=" * LINE_WIDTH)
        parts.append("Sessions with no valid rows")
        parts.append("=" * LINE_WIDTH)
        for session_id in run["empty_session_ids"]:
            parts.append(
                "{0}: no valid rows remained ({1} rejected row(s)), so it was "
                "not analysed. See {2}.".format(
                    session_id, rejected_by_session.get(session_id, 0), REJECTED_FILE))

    return "\n".join(parts) + "\n"


def render_rejected(run):
    """The rejected_records.txt text, one line per problem field."""
    rejected = run["rejected"]
    lines = [
        "Rejected records",
        "================",
        "{0} row(s) rejected. Line numbers count the header as line 1.".format(
            len(rejected)),
        "A row with several problems has one line per field.",
        "",
    ]
    if rejected:
        file_width = max(len(record.source.as_posix()) for record in rejected)
        file_width = max(file_width, len("file"))
        template = "{0:<%d}  {1:>5}  {2:<16}  {3}" % file_width
        lines.append(template.format("file", "line", "field", "reason"))
        lines.append("-" * (file_width + 50))
        for record in rejected:
            for field, reason in record.problems:
                lines.append(template.format(
                    record.source.as_posix(), record.line, field, reason))

    if run["skipped_files"]:
        lines.append("")
        lines.append("Files that were not read in full")
        lines.append("-" * 32)
        for skipped in run["skipped_files"]:
            lines.append("{0}: {1}".format(skipped.path.as_posix(), skipped.reason))

    return "\n".join(lines) + "\n"


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def write_outputs(output_dir, results, run):
    """Create the output folder if needed and write all three files.

    Returns the paths written. OSError, including PermissionError, is left to
    the caller, which reports it.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / SUMMARY_FILE
    report_path = output_dir / REPORT_FILE
    rejected_path = output_dir / REJECTED_FILE

    write_summary_csv(summary_path, results)
    write_text(report_path, render_report(results, run))
    write_text(rejected_path, render_rejected(run))
    return [summary_path, report_path, rejected_path]
