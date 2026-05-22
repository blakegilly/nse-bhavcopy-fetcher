import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from io import BytesIO
import zipfile
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
# NSE DATE (MINIMAL FIX)
# -----------------------------
today = datetime.now()

# keep your original logic (safe + predictable)
if today.weekday() == 0:
    trade_day = today - timedelta(days=3)
else:
    trade_day = today - timedelta(days=1)

date_str = trade_day.strftime("%Y%m%d")

url = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date_str}_F_0000.csv.zip"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
    "Referer": "https://www.nseindia.com/",
}

print("Fetching:", url)

response = requests.get(url, headers=headers, timeout=30)

print("HTTP Status:", response.status_code)
print("Content-Type:", response.headers.get("Content-Type"))

if response.status_code != 200:
    print("Bhavcopy not available")
    exit(0)

if "zip" not in response.headers.get("Content-Type", ""):
    print("Did not receive ZIP")
    print(response.text[:500])
    exit(1)

# -----------------------------
# READ ZIP
# -----------------------------
zf = zipfile.ZipFile(BytesIO(response.content))

print("ZIP files:", zf.namelist())

file_name = zf.namelist()[0]
df = pd.read_csv(zf.open(file_name))

print("CSV Loaded")
print("Rows:", len(df))

# -----------------------------
# CLEAN
# -----------------------------
df.columns = [c.strip().lower() for c in df.columns]

print("Columns:")
print(df.columns.tolist())

df = df[df["sctysrs"] == "EQ"]

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
    "ttltrfval": "tottrdval"
})

df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()

# -----------------------------
# 🔥 FIX (CRITICAL)
# NO python date objects anywhere
# -----------------------------
df["trade_date"] = trade_day.strftime("%Y-%m-%d")

# -----------------------------
# SELECT
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

df = df.drop_duplicates(
    subset=["symbol", "trade_date"],
    keep="last"
)

print("Final rows:", len(df))

print("Sample dataframe:")
print(df.head())

# -----------------------------
# RECORDS
# -----------------------------
records = df.to_dict(orient="records")

print("Sample record:")
print(records[0])

# -----------------------------
# UPSERT
# -----------------------------
try:
    print("Attempting insert...")

    result = supabase.table("stocks_eod").upsert(
        records,
        on_conflict="symbol,trade_date"
    ).execute()

    print("INSERT SUCCESS")
    print(result)

except Exception as e:
    print("INSERT FAILED")
    print(str(e))
