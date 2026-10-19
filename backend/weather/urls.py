from django.urls import path

from weather.views import forecast_window

urlpatterns = [
    path("forecast-window/", forecast_window, name="weather-forecast-window"),
]
