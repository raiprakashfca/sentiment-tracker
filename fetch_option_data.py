import os
import json
import pandas as pd
import datetime
import pytz
import toml
import numpy as np
from kiteconnect import KiteConnect
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from scipy.stats import norm

# -------------------- TIME --------------------
ist = pytz.timezone("Asia/Kolkata")
now = datetime.datetime.now(ist)

# -------------------- CREDENTIALS --------------------
secrets_path = os.path.expanduser("~/.streamlit/secrets.toml")
if os.path.exists(secrets_path):
    secrets = toml.load(secrets_path)
    gcreds = json.loads(secrets.get("GCREDS", "{}"))
elif "GCREDS" in os.environ:
    gcreds = json.loads(os.environ["GCREDS"])
else:
    raise RuntimeError("❌ GCREDS not found in secrets.toml or environment.")

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
client = gspread.authorize(creds)
sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")

api_key = sheet.acell("A1").value.strip()
access_token = sheet.acell("C1").value.strip()

# -------------------- INITIALIZE KITE --------------------
kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# -------------------- TOKEN VALIDATION --------------------
try:
    spot_data = kite.ltp(["NSE:NIFTY 50"])["NSE:NIFTY 50"]
    spot_price = spot_data["last_price"]
    print(f"✅ Valid token. Spot price: {spot_price}")
except Exception as e:
    print(f"❌ Invalid API Key or Access Token: {e}")
    exit(1)

# -------------------- FETCH INSTRUMENTS --------------------
instruments = pd.DataFrame(kite.instruments("NFO"))
nifty_opts = instruments[(instruments["name"] == "NIFTY") & (instruments["segment"] == "NFO-OPT")]

# -------------------- DETERMINE EXPIRY --------------------
today = datetime.date.today()
expiries = sorted(nifty_opts["expiry"].unique())
nearest_expiry = next(e for e in expiries if pd.to_datetime(e).date() >= today)
print(f"🎯 Nearest expiry: {nearest_expiry}")

# -------------------- SEPARATE CE & PE --------------------
ce_opts = nifty_opts[(nifty_opts["expiry"] == nearest_expiry) & (nifty_opts["instrument_type"] == "CE")]
pe_opts = nifty_opts[(nifty_opts["expiry"] == nearest_expiry) & (nifty_opts["instrument_type"] == "PE")]

# -------------------- BLACK-SCHOLES GREEKS --------------------
def black_scholes_delta(opt_type, S, K, T, r, sigma):
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma * np.sqrt(T))
    return norm.cdf(d1) if opt_type == "CE" else -norm.cdf(-d1)

def get_greeks(row, S, T, r, sigma):
    K = row["strike"]
    opt_type = row["instrument_type"]
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma * np.sqrt(T))
    delta = black_scholes_delta(opt_type, S, K, T, r, sigma)
    vega = S * norm.pdf(d1) * np.sqrt(T) / 100
    theta = (-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))) / 365
    return pd.Series([delta, vega, theta])

# -------------------- CALCULATE GREEKS --------------------
T = 1/12  # ~22 trading days
r = 0.06
iv = 0.14  # user-set

# Fetch LTP for each
ce_ltp = kite.ltp(ce_opts["instrument_token"].tolist())
pe_ltp = kite.ltp(pe_opts["instrument_token"].tolist())
ce_opts["ltp"] = ce_opts["instrument_token"].apply(lambda x: ce_ltp[str(x)]["last_price"])
pe_opts["ltp"] = pe_opts["instrument_token"].apply(lambda x: pe_ltp[str(x)]["last_price"])

# Compute Greeks
ce_opts[["delta","vega","theta"]] = ce_opts.apply(get_greeks, axis=1, args=(spot_price, T, r, iv))
pe_opts[["delta","vega","theta"]] = pe_opts.apply(get_greeks, axis=1, args=(spot_price, T, r, iv))

# Filter by delta range
ce_filtered = ce_opts[(ce_opts["delta"] >= 0.05) & (ce_opts["delta"] <= 0.6)]
pe_filtered = pe_opts[(pe_opts["delta"].abs() >= 0.05) & (pe_opts["delta"].abs() <= 0.6)]

# -------------------- PREPARE ROW --------------------
data = {
    "timestamp": now.isoformat(),
    "ce_delta": ce_filtered["delta"].sum(),
    "pe_delta": pe_filtered["delta"].sum(),
    "ce_vega": ce_filtered["vega"].sum(),
    "pe_vega": pe_filtered["vega"].sum(),
    "ce_theta": ce_filtered["theta"].sum(),
    "pe_theta": pe_filtered["theta"].sum()
}
row = pd.DataFrame([data])

# -------------------- SAVE TO CSV WITH VALIDATION --------------------
log_file = "greeks_log_historical.csv"
headers = ["timestamp","ce_delta","pe_delta","ce_vega","pe_vega","ce_theta","pe_theta"]

# Write or append
if not os.path.exists(log_file):
    row.to_csv(log_file, index=False)
    print("🆕 Created new greeks_log_historical.csv with headers.")
else:
    with open(log_file, 'r') as f:
        existing = f.readline().strip().split(',')
    if not all(col in existing for col in headers):
        row.to_csv(log_file, index=False)
        print("⚠️ Header mismatch. Reinitialized greeks_log_historical.csv.")
    else:
        row.to_csv(log_file, mode='a', header=False, index=False)
        print("✅ Appended row to greeks_log_historical.csv.")

# Post-save validation
temp = pd.read_csv(log_file)
missing = set(headers) - set(temp.columns)
if missing:
    print(f"⚠️ Missing columns after write: {missing}. Reinitializing file.")
    temp.to_csv(log_file, columns=headers, index=False)
    print("🔄 File headers corrected.")

# -------------------- SAVE OPEN SNAPSHOT --------------------
open_file = "greeks_open.csv"
if now.strftime("%H:%M") == "09:15":
    open_row = row.rename(columns={
        "ce_delta": "ce_delta_open","pe_delta": "pe_delta_open",
        "ce_vega": "ce_vega_open","pe_vega": "pe_vega_open",
        "ce_theta": "ce_theta_open","pe_theta": "pe_theta_open"
    })
    open_row.to_csv(open_file, index=False)
    print("📌 Market open snapshot saved.")
