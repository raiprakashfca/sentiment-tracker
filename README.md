# 📈 NIFTY Sentiment Tracker (Options Greeks Based)

This dashboard tracks market sentiment in NIFTY by summing Delta, Vega, and Theta from strikes between 0.05 to 0.60 Delta. Built for option sellers to identify trending vs rangebound markets.

## 🚀 Features

- Streamlit dashboard with live visualization
- Daily token handling via Google Sheets
- Easy deployment on Streamlit Cloud
- News headline sentiment signal powered by [TypeSafe](https://typesafe.ai) (optional)

## 🛠️ Setup

1. Clone the repo
2. Add your Google Sheet secrets in Streamlit Cloud
3. Deploy from `main_app.py`

## 🔐 Secrets Format

Paste your `gcreds.json` content in Streamlit secrets like:

```toml
[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\nABC\nXYZ\n-----END PRIVATE KEY-----\n"
client_email = "..."
...
```

## 📰 News Headline Sentiment (TypeSafe)

The dashboard can add a second, news-based read on the market next to the Greeks signal.
It pulls recent NIFTY / Sensex headlines from Google News RSS, sends them in one request to
TypeSafe's System One model (Jev), and asks two narrow questions per headline:

- a **Score** on five levels, from *strongly bearish* to *strongly bullish*, for what the headline
  implies about near-term NIFTY direction;
- a **Noul** (yes/no probability) for whether the headline is about the Indian market at all.

Code does the rest: off-topic headlines are dropped, the remaining biases are weighted by
relevance, and thresholds in `news_sentiment.py` turn the weighted bias into
`BULLISH` / `NEUTRAL` / `BEARISH` (or `NO SIGNAL` when too few relevant headlines are found).
Results are cached for 15 minutes, so the 60-second auto-refresh does not re-query the model.

To enable it, add your TypeSafe API key (from https://console.typesafe.ai/) to Streamlit secrets:

```toml
TYPESAFE_API_KEY = "ts-..."
# optional, defaults to jev-latest
# TYPESAFE_MODEL = "jev-1.13.0"
```

Without the key the section shows a setup hint and the rest of the dashboard works as before.

Run the unit tests with:

```bash
python -m pytest test_news_sentiment.py
```
