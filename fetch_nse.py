import os
import requests
import pandas as pd
from datetime import datetime
from supabase import create_client, Client

# -----------------------------
# ENV VARIABLES (GitHub Secrets)
# -----------------------------
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------------
# NSE BHAVCOPY DOWNLOAD LOGIC
# -----------------------------
today = datetime.now().strftime("%d%m%Y")

url = f"https://archives.nseindia.com/content/historical/EQUITIES/{datetime.now().strftime('%Y/%b').upper()}/cm{today}bhav.csv.zip"

headers = {
    "User-Agent": "Mozilla/5.0"
}

print(f"Fetching: {url}")

response = requests.get(url, headers=headers)

print(f"HTTP Status: {response.status_code}")

# If file not available yet
if response.status_code != 200:
    print("Bhavcopy not available yet")
    exit(0)

# -----------------------------
# READ CSV FROM ZIP
# -----------------------------
from io import BytesIO
import zipfile

zf = zipfile.ZipFile(BytesIO(response.content))
file_name = zf.namelist()[0]

df = pd.read_csv(zf.open(file_name))

# -----------------------------
# CLEAN / TRANSFORM DATA
# -----------------------------
df.columns = [c.strip().lower() for c in df.columns]

records = df.to_dict(orient="records")

# Normalize keys if needed
cleaned_records = []
for r in records:
    cleaned_records.append({
        "symbol": r.get("symbol"),
        "series": r.get("series"),
        "open": r.get("open"),
        "high": r.get("high"),
        "low": r.get("low"),
        "close": r.get("close"),
        "last": r.get("last"),
        "prevclose": r.get("prevclose"),
        "tottrdqty": r.get("tottrdqty"),
        "tottrdval": r.get("tottrdval"),
        "trade_date": datetime.now().date().isoformat()
    })

# -----------------------------
# REMOVE DUPLICATES (IMPORTANT FIX)
# -----------------------------
seen = set()
unique_records = []

for r in cleaned_records:
    key = (r["symbol"], r["trade_date"])
    if key not in seen:
        seen.add(key)
        unique_records.append(r)

print("Total records:", len(cleaned_records))
print("Unique records:", len(unique_records))

# -----------------------------
# UPSERT TO SUPABASE
# -----------------------------
response = supabase.table("stocks_eod").upsert(
    unique_records,
    on_conflict="symbol,trade_date"
).execute()

print("Insert complete:", response)
