import time
import smbus2
from Config import settings
from Utils.logger import log

## @file relay_board.py
#  @brief Hardware abstraction for relay matrix handling crossover logic and binary trees.
#  @details Supports dynamic routing for a dual-input (IN1, IN2) to 16-output setup
#  using 22 shared control lines (crossover switches on the final stage).

# MCP23017 Register addresses (assuming IOCON.BANK = 0)
IODIRA = 0x00
IODIRB = 0x01
GPIOA  = 0x12
GPIOB  = 0x13

## @brief Logical-to-Physical Pin Mapping.
#  Maps logical function names (CTRL_1 to CTRL_22) to specific integer bit indexes.
#  Bit 0-15 could be Expander 1, Bits 16+ could be Expander 2.
PIN_MAP = {
    'CTRL_1': 1, 'CTRL_2': 2, 'CTRL_3': 3, 'CTRL_4': 4,
    'CTRL_5': 5, 'CTRL_6': 12, 'CTRL_7': 13,
    'CTRL_15': 14, 'CTRL_16': 15
}

## @class RelayBoard
#  @brief Handles routing logic and calculates binary paths for a shared 30-relay matrix.
class RelayBoard:
    def __init__(self, bus_num=1):
        self.address = settings.MCP_ADDRESS
        self.bus_num = bus_num
        self.state_mask = 0x000000  # Flexible bitmask for all pins (24+ bits)
        self._last_routing = {1: [], 2: []}
        self.bus = None
        self.connect()

    ## @brief Initializes I2C connection and resets the expander pins to OUTPUT.
    def connect(self):
        try:
            self.bus = smbus2.SMBus(self.bus_num)
            # Set all pins on Expander 1 banks to OUTPUT
            self.bus.write_byte_data(self.address, IODIRA, 0x00)
            self.bus.write_byte_data(self.address, IODIRB, 0x00)

            self.state_mask = 0x000000
            self.flush_state()

            # Default state on startup: IN1 -> OUT1, IN2 -> OUT2
            self.route_signal(1, 1, source="SYSTEM")
            self.route_signal(2, 2, source="SYSTEM")

            log.info(f"Relay controller initialized at {hex(self.address)}")
        except Exception as e:
            log.error(f"I2C Error during initialization: {e}")
            self.bus = None

    ## @brief Updates internal state mask but does NOT send to hardware yet.
    #  @param logical_name String key corresponding to PIN_MAP.
    #  @param state Boolean True (HIGH) or False (LOW).
    def _set_logical_pin(self, logical_name, state):
        if logical_name not in PIN_MAP:
            log.warning(f"Pin {logical_name} not found in PIN_MAP.")
            return

        bit_index = PIN_MAP[logical_name]

        if state:
            self.state_mask |= (1 << bit_index)
        else:
            self.state_mask &= ~(1 << bit_index)

    ## @sbrief Sends the internal bitmask state to the hardware via I2C.
    def flush_state(self):
        if self.bus is None:
            return

        # Split the bitmask into 8-bit bytes
        byte_a = self.state_mask & 0xFF
        byte_b = (self.state_mask >> 8) & 0xFF
        byte_c = (self.state_mask >> 16) & 0xFF # For Expander 2 (bits 16-23)

        try:
            # Write to Expander 1
            self.bus.write_byte_data(self.address, GPIOA, byte_a)
            self.bus.write_byte_data(self.address, GPIOB, byte_b)



        except Exception as e:
            log.error(f"Failed to flush state to hardware: {e}")

    ## @brief Calculates the specific control pins needed based on hardware tree logic.
    #  @param input_ch Integer (1 or 2).
    #  @param output_ch Integer (1 to 16).
    #  @return List of tuples containing (Control_Pin_Name, Target_State).
    def _calculate_routing_path(self, input_ch, output_ch):
        val = output_ch - 1

        # Extract directional bits for each level
        b3 = (val >> 3) & 1  # Level 1 (Top split)
        b2 = (val >> 2) & 1  # Level 2
        b1 = (val >> 1) & 1  # Level 3
        b0 = val & 1         # Level 4 (Crossover outputs)

        if input_ch == 1:
            pin_lvl1 = 1
            pin_lvl2 = 2 + b3
            pin_lvl3 = 4 + (b3 * 2) + b2
            pin_lvl4= 15 + (b3 * 4) + (b2 * 2) + b1

            s1, s2, s3 ,s4 = bool(b3), bool(b2), bool(b1), bool(b0 ^ 1)
        elif input_ch == 2:
            pin_lvl1 = 8
            pin_lvl2 = 9 + b3
            pin_lvl3 = 11 + (b3 * 2) + b2
            pin_lvl4= 15 + (b3 * 4) + (b2 * 2) + b1

            s1, s2, s3 ,s4 = bool(b3 ^ 1), bool(b2 ^ 1), bool(b1 ^ 1), bool(b0)
        else:
            raise ValueError("Invalid input channel. Must be 1 or 2.")


        return [
            (f"CTRL_{pin_lvl1}", s1),
            (f"CTRL_{pin_lvl2}", s2),
            (f"CTRL_{pin_lvl3}", s3),
            (f"CTRL_{pin_lvl4}", s4)
        ]

    ## @brief Computes binary path for the relay tree and switches all needed relays simultaneously.
    #  @param input_ch Integer (1 or 2).
    #  @param output_ch Integer (1 to 16).
    #  @param source Human-readable origin of the request ("LOCAL", a client id, or
    #         "SYSTEM" for startup defaults), logged for auditing under the [ROUTE] tag.
    def route_signal(self, input_ch, output_ch, source="UNKNOWN"):
        prefix = f"IN{input_ch}"

        try:
            routing_instructions = self._calculate_routing_path(input_ch, output_ch)
        except ValueError as e:
            log.error(str(e))
            return

        new_pin_names = {pin_name for pin_name, _ in routing_instructions}
        for old_pin_name, _ in self._last_routing[input_ch]:
            if old_pin_name not in new_pin_names:
                self._set_logical_pin(old_pin_name, False)

        for pin_name, pin_state in routing_instructions:
            self._set_logical_pin(pin_name, pin_state)

        self._last_routing[input_ch] = routing_instructions
        self.flush_state()

        log.info(f"[ROUTE] source={source} in={input_ch} out={output_ch}")
