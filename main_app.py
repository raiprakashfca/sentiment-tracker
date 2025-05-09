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
Tracks real-time changes in Option Greeks (Delta, Vega, Theta)
for NIFTY options within 0.05–0.60 Delta range.
""")

# ----------------- SECRETS -----------------
gcreds = st.secrets.get("gcreds")
sheet_id = st.secrets.get("GREEKS_SHEET_ID")
if not gcreds or not sheet_id:
    st.error("❌ Missing 'gcreds' or 'GREEKS_SHEET_ID' in Streamlit secrets.")
    st.stop()

# ----------------- GOOGLE SHEETS AUTH -----------------
scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
gc = gspread.authorize(creds)
wb = gc.open_by_key(sheet_id)

# ----------------- LOAD GreeksLog -----------------
all_vals = wb.worksheet("GreeksLog").get_all_values()
if len(all_vals) < 2:
    st.error("❌ 'GreeksLog' must have a header row and at least one data row.")
    st.stop()
# Determine if header present
headers = [h.strip().lower() for h in all_vals[0]]
if headers == REQUIRED_COLUMNS:
    data_rows = all_vals[1:]
else:
    data_rows = all_vals
# Build DataFrame
df_log = pd.DataFrame(data_rows, columns=REQUIRED_COLUMNS)
# Parse timestamps
ts = pd.to_datetime(df_log['timestamp'], utc=True)
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
    # Read existing snapshot
    try:
        vals = wb.worksheet("GreeksOpen").get_all_values()
        if len(vals) >= 2:
            ser = pd.Series(vals[1], index=vals[0])
            return ser.drop('timestamp').astype(float)
    except Exception:
        pass
    # Fallback: first log entry for today
    today_rows = df_log[df_log['timestamp'].dt.date == now.date()]
    if today_rows.empty:
        st.error("❌ No 'GreeksLog' entry for today; ensure fetch script ran at open.")
        st.stop()
    base = today_rows.iloc[0]
    return pd.Series({c: float(base[c]) for c in REQUIRED_COLUMNS[1:]})
open_vals = get_open()

# ----------------- COMPUTE CHANGES -----------------
# Build list of changes across all logged intervals
changes_list = []
for _, row in df_log.iterrows():
    entry = {"timestamp": row["timestamp"]}
    for col in REQUIRED_COLUMNS[1:]:
        # compute delta vs opening baseline
        entry[f"{col}_change"] = float(row[col]) - float(open_vals[col])
    changes_list.append(entry)

# Ensure we have data
if not changes_list:
    st.error("❌ No interval data available to display.")
    st.stop()

# Create DataFrame of changes
df_changes = pd.DataFrame(changes_list)
# Format timestamp into IST string
if pd.api.types.is_datetime64_any_dtype(df_changes['timestamp']):
    df_changes['timestamp'] = df_changes['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S %Z')
else:
    df_changes['timestamp'] = pd.to_datetime(df_changes['timestamp'], utc=True).dt.tz_localize('UTC').dt.tz_convert(ist).dt.strftime('%Y-%m-%d %H:%M:%S %Z')

# ----------------- DISPLAY -----------------
def color_positive(v):
    return 'color: green' if v > 0 else 'color: red' if v < 0 else 'color: white'

st.subheader("📈 Intraday Greek Changes")
st.dataframe(
    df_changes.style.applymap(color_positive, subset=[c for c in df_changes.columns if c.endswith('_change')])
                   .format({c: '{:.2f}' for c in df_changes.columns if c.endswith('_change')})
)

# ----------------- DOWNLOAD BUTTON -----------------
import io
buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
    df_log.to_excel(writer, sheet_name='RawLog', index=False)
    df_changes.to_excel(writer, sheet_name='Changes', index=False)
reader_excel = buffer.getvalue()
st.download_button(
    label="Download intraday data as Excel",
    data=reader_excel,
    file_name=f"greeks_intraday_{now.strftime('%Y%m%d')}.xlsx",
    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
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
