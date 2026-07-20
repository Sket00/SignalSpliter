## @file main.py
#  @brief Main orchestrator with integrated Lock Management, GUI, OPC UA, and runtime tracking.
#  @details Incorporates a systemd watchdog (sdnotify) to protect against thread hangs
#           (e.g., blocked I2C/SPI calls) by triggering an automatic process restart.

import time

from Utils.logger import log
from Config import settings
from Display.screen_manager import ScreenManager
from Encoder.twist_driver import EncoderHandler
from Expander.relay_board import RelayBoard
from Interface.gui_matrix import MatrixGUI
from Utils.lock_manager import LockManager
from Utils.runtime_tracker import RuntimeTracker
from Network.opc_server import OpcServer

# --- SYSTEMD WATCHDOG --------------------------------------------------
# Fallback dummy functions if sdnotify is not installed (e.g., local testing).
try:
    import sdnotify
    _notifier = sdnotify.SystemdNotifier()

    def notify_watchdog():
        _notifier.notify("WATCHDOG=1")

    def notify_ready():
        _notifier.notify("READY=1")

except ImportError:
    log.warning("[WATCHDOG] 'sdnotify' package not installed - systemd watchdog disabled.")

    def notify_watchdog():
        pass

    def notify_ready():
        pass


## @brief Converts a hexadecimal color string to an RGB tuple.
#  @param hex_color Color in hex format (e.g., "#FF0000" or "FF0000").
#  @return A tuple containing (R, G, B) integer values.
def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


## @brief Main entry point of the SignalSplitter application.
#  @details Initializes hardware interfaces, graphical user interface, OPC UA server,
#           and executes the main loop handling events, displays, and watchdog.
def main():
    log.info("Starting SignalSplitter System...")
    display = ScreenManager()
    encoder = EncoderHandler()
    relays = RelayBoard()
    lock = LockManager()
    runtime = RuntimeTracker(settings.RUNTIME_FILE)

    canvas_w = settings.DISPLAY_HEIGHT if settings.LANDSCAPE else settings.DISPLAY_WIDTH
    canvas_h = settings.DISPLAY_WIDTH if settings.LANDSCAPE else settings.DISPLAY_HEIGHT
    gui = MatrixGUI(canvas_w, canvas_h)
    gui.runtime_tracker = runtime  # Shared for rendering in the SETTINGS screen

    opc = OpcServer(gui, lock, runtime)
    opc.start()

    if display.disp is not None:
        display.show(gui.render(lock))
    encoder.set_color(0, 122, 204)
    
    current_led = None
    last_assignments = gui.input_assignment.copy()

    SCREENSAVER_TIMEOUT = 45
    SAVER_FRAME_INTERVAL = 1.0 / 15.0  # 15 FPS
    ENCODER_POLL_INTERVAL_SAVER = 0.10   # 10 Hz wake-up detection
    LOCK_CHECK_INTERVAL_SAVER = 0.20      # Avoid high-frequency lock checks during animation
    DISPLAY_RETRY_INTERVAL = 5.0          # Seconds between dead display recovery attempts
    RUNTIME_LOG_INTERVAL = 3600.0         # Log runtime hourly

    last_activity_time = time.monotonic()
    prev_screen = gui.screen
    next_saver_frame_time = 0.0
    next_encoder_poll_time = 0.0
    next_lock_check_time = 0.0
    next_display_retry_time = 0.0
    next_runtime_log_time = time.monotonic() + RUNTIME_LOG_INTERVAL

    notify_ready()
    log.info("System Ready. Waiting for interactions...")

    try:
        while True:
            # --- SYSTEMD WATCHDOG PING ---
            # Placed at the loop start to ensure that if any subsequent call 
            # (e.g., I2C/SPI) hangs, the ping stops and systemd restarts the process.
            notify_watchdog()

            # Use monotonic time to avoid NTP sync jumps
            now = time.monotonic()

            runtime.tick()
            if now >= next_runtime_log_time:
                log.info(f"[RUNTIME] total_hours={runtime.total_hours:.1f} session_hours={runtime.session_hours:.2f}")
                next_runtime_log_time = now + RUNTIME_LOG_INTERVAL

            # --- DISPLAY RETRY ---
            # Periodically attempt to reconnect if the SPI/LCD failed during startup or runtime.
            if display.disp is None:
                if now >= next_display_retry_time:
                    log.warning("[SYSTEM] Display unavailable, attempting to reconnect...")
                    display.connect()
                    next_display_retry_time = now + DISPLAY_RETRY_INTERVAL
                    if display.disp is not None:
                        # Force full redraw on fresh connection
                        prev_screen = None

            if encoder.twist is None:
                log.warning("[SYSTEM] Qwiic Twist encoder missing or failed. Attempting to reconnect...")
                encoder.connect()
                current_led = None
                time.sleep(0.5)
                continue

            # Throttle encoder I2C reads in screensaver mode
            if gui.screen == "SCREENSAVER":
                if now >= next_encoder_poll_time:
                    diff, is_clicked = encoder.get_events()
                    next_encoder_poll_time = now + ENCODER_POLL_INTERVAL_SAVER
                else:
                    diff, is_clicked = 0, False
            else:
                diff, is_clicked = encoder.get_events()

            current_owner = lock.get_owner() if hasattr(lock, 'get_owner') else lock.owner
            
            if gui.screen == "SCREENSAVER":
                if now >= next_lock_check_time:
                    needs_update = lock.check_timeout()
                    next_lock_check_time = now + LOCK_CHECK_INTERVAL_SAVER
                else:
                    needs_update = False
            else:
                needs_update = lock.check_timeout()

            if diff != 0 or is_clicked:
                last_activity_time = now

            if diff != 0:
                log.debug(f"[ENCODER] Movement detected: {diff}, lock owner before action: {current_owner}")
                for _ in range(abs(diff)):
                    if diff > 0: gui.encoder_right(lock)
                    else: gui.encoder_left(lock)
                if lock.owner == "LOCAL": lock.update_activity()
                needs_update = True

            if is_clicked:
                gui.handle_click(lock)
                needs_update = True

            if gui.screen != "SCREENSAVER" and now - last_activity_time >= SCREENSAVER_TIMEOUT:
                gui.enter_screensaver()

            if gui.screen != prev_screen:
                needs_update = True
                prev_screen = gui.screen
                next_saver_frame_time = 0.0  # Resync pacing upon entering screensaver

            # Target-based pacing to prevent drift
            if gui.screen == "SCREENSAVER":
                if now >= next_saver_frame_time:
                    needs_update = True
                    # Reset rhythm after a missed frame instead of rushing to catch up
                    next_saver_frame_time = now + SAVER_FRAME_INTERVAL

            if gui.input_assignment != last_assignments:
                # Determine routing change source for logging (local vs OPC)
                route_source = lock.get_owner() or "UNKNOWN"
                for in_num in (1, 2):
                    if gui.input_assignment.get(in_num) != last_assignments.get(in_num):
                        out_num = gui.input_assignment.get(in_num)
                        if out_num is not None:
                            try:
                                relays.route_signal(in_num, out_num, source=route_source)
                            except Exception as e:
                                # Prevent a single relay/expander failure from crashing the main loop
                                log.error(f"[SYSTEM] Error in route_signal(IN{in_num}->OUT{out_num}): {e}", exc_info=True)
                        else:
                            log.info(f"[ROUTE] source={route_source} in={in_num} out=DISCONNECTED")
                last_assignments = gui.input_assignment.copy()
                needs_update = True

            current_owner = lock.get_owner() if hasattr(lock, 'get_owner') else lock.owner

            if needs_update or current_owner != current_led:
                image = gui.render(lock)
                display.show(image)

                if current_owner != current_led:
                    log.info(f"[LED] State changed from '{current_led}' to '{current_owner}'")
                    current_led = current_owner
                    if current_owner is None or current_owner == "FREE":
                        encoder.set_color(0, 0, 0)
                    elif current_owner == "LOCAL":
                        encoder.set_color(0, 255, 0)
                    else:
                        encoder.set_color(0, 0, 255)
                    time.sleep(0.05)

            time.sleep(0.01)

    except KeyboardInterrupt:
        pass
    except Exception as e:
        # exc_info=True appends the full traceback for accurate debugging
        log.error(f"[SYSTEM] CRITICAL ERROR: {e}", exc_info=True)
    finally:
        log.info("System shutting down...")
        display.clear()
        encoder.set_color(0, 0, 0)


if __name__ == '__main__':
    main()
