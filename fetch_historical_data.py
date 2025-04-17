from kiteconnect import KiteConnect
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import json
import pandas as pd

# -------------------- SETUP HOLIDAY LIST --------------------

nse_holidays_2025 = [
    datetime.date(2025, 1, 26),  # Republic Day
    datetime.date(2025, 2, 26),  # Mahashivratri
    datetime.date(2025, 3, 14),  # Holi
    datetime.date(2025, 3, 31),  # Id-Ul-Fitr
    datetime.date(2025, 4, 10),  # Mahavir Jayanti
    datetime.date(2025, 4, 14),  # Ambedkar Jayanti
    datetime.date(2025, 4, 18),  # Good Friday
    datetime.date(2025, 5, 1),   # Maharashtra Day
    datetime.date(2025, 8, 15),  # Independence Day
    datetime.date(2025, 8, 27),  # Ganesh Chaturthi
    datetime.date(2025, 10, 2),  # Gandhi Jayanti
    datetime.date(2025, 10, 21), # Diwali
    datetime.date(2025, 10, 22), # Balipratipada
    datetime.date(2025, 11, 5),  # Guru Nanak Jayanti
    datetime.date(2025, 12, 25), # Christmas
]

def get_last_trading_day(today, holidays):
    delta = datetime.timedelta(days=1)
    last_day = today - delta
    while last_day.weekday() >= 5 or last_day in holidays:
        last_day -= delta
    return last_day

# -------------------- LOAD GOOGLE SHEET CREDENTIALS --------------------

# Load from GitHub Actions secret
gcreds = json.loads(os.environ["GCREDS"])

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
client = gspread.authorize(creds)
sheet = client.open("ZerodhaTokenStore").worksheet("Sheet1")

api_key = sheet.acell("A1").value.strip()
access_token = sheet.acell("C1").value.strip()

# -------------------- TOKEN VALIDATOR --------------------

print("🔐 Token Validator:")
print(f"📎 API Key         : {api_key}")
print(f"🔑 Access Token    : {access_token[:6]}...{access_token[-6:]}")
print(f"🕒 Current Time    : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("-" * 40)

# -------------------- INIT KITE --------------------

kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# -------------------- DETECT LAST TRADING DAY --------------------

today = datetime.date.today()
last_trading_day = get_last_trading_day(today, nse_holidays_2025)
print(f"📆 Last Trading Day: {last_trading_day}")

from_time = datetime.datetime.combine(last_trading_day, datetime.time(9, 15))
to_time = datetime.datetime.combine(last_trading_day, datetime.time(15, 30))

# -------------------- GET INSTRUMENT TOKEN FOR NIFTY 50 --------------------

try:
    instruments = kite.instruments("NSE")
    nifty_index = [i for i in instruments if i["tradingsymbol"] == "NIFTY 50" and i["segment"] == "NSE"]
    if not nifty_index:
        raise Exception("NIFTY 50 not found in instruments list.")
    instrument_token = nifty_index[0]["instrument_token"]
    print(f"🎯 Instrument Token: {instrument_token}")
except Exception as e:
    print(f"❌ Error fetching instrument token: {e}")
    exit(1)

# -------------------- FETCH HISTORICAL OHLC DATA --------------------

try:
    ohlc = kite.historical_data(
        instrument_token,
        from_time,
        to_time,
        interval="5minute",
        continuous=False
    )
    df = pd.DataFrame(ohlc)
    print(f"✅ Retrieved {len(df)} candles for {last_trading_day}")
    print(df.head())
except Exception as e:
    print(f"❌ Failed to fetch historical data: {e}")
