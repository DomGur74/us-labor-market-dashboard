
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime

# Set project paths
PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_DIR / "data" / "labor_market_data.csv"
DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

# Define BLS indicators
series = {
    "Civilian Employment": "LNS12000000",
    "Total Nonfarm Employment": "CES0000000001",
    "Unemployment Rate": "LNS14000000",
    "Average Hourly Earnings": "CES0500000003",
    "Average Weekly Hours": "CES0500000002",
    "Labor Productivity": "PRS85006092",
    "Consumer Price Index": "CUUR0000SA0"}

series_names = {series_id: name for name, series_id in series.items()}

# Set collection period
current_year = datetime.now().year
start_year = str(current_year - 1)
end_year = str(current_year)

# Request data from BLS
url = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
payload = {"seriesid": list(series.values()), "startyear": start_year, "endyear": end_year}

print("Connecting to BLS API...")

response = requests.post(url, json=payload, timeout=60)
response.raise_for_status()
data = response.json()

if data["status"] != "REQUEST_SUCCEEDED":
    raise RuntimeError("BLS API request failed: " + str(data.get("message", "Unknown error")))

print("BLS API connection successful!")

# Process observations
records = []
skipped_observations = 0

for result in data["Results"]["series"]:
    series_id = result["seriesID"]
    series_name = series_names[series_id]

    for item in result["data"]:
        year = int(item["year"])
        period = item["period"]

        # Process monthly observations
        if period.startswith("M") and period[1:].isdigit():
            month = int(period[1:])

            if not 1 <= month <= 12:
                continue

            observation_date = pd.Timestamp(year=year, month=month, day=1)
            frequency = "Monthly"

        # Process quarterly observations
        elif period.startswith("Q") and period[1:].isdigit():
            quarter = int(period[1:])

            if not 1 <= quarter <= 4:
                continue

            observation_date = pd.Period(f"{year}Q{quarter}", freq="Q").start_time
            frequency = "Quarterly"

        else:
            continue

        # Skip unavailable values
        try:
            value = float(item["value"])
        except (ValueError, TypeError):
            skipped_observations += 1
            continue

        # Extract footnotes
        footnotes = "; ".join(note.get("text", "") for note in item.get("footnotes", []) if note.get("text"))

        records.append({
            "date": observation_date,
            "year": year,
            "period": period,
            "series_name": series_name,
            "series_id": series_id,
            "frequency": frequency,
            "value": value,
            "footnotes": footnotes})

# Validate observations
new_data = pd.DataFrame(records)

if new_data.empty:
    raise ValueError("No valid observations were returned.")

returned_series = set(new_data["series_id"])
expected_series = set(series.values())
missing_series = expected_series - returned_series

if missing_series:
    raise ValueError("Missing indicators: " + str(missing_series))

# Merge with historical dataset
if DATA_PATH.exists():
    existing_data = pd.read_csv(DATA_PATH, parse_dates=["date"])
    print("Existing observations:", len(existing_data))
    combined_data = pd.concat([existing_data, new_data], ignore_index=True)
else:
    print("No existing dataset found.")
    combined_data = new_data

# Remove duplicates and prioritize new observations
combined_data = combined_data.drop_duplicates(subset=["series_id", "date"], keep="last")
combined_data = combined_data.sort_values(["series_id", "date"]).reset_index(drop=True)

# Save updated dataset
combined_data.to_csv(DATA_PATH, index=False, date_format="%Y-%m-%d")

# Display results
print("\nDATA UPDATE COMPLETE")
print("=" * 40)
print("Collection period:", start_year, "-", end_year)
print("New observations retrieved:", len(new_data))
print("Skipped missing observations:", skipped_observations)
print("Total observations stored:", len(combined_data))
print("Number of indicators:", combined_data["series_id"].nunique())

print("\nObservations by indicator:")
print(combined_data.groupby("series_name").size().to_string())
print("\nDataset saved to:", DATA_PATH)
