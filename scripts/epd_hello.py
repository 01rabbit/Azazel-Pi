#!/usr/bin/env python3
"""Simple Waveshare e-Paper hello script (1-bit monochrome).

This script tries to import common epd driver modules and displays a
small status box. Adjust the font path or driver name if needed.
"""
from PIL import Image, ImageDraw, ImageFont
import time

# Try common driver names (V4 boards used in this project)
DRIVER_CANDIDATES = [
    "waveshare_epd.epd2in13_V4",
    "waveshare_epd.epd2in13b_V4",
    "waveshare_epd.epd2in13_V3",
]

EPD_MOD = None
for mod in DRIVER_CANDIDATES:
    try:
        parts = mod.split(".")
        pkg = __import__(".".join(parts[:-1]), fromlist=[parts[-1]])
        EPD_MOD = getattr(pkg, parts[-1])
        print(f"Using driver: {mod}")
        break
    except Exception:
        continue

if EPD_MOD is None:
    raise SystemExit("No compatible Waveshare EPD driver found. Install the Waveshare e-Paper library first.")

epd = EPD_MOD.EPD()
epd.init()
try:
    epd.Clear(0xFF)
except Exception:
    # Some drivers use Clear without args
    try:
        epd.Clear()
    except Exception:
        pass

image = Image.new('1', (epd.width, epd.height), 255)
draw = ImageDraw.Draw(image)
try:
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 18)
except Exception:
    font = ImageFont.load_default()

draw.text((8, 8), "Azazel status:", font=font, fill=0)
draw.rectangle((8, 40, epd.width - 8, 80), outline=0, width=2)
draw.text((12, 48), "ONLINE / READY", font=font, fill=0)

# Use getbuffer/display pattern used by Waveshare drivers
try:
    buf = epd.getbuffer(image)
    epd.display(buf)
except Exception:
    # Some drivers accept display(image)
    try:
        epd.display(image)
    except Exception as e:
        print("Display failed:", e)

time.sleep(2)
try:
    epd.sleep()
except Exception:
    pass

print("Done.")
