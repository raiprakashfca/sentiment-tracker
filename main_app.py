import streamlit as st
import pandas as pd
import datetime
import pytz
import gspread
import os
from oauth2client.service_account import ServiceAccountCredentials
from streamlit_autorefresh import st_autorefresh

# ----------------- CONFIGURATION -----------------
REQUIRED_COLUMNS = [
    'timestamp',
    'ce_delta', 'pe_delta',
    'ce_vega',  'pe_vega',
    'ce_theta','pe_theta'
]

# ----------------- PAGE SETUP -----------------
st.set_page_config(page_title="📈 Sentiment Tracker", layout="wide")

# ----------------- TIMEZONE -----------------
ist = pytz.timezone("Asia/Kolkata")
now = datetime.datetime.now(ist)

# ----------------- HEADER -----------------
col1, col2 = st.columns([8, 2])
with col1:
    st.title("📈 Option Greeks Sentiment Tracker")
    st.markdown(f"**🗓️ {now.strftime('%A, %d %B %Y, %I:%M:%S %p IST')}**")
with col2:
    st.metric(label="🕒 Market Time (IST)", value=now.strftime("%H:%M:%S"))

# ----------------- SECRETS -----------------
gcreds = st.secrets.get("gcreds")
if not gcreds:
    st.error("❌ 'gcreds' section missing in secrets.toml.")
    st.stop()
sheet_id = st.secrets.get("GREEKS_SHEET_ID")
if not sheet_id:
    st.error("❌ 'GREEKS_SHEET_ID' missing in secrets.toml.")
    st.stop()

# ----------------- GOOGLE SHEETS AUTH -----------------
scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
gc = gspread.authorize(creds)
wb = gc.open_by_key(sheet_id)

# ----------------- READ GreeksLog ----------------- 
# Use get_all_values to avoid header-uniqueness issues
sheet = wb.worksheet("GreeksLog")
all_values = sheet.get_all_values()
if len(all_values) < 2:
    st.error("❌ Worksheet 'GreeksLog' must have a header row and at least one data row.")
    st.stop()
headers = [h.strip().lower() for h in all_values[0]]
if headers != REQUIRED_COLUMNS:
    st.error(
        f"❌ 'GreeksLog' headers mismatch.\n"
        f"Expected: {REQUIRED_COLUMNS}\n"
        f"Found:    {headers}"
    )
    st.stop()
# Build DataFrame
data = all_values[1:]
df_log = pd.DataFrame(data, columns=headers)
# Parse types
df_log['timestamp'] = pd.to_datetime(df_log['timestamp']).dt.tz_localize('UTC').dt.tz_convert(ist)
for col in REQUIRED_COLUMNS[1:]:
    df_log[col] = pd.to_numeric(df_log[col], errors='coerce')

# ----------------- OPEN SNAPSHOT -----------------
# Read existing GreeksOpen or write baseline if missing
def get_open_snapshot():
    try:
        ws = wb.worksheet("GreeksOpen")
        vals = ws.get_all_values()
        if len(vals) >= 2:
            row = vals[1]
            return pd.Series(row, index=vals[0]).astype(float)
    except Exception:
        pass
    # Fallback: today's first log entry
    today_logs = df_log[df_log['timestamp'].dt.date == now.date()]
    if today_logs.empty:
        st.error("❌ No 'GreeksLog' entry for today to use as baseline.")
        st.stop()
    baseline = today_logs.iloc[0]
    # Overwrite sheet with baseline
    ws = wb.worksheet("GreeksOpen")
    ws.clear()
    ws.append_row([baseline['timestamp'].isoformat()] + [baseline[c] for c in REQUIRED_COLUMNS[1:]])
    return baseline[REQUIRED_COLUMNS].astype(float)

open_vals = get_open_snapshot()

# ----------------- COMPUTE CHANGES -----------------
latest = df_log.iloc[-1]
changes = {}
for col in REQUIRED_COLUMNS[1:]:
    label = col.replace('_', ' ').upper() + ' Δ'
    changes[label] = float(latest[col]) - float(open_vals[col])

# ----------------- DISPLAY -----------------
# Color mapping

def color_positive(v):
    return 'color: green' if v>0 else 'color: red' if v<0 else 'color: white'

st.subheader("📊 Live Greek Changes (vs Open)")
df_disp = pd.DataFrame([changes])
st.dataframe(
    df_disp.style.applymap(color_positive).format("{:.2f}")
)

# ----------------- FOOTER & REFRESH -----------------
st.caption(f"✅ Last updated: {now.strftime('%d-%b-%Y %I:%M:%S %p IST')}")
st.caption("🔄 Auto-refresh every 1 minute")
st_autorefresh(interval=60000)
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:grey;'>"
    "Made with ❤️ by Prakash Rai in partnership with ChatGPT | Powered by Zerodha APIs"
    "</div>", unsafe_allow_html=True
)
