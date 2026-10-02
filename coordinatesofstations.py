import json
import time
import urllib.parse
import urllib.request
import pandas as pd

INPUT_CSV = "D:/Projects/django task/data/fuel-prices-for-be-assessment.csv"
OUTPUT_CSV = "D:/Projects/django task/data/fuel-prices-for-be-assessment-stations-coordinates.csv"
import pandas as pd



# Load assessment CSV
df = pd.read_csv(INPUT_CSV)
print(f"Loaded {len(df)} fuel price rows.")

# Load public US cities dataset directly via GitHub raw or local download
us_cities_url = "https://raw.githubusercontent.com/kelvins/US-Cities-Database/main/csv/us_cities.csv"
print("Loading US Cities geographic coordinates database...")
cities_df = pd.read_csv(us_cities_url)

# Clean and standardize names for accurate matching
df['city_clean'] = df['City'].astype(str).str.strip().str.upper()
df['state_clean'] = df['State'].astype(str).str.strip().str.upper()

cities_df['city_clean'] = cities_df['CITY'].astype(str).str.strip().str.upper()
cities_df['state_clean'] = cities_df['STATE_CODE'].astype(str).str.strip().str.upper()

# Drop duplicates in reference dataset to ensure 1-to-1 merge
city_coords = cities_df[['city_clean', 'state_clean', 'LATITUDE', 'LONGITUDE']].drop_duplicates(
    subset=['city_clean', 'state_clean']
)

# Merge coordinates onto fuel dataset
merged = pd.merge(df, city_coords, on=['city_clean', 'state_clean'], how='left')

merged.rename(columns={'LATITUDE': 'Latitude', 'LONGITUDE': 'Longitude'}, inplace=True)
merged.drop(columns=['city_clean', 'state_clean'], inplace=True)

# Fill any small remaining edge cases with state-centroid fallbacks or drop unresolvable
before_count = len(merged)
clean_merged = merged.dropna(subset=['Latitude', 'Longitude']).copy()
print(f"Matched coordinates for {len(clean_merged)} / {before_count} stations ({len(clean_merged)/before_count*100:.1f}%).")

clean_merged.to_csv(OUTPUT_CSV, index=False)
print(f"Saved ready-to-use dataset to {OUTPUT_CSV}")