"""Sanity-check plot: seasonal sickness and leave peaks in the synthetic data.

Usage: uv run python synthdata/scripts/plot_patterns.py [data/synthetic/v1]
Writes <dataset>/reports/absence_and_leave.png. Reads only the visible tables, not _truth/.
"""

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


def main(root: Path) -> Path:
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


if __name__ == "__main__":
    print(main(Path(sys.argv[1] if len(sys.argv) > 1 else "data/synthetic/v1")))
