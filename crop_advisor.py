"""Rule-based crop shortlist using soil compatibility and current weather."""

import math


SOIL_TYPES = (
    "Alluvial",
    "Black",
    "Clay",
    "Laterite",
    "Loamy",
    "Red",
    "Sandy",
)


CROPS_BY_SOIL = {
    "alluvial": (
        ("Rice", 20, 35),
        ("Wheat", 10, 25),
        ("Maize", 18, 32),
        ("Mustard", 10, 25),
        ("Lentil", 15, 27),
    ),
    "black": (
        ("Cotton", 21, 35),
        ("Soybean", 20, 30),
        ("Sorghum", 20, 35),
        ("Chickpea", 15, 30),
        ("Wheat", 10, 25),
    ),
    "clay": (
        ("Rice", 20, 35),
        ("Jute", 24, 35),
        ("Wheat", 10, 25),
        ("Maize", 18, 32),
        ("Lentil", 15, 27),
    ),
    "laterite": (
        ("Cashew", 24, 34),
        ("Coconut", 22, 32),
        ("Tea", 18, 30),
        ("Coffee", 18, 28),
        ("Tapioca", 22, 32),
    ),
    "loamy": (
        ("Maize", 18, 32),
        ("Wheat", 10, 25),
        ("Rice", 20, 35),
        ("Groundnut", 20, 32),
        ("Chickpea", 15, 30),
    ),
    "red": (
        ("Groundnut", 20, 32),
        ("Pearl millet", 22, 38),
        ("Pigeon pea", 20, 35),
        ("Cotton", 21, 35),
        ("Ragi", 18, 32),
    ),
    "sandy": (
        ("Pearl millet", 22, 38),
        ("Groundnut", 20, 32),
        ("Sesame", 25, 38),
        ("Watermelon", 22, 35),
        ("Cluster bean", 25, 38),
    ),
}

WET_WEATHER_CROPS = {
    "Rice", "Jute", "Coconut", "Tea", "Coffee", "Tapioca"
}
DRY_WEATHER_CROPS = {
    "Sorghum", "Pearl millet", "Cluster bean", "Sesame",
    "Pigeon pea", "Ragi"
}


def _finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def suggest_crops(soil_type, weather):
    """Return a short, explainable crop shortlist for soil and current weather."""
    soil_key = str(soil_type or "").strip().casefold()
    if soil_key not in CROPS_BY_SOIL:
        raise ValueError("Choose a supported soil type.")
    if not isinstance(weather, dict):
        raise ValueError("Weather data must be an object.")

    temperature = _finite_number(weather.get("temperature_2m"))
    if temperature is None:
        raise ValueError("Current temperature is unavailable.")

    rainfall = _finite_number(weather.get("precipitation")) or 0
    humidity = _finite_number(weather.get("relative_humidity_2m")) or 0
    wind = _finite_number(weather.get("wind_speed_10m")) or 0
    cautions = []

    if temperature >= 38:
        cautions.append("Very hot conditions; protect crops from heat stress.")
    if rainfall >= 5:
        cautions.append("Rain is elevated; check drainage before field work.")
    if humidity >= 85:
        cautions.append("High humidity; monitor crops for fungal symptoms.")
    if wind >= 30:
        cautions.append("Strong wind; secure vulnerable plants and supports.")

    soil_name = next(
        soil for soil in SOIL_TYPES if soil.casefold() == soil_key
    )
    recommendations = []
    for crop, minimum, maximum in CROPS_BY_SOIL[soil_key]:
        weather_notes = []
        if minimum <= temperature <= maximum:
            weather_fit = "Good temperature match"
            score = 100
        else:
            distance = min(
                abs(temperature - minimum),
                abs(temperature - maximum)
            )
            score = max(40, 100 - round(distance * 5))
            weather_fit = "Temperature needs attention"

        if rainfall >= 5:
            if crop in WET_WEATHER_CROPS:
                score = min(100, score + 8)
                weather_notes.append("elevated rain supports moisture-tolerant crops")
            elif crop in DRY_WEATHER_CROPS:
                score = max(35, score - 5)
        elif rainfall < 0.1 and crop in DRY_WEATHER_CROPS:
            score = min(100, score + 5)
            weather_notes.append("low current rainfall favors drought-resilient crops")

        if temperature >= 38:
            score = max(35, score - 20)
            weather_fit = "Heat stress risk"

        reason = (
            f"Commonly grown in {soil_name} soil; suitable "
            f"temperature range {minimum}-{maximum}°C."
        )
        if weather_notes:
            reason += " Weather note: " + "; ".join(weather_notes) + "."
        recommendations.append({
            "crop": crop,
            "score": score,
            "weather_fit": weather_fit,
            "reason": reason
        })

    recommendations.sort(key=lambda item: item["score"], reverse=True)

    return {
        "soil_type": soil_name,
        "recommendations": recommendations[:4],
        "weather_cautions": cautions,
        "note": (
            "A planning shortlist only. Check local sowing season, soil test, "
            "irrigation and advice from your local agriculture office."
        )
    }
