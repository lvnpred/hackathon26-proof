"""Plan I2-b: the follow-up date from the review line. Pure; the visit day is always passed in."""
from datetime import date

from doctor_dictation.core import followup as F

SAT = date(2026, 10, 17)

def test_one_clear_duration_in_digits_words_or_hinglish_gives_a_date():
    for text, iso in [("1 week", "2026-10-24"), ("after 5 days", "2026-10-22"), ("2 months", "2026-12-17"), ("one week", "2026-10-24"),
                      ("two weeks", "2026-10-31"), ("10 days", "2026-10-27"), ("next month", "2026-11-17"), ("1wk", "2026-10-24"),
                      ("Review after 1 week with reports", "2026-10-24"), ("review after a fortnight", "2026-10-31"), ("ek hafte baad", "2026-10-24"),
                      ("15 din baad", "2026-11-01"), ("do mahine", "2026-12-17"), ("In 2 weeks with repeat USG KUB report", "2026-10-31"),
                      ("review in 2 yrs", "2028-10-17")]:
        assert F.review_date(text, SAT) == iso, text
    assert F.parse("Review after 1 week (next week)") == (1, "week")                 # the same duration twice is one

def test_no_duration_a_range_two_durations_or_an_event_gives_no_date():
    for text in ["SOS", "review SOS", "if needed", "as required", "review if fever persists", "", None, "5-7 days", "5 to 7 days", "1 week or 10 days",
                 "after 2 weeks 3 days", "review after 1 month, repeat CBC in 2 weeks", "kal", "1/52", "review on 24/10", "2 days after the USG",
                 "Review a day after the scan", "after 1 week of treatment", "100 weeks", "0 days", "do review", "come back in 2 days or if worse", "1 week " + "x" * 200]:
        assert F.parse(text) is None and F.review_date(text, SAT) == "", text
    assert F.review_date("1 week", None) == "" and F.LIMITS == {"day": 366, "week": 52, "month": 24, "year": 5}

def test_months_and_years_clamp_to_the_last_day_of_the_month():
    for visit, n, unit, iso in [(date(2026, 1, 31), 1, "month", "2026-02-28"), (date(2026, 10, 31), 1, "month", "2026-11-30"),
                                (date(2026, 11, 30), 3, "month", "2027-02-28"), (date(2028, 2, 29), 1, "year", "2029-02-28"),
                                (date(2028, 1, 31), 1, "month", "2028-02-29"), (date(2026, 12, 24), 2, "week", "2027-01-07"),
                                (date(2026, 10, 31), 1, "week", "2026-11-07"), (date(2026, 10, 31), 2, "month", "2026-12-31")]:
        assert F.add(visit, n, unit).isoformat() == iso, (visit, n, unit)

def test_the_label_is_fixed_english_and_stamp_sets_review_date_only():
    assert [F.date_label(d) for d in ("2026-10-24", "2027-01-07", "2029-02-28", "", "bad", None)] == ["Sat 24 Oct 2026", "Thu 7 Jan 2027", "Wed 28 Feb 2029", "", "", ""]
    form = {"review": "after 1 week", "review_date": "1999-01-01", "rx": []}
    assert F.stamp(form, SAT) is form and form == {"review": "after 1 week", "review_date": "2026-10-24", "rx": []}
    assert F.stamp({"review": "SOS"}, SAT)["review_date"] == "" and F.stamp({}, SAT)["review_date"] == ""


REJECT = """day after tomorrow|1.5 months|1.5 weeks|1,5 months|half a month|half month|one and a half weeks|3–4 days|3—4 days|3 4 days|1,2 weeks
1 – 2 weeks|1 to 2 weeks|3-4 days|once a week|twice a week|once weekly|every 2 weeks|review every 2 weeks|every week|weekly
no need to review for 6 months|not required after 2 weeks|no review needed|do not review for 1 month|for 5 days then review|1 month course
for 1 month|course of 5 days|repeat CBC after 1 week|repeat test after 2 weeks|after completing 5 days|continue for 2 weeks
-1 week|-5 days|−1 week|–5 days|- 1 week|Review after 1 week or SOS|review after 3 days if fever persists|if fever persists after 3 days
if no relief within 3 days|within 3 days|within 1 week|maximum 3 days|1 week or earlier|next week or earlier|come after 3 days or earlier if pain
only if not better after 1 week|review if no improvement in 3 days|after 2 weeks if not better|come back in 2 days or if worse|next week Monday
next 2 weeks|next visit 25/10 or after 1 week|review after 1 week and again after 1 month""".replace("\n", "|").split("|")

ACCEPT = {"1 week": "2026-10-24", "one week": "2026-10-24", "a week": "2026-10-24", "1week": "2026-10-24", "REVIEW AFTER 1 WEEK": "2026-10-24",
          "1 wk": "2026-10-24", "2 weeks": "2026-10-31", "after 5 days": "2026-10-22", "in 10 days": "2026-10-27", "after one month": "2026-11-17",
          "next month": "2026-11-17", "2 months": "2026-12-17", "3 months": "2027-01-17", "6 months": "2027-04-17", "after 1 year": "2027-10-17",
          "tomorrow": "2026-10-18", "fortnight": "2026-10-31", "twenty days": "2026-11-06", "do hafte": "2026-10-31", "teen din baad": "2026-10-20",
          "1 week later": "2026-10-24", "Review after 1 week": "2026-10-24", "Review in 2 weeks": "2026-10-31", "next week": "2026-10-24"}


def test_the_table_of_refused_lines_gives_no_date():
    assert len(REJECT) == 56
    for text in REJECT:
        assert F.parse(text) is None and F.review_date(text, SAT) == "", text


def test_the_table_of_clear_lines_keeps_its_exact_date():
    for text, iso in ACCEPT.items():
        assert F.review_date(text, SAT) == iso, text


def test_any_refuse_word_next_to_a_clear_duration_removes_the_date():
    words = ["if", "unless", "sos", "within", "earlier", "persists", "worse", "needed", "required", "only", "maximum", "every", "weekly", "once",
             "twice", "no", "not", "never", "course", "continue", "then", "half", "monday", "sat", "1.5", "next 2", "for 3 days"]
    for w in words:
        for text in (f"review after 1 week {w}", f"{w} review after 1 week"):
            assert F.review_date(text, SAT) == "", text


def test_a_visit_day_near_the_end_of_time_gives_no_date_instead_of_an_error():
    assert F.review_date("1 week", date(9999, 12, 30)) == "" and F.review_date("1 year", date(9999, 6, 1)) == ""
