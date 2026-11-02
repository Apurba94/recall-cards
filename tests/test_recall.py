import re
import unittest
from datetime import date, timedelta

from recall_cards import core, create_app
from recall_cards.core import AGAIN, EASY, GOOD, HARD, Memory, Sm2State, forecast, next_interval, parse_deck, recall_probability, review, simulate, sm2, true_retention


class TestSm2(unittest.TestCase):
    def test_published_interval_sequence(self):
        s = Sm2State()
        s = sm2(s, 5)
        self.assertEqual(s.interval, 1)
        s = sm2(s, 5)
        self.assertEqual(s.interval, 6)
        s = sm2(s, 5)
        self.assertEqual(s.interval, round(6 * s.ease))

    def test_ease_formula(self):
        self.assertAlmostEqual(sm2(Sm2State(), 5).ease, 2.6)
        self.assertAlmostEqual(sm2(Sm2State(), 4).ease, 2.5)
        self.assertAlmostEqual(sm2(Sm2State(), 3).ease, 2.36)

    def test_ease_has_a_floor(self):
        s = Sm2State()
        for _ in range(30):
            s = sm2(s, 0)
        self.assertEqual(s.ease, 1.3)

    def test_failure_restarts(self):
        s = sm2(sm2(sm2(Sm2State(), 5), 5), 1)
        self.assertEqual((s.interval, s.repetitions), (1, 0))

    def test_bad_quality(self):
        with self.assertRaises(ValueError):
            sm2(Sm2State(), 6)


class TestMemory(unittest.TestCase):
    def test_curve(self):
        self.assertAlmostEqual(recall_probability(10, 10), 0.9)
        self.assertEqual(recall_probability(10, 0), 1)
        self.assertLess(recall_probability(10, 100), recall_probability(10, 50))

    def test_interval_inverts_the_curve(self):
        for s in (5, 30, 200):      # shorter memories are limited by the one-day minimum
            for r in (0.8, 0.9, 0.95):
                self.assertAlmostEqual(recall_probability(s, next_interval(s, r, 10 ** 6)), r, delta=0.03)

    def test_interval_at_ninety_percent_equals_stability(self):
        self.assertEqual(next_interval(25, 0.9), 25)

    def test_higher_retention_means_sooner_reviews(self):
        self.assertLess(next_interval(30, 0.95), next_interval(30, 0.8))

    def test_bad_retention(self):
        with self.assertRaises(ValueError):
            next_interval(10, 1.5)

    def test_better_grades_give_longer_memories(self):
        m = review(Memory(), GOOD, 0)
        s = [review(m, g, 3).stability for g in (HARD, GOOD, EASY)]
        self.assertEqual(s, sorted(s))
        self.assertLess(review(m, AGAIN, 3).stability, m.stability + 1e-9)

    def test_first_ratings(self):
        s = [review(Memory(), g, 0).stability for g in (AGAIN, HARD, GOOD, EASY)]
        self.assertEqual(s, sorted(s))

    def test_lapses_counted_and_difficulty_rises(self):
        m = review(Memory(), GOOD, 0)
        f = review(m, AGAIN, 3)
        self.assertEqual(f.lapses, 1)
        self.assertGreater(f.difficulty, m.difficulty)

    def test_recalling_near_forgetting_helps_most(self):
        m = Memory(10, 5, 3)
        self.assertGreater(review(m, GOOD, 30).stability, review(m, GOOD, 3).stability)

    def test_stability_grows_with_success(self):
        m = review(Memory(), GOOD, 0)
        for _ in range(8):
            d = next_interval(m.stability)
            m = review(m, GOOD, d)
        self.assertGreater(m.stability, 100)


class TestScheduling(unittest.TestCase):
    def test_achieved_recall_matches_the_target(self):
        for target in (0.8, 0.9, 0.95):
            _, rate = simulate(300, 200, target, 1)
            self.assertAlmostEqual(rate, target, delta=0.03)

    def test_daily_load_falls_after_the_start(self):
        reviews, _ = simulate(300, 180, 0.9, 2)
        self.assertLess(sum(reviews[-30:]) / 30, reviews[0] / 2)

    def test_higher_target_costs_more_reviews(self):
        self.assertGreater(sum(simulate(200, 120, 0.95, 3)[0]), sum(simulate(200, 120, 0.8, 3)[0]))

    def test_forecast(self):
        t = date(2026, 11, 2)
        self.assertEqual(forecast([t - timedelta(days=5), t, t + timedelta(days=2), t + timedelta(days=50)], 3, t), [2, 0, 1])

    def test_true_retention(self):
        self.assertEqual(true_retention([GOOD, AGAIN, EASY, GOOD]), 0.75)
        self.assertIsNone(true_retention([]))


class TestParse(unittest.TestCase):
    def test_formats(self):
        cards, problems = parse_deck("# comment\n\na | b\nc\td\nbroken\n | x\n")
        self.assertEqual(cards, [("a", "b"), ("c", "d")])
        self.assertEqual(len(problems), 2)
        self.assertIn("line 5", problems[0])


class Day:
    def __init__(self):
        self.d = date(2026, 11, 2)

    def __call__(self):
        return self.d


class TestApp(unittest.TestCase):
    def setUp(self):
        self.day = Day()
        self.a = create_app(":memory:", self.day)
        self.a.post("/add", deck="Words", cards="পানি | water\nভাত | rice\nবই | book")

    def page(self, url):
        return self.a.get(url).body.decode()

    def answer(self, grade, deck=1):
        card_id = re.search(r'name="card" value="(\d+)"', self.page(f"/study/{deck}")).group(1)
        self.assertEqual(self.a.post(f"/study/{deck}", card=card_id, grade=grade).status, 303)

    def test_new_cards_are_due(self):
        self.assertIn("পানি", self.page("/study/1"))
        self.assertIn(">3<", self.page("/"))

    def test_good_reviews_clear_the_day(self):
        for _ in range(3):
            self.answer(GOOD)
        self.assertIn("All done", self.page("/study/1"))

    def test_again_comes_back_tomorrow_and_good_later(self):
        self.answer(AGAIN)
        self.answer(GOOD)
        self.answer(GOOD)
        self.day.d += timedelta(days=1)
        self.assertEqual(self.a.one("SELECT COUNT(*) FROM cards WHERE due <= ?", self.day.d.isoformat()), 1)
        self.day.d += timedelta(days=2)
        self.assertEqual(self.a.one("SELECT COUNT(*) FROM cards WHERE due <= ?", self.day.d.isoformat()), 3)

    def test_duplicates_are_ignored(self):
        self.a.post("/add", deck="Words", cards="পানি | water")
        self.assertEqual(self.a.one("SELECT COUNT(*) FROM cards"), 3)

    def test_statistics_page(self):
        self.answer(GOOD)
        self.answer(AGAIN)
        self.answer(GOOD)
        self.day.d += timedelta(days=3)
        self.answer(GOOD)
        page = self.page("/stats")
        self.assertIn("100%", page)
        self.assertIn("Reviews coming up", page)

    def test_bad_grade_and_card(self):
        self.assertEqual(self.a.post("/study/1", card=1, grade=9).status, 400)
        self.assertEqual(self.a.post("/study/1", card=99, grade=3).status, 404)
        self.assertEqual(self.a.get("/study/9").status, 404)

    def test_text_is_escaped(self):
        self.a.post("/add", deck="X", cards="<script>x</script> | y")
        self.assertNotIn("<script>x", self.page("/study/2"))


if __name__ == "__main__":
    unittest.main()
