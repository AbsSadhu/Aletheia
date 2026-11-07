"""A small, transparent finance lexicon scorer for headlines.

It is deliberately simple and says so in the UI: a handful of weighted words and phrases, with
negation handling. It reads headlines; it does not understand them. Scores run from -1 (bearish)
to +1 (bullish).
"""

from __future__ import annotations

import math
import re

_PHRASES: dict[str, float] = {
    "all-time high": 2.2,
    "record high": 2.2,
    "52-week high": 1.6,
    "52 week high": 1.6,
    "52-week low": -1.6,
    "52 week low": -1.6,
    "profit booking": -0.6,
    "rate cut": 0.6,
    "rate hike": -0.6,
    "beats estimates": 1.6,
    "misses estimates": -1.6,
    "buy rating": 1.2,
    "sell rating": -1.2,
    "buy the dip": 0.7,  # cancels "dip": advice, not a verdict
}

_WORDS: dict[str, float] = {
    # up
    "surge": 2.0,
    "surges": 2.0,
    "surged": 2.0,
    "soar": 2.2,
    "soars": 2.2,
    "soared": 2.2,
    "rally": 1.8,
    "rallies": 1.8,
    "rallied": 1.8,
    "jump": 1.5,
    "jumps": 1.5,
    "jumped": 1.5,
    "gain": 1.0,
    "gains": 1.0,
    "gained": 1.0,
    "rise": 0.9,
    "rises": 0.9,
    "rose": 0.9,
    "climb": 1.0,
    "climbs": 1.0,
    "climbed": 1.0,
    "advance": 0.8,
    "advances": 0.8,
    "record": 1.2,
    "upgrade": 1.5,
    "upgrades": 1.5,
    "upgraded": 1.5,
    "outperform": 1.3,
    "beat": 1.2,
    "beats": 1.2,
    "profit": 0.9,
    "profits": 0.9,
    "growth": 0.9,
    "strong": 0.9,
    "bullish": 1.5,
    "buyback": 1.0,
    "dividend": 0.5,
    "expansion": 0.8,
    "acquisition": 0.5,
    "boost": 1.0,
    "boosts": 1.0,
    "recovery": 0.9,
    "rebound": 1.2,
    "rebounds": 1.2,
    "positive": 0.8,
    "optimism": 1.0,
    "inflows": 0.9,
    "order": 0.4,
    "wins": 0.9,
    "win": 0.9,
    # down
    "plunge": -2.2,
    "plunges": -2.2,
    "plunged": -2.2,
    "crash": -2.5,
    "crashes": -2.5,
    "tumble": -2.0,
    "tumbles": -2.0,
    "tumbled": -2.0,
    "slump": -2.0,
    "slumps": -2.0,
    "slide": -1.3,
    "slides": -1.3,
    "sink": -1.6,
    "sinks": -1.6,
    "fall": -1.1,
    "falls": -1.1,
    "fell": -1.1,
    "drop": -1.0,
    "drops": -1.0,
    "dropped": -1.0,
    "decline": -1.0,
    "declines": -1.0,
    "declined": -1.0,
    "slip": -0.8,
    "slips": -0.8,
    "dip": -0.7,
    "dips": -0.7,
    "loss": -1.3,
    "losses": -1.3,
    "weak": -1.0,
    "weakness": -1.0,
    "downgrade": -1.5,
    "downgrades": -1.5,
    "downgraded": -1.5,
    "underperform": -1.3,
    "miss": -1.3,
    "misses": -1.3,
    "missed": -1.3,
    "bearish": -1.5,
    "selloff": -2.0,
    "sell-off": -2.0,
    "fraud": -2.5,
    "probe": -1.3,
    "penalty": -1.3,
    "fine": -0.6,
    "warns": -1.3,
    "warning": -1.0,
    "concern": -0.9,
    "concerns": -0.9,
    "fear": -1.3,
    "fears": -1.3,
    "outflows": -0.9,
    "cut": -0.8,
    "cuts": -0.8,
    "default": -1.8,
    "recession": -1.6,
    "tension": -0.9,
    "tensions": -0.9,
    "volatile": -0.5,
    "slowdown": -1.2,
    "dump": -1.5,
    "dumps": -1.5,
    "dumped": -1.5,
    "negative": -0.8,
    "pressure": -0.7,
    "lower": -0.5,
    "lowers": -0.6,
}

_NEGATORS = {"not", "no", "never", "without", "unlikely", "fails", "failed", "fail", "denies"}
_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-']*")

#: How far from zero a headline must score to count as bullish or bearish.
NEUTRAL_BAND = 0.15


def score_headline(text: str) -> float:
    """Return a score in [-1, 1]: negative is bearish, positive is bullish."""
    lowered = text.lower()
    total = 0.0
    for phrase, weight in _PHRASES.items():
        if phrase in lowered:
            total += weight
            lowered = lowered.replace(phrase, " ")  # do not double count its words
    tokens = _TOKEN.findall(lowered)
    for i, tok in enumerate(tokens):
        word_weight = _WORDS.get(tok)
        if word_weight is None:
            continue
        if any(t in _NEGATORS for t in tokens[max(0, i - 3) : i]):
            word_weight = -word_weight * 0.8
        total += word_weight
    if text.rstrip().endswith("?"):
        total *= 0.3  # a question asks; it does not report
    return round(math.tanh(total / 3.0), 3)


def label_for(score: float) -> str:
    if score >= NEUTRAL_BAND:
        return "bullish"
    if score <= -NEUTRAL_BAND:
        return "bearish"
    return "neutral"
