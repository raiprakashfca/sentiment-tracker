import pandas as pd
import os
from datetime import datetime
import pytz

# ----------- TIMEZONE SETUP -----------
ist = pytz.timezone("Asia/Kolkata")

# ----------- FILE PATHS -----------
open_file = "greeks_open.csv"
log_file = "greeks_log_historical.csv"

# ----------- LOAD BASELINE (MARKET OPEN GREEKS) -----------
if not os.path.exists(open_file):
    raise FileNotFoundError("❌ Market open baseline file not found.")

open_df = pd.read_csv(open_file)
open_df["timestamp"] = pd.to_datetime(open_df["timestamp"])

baseline = open_df.iloc[0]  # 9:15 AM snapshot

# ----------- LOAD HISTORICAL LOG -----------
log_df = pd.read_csv(log_file)
log_df["timestamp"] = pd.to_datetime(log_df["timestamp"])

# ----------- COMPARE LIVE TO BASELINE -----------
summary = []

for _, row in log_df.iterrows():
    summary.append({
        "timestamp": row["timestamp"],
        "ce_delta_change": row["ce_delta"] - baseline["ce_delta"],
        "pe_delta_change": row["pe_delta"] - baseline["pe_delta"],
        "ce_vega_change": row["ce_vega"] - baseline["ce_vega"],
        "pe_vega_change": row["pe_vega"] - baseline["pe_vega"],
        "ce_theta_change": row["ce_theta"] - baseline["ce_theta"],
        "pe_theta_change": row["pe_theta"] - baseline["pe_theta"],
    })

summary_df = pd.DataFrame(summary)
summary_df["timestamp"] = summary_df["timestamp"].dt.tz_localize("Asia/Kolkata")
