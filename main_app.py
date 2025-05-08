import streamlit as st
import pandas as pd
import datetime
import pytz
import json
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from streamlit_autorefresh import st_autorefresh

# ----------------- PAGE SETUP -----------------
st.set_page_config(page_title="📈 Sentiment Tracker", layout="wide")

# ----------------- TIMEZONE SETUP -----------------
ist = pytz.timezone("Asia/Kolkata")
now = datetime.datetime.now(ist)

# ----------------- HEADER -----------------
col1, col2 = st.columns([8, 2])
with col1:
    st.title("📈 Option Greeks Sentiment Tracker")
    st.markdown(f"**🗓️ {now.strftime('%A, %d %B %Y, %I:%M:%S %p IST')}**")
with col2:
    st.metric(label="🕒 Market Time (IST)", value=now.strftime("%H:%M:%S"))

# ----------------- EXPLANATION -----------------
st.markdown("""
This dashboard tracks the *real-time change* in:
- Delta
- Vega
- Theta
for NIFTY Options (0.05 to 0.60 Delta Range).

**Interpretation:**
- Positive Delta Change → Bullish Bias
- Negative Delta Change → Bearish Bias
- Rising Vega → Volatility Expansion
- Rising Theta → Faster Premium Decay

Tracking both **CE** and **PE** separately.
""")

# ----------------- LOAD SECRETS -----------------
gcreds = st.secrets.get("gcreds")
if not gcreds:
    st.error("❌ 'gcreds' section not found in secrets.toml. Paste your service-account JSON under [gcreds].")
    st.stop()
sheet_id = st.secrets.get("GREEKS_SHEET_ID")
if not sheet_id:
    st.error("❌ 'GREEKS_SHEET_ID' not found in secrets.toml. Add it as GREEKS_SHEET_ID.")
    st.stop()

# ----------------- GOOGLE SHEETS AUTH -----------------
scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
gc = gspread.authorize(creds)
wb = gc.open_by_key(sheet_id)

# ----------------- LOAD LOG WORKSHEET -----------------
# Read all values for GreeksLog
entries = wb.worksheet("GreeksLog").get_all_values()
if not entries or len(entries) < 2:
    st.error("❌ No data in 'GreeksLog'. Run the fetch script to populate baseline and logs.")
    st.stop()
headers = entries[0]
data_rows = entries[1:]
# Build df_log
df_log = pd.DataFrame(data_rows, columns=headers)
# Parse timestamp and localize
df_log['timestamp'] = pd.to_datetime(df_log['timestamp']).dt.tz_localize('UTC').dt.tz_convert(ist)

# ----------------- BASELINE SNAPSHOT ----------------- and localize
df_log['timestamp'] = pd.to_datetime(df_log['timestamp']).dt.tz_localize('UTC').dt.tz_convert(ist)

# ----------------- BASELINE SNAPSHOT -----------------
# Attempt to load existing open snapshot
open_rows = wb.worksheet("GreeksOpen").get_all_values()
if len(open_rows) >= 2:
    open_vals = pd.Series(open_rows[1], index=open_rows[0]).astype({col: float for col in headers[1:]})
else:
    # No open snapshot yet: record baseline at first log entry of today's session
    baseline = df_log[df_log['timestamp'].dt.date == now.date()]
    if baseline.empty:
        st.error("❌ No log entry found for today's date. Ensure the fetch script ran at market open.")
        st.stop()
    open_entry = baseline.iloc[0]
    # clear and write open snapshot
iw = wb.worksheet("GreeksOpen")
iw.clear()
iw.append_row([open_entry['timestamp'].isoformat()] + [open_entry[c] for c in headers[1:]])
open_vals = pd.Series([open_entry[c] for c in headers], index=headers).astype({col: float for col in headers[1:]})

# ----------------- LATEST RECORD -----------------
latest = df_log.iloc[-1]

# ----------------- COMPUTE CHANGES -----------------
changes = {}
for greek in ['delta','vega','theta']:
    for side in ['ce','pe']:
        key = f"{side}_{greek}"
        changes_key = f"{side.upper()} {greek.capitalize()} Δ"
        changes[changes_key] = float(latest[key]) - float(open_vals[key])
# Build display DataFrame
df_disp = pd.DataFrame([changes])

# ----------------- DISPLAY -----------------
def color_positive(val):
    if val > 0: return 'color: green'
    if val < 0: return 'color: red'
    return 'color: white'
st.subheader("📊 Live Greek Changes (vs Open)")
st.dataframe(
    df_disp.style
           .applymap(color_positive)
           .format("{:.2f}")
)

# ----------------- FOOTER & AUTO-REFRESH -----------------
st.caption(f"✅ Last updated: {now.strftime('%d-%b-%Y %I:%M:%S %p IST')}")
st.caption("🔄 Auto-refresh every 1 minute")
st_autorefresh(interval=60000)
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:grey;'>"
    "Made with ❤️ by Prakash Rai in partnership with ChatGPT | Powered by Zerodha APIs"
    "</div>", unsafe_allow_html=True
)
