"""
Open-Meteo Weather Scraper
──────────────────────────
Accesses Open-Meteo API for current weather, forecasts, and climate data.
No API key required. Rate limit: 10,000 requests/day (shared pool).
Reliability: Extremely High (German nonprofit, ISO certified data).

Open-Meteo provides weather data without API keys, authentication, or commercial restrictions.
Uses National Weather Services data (NOAA, DWD, Meteo-France, etc.).
"""

import asyncio
import logging
from typing import Optional

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

OPENMETEO_API_URL = "https://api.open-meteo.com/v1"
HEADERS = {
    "User-Agent": "Zhenyi Research Agent (github.com/zhenyi-research)",
}


class OpenmeteoScraper(BaseScraper):
    """Search for weather and climate data via Open-Meteo API."""

    def __init__(self, config: dict):
        super().__init__("open_meteo", config)

    async def _fetch(self, query: str) -> list[dict]:
        """
        Search Open-Meteo for weather/climate data.
        """
        try:
            results = await asyncio.to_thread(
                self._search_openmeteo,
                query,
                self.results_per_query
            )
            logger.info(f"[open_meteo] Found {len(results)} results for: {query[:50]}")
            return results
        
        except Exception as e:
            logger.warning(f"[open_meteo] Error searching: {e}")
            return []

    def _search_openmeteo(self, query: str, max_results: int) -> list[dict]:
        """
        Search for locations and retrieve weather data.
        Run in thread pool to avoid blocking.
        """
        try:
            import requests
            
            q = query.lower()
            
            # Check if query is weather/climate related
            weather_keywords = ["weather", "forecast", "temperature", "climate", "wind", "rain", "celsius", "fahrenheit"]
            if not any(kw in q for kw in weather_keywords):
                logger.debug(f"[open_meteo] Query not weather-related: {query}")
                return []
            
            # Try to extract location (very simple heuristic)
            # Example: "what is the weather in london" → "london"
            location = None
            for keyword in ["in ", "at ", "for ", "near "]:
                if keyword in q:
                    idx = q.find(keyword) + len(keyword)
                    location = query[idx:].strip().split()[0]
                    break
            
            if not location:
                # Try to grab last significant word
                words = [w for w in query.split() if len(w) > 2]
                location = words[-1] if words else "new york"
            
            # Geocode location
            geocoding_params = {
                "name": location,
                "count": 1,
                "language": "en",
            }
            
            geo_resp = requests.get(
                f"{OPENMETEO_API_URL}/geocoding",
                params=geocoding_params,
                headers=HEADERS,
                timeout=self.timeout_seconds
            )
            geo_resp.raise_for_status()
            geo_data = geo_resp.json()
            
            results_list = geo_data.get("results", [])
            if not results_list:
                logger.warning(f"[open_meteo] Location not found: {location}")
                return []
            
            location_info = results_list[0]
            lat = location_info.get("latitude")
            lon = location_info.get("longitude")
            name = location_info.get("name", location)
            country = location_info.get("country", "")
            
            # Get weather data
            weather_params = {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "timezone": "auto",
            }
            
            weather_resp = requests.get(
                f"{OPENMETEO_API_URL}/forecast",
                params=weather_params,
                headers=HEADERS,
                timeout=self.timeout_seconds
            )
            weather_resp.raise_for_status()
            weather_data = weather_resp.json()
            
            current = weather_data.get("current", {})
            timezone = weather_data.get("timezone", "UTC")
            
            content = f"Location: {name}, {country}\n"
            content += f"Timezone: {timezone}\n"
            content += f"Temperature: {current.get('temperature_2m', 'N/A')}°C\n"
            content += f"Humidity: {current.get('relative_humidity_2m', 'N/A')}%\n"
            content += f"Wind Speed: {current.get('wind_speed_10m', 'N/A')} km/h"
            
            return [{
                "source": "open_meteo",
                "title": f"Weather for {name}",
                "url": f"https://open-meteo.com/?latitude={lat}&longitude={lon}",
                "content": content,
            }]
        
        except Exception as e:
            logger.error(f"[open_meteo] Search failed: {e}")
            return []
