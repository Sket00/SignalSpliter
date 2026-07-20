## @file twist_driver.py
#  @brief I2C driver for SparkFun Qwiic Twist
import time
from Config import settings
from Utils.logger import log
try:
    import qwiic_twist
except ImportError:
    log.error("qwiic_twist library not installed!")

## @class EncoderHandler
#  @brief Manages encoder with periodic color reinforcement to survive 24/7 noise.
class EncoderHandler:
    def __init__(self):
        self.twist = None
        self.last_count = 0
        self.last_button = False
        self.target_r = 0
        self.target_g = 0
        self.target_b = 0
        self.refresh_counter = 0
        self.connect()

    def connect(self):
        try:
            self.twist = qwiic_twist.QwiicTwist()
            if not self.twist.connected:
                log.error("Qwiic Twist not found at specified I2C address.")
                self.twist = None
                return
            
            self.twist.begin()
            
            self.twist.connect_red = 0
            self.twist.connect_green = 0
            self.twist.connect_blue = 0
            
            self.twist.count = 0
            time.sleep(0.05)
            
            self.last_count = self.twist.count
            self.last_button = self.twist.pressed
            log.info("Qwiic Twist initialized.")
        except Exception as e:
            log.error(f"Encoder connection error: {e}")
            self.twist = None

    def set_color(self, r, g, b):
        self.target_r = r
        self.target_g = g
        self.target_b = b
        if self.twist:
            try:
                self.twist.set_color(r, g, b)
            except OSError:
                pass 

    def get_events(self):
        if not self.twist:
            return 0, False
        
        diff = 0
        is_clicked = False
        
        self.refresh_counter += 1
        if self.refresh_counter >= 25:
            self.refresh_counter = 0
            try:
                self.twist.set_color(self.target_r, self.target_g, self.target_b)
            except OSError:
                pass

        try:
            current_count = self.twist.count
            current_button = self.twist.pressed
        except OSError:
            try:
                self.twist.set_color(self.target_r, self.target_g, self.target_b)
            except OSError:
                pass
            return 0, False

        if current_count != self.last_count:
            raw_diff = current_count - self.last_count
            if abs(raw_diff) < 50:
                diff = raw_diff
            self.last_count = current_count

        if current_button != self.last_button:
            time.sleep(0.02)
            try:
                confirm_button = self.twist.pressed
            except OSError:
                return 0, False
                
            if confirm_button == current_button:
                if current_button == True:
                    is_clicked = True
                self.last_button = current_button
                
        return diff, is_clicked
