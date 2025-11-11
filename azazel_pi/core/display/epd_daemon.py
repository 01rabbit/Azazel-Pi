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
from azazel_pi.core.config import AzazelConfig
from collections import deque
from pathlib import Path


class EPaperDaemon:
    """Daemon to periodically update E-Paper display with system status."""

    def __init__(
        self,
        update_interval: int = 10,
        *,
        state_machine_path: Path | None = None,
        events_log: Path | None = None,
        wan_state_path: Path | None = None,
        gentle_updates: bool = True,
        full_refresh_minutes: int = 30,
        debug: bool = False,
        emulate: bool = False,
        rotation: int = 0,
        power_save: bool = False,
    ) -> None:
        """Initialize the EPaperDaemon.

        Keyword args (aside from positional `update_interval`):
            update_interval: Seconds between display updates (positional)
            state_machine_path: Optional path to a state-machine config used
                to construct an internal StateMachine instance (if present).
            events_log: Path to events.json for alert counting (defaults to
                /var/log/azazel/events.json when not provided to StatusCollector).
            wan_state_path: Optional explicit path to the WAN state JSON file
                (overrides $AZAZEL_WAN_STATE_PATH and other fallbacks).
            gentle_updates: Use partial/fast updates to reduce flicker (default True).
            full_refresh_minutes: Perform a non-partial full refresh every N minutes
                to reduce E-Paper ghosting. Set 0 to disable.
            debug: Enable debug-level logging and additional trace output.
            emulate: Emulation mode (does not require physical E-Paper hardware).
            rotation: Display rotation in degrees (0, 90, 180, 270).
            power_save: If True, attempt to sleep the EPD after each update
                (may increase chance of SPI/device races; default False).
        """
        # Core runtime configuration
        self.update_interval = int(update_interval)
        self.gentle_updates = bool(gentle_updates)
        self.debug = bool(debug)
        self.emulate = bool(emulate)
        self.running = False
        self.power_save = bool(power_save)
        # Periodic full-refresh interval in minutes. If > 0, the daemon will
        # perform a full (non-gentle) refresh every `full_refresh_minutes`
        # minutes to reduce E-Paper ghosting from repeated partial updates.
        try:
            self.full_refresh_minutes = int(full_refresh_minutes)
        except Exception:
            self.full_refresh_minutes = 0

        # Set up logging
        log_level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.logger = logging.getLogger(__name__)

        # Initialize state machine (optional, for mode/score tracking).
        # Try to build a StateMachine when either an explicit state_machine_path
        # is provided or a system config exists at /etc/azazel/azazel.yaml.
        self.state_machine = None
        try:
            config_path = None
            if state_machine_path and Path(state_machine_path).exists():
                config_path = Path(state_machine_path)
            else:
                # Fall back to system config if present
                system_cfg = Path(os.getenv('AZAZEL_CONFIG_PATH', '/etc/azazel/azazel.yaml'))
                if system_cfg.exists():
                    config_path = system_cfg

            if config_path is not None:
                try:
                    from azctl.cli import build_machine

                    self.state_machine = build_machine()
                    # Load config and apply optional scoring tuning (ewma_tau/window_size)
                    try:
                        cfg = AzazelConfig.from_file(str(config_path))
                        scoring = cfg.get('scoring', {}) or {}
                        if 'ewma_tau' in scoring:
                            try:
                                self.state_machine.ewma_tau = float(scoring.get('ewma_tau'))
                            except Exception:
                                pass
                        if 'window_size' in scoring:
                            try:
                                self.state_machine.window_size = int(scoring.get('window_size'))
                                self.state_machine._score_window = deque(maxlen=max(self.state_machine.window_size, 1))
                            except Exception:
                                pass
                    except Exception:
                        # Non-fatal: continue even if config can't be parsed
                        pass
                    self.logger.info(f"Loaded state machine (config: {config_path})")
                except Exception as e:
                    self.logger.warning(f"Could not load state machine: {e}")
        except Exception:
            # Defensive: keep running even if state machine init fails
            self.state_machine = None

    # Initialize status collector (allow explicit wan_state_path for testing).
        # Some installed copies of StatusCollector may not accept the
        # wan_state_path kwarg (older deployments). Attempt to pass the
        # argument but fall back to calling without it for compatibility.
        try:
            self.collector = StatusCollector(
                state_machine=self.state_machine,
                events_log=events_log,
                wan_state_path=wan_state_path,
            )
        except TypeError:
            # Backwards-compatible fallback for older StatusCollector API
            self.logger.debug("StatusCollector.__init__ does not accept wan_state_path; using fallback call")
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
        # Track last seen WAN state so we can detect interface-driven
        # transitions (e.g. when WAN manager sets status to "reconfiguring").
        # On such transitions we clear the E-Paper to a clean white state
        # before rendering the next update to avoid flicker/ghosting.
        self._last_wan_state: str | None = None
        # Track last seen active interface so we can detect when the
        # active WAN interface switches (e.g. eth0 -> wlan1). When this
        # happens perform a short clear + force a full refresh to avoid
        # ghosting/artifacts from partial updates.
        self._last_interface: str | None = None
        # Track last seen security mode so mode transitions can trigger
        # a full refresh on the E-Paper display (reduce ghosting/artifacts
        # after a mode switch). Initialized to None so the first update
        # won't be considered a transition.
        self._last_mode: str | None = None

        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals gracefully."""
        # Power-save mode: if True, put the EPD to sleep after each update.
        # Controlled by CLI flag --power-save or environment EPD_POWER_SAVE.
        env_ps = os.getenv("EPD_POWER_SAVE", os.getenv("AZAZEL_EPD_POWER_SAVE", "0"))
        try:
            env_ps_bool = str(env_ps).lower() in ("1", "true", "yes")
        except Exception:
            env_ps_bool = False
        # Ensure we reference the instance attribute; avoid NameError when
        # a signal arrives.
        try:
            self.power_save = bool(self.power_save) or env_ps_bool
        except Exception:
            self.power_save = env_ps_bool
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def run(self) -> int:
        """Run the daemon main loop.

        Returns:
            Exit code
        """
        self.logger.info("E-Paper daemon starting...")
        self.running = True

        # Boot animation intentionally disabled by default to reduce SPI/GPIO activity
        # and avoid timing races during early boot. The renderer's boot helper now
        # performs a simple clear-to-white; do not run animated sequences here.
        self.logger.debug("Boot animation suppressed (static clear-only behavior)")

        # Main update loop
        update_count = 0
        while self.running:
            try:
                # Collect current status
                status = self.collector.collect()
                update_count += 1

                # If WAN state transitioned to a reconfiguration event,
                # clear the display briefly before rendering the updated
                # status. This helps avoid artifacts when the active
                # interface changes (WAN manager writes 'reconfiguring'
                # into the runtime WAN state during switch). Force a
                # full refresh for this update to ensure a clean output.
                force_full_refresh = False
                try:
                    current_wan_state = getattr(status.network, "wan_state", None)
                    current_interface = getattr(status.network, "interface", None)
                    current_mode = getattr(status.security, "mode", None)
                    if self._last_wan_state != current_wan_state and current_wan_state == "reconfiguring":
                        self.logger.info("WAN reconfiguration detected: clearing display before update")
                        try:
                            # Best-effort clear — ignore hardware errors here.
                            self.renderer.clear()
                        except Exception as e:
                            self.logger.debug(f"Display clear failed: {e}")
                        force_full_refresh = True
                    # If the active interface changed (e.g. eth0 -> wlan1),
                    # perform a clear + force full refresh so the new
                    # interface/IP is shown cleanly. Skip on initial run
                    # when we don't have a previous value.
                    if (
                        current_interface is not None
                        and self._last_interface is not None
                        and current_interface != self._last_interface
                    ):
                        self.logger.info(
                            f"WAN interface changed: {self._last_interface} -> {current_interface}; clearing display"
                        )
                        try:
                            self.renderer.clear()
                        except Exception as e:
                            self.logger.debug(f"Display clear on interface change failed: {e}")
                        force_full_refresh = True
                    # If the security mode itself changed since the last
                    # update, perform a clear + full refresh so the new
                    # mode is displayed cleanly on the EPD. We avoid
                    # treating the initial run as a transition.
                    try:
                        if (
                            self._last_mode is not None
                            and current_mode is not None
                            and current_mode != self._last_mode
                        ):
                            self.logger.info(f"Mode transition detected: {self._last_mode} -> {current_mode}; forcing full refresh")
                            try:
                                self.renderer.clear()
                            except Exception as e:
                                self.logger.debug(f"Display clear on mode change failed: {e}")
                            force_full_refresh = True
                    except Exception:
                        pass
                except Exception:
                    # Conservative: if any error occurs, don't prevent normal update
                    pass

                self.logger.debug(
                    f"Update #{update_count}: mode={status.security.mode}, "
                    f"score={status.security.score_average:.1f}, "
                    f"alerts={status.security.recent_alerts}/{status.security.total_alerts}"
                )

                # Render and display
                image = self.renderer.render_status(status)
                
                # Use gentle updates after the first one
                gentle = self.gentle_updates and update_count > 1

                # If periodic full-refresh is enabled, compute whether this
                # update should be a full refresh. We convert the minutes
                # interval into an update-frequency based on update_interval
                # (in seconds). If the current update_count hits that
                # frequency, force a full refresh (gentle=False).
                if self.full_refresh_minutes and self.update_interval > 0:
                    try:
                        secs_per_full = max(1, int(self.full_refresh_minutes) * 60)
                        updates_per_full = max(1, secs_per_full // self.update_interval)
                        if update_count % updates_per_full == 0:
                            gentle = False
                    except Exception:
                        # On any error, keep existing gentle selection
                        pass
                # Display (keep module initialized). Putting the module to
                # sleep after every update causes the driver to call
                # epdconfig.module_exit() (closing the SPI device) which can
                # race with subsequent updates and produce "Bad file descriptor".
                # Keep the display initialized and only sleep on shutdown.
                # If we detected a WAN reconfiguration transition, force a
                # full (non-gentle) refresh for this specific update so the
                # display shows a clean, consistent output.
                if force_full_refresh:
                    gentle = False
                self.renderer.display(image, gentle=gentle)

                # Optionally put the module to sleep after each update when
                # power-save mode is enabled. Disabled by default to avoid
                # module_exit / SPI.close() races; enabling this will trade
                # lower power consumption for a higher chance of races.
                if self.power_save:
                    try:
                        self.renderer.sleep()
                    except Exception:
                        if self.debug:
                            import traceback

                            traceback.print_exc()
                # Remember last seen WAN state for next iteration's transition detection
                try:
                    self._last_wan_state = getattr(status.network, "wan_state", None)
                    try:
                        self._last_interface = getattr(status.network, "interface", None)
                    except Exception:
                        pass
                    # Remember last seen security mode for transition detection
                    try:
                        self._last_mode = getattr(status.security, "mode", None)
                    except Exception:
                        pass
                except Exception:
                    pass
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
        "--power-save",
        action="store_true",
        help="Enable per-update EPD sleep (power saving). Default: disabled; can also be set via EPD_POWER_SAVE env var.",
    )
    parser.add_argument(
        "--rotate",
        type=int,
        default=int(os.getenv("EPD_ROTATION", "0")),
        help="Rotate display output in degrees (0,90,180,270). Can also be set via EPD_ROTATION env var.",
    )
    parser.add_argument(
        "--full-refresh-minutes",
        type=int,
        default=int(os.getenv("EPD_FULL_REFRESH_MINUTES", "30")),
        help="Perform a full (non-partial) refresh every N minutes to reduce e-paper ghosting. Set 0 to disable (default: 30)",
    )
    parser.add_argument(
        "--wan-state-path",
        type=Path,
        help="Optional path to WAN state JSON file (overrides AZAZEL_WAN_STATE_PATH)",
    )
    parser.add_argument(
        "--emulate-output",
        type=Path,
        default=Path("/tmp/azazel_epd_test.png"),
        help="When in --mode test and --emulate is set, save the output image to this path",
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
        collector = StatusCollector(events_log=args.events_log, wan_state_path=args.wan_state_path)
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
            output_path = str(args.emulate_output)
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
        power_save=args.power_save,
        state_machine_path=args.state_config,
        events_log=args.events_log,
        wan_state_path=args.wan_state_path,
        gentle_updates=not args.no_gentle,
        debug=args.debug,
        emulate=args.emulate,
        rotation=args.rotate,
        full_refresh_minutes=args.full_refresh_minutes,
    )
    return daemon.run()


if __name__ == "__main__":
    sys.exit(main())
