import unittest

from crop_advisor import suggest_crops


class CropAdvisorTests(unittest.TestCase):
    def test_suggests_soil_compatible_crops_with_weather_details(self):
        result = suggest_crops("alluvial", {
            "temperature_2m": 24,
            "precipitation": 0.2,
            "relative_humidity_2m": 65,
            "wind_speed_10m": 8
        })

        self.assertEqual(result["soil_type"], "Alluvial")
        self.assertEqual(len(result["recommendations"]), 4)
        self.assertIn("Rice", {
            item["crop"] for item in result["recommendations"]
        })
        self.assertTrue(all(
            item["weather_fit"] == "Good temperature match"
            for item in result["recommendations"]
        ))
        self.assertEqual(result["weather_cautions"], [])

    def test_warns_about_severe_weather_and_temperature_mismatch(self):
        result = suggest_crops("sandy", {
            "temperature_2m": 42,
            "precipitation": 8,
            "relative_humidity_2m": 90,
            "wind_speed_10m": 35
        })

        self.assertEqual(len(result["weather_cautions"]), 4)
        self.assertTrue(all(
            item["score"] < 100
            for item in result["recommendations"]
        ))
        self.assertTrue(all(
            item["weather_fit"] == "Heat stress risk"
            for item in result["recommendations"]
        ))

    def test_rejects_unknown_soil_and_missing_temperature(self):
        with self.assertRaises(ValueError):
            suggest_crops("unknown", {"temperature_2m": 25})

        with self.assertRaises(ValueError):
            suggest_crops("Loamy", {})


if __name__ == "__main__":
    unittest.main()
