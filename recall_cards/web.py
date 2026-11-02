"""The offline web app. Days are passed in as a clock, so tests can move through time."""
from datetime import date, timedelta

from . import core
from .fieldkit import App, Fail, Raw, bar_chart, card, form, h, link, line_chart, redirect, stats, table

SCHEMA = """
CREATE TABLE IF NOT EXISTS decks (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS cards (id INTEGER PRIMARY KEY, deck INTEGER NOT NULL REFERENCES decks(id), front TEXT NOT NULL, back TEXT NOT NULL,
  stability REAL NOT NULL DEFAULT 0, difficulty REAL NOT NULL DEFAULT 5, reps INTEGER NOT NULL DEFAULT 0, lapses INTEGER NOT NULL DEFAULT 0, due TEXT NOT NULL, last TEXT, UNIQUE (deck, front));
CREATE TABLE IF NOT EXISTS log (id INTEGER PRIMARY KEY, card INTEGER NOT NULL REFERENCES cards(id), day TEXT NOT NULL, grade INTEGER NOT NULL, new INTEGER NOT NULL);
"""


def create_app(db="recall.db", today=date.today, retention=0.9):
    a = App("Recall Cards", db, SCHEMA, [("Decks", "/"), ("Add cards", "/add"), ("Statistics", "/stats")])

    @a.route("/")
    def home(req):
        now = today().isoformat()
        rows = a.rows("SELECT d.id, d.name, COUNT(c.id) total, SUM(CASE WHEN c.due <= ? THEN 1 ELSE 0 END) due FROM decks d LEFT JOIN cards c ON c.deck = d.id GROUP BY d.id ORDER BY d.name", now)
        return a.page("Your decks", stats([("Due today", a.one("SELECT COUNT(*) FROM cards WHERE due <= ?", now)), ("Cards", a.one("SELECT COUNT(*) FROM cards"))]) + card("Decks", table(rows, [("Deck", lambda r: link(f"/study/{r['id']}", r["name"])), ("Cards", "total"), ("Due", lambda r: r["due"] or 0)], "No decks yet. Add some cards.")))

    @a.route("/add", ("GET", "POST"))
    def add(req):
        if req.method == "POST":
            name = req.text("deck", limit=200)
            a.run("INSERT OR IGNORE INTO decks (name) VALUES (?)", name)
            deck = a.one("SELECT id FROM decks WHERE name = ?", name)
            found, problems = core.parse_deck(req.text("cards", limit=2_000_000))
            added = 0
            for front, back in found:
                added += a.run("INSERT OR IGNORE INTO cards (deck, front, back, due) VALUES (?, ?, ?, ?)", deck, front, back, today().isoformat()).rowcount
            note = f"Added {added} cards." + (" Skipped: " + "; ".join(problems) if problems else "")
            return a.page("Add cards", card("Done", f"<p>{h(note)}</p>"))
        return a.page("Add cards", card("One card per line, as front | back", form(a, "/add", [("deck", "Deck"), ("cards", "Cards", "textarea", "কম্পিউটার | computer\nপানি | water")], "Add")))

    @a.route("/study/<deck>", ("GET", "POST"))
    def study(req, deck):
        name = a.one("SELECT name FROM decks WHERE id = ?", deck)
        if name is None:
            raise Fail("No such deck", 404)
        now = today()
        if req.method == "POST":
            c = a.row("SELECT * FROM cards WHERE id = ?", req.text("card"))
            grade = int(req.number("grade", low=1, high=4))
            if c is None:
                raise Fail("No such card", 404)
            m = core.Memory(c["stability"], c["difficulty"], c["reps"], c["lapses"])
            elapsed = (now - date.fromisoformat(c["last"])).days if c["last"] else 0
            n = core.review(m, grade, elapsed)
            days = 1 if grade == core.AGAIN else core.next_interval(n.stability, retention)
            due = (now + timedelta(days=days)).isoformat()
            a.run("UPDATE cards SET stability=?, difficulty=?, reps=?, lapses=?, due=?, last=? WHERE id=?", n.stability, n.difficulty, n.reps, n.lapses, due, now.isoformat(), c["id"])
            a.run("INSERT INTO log (card, day, grade, new) VALUES (?, ?, ?, ?)", c["id"], now.isoformat(), grade, int(m.reps == 0))
            return redirect(f"/study/{deck}")
        c = a.row("SELECT * FROM cards WHERE deck = ? AND due <= ? ORDER BY reps = 0, due, id LIMIT 1", deck, now.isoformat())
        if c is None:
            return a.page(name, card("All done", "<p>No more cards are due in this deck today.</p>"))
        left = a.one("SELECT COUNT(*) FROM cards WHERE deck = ? AND due <= ?", deck, now.isoformat())
        buttons = "".join(f'<form method="post" action="/study/{deck}" style="display:inline-block;margin:4px">{a.form_token()}<input type="hidden" name="card" value="{c["id"]}"><input type="hidden" name="grade" value="{g}"><button>{core.GRADE_NAMES[g]}</button></form>' for g in core.GRADE_NAMES)
        body = f'<div class="card"><p class="muted">{left} due</p><h2>{h(c["front"])}</h2><details><summary>Show answer</summary><p>{h(c["back"])}</p>{buttons}</details></div>'
        return a.page(name, body)

    @a.route("/stats")
    def statistics(req):
        now = today()
        dues = [date.fromisoformat(r["due"]) for r in a.rows("SELECT due FROM cards")]
        coming = core.forecast(dues, 14, now)
        log = [r["grade"] for r in a.rows("SELECT grade FROM log WHERE new = 0")]
        retention_now = core.true_retention(log)
        days = a.rows("SELECT day, COUNT(*) n FROM log GROUP BY day ORDER BY day")
        hard = a.rows("SELECT front, lapses FROM cards WHERE lapses > 0 ORDER BY lapses DESC LIMIT 10")
        body = stats([("Reviews", a.one("SELECT COUNT(*) FROM log")), ("Remembered", "n/a" if retention_now is None else f"{retention_now:.0%}"), ("Target", f"{retention:.0%}")])
        body += card("Reviews coming up", bar_chart([((now + timedelta(days=i)).strftime("%d %b"), n) for i, n in enumerate(coming)]))
        body += card("Reviews per day", line_chart([(r["day"], r["n"]) for r in days]))
        body += card("Hardest cards", table(hard, [("Card", "front"), ("Forgotten", "lapses")], "None yet."))
        return a.page("Statistics", body)

    return a
