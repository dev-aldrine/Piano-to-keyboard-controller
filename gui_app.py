import tkinter as tk
from tkinter import ttk, filedialog
import customtkinter as ctk
import time
from typing import Dict, Optional

from keymap_config import KeymapManager, DEFAULT_ROBLOX_61KEY_MAP, midi_note_to_name
from keyboard_simulator import KeyboardSimulator
from salamander_engine import SalamanderGrandPianoEngine
from midi_engine import MidiEngine, get_available_midi_ports
from midi_file_player import MidiFilePlayer

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class PianoVisualizerCanvas(ctk.CTkFrame):
    """Canvas drawing a live 61-key visual piano highlighting pressed keys in real-time."""

    def __init__(self, master, keymap_mgr: KeymapManager, **kwargs):
        super().__init__(master, **kwargs)
        self.keymap_mgr = keymap_mgr

        self.canvas = tk.Canvas(self, bg="#181824", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=5, pady=5)

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
            color = "#00E5FF" if is_pressed else "#FFFFFF"
            self.canvas.itemconfig(self.white_keys_rects[note], fill=color)
        elif note in self.black_keys_rects:
            color = "#FF2A85" if is_pressed else "#252533"
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
                fill="#FFFFFF", outline="#101018", width=1
            )
            self.white_keys_rects[note] = rect
            note_to_x[note] = x

            mapped_char = self.keymap_mgr.get_key_for_note(note)
            if mapped_char:
                self.canvas.create_text(
                    x + key_w / 2, key_h - 15,
                    text=mapped_char, fill="#202030", font=("Consolas", 10, "bold")
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
                        fill="#252533", outline="#101018", width=1
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
    """Main Application Window with Integrated Zero-Latency Yamaha C5 Acoustic Grand Piano Engine."""

    def __init__(self):
        super().__init__()

        self.title("Roblox MIDI Keyboard Mapper & Yamaha C5 Grand Piano Player")
        self.geometry("1100 x 820")
        self.minsize(960, 700)

        # Core Engines
        self.keymap_mgr = KeymapManager()
        self.simulator = KeyboardSimulator(mode="VIRTUAL_KEY", trigger_type="HOLD")
        self.piano_engine = SalamanderGrandPianoEngine()
        self.engine = MidiEngine(self.keymap_mgr, self.simulator, piano_engine=self.piano_engine)
        self.file_player = MidiFilePlayer(self.keymap_mgr, self.simulator)

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

        self.logging_enabled = True

        self._build_ui()
        self._refresh_midi_ports()

    def _build_ui(self):
        # Header Bar
        header_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="#1F1F2E")
        header_frame.pack(fill="x", padx=15, pady=(15, 8))

        title_label = ctk.CTkLabel(
            header_frame,
            text="🎹 Roblox MIDI Mapper + Yamaha C5 Acoustic Grand Piano",
            font=ctk.CTkFont(family="Consolas", size=20, weight="bold"),
            text_color="#00E5FF"
        )
        title_label.pack(side="left", padx=15, pady=10)

        self.status_badge = ctk.CTkLabel(
            header_frame,
            text="● DISCONNECTED",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#FF4B4B"
        )
        self.status_badge.pack(side="right", padx=15, pady=10)

        # Main Layout
        main_content = ctk.CTkFrame(self, fg_color="transparent")
        main_content.pack(fill="both", expand=True, padx=15, pady=5)

        # Left Column (Device & Controls)
        left_col = ctk.CTkFrame(main_content, width=370, corner_radius=10, fg_color="#1E1E2A")
        left_col.pack(side="left", fill="y", padx=(0, 10), pady=5)
        left_col.pack_propagate(False)

        # MIDI Connection Card
        conn_box = ctk.CTkFrame(left_col, corner_radius=8, fg_color="#252538")
        conn_box.pack(fill="x", padx=10, pady=8)

        conn_title = ctk.CTkLabel(conn_box, text="MIDI INPUT DEVICE", font=ctk.CTkFont(size=12, weight="bold"), text_color="#A0A0B0")
        conn_title.pack(anchor="w", padx=10, pady=(8, 4))

        self.port_dropdown = ctk.CTkComboBox(conn_box, values=["Searching..."], height=32)
        self.port_dropdown.pack(fill="x", padx=10, pady=4)

        btn_row = ctk.CTkFrame(conn_box, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(4, 8))

        self.refresh_btn = ctk.CTkButton(btn_row, text="🔄 Refresh", width=90, height=32, command=self._refresh_midi_ports)
        self.refresh_btn.pack(side="left", padx=(0, 5))

        self.connect_btn = ctk.CTkButton(
            btn_row, text="Connect", width=120, height=32,
            fg_color="#28A745", hover_color="#218838",
            command=self._toggle_connection
        )
        self.connect_btn.pack(side="left", fill="x", expand=True)

        # Yamaha C5 Acoustic Grand Piano Card
        piano_box = ctk.CTkFrame(left_col, corner_radius=8, fg_color="#252538")
        piano_box.pack(fill="x", padx=10, pady=5)

        piano_title = ctk.CTkLabel(piano_box, text="🎧 YAMAHA C5 DIRECT AUDIO (0ms Latency)", font=ctk.CTkFont(size=12, weight="bold"), text_color="#00E5FF")
        piano_title.pack(anchor="w", padx=10, pady=(8, 2))

        self.piano_switch = ctk.CTkSwitch(
            piano_box, text="Enable Direct Grand Piano Sound",
            command=self._toggle_piano_sound
        )
        self.piano_switch.select()
        self.piano_switch.pack(anchor="w", padx=10, pady=4)

        # Volume Slider
        vol_label = ctk.CTkLabel(piano_box, text="Piano Volume:", font=ctk.CTkFont(size=11), text_color="#A0A0B0")
        vol_label.pack(anchor="w", padx=10, pady=(2, 0))

        self.vol_slider = ctk.CTkSlider(piano_box, from_=0.0, to=1.0, number_of_steps=20, command=self._on_volume_changed)
        self.vol_slider.set(0.85)
        self.vol_slider.pack(fill="x", padx=10, pady=(2, 8))

        # Output Settings Card
        settings_box = ctk.CTkFrame(left_col, corner_radius=8, fg_color="#252538")
        settings_box.pack(fill="x", padx=10, pady=5)

        settings_title = ctk.CTkLabel(settings_box, text="KEYBOARD MAPPING SETTINGS", font=ctk.CTkFont(size=12, weight="bold"), text_color="#A0A0B0")
        settings_title.pack(anchor="w", padx=10, pady=(8, 4))

        self.enable_switch = ctk.CTkSwitch(
            settings_box, text="Simulate Keystrokes (F8 Toggle)",
            command=self._on_switch_toggled
        )
        self.enable_switch.select()
        self.enable_switch.pack(anchor="w", padx=10, pady=4)

        # Transpose Slider
        transpose_frame = ctk.CTkFrame(settings_box, fg_color="transparent")
        transpose_frame.pack(fill="x", padx=10, pady=4)

        ctk.CTkLabel(transpose_frame, text="Transpose:", font=ctk.CTkFont(size=12)).pack(side="left")
        self.transpose_val_label = ctk.CTkLabel(transpose_frame, text="0 Semi", font=ctk.CTkFont(size=12, weight="bold"), text_color="#00E5FF")
        self.transpose_val_label.pack(side="right")

        self.transpose_slider = ctk.CTkSlider(
            settings_box, from_=-24, to=24, number_of_steps=48,
            command=self._on_transpose_changed
        )
        self.transpose_slider.set(0)
        self.transpose_slider.pack(fill="x", padx=10, pady=(2, 8))

        # Right Column (Piano Visualizer, MIDI File Player, Logs)
        right_col = ctk.CTkFrame(main_content, corner_radius=10, fg_color="#1E1E2A")
        right_col.pack(side="right", fill="both", expand=True, pady=5)

        # Piano Visualizer
        vis_title = ctk.CTkLabel(right_col, text="LIVE 61-KEY PIANO VISUALIZER", font=ctk.CTkFont(size=12, weight="bold"), text_color="#A0A0B0")
        vis_title.pack(anchor="w", padx=15, pady=(10, 2))

        self.visualizer = PianoVisualizerCanvas(right_col, self.keymap_mgr, height=130, corner_radius=8, fg_color="#181824")
        self.visualizer.pack(fill="x", padx=15, pady=(0, 10))

        # MIDI File Player Section
        player_box = ctk.CTkFrame(right_col, corner_radius=8, fg_color="#252538")
        player_box.pack(fill="x", padx=15, pady=(0, 10))

        player_header = ctk.CTkFrame(player_box, fg_color="transparent")
        player_header.pack(fill="x", padx=10, pady=(8, 2))

        ctk.CTkLabel(player_header, text="🎵 MIDI FILE PLAYER & SHEET CONVERTER", font=ctk.CTkFont(size=12, weight="bold"), text_color="#00E5FF").pack(side="left")

        self.file_label = ctk.CTkLabel(player_header, text="No file loaded", font=ctk.CTkFont(size=11), text_color="#A0A0B0")
        self.file_label.pack(side="right")

        controls_row = ctk.CTkFrame(player_box, fg_color="transparent")
        controls_row.pack(fill="x", padx=10, pady=4)

        self.load_btn = ctk.CTkButton(controls_row, text="📁 Open .mid", width=100, height=28, command=self._open_midi_file)
        self.load_btn.pack(side="left", padx=(0, 5))

        self.play_btn = ctk.CTkButton(controls_row, text="▶ Play", width=80, height=28, fg_color="#28A745", hover_color="#218838", command=self._play_midi_file)
        self.play_btn.pack(side="left", padx=5)

        self.pause_btn = ctk.CTkButton(controls_row, text="⏸ Pause", width=80, height=28, fg_color="#FFA500", hover_color="#CC8400", command=self._pause_midi_file)
        self.pause_btn.pack(side="left", padx=5)

        self.stop_btn = ctk.CTkButton(controls_row, text="⏹ Stop", width=80, height=28, fg_color="#DC3545", hover_color="#C82333", command=self._stop_midi_file)
        self.stop_btn.pack(side="left", padx=5)

        self.sheet_btn = ctk.CTkButton(controls_row, text="🎼 View Sheet Text", width=130, height=28, fg_color="#6C757D", hover_color="#5A6268", command=self._view_sheet_notation)
        self.sheet_btn.pack(side="right")

        # Progress Bar
        progress_row = ctk.CTkFrame(player_box, fg_color="transparent")
        progress_row.pack(fill="x", padx=10, pady=(2, 8))

        self.progress_bar = ctk.CTkProgressBar(progress_row, height=8)
        self.progress_bar.set(0)
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.time_label = ctk.CTkLabel(progress_row, text="00:00 / 00:00", font=ctk.CTkFont(size=11), text_color="#A0A0B0")
        self.time_label.pack(side="right")

        # MIDI Log Console
        log_header = ctk.CTkFrame(right_col, fg_color="transparent")
        log_header.pack(fill="x", padx=15, pady=(5, 2))

        ctk.CTkLabel(log_header, text="EVENT LOGS", font=ctk.CTkFont(size=12, weight="bold"), text_color="#A0A0B0").pack(side="left")

        self.log_checkbox = ctk.CTkCheckBox(log_header, text="Enable Logging", command=self._toggle_logging)
        self.log_checkbox.select()
        self.log_checkbox.pack(side="right")

        self.log_textbox = ctk.CTkTextbox(right_col, height=130, font=("Consolas", 11), fg_color="#14141E", text_color="#00FF66")
        self.log_textbox.pack(fill="both", expand=True, padx=15, pady=(0, 10))

    def _toggle_piano_sound(self):
        enabled = bool(self.piano_switch.get())
        self.piano_engine.set_enabled(enabled)
        state_str = "ENABLED" if enabled else "DISABLED"
        self.log_message(f"Yamaha C5 Direct Audio: {state_str}")

    def _on_volume_changed(self, val):
        self.piano_engine.set_volume(float(val))

    def _toggle_logging(self):
        self.logging_enabled = bool(self.log_checkbox.get())

    def _refresh_midi_ports(self):
        ports = get_available_midi_ports()
        if ports:
            self.port_dropdown.configure(values=ports)
            self.port_dropdown.set(ports[0])
            self.log_message(f"Found {len(ports)} MIDI device(s): {', '.join(ports)}")
        else:
            self.port_dropdown.configure(values=["No Devices Found"])
            self.port_dropdown.set("No Devices Found")
            self.log_message("No MIDI devices detected. Plug in your keyboard and click Refresh.")

    def _toggle_connection(self):
        if self.engine.is_running:
            self.engine.stop()
            self.connect_btn.configure(text="Connect", fg_color="#28A745", hover_color="#218838")
            self.status_badge.configure(text="● DISCONNECTED", text_color="#FF4B4B")
        else:
            selected_port = self.port_dropdown.get()
            if selected_port and selected_port != "No Devices Found":
                success = self.engine.start(selected_port)
                if success:
                    self.connect_btn.configure(text="Disconnect", fg_color="#DC3545", hover_color="#C82333")
                    self.status_badge.configure(text="● CONNECTED & LISTENING", text_color="#00E5FF")
            else:
                self.log_message("Please select a valid MIDI device port.")

    def _on_switch_toggled(self):
        enabled = bool(self.enable_switch.get())
        self.simulator.set_enabled(enabled)
        state_str = "ENABLED" if enabled else "MUTED"
        self.log_message(f"Mapping switch changed to: {state_str}")

    def _on_toggle_state_changed(self, enabled: bool):
        self.after(0, lambda: self.enable_switch.select() if enabled else self.enable_switch.deselect())

    def _on_transpose_changed(self, val):
        semitones = int(val)
        self.engine.transpose = semitones
        self.file_player.transpose = semitones
        sign = "+" if semitones > 0 else ""
        self.transpose_val_label.configure(text=f"{sign}{semitones} Semi")
        self.visualizer._draw_keyboard()

    def _open_midi_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("MIDI Files", "*.mid;*.midi")])
        if file_path:
            success = self.file_player.load_file(file_path)
            if success:
                import os
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
        self.file_player.stop()
        self.engine.stop()
        if self.piano_engine:
            self.piano_engine.close()
        self.destroy()
