# E-Paper Weather & Stock Display

A Raspberry Pi Zero based project that fetches current weather and stock prices (up to 6 symbols) and displays them on a 7.5 inch e‑Paper screen.  
Data is retrieved every 15 minutes using free APIs.


## Features

- Shows current weather (temperature, conditions) for a configurable city.
- Shows live stock prices for up to 6 symbols.
- Updates automatically every 15 minutes.
- Low power – perfect for e‑Paper.
- Runs on a Raspberry Pi Zero (or any Pi with GPIO).

## Hardware Required

- **Raspberry Pi Zero** (or Zero W / 2W) 
- **7.5 inch e‑Paper display (HAT)** – [Amazon link](https://www.amazon.de/-/en/dp/B07MB7SVHQ?ref=ppx_yo2ov_dt_b_fed_asin_title)
- **Raspberry Pi Zero GPIO header (soldered or pre‑soldered)** – [Amazon link](https://www.amazon.de/-/en/dp/B075R55WQT?ref=ppx_yo2ov_dt_b_fed_asin_title)
- MicroSD card (8GB+), power supply, optional case.

> **Note:** The e‑Paper display is sold as a HAT that plugs directly onto the Pi’s GPIO pins. Make sure your Pi Zero has the male header pins soldered.

## Software & APIs

This project uses two free APIs:

| API | Purpose | Sign‑up link |
| --- | --- | --- |
| OpenWeatherMap | Current weather | [https://openweathermap.org/](https://openweathermap.org/) |
| Yahoo Finance (via apidojo) | Stock prices | [Documentation](https://apidojo.net/documentations/yahoo#tag/) |

Both offer free tiers sufficient for personal use (update every 15 minutes).

## Setup Instructions

### 1. Install Raspberry Pi OS

Flash **Raspberry Pi OS Lite** (or full) to the microSD card. Enable SSH and Wi‑Fi during setup (or use `raspi-config` later).

### 2. Enable SPI interface

The e‑Paper display uses SPI. Run:

```bash
sudo raspi-config
→ Interface Options → SPI → Enable

sudo apt update
sudo apt install python3-pip python3-venv git -y
git clone <your-repo-url>   # or copy files manually
cd <project-directory>

python3 -m venv venv
source venv/bin/activate
pip install requests Pillow RPi.GPIO spidev

### 3. Configure secrets
# secrets.py

# Wi‑Fi credentials (for the Pi to connect to your network)
SSID = "YourWiFiName"
PASSWORD = "YourWiFiPassword"

# OpenWeatherMap
OPENWEATHER_API_KEY = "your_openweather_api_key"
COUNTRY = "DE"          # e.g., "US", "GB", "FR"
CITY = "Berlin"         # city name (English)

# Yahoo Finance API (apidojo)
YAHOO_API_KEY = "your_yahoo_api_key"


### 4. Configure stock symbols
symbols = ["ALWN.AT", "EYDAP.AT", "ETE.AT", "AETF.AT", "PPC.AT", "4UBQ.DE"]

### 5. Run the display
Step 1: Create the service file

bash
sudo nano /etc/systemd/system/epaper-display.service
Step 2: Add the service configuration

ini
[Unit]
Description=E-Paper Weather and Stock Display
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/your_project_folder/wstocks.py
WorkingDirectory=/home/pi/your_project_folder
StandardOutput=inherit
StandardError=inherit
Restart=always
RestartSec=10
User=pi

[Install]
WantedBy=multi-user.target
Replace your_project_folder with your actual project path

The Restart=always ensures your script restarts if it crashes

Step 3: Enable and start the service

bash
sudo systemctl daemon-reload
sudo systemctl enable epaper-display.service
sudo systemctl start epaper-display.service

For enclosure you may use the following: https://www.thingiverse.com/thing:7327540

License
This project is for personal/educational use. API keys must be obtained from their respective providers and used according to their terms.


![gmail_images20260402_124350](https://github.com/user-attachments/assets/5c6eb609-2c08-4ef1-a4cb-939a1de1fcaf)
![gmail_images20260402_124231](https://github.com/user-attachments/assets/8a11072b-600c-4899-8966-c146ef0685cc)
![gmail_images20260402_124204](https://github.com/user-attachments/assets/2416d575-225b-4683-823f-8f1f8d3e7c3c)


