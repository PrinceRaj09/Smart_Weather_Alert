
import requests


def analyze_weather(weather):
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
                "No configured alert threshold was triggered. "
                "Continue monitoring the weather."
            )
        })

    return alerts


def get_weather(latitude, longitude):
    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": [
            "temperature_2m",
            "relative_humidity_2m",
            "precipitation",
            "wind_speed_10m"
        ],
        "timezone": "auto"
    }

    try:
        response = requests.get(
            url, params=params, timeout=15
        )
        response.raise_for_status()

        data = response.json()
        weather = data["current"]
        weather["alerts"] = analyze_weather(weather)

        return weather

    except (requests.RequestException, KeyError, TypeError) as error:
        print("Weather API error:", error)
        return None
