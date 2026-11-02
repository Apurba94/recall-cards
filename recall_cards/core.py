"""Spaced repetition: review just before you would forget.

Two schedulers are included. SM-2 (Wozniak 1990) is the classic rule behind Anki. The memory model
is in the style of FSRS: it tracks how stable a memory is and how hard a card is, predicts the
chance of recall, and picks the interval that aims for a chosen retention.
"""
import math
from dataclasses import dataclass, replace
from datetime import date, timedelta

AGAIN, HARD, GOOD, EASY = 1, 2, 3, 4
GRADE_NAMES = {AGAIN: "Again", HARD: "Hard", GOOD: "Good", EASY: "Easy"}


@dataclass(frozen=True)
class Sm2State:
    interval: int = 0
    repetitions: int = 0
    ease: float = 2.5


def sm2(state, quality):
    """One review. quality runs from 0 (blank) to 5 (perfect), as in the original algorithm."""
    if not 0 <= quality <= 5:
        raise ValueError("quality must be 0 to 5")
    ease = max(1.3, state.ease + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    if quality < 3:
        return Sm2State(1, 0, ease)
    n = state.repetitions + 1
    if n == 1:
        i = 1
    elif n == 2:
        i = 6
    else:
        i = round(state.interval * ease)
    return Sm2State(i, n, ease)


@dataclass(frozen=True)
class Memory:
    stability: float = 0.0       # days until recall probability falls to 90%
    difficulty: float = 5.0      # 1 is easy, 10 is hard
    reps: int = 0
    lapses: int = 0


FIRST_STABILITY = {AGAIN: 0.4, HARD: 1.2, GOOD: 3.0, EASY: 8.0}
DECAY = -0.5
FACTOR = 19 / 81


def recall_probability(stability, days):
    """The forgetting curve: a power law, with R = 0.9 when days equals stability."""
    if stability <= 0:
        return 0.0
    return (1 + FACTOR * days / stability) ** DECAY


def next_interval(stability, retention=0.9, maximum=3650):
    """Days until recall falls to the target retention."""
    if not 0 < retention < 1:
        raise ValueError("retention must be between 0 and 1")
    days = stability / FACTOR * (retention ** (1 / DECAY) - 1)
    return max(1, min(maximum, round(days)))


def review(m, grade, elapsed_days):
    """Update a memory after a review. Harder recall at lower retrievability gives a bigger boost."""
    if grade not in GRADE_NAMES:
        raise ValueError("grade must be 1 to 4")
    if m.reps == 0:
        d = min(10.0, max(1.0, 7.0 - 1.5 * (grade - 1)))
        return Memory(FIRST_STABILITY[grade], d, 1, 1 if grade == AGAIN else 0)
    r = recall_probability(m.stability, elapsed_days)
    d = m.difficulty + 0.7 * (3 - grade)
    d = min(10.0, max(1.0, 0.9 * d + 0.1 * 5.0))
    if grade == AGAIN:
        s = max(0.3, 0.8 * (m.stability ** 0.3) * math.exp(0.6 * (1 - r)) * ((11 - d) / 10) ** 0.5)
        return Memory(min(s, m.stability), d, m.reps + 1, m.lapses + 1)
    bonus = {HARD: 0.6, GOOD: 1.0, EASY: 1.7}[grade]
    growth = math.exp(1.2) * (11 - d) * m.stability ** -0.2 * (math.exp(2.0 * (1 - r)) - 1) * bonus
    return Memory(m.stability * (1 + growth), d, m.reps + 1, m.lapses)


def forecast(due_dates, days, today):
    """How many cards fall due on each of the coming days. Overdue cards count for today."""
    out = [0] * days
    for d in due_dates:
        i = max(0, (d - today).days)
        if i < days:
            out[i] += 1
    return out


def true_retention(log):
    """log: grades of reviews of known cards. The share not forgotten."""
    known = [g for g in log]
    return sum(1 for g in known if g != AGAIN) / len(known) if known else None


def simulate(cards=200, days=120, retention=0.9, seed=0, true_stability_scale=1.0):
    """Run the scheduler against a simulated learner whose memory follows the same curve.
    Returns (reviews per day, recall rate at review time)."""
    import random
    rng = random.Random(seed)
    state = [dict(m=Memory(), due=0, last=0) for _ in range(cards)]
    reviews = [0] * days
    hits = total = 0
    for day in range(days):
        for s in state:
            if s["due"] > day:
                continue
            m = s["m"]
            elapsed = day - s["last"]
            if m.reps == 0:
                grade = GOOD
            else:
                p = recall_probability(m.stability * true_stability_scale, elapsed)
                total += 1
                if rng.random() < p:
                    hits += 1
                    grade = GOOD
                else:
                    grade = AGAIN
            s["m"] = review(m, grade, elapsed)
            s["last"] = day
            s["due"] = day + (1 if grade == AGAIN else next_interval(s["m"].stability, retention))
            reviews[day] += 1
    return reviews, hits / total if total else None


def parse_deck(text):
    """Cards from text: one per line, front and back separated by a tab or by ' | '. Lines starting with # are skipped."""
    out, problems = [], []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t") if "\t" in line else line.split(" | ")
        if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():
            problems.append(f"line {number}: needs a front and a back")
            continue
        out.append((parts[0].strip(), parts[1].strip()))
    return out, problems
