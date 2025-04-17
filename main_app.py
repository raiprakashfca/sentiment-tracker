import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="📈 Market Sentiment Tracker", layout="wide")

st.title("📊 NIFTY Option Greeks Sentiment Dashboard")

# -------------------- Load Files --------------------
if not os.path.exists("greeks_open.csv") or not os.path.exists("greeks_log.csv"):
    st.warning("⚠️ Greek log files not found yet. Please wait until 9:15 AM for open snapshot.")
    st.stop()

open_df = pd.read_csv("greeks_open.csv")
log_df = pd.read_csv("greeks_log.csv")

# -------------------- Show Market Open Snapshot --------------------
st.subheader("📌 Market Open Baseline (9:15 AM)")
st.dataframe(open_df.style.format(precision=2))

# -------------------- Latest Delta Summary --------------------
st.subheader("📈 Latest Greek Change from Market Open")

latest = log_df.iloc[-1]

st.metric("CE Δ Delta", f"{latest['ce_delta_change']:.2f}", delta_color="inverse")
st.metric("PE Δ Delta", f"{latest['pe_delta_change']:.2f}")

col1, col2 = st.columns(2)
with col1:
    st.metric("CE Δ Vega", f"{latest['ce_vega_change']:.2f}")
    st.metric("CE Δ Theta", f"{latest['ce_theta_change']:.2f}")
with col2:
    st.metric("PE Δ Vega", f"{latest['pe_vega_change']:.2f}")
    st.metric("PE Δ Theta", f"{latest['pe_theta_change']:.2f}")

# -------------------- Trendline Charts --------------------
st.subheader("📊 Real-Time Greek Trends")

log_df["timestamp"] = pd.to_datetime(log_df["timestamp"])

tab1, tab2 = st.tabs(["🔵 CE Greeks", "🔴 PE Greeks"])

with tab1:
    st.line_chart(log_df.set_index("timestamp")[["ce_delta_change", "ce_vega_change", "ce_theta_change"]])

with tab2:
    st.line_chart(log_df.set_index("timestamp")[["pe_delta_change", "pe_vega_change", "pe_theta_change"]])

# -------------------- Raw Logs (Optional) --------------------
with st.expander("🧾 View Raw Greek Logs"):
    st.dataframe(log_df.tail(20).style.format(precision=2))
