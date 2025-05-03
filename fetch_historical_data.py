# fetch_historical_data.py
import os
import json
import datetime
import pytz
import pandas as pd
from kiteconnect import KiteConnect
from oauth2client.service_account import ServiceAccountCredentials
import gspread

# -------------------- LOAD CREDENTIALS --------------------
raw = os.environ.get("GCREDS") or os.environ.get("gcreds")
if not raw:
    raise RuntimeError("❌ GCREDS not found in environment.")
try:
    gcreds = json.loads(raw)
except json.JSONDecodeError as e:
    raise RuntimeError(f"❌ GCREDS is not valid JSON: {e}")

# -------------------- GOOGLE SHEETS AUTH --------------------
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
gc = gspread.authorize(creds)

# Open token store and OHLCData sheets by ID
try:
    token_wb = gc.open_by_key(os.environ["TOKEN_SHEET_ID"])
except Exception as e:
    raise RuntimeError(f"❌ Cannot open TOKEN_SHEET_ID: {e}\nMake sure the service account has access and the ID is correct.")
try:
    data_wb = gc.open_by_key(os.environ["OHLCS_SHEET_ID"])
except Exception as e:
    raise RuntimeError(
        f"❌ Cannot open OHLCS_SHEET_ID: {e}\n"
        "Please share the 'OHLCData' sheet with your service account email."
    )

# Read Zerodha API tokens
cfg          = token_wb.worksheet("Sheet1")
api_key      = cfg.acell("A1").value.strip()
access_token = cfg.acell("C1").value.strip()

# Prepare OHLC worksheet
ohlc_ws = data_wb.worksheet("OHLC")

# -------------------- DETERMINE TARGET DAY --------------------
ist   = pytz.timezone("Asia/Kolkata")
now   = datetime.datetime.now(ist)
today = now.date()

# NSE Holidays for 2025
nse_holidays = {
    datetime.date(2025,1,26), datetime.date(2025,2,26), datetime.date(2025,3,14),
    datetime.date(2025,3,31), datetime.date(2025,4,10), datetime.date(2025,4,14),
    datetime.date(2025,4,18), datetime.date(2025,5,1),  datetime.date(2025,8,15),
    datetime.date(2025,8,27), datetime.date(2025,10,2), datetime.date(2025,10,21),
    datetime.date(2025,10,22), datetime.date(2025,11,5), datetime.date(2025,12,25)
}

def get_last_trading_day(d, holidays):
    prev = d
    while prev.weekday() >= 5 or prev in holidays:
        prev -= datetime.timedelta(days=1)
    return prev

target_day = get_last_trading_day(today, nse_holidays)
print(f"ℹ️ Fetching OHLC for {target_day}")

# Set time bounds for 5-min candles
time_from = datetime.datetime.combine(
    target_day, datetime.time(9,15), tzinfo=ist
)
time_to   = datetime.datetime.combine(
    target_day, datetime.time(15,30), tzinfo=ist
)

# -------------------- INIT KITE --------------------
kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

# -------------------- FETCH HISTORICAL OHLC --------------------
try:
    candles = kite.historical_data(
        instrument_token=256265,
        from_date=time_from,
        to_date=time_to,
        interval="5minute",
        continuous=False
    )
    df = pd.DataFrame(candles)
        # convert to IST timezone safely
    df['date'] = pd.to_datetime(df['date'])
    try:
        df['date'] = df['date'].dt.tz_localize('UTC').dt.tz_convert(ist)
    except TypeError:
        df['date'] = df['date'].dt.tz_convert(ist)

    # Clear sheet and write headers()
    headers = ['date', 'open', 'high', 'low', 'close', 'volume']
    ohlc_ws.append_row(headers)

    # Append all candle rows
    rows = df[['date','open','high','low','close','volume']].apply(
        lambda r: [r['date'].isoformat(), r['open'], r['high'], r['low'], r['close'], r['volume']],
        axis=1
    ).tolist()
    ohlc_ws.append_rows(rows, value_input_option='USER_ENTERED')
    print(f"✅ Logged {len(df)} OHLC candles to sheet")
except Exception as e:
    print(f"❌ Failed to fetch or log OHLC data: {e}")

if __name__ == "__main__":
    pass
