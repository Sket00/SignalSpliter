import os
## @file settings.py
#  @brief Configuration settings for the Signal Spliter project.
# --- System Paths ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, 'Assets')
LOG_FILE = os.path.join(BASE_DIR, 'signal_spliter.log')
RUNTIME_FILE = os.path.join(BASE_DIR, 'runtime.json')  ##< Persistent total-runtime counter (RuntimeTracker)
# --- I2C Addresses ---
MCP_ADDRESS = 0x27        ##< I2C address for MCP23017 relay expander
ENCODER_ADDRESS = 0x3F    ##< I2C address for DEV-15083 encoder
# --- Display Settings
DISPLAY_WIDTH = 172       ##< Physical width of the display
DISPLAY_HEIGHT = 320      ##< Physical height of the display
LANDSCAPE = True          ##< True if mounted horizontally
