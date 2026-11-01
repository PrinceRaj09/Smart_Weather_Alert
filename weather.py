
import requests


WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"


def analyze_weather(weather):
    """Generate alerts from current weather conditions."""
    alerts = []

    rain = weather.get("precipitation", 0) or 0
    wind = weather.get("wind_speed_10m", 0) or 0
    humidity = weather.get("relative_humidity_2m", 0) or 0
    temperature = weather.get("temperature_2m", 0) or 0

    if rain >= 5:
        alerts.append({
            "level": "Warning",
            "title": "Rainfall Alert",
            "message": (
                "Rainfall is elevated. Check field drainage "
                "and protect harvested crops."
            )
        })

    if wind >= 30:
        alerts.append({
            "level": "Danger",
            "title": "Strong Wind Alert",
            "message": (
                "Strong winds may damage vulnerable crops. "
                "Secure crop supports."
            )
        })

    if humidity >= 85:
        alerts.append({
            "level": "Warning",
            "title": "High Humidity Alert",
            "message": (
                "Monitor crops for fungal disease symptoms. "
                "Humidity alone does not confirm disease."
            )
        })

    if temperature >= 38:
        alerts.append({
            "level": "Warning",
            "title": "High Temperature Alert",
            "message": (
                "Check crops for heat stress and review "
                "irrigation needs."
            )
        })

    if not alerts:
        alerts.append({
            "level": "Normal",
            "title": "Weather Status Normal",
            "message": (
                "No current alert threshold was triggered. "
                "Continue monitoring the weather."
            )
        })

    return alerts


def analyze_forecast(hourly, current_time=None):
    """Check forecast data for rain and strong winds."""
    alerts = []

    times = hourly.get("time", [])
    rain_values = hourly.get("precipitation", [])
    wind_values = hourly.get("wind_speed_10m", [])

    for index, time in enumerate(times):
        if (
            isinstance(current_time, str)
            and isinstance(time, str)
            and time < current_time
        ):
            continue

        rain = (
            rain_values[index]
            if index < len(rain_values)
            else 0
        ) or 0

        wind = (
            wind_values[index]
            if index < len(wind_values)
            else 0
        ) or 0

        if rain >= 5:
            alerts.append({
                "type": "rain",
                "level": "Warning",
                "title": "Forecast Rainfall Alert",
                "message": (
                    f"Forecast rainfall is {rain} mm at {time}. "
                    "Check drainage and protect harvested crops."
                ),
                "time": time,
                "value": rain,
                "unit": "mm"
            })

        if wind >= 30:
            alerts.append({
                "type": "wind",
                "level": "Danger",
                "title": "Forecast Strong Wind Alert",
                "message": (
                    f"Forecast wind speed is {wind} km/h at {time}. "
                    "Secure crop supports and vulnerable plants."
                ),
                "time": time,
                "value": wind,
                "unit": "km/h"
            })

    return alerts


def get_weather(latitude, longitude):
    """
    Fetch current weather and the next 24 hours of forecast.

    Existing response keys are preserved for the old dashboard
    and test_weather.py.
    """
    try:
        latitude = float(latitude)
        longitude = float(longitude)

        if not -90 <= latitude <= 90:
            raise ValueError("Latitude must be between -90 and 90.")

        if not -180 <= longitude <= 180:
            raise ValueError("Longitude must be between -180 and 180.")

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": [
                "temperature_2m",
                "relative_humidity_2m",
                "precipitation",
                "wind_speed_10m"
            ],
            "hourly": [
                "precipitation",
                "wind_speed_10m",
                "temperature_2m",
                "relative_humidity_2m"
            ],
            "past_hours": 1,
            "forecast_hours": 24,
            "timezone": "auto"
        }

        response = requests.get(
            WEATHER_API_URL,
            params=params,
            timeout=15
        )
        response.raise_for_status()

        data = response.json()

        current = data.get("current")
        hourly = data.get("hourly", {})

        if not isinstance(current, dict):
            return None

        # Preserve the original current-weather fields.
        weather = dict(current)

        # Preserve the original alerts key.
        weather["alerts"] = analyze_weather(weather)

        # Add forecast information without removing old fields.
        weather["forecast"] = {
            "time": hourly.get("time", []),
            "precipitation": hourly.get("precipitation", []),
            "wind_speed_10m": hourly.get("wind_speed_10m", []),
            "temperature_2m": hourly.get("temperature_2m", [])
        }

        current_time = current.get("time")
        hourly_times = hourly.get("time", [])
        if isinstance(current_time, str) and isinstance(hourly_times, list):
            previous_indices = [
                index for index, value in enumerate(hourly_times)
                if isinstance(value, str) and value < current_time
            ]
            if previous_indices:
                index = previous_indices[-1]
                weather["previous_hour"] = {
                    "time": hourly_times[index],
                    "temperature_2m": (
                        hourly.get("temperature_2m", [])[index]
                        if index < len(hourly.get("temperature_2m", []))
                        else None
                    ),
                    "relative_humidity_2m": (
                        hourly.get("relative_humidity_2m", [])[index]
                        if index < len(hourly.get("relative_humidity_2m", []))
                        else None
                    ),
                    "precipitation": (
                        hourly.get("precipitation", [])[index]
                        if index < len(hourly.get("precipitation", []))
                        else None
                    ),
                    "wind_speed_10m": (
                        hourly.get("wind_speed_10m", [])[index]
                        if index < len(hourly.get("wind_speed_10m", []))
                        else None
                    )
                }
            else:
                weather["previous_hour"] = None
        else:
            weather["previous_hour"] = None

        weather["forecast_alerts"] = analyze_forecast(
            hourly,
            current_time
        )

        return weather

    except (
        requests.RequestException,
        KeyError,
        TypeError,
        ValueError
    ) as error:
        print("Weather API error:", error)
        return None
