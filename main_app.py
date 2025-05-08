import streamlit as st
import pandas as pd
import datetime
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from streamlit_autorefresh import st_autorefresh

# ----------------- CONFIG -----------------
REQUIRED_COLUMNS = ['timestamp','ce_delta','pe_delta','ce_vega','pe_vega','ce_theta','pe_theta']

# ----------------- PAGE SETUP -----------------
st.set_page_config(page_title="📈 Sentiment Tracker", layout="wide")
ist = pytz.timezone("Asia/Kolkata")
now = datetime.datetime.now(ist)

# ----------------- HEADER -----------------
col1, col2 = st.columns([8,2])
with col1:
    st.title("📈 Option Greeks Sentiment Tracker")
    st.markdown(f"**🗓️ {now.strftime('%A, %d %B %Y, %I:%M:%S %p IST')}**")
with col2:
    st.metric("🕒 Market Time (IST)", now.strftime("%H:%M:%S"))

# ----------------- EXPLANATION -----------------
st.markdown("""
Tracks real‑time changes in Option Greeks (Delta, Vega, Theta)
for NIFTY options within 0.05–0.60 Delta range.
""")

# ----------------- SECRETS -----------------
gcreds = st.secrets.get("gcreds")
sheet_id = st.secrets.get("GREEKS_SHEET_ID")
if not gcreds or not sheet_id:
    st.error("❌ Missing 'gcreds' or 'GREEKS_SHEET_ID' in secrets.toml.")
    st.stop()

# ----------------- GOOGLE SHEETS AUTH -----------------
scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
gc = gspread.authorize(creds)
wb = gc.open_by_key(sheet_id)

# ----------------- LOAD GreeksLog -----------------
all_vals = wb.worksheet("GreeksLog").get_all_values()
if len(all_vals) < 2:
    st.error("❌ 'GreeksLog' must have headers + data rows.")
    st.stop()
# Identify data rows
headers = [h.strip().lower() for h in all_vals[0]]
if headers == REQUIRED_COLUMNS:
    rows = all_vals[1:]
else:
    rows = all_vals
# Build DataFrame
df_log = pd.DataFrame(rows, columns=REQUIRED_COLUMNS)
# Parse timestamps robustly
ts = pd.to_datetime(df_log['timestamp'], utc=True)
# If already tz-aware, skip localize
try:
    ts = ts.dt.tz_localize('UTC')
except Exception:
    pass
df_log['timestamp'] = ts.dt.tz_convert(ist)
# Convert numeric columns
for col in REQUIRED_COLUMNS[1:]:
    df_log[col] = pd.to_numeric(df_log[col], errors='coerce')

# ----------------- OPEN SNAPSHOT -----------------
def get_open():
    try:
        vals = wb.worksheet("GreeksOpen").get_all_values()
        if len(vals) >= 2:
            return pd.Series(vals[1], index=vals[0]).astype(float)
    except Exception:
        pass
    # Fallback: first log entry of today
    today_rows = df_log[df_log['timestamp'].dt.date == now.date()]
    if today_rows.empty:
        st.error("❌ No today's entry in 'GreeksLog'; run fetch at open.")
        st.stop()
    base = today_rows.iloc[0]
    ws = wb.worksheet("GreeksOpen")
    try:
        ws.clear()
    except Exception as e:
        st.warning(f"⚠️ Could not clear 'GreeksOpen' sheet: {e}")
    try:
        ws.append_row([base['timestamp'].isoformat()] + [base[c] for c in REQUIRED_COLUMNS[1:]])
    except Exception as e:
        st.warning(f"⚠️ Could not write to 'GreeksOpen' sheet: {e}")['timestamp'].isoformat()] + [base[c] for c in REQUIRED_COLUMNS[1:]])
    return base[REQUIRED_COLUMNS].astype(float)

open_vals = get_open()

# ----------------- COMPUTE CHANGES -----------------
latest = df_log.iloc[-1]
changes = {col.replace('_',' ').upper() + ' Δ': float(latest[col]) - float(open_vals[col]) for col in REQUIRED_COLUMNS[1:]}

# ----------------- DISPLAY -----------------
def color_positive(v): return 'color: green' if v>0 else 'color: red' if v<0 else 'color: white'

st.subheader("📊 Live Greek Changes (vs Open)")
\
st.dataframe(
    pd.DataFrame([changes]).style.applymap(color_positive).format("{:.2f}")
)

# ----------------- FOOTER -----------------
st.caption(f"✅ Last updated: {now.strftime('%d-%b-%Y %I:%M:%S %p IST')}")
st.caption("🔄 Auto-refresh every 1 minute")
st_autorefresh(interval=60000)
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:grey;'>"
    "Made with ❤️ by Prakash Rai in partnership with ChatGPT | Powered by Zerodha APIs"
    "</div>", unsafe_allow_html=True
)
