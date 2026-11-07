"""How often the headline scorer agrees with a human reading.

The labels are the author's own reading of each headline, not an independent dataset, so treat the
number as a regression floor and a rough guide, not a benchmark. Hard cases are included on
purpose; the scorer is a word list and gets some of them wrong, which is why the UI calls the
score rough.
"""

from __future__ import annotations

from aletheia.core.news.sentiment import label_for, score_headline

LABELLED: list[tuple[str, str]] = [
    ("Sensex surges 900 points as banks rally", "bullish"),
    ("Nifty hits record high on strong FII inflows", "bullish"),
    ("Infosys beats estimates, raises revenue guidance", "bullish"),
    ("Brokerage upgrades HDFC Bank, sees 20% upside", "bullish"),
    ("Sona BLW zooms 9%; stock hits new high on record Q2 earnings", "bullish"),
    ("Tata Motors wins big export order", "bullish"),
    ("Rupee rebounds against dollar as crude eases", "bullish"),
    ("Sensex crashes 1,200 points on global selloff", "bearish"),
    ("Aequus shares crash 19% after Q2 losses widen", "bearish"),
    ("Dalmia Bharat hits 52-week low after weak Q2 results", "bearish"),
    ("Brokerage downgrades Paytm on regulatory concerns", "bearish"),
    ("Adani shares tumble as probe widens", "bearish"),
    ("Foreign investors dump Indian stocks, outflows hit record", "bearish"),
    ("Company misses estimates, shares slump", "bearish"),
    ("Hindustan Unilever slips 3%, hits 6-year low ahead of results", "bearish"),
    ("Market opens flat ahead of RBI policy", "neutral"),
    ("RBI keeps repo rate unchanged", "neutral"),
    ("Sensex, Nifty trade rangebound in early deals", "neutral"),
    ("Board meeting to consider fund raising on Friday", "neutral"),
    ("Nifty fails to hold gains, ends lower", "bearish"),
    ("Profit falls short of fears, stock not expected to drop", "bullish"),
    ("Stock does not fall despite weak results", "bullish"),
    ("Gold prices fall as dollar strengthens", "bearish"),
    ("Why you should buy the dip in IT stocks", "neutral"),
    ("Is the rally over? Experts weigh in", "neutral"),
]


def test_scorer_agrees_with_the_human_reading_often_enough() -> None:
    wrong = [
        (text, want, label_for(score_headline(text)))
        for text, want in LABELLED
        if label_for(score_headline(text)) != want
    ]
    accuracy = 1 - len(wrong) / len(LABELLED)
    # Floor, set under what the scorer achieves today so a real regression fails.
    assert accuracy >= 0.80, f"accuracy {accuracy:.0%}; wrong: {wrong}"


def test_polarity_is_never_flipped_on_clear_headlines() -> None:
    clear = [(t, w) for t, w in LABELLED[:15] if w != "neutral"]
    flipped = [t for t, want in clear if label_for(score_headline(t)) not in (want, "neutral")]
    assert not flipped, flipped
