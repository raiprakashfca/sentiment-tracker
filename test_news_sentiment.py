"""Tests for news_sentiment. Run with: python -m pytest test_news_sentiment.py

The TypeSafe call is exercised against a mocked HTTP transport so the SDK's real
request building and response parsing are covered without a network or API key.
"""

import datetime as dt
import json

import httpx2 as httpx  # the TypeSafe SDK uses httpx2 for transport
import pytest

import news_sentiment as ns

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title>
<item><title>Sensex crashes 1,200 points as crude tops $105 - NDTV</title>
  <link>https://example/1</link><pubDate>Thu, 24 Sep 2026 09:02:35 GMT</pubDate>
  <source url="https://ndtv.com">NDTV</source></item>
<item><title>Nifty ends flat in range-bound session - Mint</title>
  <link>https://example/2</link><pubDate>Fri, 25 Sep 2026 10:00:00 GMT</pubDate>
  <source url="https://mint.com">Mint</source></item>
<item><title>Nifty ends flat in range-bound session - Mint</title>
  <link>https://example/2b</link><pubDate>Fri, 25 Sep 2026 10:01:00 GMT</pubDate>
  <source url="https://mint.com">Mint</source></item>
<item><title>Top 5 credit cards for cashback - Blog</title>
  <link>https://example/3</link><pubDate>Mon, 01 Sep 2026 10:00:00 GMT</pubDate>
  <source url="https://blog">Blog</source></item>
</channel></rss>"""


def test_parse_rss_strips_source_dedupes_and_sorts_newest_first():
    items = ns.parse_rss(RSS)
    assert [h.title for h in items] == [
        "Nifty ends flat in range-bound session",
        "Sensex crashes 1,200 points as crude tops $105",
        "Top 5 credit cards for cashback",
    ]
    assert items[0].source == "Mint"
    assert items[1].published == dt.datetime(2026, 9, 24, 9, 2, 35, tzinfo=dt.timezone.utc)


def test_filter_headlines_drops_stale_and_caps():
    items = ns.parse_rss(RSS)
    now = dt.datetime(2026, 9, 26, 12, 0, tzinfo=dt.timezone.utc)
    fresh = ns.filter_headlines(items, now=now, max_age_hours=72, max_items=10)
    assert [h.title for h in fresh] == [
        "Nifty ends flat in range-bound session",
        "Sensex crashes 1,200 points as crude tops $105",
    ]
    assert len(ns.filter_headlines(items, now=now, max_age_hours=72, max_items=1)) == 1


def test_build_questions_one_score_and_one_noul_per_headline():
    items = ns.parse_rss(RSS)[:2]
    questions = ns.build_questions(items)
    assert set(questions) == {"direction_0", "relevant_0", "direction_1", "relevant_1"}
    assert "`headlines[1].title`" in questions["direction_1"].instructions
    assert list(questions["direction_0"].criteria) == ns.DIRECTION_LEVELS


def _judgment(score, confidence=0.8, relevance=0.9):
    return ns.HeadlineJudgment(ns.Headline("x", "y", None), score, confidence, relevance)


def test_bias_is_centred_on_neutral_level():
    assert _judgment(0).bias == -1.0
    assert _judgment(2).bias == 0.0
    assert _judgment(4).bias == 1.0


def test_aggregate_weights_by_relevance_and_ignores_off_topic():
    js = [
        _judgment(0.0, relevance=1.0),   # strongly bearish, relevant
        _judgment(1.0, relevance=0.5),   # mildly bearish, borderline relevant
        _judgment(2.0, relevance=1.0),   # neutral, relevant
        _judgment(4.0, relevance=0.1),   # bullish but off-topic -> ignored
    ]
    signal = ns.aggregate(js)
    assert signal.relevant_count == 3 and signal.total_count == 4
    expected = (-1.0 * 1.0 + -0.5 * 0.5 + 0.0 * 1.0) / 2.5
    assert signal.bias == pytest.approx(expected)
    assert signal.label == "BEARISH"


def test_aggregate_needs_minimum_relevant_headlines():
    signal = ns.aggregate([_judgment(4.0), _judgment(4.0)])
    assert signal.label == "NO SIGNAL"
    assert signal.relevant_count == 2


def test_aggregate_labels():
    assert ns.aggregate([_judgment(3.5)] * 3).label == "BULLISH"
    assert ns.aggregate([_judgment(2.2)] * 3).label == "NEUTRAL"


def test_judge_headlines_requires_api_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(ns.MissingApiKey):
        ns.judge_headlines(ns.parse_rss(RSS)[:1])


def test_judge_headlines_end_to_end_with_mock_transport(monkeypatch):
    """Drive the real SDK against a fake TypeSafe endpoint."""
    from typesafe_sdk import TypeSafeClient

    headlines = ns.parse_rss(RSS)[:2]
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("authorization")
        answers = {}
        for i, (score_probs, noul) in enumerate([
            ({"0": 0.0, "1": 0.1, "2": 0.9, "3": 0.0, "4": 0.0}, 0.95),
            ({"0": 0.8, "1": 0.2, "2": 0.0, "3": 0.0, "4": 0.0}, 0.97),
        ]):
            score = sum(int(k) * v for k, v in score_probs.items())
            answers[f"direction_{i}"] = {
                "type": "score", "score": score, "confidence": 0.8,
                "legend": {str(k): lvl for k, lvl in enumerate(ns.DIRECTION_LEVELS)},
                "probabilities": score_probs,
            }
            answers[f"relevant_{i}"] = {"type": "noul", "noul": noul}
        return httpx.Response(200, json={
            "model": "jev-1.13.0", "answers": answers,
            "usage": {"input_tokens": 512, "output_tokens": 40},
        })

    real_init = TypeSafeClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(TypeSafeClient, "__init__", patched_init)

    batch = ns.judge_headlines(headlines, api_key="test-key")

    assert captured["auth"] == "Bearer test-key"
    body = captured["body"]
    assert body["state"]["headlines"][0] == {"title": headlines[0].title, "source": "Mint"}
    assert body["questions"]["direction_0"]["type"] == "score"
    assert body["questions"]["direction_0"]["criteria"] == ns.DIRECTION_LEVELS
    assert body["questions"]["relevant_1"]["type"] == "noul"
    assert body["questions"]["relevant_1"]["criteria"]["true"]

    assert batch.model == "jev-1.13.0" and batch.input_tokens == 512
    assert batch.judgments[0].score == pytest.approx(1.9)
    assert batch.judgments[0].relevance == 0.95
    assert batch.judgments[1].score == pytest.approx(0.2)
    assert batch.judgments[1].probabilities[0] == 0.8

    signal = ns.aggregate(batch.judgments, min_relevant=2)
    assert signal.label == "BEARISH"
