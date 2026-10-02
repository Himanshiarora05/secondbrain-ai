"""
SM-2 spaced repetition for flashcards.

Three answers, mapped to SM-2 quality grades: "again" (2, forgotten),
"good" (4) and "easy" (5). The ease factor starts at 2.5, changes by SM-2's
formula on every answer (again -0.32, good 0, easy +0.1) and never drops
below 1.3. A correct answer gives intervals of 1 day, then 6 days, then the
previous interval times the ease; "easy" also multiplies the result by
EASY_BONUS (as Anki does) so it always lands later than "good". "again"
starts the card over and keeps it due today.

Pure functions only; the routes in app/routes/review.py store the result.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

GRADES = {"again": 2, "good": 4, "easy": 5}
DEFAULT_EASE = 2.5
MIN_EASE = 1.3
EASY_BONUS = 1.3
# Keeps due dates sane for a card answered "easy" for years on end.
MAX_INTERVAL_DAYS = 3650


@dataclass
class Schedule:
    ease: float
    interval_days: int
    repetitions: int
    due_date: date


def review(ease: float, interval_days: int, repetitions: int, grade: str, today: date) -> Schedule:
    """The card's next schedule after answering `grade` ("again" / "good" / "easy") on `today`."""
    if grade not in GRADES:
        raise ValueError(f"Unknown grade {grade!r}; expected one of {', '.join(GRADES)}")
    q = GRADES[grade]

    if q < 3:
        repetitions, interval = 0, 0
    else:
        repetitions += 1
        if repetitions == 1:
            interval = 1
        elif repetitions == 2:
            interval = 6
        else:
            interval = round(max(interval_days, 1) * ease)
        if grade == "easy":
            interval = max(interval + 1, round(interval * EASY_BONUS))
    interval = min(interval, MAX_INTERVAL_DAYS)

    new_ease = max(MIN_EASE, round(ease + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02), 2))
    return Schedule(new_ease, interval, repetitions, today + timedelta(days=interval))


def local_today(client_today: Optional[date], server_today: date) -> date:
    """The user's "today": the date their browser sent, if it's within a day of the server's
    UTC date (every time zone is), else the server's date."""
    if client_today is not None and abs((client_today - server_today).days) <= 1:
        return client_today
    return server_today
