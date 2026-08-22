import tkinter as tk
from tkinter import ttk, filedialog
import customtkinter as ctk
import time
import os
import json
from typing import Dict, Optional

from keymap_config import KeymapManager, DEFAULT_ROBLOX_61KEY_MAP, midi_note_to_name
from keyboard_simulator import KeyboardSimulator
from salamander_engine import SalamanderGrandPianoEngine, get_low_latency_output_devices, get_all_output_devices
from midi_engine import MidiEngine, get_available_midi_ports
from midi_file_player import MidiFilePlayer

# Neumorphism Design Tokens
NEU_BG = "#E0E5EC"            # Monochromatic cool clay surface
NEU_CARD = "#E0E5EC"          # Card surface (molded from background)
NEU_WELL = "#D4DAE3"          # Inset well background
NEU_TEXT_PRIMARY = "#3D4852"  # Primary foreground text
NEU_TEXT_MUTED = "#6B7280"    # Secondary muted text
NEU_ACCENT = "#6C63FF"        # Soft violet accent
NEU_ACCENT_HOVER = "#8B84FF"  # Lighter violet hover
NEU_TEAL = "#38B2AC"          # Secondary positive teal
NEU_DANGER = "#E53E3E"        # Soft danger red
NEU_WARNING = "#DD6B20"       # Soft warning amber

ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "user_settings.json")


class PianoVisualizerCanvas(ctk.CTkFrame):
    """Canvas drawing a live 61-key visual piano highlighting pressed keys in real-time."""

    def __init__(self, master, keymap_mgr: KeymapManager, **kwargs):
        kwargs.setdefault("fg_color", NEU_WELL)
        kwargs.setdefault("corner_radius", 16)
        super().__init__(master, **kwargs)
        self.keymap_mgr = keymap_mgr

        self.canvas = tk.Canvas(self, bg=NEU_WELL, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=6, pady=6)

        self.pressed_notes: Dict[int, bool] = {}
        self.white_keys_rects = {}
        self.black_keys_rects = {}
        self.key_labels = {}

        self.canvas.bind("<Configure>", self._draw_keyboard)

    def set_note_state(self, note: int, is_pressed: bool):
        self.pressed_notes[note] = is_pressed
        self._update_note_color(note)

    def _update_note_color(self, note: int):
        is_pressed = self.pressed_notes.get(note, False)

        if note in self.white_keys_rects:
            color = NEU_ACCENT if is_pressed else "#FFFFFF"
            self.canvas.itemconfig(self.white_keys_rects[note], fill=color)
        elif note in self.black_keys_rects:
            color = "#8B84FF" if is_pressed else "#3D4852"
            self.canvas.itemconfig(self.black_keys_rects[note], fill=color)

    def _draw_keyboard(self, event=None):
        self.canvas.delete("all")
        self.white_keys_rects.clear()
        self.black_keys_rects.clear()

        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()

        if width < 10 or height < 10:
            return

        start_note = 36
        end_note = 96

        white_notes = [n for n in range(start_note, end_note + 1) if (n % 12) not in (1, 3, 6, 8, 10)]
        num_white = len(white_notes)
        key_w = width / num_white
        key_h = height

        x = 0
        note_to_x = {}
        for note in white_notes:
            rect = self.canvas.create_rectangle(
                x, 0, x + key_w - 1, key_h,
                fill="#FFFFFF", outline="#CAD1DC", width=1
            )
            self.white_keys_rects[note] = rect
            note_to_x[note] = x

            mapped_char = self.keymap_mgr.get_key_for_note(note)
            if mapped_char:
                self.canvas.create_text(
                    x + key_w / 2, key_h - 15,
                    text=mapped_char, fill=NEU_TEXT_PRIMARY, font=("Consolas", 10, "bold")
                )

            x += key_w

        black_w = key_w * 0.65
        black_h = key_h * 0.62

        for note in range(start_note, end_note + 1):
            if (note % 12) in (1, 3, 6, 8, 10):
                prev_white = note - 1
                if prev_white in note_to_x:
                    bx = note_to_x[prev_white] + key_w - (black_w / 2)
                    rect = self.canvas.create_rectangle(
                        bx, 0, bx + black_w, black_h,
                        fill="#3D4852", outline="#252F38", width=1
                    )
                    self.black_keys_rects[note] = rect

                    mapped_char = self.keymap_mgr.get_key_for_note(note)
                    if mapped_char:
                        self.canvas.create_text(
                            bx + black_w / 2, black_h - 12,
                            text=mapped_char, fill="#FFFFFF", font=("Consolas", 9, "bold")
                        )

        for note in range(start_note, end_note + 1):
            if self.pressed_notes.get(note, False):
                self._update_note_color(note)


class RobloxMidiApp(ctk.CTk):
    """Main Application Window with Dual Outputs (Monitoring + Virtual Mic Passthrough)."""

    def __init__(self):
        super().__init__()

        self.title("HZWU • Neumorphic MIDI Studio & Grand Piano Controller")
        self.geometry("1120 x 920")
        self.minsize(980, 780)
        self.configure(fg_color=NEU_BG)

        # Load user configuration
        self.config = self._load_config()

        # Core Engines
        self.keymap_mgr = KeymapManager()
        self.simulator = KeyboardSimulator(
            mode=self.config.get("input_mode", "VIRTUAL_KEY"),
            trigger_type=self.config.get("trigger_type", "HOLD")
        )
        self.simulator.set_enabled(self.config.get("keystrokes_enabled", True))

        self.piano_engine = SalamanderGrandPianoEngine()
        self.piano_engine.set_enabled(self.config.get("piano_sound_enabled", True))
        self.piano_engine.set_volume(self.config.get("piano_volume", 0.85))
        self.piano_engine.set_virtual_mic_enabled(self.config.get("virtual_mic_enabled", False))
        self.piano_engine.set_virtual_mic_volume(self.config.get("virtual_mic_volume", 0.85))

        self.engine = MidiEngine(self.keymap_mgr, self.simulator, piano_engine=self.piano_engine)
        self.engine.transpose = self.config.get("transpose", 0)

        self.file_player = MidiFilePlayer(self.keymap_mgr, self.simulator, piano_engine=self.piano_engine)
        self.file_player.transpose = self.config.get("transpose", 0)

        # Bind callbacks
        self.engine.on_note_on_cb = self._on_midi_note_on
        self.engine.on_note_off_cb = self._on_midi_note_off
        self.engine.on_log_cb = self.log_message
        self.engine.on_toggle_state_cb = self._on_toggle_state_changed

        self.file_player.on_note_on_cb = self._on_midi_note_on
        self.file_player.on_note_off_cb = self._on_midi_note_off
        self.file_player.on_log_cb = self.log_message
        self.file_player.on_progress_cb = self._on_player_progress_updated
        self.file_player.on_playback_finished_cb = self._on_player_finished

        self.logging_enabled = self.config.get("logging_enabled", True)

        self._build_ui()
        self._refresh_midi_ports()
        self._refresh_audio_devices()

        self.after(500, self._auto_connect_saved_device)

    def _load_config(self) -> dict:
        default_config = {
            "last_midi_port": "",
            "last_audio_device": "",
            "piano_sound_enabled": True,
            "piano_volume": 0.85,
            "virtual_mic_enabled": False,
            "last_virtual_mic_device": "",
            "virtual_mic_volume": 0.85,
            "keystrokes_enabled": True,
            "transpose": 0,
            "logging_enabled": True,
            "input_mode": "VIRTUAL_KEY",
            "trigger_type": "HOLD",
            "auto_connect": True
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    default_config.update(loaded)
            except Exception as e:
                print(f"Error loading config: {e}")
        return default_config

    def _save_config(self):
        try:
            self.config["last_midi_port"] = self.port_dropdown.get()
            self.config["last_audio_device"] = self.audio_dev_dropdown.get()
            self.config["piano_sound_enabled"] = bool(self.piano_switch.get())
            self.config["piano_volume"] = float(self.vol_slider.get())
            self.config["virtual_mic_enabled"] = bool(self.vmic_switch.get())
            self.config["last_virtual_mic_device"] = self.vmic_dropdown.get()
            self.config["virtual_mic_volume"] = float(self.vmic_vol_slider.get())
            self.config["keystrokes_enabled"] = bool(self.enable_switch.get())
            self.config["transpose"] = int(self.transpose_slider.get())
            self.config["logging_enabled"] = bool(self.log_checkbox.get())
            self.config["auto_connect"] = bool(self.auto_connect_checkbox.get())

            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    def _build_ui(self):
        # Top Header Bar - Neumorphic elevated header with HZWU branding badge
        header_frame = ctk.CTkFrame(self, corner_radius=20, fg_color=NEU_CARD)
        header_frame.pack(fill="x", padx=16, pady=(16, 10))

        brand_badge = ctk.CTkLabel(
            header_frame,
            text="HZWU",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=NEU_ACCENT,
            text_color="#FFFFFF",
            corner_radius=10,
            width=58,
            height=28
        )
        brand_badge.pack(side="left", padx=(14, 8), pady=12)

        title_label = ctk.CTkLabel(
            header_frame,
            text="MIDI STUDIO & GRAND PIANO CONTROLLER",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=NEU_TEXT_PRIMARY
        )
        title_label.pack(side="left", padx=4, pady=12)

        self.status_badge = ctk.CTkLabel(
            header_frame,
            text="● DISCONNECTED",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=NEU_WELL,
            text_color=NEU_DANGER,
            corner_radius=12,
            padx=12,
            pady=4
        )
        self.status_badge.pack(side="right", padx=14, pady=12)

        main_content = ctk.CTkFrame(self, fg_color="transparent")
        main_content.pack(fill="both", expand=True, padx=16, pady=5)

        # Left Column (Controls & Device Settings)
        left_col = ctk.CTkFrame(main_content, width=390, corner_radius=24, fg_color=NEU_CARD)
        left_col.pack(side="left", fill="y", padx=(0, 12), pady=5)
        left_col.pack_propagate(False)

        # Card 1: MIDI Connection Card
        conn_box = ctk.CTkFrame(left_col, corner_radius=18, fg_color=NEU_WELL)
        conn_box.pack(fill="x", padx=12, pady=(12, 6))

        conn_title = ctk.CTkLabel(conn_box, text="MIDI INPUT DEVICE", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=NEU_TEXT_PRIMARY)
        conn_title.pack(anchor="w", padx=12, pady=(8, 2))

        self.port_dropdown = ctk.CTkComboBox(
            conn_box, values=["Searching..."], height=32,
            fg_color=NEU_BG, text_color=NEU_TEXT_PRIMARY, button_color=NEU_ACCENT,
            button_hover_color=NEU_ACCENT_HOVER, dropdown_fg_color=NEU_BG,
            dropdown_text_color=NEU_TEXT_PRIMARY, corner_radius=12,
            command=lambda _: self._save_config()
        )
        self.port_dropdown.pack(fill="x", padx=12, pady=4)

        btn_row = ctk.CTkFrame(conn_box, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(2, 4))

        self.refresh_btn = ctk.CTkButton(
            btn_row, text="🔄 Refresh", width=95, height=32,
            fg_color=NEU_BG, hover_color="#CAD1DC", text_color=NEU_TEXT_PRIMARY,
            corner_radius=12, command=self._refresh_midi_ports
        )
        self.refresh_btn.pack(side="left", padx=(0, 6))

        self.connect_btn = ctk.CTkButton(
            btn_row, text="Connect", width=130, height=32,
            fg_color=NEU_TEAL, hover_color="#2C8F8A", text_color="#FFFFFF",
            corner_radius=12, font=ctk.CTkFont(weight="bold"),
            command=self._toggle_connection
        )
        self.connect_btn.pack(side="left", fill="x", expand=True)

        self.auto_connect_checkbox = ctk.CTkCheckBox(
            conn_box, text="Auto-Connect on Startup",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=NEU_TEXT_MUTED, fg_color=NEU_ACCENT,
            command=self._save_config
        )
        if self.config.get("auto_connect", True):
            self.auto_connect_checkbox.select()
        self.auto_connect_checkbox.pack(anchor="w", padx=12, pady=(4, 8))

        # Card 2: Yamaha C5 Direct Audio Card
        piano_box = ctk.CTkFrame(left_col, corner_radius=18, fg_color=NEU_WELL)
        piano_box.pack(fill="x", padx=12, pady=6)

        piano_title = ctk.CTkLabel(piano_box, text="🎧 YAMAHA C5 DIRECT AUDIO", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=NEU_ACCENT)
        piano_title.pack(anchor="w", padx=12, pady=(8, 2))

        self.piano_switch = ctk.CTkSwitch(
            piano_box, text="Direct Grand Piano Output",
            progress_color=NEU_ACCENT, text_color=NEU_TEXT_PRIMARY,
            command=self._toggle_piano_sound
        )
        if self.config.get("piano_sound_enabled", True):
            self.piano_switch.select()
        else:
            self.piano_switch.deselect()
        self.piano_switch.pack(anchor="w", padx=12, pady=3)

        dev_label = ctk.CTkLabel(piano_box, text="Audio Device (WASAPI Low-Latency):", font=ctk.CTkFont(family="Segoe UI", size=11), text_color=NEU_TEXT_MUTED)
        dev_label.pack(anchor="w", padx=12, pady=(2, 0))

        self.audio_dev_dropdown = ctk.CTkComboBox(
            piano_box, values=["Loading..."], height=30,
            fg_color=NEU_BG, text_color=NEU_TEXT_PRIMARY, button_color=NEU_ACCENT,
            button_hover_color=NEU_ACCENT_HOVER, dropdown_fg_color=NEU_BG,
            dropdown_text_color=NEU_TEXT_PRIMARY, corner_radius=12,
            command=self._on_audio_device_changed
        )
        self.audio_dev_dropdown.pack(fill="x", padx=12, pady=(2, 4))

        vol_label = ctk.CTkLabel(piano_box, text="Piano Volume:", font=ctk.CTkFont(family="Segoe UI", size=11), text_color=NEU_TEXT_MUTED)
        vol_label.pack(anchor="w", padx=12, pady=(2, 0))

        self.vol_slider = ctk.CTkSlider(
            piano_box, from_=0.0, to=1.0, number_of_steps=20,
            button_color=NEU_ACCENT, progress_color=NEU_ACCENT,
            command=self._on_volume_changed
        )
        self.vol_slider.set(self.config.get("piano_volume", 0.85))
        self.vol_slider.pack(fill="x", padx=12, pady=(2, 8))

        # Card 3: Virtual Mic Broadcast Card
        vmic_box = ctk.CTkFrame(left_col, corner_radius=18, fg_color=NEU_WELL)
        vmic_box.pack(fill="x", padx=12, pady=6)

        vmic_title = ctk.CTkLabel(vmic_box, text="🎙️ VIRTUAL MIC BROADCAST", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=NEU_TEAL)
        vmic_title.pack(anchor="w", padx=12, pady=(8, 2))

        self.vmic_switch = ctk.CTkSwitch(
            vmic_box, text="Broadcast to Virtual Cable",
            progress_color=NEU_TEAL, text_color=NEU_TEXT_PRIMARY,
            command=self._toggle_virtual_mic
        )
        if self.config.get("virtual_mic_enabled", False):
            self.vmic_switch.select()
        else:
            self.vmic_switch.deselect()
        self.vmic_switch.pack(anchor="w", padx=12, pady=3)

        vmic_dev_label = ctk.CTkLabel(vmic_box, text="Virtual Cable Target (e.g. CABLE Input):", font=ctk.CTkFont(family="Segoe UI", size=11), text_color=NEU_TEXT_MUTED)
        vmic_dev_label.pack(anchor="w", padx=12, pady=(2, 0))

        self.vmic_dropdown = ctk.CTkComboBox(
            vmic_box, values=["Loading..."], height=30,
            fg_color=NEU_BG, text_color=NEU_TEXT_PRIMARY, button_color=NEU_TEAL,
            button_hover_color="#2C8F8A", dropdown_fg_color=NEU_BG,
            dropdown_text_color=NEU_TEXT_PRIMARY, corner_radius=12,
            command=self._on_virtual_mic_device_changed
        )
        self.vmic_dropdown.pack(fill="x", padx=12, pady=(2, 4))

        vmic_vol_label = ctk.CTkLabel(vmic_box, text="Mic Broadcast Gain:", font=ctk.CTkFont(family="Segoe UI", size=11), text_color=NEU_TEXT_MUTED)
        vmic_vol_label.pack(anchor="w", padx=12, pady=(2, 0))

        self.vmic_vol_slider = ctk.CTkSlider(
            vmic_box, from_=0.0, to=1.0, number_of_steps=20,
            button_color=NEU_TEAL, progress_color=NEU_TEAL,
            command=self._on_virtual_mic_vol_changed
        )
        self.vmic_vol_slider.set(self.config.get("virtual_mic_volume", 0.85))
        self.vmic_vol_slider.pack(fill="x", padx=12, pady=(2, 8))

        # Card 4: Keyboard Simulation Settings
        settings_box = ctk.CTkFrame(left_col, corner_radius=18, fg_color=NEU_WELL)
        settings_box.pack(fill="x", padx=12, pady=6)

        settings_title = ctk.CTkLabel(settings_box, text="KEYBOARD MAPPING SETTINGS", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=NEU_TEXT_PRIMARY)
        settings_title.pack(anchor="w", padx=12, pady=(8, 2))

        self.enable_switch = ctk.CTkSwitch(
            settings_box, text="Simulate Keystrokes (F8 Toggle)",
            progress_color=NEU_ACCENT, text_color=NEU_TEXT_PRIMARY,
            command=self._on_switch_toggled
        )
        if self.config.get("keystrokes_enabled", True):
            self.enable_switch.select()
        else:
            self.enable_switch.deselect()
        self.enable_switch.pack(anchor="w", padx=12, pady=3)

        transpose_frame = ctk.CTkFrame(settings_box, fg_color="transparent")
        transpose_frame.pack(fill="x", padx=12, pady=2)

        ctk.CTkLabel(transpose_frame, text="Transpose:", font=ctk.CTkFont(family="Segoe UI", size=11), text_color=NEU_TEXT_MUTED).pack(side="left")
        trans_val = self.config.get("transpose", 0)
        sign = "+" if trans_val > 0 else ""
        self.transpose_val_label = ctk.CTkLabel(
            transpose_frame, text=f"{sign}{trans_val} Semi",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"), text_color=NEU_ACCENT
        )
        self.transpose_val_label.pack(side="right")

        self.transpose_slider = ctk.CTkSlider(
            settings_box, from_=-24, to=24, number_of_steps=48,
            button_color=NEU_ACCENT, progress_color=NEU_ACCENT,
            command=self._on_transpose_changed
        )
        self.transpose_slider.set(trans_val)
        self.transpose_slider.pack(fill="x", padx=12, pady=(2, 8))

        # Right Column (Visualizer, Player, Logs)
        right_col = ctk.CTkFrame(main_content, corner_radius=24, fg_color=NEU_CARD)
        right_col.pack(side="right", fill="both", expand=True, pady=5)

        # 1. Piano Visualizer
        vis_header = ctk.CTkFrame(right_col, fg_color="transparent")
        vis_header.pack(fill="x", padx=16, pady=(12, 4))
        vis_title = ctk.CTkLabel(vis_header, text="LIVE 61-KEY PIANO VISUALIZER", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=NEU_TEXT_PRIMARY)
        vis_title.pack(side="left")

        vis_brand_sub = ctk.CTkLabel(vis_header, text="HZWU • Neumorphic Engine", font=ctk.CTkFont(family="Segoe UI", size=10), text_color=NEU_TEXT_MUTED)
        vis_brand_sub.pack(side="right")

        self.visualizer = PianoVisualizerCanvas(right_col, self.keymap_mgr, height=130)
        self.visualizer.pack(fill="x", padx=16, pady=(0, 10))

        # 2. MIDI File Player Card
        player_box = ctk.CTkFrame(right_col, corner_radius=18, fg_color=NEU_WELL)
        player_box.pack(fill="x", padx=16, pady=(0, 10))

        player_header = ctk.CTkFrame(player_box, fg_color="transparent")
        player_header.pack(fill="x", padx=14, pady=(10, 4))

        ctk.CTkLabel(
            player_header, text="🎵 MIDI FILE PLAYER & SHEET CONVERTER",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=NEU_ACCENT
        ).pack(side="left")

        self.file_label = ctk.CTkLabel(player_header, text="No file loaded", font=ctk.CTkFont(family="Segoe UI", size=11), text_color=NEU_TEXT_MUTED)
        self.file_label.pack(side="right")

        controls_row = ctk.CTkFrame(player_box, fg_color="transparent")
        controls_row.pack(fill="x", padx=14, pady=4)

        self.load_btn = ctk.CTkButton(
            controls_row, text="📁 Open .mid", width=105, height=32,
            fg_color=NEU_BG, hover_color="#CAD1DC", text_color=NEU_TEXT_PRIMARY,
            corner_radius=12, command=self._open_midi_file
        )
        self.load_btn.pack(side="left", padx=(0, 6))

        self.play_btn = ctk.CTkButton(
            controls_row, text="▶ Play", width=85, height=32,
            fg_color=NEU_TEAL, hover_color="#2C8F8A", text_color="#FFFFFF",
            corner_radius=12, font=ctk.CTkFont(weight="bold"), command=self._play_midi_file
        )
        self.play_btn.pack(side="left", padx=4)

        self.pause_btn = ctk.CTkButton(
            controls_row, text="⏸ Pause", width=85, height=32,
            fg_color=NEU_WARNING, hover_color="#C05621", text_color="#FFFFFF",
            corner_radius=12, font=ctk.CTkFont(weight="bold"), command=self._pause_midi_file
        )
        self.pause_btn.pack(side="left", padx=4)

        self.stop_btn = ctk.CTkButton(
            controls_row, text="⏹ Stop", width=85, height=32,
            fg_color=NEU_DANGER, hover_color="#C53030", text_color="#FFFFFF",
            corner_radius=12, font=ctk.CTkFont(weight="bold"), command=self._stop_midi_file
        )
        self.stop_btn.pack(side="left", padx=4)

        self.sheet_btn = ctk.CTkButton(
            controls_row, text="🎼 View Sheet", width=115, height=32,
            fg_color=NEU_ACCENT, hover_color=NEU_ACCENT_HOVER, text_color="#FFFFFF",
            corner_radius=12, command=self._view_sheet_notation
        )
        self.sheet_btn.pack(side="right")

        progress_row = ctk.CTkFrame(player_box, fg_color="transparent")
        progress_row.pack(fill="x", padx=14, pady=(4, 10))

        self.progress_bar = ctk.CTkProgressBar(
            progress_row, height=8, corner_radius=6,
            progress_color=NEU_ACCENT, fg_color=NEU_BG
        )
        self.progress_bar.set(0)
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.time_label = ctk.CTkLabel(progress_row, text="00:00 / 00:00", font=ctk.CTkFont(family="Segoe UI", size=11), text_color=NEU_TEXT_MUTED)
        self.time_label.pack(side="right")

        # 3. Logs Console Card
        log_header = ctk.CTkFrame(right_col, fg_color="transparent")
        log_header.pack(fill="x", padx=16, pady=(4, 4))

        ctk.CTkLabel(log_header, text="EVENT LOGS", font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"), text_color=NEU_TEXT_PRIMARY).pack(side="left")

        self.log_checkbox = ctk.CTkCheckBox(
            log_header, text="Enable Logging",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=NEU_TEXT_MUTED, fg_color=NEU_ACCENT,
            command=self._toggle_logging
        )
        if self.logging_enabled:
            self.log_checkbox.select()
        else:
            self.log_checkbox.deselect()
        self.log_checkbox.pack(side="right")

        self.log_textbox = ctk.CTkTextbox(
            right_col, height=140, font=("Consolas", 11),
            fg_color=NEU_WELL, text_color=NEU_TEXT_PRIMARY,
            corner_radius=16
        )
        self.log_textbox.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    def _auto_connect_saved_device(self):
        saved_port = self.config.get("last_midi_port")
        auto_conn = self.config.get("auto_connect", True)
        if auto_conn and saved_port and saved_port in self.port_dropdown.cget("values"):
            self.port_dropdown.set(saved_port)
            self._toggle_connection()

    def _refresh_audio_devices(self):
        self.audio_devices = get_low_latency_output_devices()
        self.all_devices = get_all_output_devices()

        if self.audio_devices:
            names = [name for _, name in self.audio_devices]
            self.audio_dev_dropdown.configure(values=names)

            saved_audio = self.config.get("last_audio_device")
            if saved_audio and saved_audio in names:
                self.audio_dev_dropdown.set(saved_audio)
                self._on_audio_device_changed(saved_audio)
            else:
                self.audio_dev_dropdown.set(names[0])
                self._on_audio_device_changed(names[0])

        if self.all_devices:
            all_names = [name for _, name in self.all_devices]
            self.vmic_dropdown.configure(values=all_names)

            saved_vmic = self.config.get("last_virtual_mic_device")
            # Auto-detect cable if not specified
            cable_matches = [n for n in all_names if "cable" in n.lower() or "virtual" in n.lower()]
            if saved_vmic and saved_vmic in all_names:
                self.vmic_dropdown.set(saved_vmic)
                self._on_virtual_mic_device_changed(saved_vmic)
            elif cable_matches:
                self.vmic_dropdown.set(cable_matches[0])
                self._on_virtual_mic_device_changed(cable_matches[0])
            else:
                self.vmic_dropdown.set(all_names[0])
                self._on_virtual_mic_device_changed(all_names[0])

    def _on_audio_device_changed(self, chosen_name: str):
        for dev_id, name in self.audio_devices:
            if name == chosen_name:
                self.piano_engine.set_device(dev_id)
                self._save_config()
                self.log_message(f"Active WASAPI monitoring device: {chosen_name}")
                break

    def _on_virtual_mic_device_changed(self, chosen_name: str):
        for dev_id, name in self.all_devices:
            if name == chosen_name:
                self.piano_engine.set_virtual_mic_device(dev_id)
                self._save_config()
                self.log_message(f"Active Virtual Mic target: {chosen_name}")
                break

    def _toggle_virtual_mic(self):
        enabled = bool(self.vmic_switch.get())
        self.piano_engine.set_virtual_mic_enabled(enabled)
        self._save_config()
        state_str = "ENABLED" if enabled else "DISABLED"
        self.log_message(f"Virtual Mic Broadcast: {state_str}")

    def _on_virtual_mic_vol_changed(self, val):
        self.piano_engine.set_virtual_mic_volume(float(val))
        self._save_config()

    def _toggle_piano_sound(self):
        enabled = bool(self.piano_switch.get())
        self.piano_engine.set_enabled(enabled)
        self._save_config()
        state_str = "ENABLED" if enabled else "DISABLED"
        self.log_message(f"Yamaha C5 Direct Audio: {state_str}")

    def _on_volume_changed(self, val):
        self.piano_engine.set_volume(float(val))
        self._save_config()

    def _toggle_logging(self):
        self.logging_enabled = bool(self.log_checkbox.get())
        self._save_config()

    def _refresh_midi_ports(self):
        ports = get_available_midi_ports()
        if ports:
            self.port_dropdown.configure(values=ports)
            saved_port = self.config.get("last_midi_port")
            if saved_port and saved_port in ports:
                self.port_dropdown.set(saved_port)
            else:
                self.port_dropdown.set(ports[0])
            self.log_message(f"Found {len(ports)} MIDI device(s): {', '.join(ports)}")
        else:
            self.port_dropdown.configure(values=["No Devices Found"])
            self.port_dropdown.set("No Devices Found")
            self.log_message("No MIDI devices detected. Plug in your keyboard and click Refresh.")

    def _toggle_connection(self):
        if self.engine.is_running:
            self.engine.stop()
            self.connect_btn.configure(text="Connect", fg_color=NEU_TEAL, hover_color="#2C8F8A")
            self.status_badge.configure(text="● DISCONNECTED", text_color=NEU_DANGER)
        else:
            selected_port = self.port_dropdown.get()
            if selected_port and selected_port != "No Devices Found":
                success = self.engine.start(selected_port)
                if success:
                    self._save_config()
                    self.connect_btn.configure(text="Disconnect", fg_color=NEU_DANGER, hover_color="#C53030")
                    self.status_badge.configure(text="● CONNECTED & LISTENING", text_color=NEU_TEAL)
            else:
                self.log_message("Please select a valid MIDI device port.")

    def _on_switch_toggled(self):
        enabled = bool(self.enable_switch.get())
        self.simulator.set_enabled(enabled)
        self._save_config()
        state_str = "ENABLED" if enabled else "MUTED"
        self.log_message(f"Mapping switch changed to: {state_str}")

    def _on_toggle_state_changed(self, enabled: bool):
        self.after(0, lambda: self.enable_switch.select() if enabled else self.enable_switch.deselect())
        self._save_config()

    def _on_transpose_changed(self, val):
        semitones = int(val)
        self.engine.transpose = semitones
        self.file_player.transpose = semitones
        self._save_config()
        sign = "+" if semitones > 0 else ""
        self.transpose_val_label.configure(text=f"{sign}{semitones} Semi")
        self.visualizer._draw_keyboard()

    def _open_midi_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("MIDI Files", "*.mid;*.midi")])
        if file_path:
            success = self.file_player.load_file(file_path)
            if success:
                fname = os.path.basename(file_path)
                self.file_label.configure(text=fname)
                self.time_label.configure(text=f"00:00 / {MidiFilePlayer.format_time(self.file_player.total_duration)}")
                self.progress_bar.set(0)

    def _play_midi_file(self):
        self.file_player.play()

    def _pause_midi_file(self):
        self.file_player.pause()

    def _stop_midi_file(self):
        self.file_player.stop()
        self.progress_bar.set(0)
        self.time_label.configure(text=f"00:00 / {MidiFilePlayer.format_time(self.file_player.total_duration)}")

    def _view_sheet_notation(self):
        sheet_text = self.file_player.generate_sheet_text(transpose=self.engine.transpose)
        if not sheet_text:
            self.log_message("Please open a MIDI file first to generate sheet notation.")
            return

        win = ctk.CTkToplevel(self)
        win.title("Generated Sheet Text")
        win.geometry("600 x 400")
        win.attributes("-topmost", True)

        txt = ctk.CTkTextbox(win, font=("Consolas", 12))
        txt.pack(fill="both", expand=True, padx=15, pady=15)
        txt.insert("1.0", sheet_text)

    def _on_midi_note_on(self, note: int, velocity: int, mapped_key: Optional[str]):
        self.after(0, lambda: self.visualizer.set_note_state(note + self.engine.transpose, True))

    def _on_midi_note_off(self, note: int, mapped_key: Optional[str]):
        self.after(0, lambda: self.visualizer.set_note_state(note + self.engine.transpose, False))

    def _on_player_progress_updated(self, elapsed: float, total: float):
        if total > 0:
            frac = min(1.0, elapsed / total)
            self.after(0, lambda: self._update_progress_ui(frac, elapsed, total))

    def _update_progress_ui(self, frac: float, elapsed: float, total: float):
        self.progress_bar.set(frac)
        self.time_label.configure(text=f"{MidiFilePlayer.format_time(elapsed)} / {MidiFilePlayer.format_time(total)}")

    def _on_player_finished(self):
        self.after(0, lambda: self.progress_bar.set(0))

    def log_message(self, text: str):
        if not self.logging_enabled:
            return
        timestamp = time.strftime("[%H:%M:%S] ")
        self.after(0, lambda: self._append_log(timestamp + text + "\n"))

    def _append_log(self, full_text: str):
        self.log_textbox.insert("end", full_text)
        self.log_textbox.see("end")

    def on_closing(self):
        self._save_config()
        self.file_player.stop()
        self.engine.stop()
        if self.piano_engine:
            self.piano_engine.close()
        self.destroy()
