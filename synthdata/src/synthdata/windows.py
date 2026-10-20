"""Request windows (Wunschphase): one per roster month, with who answered and what."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from synthdata.behaviour import Latent, Wish, draw_wishes
from synthdata.calendar import days, monday_on_or_before, month_end
from synthdata.config import DEMO_NOW, OPEN_WINDOW_MONTH, OPEN_WINDOW_RESPONDENTS, TZ
from synthdata.ids import uid
from synthdata.rng import Streams
from synthdata.staff import Person


@dataclass
class Window:
    """A request window and its answers."""

    id: object
    month: date
    opens_at: datetime
    closes_at: datetime
    status: str
    recipients: list[str]
    responses: dict[str, datetime]  # person key → submitted at
    wishes: dict[str, list[Wish]]


def window_times(month: date) -> tuple[datetime, datetime]:
    """Return (opens, closes): closes Monday 23:59 five weeks ahead, opens 14 days earlier."""
    close_day = monday_on_or_before(month - timedelta(days=35))
    closes = datetime.combine(close_day, time(23, 59), tzinfo=TZ)
    opens = datetime.combine(close_day - timedelta(days=14), time(8, 0), tzinfo=TZ)
    return opens, closes


def publish_time(month: date) -> datetime:
    """Return the publication time: 14:00 on the Monday at least 13 days before the month."""
    return datetime.combine(monday_on_or_before(month - timedelta(days=13)), time(14, 0), tzinfo=TZ)


def build_window(
    streams: Streams, month: date, people: list[Person], latents: dict[str, Latent]
) -> Window:
    """Who received the window, who answered, and their answers."""
    opens, closes = window_times(month)
    month_days = list(days(month, month_end(month)))
    recipients = [
        p.key
        for p in people
        if p.role_on(opens.date()) is not None
        and any(p.role_on(d) is not None and not p.on_rotation(d) for d in month_days)
    ]
    rng = streams.get("window", month.isoformat())
    is_open = month == OPEN_WINDOW_MONTH
    if is_open:
        # UI_SPEC §1: 21 of 28 have responded. Dr. Kaya has not (her open task on M2).
        ranked = sorted(
            (k for k in recipients if k != "kaya"),
            key=lambda k: -(latents[k].responsiveness + float(rng.normal(0, 0.15))),
        )
        responders = set(ranked[:OPEN_WINDOW_RESPONDENTS])
        latest = DEMO_NOW
    else:
        responders = {k for k in recipients if rng.random() < latents[k].responsiveness}
        latest = closes
    responses: dict[str, datetime] = {}
    wishes: dict[str, list[Wish]] = {}
    for k in sorted(responders):
        prng = streams.get("wishes", month.isoformat(), k)
        at = opens + (latest - opens) * float(prng.random())
        responses[k] = at.replace(second=0, microsecond=0)
        wishes[k] = draw_wishes(prng, latents[k], month_days)
    status = "open" if is_open else "closed"
    return Window(uid("window", month), month, opens, closes, status, recipients, responses, wishes)
