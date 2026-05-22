import os
import time
import requests
import pandas as pd
from io import BytesIO
import zipfile
from datetime import datetime, timedelta
from supabase import create_client

print("STARTING SCRIPT")

# -----------------------------
# ENV
# -----------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

print("SUPABASE_URL exists:", bool(SUPABASE_URL))
print("SUPABASE_KEY exists:", bool(SUPABASE_KEY))

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("Missing Supabase credentials")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
print("Supabase client created")


# -----------------------------
# NSE FETCH (WITH RETRY)
# -----------------------------
def fetch_bhavcopy(max_lookback_days=5):
    base_headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Referer": "https://www.nseindia.com/",
    }

    today = datetime.now()

    for i in range(max_lookback_days):
        trade_day = today - timedelta(days=i + 1)
        date_str = trade_day.strftime("%Y%m%d")

        url = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date_str}_F_0000.csv.zip"

        print("Trying:", url)

        try:
            r = requests.get(url, headers=base_headers, timeout=20)

            if r.status_code != 200:
                continue

            if "zip" not in r.headers.get("Content-Type", ""):
                continue

            print("SUCCESS FOUND FILE FOR:", date_str)
            return trade_day, r.content

        except Exception as e:
            print("Error for date", date_str, "->", str(e))
            continue

    raise Exception("No bhavcopy found in last N days")


trade_day, content = fetch_bhavcopy()


# -----------------------------
# READ ZIP
# -----------------------------
zf = zipfile.ZipFile(BytesIO(content))
file_name = zf.namelist()[0]

df = pd.read_csv(zf.open(file_name))

print("CSV Loaded")
print("Rows:", len(df))

# -----------------------------
# CLEAN COLUMN NAMES
# -----------------------------
df.columns = [c.strip().lower() for c in df.columns]

print("Columns:", df.columns.tolist())


# -----------------------------
# FILTER EQ ONLY
# -----------------------------
df = df[df["sctysrs"] == "EQ"]


# -----------------------------
# RENAME TO DB FORMAT
# -----------------------------
df = df.rename(columns={
    "tckrsymb": "symbol",
    "sctysrs": "series",
    "opnpric": "open",
    "hghpric": "high",
    "lwpric": "low",
    "clspric": "close",
    "lastpric": "last",
    "prvsclsgpric": "prevclose",
    "ttltradgvol": "tottrdqty",
    "ttltrfval": "tottrdval",
    "bizdt": "trade_date"
})


# -----------------------------
# CLEAN SYMBOL
# -----------------------------
df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()


# -----------------------------
# USE NSE DATE (IMPORTANT FIX)
# -----------------------------
df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date


# -----------------------------
# SELECT FINAL COLUMNS
# -----------------------------
df = df[
    [
        "symbol",
        "trade_date",
        "series",
        "open",
        "high",
        "low",
        "close",
        "last",
        "prevclose",
        "tottrdqty",
        "tottrdval",
    ]
]


# -----------------------------
# CLEAN NULLS
# -----------------------------
df = df.where(pd.notnull(df), None)


# -----------------------------
# DEDUPE
# -----------------------------
df = df.drop_duplicates(subset=["symbol", "trade_date"], keep="last")

print("Final rows:", len(df))


# -----------------------------
# SUPABASE SAFE SERIALIZATION FIX
# -----------------------------
records = df.to_dict(orient="records")

# convert python date -> string (CRITICAL FIX)
for r in records:
    if r.get("trade_date"):
        r["trade_date"] = r["trade_date"].isoformat()


print("Sample record:", records[0])


# -----------------------------
# UPSERT
# -----------------------------
try:
    print("Uploading to Supabase...")

    result = supabase.table("stocks_eod").upsert(
        records,
        on_conflict="symbol,trade_date"
    ).execute()

    print("SUCCESS")
    print("Inserted rows:", len(records))

except Exception as e:
    print("FAILED INSERT")
    print(str(e))
