import streamlit as st
import pandas as pd
import datetime
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from streamlit_autorefresh import st_autorefresh

# ----------------- CONFIG -----------------
REQUIRED_COLUMNS = [
    'timestamp',
    'nifty_ce_delta', 'nifty_pe_delta', 'nifty_ce_vega', 'nifty_pe_vega', 'nifty_ce_theta', 'nifty_pe_theta',
    'bn_ce_delta',    'bn_pe_delta',    'bn_ce_vega',    'bn_pe_vega',    'bn_ce_theta',    'bn_pe_theta'
]

# ----------------- PAGE SETUP -----------------
st.set_page_config(page_title="📈 Sentiment Tracker", layout="wide")
ist = pytz.timezone("Asia/Kolkata")
now = datetime.datetime.now(ist)

# ----------------- AUTHENTICATION -----------------
scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
raw = st.secrets.get("GCREDS") or st.secrets.get("gcreds")
creds = ServiceAccountCredentials.from_json_keyfile_dict(raw, scope)
gc = gspread.authorize(creds)
sheet_id = st.secrets.get("GREEKS_SHEET_ID")
wb = gc.open_by_key(sheet_id)

# ----------------- LOAD LOGGED GREEKS -----------------
all_vals = wb.worksheet("GreeksLog").get_all_values()
if len(all_vals) < 2:
    st.error("❌ 'GreeksLog' must have header + data. Please check your fetch script.")
    st.stop()
headers = [h.strip().lower() for h in all_vals[0]]
if headers == REQUIRED_COLUMNS:
    data_rows = all_vals[1:]
else:
    data_rows = all_vals
# Build DataFrame
_df = pd.DataFrame(data_rows, columns=headers)
# Parse timestamp
_df['timestamp'] = pd.to_datetime(_df['timestamp'], utc=True).dt.tz_convert(ist)
# Convert numeric cols
type_cols = [c for c in headers if c != 'timestamp']
for col in type_cols:
    _df[col] = pd.to_numeric(_df[col], errors='coerce')
# Raw log DF
_df_log = _df.copy()

# ----------------- OPEN SNAPSHOT -----------------
def get_open_snapshot():
    try:
        vals = wb.worksheet("GreeksOpen").get_all_values()
        if len(vals) >= 2:
            ser = pd.Series(vals[1], index=vals[0])
            return ser.drop('timestamp').astype(float)
    except Exception:
        pass
    # fallback to first entry today
    today_rows = _df_log[_df_log['timestamp'].dt.date == now.date()]
    if today_rows.empty:
        st.error("❌ No 'GreeksLog' entry for today; ensure fetch script ran at open.")
        st.stop()
    base = today_rows.iloc[0]
    return base.drop('timestamp')

open_snapshot = get_open_snapshot()

# ----------------- CALCULATE CHANGES -----------------
latest = _df_log.iloc[-1]
changes = {}
for col in open_snapshot.index:
    changes[col] = latest[col] - open_snapshot[col]

# ----------------- SENTIMENT CLASSIFICATION -----------------
def classify_sentiment(ce_vega, pe_vega, ce_theta, pe_theta):
    # Vega-based
    if pe_vega > 0 and ce_vega < 0:
        sentiment = 'BEARISH'
    elif ce_vega > 0 and pe_vega < 0:
        sentiment = 'BULLISH'
    elif ce_vega > 0 and pe_vega > 0:
        sentiment = 'RANGE BOUND'
    else:
        sentiment = 'VOLATILE'
    # Theta override
    if ce_theta < 0 or pe_theta < 0:
        sentiment = 'VOLATILE'
    return sentiment

# ----------------- BUILD SUMMARY -----------------
rows = []
for prefix, label in [('nifty', 'NIFTY'), ('bn', 'BANKNIFTY')]:
    ce_d = changes[f'{prefix}_ce_delta']
    pe_d = changes[f'{prefix}_pe_delta']
    ce_v = changes[f'{prefix}_ce_vega']
    pe_v = changes[f'{prefix}_pe_vega']
    ce_t = changes[f'{prefix}_ce_theta']
    pe_t = changes[f'{prefix}_pe_theta']
    sent = classify_sentiment(ce_v, pe_v, ce_t, pe_t)
    # CE row
    row_ce = {
        'Instrument': f"{label} CE",
        'SENTIMENT': sent,
        'VEGA': ce_v,
        'THETA': ce_t,
        'DELTA': ce_d
    }
    # PE row
    row_pe = {
        'Instrument': f"{label} PE",
        'SENTIMENT': sent,
        'VEGA': pe_v,
        'THETA': pe_t,
        'DELTA': pe_d
    }
    rows.extend([row_ce, row_pe])
# Include OI if available
if any(col.endswith('_oi') for col in headers):
    for r in rows:
        pref = 'nifty' if 'NIFTY' in r['Instrument'] and 'BANK' not in r['Instrument'] else 'bn'
        typ = 'ce' if r['Instrument'].endswith('CE') else 'pe'
        oi_col = f"{pref}_{typ}_oi"
        r['OI'] = changes.get(oi_col, None)

summary_df = pd.DataFrame(rows)

# ----------------- DISPLAY -----------------
st.title("📈 Greeks Sentiment Tracker")
st.caption(f"✅ Last updated: {now.strftime('%d-%b-%Y %I:%M:%S %p IST')}")
st.subheader("Sentiment Summary")
st.table(summary_df.style.format({c: '{:.2f}' for c in ['VEGA','THETA','DELTA'] if c in summary_df.columns}))

# ----------------- RAW DATA DOWNLOAD -----------------
st.subheader("Raw Log Data")
st.download_button(
    label="Download Full Greeks Log CSV",
    data=pd.DataFrame._df_log.to_csv(index=False),
    file_name=f"greeks_log_{now.strftime('%Y%m%d_%H%M%S')}.csv",
    mime='text/csv'
)

# ----------------- FOOTER & REFRESH -----------------
st.markdown("---")
st.caption("🔄 Auto-refresh every 1 minute (set to 5 minutes if instability arises)")
st_autorefresh = st_autorefresh(interval=60000)
st.markdown(
    "<div style='text-align:center;color:grey;'>"
    "Made with ❤️ by Prakash Rai | Powered by Zerodha APIs"
    "</div>", unsafe_allow_html=True
)
