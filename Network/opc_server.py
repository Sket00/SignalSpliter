## @file opc_server.py
#  @brief OPC UA Server for remote routing control and status monitoring.

import asyncio
import threading
import time
from asyncua import Server, ua, uamethod
from Utils.logger import log, memory_handler


## @class OpcServer
#  @brief Runs the OPC UA Server asynchronously in a background thread.
#  @details Designed for 24/7 operation. If the async loop crashes (e.g., port binding 
#           issue, client-triggered exception), the thread does not die silently. 
#           It logs the traceback and instantiates a fresh server after a delay, 
#           ensuring remote control is ultimately restored.
class OpcServer(threading.Thread):
    RESTART_DELAY_SEC = 5

    ## @brief Initializes the OPC UA Server thread.
    #  @param gui MatrixGUI instance - source of the routing state exposed to clients.
    #  @param lock_mgr LockManager instance - arbitrates local vs. remote control access.
    #  @param runtime_tracker RuntimeTracker instance - provides the total device runtime.
    def __init__(self, gui, lock_mgr, runtime_tracker):
        super().__init__()
        self.daemon = True
        self.gui = gui
        self.lock_mgr = lock_mgr
        self.runtime_tracker = runtime_tracker
        self.loop = asyncio.new_event_loop()
        self.server = Server()
        self._stop_requested = False

    ## @brief Background thread entry point. Handles the event loop and crash recovery.
    def run(self):
        asyncio.set_event_loop(self.loop)
        while not self._stop_requested:
            try:
                self.loop.run_until_complete(self._async_run())
                log.warning("[OPC] OPC UA server exited without an exception. Restarting...")
            except Exception as e:
                log.error(f"[OPC] OPC UA server crashed with error: {e}", exc_info=True)

            if self._stop_requested:
                break

            log.info(f"[OPC] Attempting to restart OPC UA server in {self.RESTART_DELAY_SEC}s...")
            time.sleep(self.RESTART_DELAY_SEC)
            
            # Create a new Server instance - the old one might be in an inconsistent state 
            # following an exception (e.g., partially initialized endpoints).
            self.server = Server()

    ## @brief Gracefully signals the server thread to stop.
    def stop(self):
        self._stop_requested = True

    ## @brief Main async coroutine that configures endpoints, exposes nodes, and updates data.
    async def _async_run(self):
        await self.server.init()
        self.server.set_endpoint("opc.tcp://0.0.0.0:4840/freeopcua/server/")
        self.server.set_server_name("SignalSplitter OPC Server")
        idx = await self.server.register_namespace("http://signalsplitter.local")
        myobj = await self.server.nodes.objects.add_object(idx, "Matrix")

        # --- READ-ONLY VARIABLES ---
        var_in1 = await myobj.add_variable(idx, "IN1_Output", 0)
        var_in2 = await myobj.add_variable(idx, "IN2_Output", 0)
        var_lock = await myobj.add_variable(idx, "Lock_Owner", "FREE")
        var_logs = await myobj.add_variable(idx, "Recent_Logs", [""])
        var_runtime = await myobj.add_variable(idx, "Total_Runtime_Hours", 0.0)

        # --- OPC UA METHODS ---
        @uamethod
        def RouteSignal(parent, in_ch: int, out_ch: int, client_id: str) -> str:
            try:
                # Check permissions against the Lock Manager
                if not self.lock_mgr.try_acquire(client_id):
                    return f"Access Denied. Lock held by {self.lock_mgr.owner} (Priority: {self.lock_mgr.priority})"
                if in_ch not in [1, 2]:
                    return "Error: Invalid Input (Must be 1 or 2)"
                if out_ch < 0 or out_ch > 16:
                    return "Error: Invalid Output (0-16)"
                    
                # Update GUI state. main.py will detect this change, physically switch 
                # the relays, and log the route event attributing it to this client_id.
                self.gui.input_assignment[in_ch] = out_ch if out_ch > 0 else None
                self.lock_mgr.update_activity()
                return "Success: Routing initiated"
            except Exception as e:
                # Method called by a remote client - prevent an exception here 
                # from killing the entire server thread. Log and return safely.
                log.error(f"[OPC] RouteSignal error: {e}", exc_info=True)
                return f"Error: Internal server error ({e})"

        @uamethod
        def ReleaseLock(parent, client_id: str) -> str:
            try:
                if self.lock_mgr.owner == client_id:
                    self.lock_mgr.release(client_id)
                    return "Success: Lock released"
                return "Error: You do not own the lock"
            except Exception as e:
                log.error(f"[OPC] ReleaseLock error: {e}", exc_info=True)
                return f"Error: Internal server error ({e})"

        # Register methods to the OPC object
        await myobj.add_method(idx, "RouteSignal", RouteSignal,
                               [ua.VariantType.Int32, ua.VariantType.Int32, ua.VariantType.String],
                               [ua.VariantType.String])
        await myobj.add_method(idx, "ReleaseLock", ReleaseLock,
                               [ua.VariantType.String],
                               [ua.VariantType.String])

        log.info("[OPC] OPC UA Server started on port 4840")

        # Loop updating variable values for connected OPC clients
        async with self.server:
            while not self._stop_requested:
                try:
                    out1 = self.gui.input_assignment.get(1)
                    out2 = self.gui.input_assignment.get(2)
                    
                    await var_in1.write_value(out1 if out1 else 0)
                    await var_in2.write_value(out2 if out2 else 0)
                    
                    lock_status = self.lock_mgr.owner if self.lock_mgr.owner else "FREE"
                    await var_lock.write_value(lock_status)
                    
                    recent_logs = list(memory_handler.history)
                    if not recent_logs:
                        recent_logs = ["No logs yet."]
                    await var_logs.write_value(recent_logs)
                    
                    await var_runtime.write_value(round(self.runtime_tracker.total_hours, 2))
                except Exception as e:
                    # A single update failure (e.g., node write error) shouldn't 
                    # crash the server loop. Log and retry on the next iteration.
                    log.error(f"[OPC] Variable update error: {e}", exc_info=True)
                
                await asyncio.sleep(0.5)
