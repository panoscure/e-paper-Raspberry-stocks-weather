# E-Paper Weather & Stock Display

A Raspberry Pi Zero based project that fetches current weather and stock prices (up to 6 symbols) and displays them on a 7.5 inch e‑Paper screen.  
Data is retrieved every 15 minutes using free APIs.


## Features

- Shows current weather (temperature, conditions) for a configurable city.<br/>
- Shows live stock prices for up to 6 symbols.<br/>
- Updates automatically every 15 minutes.<br/>
- Low power – perfect for e‑Paper.<br/>
- Runs on a Raspberry Pi Zero (or any Pi with GPIO).<br/>

## Hardware Required

- **Raspberry Pi Zero** (or Zero W / 2W) 
- **7.5 inch e‑Paper display (HAT)** – [Amazon link](https://www.amazon.de/-/en/dp/B07MB7SVHQ?ref=ppx_yo2ov_dt_b_fed_asin_title)
- **Raspberry Pi Zero GPIO header (soldered or pre‑soldered)** – [Amazon link](https://www.amazon.de/-/en/dp/B075R55WQT?ref=ppx_yo2ov_dt_b_fed_asin_title)
- MicroSD card (8GB+), power supply, optional case.

> **Note:** The e‑Paper display is sold as a HAT that plugs directly onto the Pi’s GPIO pins. Make sure your Pi Zero has the male header pins soldered.

## Software & APIs

This project uses two free APIs:<br/>

| API | Purpose | Sign‑up link |
| --- | --- | --- |
| OpenWeatherMap | Current weather | [https://openweathermap.org/](https://openweathermap.org/) |
| Yahoo Finance (via apidojo) | Stock prices | [Documentation](https://apidojo.net/documentations/yahoo#tag/) |

Both offer free tiers sufficient for personal use (update every 15 minutes).

## Setup Instructions

### 1. Install Raspberry Pi OS

Flash **Raspberry Pi OS Lite** (or full) to the microSD card. Enable SSH and Wi‑Fi during setup (or use `raspi-config` later).

### 2. Enable SPI interface

The e‑Paper display uses SPI. Run:<br/>

bash<br/>
sudo raspi-config<br/>
→ Interface Options → SPI → Enable<br/>

sudo apt update<br/>
sudo apt install python3-pip python3-venv git -y<br/>
git clone <your-repo-url>   # or copy files manually<br/>
cd <project-directory><br/>

python3 -m venv venv<br/>
source venv/bin/activate<br/>
pip install requests Pillow RPi.GPIO spidev<br/>

### 3. Configure secrets
secrets.py<br/>

Wi‑Fi credentials (for the Pi to connect to your network)<br/>
SSID = "YourWiFiName"<br/>
PASSWORD = "YourWiFiPassword"<br/>

OpenWeatherMap<br/>
OPENWEATHER_API_KEY = "your_openweather_api_key"<br/>
COUNTRY = "DE"          # e.g., "US", "GB", "FR"<br/>
CITY = "Berlin"         # city name (English)<br/>

Yahoo Finance API (apidojo)<br/>
YAHOO_API_KEY = "your_yahoo_api_key"<br/>


### 4. Configure stock symbols<br/>
symbols = ["ALWN.AT", "EYDAP.AT", "ETE.AT", "AETF.AT", "PPC.AT", "4UBQ.DE"]<br/>

### 5. Run the display
**Step 1: Create the service file**<br/>

bash<br/>
sudo nano /etc/systemd/system/epaper-display.service<br/>

**Step 2: Add the service configuration**

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

**Step 3: Enable and start the service**

bash<br/>
sudo systemctl daemon-reload<br/>
sudo systemctl enable epaper-display.service<br/>
sudo systemctl start epaper-display.service<br/>

For enclosure you may use the following: https://www.thingiverse.com/thing:7327540


### License
### This project is for personal/educational use. API keys must be obtained from their respective providers and used according to their terms.


![gmail_images20260402_124350](https://github.com/user-attachments/assets/5c6eb609-2c08-4ef1-a4cb-939a1de1fcaf)
![gmail_images20260402_124231](https://github.com/user-attachments/assets/8a11072b-600c-4899-8966-c146ef0685cc)
![gmail_images20260402_124204](https://github.com/user-attachments/assets/2416d575-225b-4683-823f-8f1f8d3e7c3c)


