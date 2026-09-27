"""News headline sentiment signal for the Greeks dashboard, powered by TypeSafe.

Flow (code owns the workflow, the model supplies the judgment):

1. ``fetch_headlines``  pulls recent NIFTY / Sensex headlines from Google News RSS
   and filters them by age in code.
2. ``judge_headlines``  sends every headline to TypeSafe's System One model in ONE
   request. For each headline it asks two narrow questions:
     * a Score: what the headline implies for the near-term NIFTY direction,
       on five concrete levels from strongly bearish to strongly bullish;
     * a Noul: whether the headline is about the Indian equity market at all,
       so off-topic items can be down-weighted in code.
3. ``aggregate``        turns the per-headline answers into one signal with a
   relevance-weighted bias in [-1, 1] and a label. Thresholds live here, so they
   can be tuned without re-running inference.

No API key? ``judge_headlines`` raises ``MissingApiKey`` and the dashboard shows
how to enable the section instead of failing.
"""

from __future__ import annotations

import datetime as _dt
import email.utils
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------- headlines --

NEWS_QUERY = 'NIFTY OR Sensex OR "Bank Nifty" OR "Indian stock market"'
GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
)
DEFAULT_MAX_HEADLINES = 20
DEFAULT_MAX_AGE_HOURS = 48

# Google News appends " - Publisher" to every title; strip it, the <source> tag
# already carries the publisher.
_TRAILING_SOURCE = re.compile(r"\s+-\s+[^-]+$")


@dataclass
class Headline:
    title: str
    source: str
    published: _dt.datetime | None
    link: str = ""

    def as_state(self) -> dict[str, str]:
        """The fields the model sees. Keep it small: title and source only."""
        return {"title": self.title, "source": self.source}


def _parse_pubdate(value: str | None) -> _dt.datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed


def parse_rss(xml_text: str) -> list[Headline]:
    """Parse a Google News RSS document into headlines, newest first, de-duplicated."""
    root = ET.fromstring(xml_text)
    seen: set[str] = set()
    items: list[Headline] = []
    for item in root.findall("./channel/item"):
        raw_title = (item.findtext("title") or "").strip()
        if not raw_title:
            continue
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None else ""
        title = _TRAILING_SOURCE.sub("", raw_title).strip() if source else raw_title
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(
            Headline(
                title=title,
                source=source,
                published=_parse_pubdate(item.findtext("pubDate")),
                link=(item.findtext("link") or "").strip(),
            )
        )
    items.sort(key=lambda h: h.published or _dt.datetime.min.replace(tzinfo=_dt.timezone.utc), reverse=True)
    return items


def filter_headlines(
    headlines: list[Headline],
    *,
    now: _dt.datetime | None = None,
    max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
    max_items: int = DEFAULT_MAX_HEADLINES,
) -> list[Headline]:
    """Age filtering and capping happen in code, not in the model (Jev does not compare dates)."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    cutoff = now - _dt.timedelta(hours=max_age_hours)
    fresh = [h for h in headlines if h.published is None or h.published >= cutoff]
    return fresh[:max_items]


def fetch_headlines(
    *,
    query: str = NEWS_QUERY,
    max_items: int = DEFAULT_MAX_HEADLINES,
    max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
    timeout: float = 10.0,
) -> list[Headline]:
    url = GOOGLE_NEWS_RSS.format(query=urllib.parse.quote(query))
    request = urllib.request.Request(url, headers={"User-Agent": "sentiment-tracker/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        xml_text = response.read().decode("utf-8", errors="replace")
    return filter_headlines(parse_rss(xml_text), max_age_hours=max_age_hours, max_items=max_items)


# ---------------------------------------------------------------- questions --

# Ordered from bearish to bullish. Each level describes a concrete situation and
# stands on its own, as the Score primitive docs ask.
DIRECTION_LEVELS: list[str] = [
    "Strongly bearish: the headline reports a sharp fall, crash, heavy losses, "
    "panic selling, or a major negative shock for Indian equities",
    "Mildly bearish: the headline reports weakness, a modest decline, caution, "
    "profit booking, or a headwind such as FII selling, rising crude, or weak global cues",
    "Neutral or mixed: a flat or range-bound market, balanced or conflicting signals, "
    "or a factual item with no clear implication for market direction",
    "Mildly bullish: the headline reports gains, a recovery, buying interest, or a "
    "supportive factor such as FII inflows, rate-cut hopes, or upbeat earnings",
    "Strongly bullish: the headline reports a sharp rally, record highs, a broad-based "
    "surge, or a major positive shock for Indian equities",
]
NEUTRAL_LEVEL = 2  # index of the neutral level; used to centre scores on zero

MARKET_CONTEXT = (
    "Headlines from Indian financial news. NIFTY 50 and Sensex are India's benchmark "
    "equity indices; Bank Nifty is the banking index. FII means foreign institutional "
    "investors. The reader is an options seller who wants to know whether news points "
    "to a rising, falling, or range-bound market in the next few sessions."
)


def build_state(headlines: list[Headline]) -> dict[str, Any]:
    return {"context": MARKET_CONTEXT, "headlines": [h.as_state() for h in headlines]}


def build_questions(headlines: list[Headline]) -> dict[str, Any]:
    """One direction Score and one relevance Noul per headline, referenced by state path."""
    from typesafe_sdk import Noul, NoulCriteria, Score

    questions: dict[str, Any] = {}
    for i in range(len(headlines)):
        path = f"`headlines[{i}].title`"
        questions[f"direction_{i}"] = Score(
            instructions=(
                f"Based only on {path}, what does this headline imply for the near-term "
                "direction of the NIFTY 50 / Indian equity market?"
            ),
            criteria=DIRECTION_LEVELS,
        )
        questions[f"relevant_{i}"] = Noul(
            instructions=(
                f"Is {path} about the Indian stock market (NIFTY, Sensex, Bank Nifty, or "
                "Indian equities broadly), or about a macro factor that moves it?"
            ),
            criteria=NoulCriteria(
                true=(
                    "Mentions Indian indices, Indian stocks, FII/DII flows, RBI policy, "
                    "Indian macro data, or global events framed by their effect on India"
                ),
                false=(
                    "About a single company's product, personal finance tips, crypto, a "
                    "foreign market with no Indian angle, or an unrelated topic"
                ),
            ),
        )
    return questions


# ----------------------------------------------------------------- judging --


class MissingApiKey(RuntimeError):
    """Raised when no TypeSafe API key is configured."""


@dataclass
class HeadlineJudgment:
    headline: Headline
    score: float          # 0..4 position on DIRECTION_LEVELS
    confidence: float     # 0..1, how peaked the Score distribution is
    relevance: float      # 0..1, probability the headline is about the Indian market
    probabilities: dict[int, float] = field(default_factory=dict)

    @property
    def bias(self) -> float:
        """Direction centred on zero: -1 strongly bearish, +1 strongly bullish."""
        return (self.score - NEUTRAL_LEVEL) / NEUTRAL_LEVEL


@dataclass
class JudgedBatch:
    judgments: list[HeadlineJudgment]
    model: str
    input_tokens: int


def resolve_api_key(explicit: str | None = None) -> str | None:
    return explicit or os.environ.get("TYPESAFE_API_KEY") or None


def judge_headlines(
    headlines: list[Headline],
    *,
    api_key: str | None = None,
    model: str | None = None,
    timeout: float = 20.0,
) -> JudgedBatch:
    """Ask TypeSafe about every headline in a single request."""
    key = resolve_api_key(api_key)
    if not key:
        raise MissingApiKey("TYPESAFE_API_KEY is not set")
    if not headlines:
        return JudgedBatch(judgments=[], model=model or "", input_tokens=0)

    from typesafe_sdk import TypeSafeClient

    with TypeSafeClient(api_key=key, model=model, timeout=timeout) as client:
        response = client.system_one(build_state(headlines), build_questions(headlines))
    return _judgments_from_response(headlines, response)


def _judgments_from_response(headlines: list[Headline], response: Any) -> JudgedBatch:
    judgments = []
    for i, headline in enumerate(headlines):
        score_answer = response.scores[f"direction_{i}"]
        noul_answer = response.nouls[f"relevant_{i}"]
        judgments.append(
            HeadlineJudgment(
                headline=headline,
                score=float(score_answer.score),
                confidence=float(score_answer.confidence),
                relevance=float(noul_answer.noul),
                probabilities={int(k): float(v) for k, v in dict(score_answer.probabilities).items()},
            )
        )
    usage = getattr(response, "usage", None)
    return JudgedBatch(
        judgments=judgments,
        model=str(getattr(response, "model", "") or ""),
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
    )


# --------------------------------------------------------------- aggregate --

RELEVANCE_THRESHOLD = 0.5   # headlines below this do not count toward the signal
BULLISH_THRESHOLD = 0.25    # weighted bias above this -> BULLISH
BEARISH_THRESHOLD = -0.25   # weighted bias below this -> BEARISH
MIN_RELEVANT = 3            # fewer relevant headlines than this -> NO SIGNAL


@dataclass
class NewsSignal:
    label: str                # BULLISH / BEARISH / NEUTRAL / NO SIGNAL
    bias: float               # relevance-weighted mean bias, -1..1
    confidence: float         # relevance-weighted mean Score confidence, 0..1
    relevant_count: int
    total_count: int


def aggregate(
    judgments: list[HeadlineJudgment],
    *,
    relevance_threshold: float = RELEVANCE_THRESHOLD,
    bullish_threshold: float = BULLISH_THRESHOLD,
    bearish_threshold: float = BEARISH_THRESHOLD,
    min_relevant: int = MIN_RELEVANT,
) -> NewsSignal:
    """Combine per-headline answers. The model's raw judgments stay untouched; policy lives here."""
    relevant = [j for j in judgments if j.relevance >= relevance_threshold]
    total_weight = sum(j.relevance for j in relevant)
    if len(relevant) < min_relevant or total_weight <= 0:
        return NewsSignal("NO SIGNAL", 0.0, 0.0, len(relevant), len(judgments))

    bias = sum(j.bias * j.relevance for j in relevant) / total_weight
    confidence = sum(j.confidence * j.relevance for j in relevant) / total_weight
    if bias >= bullish_threshold:
        label = "BULLISH"
    elif bias <= bearish_threshold:
        label = "BEARISH"
    else:
        label = "NEUTRAL"
    return NewsSignal(label, bias, confidence, len(relevant), len(judgments))


def level_name(score: float) -> str:
    """Short label for the nearest level, for display only."""
    names = ["Strongly bearish", "Mildly bearish", "Neutral", "Mildly bullish", "Strongly bullish"]
    idx = max(0, min(len(names) - 1, int(round(score))))
    return names[idx]
