"""Latent per-person behaviour (ground truth) and the observable data it produces.

Request-window answers, sickness waves and report times derive from these parameters.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import numpy as np

from synthdata.calendar import is_weekend
from synthdata.config import PARAMS, TZ
from synthdata.rng import Streams
from synthdata.staff import Person

PREF_SHIFTS = ("frueh", "spaet", "nacht", "bereitschaft")


@dataclass
class Latent:
    """Hidden parameters of one person. Written only to _truth/."""

    preference: np.ndarray  # 7 weekdays × 4 shifts (frueh, spaet, nacht, bereitschaft), mean 0
    night_tolerance: float
    weekend_aversion: float
    holiday_period_affinity: float  # how strongly leave clusters in school holidays (0–1)
    cover_willingness: float  # base log-odds of accepting a cover request
    cover_load_decay: float  # log-odds lost per cover accepted in the last 30 days
    swap_propensity: float  # probability of offering a shift in a month
    responsiveness: float  # probability of answering a request window
    planner_favour: float  # how much the manual planner leans on this person for weekends
    sickness_frailty: float  # multiplier on the sickness hazard

    def shift_affinity(self, d: date, shift: str) -> float:
        """Return the latent liking of a shift on a weekday (higher is better)."""
        if shift not in PREF_SHIFTS:
            return 0.0
        v = float(self.preference[d.weekday(), PREF_SHIFTS.index(shift)])
        if shift in ("nacht", "bereitschaft"):
            v += self.night_tolerance
        if is_weekend(d):
            v -= self.weekend_aversion
        return v


def draw_latents(streams: Streams, people: list[Person]) -> dict[str, Latent]:
    """One Latent per person, each from its own stream."""
    out: dict[str, Latent] = {}
    for p in people:
        rng = streams.get("latent", p.key)
        pref = rng.normal(0.0, 0.6, size=(7, 4))
        pref -= pref.mean()
        out[p.key] = Latent(
            preference=pref,
            night_tolerance=float(rng.normal(0.0, 0.7)),
            weekend_aversion=float(rng.normal(0.5, 0.5)),
            holiday_period_affinity=float(rng.beta(1.6, 3.0)),
            cover_willingness=float(rng.normal(0.4, 0.8)),
            cover_load_decay=float(rng.uniform(0.2, 0.9)),
            swap_propensity=float(rng.beta(1.5, 6.0)),
            responsiveness=float(np.clip(rng.normal(PARAMS.response_rate, 0.1), 0.4, 0.99)),
            planner_favour=float(rng.normal(0.0, 1.0)),
            sickness_frailty=float(rng.lognormal(0.0, 0.3)),
        )
    return out


@dataclass(frozen=True)
class Wish:
    """One request-window entry."""

    day: date
    kind: str  # "unavailable" ("kann nicht") | "wish_work" ("möchte arbeiten")
    shift: str | None
    important: bool


def draw_wishes(rng: np.random.Generator, lat: Latent, month_days: list[date]) -> list[Wish]:
    """Draw a person's request-window answer for one month from the latent preferences."""
    wishes: list[Wish] = []
    n_unavail = int(rng.poisson(1.6))
    unavail = sorted(
        int(i) for i in rng.choice(len(month_days), size=min(n_unavail, 4), replace=False)
    )
    taken = {month_days[i] for i in unavail}
    for i in unavail:
        wishes.append(Wish(month_days[i], "unavailable", None, False))
    # "Möchte arbeiten": the days and shifts the person likes most, with noise.
    scored = [
        (lat.shift_affinity(d, s) + float(rng.normal(0, 0.5)), d, s)
        for d in month_days
        if d not in taken
        for s in PREF_SHIFTS
        if s != "bereitschaft" or is_weekend(d)
    ]
    scored.sort(key=lambda t: (-t[0], t[1], t[2]))
    n_wish = int(rng.integers(1, 6))
    chosen: list[tuple[float, date, str]] = []
    for item in scored:
        if all(item[1] != c[1] for c in chosen):
            chosen.append(item)
        if len(chosen) == n_wish:
            break
    n_important = int(rng.integers(0, 3))
    for rank, (_, d, s) in enumerate(chosen):
        shift = s if rng.random() < 0.7 else None
        wishes.append(Wish(d, "wish_work", shift, rank < n_important))
    wishes.sort(key=lambda w: (w.day, w.kind))
    return wishes


def sickness_wave(rng: np.random.Generator) -> tuple[float, float, float, float]:
    """Draw a season's wave: (peak offset from 1 Jan, width in days, amplitude, autumn bump)."""
    peak = float(rng.uniform(-15, 50))  # mid-December to late February (negative = December)
    width = float(rng.uniform(14, 30))
    amplitude = float(rng.uniform(0.8, 2.4))
    autumn = float(rng.uniform(0.0, 0.5))
    return peak, width, amplitude, autumn


def seasonal_factor(d: date, waves: dict[int, tuple[float, float, float, float]]) -> float:
    """Return the multiplier on the sickness hazard on d from the respiratory waves."""
    factor = 1.0
    for season_year, (peak, width, amp, _) in waves.items():
        # A season's wave peaks around the turn of the year season_year/season_year+1.
        centre = date(season_year + 1, 1, 1) + timedelta(days=peak)
        factor += amp * float(np.exp(-0.5 * ((d - centre).days / width) ** 2))
    # A smaller autumn bump around early November, varying by year.
    wave = waves.get(d.year)
    if wave is not None:
        factor += wave[3] * float(np.exp(-0.5 * ((d.timetuple().tm_yday - 305) / 20.0) ** 2))
    return factor


def report_time(rng: np.random.Generator, d: date) -> datetime:
    """When a sick report arrives: early morning of the first day."""
    minutes = int(rng.integers(0, 90))
    return datetime.combine(d, time(6, 0), tzinfo=TZ) + timedelta(minutes=minutes)
