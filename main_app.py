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

# ----------------- LOAD DATA -----------------
try:
    df = pd.read_csv("greeks_log_historical.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize("UTC").dt.tz_convert(ist)
except Exception as e:
    st.error(f"❌ Error loading data: {e}")
    st.stop()

# ----------------- CHECK MARKET STATUS -----------------
market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

if not (market_open <= now <= market_close):
    st.warning("🏁 **Market Closed** — Updates will resume on next trading session.")
    st.stop()

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
