## @file gui_matrix_showcase.py
#  @brief Graphical User Interface for SignalSpliter

import os
import math
import time
from PIL import Image, ImageDraw, ImageFont
from Config import settings
from Utils.logger import log
from Utils.network_info import get_ip
from Utils.device_clock import current_hm, set_manual_time

COLOR_PALETTE = [
    ("Blue", "#3366FF"), ("Green", "#27AE60"), ("Red", "#E74C3C"),
    ("Orange", "#E67E22"), ("Purple", "#8E44AD"), ("Cyan", "#1ABC9C"), ("Yellow", "#F1C40F"),
]

ICON_FOR_LABEL = {
    "< Back": "back",
    "BACK": "back",
    "Release Lock": "lock",
    "IN1 Color": "palette",
    "IN2 Color": "palette",
}
ICON_PREFIXES = {
    "Priority:": "priority",
    "Switch to": "theme",
}


def _resolve_icon(label):
    if label in ICON_FOR_LABEL:
        return ICON_FOR_LABEL[label]
    for prefix, icon in ICON_PREFIXES.items():
        if label.startswith(prefix):
            return icon
    return None


## @class MatrixGUI
#  @brief Screen state machine and Pillow-based rendering for the LCD interface.
class MatrixGUI:
    def __init__(self, w, h):
        self.w = w
        self.h = h

        try:
            bold_path = os.path.join(settings.ASSETS_DIR, "Roboto-Bold.ttf")
            self.font_title = ImageFont.truetype(bold_path, 14)
            self.font_main = ImageFont.truetype(bold_path, 16)
            self.font_small = ImageFont.truetype(bold_path, 11)
            self.font_big = ImageFont.truetype(bold_path, 26)
        except Exception as e:
            log.warning(f"[GUI] Roboto-Bold.ttf not found: {e}. .")
            self.font_title = self.font_main = self.font_small = self.font_big = ImageFont.load_default()

        self.input_assignment = {1: 1, 2: 2}
        self.colors = {1: "#3366FF", 2: "#27AE60"}

        self.light_mode = False
        self.screen = "MENU"
        self.cursor = 0
        self.scroll_y = 0

        self.active_input = 1
        self.color_target = None
        self.show_locked_warning = False

        self.status_bar_h = 14
        self.header_h = 26
        self.item_h = 34
        self.visible_items = (self.h - self.status_bar_h - self.header_h) // self.item_h

        self.grid_cols = 8
        self.grid_rows = 2
        self.menu_icons = ["routing", "settings"]
        self.LIST_SCREENS = {"SETTINGS", "COLOR_SELECT", "STEAL_PROMPT"}

        self.loaded_icons = {}
        self.icon_cache = {}
        self.menu_bg_cache = {}
        self.last_cpu_temp = "0.0Â°C"
        self.last_temp_time = 0

        self.runtime_tracker = None

        # --- SET TIME  ---
        self._settime_hour = 0
        self._settime_minute = 0
        self._settime_field = 0  # 0 = h, 1 = min


        self.screensaver_icon_files = ["saver1.png", "saver2.png", "saver3.png"]
        self.showcase_icon_size = 80
        self.showcase_arrangement_interval = 4.0  
        self.showcase_transition_duration = 3    
        self.showcase_grid_cols = 8
        self.showcase_grid_rows = 8
        self.loaded_showcase_icons = {}
        self._showcase_slots = [
            (self.w * 1 / 6, self.h / 2),
            (self.w * 1 / 2, self.h / 2),
            (self.w * 5 / 6, self.h / 2),
        ]
        self._showcase_started_at = None
        self._load_showcase_icons()
        self._load_png_icons()

    def _load_png_icons(self):
        icon_files = {
            "routing": "routing.png", "theme": "theme.png", "settings": "settings.png",
            "back": "back.png", "forward": "forward.png", "check": "check.png",
            "lock": "lock.png", "priority": "priority.png", "palette": "palette.png",
        }
        for name, filename in icon_files.items():
            path = os.path.join(settings.ASSETS_DIR, filename)
            if os.path.exists(path):
                self.loaded_icons[name] = Image.open(path).convert("RGBA")
            else:
                self.loaded_icons[name] = None


    def _load_showcase_icons(self):
        target_h = self.showcase_icon_size
        for filename in self.screensaver_icon_files:
            path = os.path.join(settings.ASSETS_DIR, filename)
            if not os.path.exists(path):
                self.loaded_showcase_icons[filename] = None
                continue
            icon = Image.open(path).convert("RGBA")
            bbox = icon.getbbox()
            if bbox:
                icon = icon.crop(bbox)
            scale = target_h / icon.height
            new_w = max(1, round(icon.width * scale))
            self.loaded_showcase_icons[filename] = icon.resize((new_w, target_h), Image.Resampling.LANCZOS)

    def draw_icon(self, img, draw_obj, name, cx, cy, size, hex_color, width=2):
        icon_img = self.loaded_icons.get(name)
        if icon_img:
            cache_key = (name, int(size), hex_color)
            if cache_key not in self.icon_cache:
                resized = icon_img.resize((int(size), int(size)), Image.Resampling.BILINEAR)
                color_layer = Image.new("RGBA", resized.size, hex_color)
                color_layer.putalpha(resized.getchannel("A"))
                self.icon_cache[cache_key] = color_layer
            cached_icon = self.icon_cache[cache_key]
            x, y = int(cx - size / 2), int(cy - size / 2)
            img.paste(cached_icon, (x, y), cached_icon)
            return

        r = size / 2
        if name == "back":
            draw_obj.line((cx + r * 0.4, cy - r * 0.7, cx - r * 0.5, cy), fill=hex_color, width=width)
            draw_obj.line((cx - r * 0.5, cy, cx + r * 0.4, cy + r * 0.7), fill=hex_color, width=width)
        elif name == "routing":
            gap = size * 0.18
            s = (size - gap) / 2
            for dx in (-1, 1):
                for dy in (-1, 1):
                    x0, y0 = cx + (gap / 2 if dx > 0 else -gap / 2 - s), cy + (gap / 2 if dy > 0 else -gap / 2 - s)
                    draw_obj.rectangle((x0, y0, x0 + s, y0 + s), outline=hex_color, width=width)
        elif name == "theme":
            draw_obj.ellipse((cx - r, cy - r, cx + r, cy + r), outline=hex_color, width=width)
        elif name == "settings":
            draw_obj.ellipse((cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55), outline=hex_color, width=width)
            for ang in range(0, 360, 45):
                rad = math.radians(ang)
                x0, y0 = cx + r * 0.55 * math.cos(rad), cy + r * 0.55 * math.sin(rad)
                x1, y1 = cx + r * 0.9 * math.cos(rad), cy + r * 0.9 * math.sin(rad)
                draw_obj.line((x0, y0, x1, y1), fill=hex_color, width=width)
        elif name == "check":
            draw_obj.line((cx - r * 0.6, cy, cx - r * 0.1, cy + r * 0.5), fill=hex_color, width=width)
            draw_obj.line((cx - r * 0.1, cy + r * 0.5, cx + r * 0.6, cy - r * 0.5), fill=hex_color, width=width)
        elif name == "lock":
            body_w, body_h = r * 1.1, r * 0.9
            x0, y0 = cx - body_w / 2, cy - body_h / 4
            draw_obj.rectangle((x0, y0, x0 + body_w, y0 + body_h), outline=hex_color, width=width)
            draw_obj.arc((cx - r * 0.45, y0 - r * 0.7, cx + r * 0.45, y0 + r * 0.25), 180, 360, fill=hex_color, width=width)
        elif name == "priority":
            draw_obj.line((cx, cy - r * 0.7, cx, cy + r * 0.7), fill=hex_color, width=width)
            draw_obj.line((cx - r * 0.3, cy - r * 0.35, cx, cy - r * 0.7), fill=hex_color, width=width)
            draw_obj.line((cx + r * 0.3, cy - r * 0.35, cx, cy - r * 0.7), fill=hex_color, width=width)
        elif name == "palette":
            draw_obj.ellipse((cx - r * 0.75, cy - r * 0.55, cx + r * 0.75, cy + r * 0.55), outline=hex_color, width=width)
            for ang, off in ((0.55, -0.25), (0.0, 0.35), (-0.55, -0.25)):
                px, py = cx + ang * r, cy + off * r
                draw_obj.ellipse((px - 2, py - 2, px + 2, py + 2), fill=hex_color)

    @property
    def bg_color(self): return "#EFEFEC" if self.light_mode else "#0A0A0C"
    @property
    def panel(self): return "#FFFFFF" if self.light_mode else "#141416"
    @property
    def divider(self): return "#DADAD6" if self.light_mode else "#1F1F22"
    @property
    def text_color(self): return "#101010" if self.light_mode else "#EDEDED"
    @property
    def text_muted(self): return "#8C8C88" if self.light_mode else "#6A6A6E"
    @property
    def accent(self): return "#E67E22"
    @property
    def accent_danger(self): return "#E74C3C"
    @property
    def accent_ok(self): return "#2ECC71"

    def _menu_items(self): return ["Routing", "Settings"]

    def _settings_items(self, lock):
        pri_str = lock.priority if lock else "LOCAL"
        return ["< Back", "Release Lock", f"Priority: {pri_str}", "IN1 Color", "IN2 Color",
                f"Switch to {'Dark' if self.light_mode else 'Light'}", "Set Time"]

    def _color_select_items(self): return ["< Back"] + [name for name, _ in COLOR_PALETTE]
    def _steal_prompt_items(self): return ["No, Cancel", "Yes, Steal Lock"]

    def _current_items(self, lock=None):
        if self.screen == "MENU": return self._menu_items()
        elif self.screen == "SETTINGS": return self._settings_items(lock)
        elif self.screen == "COLOR_SELECT": return self._color_select_items()
        elif self.screen == "STEAL_PROMPT": return self._steal_prompt_items()
        return []

    def _grid_nav_items(self):
        other = 2 if self.active_input == 1 else 1
        blocked = self.input_assignment[other]
        items = ["BACK"]
        for n in range(1, 17):
            if n != blocked: items.append(n)
        return items

    def _item_count(self, lock=None):
        if self.screen == "MENU": return len(self._menu_items())
        elif self.screen == "ROUTING": return 3
        elif self.screen == "ROUTING_GRID": return len(self._grid_nav_items())
        return len(self._current_items(lock))

    ## @brief Enters the "Set Time" screen, preloading current best-effort HH:MM.
    def _enter_set_time(self):
        hm = current_hm()
        self._settime_hour, self._settime_minute = hm if hm else (0, 0)
        self._settime_field = 0
        self._goto("SET_TIME")

    ## @brief Adjusts the currently active field (hour or minute) on the Set Time screen.
    def _adjust_set_time(self, delta):
        if self._settime_field == 0:
            self._settime_hour = (self._settime_hour + delta) % 24
        else:
            self._settime_minute = (self._settime_minute + delta) % 60

    def encoder_left(self, lock=None):
        if self.screen == "SCREENSAVER":
            self.exit_screensaver()
            return
        if self.screen == "SET_TIME":
            self._adjust_set_time(-1)
            return
        self.show_locked_warning = False
        if self.cursor > 0:
            self.cursor -= 1
            self._update_scroll(lock)

    def encoder_right(self, lock=None):
        if self.screen == "SCREENSAVER":
            self.exit_screensaver()
            return
        if self.screen == "SET_TIME":
            self._adjust_set_time(1)
            return
        self.show_locked_warning = False
        if self.cursor < self._item_count(lock) - 1:
            self.cursor += 1
            self._update_scroll(lock)

    def _update_scroll(self, lock=None):
        if self.screen not in self.LIST_SCREENS: return
        if self.cursor < self.scroll_y:
            self.scroll_y = self.cursor
        elif self.cursor >= self.scroll_y + self.visible_items:
            self.scroll_y = self.cursor - self.visible_items + 1

    def _goto(self, screen, cursor=0):
        self.screen = screen
        self.cursor = cursor
        self.scroll_y = 0

    def enter_screensaver(self):
        if self.screen == "SCREENSAVER": return
        self._pre_saver_state = (self.screen, self.cursor, self.scroll_y)
        self.screen = "SCREENSAVER"

    def exit_screensaver(self):
        if getattr(self, "_pre_saver_state", None) is not None:
            self.screen, self.cursor, self.scroll_y = self._pre_saver_state
            self._pre_saver_state = None
        else:
            self.screen = "MENU"

    def handle_click(self, lock):
        if self.screen == "SCREENSAVER":
            self.exit_screensaver()
            return
        if self.screen == "SET_TIME":
            if self._settime_field == 0:
                self._settime_field = 1
            else:
                set_manual_time(self._settime_hour, self._settime_minute)
                self._goto("SETTINGS", cursor=6)
            return
        self.show_locked_warning = False
        if self.screen == "MENU":
            label = self._current_items(lock)[self.cursor]
            if label == "Routing": self._goto("ROUTING")
            elif label == "Settings": self._goto("SETTINGS")
            return
        if self.screen == "ROUTING" and self.cursor == 0:
            self._goto("MENU")
            return
        if self.screen == "STEAL_PROMPT":
            if self.cursor == 1:
                lock.force_steal("LOCAL")
                self._goto("ROUTING")
            else: self._goto("MENU")
            return

        label = ""
        if self._item_count(lock) > 0 and self.screen not in ["ROUTING"]:
            if self.screen == "ROUTING_GRID":
                label = str(self._grid_nav_items()[self.cursor])
            else:
                label = self._current_items(lock)[self.cursor]

        if label == "< Back" or label == "BACK":
            if self.screen == "ROUTING_GRID": self._goto("ROUTING", cursor=self.active_input)
            elif self.screen == "SETTINGS": self._goto("MENU", cursor=1)
            elif self.screen == "COLOR_SELECT": self._goto("SETTINGS", cursor=3)
            return

        if label == "Release Lock":
            lock.release("LOCAL")
            self._goto("MENU", cursor=1)
            return
        if label.startswith("Priority:"):
            lock.priority = "REMOTE" if lock.priority == "LOCAL" else "LOCAL"
            return
        if label.startswith("Switch to"):
            self.light_mode = not self.light_mode
            return
        if label == "Set Time":
            self._enter_set_time()
            return

        if not lock.try_acquire("LOCAL"):
            if lock.priority == "LOCAL": self._goto("STEAL_PROMPT")
            else: self.show_locked_warning = True
            return

        lock.update_activity()
        if self.screen == "ROUTING":
            if self.cursor == 1:
                self.active_input = 1
                self._goto("ROUTING_GRID", cursor=0)
            elif self.cursor == 2:
                self.active_input = 2
                self._goto("ROUTING_GRID", cursor=0)
        elif self.screen == "ROUTING_GRID":
            self._assign_output(self.active_input, int(label))
            self._goto("ROUTING", cursor=self.active_input)
        elif self.screen == "SETTINGS":
            if label.startswith("IN1 Color"):
                self.color_target = 1
                self._goto("COLOR_SELECT")
            elif label.startswith("IN2 Color"):
                self.color_target = 2
                self._goto("COLOR_SELECT")
        elif self.screen == "COLOR_SELECT":
            _, hex_color = COLOR_PALETTE[self.cursor - 1]
            self.colors[self.color_target] = hex_color
            self._goto("SETTINGS", cursor=3 if self.color_target == 1 else 4)

    def _assign_output(self, input_num, out_num):
        other = 2 if input_num == 1 else 1
        if self.input_assignment[other] == out_num: return
        self.input_assignment[input_num] = out_num

    def _get_cpu_temp(self):
        now = time.time()
        if now - self.last_temp_time > 2.0:
            try:
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    self.last_cpu_temp = f"{float(f.read()) / 1000.0:.1f}°C"
            except: self.last_cpu_temp = "42.5°C"
            self.last_temp_time = now
        return self.last_cpu_temp

    def _draw_status_bar(self, draw, lock=None):
        draw.rectangle((0, 0, self.w, self.status_bar_h), fill=self.bg_color)
        if lock and lock.owner == "LOCAL": lock_txt, dot_color = "LOCAL", self.accent_ok
        elif lock and lock.owner is not None: lock_txt, dot_color = str(lock.owner), self.accent_danger
        else: lock_txt, dot_color = "FREE", self.text_muted
        dot_r, dot_cy = 2, self.status_bar_h / 2
        draw.ellipse((6, dot_cy - dot_r, 6 + dot_r * 2, dot_cy + dot_r), fill=dot_color)
        draw.text((6 + dot_r * 2 + 4, 1), lock_txt, fill=self.text_muted, font=self.font_small)
        ip = get_ip()
        ip_text = ip if ip else "OFFLINE"
        ip_w = draw.textlength(ip_text, font=self.font_small)
        draw.text(((self.w - ip_w) / 2, 1), ip_text, fill=self.text_muted, font=self.font_small)
        cpu_temp = self._get_cpu_temp()
        temp_w = draw.textlength(cpu_temp, font=self.font_small)
        draw.text((self.w - temp_w - 6, 1), cpu_temp, fill=self.text_muted, font=self.font_small)
        draw.line((0, self.status_bar_h, self.w, self.status_bar_h), fill=self.divider, width=1)

    def _draw_hero_row(self, draw, box, in_num, is_selected=False):
        x0, y0, x1, y1 = box
        draw.rectangle(box, fill=self.panel)
        draw.rectangle((x0, y0, x0 + 5, y1), fill=self.colors[in_num])
        if is_selected:
            outl = self.accent_danger if self.show_locked_warning else self.accent
            draw.rectangle((x0, y0, x1 - 1, y1 - 1), outline=outl, width=2)
        draw.text((x0 + 17, y0 + 8), f"INPUT {in_num}", fill=self.text_muted, font=self.font_small)
        out_val = self.input_assignment[in_num]
        val_text = f"OUT {out_val:02d}" if out_val else "OFF"
        val_w = draw.textlength(val_text, font=self.font_big)
        draw.text((x1 - val_w - 14, (y0 + y1) / 2 - 15), val_text, fill=self.colors[in_num], font=self.font_big)
        draw.line((x0, y1, x1, y1), fill=self.divider, width=1)

    def render_menu_static(self, lock):
        img = Image.new("RGBA", (self.w, self.h), self.bg_color)
        draw = ImageDraw.Draw(img)
        self._draw_status_bar(draw, lock)
        h_top, nav_h, gap = self.status_bar_h, 40, 4
        hero_top, hero_bottom = h_top + 4, self.h - nav_h
        row_h = (hero_bottom - hero_top - gap) // 2
        self._draw_hero_row(draw, (0, hero_top, self.w, hero_top + row_h), 1)
        self._draw_hero_row(draw, (0, hero_top + row_h + gap, self.w, hero_top + 2 * row_h + gap), 2)
        items, dock_top = self._menu_items(), self.h - nav_h
        seg_w = self.w // len(items)
        for i, item in enumerate(items):
            is_selected = (i == self.cursor)
            x0, x1 = i * seg_w, (i + 1) * seg_w if i < len(items) - 1 else self.w
            draw.rectangle((x0, dock_top, x1, self.h), fill=self.accent if is_selected else self.panel)
            if i > 0: draw.line((x0, dock_top, x0, self.h), fill=self.divider, width=1)
            cx = (x0 + x1) / 2
            icon_color = "#101010" if is_selected else self.text_muted
            self.draw_icon(img, draw, self.menu_icons[i], cx - 30, dock_top + nav_h / 2, 18, icon_color)
            draw.text((cx - 12, dock_top + nav_h / 2 - 7), item, fill="#101010" if is_selected else self.text_color, font=self.font_main)
        return img.convert("RGB")

    def _render_tile_list(self, img, draw, title, lock):
        self._draw_status_bar(draw, lock)
        h_top = self.status_bar_h
        header_fill = self.accent_danger if title == "LOCK ALERT!" else self.bg_color
        draw.rectangle((0, h_top, self.w, h_top + self.header_h), fill=header_fill)
        draw.text((12, h_top + 6), title, fill="#FFFFFF" if title == "LOCK ALERT!" else self.text_color, font=self.font_title)
        draw.line((0, h_top + self.header_h, self.w, h_top + self.header_h), fill=self.divider, width=1)
        items = self._current_items(lock)
        y_off = h_top + self.header_h
        for idx in range(self.scroll_y, min(len(items), self.scroll_y + self.visible_items + 1)):
            label, is_selected = items[idx], (idx == self.cursor)
            row_box = (0, y_off, self.w, y_off + self.item_h)
            swatch_hex = COLOR_PALETTE[idx - 1][1] if self.screen == "COLOR_SELECT" and label != "< Back" else None
            if swatch_hex:
                draw.rectangle(row_box, fill=swatch_hex)
                item_text_color = "#000000"
            else:
                draw.rectangle(row_box, fill=self.panel if is_selected else self.bg_color)
                item_text_color = self.text_color
            bar_color = (self.accent_danger if self.show_locked_warning else self.accent) if is_selected else None
            if bar_color: draw.rectangle((0, y_off, 4, y_off + self.item_h), fill=bar_color)
            tx = 16
            icon = _resolve_icon(label)
            if icon:
                self.draw_icon(img, draw, icon, 28, y_off + self.item_h / 2, 16, bar_color or item_text_color)
                tx = 46
            draw.text((tx, y_off + self.item_h / 2 - 8), label, fill=item_text_color, font=self.font_main)
            if self.screen == "SETTINGS":
                if label.startswith("IN1 Color"): draw.rectangle((self.w - 30, y_off + 9, self.w - 14, y_off + self.item_h - 9), fill=self.colors[1])
                elif label.startswith("IN2 Color"): draw.rectangle((self.w - 30, y_off + 9, self.w - 14, y_off + self.item_h - 9), fill=self.colors[2])
            if self.screen == "COLOR_SELECT" and swatch_hex == self.colors.get(self.color_target):
                draw.ellipse((self.w - 36, y_off + self.item_h / 2 - 10, self.w - 16, y_off + self.item_h / 2 + 10), fill="#FFFFFF")
                self.draw_icon(img, draw, "check", self.w - 26, y_off + self.item_h / 2, 13, "#000000")
            draw.line((0, y_off + self.item_h, self.w, y_off + self.item_h), fill=self.divider, width=1)
            y_off += self.item_h

        if self.screen == "SETTINGS" and self.runtime_tracker is not None:
            uptime_text = f"Uptime: {self.runtime_tracker.total_hours:.0f}h"
            draw.text((16, y_off + self.item_h / 2 - 8), uptime_text,
                      fill=self.text_muted, font=self.font_small)
            y_off += self.item_h

    def _render_routing_tabs(self, img, draw, lock):
        self._draw_status_bar(draw, lock)
        h_top, seg_h, seg_w = self.status_bar_h, 34, self.w // 3
        draw.rectangle((0, h_top, self.w, h_top + self.header_h), fill=self.bg_color)
        draw.text((12, h_top + 6), "ROUTING", fill=self.text_color, font=self.font_title)
        draw.line((0, h_top + self.header_h, self.w, h_top + self.header_h), fill=self.divider, width=1)
        tabs = [("Back", "back"), ("IN 1", None), ("IN 2", None)]
        st = h_top + self.header_h
        for i, (l, icon) in enumerate(tabs):
            is_curs = (self.cursor == i)
            fill = (self.accent_danger if self.show_locked_warning else self.accent) if is_curs else self.panel
            txt = "#101010" if is_curs else (self.colors[i] if i > 0 else self.text_muted)
            draw.rectangle((i * seg_w, st, (i + 1) * seg_w if i < 2 else self.w, st + seg_h), fill=fill)
            if i > 0: draw.line((i * seg_w, st, i * seg_w, st + seg_h), fill=self.divider, width=1)
            cx = (i * seg_w + ((i + 1) * seg_w if i < 2 else self.w)) / 2
            if icon: self.draw_icon(img, draw, icon, cx - 20, st + seg_h / 2, 15, txt)
            else: draw.text((cx - draw.textlength(l, font=self.font_main) / 2, st + seg_h / 2 - 8), l, fill=txt, font=self.font_main)
        self._draw_hero_row(draw, (0, st + seg_h + 4, self.w, self.h - (self.h - st - seg_h - 4) // 2), 1)
        self._draw_hero_row(draw, (0, st + seg_h + 4 + (self.h - st - seg_h - 4) // 2 + 4, self.w, self.h), 2)

    def _render_routing_grid(self, img, draw, lock):
        self._draw_status_bar(draw, lock)
        h_top = self.status_bar_h
        sel = self._grid_nav_items()[self.cursor] == "BACK"
        hf = (self.accent_danger if sel else self.accent) if sel and not self.show_locked_warning else (self.accent_danger if sel else self.bg_color)
        draw.rectangle((0, h_top, self.w, h_top + self.header_h), fill=hf)
        col = "#101010" if sel else self.text_color
        self.draw_icon(img, draw, "back", 20, h_top + self.header_h / 2, 14, col)
        draw.text((36, h_top + 6), f"IN {self.active_input}", fill=col, font=self.font_title)
        gt = h_top + self.header_h + 6
        cell_w, cell_h = (self.w - 10) // 8, (self.h - gt) // 2
        dot_d = min(cell_w, cell_h) - 16
        for out in range(1, 17):
            idx = out - 1
            cx = ((idx % 8) // 4) * 10 + (idx % 8) * cell_w + cell_w // 2
            cy = gt + (idx // 8) * cell_h + cell_h // 2 + 6
            txt = str(out)
            draw.text((cx - draw.textlength(txt, font=self.font_small) / 2, gt + (idx // 8) * cell_h + 2), txt, fill=self.text_muted, font=self.font_small)
            assigned = 1 if self.input_assignment[1] == out else (2 if self.input_assignment[2] == out else None)
            if out == self.input_assignment.get(2 if self.active_input == 1 else 1):
                draw.ellipse((cx - dot_d//2, cy - dot_d//2, cx + dot_d//2, cy + dot_d//2), fill=self.divider, outline=self.text_muted, width=1)
            elif assigned: draw.ellipse((cx - dot_d//2, cy - dot_d//2, cx + dot_d//2, cy + dot_d//2), fill=self.colors[assigned])
            else: draw.ellipse((cx - dot_d//2, cy - dot_d//2, cx + dot_d//2, cy + dot_d//2), outline=self.colors[self.active_input], width=2)
            if self._grid_nav_items()[self.cursor] == out:
                draw.ellipse((cx - dot_d//2 - 4, cy - dot_d//2 - 4, cx + dot_d//2 + 4, cy + dot_d//2 + 4), outline=self.accent_danger if self.show_locked_warning else self.accent, width=2)

    ## @brief Renders the Set Time screen: big HH:MM digits, active field highlighted.
    def _render_set_time(self, img, draw, lock):
        self._draw_status_bar(draw, lock)
        h_top = self.status_bar_h
        draw.rectangle((0, h_top, self.w, h_top + self.header_h), fill=self.bg_color)
        draw.text((12, h_top + 6), "SET TIME", fill=self.text_color, font=self.font_title)
        draw.line((0, h_top + self.header_h, self.w, h_top + self.header_h), fill=self.divider, width=1)

        hour_txt = f"{self._settime_hour:02d}"
        min_txt = f"{self._settime_minute:02d}"
        sep = ":"
        hour_w = draw.textlength(hour_txt, font=self.font_big)
        sep_w = draw.textlength(sep, font=self.font_big)
        min_w = draw.textlength(min_txt, font=self.font_big)
        total_w = hour_w + sep_w + min_w + 20
        x = (self.w - total_w) / 2
        cy = h_top + self.header_h + (self.h - h_top - self.header_h) / 2 - 20

        hour_color = self.accent if self._settime_field == 0 else self.text_color
        min_color = self.accent if self._settime_field == 1 else self.text_color

        draw.text((x, cy), hour_txt, fill=hour_color, font=self.font_big)
        x += hour_w + 10
        draw.text((x, cy), sep, fill=self.text_muted, font=self.font_big)
        x += sep_w + 10
        draw.text((x, cy), min_txt, fill=min_color, font=self.font_big)

        hint = "Rotate: adjust   Click: next / save"
        hint_w = draw.textlength(hint, font=self.font_small)
        draw.text(((self.w - hint_w) / 2, cy + 46), hint, fill=self.text_muted, font=self.font_small)

    @staticmethod
    def _bounce_pos(e, s, r, p=0.0):
        period = 2 * r
        t = (e * s + p) % period
        return t if t <= r else period - t

    ## @brief Composes a full-canvas static frame for a given 3-logo arrangement.
    #  @param arrangement List of 3 filenames (from screensaver_icon_files) in slot order.
    def _compose_showcase_frame(self, arrangement):
        frame = Image.new("RGB", (self.w, self.h), "#0A0A0C")
        for filename, (cx, cy) in zip(arrangement, self._showcase_slots):
            icon = self.loaded_showcase_icons.get(filename)
            if icon is None:
                continue
            x, y = int(cx - icon.width / 2), int(cy - icon.height / 2)
            frame.paste(icon, (x, y), icon)
        return frame

    ## @brief Reveals tiles of the next arrangement over the current canvas as
    #         progress advances, in a diagonal sweep order (column + row offset).
    #         Cheap by design: only newly-crossed tiles are pasted, never redrawn.
    def _reveal_showcase_tiles(self, progress):
        cols, rows = self.showcase_grid_cols, self.showcase_grid_rows
        tile_w, tile_h = self.w / cols, self.h / rows
        max_order = (cols - 1) + (rows - 1) * 0.4
        for col in range(cols):
            for row in range(rows):
                tile_key = (col, row)
                if tile_key in self._showcase_revealed:
                    continue
                order_index = col + row * 0.4
                reveal_threshold = order_index / max_order if max_order > 0 else 0
                if progress >= reveal_threshold:
                    x0, y0 = int(col * tile_w), int(row * tile_h)
                    x1, y1 = min(int(x0 + tile_w) + 1, self.w), min(int(y0 + tile_h) + 1, self.h)
                    crop = self._showcase_next_frame_img.crop((x0, y0, x1, y1))
                    self._showcase_canvas.paste(crop, (x0, y0))
                    self._showcase_revealed.add(tile_key)

    ## @brief Main screensaver entry point: shows 3 static logos, cycling their
    #         arrangement every showcase_arrangement_interval seconds via a
    #         smooth tile-wipe transition rather than an abrupt swap.
    def _render_screensaver(self):
        now = time.monotonic()
        if self._showcase_started_at is None:
            self._showcase_started_at = now
            self._showcase_current = list(self.screensaver_icon_files)
            self._showcase_target = None
            self._showcase_revealed = set()
            self._showcase_next_change_time = now + self.showcase_arrangement_interval
            self._showcase_canvas = self._compose_showcase_frame(self._showcase_current)

        if self._showcase_target is None and now >= self._showcase_next_change_time:
            self._showcase_target = self._showcase_current[1:] + self._showcase_current[:1]
            self._showcase_transition_start = now
            self._showcase_revealed = set()
            self._showcase_next_frame_img = self._compose_showcase_frame(self._showcase_target)

        if self._showcase_target is not None:
            elapsed = now - self._showcase_transition_start
            progress = min(1.0, elapsed / self.showcase_transition_duration)
            self._reveal_showcase_tiles(progress)
            if progress >= 1.0:
                self._showcase_current = self._showcase_target
                self._showcase_target = None
                self._showcase_next_change_time = now + self.showcase_arrangement_interval

        return self._showcase_canvas

    def render(self, lock):
        if self.screen == "SCREENSAVER": return self._render_screensaver()
        self._showcase_started_at = None
        if self.screen == "MENU": return self.render_menu_static(lock)
        img = Image.new("RGBA", (self.w, self.h), self.bg_color)
        draw = ImageDraw.Draw(img)
        if self.screen == "ROUTING": self._render_routing_tabs(img, draw, lock)
        elif self.screen == "ROUTING_GRID": self._render_routing_grid(img, draw, lock)
        elif self.screen == "STEAL_PROMPT": self._render_tile_list(img, draw, "LOCK ALERT!", lock)
        elif self.screen == "SETTINGS": self._render_tile_list(img, draw, "SETTINGS", lock)
        elif self.screen == "COLOR_SELECT": self._render_tile_list(img, draw, f"IN{self.color_target} COLOR", lock)
        elif self.screen == "SET_TIME": self._render_set_time(img, draw, lock)
        return img.convert("RGB")
