from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

class FuelCostValidationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_fuel_cost_and_gallons_math(self):
        payload = {
            "start": [-87.6298, 41.8781],   # Chicago, IL
            "finish": [-95.3698, 29.7604]   # Houston, TX
        }
        response = self.client.post('/api/route/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.data
        summary = data['summary']
        stops = data['optimal_fuel_stops']
        
        total_dist = summary['total_distance_miles']
        total_spent = summary['total_money_spent']
        total_gallons = summary['total_gallons_consumed']
        
        # Test 1: Gallons bought must cover (Total Miles - 500 Starting Miles) / 10 MPG
        expected_gallons = max(0.0, (total_dist - 500.0) / 10.0)
        self.assertAlmostEqual(total_gallons, expected_gallons, delta=1.5)
        
        # Test 2: Sum of individual stop costs must match total_money_spent
        summed_cost = 0.0
        for stop in stops:
            expected_stop_cost = round(stop['gallons_bought'] * stop['fuel_price_per_gal'], 2)
            self.assertAlmostEqual(stop['cost'], expected_stop_cost, delta=0.05)
            summed_cost += stop['cost']
            
        self.assertAlmostEqual(total_spent, round(summed_cost, 2), delta=0.05)
        
        # Test 3: Vehicle must never run dry (no leg > 500 miles)
        prev_mile = 0.0
        for stop in stops:
            leg_distance = stop['mile_marker'] - prev_mile
            self.assertLessEqual(leg_distance, 500.0, f"Exceeded 500m tank: {leg_distance} mi")
            prev_mile = stop['mile_marker']
            
        final_leg = total_dist - prev_mile
        self.assertLessEqual(final_leg, 500.0, f"Ran dry on final leg: {final_leg} mi")