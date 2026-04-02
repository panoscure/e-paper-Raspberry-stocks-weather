# class_lib.py
# MicroPython class for fetching weather and stock data via APIs
from PIL import ImageFont, ImageDraw, Image
import requests
import os
import math
import datetime
import time
from collections import defaultdict


from zoneinfo import ZoneInfo          # Python 3.9+; for older use pytz
# For Python < 3.9: import pytz and replace ZoneInfo with pytz.timezone('Europe/Athens')


class DateTime:
    def __init__(self):
        self.actual_time = None

    # ---------- Helper functions for DST calculation ----------
    def _is_leap_year(self, year):
        return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)

    def _last_sunday(self, year, month):
        """Return the day of the month (1-31) of the last Sunday in the given month."""
        if month in (1, 3, 5, 7, 8, 10, 12):
            last_day = 31
        elif month in (4, 6, 9, 11):
            last_day = 30
        elif month == 2:
            last_day = 29 if self._is_leap_year(year) else 28
        else:
            raise ValueError("Invalid month")

        t = time.mktime((year, month, last_day, 0, 0, 0, 0, 0, 0))
        wday = time.gmtime(t)[6]          # Monday=0, Sunday=6
        days_back = (wday - 6) % 7
        return last_day - days_back

    def _get_greek_offset(self, utc_now):
        """Return the current Greek UTC offset (2 or 3 hours) based on UTC timestamp."""
        utc_t = time.gmtime(utc_now)
        year = utc_t[0]

        start_day = self._last_sunday(year, 3)
        end_day   = self._last_sunday(year, 10)

        # DST starts at 01:00 UTC on the last Sunday of March
        # DST ends at 01:00 UTC on the last Sunday of October
        start_dst = time.mktime((year, 3, start_day, 1, 0, 0, 0, 0, 0))
        end_dst   = time.mktime((year, 10, end_day, 1, 0, 0, 0, 0, 0))

        if start_dst <= utc_now < end_dst:
            return 3   # summer time (UTC+3)
        else:
            return 2   # winter time (UTC+2)

    # ---------- Public methods ----------
    def get_current_offset(self):
        """Return current Greek UTC offset in hours (2 or 3)."""
        utc_now = time.time()
        return self._get_greek_offset(utc_now)

    def get_current_dt(self):
        """
        Fetch current UTC time, apply Greek offset, store the local time tuple
        in self.actual_time, and return it.
        """
        utc_now = time.time()
        offset = self._get_greek_offset(utc_now)
        # Add offset and then use gmtime (no further system timezone adjustment)
        self.actual_time = time.gmtime(utc_now + offset * 3600)
        return self.actual_time

    def get_date(self):
        """Return formatted date string (DD/MM/YYYY)."""
        if not self.actual_time:
            return "No time set"
        return "{:02d}/{:02d}/{:04d}".format(
            self.actual_time[2], self.actual_time[1], self.actual_time[0]
        )

    def get_ttime(self):
        """Return formatted time string (HH:MM:SS)."""
        if not self.actual_time:
            return "No time set"
        return "{:02d}:{:02d}:{:02d}".format(
            self.actual_time[3], self.actual_time[4], self.actual_time[5]
        )


class APIClient:
    """
    A simple client to fetch:
    - Current weather from OpenWeatherMap
    - Real-time stock data from EOD Historical Data
    """
    def __init__(self, owm_api_key, city, country, eodhd_api_token, yahoo_api_key):
        """
        :param owm_api_key:      OpenWeatherMap API key
        :param city:             City name (e.g., "Athens")
        :param country:          2‑letter country code (e.g., "GR")
        :param eodhd_api_token:  EOD Historical Data API token
        """
        self.owm_api_key = owm_api_key
        self.yahoo_api_token = yahoo_api_key
        self.city = city
        self.country = country
        self.eodhd_api_token = eodhd_api_token

    # ---------- Weather ----------
    def fetch_weather(self):
        """
        Fetch current weather from OpenWeatherMap.
        Returns a dictionary with keys:
            condition, temp, feels, humidity, pressure,
            wind_speed, wind_deg, visibility,
            sunrise, sunset, rain, snow
        """
        url = (
            "http://api.openweathermap.org/data/2.5/weather"
            "?q={},{}&appid={}&units=metric".format(
                self.city, self.country, self.owm_api_key
            )
        )
        try:
            response = requests.get(url)
            data = response.json()
            response.close()
        except Exception as e:
            print("Weather fetch failed:", e)
            return None

        # Extract fields (with fallbacks for missing data)
        weather = {
            "condition": data["weather"][0]["description"],
            "weather_icon": data["weather"][0]["icon"],
            "weather_id": data["weather"][0]["id"],
            "temp": data["main"]["temp"],
            "feels": data["main"]["feels_like"],
            "humidity": data["main"]["humidity"],
            "pressure": data["main"]["pressure"],
            "wind_speed": data["wind"]["speed"],
            "wind_deg": data["wind"].get("deg", 0),
            "visibility": data.get("visibility", 0),
            "sunrise": data["sys"]["sunrise"],
            "sunset": data["sys"]["sunset"],
            "rain": data.get("rain", {}).get("1h", 0),
            "snow": data.get("snow", {}).get("1h", 0)
        }
        return weather




    def fetch_forecast(self):
        """
        Fetch 5-day forecast from OpenWeatherMap and return structured data.
    
        Returns a dictionary with:
            - current: current weather (temp, humidity, condition, time in Greek time)
            - next_3hour: list of the next 4 three‑hour forecast intervals (strictly after now,
                          with times converted to Greek local time)
            - next_daily: list of one forecast per day for the next 4 days (midday local time),
                          excluding the current Greek day
        Returns None if the request fails.
        """
        # Build forecast URL
        url = (
            "http://api.openweathermap.org/data/2.5/forecast"
            "?q={},{}&appid={}&units=metric".format(
                self.city, self.country, self.owm_api_key
            )
        )
        try:
            response = requests.get(url)
            data = response.json()
            response.close()
        except Exception as e:
            print("Forecast fetch failed:", e)
            return None
    
        if data.get("cod") != "200":
            print("Forecast error:", data.get("message"))
            return None
    
        # --- Current weather (reuse fetch_weather) ---
        current_weather = self.fetch_weather()
        if not current_weather:
            return None
    
        # --- Time zone setup ---
        greek_tz = ZoneInfo('Europe/Athens')      # For Python < 3.9: pytz.timezone('Europe/Athens')
        now_greek = datetime.datetime.now(greek_tz)
    
        current_data = {
            "temp": current_weather["temp"],
            "humidity": current_weather["humidity"],
            "condition": current_weather["condition"],
            "weather_id": current_weather["weather_id"],
            "time": now_greek.strftime("%Y-%m-%d %H:%M:%S")   # Greek local time
        }
    
        # --- Convert all forecast entries to Greek time and filter future entries ---
        future_entries = []
        for e in data["list"]:
            # Convert UTC timestamp to Greek local datetime
            dt_utc = datetime.datetime.fromtimestamp(e["dt"], tz=datetime.timezone.utc)
            dt_greek = dt_utc.astimezone(greek_tz)
            # Keep only entries strictly after current Greek time
            if dt_greek > now_greek:
                # Attach the Greek datetime to the entry for later use
                e["_dt_greek"] = dt_greek
                future_entries.append(e)
    
        # --- 3‑hour intervals after now (next 4) ---
        next_3hour = []
        for i in range(min(4, len(future_entries))):
            e = future_entries[i]
            next_3hour.append({
                "temp": e["main"]["temp"],
                "humidity": e["main"]["humidity"],
                "condition": e["weather"][0]["description"],
                "weather_id": e["weather"][0]["id"],
                "time": e["_dt_greek"].strftime("%Y-%m-%d %H:%M:%S")   # Greek local time
            })
    
        # --- Daily forecasts (one per day, excluding today's Greek date) ---
        # Group forecast entries by Greek date (YYYY-MM-DD)
        daily_groups = defaultdict(list)
        for e in future_entries:
            date_str = e["_dt_greek"].strftime("%Y-%m-%d")
            # Only consider dates that are not today (Greek)
            if e["_dt_greek"].date() != now_greek.date():
                daily_groups[date_str].append(e)
    
        # Sort the dates and take the next 4 distinct dates (after today)
        dates = sorted(daily_groups.keys())
        next_daily = []
        for date in dates[:4]:
            entries = daily_groups[date]
            # Find the entry whose Greek local hour is closest to 12:00 (midday)
            best = None
            best_diff = 24
            for e in entries:
                hour = e["_dt_greek"].hour
                diff = abs(hour - 12)
                if diff < best_diff:
                    best = e
                    best_diff = diff
            if best:
                # Use Greek date to get weekday name
                dt_obj = best["_dt_greek"]
                day_name = dt_obj.strftime("%a").upper()[:3]
                next_daily.append({
                    "temp": best["main"]["temp"],
                    "humidity": best["main"]["humidity"],
                    "condition": best["weather"][0]["description"],
                    "weather_id": best["weather"][0]["id"],
                    "day": day_name,
                    "date": date,                       # YYYY-MM-DD in Greek time
                    "time": best["_dt_greek"].strftime("%Y-%m-%d %H:%M:%S")   # Greek local time
                })
    
        return {
            "current": current_data,
            "next_3hour": next_3hour,
            "next_daily": next_daily
        }


 

    def yahoo_fetch_stocks(self, symbols):
        """
        Fetch real‑time data for a list of stock symbols from Yahoo Finance (RapidAPI).
        Returns the same dictionary format as the original fetch_stocks method.
        """
        # Build the comma‑separated symbol string
        symbols_str = ",".join(symbols)
        print("yahoo key: ",self.yahoo_api_token)

        # Yahoo Finance API endpoint and headers
        url = "https://apidojo-yahoo-finance-v1.p.rapidapi.com/market/v2/get-quotes"
        headers = {
            "x-rapidapi-host": "apidojo-yahoo-finance-v1.p.rapidapi.com",
            "x-rapidapi-key": self.yahoo_api_token   # renamed from eodhd_api_token
        }
        params = {
            "region": "GR",      # Greek market
            "lang": "en",
            "symbols": symbols_str
        }

        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code != 200:
                print("Stock fetch error: HTTP", response.status_code)
                response.close()
                return None

            data = response.json()
            response.close()

            # Extract the quotes array
            if "quoteResponse" not in data or "result" not in data["quoteResponse"]:
                return None
            quotes = data["quoteResponse"]["result"]

        except Exception as e:
            print("Stock fetch failed:", e)
            return None

        # Build result dictionary in exactly the same format as the original method
        result = {
            "codes": [],
            "timestamps": [],
            "gmtoffsets": [],
            "opens": [],
            "highs": [],
            "lows": [],
            "closes": [],
            "volumes": [],
            "previousCloses": [],
            "changes": [],
            "change_ps": []
        }

        for quote in quotes:
            result["codes"].append(quote.get("symbol"))
            # regularMarketTime is already in seconds
            result["timestamps"].append(quote.get("regularMarketTime"))
            # gmtOffSetMilliseconds is in milliseconds; original used seconds.
            # If your main code expects seconds, you can divide by 1000 here.
            result["gmtoffsets"].append(quote.get("gmtOffSetMilliseconds"))
            result["opens"].append(quote.get("regularMarketOpen"))
            result["highs"].append(quote.get("regularMarketDayHigh"))
            result["lows"].append(quote.get("regularMarketDayLow"))
            result["closes"].append(quote.get("regularMarketPrice"))
            result["volumes"].append(quote.get("regularMarketVolume"))
            result["previousCloses"].append(quote.get("regularMarketPreviousClose"))
            result["changes"].append(quote.get("regularMarketChange"))
            result["change_ps"].append(quote.get("regularMarketChangePercent"))

        return result




    # ---------- Stocks ----------
    def fetch_stocks(self, symbols):
        """
        Fetch real‑time data for a list of stock symbols from EOD Historical Data.
        :param symbols: list of strings, e.g. ['OPAP.AT', 'ETE.AT']
        Returns a dictionary with lists for each field:
            codes, timestamps, gmtoffsets, opens, highs, lows,
            closes, volumes, previousCloses, changes, change_ps
        Returns None if the request fails.
        """
        # Build the URL with properly encoded commas
        symbols_str = ",".join(symbols).replace(",", "%2C")
        url = (
            "https://eodhd.com/api/real-time/AMZN"   # base endpoint (AMZN is just placeholder)
            "?api_token={}&s={}&fmt=json".format(self.eodhd_api_token, symbols_str)
        )
        try:
            response = requests.get(url)
            if response.status_code != 200:
                print("Stock fetch error: HTTP", response.status_code)
                response.close()
                return None
            data = response.json()
            response.close()
        except Exception as e:
            print("Stock fetch failed:", e)
            return None

        # Build result dictionary
        result = {
            "codes": [],
            "timestamps": [],
            "gmtoffsets": [],
            "opens": [],
            "highs": [],
            "lows": [],
            "closes": [],
            "volumes": [],
            "previousCloses": [],
            "changes": [],
            "change_ps": []
        }
        for item in data:
            result["codes"].append(item.get("code"))
            result["timestamps"].append(item.get("timestamp"))
            result["gmtoffsets"].append(item.get("gmtoffset"))
            result["opens"].append(item.get("open"))
            result["highs"].append(item.get("high"))
            result["lows"].append(item.get("low"))
            result["closes"].append(item.get("close"))
            result["volumes"].append(item.get("volume"))
            result["previousCloses"].append(item.get("previousClose"))
            result["changes"].append(item.get("change"))
            result["change_ps"].append(item.get("change_p"))
        return result


class FontManager:
    """
    Provides four font sizes (tiny, small, medium, large) for PIL.
    Attempts to load a TrueType font; falls back to default bitmap font.
    """

    # Common font paths (Linux, macOS, Windows)
    DEFAULT_FONT_PATHS = [
        "/home/panos/epaper/fonts/NunitoSans.ttf",
        "/home/panos/epaper/fonts/Caveat.ttf",
        "/home/panos/epaper/fonts/NunitoSans-Italic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:\\Windows\\Fonts\\arial.ttf"
    ]

    def __init__(self, font_path=None, size_tiny=12, size_small=20, size_medium=32, size_large=40):
        """
        :param font_path:   Path to a TrueType font file. If None, search common locations.
        :param size_tiny:   Point size for the tiniest font.
        :param size_small:  Point size for the small font.
        :param size_medium: Point size for the medium font.
        :param size_large:  Point size for the large font.
        """
        self.size_tiny = size_tiny
        self.size_small = size_small
        self.size_medium = size_medium
        self.size_large = size_large

        if font_path is None:
            font_path = self._find_font()
            if font_path is None:
                print("FontManager: No TrueType font found. Using default bitmap font.")
                self._use_default_fonts()
                return
        else:
            if not os.path.exists(font_path):
                raise FileNotFoundError(f"Font not found: {font_path}")

        try:
            self.font_tiny = ImageFont.truetype(font_path, size_tiny)
            self.font_small = ImageFont.truetype(font_path, size_small)
            self.font_medium = ImageFont.truetype(font_path, size_medium)
            self.font_large = ImageFont.truetype(font_path, size_large)
            print(f"FontManager: Loaded {font_path} with sizes {size_tiny}, {size_small}, {size_medium}, {size_large}")
        except Exception as e:
            print(f"FontManager: Error loading font: {e}. Falling back to default.")
            self._use_default_fonts()

    def _find_font(self):
        """Search DEFAULT_FONT_PATHS for an existing font file."""
        for path in self.DEFAULT_FONT_PATHS:
            if os.path.exists(path):
                return path
        return None

    def _use_default_fonts(self):
        """Fallback: use PIL's default bitmap font (all sizes same)."""
        default = ImageFont.load_default()
        self.font_tiny = default
        self.font_small = default
        self.font_medium = default
        self.font_large = default

    def get_tiny(self):
        return self.font_tiny

    def get_small(self):
        return self.font_small

    def get_medium(self):
        return self.font_medium

    def get_large(self):
        return self.font_large

    def get_text_size(self, text, font):
        """
        Return (width, height) of text when drawn with given font.
        Works with both TrueType and default bitmap fonts.
        """
        if hasattr(font, "getbbox"):      # Pillow >= 8.0.0
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0], bbox[3] - bbox[1]
        else:
            return font.getsize(text)     # older method
            





import math
import os
from PIL import Image, ImageDraw, ImageFont

class EPDDrawing:
    """
    Helper class for drawing on an e‑Paper image.
    Supports pasting pre‑made PNG icons with transparency.
    """
    def __init__(self, image, icon_folder="/home/pi/icons"):
        """
        :param image:       PIL Image object (your canvas)
        :param icon_folder: path to folder containing icon PNGs
        """
        self.image = image
        self.draw = ImageDraw.Draw(image)
        self.width = image.width
        self.height = image.height
        self.icon_folder = icon_folder
        self.icons = {}          # cache for loaded icons

    # ------------------------------------------------------------------
    # Icon loading and pasting helpers
    # ------------------------------------------------------------------
    def _load_icon(self, name):
        """Load a PNG icon, composite onto white, convert to 1‑bit (black on white)."""
        if name not in self.icons:
            path = os.path.join(self.icon_folder, f"{name}.png")
            try:
                # Open as RGBA to preserve transparency
                icon = Image.open(path).convert('RGBA')
                # Create a white background image of the same size
                white_bg = Image.new('RGBA', icon.size, (255, 255, 255, 255))
                # Composite the icon onto the white background, using its alpha channel as mask
                composite = Image.alpha_composite(white_bg, icon)
                # Convert to grayscale then to 1‑bit with a threshold
                # This makes all non‑white parts black (0) and white parts white (1)
                composite = composite.convert('L')
                composite = composite.point(lambda p: 0 if p < 128 else 255, mode='1')
                self.icons[name] = composite
            except Exception as e:
                print(f"Error loading icon {name}: {e}")
                # Return a blank white square as fallback
                self.icons[name] = Image.new('1', (100, 100), 1)
        return self.icons[name]

    def paste_icon(self, name, x0, y0, x1, y1, scale=0.7, vertical_offset=0):
        """
        Paste an icon scaled by `scale`, centered horizontally, and shifted vertically
        by `vertical_offset` pixels (negative = up, positive = down).
        """
        icon = self._load_icon(name)
        cell_w = x1 - x0
        cell_h = y1 - y0
        target_w = int(cell_w * scale)
        target_h = int(cell_h * scale)
        resized = icon.resize((target_w, target_h), Image.Resampling.LANCZOS)
        paste_x = x0 + (cell_w - target_w) // 2
        paste_y = y0 + (cell_h - target_h) // 2 + vertical_offset
        self.image.paste(resized, (paste_x, paste_y))

    # ------------------------------------------------------------------
    # Grid drawing
    # ------------------------------------------------------------------
    def draw_grid(self, rows=3, cols=3, color=0, line_width=1, include_outer_border=True):
        self.rows = rows
        self.cols = cols
        self.cell_w = self.width // cols
        self.cell_h = self.height // rows

        if include_outer_border:
            self.draw.rectangle([(0, 0), (self.width-1, self.height-1)],
                                outline=color, width=line_width)

        for i in range(1, cols):
            x = round(i * self.width / cols)
            self.draw.line([(x, 0), (x, self.height-1)], fill=color, width=line_width)

        for i in range(1, rows):
            y = round(i * self.height / rows)
            self.draw.line([(0, y), (self.width-1, y)], fill=color, width=line_width)

    # ------------------------------------------------------------------
    # Weather icon drawing (using PNGs)
    # ------------------------------------------------------------------
    def draw_weather_icon_in_cell(self, row, col, weather_data, rows=None, cols=None,
                                  scale=0.7, vertical_offset=0):
        """Place a weather icon in the specified grid cell, scaled and centered with optional vertical shift."""
        #link to weather images https://github.com/breakstring/WeatherIcons/tree/master
        if rows is not None and cols is not None:
            cell_w = self.width // cols
            cell_h = self.height // rows
        elif hasattr(self, 'cell_w'):
            cell_w = self.cell_w
            cell_h = self.cell_h
        else:
            raise ValueError("Grid not drawn yet – call draw_grid() or provide rows/cols")

        x0 = col * cell_w
        y0 = row * cell_h
        x1 = x0 + cell_w
        y1 = y0 + cell_h
        self._draw_weather_icon(x0, y0, x1, y1, weather_data, scale, vertical_offset)

    def _draw_weather_icon(self, x0, y0, x1, y1, weather_data, scale, vertical_offset):
        """
        Draw a weather icon based on the weather_id and the current local time.
        For clear (800) and partly‑cloudy (801, 802) conditions, the night version
        is used if the current hour is between 20:00 and 07:59.
        """
        cond = weather_data["condition"].lower()
        rain = weather_data["rain"]
        snow = weather_data["snow"]
        weather_icon = weather_data["weather_icon"]
        weather_id = weather_data["weather_id"]
    
        # Determine if it's night based on current local time
        current_hour = datetime.datetime.now().hour
        is_night = (current_hour >= 20 or current_hour < 8)
    
        # --- Thunderstorm (200-232) ---
        if 200 <= weather_id < 300:
            self.paste_icon("thunder", x0, y0, x1, y1, scale, vertical_offset)
    
        # --- Drizzle (300-321) ---
        elif 300 <= weather_id < 400:
            self.paste_icon("drizzle", x0, y0, x1, y1, scale, vertical_offset)
    
        # --- Rain (500-531) ---
        elif 500 <= weather_id < 600:
            if weather_id in [500, 501]:
                self.paste_icon("light_rain", x0, y0, x1, y1, scale, vertical_offset)
            if weather_id in [502, 504]:
                self.paste_icon("heavy_rain", x0, y0, x1, y1, scale, vertical_offset)
            if weather_id in [511, 531]:
                self.paste_icon("showers", x0, y0, x1, y1, scale, vertical_offset)
    
        # --- Snow (600-622) ---
        elif 600 <= weather_id < 700:
            if weather_id in [600, 601]:
                self.paste_icon("light_snow", x0, y0, x1, y1, scale, vertical_offset)
            if weather_id in [602, 616]:
                self.paste_icon("heavy_snow", x0, y0, x1, y1, scale, vertical_offset)
            if weather_id in [617, 699]:
                self.paste_icon("showers_snow", x0, y0, x1, y1, scale, vertical_offset)
    
        # --- Atmosphere (700-781) e.g., fog, mist, haze ---
        elif 700 <= weather_id < 800:
            self.paste_icon("fog", x0, y0, x1, y1, scale, vertical_offset)
    
        # --- Clear (800) ---
        elif weather_id == 800:
            icon_name = "night_clear" if is_night else "clear"
            self.paste_icon(icon_name, x0, y0, x1, y1, scale, vertical_offset)
    
        # --- Clouds (801-804) ---
        elif 801 <= weather_id < 900:
            if weather_id in [801, 802]:
                icon_name = "night_partly-cloudy" if is_night else "partly-cloudy"
                self.paste_icon(icon_name, x0, y0, x1, y1, scale, vertical_offset)
            else:  # 803, 804
                self.paste_icon("cloudy", x0, y0, x1, y1, scale, vertical_offset)
    
        # --- Fallback for any other codes ---
        else:
            self.paste_icon("clear", x0, y0, x1, y1, scale, vertical_offset)
        
        
        

    def draw_wind_compass_in_cell(self, row, col, wind_deg, wind_speed=None,
                                  wind_unit="km/h", rows=None, cols=None,
                                  compass_scale=0.7, vertical_offset=0,
                                  horizontal_offset=0, tiny_font=None, large_font=None):
        """
        Draw a wind compass (double circle + arrow) in the specified grid cell.
        - row, col: cell indices
        - wind_deg: meteorological wind direction (0° = North, clockwise)
        - wind_speed: optional speed to display in the centre
        - wind_unit: unit label to display below the speed (default "km/h")
        - rows, cols: grid dimensions (if not already known)
        - compass_scale: size of compass relative to cell (0.0-1.0)
        - vertical_offset: shift everything up/down (pixels, negative = up)
        - horizontal_offset: shift everything left/right (negative = left)
        - tiny_font: PIL ImageFont for cardinal labels
        - large_font: PIL ImageFont for speed and unit text (centred)
        """
        if rows is not None and cols is not None:
            cell_w = self.width // cols
            cell_h = self.height // rows
        elif hasattr(self, 'cell_w'):
            cell_w = self.cell_w
            cell_h = self.cell_h
        else:
            raise ValueError("Grid not drawn yet – call draw_grid() or provide rows/cols")

        x0 = col * cell_w
        y0 = row * cell_h
        x1 = x0 + cell_w
        y1 = y0 + cell_h

        cx = (x0 + x1) // 2 + horizontal_offset
        cy = (y0 + y1) // 2 + vertical_offset

        # Compass radius (outer circle)
        radius = int(min(cell_w, cell_h) * compass_scale / 2)

        # Draw outer circle (thicker)
        self.draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                          outline=0, width=3)

        # Inner circle, closer to outer (80% of radius) and thicker
        inner_r = int(radius * 0.8)
        self.draw.ellipse([cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
                          outline=0, width=2)

        # Convert wind direction to arrow angle
        angle_rad = math.radians(90 - wind_deg)

        # Arrow tip on outer circle
        tip_x = cx + radius * math.cos(angle_rad)
        tip_y = cy - radius * math.sin(angle_rad)

        # Arrow start on inner circle edge
        start_x = cx + inner_r * math.cos(angle_rad)
        start_y = cy - inner_r * math.sin(angle_rad)

        # Draw arrow shaft (only from inner to outer)
        self.draw.line([(start_x, start_y), (tip_x, tip_y)], fill=0, width=2)

        # Draw larger arrowhead
        head_size = radius // 4
        perp_rad = angle_rad + math.pi/2
        left_x = tip_x - head_size * math.cos(angle_rad) + head_size * math.cos(perp_rad)
        left_y = tip_y + head_size * math.sin(angle_rad) - head_size * math.sin(perp_rad)
        right_x = tip_x - head_size * math.cos(angle_rad) - head_size * math.cos(perp_rad)
        right_y = tip_y + head_size * math.sin(angle_rad) + head_size * math.sin(perp_rad)
        self.draw.polygon([(tip_x, tip_y), (left_x, left_y), (right_x, right_y)],
                          fill=0, outline=None)

        # --- Cardinal and intercardinal labels ---
        margin = 12
        R = radius + margin

        dir_labels = [
            (0, 'N'), (90, 'E'), (180, 'S'), (270, 'W'),
            (45, 'NE'), (135, 'SE'), (225, 'SW'), (315, 'NW')
        ]

        for d, label in dir_labels:
            angle_rad = math.radians(90 - d)
            lx = cx + R * math.cos(angle_rad)
            ly = cy - R * math.sin(angle_rad)
            if tiny_font:
                self.draw.text((lx, ly), label, fill=0, font=tiny_font, anchor="mm")
            else:
                try:
                    self.draw.text((lx, ly), label, fill=0, anchor="mm")
                except TypeError:
                    bbox = self.draw.textbbox((0, 0), label)
                    w = bbox[2] - bbox[0]
                    h = bbox[3] - bbox[1]
                    self.draw.text((lx - w//2, ly - h//2), label, fill=0)

        # --- Wind speed and unit in the centre (stacked vertically) ---
        if wind_speed is not None:
            speed_text = f"{wind_speed:.1f}"
            unit_text = wind_unit

            # Use large_font if provided, otherwise fall back to tiny_font or default
            font = large_font or tiny_font
            if font:
                # Get text heights to centre the block vertically
                try:
                    bbox_s = font.getbbox(speed_text)
                    bbox_u = font.getbbox(unit_text)
                    h_s = bbox_s[3] - bbox_s[1]
                    h_u = bbox_u[3] - bbox_u[1]
                except AttributeError:
                    # Older Pillow fallback
                    bbox_s = self.draw.textbbox((0, 0), speed_text, font=font)
                    bbox_u = self.draw.textbbox((0, 0), unit_text, font=font)
                    h_s = bbox_s[3] - bbox_s[1]
                    h_u = bbox_u[3] - bbox_u[1]

                spacing = 5  # pixels between lines
                total_height = h_s + spacing + h_u
                #y_start = cy - total_height // 2
                y_start = cy - total_height // 2 + 10   # +10 pixels down (adjust as needed)


                self.draw.text((cx, y_start), speed_text, fill=0, font=font, anchor="mm")
                self.draw.text((cx, y_start + h_s + spacing), unit_text, fill=0, font=font, anchor="mm")
            else:
                # No font provided – use default with approximate centering
                self.draw.text((cx, cy - 10), speed_text, fill=0, anchor="mm")
                self.draw.text((cx, cy + 10), unit_text, fill=0, anchor="mm")

    def draw_day_night_in_cell(self, row, col, sunrise_ts, sunset_ts, current_ts,
                               timezone_offset, rows=None, cols=None,
                               circle_scale=0.6, vertical_offset=0,
                               small_font=None, tiny_font=None, large_font=None,
                               col_offset=15):
        """
        Draw a day/night cycle visualization in the specified grid cell.
        - sunrise_ts, sunset_ts: Unix timestamps (UTC) for sunrise/sunset
        - current_ts: Unix timestamp (UTC) for current time
        - timezone_offset: local timezone offset in hours (e.g., 2 or 3 for Greece)
        - rows, cols: grid dimensions
        - circle_scale: size of circle relative to cell
        - vertical_offset: shift up/down (negative = up)
        - small_font, tiny_font: PIL fonts for text
        - col_offset: horizontal distance (pixels) from cell center to each column's edge
        """
        if rows is not None and cols is not None:
            cell_w = self.width // cols
            cell_h = self.height // rows
        elif hasattr(self, 'cell_w'):
            cell_w = self.cell_w
            cell_h = self.cell_h
        else:
            raise ValueError("Grid not drawn yet – call draw_grid() or provide rows/cols")

        x0 = col * cell_w
        y0 = row * cell_h
        x1 = x0 + cell_w
        y1 = y0 + cell_h

        cx = (x0 + x1) // 2
        cy = (y0 + y1) // 2 + vertical_offset
        radius = int(min(cell_w, cell_h) * circle_scale / 2)

        # Local time (add offset)
        offset_seconds = timezone_offset * 3600
        sunrise_local = sunrise_ts + offset_seconds
        sunset_local = sunset_ts + offset_seconds
        current_local = current_ts + offset_seconds

        sunrise_t = time.gmtime(sunrise_local)
        sunset_t = time.gmtime(sunset_local)
        current_t = time.gmtime(current_local)

        def seconds_since_midnight(t):
            return t[3] * 3600 + t[4] * 60 + t[5]

        sunrise_sec = seconds_since_midnight(sunrise_t)
        sunset_sec = seconds_since_midnight(sunset_t)
        current_sec = seconds_since_midnight(current_t)

        if sunset_sec > sunrise_sec:
            day_sec = sunset_sec - sunrise_sec
        else:
            day_sec = (24*3600 - sunrise_sec) + sunset_sec

        night_sec = 24*3600 - day_sec

        # --- ANGLE MAPPING: 0° = right, but we want left (midnight) at 180° ---
        sec_to_deg = 360 / (24*3600)          # degrees per second
        def sec_to_angle(sec):
            # Returns angle in standard math coordinates (0°=right, CCW)
            # such that midnight (0 sec) → 180° (left), sunrise → 90° (top), etc.
            return (180 - sec * sec_to_deg) % 360

        sunrise_angle = sec_to_angle(sunrise_sec)
        sunset_angle = sec_to_angle(sunset_sec)
        current_angle = sec_to_angle(current_sec)

        # Convert to Pillow's angle system (0° at right, positive clockwise)
        def to_pillow_angle(phi):
            return (360 - phi) % 360

        sunset_pillow = to_pillow_angle(sunset_angle)
        sunrise_pillow = to_pillow_angle(sunrise_angle)

        # --- Fill entire circle with white (day background) ---
        self.draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                          fill='white', outline=None)

        # Draw night sector (from sunset to sunrise, through midnight/left)
        if sunset_pillow <= sunrise_pillow:
            start = sunset_pillow
            end = sunrise_pillow
        else:
            start = sunset_pillow
            end = sunrise_pillow + 360
        self.draw.pieslice([cx - radius, cy - radius, cx + radius, cy + radius],
                           start, end, fill='black', outline=None)

        # Outer circle outline
        self.draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                          outline=0, width=2)

        # Ticks at sunrise and sunset
        tick_len = radius // 8
        for angle in [sunrise_angle, sunset_angle]:
            x = cx + radius * math.cos(math.radians(angle))
            y = cy - radius * math.sin(math.radians(angle))
            perp = math.radians(angle + 90)
            dx = tick_len * math.cos(perp)
            dy = -tick_len * math.sin(perp)
            self.draw.line([(x - dx, y - dy), (x + dx, y + dy)], fill=0, width=1)

        # Determine if current time is in night (black background)
        if sunset_angle <= sunrise_angle:
            is_night = sunset_angle <= current_angle <= sunrise_angle
        else:
            is_night = current_angle >= sunset_angle or current_angle <= sunrise_angle

        # --- Current time dot: larger and with contrasting outline ---
        dot_x = cx + radius * 0.8 * math.cos(math.radians(current_angle))
        dot_y = cy - radius * 0.8 * math.sin(math.radians(current_angle))
        dot_r = max(4, radius // 8)                 # larger dot
        dot_fill = 'white' if is_night else 'black'
        dot_outline = 'black' if is_night else 'white'   # opposite for visibility
        self.draw.ellipse([dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r],
                          fill=dot_fill, outline=dot_outline, width=1)

        # --- Text (unchanged) ---
        text_y_start = cy + radius + 10
        line_height = 20

        date_str = f"{current_t[2]:02d}/{current_t[1]:02d}/{current_t[0]}"
        time_str = f"{current_t[3]:02d}:{current_t[4]:02d}"
        sunrise_str = f"SR: {sunrise_t[3]:02d}:{sunrise_t[4]:02d}"
        sunset_str = f"SS: {sunset_t[3]:02d}:{sunset_t[4]:02d}"
        day_h = day_sec // 3600
        day_m = (day_sec % 3600) // 60
        day_len_str = f"Day: {day_h:02d}:{day_m:02d}"

        font_t = tiny_font if tiny_font else None
        font_m = small_font if small_font else None

        x_left = cx - col_offset
        x_right = cx + col_offset

        y = text_y_start
        self._draw_text_aligned(sunrise_str, x_left, y, font_t, align='right')
        self._draw_text_aligned(sunset_str, x_right, y, font_t, align='left')
        y += line_height
        self._draw_text_aligned(day_len_str, x_left, y, font_t, align='right')
        y += line_height

        x_left = cx - col_offset - 90
        x_right = cx + col_offset + 84
        self._draw_text_aligned(date_str, x_left, y+5, font_m, align='left')
        self._draw_text_aligned(time_str, x_right, y+10, font_m, align='right')


    def _draw_text_aligned(self, text, x, y, font=None, align='left'):
        """Helper to draw text at (x,y) with given alignment."""
        try:
            if align == 'left':
                self.draw.text((x, y), text, fill=0, font=font, anchor='lt')
            elif align == 'right':
                self.draw.text((x, y), text, fill=0, font=font, anchor='rt')
            else:  # center
                self.draw.text((x, y), text, fill=0, font=font, anchor='mt')
        except TypeError:
            # Fallback for older Pillow
            if font:
                bbox = font.getbbox(text)
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
            else:
                bbox = self.draw.textbbox((0, 0), text)
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
            if align == 'left':
                self.draw.text((x, y), text, fill=0, font=font)
            elif align == 'right':
                self.draw.text((x - w, y), text, fill=0, font=font)
            else:  # center
                self.draw.text((x - w//2, y - h//2), text, fill=0, font=font)
                
                
                
    def draw_stock_in_cell(self, row, col, symbol, change, change_pct, stock_close,
                           rows=None, cols=None, font=None):
        """
        Draw stock information in a grid cell:
        - symbol at the top centre
        - percentage (with %) in the middle centre
        - closing price (left) and absolute change (right) at the bottom
        - a small square at the top‑right corner containing:
            * ▲ (up arrow)  if change_pct > 0
            * ▼ (down arrow) if change_pct < 0
            * – (dash)       if change_pct == 0
        """
        # Get cell dimensions
        if rows is not None and cols is not None:
            cell_w = self.width // cols
            cell_h = self.height // rows
        elif hasattr(self, 'cell_w'):
            cell_w = self.cell_w
            cell_h = self.cell_h
        else:
            raise ValueError("Grid not drawn yet – call draw_grid() or provide rows/cols")

        x0 = col * cell_w
        y0 = row * cell_h
        x1 = x0 + cell_w
        y1 = y0 + cell_h

        # Center of the cell
        cx = (x0 + x1) // 2
        cy = (y0 + y1) // 2

        # Determine font and line height
        if font is None:
            font = getattr(self, 'tiny_font', None)   # fallback
        if font:
            bbox = font.getbbox('Ay')
            line_height = (bbox[3] - bbox[1]) + 6     # height + padding
        else:
            line_height = 20

        # Convert values to floats
        try:
            change_val = float(change)
        except (TypeError, ValueError):
            change_val = 0.0
        try:
            pct_val = float(change_pct)
        except (TypeError, ValueError):
            pct_val = 0.0
        try:
            close_val = float(stock_close)
        except (TypeError, ValueError):
            close_val = 0.0

        # Format strings
        symbol_str = str(symbol)
        pct_str    = f"{pct_val:+.2f}%"
        close_str  = f"{close_val:.2f}"          # closing price without sign
        change_str = f"{change_val:+.2f}"        # absolute change with sign

        # Vertical positions
        y_symbol = cy - line_height - 20
        y_mid    = cy - 10
        y_bottom = cy + line_height

        symbol_bottom_offset = int(cell_w * 0.15)        # adjust as needed
        left_symbol_x  = cx - symbol_bottom_offset

        # Draw symbol at top
        self._draw_centered_text(symbol_str, left_symbol_x, y_symbol, font, fill=0)

        # Draw percentage in middle
        self._draw_centered_text(pct_str, cx, y_mid, font, fill=0)

        # Draw bottom line: closing price on left, change on right
        bottom_offset = int(cell_w * 0.27)        # adjust as needed
        left_x  = cx - bottom_offset
        right_x = cx + bottom_offset

        self._draw_centered_text(close_str, left_x, y_bottom, font, fill=0)
        self._draw_centered_text(change_str, right_x, y_bottom, font, fill=0)

        # --- Arrow / dash in top‑right corner (unchanged) ---
        margin = 9
        square_size = 40
        if cell_w > square_size + 2*margin and cell_h > square_size + 2*margin:
            square_x0 = x1 - margin - square_size
            square_y0 = y0 + margin
            square_x1 = x1 - margin
            square_y1 = y0 + margin + square_size
            self.draw.rectangle([square_x0, square_y0, square_x1, square_y1], outline=0, width=1)

            arrow_cx = (square_x0 + square_x1) // 2
            arrow_cy = (square_y0 + square_y1) // 2
            arrow_size = int(square_size * 0.6)
            arrow_width = int(arrow_size * 0.8)

            if pct_val > 0:
                points = [
                    (arrow_cx, arrow_cy - arrow_size//2),
                    (arrow_cx - arrow_width//2, arrow_cy + arrow_size//2),
                    (arrow_cx + arrow_width//2, arrow_cy + arrow_size//2)
                ]
                self.draw.polygon(points, fill=0)
            elif pct_val < 0:
                points = [
                    (arrow_cx, arrow_cy + arrow_size//2),
                    (arrow_cx - arrow_width//2, arrow_cy - arrow_size//2),
                    (arrow_cx + arrow_width//2, arrow_cy - arrow_size//2)
                ]
                self.draw.polygon(points, fill=0)
            else:
                dash_length = arrow_width
                self.draw.line([
                    (arrow_cx - dash_length//2, arrow_cy),
                    (arrow_cx + dash_length//2, arrow_cy)
                ], fill=0, width=2)


    def _draw_centered_text(self, text, cx, y, font=None, fill=0):
        """Draw text centered horizontally at (cx, y)."""
        try:
            # Modern Pillow (>=8.0.0) with anchor
            self.draw.text((cx, y), text, fill=fill, font=font, anchor="mt")
        except TypeError:
            # Fallback for older versions
            if font:
                bbox = font.getbbox(text)
                w = bbox[2] - bbox[0]
            else:
                bbox = self.draw.textbbox((0, 0), text)
                w = bbox[2] - bbox[0]
            self.draw.text((cx - w//2, y - 5), text, fill=fill, font=font)
            
            
            



    def draw_humidity_in_cell(self, row, col, humidity, rows=None, cols=None,
                          icon_scale=0.8, vertical_offset=0, font=None,
                          icon_margin=10, text_gap=10):
        """
        Draw a humidity drop icon (from icons folder) on the left, and the humidity
        percentage as black text to its right.
        - icon_scale: size of the icon relative to the cell (0.0‑1.0)
        - vertical_offset: shift icon/text up/down (negative = up)
        - font: font for the percentage text
        - icon_margin: pixels from left edge of cell to icon
        - text_gap: pixels between icon and text
        """
        # Get cell dimensions
        if rows is not None and cols is not None:
            cell_w = self.width // cols
            cell_h = self.height // rows
        elif hasattr(self, 'cell_w'):
            cell_w = self.cell_w
            cell_h = self.cell_h
        else:
            raise ValueError("Grid not drawn yet – call draw_grid() or provide rows/cols")

        x0 = col * cell_w
        y0 = row * cell_h
        x1 = x0 + cell_w
        y1 = y0 + cell_h

        # Desired icon size (square)
        icon_size = int(min(cell_w, cell_h) * icon_scale)

        # Icon rectangle – left‑aligned with margin, vertically centered + offset
        icon_x0 = x0 + icon_margin
        icon_y0 = y0 + (cell_h - icon_size) // 2 + vertical_offset
        icon_x1 = icon_x0 + icon_size
        icon_y1 = icon_y0 + icon_size

        # Clamp to cell bounds (optional, prevents drawing outside)
        if icon_x1 > x1:
            icon_x1 = x1
            icon_x0 = x1 - icon_size
        if icon_y1 > y1:
            icon_y1 = y1
            icon_y0 = y1 - icon_size
        if icon_y0 < y0:
            icon_y0 = y0
            icon_y1 = y0 + icon_size

        # Paste the icon – we pass the exact rectangle and scale=1.0 so it fills it
        self.paste_icon("humidity", icon_x0, icon_y0, icon_x1, icon_y1,
                        scale=1.0, vertical_offset=0)

        # Format humidity text
        try:
            hum_val = int(round(float(humidity)))
        except (TypeError, ValueError):
            hum_val = 0
        text = f"{hum_val}%"

        if font is None:
            font = getattr(self, 'tiny_font', None)

        # Text position: to the right of the icon, vertically centered
        text_x = icon_x1 + text_gap
        text_cy = (y0 + y1) // 2 + vertical_offset

        # Draw text left‑aligned at (text_x, text_cy)
        self._draw_text_aligned(text, text_x, text_cy, font, align='left')
        
        
        
        
        
        
        
                
    def draw_pressure_in_cell(self, row, col, pressure, rows=None, cols=None,
                              icon_scale=0.8, vertical_offset=0, font=None,
                              unit_font=None, icon_margin=10, text_gap=10):
        """
        Draw a pressure icon on the left, and the pressure value with "hPa" below it on the right.
        - pressure: numeric value in hPa (e.g. 1013)
        - icon_scale: size of the icon relative to the cell (0.0‑1.0)
        - vertical_offset: shift icon/text up/down (negative = up)
        - font: font for the pressure value (larger)
        - unit_font: font for the "hPa" unit (if None, uses the same as font but smaller line height)
        - icon_margin: pixels from left edge of cell to icon
        - text_gap: pixels between icon and text
        """
        # Get cell dimensions
        if rows is not None and cols is not None:
            cell_w = self.width // cols
            cell_h = self.height // rows
        elif hasattr(self, 'cell_w'):
            cell_w = self.cell_w
            cell_h = self.cell_h
        else:
            raise ValueError("Grid not drawn yet – call draw_grid() or provide rows/cols")

        x0 = col * cell_w
        y0 = row * cell_h
        x1 = x0 + cell_w
        y1 = y0 + cell_h

        # Desired icon size (square)
        icon_size = int(min(cell_w, cell_h) * icon_scale)

        # Icon rectangle – left‑aligned with margin, vertically centered + offset
        icon_x0 = x0 + icon_margin
        icon_y0 = y0 + (cell_h - icon_size) // 2 + vertical_offset
        icon_x1 = icon_x0 + icon_size
        icon_y1 = icon_y0 + icon_size

        # Clamp to cell bounds
        if icon_x1 > x1:
            icon_x1 = x1
            icon_x0 = x1 - icon_size
        if icon_y1 > y1:
            icon_y1 = y1
            icon_y0 = y1 - icon_size
        if icon_y0 < y0:
            icon_y0 = y0
            icon_y1 = y0 + icon_size

        # Paste the pressure icon
        self.paste_icon("pressure", icon_x0, icon_y0, icon_x1, icon_y1,
                        scale=1.0, vertical_offset=0)

        # Format pressure value
        try:
            press_val = int(round(float(pressure)))
        except (TypeError, ValueError):
            press_val = 0
        value_text = f"{press_val}"

        # Determine fonts
        if font is None:
            font = getattr(self, 'tiny_font', None)
        if unit_font is None:
            unit_font = font   # use same font by default

        # Get line heights
        if font:
            bbox = font.getbbox('Ay')
            line_height_val = (bbox[3] - bbox[1])
        else:
            line_height_val = 20
        if unit_font:
            bbox_u = unit_font.getbbox('Ay')
            line_height_unit = (bbox_u[3] - bbox_u[1])
        else:
            line_height_unit = 16

        # Total height of two lines (approximate, with a little spacing)
        total_text_height = line_height_val + line_height_unit + 4   # 4px gap

        # Vertical center of the cell (with offset)
        cy = (y0 + y1) // 2 + vertical_offset

        # Starting y so that the midpoint of the two lines aligns with cy
        y_start = cy - total_text_height // 2

        # Text x position (left edge after icon and gap)
        text_x = icon_x1 + text_gap

        # Draw value (larger font)
        self._draw_text_aligned(value_text, text_x, y_start, font, align='left')

        # Draw "hPa" below with a small gap
        y_unit = y_start + line_height_val + 4
        self._draw_text_aligned("hPa", text_x, y_unit, unit_font, align='left')
        
        print(f"DEBUG pressure: icon_x1={icon_x1}, text_gap={text_gap}, text_x={text_x}")

        
        
        
        
        
        
        
        
            
    def draw_temperature_in_cell(self, row, col, temperature, rows=None, cols=None,
                                 icon_scale=0.8, vertical_offset=0, font=None,
                                 unit_font=None, icon_margin=10, text_gap=15):
        """
        Draw a temperature icon on the left, and the temperature value with "°C" below it on the right.
        - temperature: numeric value in Celsius (float or int)
        - icon_scale: size of the icon relative to the cell (0.0‑1.0)
        - vertical_offset: shift icon/text up/down (negative = up)
        - font: font for the temperature value (larger)
        - unit_font: font for the "°C" unit (if None, uses the same as font but smaller line height)
        - icon_margin: pixels from left edge of cell to icon
        - text_gap: pixels between icon and text
        """
        # Get cell dimensions
        if rows is not None and cols is not None:
            cell_w = self.width // cols
            cell_h = self.height // rows
        elif hasattr(self, 'cell_w'):
            cell_w = self.cell_w
            cell_h = self.cell_h
        else:
            raise ValueError("Grid not drawn yet – call draw_grid() or provide rows/cols")

        x0 = col * cell_w
        y0 = row * cell_h
        x1 = x0 + cell_w
        y1 = y0 + cell_h

        # Desired icon size (square)
        icon_size = int(min(cell_w, cell_h) * icon_scale)

        # Icon rectangle – left‑aligned with margin, vertically centered + offset
        icon_x0 = x0 + icon_margin
        icon_y0 = y0 + (cell_h - icon_size) // 2 + vertical_offset
        icon_x1 = icon_x0 + icon_size
        icon_y1 = icon_y0 + icon_size

        # Clamp to cell bounds
        if icon_x1 > x1:
            icon_x1 = x1
            icon_x0 = x1 - icon_size
        if icon_y1 > y1:
            icon_y1 = y1
            icon_y0 = y1 - icon_size
        if icon_y0 < y0:
            icon_y0 = y0
            icon_y1 = y0 + icon_size

        # Paste the temperature icon (assumes "temp.png" in icon_folder)
        self.paste_icon("temp", icon_x0, icon_y0, icon_x1, icon_y1,
                        scale=1.0, vertical_offset=0)

        # Format temperature value
        try:
            #temp_val = int(round(float(temperature)))   # whole degrees
            temp_val = round(float(temperature), 1)   # for one decimal place
        except (TypeError, ValueError):
            temp_val = 0
        value_text = f"{temp_val}"

        # Determine fonts
        if font is None:
            font = getattr(self, 'tiny_font', None)
        if unit_font is None:
            unit_font = font   # use same font by default

        # Get line heights
        if font:
            bbox = font.getbbox('Ay')
            line_height_val = (bbox[3] - bbox[1])
        else:
            line_height_val = 20
        if unit_font:
            bbox_u = unit_font.getbbox('Ay')
            line_height_unit = (bbox_u[3] - bbox_u[1])
        else:
            line_height_unit = 16

        # Total height of two lines (with a little spacing)
        total_text_height = line_height_val + line_height_unit + 4   # 4px gap

        # Vertical center of the cell (with offset)
        cy = (y0 + y1) // 2 + vertical_offset

        # Starting y so that the midpoint of the two lines aligns with cy
        y_start = cy - total_text_height // 2

        # Text x position (left edge after icon and gap)
        text_x = icon_x1 + text_gap

        # Draw value (larger font)
        self._draw_text_aligned(value_text, text_x, y_start, font, align='left')

        # Draw "°C" below with a small gap
        y_unit = y_start + line_height_val + 4
        self._draw_text_aligned("°C", text_x, y_unit, unit_font, align='left')




    def _get_icon_name(self, weather_id, time_str):
        """
        Map OpenWeatherMap weather ID to icon filename (without .png).
        If time_str is given, use night versions for clear/partly‑cloudy
        when hour is >=20 or <8.
        """
        # Parse hour from the time string (supports "HH:MM", "HH:MM:SS", or full datetime)
        if time_str:
            try:
                # If time_str contains a space, assume it's "YYYY-MM-DD HH:MM:SS"
                if ' ' in time_str:
                    time_part = time_str.split()[1]
                else:
                    time_part = time_str
                hour = int(time_part.split(':')[0])
            except (ValueError, IndexError):
                hour = None  # fallback to day icon
        else:
            hour = None
    
        # Determine if it's night (20:00 - 07:59)
        is_night = hour is not None and (hour >= 20 or hour < 8)
    
        if 200 <= weather_id < 300:
            return "thunder"
        elif 300 <= weather_id < 400:
            return "drizzle"
        elif 500 <= weather_id < 600:
            if weather_id in (500, 501):
                return "light_rain"
            elif weather_id in (502, 504):
                return "heavy_rain"
            elif weather_id in (511, 531):
                return "showers"
            else:
                return "rain"
        elif 600 <= weather_id < 700:
            if weather_id in (600, 601):
                return "light_snow"
            elif weather_id in (602, 616):
                return "heavy_snow"
            elif weather_id in (617, 699):
                return "showers_snow"
            else:
                return "snow"
        elif 700 <= weather_id < 800:
            return "fog"
        elif weather_id == 800:
            return "night_clear" if is_night else "clear"
        elif 801 <= weather_id < 900:
            if weather_id in (801, 802):
                return "night_partly-cloudy" if is_night else "partly-cloudy"
            else:
                return "cloudy"
        else:
            return "clear"
            
        
        
        
      
    def draw_weather_forecast(self, forecast_data, split_x, fonts,
                              top_gap_ratio=0.1, bottom_gap_ratio=0.1,
                              margin=10, current_icon_size=60, forecast_icon_size=40,
                              gap=5, cell_width=None, current_top_offset=5,
                              forecast_offset_x=0, current_offset_y=0,
                              icon_vertical_offset=0, city="ERROR"):
        """
        Draw weather forecast on the left side of the screen.
        - Current weather stays at the top, with offset from top gap.
        - A horizontal line is drawn at the vertical centre of the left panel.
        - The four 3‑hour forecasts are placed in a horizontal row between the current
          weather and that centre line, with gaps between them.
        - The row is centred horizontally, then shifted by forecast_offset_x (no clamping).
        - The current weather text is shifted by current_offset_y.
        - The current weather icon is shifted additionally by icon_vertical_offset.
        """
        if not forecast_data:
            print("No forecast data to draw")
            return
    
        # Compute content area (same as calendar layout)
        top_gap_h = int(self.height * top_gap_ratio)
        bottom_gap_h = int(self.height * bottom_gap_ratio)
        content_y0 = top_gap_h
        content_y1 = self.height - bottom_gap_h
        content_h = content_y1 - content_y0
    
        # Left panel boundaries
        left_x0 = 0
        left_x1 = split_x
        left_w = left_x1 - left_x0
    
        # ---- Draw city at top left (same line as date) ----
        self.draw.text((margin, content_y0-40), city, fill=0, font=fonts['medium'], anchor='lt')
    
        # ---- Draw current weather ----
        current = forecast_data.get('current')
        if not current:
            print("No current weather data")
            return
        
        icon_name = self._get_icon_name(current.get('weather_id', 800),current.get('time').split()[1])
    
        # Base position for the icon (without icon offset)
        icon_y0_base = content_y0 + current_top_offset + current_offset_y
        icon_x0 = left_x0 + margin
        icon_x1 = icon_x0 + current_icon_size
        icon_y1_base = icon_y0_base + current_icon_size
    
        # Apply icon vertical offset to the paste coordinates
        icon_y0 = icon_y0_base + icon_vertical_offset
        icon_y1 = icon_y1_base + icon_vertical_offset
    
        # Paste icon with the offset
        self.paste_icon(icon_name, icon_x0, icon_y0, icon_x1, icon_y1, scale=1.0)
    
        # Text positions remain based on the base icon top (so they don't move with the icon)
        text_x = icon_x1 + 8
        text_y1 = icon_y0_base
        line_h_medium = fonts['medium'].getbbox('A')[3] - fonts['medium'].getbbox('A')[1]
    
        # ---- First line: condition only ----
        condition = current.get('condition', '')
        self.draw.text((text_x, text_y1), condition, fill=0, font=fonts['medium'], anchor='lt')
    
        # ---- Second line: temperature | humidity + humidity icon ----
        temp = current.get('temp', '')
        temp_str = f"{temp:.1f}°C" if isinstance(temp, (int, float)) else str(temp)
        humidity = current.get('humidity', '')
        hum_str = f"{humidity}%" if humidity else ""
    
        # Build the text parts
        text_parts = [temp_str, "|", hum_str]
        # Measure the total width of the text parts
        total_text_width = 0
        for part in text_parts:
            bbox = fonts['medium'].getbbox(part)
            total_text_width += bbox[2] - bbox[0]
        # Add small spacing between parts (optional)
        spacing = 5
        total_text_width += spacing * (len(text_parts) - 1)
    
        # Position for the second line (below condition)
        line_spacing = 4
        text_y2 = text_y1 + line_h_medium + line_spacing
    
        # Draw temperature
        self.draw.text((text_x, text_y2), temp_str, fill=0, font=fonts['medium'], anchor='lt')
        # Get width of temperature text
        temp_bbox = fonts['medium'].getbbox(temp_str)
        temp_w = temp_bbox[2] - temp_bbox[0]
        # Draw pipe with a small gap
        pipe_x = text_x + temp_w + spacing
        self.draw.text((pipe_x, text_y2), "|", fill=0, font=fonts['medium'], anchor='lt')
        pipe_bbox = fonts['medium'].getbbox("|")
        pipe_w = pipe_bbox[2] - pipe_bbox[0]
        # Draw humidity text
        hum_x = pipe_x + pipe_w + spacing
        self.draw.text((hum_x, text_y2), hum_str, fill=0, font=fonts['medium'], anchor='lt')
        hum_bbox = fonts['medium'].getbbox(hum_str)
        hum_w = hum_bbox[2] - hum_bbox[0]
    
        # ---- Paste humidity icon after the humidity text ----
        # Icon size: match the line height (makes it look inline)
        icon_size = line_h_medium
        # Icon top aligned with text top
        icon_top = text_y2
        icon_bottom = icon_top + icon_size
        # Position icon after the humidity text with a small gap
        icon_x = hum_x + hum_w + spacing
        # Use self.paste_icon (assuming it handles missing files gracefully)
        self.paste_icon("humidity", icon_x, icon_top, icon_x + icon_size, icon_bottom, scale=1.0)
    
        # Determine bottom of current weather section (using base icon bottom, because text is there)
        icon_bottom = icon_y1_base  # use base icon bottom, since text aligns with that
        # Text bottom is the second line + line height
        text_bottom = text_y2 + line_h_medium
        current_bottom = max(icon_bottom, text_bottom) + margin
        # Clip to content area
        current_bottom = min(current_bottom, content_y1 - margin)
    
        # ---- Horizontal line at the vertical centre of the left panel ----
        centre_y = content_y0 + content_h // 2
        self.draw.line([(left_x0 + margin, centre_y + 30),
                        (left_x1 - margin + 75, centre_y + 30)],
                       fill=0, width=2)
    
        # ---- Forecasts area: from current_bottom to centre_y ----
        forecast_area_top = current_bottom
        forecast_area_bottom = centre_y
        forecast_area_h = forecast_area_bottom - forecast_area_top
    
        # If the area is too small, adjust forecast icon size
        line_h_small = fonts['small'].getbbox('A')[3] - fonts['small'].getbbox('A')[1]
        min_required_h = forecast_icon_size + 2 * line_h_small + 4*4
        if forecast_area_h < min_required_h:
            scale = forecast_area_h / min_required_h
            new_icon_size = int(forecast_icon_size * scale)
            if new_icon_size < 10:
                new_icon_size = 10
            forecast_icon_size = new_icon_size
    
        # Draw the 4 forecasts in a horizontal row with gaps between cells
        next_3hour = forecast_data.get('next_3hour', [])
        if not next_3hour:
            print("No 3‑hour forecast data")
            return
    
        # Helper to draw centered text
        def draw_centered(text, x, y, font):
            try:
                self.draw.text((x, y), text, fill=0, font=font, anchor='mt')
            except TypeError:
                bbox = self.draw.textbbox((0, 0), text, font=font)
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
                self.draw.text((x - w//2, y - h//2), text, fill=0, font=font)
    
        num_items = min(4, len(next_3hour))
    
        # Determine cell width (if not provided)
        if cell_width is None:
            # Estimate based on forecast_icon_size and typical text width
            sample_texts = ["88:88", "88.8°C", "88%"]
            max_text_width = 0
            for s in sample_texts:
                bbox = fonts['small'].getbbox(s)
                w = bbox[2] - bbox[0]
                if w > max_text_width:
                    max_text_width = w
            cell_width = max(forecast_icon_size, max_text_width) + 20  # +20 for padding
    
        total_gap = (num_items - 1) * gap
        total_group_width = num_items * cell_width + total_gap
    
        # Centre the group horizontally within the left panel, then apply offset
        start_x = left_x0 + (left_w - total_group_width) // 2
        start_x += forecast_offset_x
    
        # No clamping – the offset can move the row anywhere (may go off screen)
        for idx in range(num_items):
            entry = next_3hour[idx]
            cell_x0 = start_x + idx * (cell_width + gap)
            cell_x1 = cell_x0 + cell_width
            cell_y0 = forecast_area_top
            cell_y1 = forecast_area_bottom
            cell_center_y = (cell_y0 + cell_y1) // 2
    
            # Extract data
            hour_str = entry.get('time', '')
            if hour_str:
                try:
                    hour_str = hour_str.split()[1][:5]  # HH:MM
                except:
                    pass
            else:
                hour_str = "--:--"
            temp_val = entry.get('temp', '')
            temp_str = f"{temp_val:.1f}°C" if isinstance(temp_val, (int, float)) else str(temp_val)
            hum = entry.get('humidity', '')
            hum_str = f"{hum}%" if hum else ""
            weather_id = entry.get('weather_id', 800)
            icon_name = self._get_icon_name(weather_id,hour_str)
    
            # Vertical stack: hour, icon, temp, humidity
            icon_w = forecast_icon_size
            icon_h = forecast_icon_size
            spacing = 4
            total_height = line_h_small + icon_h + 2*line_h_small + 3*spacing
            start_y = cell_center_y - total_height // 2
    
            # Draw hour
            hour_x = (cell_x0 + cell_x1) // 2
            draw_centered(hour_str, hour_x, start_y, fonts['small'])
    
            # Draw icon (centered horizontally)
            icon_x = hour_x - icon_w // 2
            icon_y = start_y + line_h_small + spacing
            self.paste_icon(icon_name, icon_x, icon_y, icon_x + icon_w, icon_y + icon_h, scale=1.0)
    
            # Draw temperature
            temp_y = icon_y + icon_h + spacing
            draw_centered(temp_str, hour_x, temp_y, fonts['small'])
    
            # Draw humidity
            hum_y = temp_y + line_h_small + spacing
            draw_centered(hum_str, hour_x, hum_y, fonts['small'])
            
            
        
        

    def draw_daily_forecast(self, forecast_data, split_x, fonts,
                            top_gap_ratio=0.1, bottom_gap_ratio=0.1,
                            margin=10, icon_size=40, gap=5, cell_width=None,
                            offset_x=0, offset_y=0):
        """
        Draw daily forecasts below the centre line in the left panel.
        Uses data from forecast_data['next_daily'].
        Each cell shows: weekday, icon, temperature, humidity.
    
        :param forecast_data: dict returned by APIClient.fetch_forecast()
        :param split_x: x-coordinate of vertical divider (e.g., width // 2)
        :param fonts: dict with 'tiny', 'small', 'medium', 'large'
        :param top_gap_ratio: same as used in calendar layout
        :param bottom_gap_ratio: same as used in calendar layout
        :param margin: horizontal margin inside left panel
        :param icon_size: size of the weather icon (square)
        :param gap: pixels between cells
        :param cell_width: optional fixed cell width; if None, auto‑calculated
        :param offset_x: horizontal shift of the entire row (positive = right)
        :param offset_y: vertical shift of the entire row (positive = down)
        """
        if not forecast_data:
            print("No forecast data to draw")
            return
    
        # Compute the vertical centre line (same as in draw_weather_forecast)
        top_gap_h = int(self.height * top_gap_ratio)
        bottom_gap_h = int(self.height * bottom_gap_ratio)
        content_y0 = top_gap_h
        content_y1 = self.height - bottom_gap_h
        content_h = content_y1 - content_y0
        centre_y = content_y0 + content_h // 2
    
        # Left panel boundaries
        left_x0 = 0
        left_x1 = split_x
        left_w = left_x1 - left_x0
    
        # Get daily data
        daily = forecast_data.get('next_daily', [])
        if not daily:
            print("No daily forecast data to draw")
            return
    
        # Limit to 4 days (or as many as available)
        num_items = min(4, len(daily))
    
        # Helper for centered text
        def draw_centered(text, x, y, font):
            try:
                self.draw.text((x, y), text, fill=0, font=font, anchor='mt')
            except TypeError:
                bbox = self.draw.textbbox((0, 0), text, font=font)
                w = bbox[2] - bbox[0]
                h = bbox[3] - bbox[1]
                self.draw.text((x - w//2, y - h//2), text, fill=0, font=font)
    
        # Determine cell width
        line_h_small = fonts['small'].getbbox('A')[3] - fonts['small'].getbbox('A')[1]
        if cell_width is None:
            # Estimate based on icon and typical text width
            sample_texts = ["MON", "88.8°C", "88%"]
            max_text_width = 0
            for s in sample_texts:
                bbox = fonts['small'].getbbox(s)
                w = bbox[2] - bbox[0]
                if w > max_text_width:
                    max_text_width = w
            cell_width = max(icon_size, max_text_width) + 20  # padding
    
        total_gap = (num_items - 1) * gap
        total_group_width = num_items * cell_width + total_gap
    
        # Centre horizontally, then apply offset_x
        start_x = left_x0 + (left_w - total_group_width) // 2
        start_x += offset_x
    
        # Vertical starting point: below centre line + offset_y (with some padding)
        # We'll place the row a bit below the line, so we use centre_y + 20 + offset_y
        # Adjust the constant as needed (e.g., 20 pixels gap).
        row_y = centre_y + 20 + offset_y
    
        # Compute the height of the row (approximately icon + text)
        row_height = icon_size + 2 * line_h_small + 3*4  # icon + two text lines + spacings
        # Center the row vertically around row_y
        row_center_y = row_y + row_height // 2
    
        for idx in range(num_items):
            day = daily[idx]
            cell_x0 = start_x + idx * (cell_width + gap)
            cell_x1 = cell_x0 + cell_width
            cell_center_x = (cell_x0 + cell_x1) // 2
    
            # Vertical stack: weekday (top), icon (middle), temp + humidity (bottom)
            # We'll position everything relative to the cell's vertical center
            total_height = line_h_small + icon_size + 2*line_h_small + 3*4  # hour + icon + temp + humidity + spacing
            start_y = row_center_y - total_height // 2
    
            # Weekday
            weekday = day.get('day', '???')
            draw_centered(weekday, cell_center_x, start_y, fonts['small'])
    
            # Icon
            icon_name = self._get_icon_name(day.get('weather_id', 800),day.get('time').split()[1])
            icon_x = cell_center_x - icon_size // 2
            icon_y = start_y + line_h_small + 4
            self.paste_icon(icon_name, icon_x, icon_y, icon_x + icon_size, icon_y + icon_size, scale=1.0)
    
            # Temperature
            temp = day.get('temp', '')
            temp_str = f"{temp:.1f}°C" if isinstance(temp, (int, float)) else str(temp)
            temp_y = icon_y + icon_size + 4
            draw_centered(temp_str, cell_center_x, temp_y, fonts['small'])
    
            # Humidity
            hum = day.get('humidity', '')
            hum_str = f"{hum}%" if hum else ""
            hum_y = temp_y + line_h_small + 4
            draw_centered(hum_str, cell_center_x, hum_y, fonts['small'])
    



    def draw_calendar_layout(self, events, current_date_str, last_refresh_str,
                             fonts, fat_line_x=0.5, right_rows=5,
                             top_gap_ratio=0.1, bottom_gap_ratio=0.1,
                             date_width_ratio=0.22, top_offset=-10, bottom_offset=-10):
        """
        Draw a calendar layout with a vertical divider that stops before top/bottom gaps.
        The date and refresh text are placed in the top and bottom gaps, centered.

        :param events:            list of event dicts (from CalendarEvents)
        :param current_date_str:  text for top gap (e.g. "15 Feb 2026")
        :param last_refresh_str:  text for bottom gap (e.g. "14:25:12")
        :param fonts:             dict with 'tiny', 'small', 'medium', 'large' fonts
        :param fat_line_x:        (unused – kept for compatibility) x‑position of vertical divider (fraction of width, 0..1)
        :param right_rows:        number of event rows
        :param top_gap_ratio:     fraction of screen height reserved for top gap
        :param bottom_gap_ratio:  fraction of screen height reserved for bottom gap
        :param date_width_ratio:  fraction of row width reserved for the date block (left part)
        :param top_offset:        vertical shift for top date (pixels, negative up)
        :param bottom_offset:     vertical shift for bottom refresh (pixels, negative up)
        """
        # Gaps
        top_gap_h = int(self.height * top_gap_ratio)
        bottom_gap_h = int(self.height * bottom_gap_ratio)
        content_y0 = top_gap_h
        content_y1 = self.height - bottom_gap_h
        content_h = content_y1 - content_y0

        # Draw date in top gap (centered, with offset)
        date_y = top_gap_h // 2 + top_offset
        self._draw_centered_text(current_date_str,
                                 self.width // 2, date_y,
                                 font=fonts.get('medium'), fill=0)

        # Draw refresh text in bottom gap (centered, with offset)
        refresh_y = self.height - bottom_gap_h // 2 + bottom_offset
        self._draw_centered_text(last_refresh_str,
                                 self.width // 2, refresh_y,
                                 font=fonts.get('small'), fill=0)

        # Fat vertical line (exactly at half width)
        split_x = self.width // 2
        self.draw.line([(split_x, content_y0), (split_x, content_y1-1)],
                       fill=0, width=4)

        # ----- Right panel (inside content area) -----
        right_x0 = split_x
        right_x1 = self.width
        right_w = right_x1 - right_x0
        right_h = content_h

        # Row height (equal)
        row_h = right_h // right_rows

        # Helper for wrapping text
        def draw_wrapped_text(x, y, text, font, max_width, line_spacing=4):
            """Draw text wrapped to max_width, returning the next y position."""
            if not text:
                return y
            words = text.split()
            lines = []
            current_line = []
            for w in words:
                test_line = ' '.join(current_line + [w])
                bbox = self.draw.textbbox((0,0), test_line, font=font)
                w_width = bbox[2] - bbox[0]
                if w_width <= max_width:
                    current_line.append(w)
                else:
                    if current_line:
                        lines.append(' '.join(current_line))
                    current_line = [w]
            if current_line:
                lines.append(' '.join(current_line))

            for line in lines:
                self.draw.text((x, y), line, fill=0, font=font, anchor='lt')
                y += font.getbbox('A')[3] - font.getbbox('A')[1] + line_spacing
            return y

        for i in range(right_rows):
            y0 = content_y0 + i * row_h
            y1 = y0 + row_h

            # Horizontal line between rows (except first)
            if i > 0:
                self.draw.line([(right_x0, y0), (right_x1, y0)], fill=0, width=1)

            # Vertical separator inside each row (between date and details)
            sep_x = right_x0 + int(right_w * date_width_ratio)
            self.draw.line([(sep_x, y0), (sep_x, y1)], fill=0, width=1)

            # ---- Left part of row: date info ----
            date_x_center = (right_x0 + sep_x) // 2
            date_y_center = (y0 + y1) // 2

            if i < len(events):
                ev = events[i]
                start_date_str = ev['start_date']
                try:
                    dt = datetime.datetime.strptime(start_date_str, '%Y-%m-%d')
                    weekday = dt.strftime('%a').upper()[:3]   # MON, TUE, ...
                    day = str(dt.day)
                    month = dt.strftime('%B')
                except:
                    weekday = day = month = "??"
            else:
                weekday = day = month = ""

            # Increased line spacing for date block (+6 instead of +2)
            font_tiny = fonts.get('tiny')
            line_h = font_tiny.getbbox('A')[3] - font_tiny.getbbox('A')[1] + 6
            total_h = line_h * 3
            start_y = date_y_center - total_h // 2

            if weekday:
                self._draw_centered_text(weekday, date_x_center, start_y,
                                         font=fonts.get('small'), fill=0)
                start_y += line_h
                self._draw_centered_text(day, date_x_center, start_y,
                                         font=fonts.get('small'), fill=0)
                start_y += line_h
                self._draw_centered_text(month, date_x_center, start_y,
                                         font=fonts.get('small'), fill=0)

            # ---- Right part of row: event details (with wrapping) ----
            if i < len(events):
                ev = events[i]
                summary = ev['summary']
                description = ev['description']
                location = ev['location']
                start_time = ev['start_time']
                end_time = ev['end_time']

                # Format time range
                if start_time and end_time:
                    start_t = start_time.split('+')[0].split('-')[0][:5]
                    end_t = end_time.split('+')[0].split('-')[0][:5]
                    time_str = f"{start_t} – {end_t}"
                elif start_time:
                    time_str = start_time.split('+')[0].split('-')[0][:5]
                else:
                    time_str = "All day"

                # Max width for text (right part minus margin)
                max_text_width = right_x1 - sep_x - 15   # 15px left margin
                text_x = sep_x + 10
                text_y = y0 + 8
                line_spacing = 6

                # Draw summary (use small font)
                text_y = draw_wrapped_text(text_x, text_y, summary,
                                           fonts.get('medium'), max_text_width, line_spacing)

                # Draw time (tiny font)
                text_y = draw_wrapped_text(text_x, text_y, time_str,
                                           fonts.get('small'), max_text_width, line_spacing)

                # Draw description (tiny font)
                text_y = draw_wrapped_text(text_x, text_y, description,
                                           fonts.get('small'), max_text_width, line_spacing)

                # Draw location (tiny font)
                draw_wrapped_text(text_x, text_y, location,
                                  fonts.get('small'), max_text_width, line_spacing)






import pickle
import datetime
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

class CalendarEvents:
    def __init__(self, credentials_file='client_secrets.json', token_file='token.pickle'):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.scopes = ['https://www.googleapis.com/auth/calendar.readonly']
        self.service = None

    def authenticate(self):
        creds = None
        if os.path.exists(self.token_file):
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Load client secrets from JSON file
                with open(self.credentials_file) as f:
                    import json
                    client_config = json.load(f)['installed']

                client_id = client_config['client_id']
                client_secret = client_config['client_secret']
                redirect_uri = client_config['redirect_uris'][0]  # should be "http://localhost"

                # Build the authorization URL
                auth_url = (
                    "https://accounts.google.com/o/oauth2/auth"
                    f"?response_type=code"
                    f"&client_id={client_id}"
                    f"&redirect_uri={redirect_uri}"
                    f"&scope={' '.join(self.scopes)}"
                    "&access_type=offline"
                    "&prompt=consent"
                )
                print("\nPlease visit this URL to authorize the application:\n")
                print(auth_url)

                # Get the authorization code from the user
                code = input("\nEnter the authorization code: ")

                # Exchange the code for tokens
                token_url = "https://oauth2.googleapis.com/token"
                data = {
                    'code': code,
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'redirect_uri': redirect_uri,
                    'grant_type': 'authorization_code'
                }
                response = requests.post(token_url, data=data)
                token_info = response.json()

                # Create credentials object from the token info
                creds = Credentials(
                    token=token_info.get('access_token'),
                    refresh_token=token_info.get('refresh_token'),
                    token_uri=token_url,
                    client_id=client_id,
                    client_secret=client_secret,
                    scopes=self.scopes
                )

            # Save credentials for next run
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)

        self.service = build('calendar', 'v3', credentials=creds)

    def get_upcoming_events(self, max_results=5):
        if not self.service:
            raise Exception("Not authenticated. Call authenticate() first.")

        now = datetime.datetime.utcnow().isoformat() + 'Z'
        events_result = self.service.events().list(
            calendarId='primary',
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        upcoming_events = []

        for event in events:
            # Extract basic fields
            summary = event.get('summary', 'No title')
            description = event.get('description', '')
            location = event.get('location', '')

            # Start date/time
            start_obj = event['start']
            if 'dateTime' in start_obj:
                # Timed event
                start_dt_str = start_obj['dateTime']
                start_date, start_time = start_dt_str.split('T')
            else:
                # All‑day event
                start_date = start_obj['date']
                start_time = ''   # no time for all‑day events

            # End date/time
            end_obj = event['end']
            if 'dateTime' in end_obj:
                end_dt_str = end_obj['dateTime']
                end_date, end_time = end_dt_str.split('T')
            else:
                # All‑day event: end is the day after (exclusive)
                end_date = end_obj['date']
                end_time = ''

            # Build the event dict
            upcoming_events.append({
                'summary': summary,
                'description': description,
                'location': location,
                'start_date': start_date,
                'start_time': start_time,
                'end_date': end_date,
                'end_time': end_time,
            })
        return upcoming_events
