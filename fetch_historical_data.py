# fetch_historical_data.py
import os
import json
import datetime
import pytz
import pandas as pd
from kiteconnect import KiteConnect
from oauth2client.service_account import ServiceAccountCredentials
import gspread

def main():
    # -------------------- CONFIG --------------------
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.datetime.now(ist)
    today = now.date()

    # NSE Holidays for 2025 (update as needed)
    nse_holidays = {
        datetime.date(2025,1,26), datetime.date(2025,2,26), datetime.date(2025,3,14),
        datetime.date(2025,3,31), datetime.date(2025,4,10), datetime.date(2025,4,14),
        datetime.date(2025,4,18), datetime.date(2025,5,1),  datetime.date(2025,8,15),
        datetime.date(2025,8,27), datetime.date(2025,10,2), datetime.date(2025,10,21),
        datetime.date(2025,10,22), datetime.date(2025,11,5), datetime.date(2025,12,25)
    }
    # Skip weekends and holidays
    if today.weekday() >= 5 or today in nse_holidays:
        print("❌ Market closed or holiday. Exiting.")
        return

    # -------------------- LOAD CREDENTIALS --------------------
    raw = os.environ.get("GCREDS") or os.environ.get("gcreds")
    if not raw:
        raise RuntimeError("❌ GCREDS not found in environment.")
    try:
        gcreds = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"❌ GCREDS is not valid JSON: {e}")

    # -------------------- GOOGLE SHEETS AUTH --------------------
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(gcreds, scope)
    gc = gspread.authorize(creds)

    # Open token and OHLC data workbooks
    token_wb = gc.open_by_key(os.environ["TOKEN_SHEET_ID"])
    data_wb  = gc.open_by_key(os.environ["OHLCS_SHEET_ID"])

    # Read API tokens
    cfg = token_wb.worksheet("Sheet1")
    api_key = cfg.acell("A1").value.strip()
    access_token = cfg.acell("C1").value.strip()

    # Prepare OHLC worksheet
    ohlc_ws = data_wb.worksheet("OHLC")

    # -------------------- INIT KITE --------------------
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)

    # Determine last trading day
    from kiteconnect import KiteException
    def last_trading_day(ref_date):
        d = ref_date - datetime.timedelta(days=1)
        while d.weekday() >= 5 or d in nse_holidays:
            d -= datetime.timedelta(days=1)
        return d

    ltd = last_trading_day(today)
    start = datetime.datetime.combine(ltd, datetime.time(9,15, tzinfo=ist))
    end   = datetime.datetime.combine(ltd, datetime.time(15,30, tzinfo=ist))

    # -------------------- FETCH HISTORICAL OHLC DATA --------------------
    try:
        ohlc = kite.historical_data(
            instrument_token=256265,
            from_date=start,
            to_date=end,
            interval="5minute"
        )
        df = pd.DataFrame(ohlc)
        # convert to IST timezone if needed
        df['date'] = pd.to_datetime(df['date']).dt.tz_localize('UTC').dt.tz_convert(ist)

        # Clear existing sheet and set headers
        ohlc_ws.clear()
        headers = ['date', 'open', 'high', 'low', 'close', 'volume']
        ohlc_ws.append_row(headers)

        # Append all rows
        rows = [
            [row['date'].isoformat(), row['open'], row['high'], row['low'], row['close'], row['volume']]
            for _, row in df.iterrows()
        ]
        ohlc_ws.append_rows(rows, value_input_option='USER_ENTERED')
        print(f"✅ Retrieved and logged {len(df)} candles for {ltd}")
    except Exception as e:
        print(f"❌ Failed to fetch or log historical data: {e}")

if __name__ == "__main__":
    main()
