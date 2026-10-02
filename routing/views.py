from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .services import get_route, find_candidate_stations, optimize_fuel_stops

class RoutePlannerView(APIView):
    def post(self, request):
        start = request.data.get('start')    # Expected format: [lon, lat] e.g. [-74.006, 40.7128] (NYC)
        finish = request.data.get('finish')  # Expected format: [lon, lat] e.g. [-118.2437, 34.0522] (LA)

        if not start or not finish:
            return Response(
                {"error": "Please provide 'start' and 'finish' as [longitude, latitude] arrays."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # 1. Fetch Route (Single API Call)
            route_geometry, total_distance = get_route(start, finish)

            # 2. Extract Candidate Gas Stations Along Highway
            candidates, total_route_miles = find_candidate_stations(route_geometry, max_detour_miles=10.0)

            # 3. Optimize Fuel Stops
            fuel_plan = optimize_fuel_stops(candidates, total_route_miles)

            # 4. Assemble GeoJSON output
            features = [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": route_geometry
                    },
                    "properties": {
                        "name": "Route",
                        "total_distance_miles": round(total_distance, 2),
                        "total_fuel_cost": fuel_plan['total_fuel_cost']
                    }
                }
            ]

            # Add each fuel stop as a Point Feature for mapping
            for stop in fuel_plan['stops']:
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": stop['coordinates']
                    },
                    "properties": {
                        "name": stop['name'],
                        "city": stop['city'],
                        "state": stop['state'],
                        "price": stop['fuel_price_per_gal'],
                        "gallons": stop['gallons_bought'],
                        "cost": stop['cost'],
                        "mile_marker": stop['mile_marker']
                    }
                })

            response_payload = {
                "summary": {
                    "total_distance_miles": round(total_distance, 2),
                    "total_money_spent": fuel_plan['total_fuel_cost'],
                    "total_gallons_consumed": fuel_plan['total_gallons'],
                    "fuel_stops_count": len(fuel_plan['stops'])
                },
                "optimal_fuel_stops": fuel_plan['stops'],
                "map": {
                    "type": "FeatureCollection",
                    "features": features
                }
            }

            return Response(response_payload, status=status.HTTP_200_OK)

        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)