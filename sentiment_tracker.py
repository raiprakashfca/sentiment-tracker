import pandas as pd
import os
from datetime import datetime

# ----------------- File Paths -----------------
LIVE_LOG_PATH = "greeks_log.csv"
HISTORICAL_LOG_PATH = "greeks_log_historical.csv"
OPEN_PATH = "greeks_open.csv"

# ----------------- Check File Availability -----------------
use_historical = False
if not os.path.exists(LIVE_LOG_PATH):
    if os.path.exists(HISTORICAL_LOG_PATH):
        use_historical = True
        log_path = HISTORICAL_LOG_PATH
    else:
        raise FileNotFoundError("❌ No Greek log file (live or historical) found.")
else:
    log_path = LIVE_LOG_PATH

# ----------------- Load Baseline -----------------
if not os.path.exists(OPEN_PATH):
    raise FileNotFoundError("❌ Market open baseline file not found.")

open_df = pd.read_csv(OPEN_PATH)
log_df = pd.read_csv(log_path)

# ----------------- Compute Changes -----------------
log_df["timestamp"] = pd.to_datetime(log_df["timestamp"])

latest = log_df.iloc[-1]

metrics = {
    "ce_delta_change": latest["ce_delta_change"],
    "pe_delta_change": latest["pe_delta_change"],
    "ce_vega_change": latest["ce_vega_change"],
    "pe_vega_change": latest["pe_vega_change"],
    "ce_theta_change": latest["ce_theta_change"],
    "pe_theta_change": latest["pe_theta_change"],
}

# ----------------- Output Data for Use in app -----------------
summary = {
    "source": "Historical" if use_historical else "Live",
    "timestamp": latest["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
    "metrics": metrics,
    "open_df": open_df,
    "log_df": log_df,
}
