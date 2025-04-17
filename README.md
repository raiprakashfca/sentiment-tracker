# 📈 NIFTY Sentiment Tracker (Options Greeks Based)

This dashboard tracks market sentiment in NIFTY by summing Delta, Vega, and Theta from strikes between 0.05 to 0.60 Delta. Built for option sellers to identify trending vs rangebound markets.

## 🚀 Features

- Streamlit dashboard with live visualization
- Daily token handling via Google Sheets
- Easy deployment on Streamlit Cloud

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
