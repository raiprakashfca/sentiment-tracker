import streamlit as st
import pandas as pd
import datetime
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from streamlit_autorefresh import st_autorefresh
import fetch_option_data  # ensure this module is importable

# ---------- PAGE CONFIGURATION ----------
st.set_page_config(page_title="📈 Greeks Sentiment Tracker", layout="wide")

# ---------- SECRETS & CONSTANTS ----------
creds_json = st.secrets.get("GCREDS") or st.secrets.get("gcreds")
if not creds_json:
    st.error("Service account credentials (GCREDS) not found. Please configure your secret.")
    st.stop()
greeks_sheet_id = st.secrets.get("GREEKS_SHEET_ID") or st.secrets.get("greeks_sheet_id")
if not greeks_sheet_id:
    st.error("GREEKS_SHEET_ID secret not found.")
    st.stop()
token_sheet_id = st.secrets.get("TOKEN_SHEET_ID") or st.secrets.get("token_sheet_id")
if not token_sheet_id:
    st.error("TOKEN_SHEET_ID secret not found.")
    st.stop()

# ---------- AUTHENTICATE GOOGLE SHEETS ----------
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
client = gspread.authorize(creds)
wb = client.open_by_key(greeks_sheet_id)
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
client = gspread.authorize(creds)
wb = client.open_by_key(greeks_sheet_id)

# ---------- ENSURE HEADER & INITIAL DATA ----------
log_sheet = wb.worksheet(LOG_WS)
vals = log_sheet.get_all_values()
if not vals or vals[0] != HEADER:
    log_sheet.clear()
    log_sheet.append_row(HEADER)
    try:
        fetch_option_data.log_greeks()
    except Exception as e:
        st.error(f"Failed to log initial data: {e}")
        st.stop()
    vals = log_sheet.get_all_values()
if len(vals) < 2:
    st.error("❌ 'GreeksLog' must have a header row and at least one data row.")
    st.stop()
headers = vals[0]
rows = vals[1:]

# ---------- LOAD DATAFRAME ----------
df = pd.DataFrame(rows, columns=headers)
df['timestamp'] = pd.to_datetime(df['timestamp'], format='%Y-%m-%d %H:%M:%S')
df['timestamp'] = df['timestamp'].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
for col in headers[1:]:
    df[col] = pd.to_numeric(df[col], errors='coerce')

# ---------- OPEN SNAPSHOT ----------
open_sheet = wb.worksheet(OPEN_WS)
open_vals = open_sheet.get_all_values()
if len(open_vals) >= 2 and open_vals[0] == HEADER:
    open_series = pd.Series(open_vals[1], index=open_vals[0]).drop('timestamp').astype(float)
else:
    open_series = df.iloc[0].drop('timestamp').astype(float)

# ---------- CALCULATE CHANGES ----------
latest = df.iloc[-1]
changes = {col: latest[col] - open_series[col] for col in open_series.index}

# ---------- SENTIMENT LOGIC ----------
def classify_sentiment(ce_v, pe_v, ce_t, pe_t):
    if pe_v > 0 and ce_v < 0:
        s = 'BEARISH'
    elif ce_v > 0 and pe_v < 0:
        s = 'BULLISH'
    elif ce_v > 0 and pe_v > 0:
        s = 'RANGE BOUND'
    else:
        s = 'VOLATILE'
    if ce_t < 0 or pe_t < 0:
        s = 'VOLATILE'
    return s

# ---------- BUILD SUMMARY ----------
rows_out = []
today = datetime.datetime.now(pytz.timezone('Asia/Kolkata'))
for key, label in [('nifty', 'NIFTY'), ('bn', 'BANKNIFTY')]:
    ce_d, ce_v, ce_t = (changes[f"{key}_ce_delta"], changes[f"{key}_ce_vega"], changes[f"{key}_ce_theta"])
    pe_d, pe_v, pe_t = (changes[f"{key}_pe_delta"], changes[f"{key}_pe_vega"], changes[f"{key}_pe_theta"])
    sentiment = classify_sentiment(ce_v, pe_v, ce_t, pe_t)
    for opt, d, v, t in [('CE', ce_d, ce_v, ce_t), ('PE', pe_d, pe_v, pe_t)]:
        rows_out.append({'Instrument': f"{label} {opt}", 'SENTIMENT': sentiment,
                         'DELTA': d, 'VEGA': v, 'THETA': t})
oi_cols = [c for c in headers if c.endswith('_oi')]
if oi_cols:
    for entry in rows_out:
        pref = 'nifty' if 'NIFTY' in entry['Instrument'] and 'BANKNIFTY' not in entry['Instrument'] else 'bn'
        opt = 'ce' if entry['Instrument'].endswith('CE') else 'pe'
        entry['OI'] = changes.get(f"{pref}_{opt}_oi")
summary_df = pd.DataFrame(rows_out)

# ---------- DISPLAY ----------
st.title("📈 Greeks Sentiment Tracker")
st.caption(f"Last updated: {today.strftime('%d-%b-%Y %I:%M:%S %p IST')}")
st.subheader("Sentiment Summary")
st.table(summary_df.style.format({
    'DELTA': '{:.4f}', 'VEGA': '{:.2f}', 'THETA': '{:.2f}',
    **({'OI': '{:.0f}'} if 'OI' in summary_df.columns else {})
}))
st.subheader("Raw Data Log")
st.download_button(label="Download CSV", data=df.to_csv(index=False),
                   file_name="greeks_log.csv", mime="text/csv")
st.caption("🔄 Auto-refresh every minute.")
st_autorefresh(interval=60 * 1000)
