import streamlit as st
import pandas as pd
import datetime
import pytz
from streamlit_autorefresh import st_autorefresh

# ----------------- PAGE CONFIG -----------------
st.set_page_config(page_title="📈 Sentiment Tracker", layout="wide")
ist = pytz.timezone("Asia/Kolkata")
now = datetime.datetime.now(ist)

# ----------------- HEADER -----------------
col1, col2 = st.columns([8, 2])
with col1:
    st.title("📈 Option Greeks Sentiment Tracker")
    st.markdown(f"**🗓️ {now.strftime('%A, %d %B %Y, %I:%M:%S %p IST')}**")
with col2:
    st.metric("🕒 Market Time (IST)", value=now.strftime("%H:%M:%S"))

# ----------------- DESCRIPTION -----------------
st.markdown("""
Tracks the *real-time change* in Delta, Vega, Theta for NIFTY Options (Delta 0.05 to 0.60).

**Interpretation:**
- Positive Delta Change → Bullish Bias
- Negative Delta Change → Bearish Bias
- Rising Vega → Volatility Expansion
- Rising Theta → Faster Premium Decay

**Both CE and PE tracked separately**.
""")

# ----------------- LOAD OPEN BASELINE -----------------
try:
    open_df = pd.read_csv("greeks_open.csv")
    open_vals = open_df.iloc[0].to_dict()
except Exception as e:
    st.error(f"❌ Missing or corrupted greeks_open.csv: {e}")
    st.stop()

# ----------------- LOAD HISTORICAL LOG -----------------
try:
    df = pd.read_csv("greeks_log_historical.csv")
    if df["timestamp"].dtype == 'O':
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["timestamp"] = df["timestamp"].dt.tz_convert(ist)
except Exception as e:
    st.error(f"❌ Error loading greeks_log_historical.csv: {e}")
    st.stop()

# ----------------- CHECK MARKET STATUS -----------------
market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

if not (market_open <= now <= market_close):
    st.warning("🏁 **Market Closed** — Updates will resume on next trading session.")
    st.stop()

# ----------------- CALCULATE GREEK CHANGES -----------------
df["ce_delta_change"] = df["ce_delta"] - open_vals["ce_delta_open"]
df["pe_delta_change"] = df["pe_delta"] - open_vals["pe_delta_open"]
df["ce_vega_change"] = df["ce_vega"] - open_vals["ce_vega_open"]
df["pe_vega_change"] = df["pe_vega"] - open_vals["pe_vega_open"]
df["ce_theta_change"] = df["ce_theta"] - open_vals["ce_theta_open"]
df["pe_theta_change"] = df["pe_theta"] - open_vals["pe_theta_open"]

# ----------------- COLOR FORMAT -----------------
def colorize(val):
    if val > 0:
        return 'color: green'
    elif val < 0:
        return 'color: red'
    else:
        return 'color: black'

# ----------------- DISPLAY TABLE -----------------
st.subheader("📊 Live Greek Changes (vs 9:15 AM IST)")
st.dataframe(
    df.style
    .applymap(colorize, subset=[
        "ce_delta_change", "pe_delta_change",
        "ce_vega_change", "pe_vega_change",
        "ce_theta_change", "pe_theta_change"
    ])
    .format("{:.2f}", subset=df.columns[1:])
)

# ----------------- REFRESH TIMESTAMP -----------------
st.caption(f"✅ Last updated at: {now.strftime('%d-%b-%Y %I:%M:%S %p IST')}")

# ----------------- AUTO REFRESH -----------------
st.caption("🔄 Auto-refreshes every 1 minute")
st_autorefresh(interval=60000, key="refresh")

# ----------------- FOOTER -----------------
st.markdown("""
---
<div style='text-align: center; color: grey;'>
Made with ❤️ by Prakash Rai in partnership with ChatGPT | Powered by Zerodha APIs
</div>
""", unsafe_allow_html=True)
