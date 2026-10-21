"""Sanity report on the synthetic data: seasonal patterns and leave decisions.

Usage: uv run python synthdata/scripts/sanity_report.py [data/synthetic/v1]
Writes <dataset>/reports/absence_and_leave.png and <dataset>/reports/sanity_report.md.
The figures come from the visible tables; only the target and the calibration are read from
_truth/params.json (synthdata may read it, application code may not).
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import polars as pl


def _per_day(intervals: pl.DataFrame, start: date, end: date) -> pl.DataFrame:
    """Count how many intervals (start_date..end_date) cover each day."""
    days = pl.DataFrame({"date": pl.date_range(start, end, "1d", eager=True)})
    expanded = intervals.select(
        pl.date_ranges("start_date", "end_date", "1d").alias("date")
    ).explode("date")
    counts = expanded.group_by("date").len()
    return days.join(counts, on="date", how="left").fill_null(0).sort("date")


def plot(root: Path) -> Path:
    start, end = date(2021, 1, 1), date(2026, 10, 20)
    sick = pl.read_parquet(root / "operations" / "absence.parquet")
    leave = pl.read_parquet(root / "requests" / "leave_request.parquet").filter(
        pl.col("status") == "approved"
    )
    school = pl.read_parquet(root / "organization" / "school_holiday.parquet")

    sick_daily = _per_day(sick, start, end).with_columns(pl.col("len").rolling_mean(7).alias("avg"))
    leave_daily = _per_day(leave, start, end).with_columns(
        pl.col("len").rolling_mean(7).alias("avg")
    )

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6.5), sharex=True, constrained_layout=True)
    ax1.plot(sick_daily["date"], sick_daily["avg"], color="#1F5FD1", lw=1.2)
    ax1.set_ylabel("Absent (sick), 7-day mean")
    ax1.set_title(
        "Synthetic data: department-level sickness (winter waves)", loc="left", fontsize=11
    )
    ax2.plot(leave_daily["date"], leave_daily["avg"], color="#2A7F5B", lw=1.2)
    ax2.set_ylabel("On approved leave, 7-day mean")
    ax2.set_title("Approved leave (shaded: approximate school holidays)", loc="left", fontsize=11)
    for row in school.iter_rows(named=True):
        if row["end_date"] >= start and row["start_date"] <= end:
            ax2.axvspan(
                row["start_date"],
                row["end_date"] + timedelta(days=1),
                color="#9AA5B1",
                alpha=0.25,
                lw=0,
            )
    for ax in (ax1, ax2):
        ax.axvspan(date(2026, 1, 1), end, color="#FFF6D6", alpha=0.6, lw=0, zorder=0)
        ax.grid(axis="y", color="#D6DDE2", lw=0.6)
        ax.spines[["top", "right"]].set_visible(False)
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax1.text(
        date(2026, 1, 15), ax1.get_ylim()[1] * 0.92, "demo period", fontsize=9, color="#5C4A00"
    )
    fig.suptitle(
        "Klinik für Innere Medizin, Klinikum Musterstadt (fictional)."
        " Demo environment, synthetic data.",
        fontsize=9,
        x=0.01,
        ha="left",
        color="#4D5D69",
    )
    out = root / "reports" / "absence_and_leave.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130)
    return out


PERIOD_ORDER = [
    "Osterferien",
    "Sommerferien",
    "Herbstferien",
    "Weihnachtsferien",
    "Außerhalb der Ferien",
]
PERIOD_EN = {
    "Osterferien": "Easter holidays",
    "Sommerferien": "Summer holidays",
    "Herbstferien": "Autumn holidays",
    "Weihnachtsferien": "Christmas holidays",
    "Außerhalb der Ferien": "Outside school holidays",
}


def leave_decline_table(root: Path) -> list[tuple[str, int, int]]:
    """Return (holiday period, decided first requests, declined) per period, plus "Gesamt".

    A first request has no previous_request_id. It belongs to the school-holiday period its
    dates overlap most, or to "Außerhalb der Ferien".
    """
    lr = pl.read_parquet(root / "requests" / "leave_request.parquet")
    first = lr.filter(pl.col("previous_request_id").is_null() & (pl.col("status") != "pending"))
    school = pl.read_parquet(root / "organization" / "school_holiday.parquet").to_dicts()
    counts: dict[str, list[int]] = {p: [0, 0] for p in PERIOD_ORDER}
    for r in first.iter_rows(named=True):
        best, overlap = "Außerhalb der Ferien", 0
        for h in school:
            days = (
                min(r["end_date"], h["end_date"]) - max(r["start_date"], h["start_date"])
            ).days + 1
            if days > overlap:
                best, overlap = h["name_de"], days
        counts[best][0] += 1
        counts[best][1] += r["status"] == "declined"
    rows = [(p, n, k) for p, (n, k) in counts.items()]
    rows.append(("Gesamt", sum(n for _, n, _ in rows), sum(k for _, _, k in rows)))
    return rows


def report(root: Path) -> Path:
    """Write the markdown sanity report and the plot; return the report's path."""
    png = plot(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    params = json.loads((root / "_truth" / "params.json").read_text(encoding="utf-8"))
    lines = [
        "# Sanity report: synthetic data",
        "",
        "Klinik für Innere Medizin, Klinikum Musterstadt (fictional)."
        " Demo environment, synthetic data.",
        f"Seed {manifest['seed']}, generator v{manifest['generator_version']}."
        " Generated by synthdata/scripts/sanity_report.py; do not edit by hand.",
        "",
        f"![Sickness and leave over time]({png.name})",
        "",
        "## Leave: first-request decline rate per holiday period",
        "",
        "First requests only (follow-ups after a decline are excluded), decided by the demo date.",
        f"Target (`target_first_request_decline_rate`, a placeholder to confirm with a physician):"
        f" {params['target_first_request_decline_rate']:.0%}."
        f" Calibrated holiday-clustering scale: {params['calibration']['leave_affinity_scale']}.",
        "",
        "| Period | First requests | Declined | Decline rate |",
        "|---|---:|---:|---:|",
    ]
    for period, n, k in leave_decline_table(root):
        label = period if period == "Gesamt" else f"{period} ({PERIOD_EN[period]})"
        rate = f"{k / n:.1%}" if n else "–"
        lines.append(
            f"| {'**' + label + '**' if period == 'Gesamt' else label} | {n} | {k} | {rate} |"
        )
    out = root / "reports" / "sanity_report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    print(report(Path(sys.argv[1] if len(sys.argv) > 1 else "data/synthetic/v1")))
