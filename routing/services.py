import math
import requests
from django.apps import apps
from django.conf import settings

ORS_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6Ijk3MTIzNTA1OTY3YTRjMWFiZDU5OTAzYzhjYmVhNDc5IiwiaCI6Im11cm11cjY0In0="

def haversine_miles(lat1, lon1, lat2, lon2):
    """Calculates great circle distance between two points in miles."""
    r = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c

def get_route(start_coords, finish_coords):
    """
    Calls OpenRouteService once.
    Coordinates input format: [lon, lat]
    """
    url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
    headers = {
        "Authorization": ORS_API_KEY,
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/geo+json"
    }
    body = {
        "coordinates": [start_coords, finish_coords],
        "instructions": False,
        "units": "mi"
    }
    
    resp = requests.post(url, json=body, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    
    feature = data['features'][0]
    geometry = feature['geometry']['coordinates']  # List of [lon, lat]
    total_distance = feature['properties']['summary']['distance']  # in miles
    return geometry, total_distance

def find_candidate_stations(route_coords, max_detour_miles=10.0):
    """
    Projects cumulative distance along route and finds all gas stations
    within max_detour_miles using the KDTree.
    """
    routing_app = apps.get_app_config('routing')
    df = routing_app.stations_df
    tree = routing_app.kdtree

    # 1. Compute cumulative distance along the route polyline
    cum_dist = [0.0]
    for i in range(1, len(route_coords)):
        prev_lon, prev_lat = route_coords[i - 1]
        cur_lon, cur_lat = route_coords[i]
        seg_dist = haversine_miles(prev_lat, prev_lon, cur_lat, cur_lon)
        cum_dist.append(cum_dist[-1] + seg_dist)

    total_route_miles = cum_dist[-1]

    # Convert detour miles to degrees approx (1 deg lat ~ 69 miles)
    radius_deg = max_detour_miles / 69.0

    seen_station_ids = {}
    
    # Sample points every ~5-10 coordinates along the route for speed
    step = max(1, len(route_coords) // 200)
    for i in range(0, len(route_coords), step):
        lon, lat = route_coords[i]
        curr_mile = cum_dist[i]
        
        # Query stations within radius
        indices = tree.query_ball_point([lat, lon], r=radius_deg)
        for idx in indices:
            row = df.iloc[idx]
            station_id = row['OPIS Truckstop ID']
            station_lat = row['Latitude']
            station_lon = row['Longitude']
            
            # Check actual haversine distance
            dist_to_route = haversine_miles(lat, lon, station_lat, station_lon)
            if dist_to_route <= max_detour_miles:
                if station_id not in seen_station_ids:
                    seen_station_ids[station_id] = {
                        'id': int(station_id),
                        'name': row['Truckstop Name'],
                        'address': row['Address'],
                        'city': row['City'],
                        'state': row['State'],
                        'price': float(row['Retail Price']),
                        'latitude': float(station_lat),
                        'longitude': float(station_lon),
                        'mile_marker': curr_mile
                    }

    # Sort candidate stations by position along route
    sorted_candidates = sorted(seen_station_ids.values(), key=lambda s: s['mile_marker'])
    return sorted_candidates, total_route_miles

import heapq

def optimize_fuel_stops(candidates, total_route_miles):
    """
    Constrained Global Optimal Fuel Planner via Dijkstra / Dynamic Programming:
    - 500-mile maximum vehicle range (50 gal @ 10 MPG).
    - Starts with a full tank (500 miles of free range at START).
    - Strict minimum leg: driver must travel at least 250 miles before next stop (no micro-stops).
    - Refuel safety ceiling: refuels before 480 miles (20-mile buffer).
    - Destination exception: reaching the finish line has no minimum distance requirement.
    """
    MAX_RANGE = 500.0
    MPG = 10.0
    MIN_LEG_DISTANCE = 250.0  # Must drive at least 250 miles before stopping again
    SAFETY_MARGIN = 20.0     # 20-mile reserve buffer
    EFFECTIVE_MAX = MAX_RANGE - SAFETY_MARGIN  # 480.0 miles

    # If the trip is within the initial 500-mile tank
    if total_route_miles <= MAX_RANGE:
        return {
            "stops": [],
            "total_fuel_cost": 0.0,
            "total_gallons": 0.0
        }

    # Build graph nodes: START (mile 0) -> Filtered Stations -> FINISH (total_route_miles)
    nodes = [{
        'id': 'START',
        'name': 'Start Location',
        'city': '',
        'state': '',
        'longitude': 0.0,
        'latitude': 0.0,
        'mile_marker': 0.0,
        'price': 0.0
    }]

    for c in candidates:
        if 0 < c['mile_marker'] < total_route_miles:
            nodes.append(c)

    nodes.append({
        'id': 'FINISH',
        'name': 'Destination',
        'city': '',
        'state': '',
        'longitude': 0.0,
        'latitude': 0.0,
        'mile_marker': total_route_miles,
        'price': 0.0
    })

    n = len(nodes)
    INF = float('inf')
    min_cost = [INF] * n
    parent = [-1] * n

    min_cost[0] = 0.0
    pq = [(0.0, 0)]  # (cumulative_cost, node_index)

    while pq:
        curr_cost, u = heapq.heappop(pq)

        if curr_cost > min_cost[u]:
            continue

        if u == n - 1:
            break

        u_mile = nodes[u]['mile_marker']
        u_price = nodes[u]['price']

        for v in range(u + 1, n):
            dist = nodes[v]['mile_marker'] - u_mile

            # Rule 1: Cannot exceed vehicle tank range
            max_allowed = MAX_RANGE if v == n - 1 else EFFECTIVE_MAX
            if dist > max_allowed:
                break  # Candidates are sorted by mile marker, further nodes are unreachable

            # Rule 2: Cannot stop if driven less than 250 miles
            # Exception: Allowed if node v is FINISH (final arrival)
            if dist < MIN_LEG_DISTANCE and v != n - 1:
                continue

            # Leg cost: Leaving START costs 0 (starts full).
            # Otherwise, fuel consumed for this leg is purchased at station u.
            segment_cost = 0.0 if u == 0 else (dist / MPG) * u_price
            new_cost = curr_cost + segment_cost

            if new_cost < min_cost[v]:
                min_cost[v] = new_cost
                parent[v] = u
                heapq.heappush(pq, (new_cost, v))

    # Reconstruct optimal sequence from FINISH backwards
    curr = n - 1
    path_indices = []
    while curr != -1:
        path_indices.append(curr)
        curr = parent[curr]
    path_indices.reverse()

    stops = []
    for k in range(len(path_indices) - 1):
        idx = path_indices[k]
        next_idx = path_indices[k + 1]

        if idx == 0:
            continue  # Start point (pre-filled, not a purchased stop)

        station = nodes[idx]
        leg_dist = nodes[next_idx]['mile_marker'] - station['mile_marker']
        gallons = leg_dist / MPG
        cost = gallons * station['price']

        stops.append({
            "truckstop_id": station['id'],
            "name": station['name'].strip(),
            "city": station['city'].strip(),
            "state": station['state'].strip(),
            "coordinates": [station['longitude'], station['latitude']],
            "mile_marker": round(station['mile_marker'], 2),
            "fuel_price_per_gal": round(station['price'], 3),
            "gallons_bought": round(gallons, 2),
            "cost": round(cost, 2)
        })

    return {
        "stops": stops,
        "total_fuel_cost": round(min_cost[n - 1], 2),
        "total_gallons": round(sum(s['gallons_bought'] for s in stops), 2)
    }