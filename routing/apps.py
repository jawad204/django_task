# routing/apps.py
import os
import pandas as pd
from scipy.spatial import KDTree
from django.apps import AppConfig
from django.conf import settings

class RoutingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'routing'

    # Declare both attributes explicitly so they always exist
    stations_df = None
    kdtree = None

    def ready(self):
        # Prevent running twice during Django dev server auto-reload
        # In runserver, RUN_MAIN is 'true' for the actual worker process
        if os.environ.get('RUN_MAIN') != 'true' and 'runserver' in os.sys.argv:
            return

        csv_path = os.path.join(
            settings.BASE_DIR,
            'data',
            'fuel-prices-for-be-assessment-stations-coordinates.csv'
        )

        print(f"[*] Looking for fuel data at: {csv_path}")

        if os.path.exists(csv_path):
            try:
                # Load CSV
                df = pd.read_csv(csv_path)

                # Ensure required columns exist
                if 'Latitude' in df.columns and 'Longitude' in df.columns:
                    coords = df[['Latitude', 'Longitude']].values
                elif 'latitude' in df.columns and 'longitude' in df.columns:
                    coords = df[['latitude', 'longitude']].values
                else:
                    raise KeyError(f"Missing Latitude/Longitude columns. Available: {list(df.columns)}")

                RoutingConfig.stations_df = df
                RoutingConfig.kdtree = KDTree(coords)
                print(f"[+] Successfully loaded {len(df)} stations and built KDTree.")
            except Exception as e:
                print(f"[!] Error loading fuel data: {e}")
        else:
            print(f"[!] Warning: File NOT FOUND at {csv_path}. Please check the filename and location.")