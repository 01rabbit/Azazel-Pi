#!/usr/bin/env python3
"""E-Paper status display daemon for Azazel Pi."""
from __future__ import annotations

import argparse
import os
import logging
import signal
import sys
import time
from pathlib import Path

# Add project root (/opt/azazel) to sys.path so `import azazel_pi` works
# __file__ = .../azazel_pi/core/display/epd_daemon.py
# parents[0]=display, [1]=core, [2]=azazel_pi, [3]=/opt/azazel (project root)
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from azazel_pi.core.display import EPaperRenderer, StatusCollector
from azazel_pi.core.state_machine import StateMachine


class EPaperDaemon:
    """Daemon to periodically update E-Paper display with system status."""

    def __init__(
        self,
        update_interval: int = 10,
        state_machine_path: Path | None = None,
        events_log: Path | None = None,
        gentle_updates: bool = True,
        debug: bool = False,
        emulate: bool = False,
        rotation: int = 0,
    ):
        """Initialize the daemon.

        Args:
            update_interval: Seconds between display updates
            state_machine_path: Optional path to state machine config
            events_log: Path to events.json log file
            gentle_updates: Use partial updates to reduce flicker
            debug: Enable debug logging
            emulate: Emulation mode (no physical display required)
        """
        self.update_interval = update_interval
        self.gentle_updates = gentle_updates
        self.debug = debug
        self.emulate = emulate
        self.running = False

        # Set up logging
        log_level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.logger = logging.getLogger(__name__)

        # Initialize state machine (optional, for mode/score tracking)
        self.state_machine = None
        if state_machine_path and Path(state_machine_path).exists():
            try:
                # Import the build_machine function from azctl
                from azctl.cli import build_machine

                self.state_machine = build_machine()
                self.logger.info(f"Loaded state machine from {state_machine_path}")
            except Exception as e:
                self.logger.warning(f"Could not load state machine: {e}")

        # Initialize status collector
        self.collector = StatusCollector(
            state_machine=self.state_machine,
            events_log=events_log,
        )

        # Initialize renderer (support rotation)
        try:
            self.rotation = int(rotation) if rotation is not None else 0
        except Exception:
            self.rotation = 0
        self.renderer = EPaperRenderer(debug=debug, emulate=emulate, rotation=self.rotation)

        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals gracefully."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def run(self) -> int:
        """Run the daemon main loop.

        Returns:
            Exit code
        """
        self.logger.info("E-Paper daemon starting...")
        self.running = True

        # Show boot animation unless explicitly disabled via environment
        skip_boot = os.getenv("EPD_SKIP_BOOT_ANIM", os.getenv("AZAZEL_EPD_SKIP_BOOT", "0"))
        if str(skip_boot).lower() in ("1", "true", "yes"):
            self.logger.info("Skipping boot animation (EPD_SKIP_BOOT_ANIM set)")
        else:
            try:
                self.logger.info("Displaying boot animation...")
                self.renderer.render_boot_animation(steps=8, frame_delay=0.2)
                time.sleep(1)
            except Exception as e:
                self.logger.error(f"Boot animation failed: {e}")
                if self.debug:
                    import traceback

                    traceback.print_exc()

        # Main update loop
        update_count = 0
        while self.running:
            try:
                # Collect current status
                status = self.collector.collect()
                update_count += 1

                self.logger.debug(
                    f"Update #{update_count}: mode={status.security.mode}, "
                    f"score={status.security.score_average:.1f}, "
                    f"alerts={status.security.recent_alerts}/{status.security.total_alerts}"
                )

                # Render and display
                image = self.renderer.render_status(status)
                
                # Use gentle updates after the first one
                gentle = self.gentle_updates and update_count > 1
                self.renderer.display(image, gentle=gentle)
                self.renderer.sleep()

                # Wait for next update (with early exit on shutdown)
                for _ in range(self.update_interval):
                    if not self.running:
                        break
                    time.sleep(1)

            except KeyboardInterrupt:
                self.logger.info("Interrupted by user")
                break
            except Exception as e:
                self.logger.error(f"Update error: {e}")
                if self.debug:
                    import traceback

                    traceback.print_exc()
                # Continue running despite errors
                time.sleep(self.update_interval)

        # Shutdown sequence
        self.logger.info("E-Paper daemon shutting down...")
        try:
            self.renderer.render_shutdown_animation(hold_seconds=1.5)
        except Exception as e:
            self.logger.error(f"Shutdown animation failed: {e}")
            try:
                self.renderer.clear()
                self.renderer.sleep()
            except Exception:
                pass

        self.logger.info("E-Paper daemon stopped")
        return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="E-Paper status display daemon for Azazel Pi"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Update interval in seconds (default: 10)",
    )
    parser.add_argument(
        "--events-log",
        type=Path,
        default=Path("/var/log/azazel/events.json"),
        help="Path to events.json log file",
    )
    parser.add_argument(
        "--state-config",
        type=Path,
        help="Path to state machine config (optional)",
    )
    parser.add_argument(
        "--no-gentle",
        action="store_true",
        help="Disable gentle (partial) updates",
    )
    parser.add_argument(
        "--mode",
        choices=["daemon", "boot", "shutdown", "test"],
        default="daemon",
        help="Operation mode: daemon (run continuously), boot (show animation), "
        "shutdown (show shutdown screen), test (single update)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output",
    )
    parser.add_argument(
        "--emulate",
        action="store_true",
        help="Emulation mode (no physical E-Paper required)",
    )
    parser.add_argument(
        "--rotate",
        type=int,
        default=int(os.getenv("EPD_ROTATION", "0")),
        help="Rotate display output in degrees (0,90,180,270). Can also be set via EPD_ROTATION env var.",
    )

    args = parser.parse_args()

    # Quick mode handlers
    if args.mode == "boot":
        renderer = EPaperRenderer(debug=args.debug, emulate=args.emulate, rotation=args.rotate)
        renderer.render_boot_animation(steps=10, frame_delay=0.25)
        return 0

    if args.mode == "shutdown":
        renderer = EPaperRenderer(debug=args.debug, emulate=args.emulate, rotation=args.rotate)
        renderer.render_shutdown_animation(hold_seconds=1.5)
        return 0

    if args.mode == "test":
        collector = StatusCollector(events_log=args.events_log)
        renderer = EPaperRenderer(debug=args.debug, emulate=args.emulate, rotation=args.rotate)
        status = collector.collect()
        image = renderer.render_status(status)

        # Display (which will apply rotation internally), then sleep
        renderer.display(image, gentle=False)
        renderer.sleep()

        # In emulation mode, save the image as it would appear on the display
        # (apply the renderer rotation before saving so test output matches
        # what hardware would receive).
        if args.emulate:
            output_path = "/tmp/azazel_epd_test.png"
            try:
                rot = getattr(renderer, "rotation", 0)
                if rot:
                    save_img = image.rotate(rot, expand=False)
                else:
                    save_img = image
                save_img.save(output_path)
                print(f"Emulation mode: Image saved to {output_path} (rotation={rot})")
            except Exception as e:
                # Best-effort fallback — save the original image
                try:
                    image.save(output_path)
                    print(f"Emulation mode: Image saved to {output_path} (fallback, error: {e})")
                except Exception:
                    print(f"Emulation mode: failed to save image: {e}")

        return 0

    # Daemon mode
    daemon = EPaperDaemon(
        update_interval=args.interval,
        state_machine_path=args.state_config,
        events_log=args.events_log,
        gentle_updates=not args.no_gentle,
        debug=args.debug,
        emulate=args.emulate,
        rotation=args.rotate,
    )
    return daemon.run()


if __name__ == "__main__":
    sys.exit(main())
