import streamlit as st
import pandas as pd
import datetime
import pytz

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

# ----------------- LOAD DATA -----------------
try:
    df = pd.read_csv("greeks_log_historical.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
except Exception as e:
    st.error(f"❌ Error loading greeks_log_historical.csv: {e}")
    st.stop()

try:
    open_vals = pd.read_csv("greeks_open.csv").iloc[0]
except Exception as e:
    st.error(f"❌ Error loading greeks_open.csv: {e}")
    st.stop()

required_cols = ["ce_delta", "pe_delta", "ce_vega", "pe_vega", "ce_theta", "pe_theta"]
if not all(col in df.columns for col in required_cols):
    st.error("❌ Required columns not found in data. Please check if fetch_option_data.py has populated data correctly.")
    st.stop()

# ----------------- MARKET STATUS -----------------
market_open_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
market_close_time = now.replace(hour=15, minute=30, second=0, microsecond=0)

if not (market_open_time <= now <= market_close_time):
    st.warning("🏁 **Market Closed for the Day**\n\n✅ Showing last trading snapshot.")

# ----------------- COLOR CODING -----------------
def color_positive(val):
    color = 'green' if val > 0 else 'red' if val < 0 else 'black'
    return f'color: {color}'

# ----------------- COMPUTE CHANGES -----------------
try:
    df["ce_delta_change"] = df["ce_delta"] - open_vals["ce_delta_open"]
    df["pe_delta_change"] = df["pe_delta"] - open_vals["pe_delta_open"]
    df["ce_vega_change"] = df["ce_vega"] - open_vals["ce_vega_open"]
    df["pe_vega_change"] = df["pe_vega"] - open_vals["pe_vega_open"]
    df["ce_theta_change"] = df["ce_theta"] - open_vals["ce_theta_open"]
    df["pe_theta_change"] = df["pe_theta"] - open_vals["pe_theta_open"]
except KeyError as e:
    st.error("❌ Required columns not found in open snapshot. Please verify greeks_open.csv format.")
    st.stop()

# ----------------- DISPLAY TABLE -----------------
st.subheader("📊 Live Greek Changes (vs 9:15 AM IST)")
st.dataframe(
    df.style.applymap(color_positive, subset=[
        "ce_delta_change", "pe_delta_change",
        "ce_vega_change", "pe_vega_change",
        "ce_theta_change", "pe_theta_change"
    ]).format({
        "ce_delta_change": "{:.2f}",
        "pe_delta_change": "{:.2f}",
        "ce_vega_change": "{:.2f}",
        "pe_vega_change": "{:.2f}",
        "ce_theta_change": "{:.2f}",
        "pe_theta_change": "{:.2f}"
    })
)

# ----------------- LAST REFRESH TIME -----------------
st.caption(f"✅ Last updated at: {now.strftime('%d-%b-%Y %I:%M:%S %p IST')}")

# ----------------- AUTO REFRESH -----------------
from streamlit_autorefresh import st_autorefresh
st.caption("🔄 Auto-refreshes every 1 minute")
st_autorefresh(interval=60000)

# ----------------- FOOTER -----------------
st.markdown("""---""")
st.markdown(
    "<div style='text-align: center; color: grey;'>"
    "Made with ❤️ by Prakash Rai in partnership with ChatGPT | Powered by Zerodha APIs"
    "</div>",
    unsafe_allow_html=True
)
