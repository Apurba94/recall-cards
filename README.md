# Recall Cards

Study flashcards at the moment you are about to forget them. Recall Cards decides when each card should come back, and it works offline, in English, Bangla or any other language.

```
python -m recall_cards
```

Then open http://127.0.0.1:8025. Add cards as `front | back`, one per line. Python 3.10 or newer is all it needs.

## How the scheduling works

Memory fades along a curve. Reviewing just as a memory weakens strengthens it the most, so the gaps between reviews can keep growing.

Each card tracks two things: **stability**, the number of days until your chance of recall falls to 90%, and **difficulty**. After each review, these update, and the next date is set to aim for your target retention, which is 90% by default.

The memory model is in the style of FSRS, simplified to a few fixed constants. The classic SM-2 algorithm is also included in `core.py`, as the published rule.

## What the app does

- Decks, with import from plain text, and duplicates ignored
- Four grades: Again, Hard, Good and Easy
- Statistics: what you actually remembered against your target, a forecast of coming reviews, and your hardest cards

## How it is tested

SM-2 is checked against its published interval sequence and ease formula. The scheduler is tested by simulating a learner whose memory follows the same forgetting curve: at targets of 80%, 90% and 95%, the achieved recall must land within 3 points of the target, and the daily workload must fall after the first days.

That simulation assumes memory behaves as the model says, so it proves the scheduler is consistent. It does not prove how well this works for real learners.

## Limits

The model's constants were chosen by hand, and not fitted to real review data as full FSRS is. It is for one person, with no sync between devices. Cards are plain text, with no images or audio.

## Tests

```
python -m unittest discover -s tests
```

MIT licence.
