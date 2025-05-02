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

# -------------------- SETUP --------------------
ist = pytz.timezone("Asia/Kolkata")
now = datetime.datetime.now(ist)
log_file = "greeks_log_historical.csv"
open_file = "greeks_open.csv"
HEADERS = ["timestamp","ce_delta","pe_delta","ce_vega","pe_vega","ce_theta","pe_theta"]

# -------------------- HELPERS --------------------
def initialize_log_file():
    zero_row = {h: 0.0 for h in HEADERS}
    zero_row["timestamp"] = now.isoformat()
    pd.DataFrame([zero_row]).to_csv(log_file, index=False)
    print("⚠️ Initialized log file with headers and zero values.")

# Ensure log file exists before anything
if not os.path.exists(log_file):
    initialize_log_file()

# -------------------- MAIN SCRIPT --------------------
def main():
    # Load credentials
    secrets_path = os.path.expanduser("~/.streamlit/secrets.toml")
    if os.path.exists(secrets_path):
        secrets = toml.load(secrets_path)
        gcreds = json.loads(secrets.get("GCREDS", "{}"))
    elif "GCREDS" in os.environ:
        gcreds = json.loads(os.environ["GCREDS"])
    else:
        raise RuntimeError("❌ GCREDS not found.")

    creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ])
    client = gspread.authorize(creds)
    sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")

    api_key = sheet.acell("A1").value.strip()
    access_token = sheet.acell("C1").value.strip()

    # Init Kite
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    # Validate token
    try:
        sp = kite.ltp(["NSE:NIFTY 50"])["NSE:NIFTY 50"]["last_price"]
        print(f"✅ Valid token. Spot price: {sp}")
    except Exception as e:
        print(f"❌ Token invalid: {e}")
        return

    # Fetch instruments
    inst = pd.DataFrame(kite.instruments("NFO"))
    opts = inst[(inst["name"]=="NIFTY") & (inst["segment"]=="NFO-OPT")]

    # Determine expiry
    today = datetime.date.today()
    exp = sorted(opts["expiry"].unique())
    nearest = next(e for e in exp if pd.to_datetime(e).date()>=today)
    ce = opts[(opts["expiry"]==nearest)&(opts["instrument_type"]=="CE")]
    pe = opts[(opts["expiry"]==nearest)&(opts["instrument_type"]=="PE")]

    # Greeks calculation
    T=1/12; r=0.06; iv=0.14
    def bs_delta(t,S,K):
        d1=(np.log(S/K)+(r+0.5*iv**2)*T)/(iv*np.sqrt(T))
        return norm.cdf(d1)
    ce_ltp = kite.ltp(ce["instrument_token"].tolist())
    pe_ltp = kite.ltp(pe["instrument_token"].tolist())
    ce["ltp"] = ce["instrument_token"].apply(lambda x: ce_ltp[str(x)]["last_price"])
    pe["ltp"] = pe["instrument_token"].apply(lambda x: pe_ltp[str(x)]["last_price"])
    ce["delta"] = ce.apply(lambda r: bs_delta(r,sp,r["strike"]), axis=1)
    pe["delta"] = pe.apply(lambda r: -bs_delta(r,sp,r["strike"]), axis=1)
    ce_sum = ce[(ce["delta"]>=0.05)&(ce["delta"]<=0.6)]["delta"].sum()
    pe_sum = pe[(pe["delta"].abs()>=0.05)&(pe["delta"].abs()<=0.6)]["delta"].sum()

    # Build row
    row = pd.DataFrame([{
        "timestamp": now.isoformat(),
        "ce_delta": ce_sum,
        "pe_delta": pe_sum,
        # vega/theta placeholders
        "ce_vega": 0.0, "pe_vega":0.0,
        "ce_theta": 0.0, "pe_theta":0.0
    }])

    # Append to log
    headers_ok = pd.read_csv(log_file, nrows=0).columns.tolist()
    if headers_ok!=HEADERS:
        initialize_log_file()
    row.to_csv(log_file, mode='a', header=False, index=False)
    print("✅ Appended to log.")

    # Save open snapshot if first run
    if now.strftime("%H:%M")=="09:15":
        row.rename(columns={
            "ce_delta":"ce_delta_open","pe_delta":"pe_delta_open",
            "ce_vega":"ce_vega_open","pe_vega":"pe_vega_open",
            "ce_theta":"ce_theta_open","pe_theta":"pe_theta_open"
        }).to_csv(open_file,index=False)
        print("📌 Open snapshot saved.")

# Run
try:
    main()
except Exception as e:
    print(f"🔴 Script error: {e}")
    initialize_log_file()
