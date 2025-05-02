import os
import json
import pandas as pd
import datetime
iimport pytz
import toml
import numpy as np
from kiteconnect import KiteConnect
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from scipy.stats import norm

# -------------------- CONFIG --------------------
ist = pytz.timezone("Asia/Kolkata")
now = datetime.datetime.now(ist)
log_file = "greeks_log_historical.csv"
open_file = "greeks_open.csv"

# Raw Greek headers
RAW_HEADERS = ["timestamp","ce_delta","pe_delta","ce_vega","pe_vega","ce_theta","pe_theta"]

# -------------------- HELPERS --------------------
def init_log():
    base = {h:0.0 for h in RAW_HEADERS}
    base["timestamp"] = now.isoformat()
    pd.DataFrame([base]).to_csv(log_file,index=False)
    print("⚠️ Initialized log with RAW_HEADERS and zeros.")

if not os.path.exists(log_file):
    init_log()

# -------------------- MAIN --------------------
# Load creds
secrets_path = os.path.expanduser("~/.streamlit/secrets.toml")
if os.path.exists(secrets_path):
    sec = toml.load(secrets_path)
    gcreds = json.loads(sec.get("GCREDS","{}"))
elif "GCREDS" in os.environ:
    gcreds = json.loads(os.environ["GCREDS"])
else:
    raise RuntimeError("GCREDS not found.")

creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds,["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"])
client = gspread.authorize(creds)
sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")

api_key = sheet.acell("A1").value.strip()
access_token = sheet.acell("C1").value.strip()

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# Validate
try:
    sp = kite.ltp(["NSE:NIFTY 50"])["NSE:NIFTY 50"]["last_price"]
    print(f"✅ Valid token. Spot: {sp}")
except Exception as e:
    print(f"❌ Token invalid: {e}")
    exit(1)

# Instruments
inst = pd.DataFrame(kite.instruments("NFO"))
opts = inst[(inst["name"]=="NIFTY") & (inst["segment"]=="NFO-OPT")]

# Expiry
today = datetime.date.today()
exp = sorted(opts["expiry"].unique())
ne = next(e for e in exp if pd.to_datetime(e).date()>=today)
ce = opts[(opts["expiry"]==ne)&(opts["instrument_type"]=="CE")]
pe = opts[(opts["expiry"]==ne)&(opts["instrument_type"]=="PE")]

# Greeks raw calc
T, r, iv = 1/12, 0.06, 0.14
ce_ltp = kite.ltp(ce["instrument_token"].tolist())
pe_ltp = kite.ltp(pe["instrument_token"].tolist())
ce["ltp"] = ce["instrument_token"].apply(lambda x: ce_ltp[str(x)]["last_price"])
pe["ltp"] = pe["instrument_token"].apply(lambda x: pe_ltp[str(x)]["last_price"])

# Black-Scholes
def greeks_KS(row, S):
    K=row["strike"]
    d1=(np.log(S/K)+(r+0.5*iv**2)*T)/(iv*np.sqrt(T))
    delta = norm.cdf(d1) if row["instrument_type"]=="CE" else -norm.cdf(-d1)
    vega = S*norm.pdf(d1)*np.sqrt(T)/100
    theta = -S*norm.pdf(d1)*iv/(2*np.sqrt(T))/365
    return pd.Series([delta,vega,theta])

ce[["delta","vega","theta"]] = ce.apply(greeks_KS,axis=1,args=(sp,))
pe[["delta","vega","theta"]] = pe.apply(greeks_KS,axis=1,args=(sp,))

# Sum raw
data = {
    "timestamp":now.isoformat(),
    "ce_delta":ce[(ce["delta"]>=0.05)&(ce["delta"]<=0.6)]["delta"].sum(),
    "pe_delta":pe[(pe["delta"].abs()>=0.05)&(pe["delta"].abs()<=0.6)]["delta"].sum(),
    "ce_vega":ce["vega"].sum(),
    "pe_vega":pe["vega"].sum(),
    "ce_theta":ce["theta"].sum(),
    "pe_theta":pe["theta"].sum()
}
row=pd.DataFrame([data])

# Append
hdr = pd.read_csv(log_file,nrows=0).columns.tolist()
if hdr!=RAW_HEADERS:
    init_log()
    hdr = RAW_HEADERS
row.to_csv(log_file,mode='a',header=False,index=False)
print("✅ Logged raw Greeks.")

# Open snapshot
if now.strftime("%H:%M")=="09:15":
    s=row.rename(columns={
        "ce_delta":"ce_delta_open","pe_delta":"pe_delta_open",
        "ce_vega":"ce_vega_open","pe_vega":"pe_vega_open",
        "ce_theta":"ce_theta_open","pe_theta":"pe_theta_open"
    })
    s.to_csv(open_file,index=False)
    print("📌 Saved open snapshot.")
