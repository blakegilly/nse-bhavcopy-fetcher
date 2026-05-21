import requests
import zipfile
import io
import pandas as pd
from datetime import datetime
from supabase import create_client
import os
import time

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

today = datetime.now().strftime("%Y%m%d")

url = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{today}_F_0000.csv.zip"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Accept": "*/*",
    "Connection": "keep-alive"
}

session = requests.Session()

# NSE often requires homepage hit first
session.get("https://www.nseindia.com", headers=headers, timeout=10)

time.sleep(2)

response = session.get(url, headers=headers, timeout=30)

print("HTTP Status:", response.status_code)

if response.status_code != 200:
    print("Bhavcopy not available yet")
    exit()

z = zipfile.ZipFile(io.BytesIO(response.content))

csv_file = z.namelist()[0]

with z.open(csv_file) as f:
    df = pd.read_csv(f)

symbol_col = "TckrSymb" if "TckrSymb" in df.columns else "SYMBOL"
open_col = "OpnPric" if "OpnPric" in df.columns else "OPEN"
high_col = "HghPric" if "HghPric" in df.columns else "HIGH"
low_col = "LwPric" if "LwPric" in df.columns else "LOW"
close_col = "ClsPric" if "ClsPric" in df.columns else "CLOSE"
volume_col = "TtlTradgVol" if "TtlTradgVol" in df.columns else "TOTTRDQTY"

trade_date = datetime.now().strftime("%Y-%m-%d")

records = []

for _, row in df.iterrows():

    try:
        records.append({
            "symbol": str(row[symbol_col]),
            "trade_date": trade_date,
            "open": float(row[open_col]),
            "high": float(row[high_col]),
            "low": float(row[low_col]),
            "close": float(row[close_col]),
            "volume": int(row[volume_col])
        })

    except Exception as e:
        print("Skipping row:", e)

if records:
    response = supabase.table("stocks_eod").upsert(records).execute()
    print("Inserted rows:", len(records))
else:
    print("No valid records found")
