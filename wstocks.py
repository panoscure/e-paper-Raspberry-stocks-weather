import socket
import time
from PIL import Image, ImageDraw
from epd_driver import EPD, RaspberryPi, EPD_WIDTH, EPD_HEIGHT
from class_lib import APIClient, EPDDrawing, DateTime, FontManager, CalendarEvents
from secrets import OWM_API_KEY, CITY, COUNTRY, EODHD_API_TOKEN, YAHOO_API_KEY

def internet_available(host="8.8.8.8", port=53, timeout=3):
    """Return True if internet is reachable, else False."""
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except Exception:
        return False

def main():
    print("=== GitHub Driver Full Test (Continuous Mode) ===")
    epdcfg = RaspberryPi()
    epd = EPD(epdcfg)

    try:
        # ---------- One‑time initialisation ----------
        fonts_caveat = FontManager(font_path="/home/panos/epaper/fonts/Caveat.ttf")
        fonts_nunito = FontManager(font_path="/home/panos/epaper/fonts/NunitoSans-Italic.ttf")
        fonts = FontManager()

        caveat_tiny   = fonts_caveat.get_tiny()
        caveat_small  = fonts_caveat.get_small()
        caveat_medium = fonts_caveat.get_medium()
        caveat_large  = fonts_caveat.get_large()

        nunito_tiny   = fonts_nunito.get_tiny()
        nunito_small  = fonts_nunito.get_small()
        nunito_medium = fonts_nunito.get_medium()
        nunito_large  = fonts_nunito.get_large()

        #client = APIClient(OWM_API_KEY, CITY, COUNTRY, EODHD_API_TOKEN)
        client = APIClient(OWM_API_KEY, CITY, COUNTRY, EODHD_API_TOKEN, YAHOO_API_KEY)

        symbols = ["ALWN.AT", "EYDAP.AT", "ETE.AT", "AETF.AT", "PPC.AT", "4UBQ.DE"]
        dt = DateTime()

        last_stocks = None
        last_image = None  # Stores the last successfully drawn image

        while True:
            # --- Internet check ---
            online = internet_available()
            print(f"Internet {'available' if online else 'OFFLINE'}")

            if not online:
                # No internet – display overlay on last image (if exists)
                if last_image is not None:
                    # Create a copy to avoid modifying the stored original
                    img = last_image.copy()
                    draw = ImageDraw.Draw(img)
                    # Draw "No Internet" in a corner (e.g., bottom‑right)
                    draw.text((EPD_WIDTH - 150, EPD_HEIGHT - 30),
                              "No Internet", fill=0, font=caveat_medium)
                else:
                    # First run and no internet – show a minimal message
                    img = Image.new('1', (EPD_WIDTH, EPD_HEIGHT), 1)
                    draw = ImageDraw.Draw(img)
                    draw.text((EPD_WIDTH//2, EPD_HEIGHT//2),
                              "No Internet", fill=0, font=caveat_large, anchor="mm")

                epd.display_image(img)
                print("No internet – sleeping 5 minutes...")
                time.sleep(300)   # 5 minutes
                continue          # go back to check internet again

            # --- Internet is online – proceed with normal update ---
            local_time = dt.get_current_dt()
            hour = local_time[3]
            minute = local_time[4]
            print(f"\nLocal time: {hour:02d}:{minute:02d}")

            # Fetch weather
            weather = client.fetch_weather()
            if weather:
                temp = weather["temp"]
                weather_icon = weather["weather_icon"]
                condition = weather["condition"]
                wind_speed = weather["wind_speed"] * 3.6
                wind_deg = weather["wind_deg"]
                sunrise = weather["sunrise"]
                sunset = weather["sunset"]
                humidity = weather["humidity"]
                pressure = weather["pressure"]

                print("Condition:", condition)
                print("Temp:", temp)
                print("weather_icon:", weather_icon)
                print("wind_speed:", wind_speed)
                print("wind_deg:", wind_deg)
                print("feels_like:", weather["feels"])
                print("sunrise:", sunrise)
                print("sunset:", sunset)
                print("humidity:", humidity)
                print("pressure:", pressure)

            # Fetch stocks during trading hours
            if(hour):
            #if (hour == 10 and minute >= 30) or (11 <= hour <= 17) or (hour == 18 and minute == 0):
                #stocks = client.fetch_stocks(symbols)
                stocks = client.yahoo_fetch_stocks(symbols)
                if stocks:
                    last_stocks = stocks
                    codes = stocks["codes"]
                    changes = stocks["changes"]
                    change_ps = stocks["change_ps"]
                    closes = stocks["closes"]
                    print("Codes:", codes)
                    print("Changes:", changes)
                    print("change_ps:", change_ps)
                    print("closes:", closes)
                else:
                    print("Stock fetch returned None – keeping previous data")
            else:
                print("Outside stock trading hours – using last known stock data")
                stocks = None

            greek_offset = dt.get_current_offset()
            current_utc = int(time.time())
            sunrise_ts = weather.get("sunrise") if weather else None
            sunset_ts = weather.get("sunset") if weather else None

            # Create fresh image
            print("Clearing screen and redrawing...")
            epd.clear()
            time.sleep(1)

            img = Image.new('1', (EPD_WIDTH, EPD_HEIGHT), 1)
            epd_draw = EPDDrawing(img, icon_folder="/home/panos/epaper/icons")

            # Draw grid
            epd_draw.draw_grid(rows=3, cols=4, color=0, include_outer_border=True)

            # Draw condition
            draw = epd_draw.draw
            draw.text((5, 110), condition, font=fonts_caveat.get_large(), fill=0)

            # Place weather icon and other data
            if weather:
                epd_draw.draw_weather_icon_in_cell(0, 0, weather, rows=3, cols=4,
                                                   scale=0.8, vertical_offset=-15)

                if wind_speed is not None:
                    epd_draw.draw_wind_compass_in_cell(2, 0, wind_deg, wind_speed=wind_speed,
                                                       rows=3, cols=4, compass_scale=0.8,
                                                       vertical_offset=0, horizontal_offset=0,
                                                       tiny_font=caveat_small, large_font=caveat_large)

                if sunrise_ts and sunset_ts:
                    epd_draw.draw_day_night_in_cell(1, 0,
                        sunrise_ts, sunset_ts, current_utc,
                        timezone_offset=greek_offset,
                        rows=3, cols=4,
                        circle_scale=0.4,
                        vertical_offset=-40,
                        small_font=caveat_medium,
                        tiny_font=caveat_small,
                        large_font=caveat_large
                    )

                if humidity is not None:
                    epd_draw.draw_humidity_in_cell(2, 1, humidity,
                                                   rows=3, cols=4,
                                                   icon_scale=0.8,
                                                   vertical_offset=-5,
                                                   font=caveat_large,
                                                   icon_margin=9,
                                                   text_gap=-5)

                if pressure is not None:
                    epd_draw.draw_pressure_in_cell(1, 1, pressure,
                                   rows=3, cols=4,
                                   icon_scale=0.7,
                                   vertical_offset=-5,
                                   font=caveat_large,
                                   unit_font=caveat_medium,
                                   icon_margin=9,
                                   text_gap=2)

                if temp is not None:
                    epd_draw.draw_temperature_in_cell(0, 1, temp,
                                      rows=3, cols=4,
                                      icon_scale=0.7,
                                      vertical_offset=-5,
                                      font=caveat_large,
                                      unit_font=caveat_medium,
                                      icon_margin=10,
                                      text_gap=5)

            # Draw stocks if available
            if last_stocks:
                codes = last_stocks["codes"]
                changes = last_stocks["changes"]
                change_ps = last_stocks["change_ps"]
                closes = last_stocks["closes"]
                for i in range(6):
                    if i < len(codes):
                        symbol = codes[i]
                        change = changes[i]
                        change_pct = change_ps[i]
                        stock_close = closes[i]
                    else:
                        continue

                    row = i // 2
                    col = 2 + (i % 2)
                    epd_draw.draw_stock_in_cell(row, col, symbol, change, change_pct, stock_close,
                                                rows=3, cols=4, font=caveat_large)
            else:
                print("No stock data available yet – skipping stock display")

            # Store this image as the last successful one
            last_image = img.copy()

            # Display
            print("Displaying updated screen...")
            epd.display_image(img)
            

            
            
            

            # Sleep 30 minutes
            print("Sleeping for 15 minutes...")
            time.sleep(900)

    except KeyboardInterrupt:
        print("\nInterrupted by user – shutting down.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        epdcfg.module_exit()
        print("Test complete.")
        
        
        
        
if __name__ == "__main__":
    main()
