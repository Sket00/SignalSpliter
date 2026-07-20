## @file screen_manager.py
#  @brief Display manager for JD9853 1.47" IPS LCD with partial update support.

import os
import sys

from PIL import Image, ImageChops

from Config import settings
from Utils.logger import log

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    import jd9853
except ImportError:
    jd9853 = None
    log.error("[DISPLAY] JD9853 driver module not found in the Display folder!")


## @class ScreenManager
#  @brief Handles LCD initialization, orientation, and optimized rendering.
#  @details Incorporates a smart partial-update mechanism to reduce SPI bus load
#           by drawing only the screen areas that have changed between frames.
class ScreenManager:
    _TILE_SIZE = 40
    _FULL_UPDATE_THRESHOLD = 0.55

    def __init__(self):
        self.disp = None
        self.landscape = settings.LANDSCAPE
        self._last_image = None
        self.connect()

    ## @brief Attempts to connect and initialize the JD9853 display hardware.
    def connect(self):
        try:
            if jd9853 is None:
                raise RuntimeError("Missing jd9853 module")
            self.disp = jd9853.jd9853()
            self.disp.clear()
            self._last_image = None
            log.info("[DISPLAY] JD9853 hardware initialized successfully.")
        except Exception as e:
            self.disp = None
            log.error(f"[DISPLAY] Initialization failed: {e}")

    ## @brief Clears the hardware display and resets the internal image buffer.
    def clear(self):
        if self.disp:
            self.disp.clear()
        self._last_image = None

    ## @brief Merges overlapping or adjacent rectangular regions.
    #  @details Groups changed tiles together to minimize the number of separate
    #           drawing commands sent to the LCD.
    #  @param regions List of bounding box tuples (x0, y0, x1, y1).
    #  @return List of consolidated bounding box tuples.
    @staticmethod
    def _merge_regions(regions):
        regions = list(regions)
        changed = True
        while changed:
            changed = False
            merged = []
            while regions:
                x0, y0, x1, y1 = regions.pop()
                index = 0
                while index < len(regions):
                    ox0, oy0, ox1, oy1 = regions[index]
                    # Check if bounding boxes overlap or touch
                    if x0 <= ox1 and ox0 <= x1 and y0 <= oy1 and oy0 <= y1:
                        x0, y0 = min(x0, ox0), min(y0, oy0)
                        x1, y1 = max(x1, ox1), max(y1, oy1)
                        regions.pop(index)
                        changed = True
                        index = 0
                    else:
                        index += 1
                merged.append((x0, y0, x1, y1))
            regions = merged
        return regions

    ## @brief Calculates which parts of the image changed compared to the last frame.
    #  @param image The new PIL Image to be displayed.
    #  @return A list of regions to update, or None if a full update is more efficient.
    def _changed_regions(self, image):
        if self._last_image is None or self._last_image.size != image.size:
            return None  # Force full update

        # Find visual differences between the current and previous frame
        difference = ImageChops.difference(image, self._last_image)
        if difference.getbbox() is None:
            return []  # No changes detected

        width, height = image.size
        tiles = []
        
        # Divide the screen into a grid and mark tiles containing differences
        for y0 in range(0, height, self._TILE_SIZE):
            y1 = min(y0 + self._TILE_SIZE, height)
            for x0 in range(0, width, self._TILE_SIZE):
                x1 = min(x0 + self._TILE_SIZE, width)
                if difference.crop((x0, y0, x1, y1)).getbbox() is not None:
                    tiles.append((x0, y0, x1, y1))

        regions = self._merge_regions(tiles)
        partial_pixels = sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in regions)
        
        # If the changed area is too large, it's faster to just redraw everything
        if partial_pixels >= width * height * self._FULL_UPDATE_THRESHOLD:
            return None
            
        return regions

    ## @brief Renders the provided image onto the LCD.
    #  @details Automatically handles landscape rotation and optimizes SPI transfer
    #           using partial updates when applicable.
    #  @param image A PIL Image object.
    def show(self, image):
        if not self.disp:
            return

        # The hardware driver expects portrait orientation; rotate in software if needed.
        if self.landscape:
            image = image.transpose(Image.Transpose.ROTATE_270)
            
        if image.mode != "RGB":
            image = image.convert("RGB")

        regions = self._changed_regions(image)
        
        # Determine whether to execute a full or partial hardware redraw
        if regions is None or not hasattr(self.disp, "show_image_region"):
            self.disp.show_image(image)
        else:
            for x0, y0, x1, y1 in regions:
                self.disp.show_image_region(image, x0, y0, x1, y1)

        # Keep a copy as the reference for the next frame's partial update logic
        self._last_image = image.copy()
