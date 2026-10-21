"""The department's staff over time: positions, people, roles, contracts, qualifications, rotations.

The 2026 team uses the fictional names from UI_SPEC §1. Everyone else (earlier occupants and the
remaining 2026 positions) gets a generated fictional name. Headcount stays at 28 positions.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from synthdata.config import HISTORY_START
from synthdata.ids import uid
from synthdata.rng import Streams

ROLES = ("chefaerztin", "oberarzt", "facharzt", "assistenzarzt")
# Gender-neutral German titles for people whose title form the specs do not give.
NEUTRAL_TITLE_DE = {
    "chefaerztin": "Chefärzt:in",
    "oberarzt": "Oberärzt:in",
    "facharzt": "Fachärzt:in",
    "assistenzarzt": "Assistenzärzt:in",
}
TITLE_EN = {
    "chefaerztin": "Head of department",
    "oberarzt": "Senior physician",
    "facharzt": "Specialist",
    "assistenzarzt": "Resident",
}
ROTATION_TARGETS = ("Intensivstation", "Zentrale Notaufnahme", "Gastroenterologie", "Kardiologie")
FAR_PAST = date(2010, 1, 1)


@dataclass
class RolePeriod:
    """One contract period: a role, hours and an optional explicit German title."""

    role: str
    start: date
    end: date | None
    weekly_hours: float
    title_de: str | None = None


@dataclass
class Person:
    """A physician of the department (current or former)."""

    key: str
    display_name: str
    named: bool
    periods: list[RolePeriod]
    rotations: list[tuple[date, date, str]] = field(default_factory=list)

    @property
    def id(self) -> object:
        """Stable UUID."""
        return uid("staff", self.key)

    @property
    def start(self) -> date:
        """First day employed."""
        return self.periods[0].start

    @property
    def end(self) -> date | None:
        """Last day employed, or None if still employed."""
        return self.periods[-1].end

    def period_on(self, d: date) -> RolePeriod | None:
        """Return the contract period covering d."""
        for p in self.periods:
            if p.start <= d and (p.end is None or d <= p.end):
                return p
        return None

    def role_on(self, d: date) -> str | None:
        """Role on d, or None if not employed."""
        p = self.period_on(d)
        return None if p is None else p.role

    def on_rotation(self, d: date) -> bool:
        """External rotation: employed but not on the department's roster."""
        return any(a <= d <= b for a, b, _ in self.rotations)

    def first_role_start(self, roles: tuple[str, ...]) -> date | None:
        """Start of the first period in one of the given roles."""
        for p in self.periods:
            if p.role in roles:
                return p.start
        return None

    def qualifications_on(self, d: date) -> set[str]:
        """Qualifications valid on d (derived from role history, see ASSUMPTIONS.md)."""
        role = self.role_on(d)
        if role is None:
            return set()
        quals: set[str] = set()
        if role in ("chefaerztin", "oberarzt"):
            quals |= {"oberarzt", "facharzt", "nachtdienstfaehig"}
        elif role == "facharzt":
            quals |= {"facharzt", "nachtdienstfaehig"}
        else:
            # Residents are cleared for nights and in-house on-call after 12 months.
            if self.start + timedelta(days=365) <= d:
                quals.add("nachtdienstfaehig")
        return quals


# --- The 2026 team (UI_SPEC §1) and its history -------------------------------------------
# Each slot lists its occupants in order: (person key, role, start, title_de). Starts before
# 2021 are hire dates of people already employed when the simulation begins.
NAMED: dict[str, str] = {
    "hoffmann": "Prof. Dr. Claudia Hoffmann",
    "brandt": "Dr. Thomas Brandt",
    "lorenz": "Dr. Lea Lorenz",
    "kaya": "Dr. Aylin Kaya",
    "mehta": "Dr. Rohan Mehta",
    "weber": "Dr. Jonas Weber",
    "alvarez": "Dr. Sofía Alvarez",
    "nowak": "Dr. Marek Nowak",
    "schulz": "Dr. Hannah Schulz",
    "demir": "Dr. Yusuf Demir",
    "becker": "Dr. Ines Becker",
    "wagner": "Dr. Felix Wagner",
    "okafor": "Dr. Mira Okafor",
    "richter": "Dr. Paul Richter",
    "lehmann": "Dr. Anna Lehmann",
    "klein": "Dr. Tobias Klein",
    "arslan": "Dr. Elif Arslan",
}
# Title forms stated in UI_SPEC §1 and the design system's roster preview; others stay neutral.
TITLES_DE: dict[tuple[str, str], str] = {
    ("hoffmann", "chefaerztin"): "Chefärztin",
    ("brandt", "oberarzt"): "Oberarzt",
    ("lorenz", "facharzt"): "Fachärztin",
    ("lorenz", "assistenzarzt"): "Assistenzärztin",
    ("kaya", "assistenzarzt"): "Assistenzärztin",
    ("mehta", "assistenzarzt"): "Assistenzarzt",
    ("weber", "assistenzarzt"): "Assistenzarzt",
    ("alvarez", "assistenzarzt"): "Assistenzärztin",
    ("nowak", "assistenzarzt"): "Assistenzarzt",
    ("schulz", "facharzt"): "Fachärztin",
}
# Part-time contracts (weekly hours); everyone else works 40 h.
PART_TIME: dict[str, float] = {"schulz": 30.0, "lehmann": 32.0}

Slot = list[tuple[str | None, str, date]]  # (person key or None = generated, role, start)


def _generated_resident() -> Slot:
    return [(None, "assistenzarzt", FAR_PAST)]


SLOTS: list[Slot] = [
    [("hoffmann", "chefaerztin", date(2015, 4, 1))],
    [("brandt", "oberarzt", date(2014, 10, 1))],
    [("becker", "oberarzt", date(2016, 7, 1))],
    [(None, "oberarzt", FAR_PAST), ("richter", "oberarzt", date(2022, 1, 1))],
    [(None, "oberarzt", FAR_PAST), ("klein", "oberarzt", date(2023, 4, 1))],
    [("klein", "facharzt", date(2018, 2, 1)), ("lorenz", "facharzt", date(2023, 4, 1))],
    [("schulz", "facharzt", date(2018, 9, 1))],
    [("demir", "facharzt", date(2017, 5, 1))],
    [(None, "facharzt", FAR_PAST), ("wagner", "facharzt", date(2022, 7, 1))],
    [(None, "facharzt", FAR_PAST), ("lehmann", "facharzt", date(2024, 10, 1))],
    [(None, "facharzt", FAR_PAST)],
    [(None, "facharzt", FAR_PAST), (None, "facharzt", date(2025, 1, 1))],
    [("lorenz", "assistenzarzt", date(2017, 10, 1)), ("mehta", "assistenzarzt", date(2023, 4, 1))],
    [
        ("lehmann", "assistenzarzt", date(2019, 4, 1)),
        ("alvarez", "assistenzarzt", date(2024, 10, 1)),
    ],
    [(None, "assistenzarzt", FAR_PAST), ("kaya", "assistenzarzt", date(2022, 10, 1))],
    [(None, "assistenzarzt", FAR_PAST), ("weber", "assistenzarzt", date(2021, 4, 1))],
    [("nowak", "assistenzarzt", date(2020, 10, 1))],
    [(None, "assistenzarzt", FAR_PAST), ("okafor", "assistenzarzt", date(2025, 3, 1))],
    [(None, "assistenzarzt", FAR_PAST), ("arslan", "assistenzarzt", date(2026, 4, 1))],
    # Nine resident positions held by generated people in 2026.
    *[_generated_resident() for _ in range(9)],
]

FIRST_NAMES = [
    "Clara",
    "Jan",
    "Miriam",
    "Lukas",
    "Nora",
    "David",
    "Selin",
    "Moritz",
    "Johanna",
    "Emil",
    "Leonie",
    "Niklas",
    "Amira",
    "Philipp",
    "Katharina",
    "Samuel",
    "Lina",
    "Tim",
    "Hanna",
    "Ole",
    "Mariam",
    "Julian",
    "Carla",
    "Benedikt",
    "Sara",
    "Henrik",
    "Ida",
    "Kemal",
    "Frieda",
    "Malte",
    "Zeynep",
    "Vincent",
    "Greta",
    "Aaron",
    "Pia",
    "Daniel",
    "Lea-Marie",
    "Erik",
    "Nadia",
    "Jonte",
]
LAST_NAMES = [
    "Hartmann",
    "Krüger",
    "Vogt",
    "Brenner",
    "Seidel",
    "Albrecht",
    "Kuhn",
    "Engel",
    "Busch",
    "Pohl",
    "Franke",
    "Graf",
    "Haas",
    "Lang",
    "Winter",
    "Sommer",
    "Brandl",
    "Jäger",
    "Roth",
    "Frey",
    "Böhm",
    "Ziegler",
    "Lorenzen",
    "Marx",
    "Kaiser",
    "Fuchs",
    "Peters",
    "Scholz",
    "Möller",
    "Dietrich",
    "Ernst",
    "Stein",
    "Huber",
    "Arnold",
    "Sauer",
    "Thiel",
    "Kraus",
]


def _months(n: float) -> timedelta:
    return timedelta(days=round(n * 30.44))


class NamePool:
    """Generated fictional names, drawn without repetition in a seeded order."""

    def __init__(self, rng: np.random.Generator) -> None:
        """Shuffle all first × last name combinations once."""
        combos = [f"Dr. {f} {last}" for f in FIRST_NAMES for last in LAST_NAMES]
        self._names: list[str] = [combos[int(i)] for i in rng.permutation(len(combos))]
        self._next = 0

    def take(self) -> str:
        """Return the next unused name."""
        name = self._names[self._next]
        self._next += 1
        return name


def _tenure(rng: np.random.Generator, role: str) -> timedelta:
    # Residents train 54–72 months; specialists and seniors stay 6–15 years.
    return _months(rng.uniform(54, 72) if role == "assistenzarzt" else rng.uniform(72, 180))


def build_staff(streams: Streams) -> list[Person]:
    """All people who work in the department at any time from 2021 on."""
    rng = streams.get("staff")
    names = NamePool(streams.get("names"))
    segments: list[tuple[str, str, date, date | None]] = []  # key, role, start, end
    gen = 0

    def new_key() -> str:
        nonlocal gen
        gen += 1
        return f"gen-{gen:03d}"

    for slot in SLOTS:
        occupants: list[tuple[str, str, date]] = []
        for i, (key, role, start) in enumerate(slot):
            if start == FAR_PAST:
                nxt = slot[i + 1][2] if i + 1 < len(slot) else None
                if nxt is not None:
                    start = nxt - _tenure(rng, role)
                elif role == "assistenzarzt":
                    start = date(2020, 6, 1) + timedelta(days=int(rng.integers(0, 6 * 365)))
                else:
                    start = date(2012, 1, 1) + timedelta(days=int(rng.integers(0, 10 * 365)))
            occupants.append((key or new_key(), role, start))
        # Predecessors back to the start of the simulation.
        while occupants[0][2] > HISTORY_START:
            role = occupants[0][1]
            occupants.insert(0, (new_key(), role, occupants[0][2] - _tenure(rng, role)))
        for i, (key, role, start) in enumerate(occupants):
            end = occupants[i + 1][2] - timedelta(days=1) if i + 1 < len(occupants) else None
            segments.append((key, role, start, end))

    people: dict[str, Person] = {}
    for key, role, start, end in sorted(segments, key=lambda s: (s[0], s[2])):
        named = key in NAMED
        person = people.get(key)
        if person is None:
            display = NAMED[key] if named else names.take()
            person = people[key] = Person(key, display, named, [])
        hours = PART_TIME.get(key, 40.0)
        if not named and rng.random() < 0.12:
            hours = float(rng.choice([20.0, 30.0, 32.0]))
        if person.periods:
            # A second segment is a promotion; it inherits the hours of the first.
            hours = person.periods[-1].weekly_hours
        person.periods.append(RolePeriod(role, start, end, hours, TITLES_DE.get((key, role))))

    _assign_rotations(streams, list(people.values()))
    return sorted(people.values(), key=lambda p: (p.start, p.key))


def _six_months_on(start: date) -> date:
    """Last day of the sixth month starting at ``start`` (a first of month)."""
    m = start.month + 6
    nxt = date(start.year + (m - 1) // 12, (m - 1) % 12 + 1, 1)
    return nxt - timedelta(days=1)


def _assign_rotations(streams: Streams, people: list[Person]) -> None:
    """One six-month external rotation per resident, in years 2–4 of training.

    Named 2026 residents are kept on the roster from September 2026 (demo months).
    """
    rng = streams.get("rotations")
    # Nobody rotates out from September to December 2026: the whole team is on the demo roster.
    demo_guard = (date(2026, 9, 1), date(2026, 12, 31))
    for p in people:
        aa_start = p.first_role_start(("assistenzarzt",))
        if aa_start is None:
            continue
        lo, hi = aa_start + _months(24), aa_start + _months(48)
        start = lo + timedelta(days=int(rng.integers(0, max(1, (hi - lo).days))))
        start = date(start.year, start.month, 1)
        end = _six_months_on(start)
        if start <= demo_guard[1] and end >= demo_guard[0]:
            start = (
                date(2025, 3, 1)
                if aa_start < date(2023, 3, 1)
                else demo_guard[1] + timedelta(days=1)
            )
            end = _six_months_on(start)
        aa_end = next((r.end for r in p.periods if r.role == "assistenzarzt"), None)
        if aa_end is not None and end > aa_end:
            continue
        if end < HISTORY_START or start < p.start:
            continue
        p.rotations.append((start, end, str(rng.choice(ROTATION_TARGETS))))


def headcount_on(people: list[Person], d: date) -> dict[str, int]:
    """Count the people per role employed on d."""
    counts = dict.fromkeys(ROLES, 0)
    for p in people:
        r = p.role_on(d)
        if r is not None:
            counts[r] += 1
    return counts
