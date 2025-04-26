import streamlit as st
import pandas as pd
import datetime
import pytz

# ----------------- PAGE SETUP -----------------
st.set_page_config(page_title="📈 Sentiment Tracker", layout="wide")

# ----------------- TIMEZONE SETUP -----------------
ist = pytz.timezone("Asia/Kolkata")

# ----------------- HEADER -----------------
col1, col2 = st.columns([8, 2])
with col1:
    st.title("📈 Option Greeks Sentiment Tracker")
    today = datetime.datetime.now(ist)
    st.markdown(f"**🗓️ {today.strftime('%A, %d %B %Y, %I:%M:%S %p IST')}**")
with col2:
    st.metric(label="🕒 Market Time (IST)", value=datetime.datetime.now(ist).strftime("%H:%M:%S"))

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

# ----------------- LOAD DATA -----------------
try:
    df = pd.read_csv("greeks_log_historical.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_convert("Asia/Kolkata")
except Exception as e:
    st.error(f"❌ Error loading data: {e}")
    st.stop()

# ----------------- COLOR CODING -----------------
def color_positive(val):
    color = 'green' if val > 0 else 'red' if val < 0 else 'black'
    return f'color: {color}'

# ----------------- DISPLAY TABLE -----------------
st.subheader("📊 Live Greek Changes (vs 9:15 AM IST)")
st.dataframe(
    df.style.applymap(color_positive, subset=[
        "ce_delta_change", "pe_delta_change",
        "ce_vega_change", "pe_vega_change",
        "ce_theta_change", "pe_theta_change"
    ])
    .format({
        "ce_delta_change": "{:.2f}",
        "pe_delta_change": "{:.2f}",
        "ce_vega_change": "{:.2f}",
        "pe_vega_change": "{:.2f}",
        "ce_theta_change": "{:.2f}",
        "pe_theta_change": "{:.2f}",
    })
)

# ----------------- LAST REFRESH TIME -----------------
st.caption(f"✅ Last updated at: {datetime.datetime.now(ist).strftime('%d-%b-%Y %I:%M:%S %p IST')}")

# ----------------- AUTO REFRESH -----------------
from streamlit_autorefresh import st_autorefresh

st.caption("🔄 Auto-refreshes every 1 minute")
st_autorefresh(interval=60000)  # 60000 ms = 1 minute

