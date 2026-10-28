from weather import get_weather

weather = get_weather(28.6139, 77.2090)

if weather:
    print("Weather fetched successfully!")
    print("Temperature:", weather["temperature_2m"], "°C")
    print("Humidity:", weather["relative_humidity_2m"], "%")
    print("Rainfall:", weather["precipitation"], "mm")
    print("Wind speed:", weather["wind_speed_10m"], "km/h")
else:
    print("Weather could not be fetched.")