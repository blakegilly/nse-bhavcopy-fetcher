import os
import requests
import pandas as pd
from datetime import datetime
from io import BytesIO
import zipfile
from supabase import create_client

# -----------------------------
# ENV
# -----------------------------
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------------
# NSE URL
# -----------------------------
today = datetime.now()

date_str = today.strftime("%d%m%Y")
month_str = today.strftime("%Y/%b").upper()

url = f"https://archives.nseindia.com/content/historical/EQUITIES/{month_str}/cm{date_str}bhav.csv.zip"

headers = {"User-Agent": "Mozilla/5.0"}

print("Fetching:", url)

response = requests.get(url, headers=headers)
print("HTTP Status:", response.status_code)

if response.status_code != 200:
    print("Bhavcopy not available yet")
    exit(0)

# -----------------------------
# READ ZIP CSV
# -----------------------------
zf = zipfile.ZipFile(BytesIO(response.content))
file_name = zf.namelist()[0]

df = pd.read_csv(zf.open(file_name))

# -----------------------------
# CLEAN COLUMN NAMES
# -----------------------------
df.columns = [c.strip().lower() for c in df.columns]

# -----------------------------
# NORMALIZE DATA (CRITICAL FIX)
# -----------------------------
df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()

df["trade_date"] = today.date().isoformat()

# -----------------------------
# SELECT ONLY REQUIRED FIELDS
# -----------------------------
df = df[
    [
        "symbol",
        "series",
        "open",
        "high",
        "low",
        "close",
        "last",
        "prevclose",
        "tottrdqty",
        "tottrdval",
        "trade_date",
    ]
]

# -----------------------------
# FORCE CLEAN TYPES (IMPORTANT)
# -----------------------------
df = df.fillna(0)

# -----------------------------
# HARD DEDUPLICATION (CRITICAL FIX)
# -----------------------------
df = df.sort_values(["symbol", "trade_date"])
df = df.drop_duplicates(subset=["symbol", "trade_date"], keep="last")

print("Final rows to insert:", len(df))

# -----------------------------
# FINAL SAFETY CHECK (VERY IMPORTANT)
# -----------------------------
dupes = df[df.duplicated(["symbol", "trade_date"], keep=False)]

if len(dupes) > 0:
    print("❌ Still duplicates found, fixing again...")
    df = df.drop_duplicates(["symbol", "trade_date"], keep="last")

# -----------------------------
# CONVERT TO RECORDS
# -----------------------------
records = df.to_dict(orient="records")

# -----------------------------
# UPSERT TO SUPABASE
# -----------------------------
try:
    response = supabase.table("stocks_eod").upsert(
        records,
        on_conflict="symbol,trade_date",
        ignore_duplicates=False
    ).execute()

    print("Supabase response:")
    print(response)

except Exception as e:
    print("SUPABASE ERROR:")
    print(str(e))
