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
        img = Image.new("1", (self.width, self.height), 255)
        draw = ImageDraw.Draw(img)

        # Fonts
        title_font = self._pick_font(TITLE_FONT_CANDIDATES, 16)
        header_font = self._pick_font(MONO_FONT_CANDIDATES, 14)
        body_font = self._pick_font(MONO_FONT_CANDIDATES, 12)

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
        
        # Score on the right
        draw.text((self.width - 80, y + 2), score_text, font=header_font, fill=0)
        y += 22

        # Separator line
        draw.line([(0, y), (self.width, y)], fill=0, width=1)
        y += 4

        # Network status
        net_icon = "●" if status.network.is_up else "○"
        ip_text = status.network.ip_address or "No IP"
        net_line = f"{net_icon} {status.network.interface}: {ip_text}"
        net_line = self._fit_text(draw, net_line, body_font, self.width - 8)
        draw.text((4, y), net_line, font=body_font, fill=0)
        y += 16

        # Alert counters
        alert_line = f"Alerts: {status.security.recent_alerts}/{status.security.total_alerts} (5m/total)"
        alert_line = self._fit_text(draw, alert_line, body_font, self.width - 8)
        draw.text((4, y), alert_line, font=body_font, fill=0)
        y += 16

        # Service status
        suri_status = "✓" if status.security.suricata_active else "✗"
        canary_status = "✓" if status.security.opencanary_active else "✗"
        svc_line = f"Svc: Suri{suri_status} Canary{canary_status}"
        draw.text((4, y), svc_line, font=body_font, fill=0)
        y += 16

        # Uptime and timestamp
        uptime_hours = status.uptime_seconds // 3600
        uptime_mins = (status.uptime_seconds % 3600) // 60
        time_str = status.timestamp.strftime("%H:%M:%S")
        footer = f"Up {uptime_hours}h{uptime_mins}m | {time_str}"
        footer = self._fit_text(draw, footer, body_font, self.width - 8)
        draw.text((4, self.height - 14), footer, font=body_font, fill=0)

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
                # Best-effort cleanup
                try:
                    if hasattr(self._epd, "sleep"):
                        try:
                            self._epd.sleep()
                        except Exception:
                            pass
                finally:
                    # Drop reference so _init_driver will recreate it
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
        """Display a boot progress animation.

        Args:
            steps: Number of animation steps
            frame_delay: Delay between frames in seconds
        """
        import time

        self._init_driver()
        self.clear()

        title_font = self._pick_font(TITLE_FONT_CANDIDATES, 18)
        body_font = self._pick_font(MONO_FONT_CANDIDATES, 12)

        for i in range(steps + 1):
            img = Image.new("1", (self.width, self.height), 255)
            draw = ImageDraw.Draw(img)

            # Title (inverted)
            title = "Azazel-Pi"
            bbox = draw.textbbox((0, 0), title, font=title_font)
            title_height = bbox[3] - bbox[1] + 8
            draw.rectangle([(0, 0), (self.width, title_height)], fill=0)
            title_x = (self.width - (bbox[2] - bbox[0])) // 2
            draw.text((title_x, 4), title, font=title_font, fill=255)

            # Progress bar
            bar_y = title_height + 20
            bar_height = 16
            bar_margin = 10
            bar_width = self.width - (2 * bar_margin)

            # Border
            draw.rectangle(
                [(bar_margin, bar_y), (self.width - bar_margin, bar_y + bar_height)],
                outline=0,
                width=2,
            )

            # Fill
            progress = i / steps
            fill_width = int((bar_width - 4) * progress)
            if fill_width > 0:
                draw.rectangle(
                    [(bar_margin + 2, bar_y + 2), (bar_margin + 2 + fill_width, bar_y + bar_height - 2)],
                    fill=0,
                )

            # Status text
            status_text = f"Booting... {int(progress * 100)}%"
            bbox = draw.textbbox((0, 0), status_text, font=body_font)
            text_x = (self.width - (bbox[2] - bbox[0])) // 2
            draw.text((text_x, bar_y + bar_height + 8), status_text, font=body_font, fill=0)

            # Display with gentle update after first frame
            self.display(img, gentle=(i > 0))
            time.sleep(frame_delay)

        self.sleep()

    def render_shutdown_animation(self, hold_seconds: float = 1.0) -> None:
        """Display a shutdown message and clear.

        Args:
            hold_seconds: How long to show the message before clearing
        """
        import time

        self._init_driver()

        title_font = self._pick_font(TITLE_FONT_CANDIDATES, 18)
        body_font = self._pick_font(MONO_FONT_CANDIDATES, 14)

        img = Image.new("1", (self.width, self.height), 255)
        draw = ImageDraw.Draw(img)

        # Title (inverted)
        title = "Azazel-Pi"
        bbox = draw.textbbox((0, 0), title, font=title_font)
        title_height = bbox[3] - bbox[1] + 8
        draw.rectangle([(0, 0), (self.width, title_height)], fill=0)
        title_x = (self.width - (bbox[2] - bbox[0])) // 2
        draw.text((title_x, 4), title, font=title_font, fill=255)

        # Shutdown message
        message = "Shutting down..."
        bbox = draw.textbbox((0, 0), message, font=body_font)
        msg_x = (self.width - (bbox[2] - bbox[0])) // 2
        msg_y = (self.height - (bbox[3] - bbox[1])) // 2
        draw.text((msg_x, msg_y), message, font=body_font, fill=0)

        self.display(img, gentle=False)
        time.sleep(hold_seconds)
        self.clear()
        self.sleep()
