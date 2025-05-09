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
headers = [h.strip().lower() for h in all_vals[0]]
if headers == REQUIRED_COLUMNS:
    rows = all_vals[1:]
else:
    rows = all_vals

# Build DataFrame
df_log = pd.DataFrame(rows, columns=REQUIRED_COLUMNS)

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
    # Attempt to read existing open snapshot
    try:
        vals = wb.worksheet("GreeksOpen").get_all_values()
        if len(vals) >= 2:
            ser = pd.Series(vals[1], index=vals[0])
            return ser.drop('timestamp').astype(float)
    except Exception:
        pass
    # Fallback: first record of today from df_log
    today_rows = df_log[df_log['timestamp'].dt.date == now.date()]
    if today_rows.empty:
        st.error("❌ No 'GreeksLog' entry for today; ensure fetch script ran at market open.")
        st.stop()
    base = today_rows.iloc[0]
    # Return numeric columns only
    return pd.Series({c: float(base[c]) for c in REQUIRED_COLUMNS[1:]})

open_vals = get_open()

# ----------------- COMPUTE CHANGES -----------------
latest = df_log.iloc[-1]
changes = {col.replace('_',' ').upper() + ' Δ': float(latest[col]) - float(open_vals[col]) for col in REQUIRED_COLUMNS[1:]}

# ----------------- DISPLAY ALL INTERVAL CHANGES -----------------
# Build a table of changes at each timestamp vs opening baseline
# Ensure timestamps are in IST
for i, entry in enumerate(changes_list):
    ts = entry['timestamp']
    # localize/convert to IST if needed
    if hasattr(ts, 'tz_convert'):
        entry['timestamp'] = ts.tz_convert(ist)
    else:
        entry['timestamp'] = pd.to_datetime(ts).tz_localize('UTC').tz_convert(ist)

# Now build the DataFrame
# Format timestamp column as string in IST
df_changes = pd.DataFrame(changes_list)
df_changes['timestamp'] = df_changes['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S %Z')
# Color coding function
styled = df_changes.style.format({'timestamp': lambda t: t.strftime('%Y-%m-%d %H:%M:%S')} )
for change_col in [c for c in df_changes.columns if c.endswith('_change')]:
    styled = styled.applymap(lambda v: 'color: green' if v>0 else 'color: red' if v<0 else 'color: white', subset=[change_col])
    styled = styled.format({change_col: '{:.2f}'})

st.subheader("📈 Intraday Greek Changes")
st.dataframe(styled)

# ----------------- DOWNLOAD BUTTON -----------------
# Export to Excel
import io
buffer = io.BytesIO()
# Use openpyxl (built-in) to avoid requiring xlsxwriter
with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
    # save raw log and changes
    df_log.to_excel(writer, sheet_name='RawLog', index=False)
    df_changes.to_excel(writer, sheet_name='Changes', index=False)
    writer.save()
buffer.seek(0)

st.download_button(
    label="Download intraday data as Excel",
    data=buffer,
    file_name=f"greeks_intraday_{now.strftime('%Y%m%d')}.xlsx",
    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
)

# ----------------- FOOTER & REFRESH ----------------- & REFRESH -----------------
st.caption(f"✅ Last updated: {now.strftime('%d-%b-%Y %I:%M:%S %p IST')}")
st.caption("🔄 Auto-refresh every 1 minute")
st_autorefresh(interval=60000)
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:grey;'>"
    "Made with ❤️ by Prakash Rai in partnership with ChatGPT | Powered by Zerodha APIs"
    "</div>", unsafe_allow_html=True
)
