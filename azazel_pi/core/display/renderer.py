"""E-Paper renderer for Azazel Pi status display."""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from .status_collector import SystemStatus

# Waveshare E-Paper library paths
WS_ROOT = Path("/opt/waveshare-epd/RaspberryPi_JetsonNano/python")
WS_LIB = WS_ROOT / "lib"

# Font candidates (fallback chain)
TITLE_FONT_CANDIDATES = [
    # Prefer local repo font if present (fonts/ in project root), then fall back
    # to system fonts.
    # Path: <repo root>/fonts/Tamanegi_kaisyo_geki_v7.ttf
    str(Path(__file__).resolve().parents[3] / "fonts" / "Tamanegi_kaisyo_geki_v7.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
]
MONO_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf",
]


class EPaperRenderer:
    """Renders Azazel Pi status to Waveshare E-Paper display."""

    def __init__(
        self,
        width: int = 250,
        height: int = 122,
        driver_name: str = "epd2in13_V4",
        rotation: int = 0,
        debug: bool = False,
        emulate: bool = False,
    ):
        """Initialize the E-Paper renderer.

        Args:
            width: Display width in pixels
            height: Display height in pixels
            driver_name: Waveshare driver module name
            debug: Enable debug output
            emulate: Emulation mode (no physical display required)
        """
        self.width = width
        self.height = height
        self.driver_name = driver_name
        # Rotation in degrees (0, 90, 180, 270). Applied to final image before sending.
        try:
            self.rotation = int(rotation) % 360
        except Exception:
            self.rotation = 0
        self.debug = debug
        self.emulate = emulate
        self._epd = None
        self._bicolor = False

    def _init_driver(self) -> None:
        """Initialize the E-Paper driver."""
        if self._epd is not None:
            return

        if self.emulate:
            if self.debug:
                print("Running in emulation mode (no physical display)", file=sys.stderr)
            # Create a mock EPD object
            class MockEPD:
                def init(self): pass
                def getbuffer(self, image): return bytes(image.tobytes())
                def display(self, *args): pass
                def displayPartial(self, *args): pass
                def Clear(self, *args): pass
                def sleep(self): pass
                width = self.width
                height = self.height
            self._epd = MockEPD()
            self._bicolor = False
            return

        # Add Waveshare library to path
        for path in (WS_ROOT, WS_LIB):
            path_str = str(path)
            if path_str not in sys.path:
                sys.path.append(path_str)

        # Force lgpio backend for Raspberry Pi 5
        try:
            import gpiozero
            from gpiozero.pins.lgpio import LGPIOFactory
            if gpiozero.Device.pin_factory is None:
                gpiozero.Device.pin_factory = LGPIOFactory()
                if self.debug:
                    print("Using lgpio backend for Raspberry Pi 5", file=sys.stderr)
        except Exception as e:
            if self.debug:
                print(f"Could not set lgpio backend: {e}", file=sys.stderr)

        try:
            # Try to import the specified driver
            from waveshare_epd import epd2in13_V4 as drv

            self._epd = drv.EPD()
            self._epd.init()
            self._bicolor = False
        except ImportError:
            try:
                # Fallback to bicolor version
                from waveshare_epd import epd2in13b_V4 as drv

                self._epd = drv.EPD()
                self._epd.init()
                self._bicolor = True
            except ImportError as e:
                if self.debug:
                    traceback.print_exc()
                raise RuntimeError(f"E-Paper driver not found: {e}")

        # Adjust dimensions based on driver
        if hasattr(self._epd, "width") and hasattr(self._epd, "height"):
            w = self._epd.width
            h = self._epd.height
            # Landscape orientation
            self.width, self.height = (h, w) if h > w else (w, h)

    def _pick_font(self, candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
        """Select first available font from candidates."""
        # Pick the first existing font from the candidate list. Don't log
        # during normal operation to keep journal output clean.
        for path in candidates:
            try:
                if Path(path).exists():
                    return ImageFont.truetype(path, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _fit_text(
        self, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int
    ) -> str:
        """Truncate text to fit within max_width."""
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        
        if text_width <= max_width:
            return text

        # Binary search for fitting length
        while text:
            text = text[:-1]
            test_text = text + "…"
            bbox = draw.textbbox((0, 0), test_text, font=font)
            if bbox[2] - bbox[0] <= max_width:
                return test_text
        return ""

    def render_status(self, status: SystemStatus) -> Image.Image:
        """Render system status to an image.

        Args:
            status: System status snapshot

        Returns:
            PIL Image ready for display
        """
        # Ensure driver dimensions are known before composing the image. Some
        # drivers update `self.width`/`self.height` during init, and composing
        # an image with the wrong size will cause clipping on hardware.
        try:
            self._init_driver()
        except Exception:
            # If driver init fails, continue with configured dimensions so we
            # can still produce an image in emulation or degraded mode.
            pass

        img = Image.new("1", (self.width, self.height), 255)
        draw = ImageDraw.Draw(img)

        # Fonts
        # Use a slightly larger title font so the header is readable. Keep
        # conservative sizing to avoid layout overflow on small displays.
        title_font = self._pick_font(TITLE_FONT_CANDIDATES, 18)
        header_font = self._pick_font(MONO_FONT_CANDIDATES, 14)
        body_font = self._pick_font(MONO_FONT_CANDIDATES, 12)
        small_font = self._pick_font(MONO_FONT_CANDIDATES, 10)

        y = 2

        # Title bar (inverted)
        title = "Azazel-Pi"
        bbox = draw.textbbox((0, 0), title, font=title_font)
        title_height = bbox[3] - bbox[1] + 6
        draw.rectangle([(0, 0), (self.width, title_height)], fill=0)
        title_x = (self.width - (bbox[2] - bbox[0])) // 2
        draw.text((title_x, 3), title, font=title_font, fill=255)
        y = title_height + 4

        # Mode and score
        mode_text = f"Mode: {status.security.mode.upper()}"
        score_text = f"Score: {status.security.score_average:.1f}"
        
        # Mode indicator with background
        mode_colors = {
            "portal": (255, 0),    # white bg, black text
            "shield": (0, 255),    # black bg, white text
            "lockdown": (0, 255),  # black bg, white text
        }
        bg_color, text_color = mode_colors.get(status.security.mode, (255, 0))
        
        bbox = draw.textbbox((0, 0), mode_text, font=header_font)
        mode_width = bbox[2] - bbox[0] + 8
        draw.rectangle([(4, y), (4 + mode_width, y + 18)], fill=bg_color)
        draw.text((8, y + 2), mode_text, font=header_font, fill=text_color)
        
        # Score on the right — compute width and ensure it doesn't overlap the
        # mode indicator box. Shift left as needed so the text isn't clipped.
        score_bbox = draw.textbbox((0, 0), score_text, font=header_font)
        score_w = score_bbox[2] - score_bbox[0]
        # Desired x so the score has a small right margin
        score_x = self.width - score_w - 6
        # Minimum x: leave a small gap after the mode box
        min_x_after_mode = 8 + mode_width + 4
        if score_x < min_x_after_mode:
            score_x = min_x_after_mode
        draw.text((score_x, y + 2), score_text, font=header_font, fill=0)
        y += 22

        # Draw a tiny sparkline for recent scores (if available).
        # Use font-independent rectangle bars so the E-Paper hardware
        # doesn't depend on availability of block glyphs. This method
        # renders reliably on real devices.
        try:
            sh = getattr(status.security, "score_history", []) or []
            if sh:
                vals = list(sh[-12:])
                n = len(vals)
                # Sparkline drawing area (left margin 4, right margin 4)
                area_x = 4
                area_w = max(8, self.width - 8)
                area_y = y
                area_h = 10

                # Determine mapping: if constant values, map absolute 0-100
                # so a constant high score appears high; otherwise normalize
                mn = min(vals)
                mx = max(vals)

                bars_total_w = area_w
                bar_w = max(1, bars_total_w // n)
                gap = max(1, bar_w // 6)

                for i, v in enumerate(vals):
                    try:
                        fv = float(v)
                    except Exception:
                        fv = 0.0

                    if mx - mn < 1e-6:
                        # absolute mapping 0..100
                        frac = max(0.0, min(1.0, fv / 100.0))
                    else:
                        frac = (fv - mn) / (mx - mn)

                    bar_h = int(frac * area_h)
                    x0 = area_x + i * bar_w + gap // 2
                    x1 = x0 + bar_w - gap
                    y0 = area_y + (area_h - bar_h)
                    y1 = area_y + area_h
                    # Draw filled rectangle for the bar (black)
                    draw.rectangle([(x0, y0), (x1, y1)], fill=0)

                # Move cursor down after drawing sparkline area
                y += area_h + 4
        except Exception:
            pass

        # Separator line
        draw.line([(0, y), (self.width, y)], fill=0, width=1)
        y += 4

        net_icon = "●" if status.network.is_up else "○"
        primary_iface = status.network.interface
        ip_text = status.network.ip_address or "No IP"
        # Show only the active interface and IP to keep the display concise;
        # remove the literal "WAN" prefix which the user found redundant.
        net_line = f"{net_icon} {primary_iface}: {ip_text}"
        net_line = self._fit_text(draw, net_line, body_font, self.width - 8)
        draw.text((4, y), net_line, font=body_font, fill=0)
        y += 16

        # Only display WAN status messages for meaningful states. Suppress
        # the common/harmless 'unknown' state to avoid clutter.
        if (
            status.network.wan_state
            and status.network.wan_state not in ("ready", "unknown")
        ):
            warn_text = status.network.wan_message or status.network.wan_state
            warn_line = self._fit_text(
                draw,
                f"{warn_text}",
                small_font,
                self.width - 8,
            )
            draw.text((4, y), warn_line, font=small_font, fill=0)
            y += 14

        # Alert counters
        alert_line = f"Alerts: {status.security.recent_alerts}/{status.security.total_alerts} (5m/total)"
        alert_line = self._fit_text(draw, alert_line, body_font, self.width - 8)
        draw.text((4, y), alert_line, font=body_font, fill=0)
        y += 14

        # Service status: show ON/OFF explicitly. Also display the current
        # local time at the right edge of this same row so the bottom area
        # doesn't need a separate uptime footer (uptime removed per request).
        suri_txt = "ON" if status.security.suricata_active else "OFF"
        canary_txt = "ON" if status.security.opencanary_active else "OFF"
        # Short EPD form requested by user: 'Serv: Suri:ON, Canary:OFF'
        svc_line = f"Serv: Suri:{suri_txt}, Canary:{canary_txt}"

        # Time string (local)
        try:
            local_ts = status.timestamp.astimezone()
            time_str = local_ts.strftime("%H:%M:%S")
        except Exception:
            time_str = status.timestamp.strftime("%H:%M:%S")

        # Draw service text at left, time at right
        draw.text((4, y), svc_line, font=body_font, fill=0)
        try:
            tbbox = draw.textbbox((0, 0), time_str, font=body_font)
            tw = tbbox[2] - tbbox[0]
        except Exception:
            tw = 40
        time_x = max(4, self.width - tw - 4)
        draw.text((time_x, y), time_str, font=body_font, fill=0)
        y += 16

        # Prevent any accidental drawing beyond footer by returning image
        # (all content should be complete at this point).

        return img

    def display(self, image: Image.Image, gentle: bool = False) -> None:
        """Display an image on the E-Paper.

        Args:
            image: PIL Image to display
            gentle: Use partial update if available (less flicker)
        """
        self._init_driver()

        # Ensure the driver is initialized (wake from sleep) before attempting display.
        if not self.emulate and getattr(self, "_epd", None) is not None:
            try:
                if hasattr(self._epd, "init"):
                    # Some drivers support re-init to wake the module from sleep.
                    self._epd.init()
            except Exception:
                # If re-init fails, we'll rely on the retry logic below to recreate the driver.
                if self.debug:
                    print("EPD re-init failed; will attempt reinit on retry.", file=sys.stderr)
        # Check for partial update capability
        partial_update = None
        if gentle:
            for method_name in ("displayPartial", "display_Partial", "DisplayPartial"):
                if hasattr(self._epd, method_name):
                    partial_update = getattr(self._epd, method_name)
                    break

        # Apply rotation if requested (handle 180° flip for upside-down displays)
        if getattr(self, "rotation", 0):
            try:
                # Use expand=False to keep target dimensions; 180° is safe for same-size
                image = image.rotate(self.rotation, expand=False)
            except Exception as e:
                if self.debug:
                    print(f"Rotation error: {e}", file=sys.stderr)

        def _do_display():
            """Internal helper to perform the actual display call."""
            buf = self._epd.getbuffer(image)
            if partial_update and gentle:
                partial_update(buf)
            elif self._bicolor:
                # Bicolor display needs red buffer (all white for status display)
                red_buffer = self._epd.getbuffer(Image.new("1", (self.width, self.height), 255))
                self._epd.display(buf, red_buffer)
            else:
                self._epd.display(buf)

        # Try display, on SPI/OS errors attempt one reinit+retry
        try:
            _do_display()
            return
        except Exception as e:
            # Detect common SPI/GPIO issues and attempt recovery once
            is_spi_error = isinstance(e, OSError) or "Bad file descriptor" in str(e) or "GPIO busy" in str(e)
            if self.debug:
                print(f"Display error (first attempt): {e}", file=sys.stderr)
                traceback.print_exc()

            if is_spi_error:
                if self.debug:
                    print("Attempting to reinitialize E-Paper driver and retry display...", file=sys.stderr)
                # Best-effort cleanup — avoid calling driver sleep/module_exit here
                # because that closes the SPI device (module_exit) and can race
                # with ongoing display calls, causing Bad file descriptor errors.
                # Instead, drop our reference and force a reinit on retry.
                self._epd = None

                # Short backoff before retry
                try:
                    import time

                    time.sleep(0.25)
                except Exception:
                    pass

                # Reinit and retry once
                try:
                    self._init_driver()
                    _do_display()
                    if self.debug:
                        print("Retry successful.", file=sys.stderr)
                    return
                except Exception as e2:
                    if self.debug:
                        print(f"Retry failed: {e2}", file=sys.stderr)
                        traceback.print_exc()
                    # Fall through to raise the original exception

            # If not a SPI-related error or retry failed, re-raise
            raise

    def clear(self) -> None:
        """Clear the display."""
        self._init_driver()
        try:
            if hasattr(self._epd, "Clear"):
                self._epd.Clear(0xFF)
            else:
                # Fallback: display blank white image
                blank = Image.new("1", (self.width, self.height), 255)
                self.display(blank, gentle=False)
        except Exception:
            pass

    def sleep(self) -> None:
        """Put the display into sleep mode."""
        if self._epd:
            try:
                self._epd.sleep()
            except Exception:
                pass

    def render_boot_animation(self, steps: int = 10, frame_delay: float = 0.3) -> None:
        """Boot: clear the display to a clean (white) state and keep the module initialized.

        We deliberately do not perform any animated drawing here. The goal is to
        ensure the display is in a known clean state before the daemon's first
        status update. Keeping the module initialized avoids repeated open/close
        of the SPI device which can race with updates.
        """
        # Ensure driver is available and clear the screen to white. Keep the
        # module initialized for subsequent updates.
        try:
            self._init_driver()
            self.clear()
            if self.debug:
                print("Boot: display cleared (white); keeping EPD initialized.", file=sys.stderr)
        except Exception as e:
            # If we can't init the driver at boot, log debug info but don't raise
            # — daemon will attempt normal updates and retry driver init later.
            if self.debug:
                print(f"Boot: failed to init/clear display: {e}", file=sys.stderr)

    def render_shutdown_animation(self, hold_seconds: float = 1.0) -> None:
        """Shutdown: clear the display to a clean (white) state and put module to sleep.

        We avoid rendering any text or animation during shutdown to minimise SPI/GPIO
        activity and reduce the chance of races. If the driver cannot be initialized
        during shutdown, silently skip hardware operations.
        Args:
            hold_seconds: Ignored for the simplified shutdown — left for API
                compatibility.
        """
        try:
            self._init_driver()
            # Clear to white then put hardware to sleep for power savings.
            self.clear()
            try:
                self.sleep()
            except Exception:
                # Best-effort; don't raise during shutdown
                pass
            if self.debug:
                print("Shutdown: display cleared and EPD put to sleep.", file=sys.stderr)
        except Exception as e:
            if self.debug:
                print(f"Shutdown: driver init/clear failed: {e}", file=sys.stderr)
            # Nothing else to do during shutdown
