import tkinter as tk
from tkinter import ttk, filedialog
import customtkinter as ctk
import time
from typing import Dict, Optional

from keymap_config import KeymapManager, DEFAULT_ROBLOX_61KEY_MAP, midi_note_to_name
from keyboard_simulator import KeyboardSimulator
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
        """Highlights or un-highlights a note on the canvas."""
        self.pressed_notes[note] = is_pressed
        self._update_note_color(note)

    def _update_note_color(self, note: int):
        is_pressed = self.pressed_notes.get(note, False)

        if note in self.white_keys_rects:
            color = "#00E5FF" if is_pressed else "#FFFFFF"  # Cyan highlight when pressed
            self.canvas.itemconfig(self.white_keys_rects[note], fill=color)
        elif note in self.black_keys_rects:
            color = "#FF2A85" if is_pressed else "#252533"  # Neon Pink highlight when pressed
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
    """Main Application Window for Roblox MIDI Mapper and File Player."""

    def __init__(self):
        super().__init__()

        self.title("Roblox MIDI Keyboard Mapper & File Player v2.0")
        self.geometry("1060 x 780")
        self.minsize(920, 680)

        # Core Engines
        self.keymap_mgr = KeymapManager()
        self.simulator = KeyboardSimulator(mode="VIRTUAL_KEY", trigger_type="HOLD")
        self.engine = MidiEngine(self.keymap_mgr, self.simulator)
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
            text="🎹 ROBLOX MIDI KEYBOARD MAPPER & PLAYER",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#00E5FF"
        )
        title_label.pack(side="left", padx=15, pady=12)

        self.status_badge = ctk.CTkLabel(
            header_frame,
            text="● DISCONNECTED",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#FF4B4B",
            fg_color="#2A2A3D",
            corner_radius=6,
            padx=10,
            pady=4
        )
        self.status_badge.pack(side="right", padx=15, pady=12)

        # Top Control Row: Device Connection & Toggle Switch
        top_ctrl_frame = ctk.CTkFrame(self, corner_radius=10)
        top_ctrl_frame.pack(fill="x", padx=15, pady=4)

        ctk.CTkLabel(top_ctrl_frame, text="MIDI Input Device:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(15, 5), pady=10)

        self.port_dropdown = ctk.CTkOptionMenu(top_ctrl_frame, values=["Scanning..."], width=240)
        self.port_dropdown.pack(side="left", padx=5, pady=10)

        self.refresh_btn = ctk.CTkButton(top_ctrl_frame, text="🔄 Refresh", width=90, command=self._refresh_midi_ports)
        self.refresh_btn.pack(side="left", padx=5, pady=10)

        self.connect_btn = ctk.CTkButton(top_ctrl_frame, text="Connect", width=100, fg_color="#28A745", hover_color="#218838", command=self._toggle_connection)
        self.connect_btn.pack(side="left", padx=10, pady=10)

        self.enable_switch = ctk.CTkSwitch(
            top_ctrl_frame,
            text="Enable Mapping (F8)",
            font=ctk.CTkFont(weight="bold"),
            command=self._on_switch_toggled
        )
        self.enable_switch.select()
        self.enable_switch.pack(side="right", padx=15, pady=10)

        # MIDI File Player Section
        player_frame = ctk.CTkFrame(self, corner_radius=10, fg_color="#181824")
        player_frame.pack(fill="x", padx=15, pady=4)

        player_header = ctk.CTkFrame(player_frame, fg_color="transparent")
        player_header.pack(fill="x", padx=10, pady=(8, 2))

        ctk.CTkLabel(player_header, text="📁 MIDI File Player & Roblox Sheet Converter:", font=ctk.CTkFont(size=13, weight="bold"), text_color="#00E5FF").pack(side="left")

        self.load_file_btn = ctk.CTkButton(player_header, text="📁 Load MIDI File...", width=140, fg_color="#6C5CE7", hover_color="#5A4BD1", command=self._browse_midi_file)
        self.load_file_btn.pack(side="left", padx=15)

        self.file_label = ctk.CTkLabel(player_header, text="No MIDI file loaded", font=ctk.CTkFont(size=12), text_color="#AAA")
        self.file_label.pack(side="left", padx=5)

        self.gen_sheet_btn = ctk.CTkButton(player_header, text="📄 Export Sheet (.txt)", width=140, fg_color="#17A2B8", hover_color="#138496", command=self._open_sheet_exporter)
        self.gen_sheet_btn.pack(side="right")

        # Player Controls Row
        ctrl_row = ctk.CTkFrame(player_frame, fg_color="transparent")
        ctrl_row.pack(fill="x", padx=10, pady=(4, 8))

        self.play_btn = ctk.CTkButton(ctrl_row, text="▶ Play", width=80, fg_color="#28A745", hover_color="#218838", command=self._play_file)
        self.play_btn.pack(side="left", padx=4)

        self.pause_btn = ctk.CTkButton(ctrl_row, text="⏸ Pause", width=80, fg_color="#FFC107", hover_color="#E0A800", text_color="#202030", command=self._pause_file)
        self.pause_btn.pack(side="left", padx=4)

        self.stop_btn = ctk.CTkButton(ctrl_row, text="⏹ Stop", width=80, fg_color="#DC3545", hover_color="#C82333", command=self._stop_file)
        self.stop_btn.pack(side="left", padx=4)

        self.progress_label = ctk.CTkLabel(ctrl_row, text="00:00 / 00:00", font=ctk.CTkFont(size=12, weight="bold"), width=100)
        self.progress_label.pack(side="left", padx=10)

        self.progress_bar = ctk.CTkProgressBar(ctrl_row, width=280)
        self.progress_bar.set(0)
        self.progress_bar.pack(side="left", padx=10)

        ctk.CTkLabel(ctrl_row, text="Speed:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(10, 2))
        self.speed_val_label = ctk.CTkLabel(ctrl_row, text="1.0x", width=40, font=ctk.CTkFont(weight="bold"), text_color="#00E5FF")
        self.speed_val_label.pack(side="left", padx=2)

        self.speed_slider = ctk.CTkSlider(ctrl_row, from_=0.5, to=2.0, number_of_steps=15, width=120, command=self._on_speed_changed)
        self.speed_slider.set(1.0)
        self.speed_slider.pack(side="left", padx=5)

        # Middle Controls Row: Transpose, Input Engine & Trigger Mode Settings
        settings_frame = ctk.CTkFrame(self, corner_radius=10)
        settings_frame.pack(fill="x", padx=15, pady=4)

        ctk.CTkLabel(settings_frame, text="Transpose:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(15, 5), pady=8)

        self.transpose_val_label = ctk.CTkLabel(settings_frame, text="0 Semi", width=60, font=ctk.CTkFont(weight="bold"), text_color="#00E5FF")
        self.transpose_val_label.pack(side="left", padx=2, pady=8)

        self.transpose_slider = ctk.CTkSlider(
            settings_frame,
            from_=-24,
            to=24,
            number_of_steps=48,
            width=130,
            command=self._on_transpose_changed
        )
        self.transpose_slider.set(0)
        self.transpose_slider.pack(side="left", padx=5, pady=8)

        self.reset_trans_btn = ctk.CTkButton(settings_frame, text="Reset", width=60, command=self._reset_transpose)
        self.reset_trans_btn.pack(side="left", padx=5, pady=8)

        ctk.CTkLabel(settings_frame, text="Trigger Mode:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(15, 5), pady=8)
        self.trigger_dropdown = ctk.CTkOptionMenu(
            settings_frame,
            values=["Hold Key (Sustain)", "Tap Key (Instant Pulse)"],
            width=175,
            command=self._on_trigger_mode_changed
        )
        self.trigger_dropdown.set("Hold Key (Sustain)")
        self.trigger_dropdown.pack(side="left", padx=5, pady=8)

        ctk.CTkLabel(settings_frame, text="Engine:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(15, 5), pady=8)
        self.mode_dropdown = ctk.CTkOptionMenu(
            settings_frame,
            values=["Virtual Key (Win32)", "Unicode Direct"],
            width=150,
            command=self._on_mode_changed
        )
        self.mode_dropdown.set("Virtual Key (Win32)")
        self.mode_dropdown.pack(side="left", padx=5, pady=8)

        # Visualizer Frame
        viz_frame = ctk.CTkFrame(self, corner_radius=10)
        viz_frame.pack(fill="both", expand=True, padx=15, pady=4)

        ctk.CTkLabel(viz_frame, text="Live Roblox Piano Keyboard Layout (C2 to C7):", font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=15, pady=(6, 2))

        self.visualizer = PianoVisualizerCanvas(viz_frame, self.keymap_mgr, height=150, fg_color="#181824", corner_radius=8)
        self.visualizer.pack(fill="both", expand=True, padx=10, pady=(2, 8))

        # Bottom Frame: Live Activity Log
        log_frame = ctk.CTkFrame(self, corner_radius=10)
        log_frame.pack(fill="x", padx=15, pady=(4, 12))

        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=10, pady=(4, 0))

        ctk.CTkLabel(log_header, text="Activity Feed & MIDI Event Log:", font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")

        self.log_checkbox = ctk.CTkCheckBox(log_header, text="Enable Logging", command=self._toggle_logging)
        self.log_checkbox.select()
        self.log_checkbox.pack(side="right", padx=(10, 0))

        ctk.CTkButton(log_header, text="Clear Log", width=70, height=22, command=self._clear_log).pack(side="right")

        self.log_textbox = ctk.CTkTextbox(log_frame, height=100, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_textbox.pack(fill="x", padx=10, pady=(4, 8))

    def _browse_midi_file(self):
        filepath = filedialog.askopenfilename(
            title="Select MIDI File",
            filetypes=[("MIDI Files", "*.mid *.midi"), ("All Files", "*.*")]
        )
        if filepath:
            success = self.file_player.load_file(filepath)
            if success:
                filename = filepath.split("/")[-1].split("\\")[-1]
                self.file_label.configure(text=f"Loaded: {filename}", text_color="#00E5FF")
                dur_str = self.file_player.format_time(self.file_player.total_duration)
                self.progress_label.configure(text=f"00:00 / {dur_str}")
                self.progress_bar.set(0)

    def _play_file(self):
        self.file_player.play()

    def _pause_file(self):
        self.file_player.pause()

    def _stop_file(self):
        self.file_player.stop()
        self.progress_bar.set(0)
        dur_str = self.file_player.format_time(self.file_player.total_duration)
        self.progress_label.configure(text=f"00:00 / {dur_str}")

    def _on_speed_changed(self, val):
        speed = round(float(val), 2)
        self.file_player.set_speed(speed)
        self.speed_val_label.configure(text=f"{speed:.1f}x")

    def _on_player_progress_updated(self, elapsed: float, total: float):
        if total > 0:
            frac = max(0.0, min(1.0, elapsed / total))
            el_str = self.file_player.format_time(elapsed)
            tot_str = self.file_player.format_time(total)
            self.after(0, lambda: self._update_progress_ui(frac, el_str, tot_str))

    def _update_progress_ui(self, frac: float, el_str: str, tot_str: str):
        self.progress_bar.set(frac)
        self.progress_label.configure(text=f"{el_str} / {tot_str}")

    def _on_player_finished(self):
        self.after(0, lambda: self.progress_bar.set(1.0))

    def _open_sheet_exporter(self):
        if not self.file_player.midi_file:
            self.log_message("Please load a MIDI file first to generate a sheet.")
            return

        sheet_text = self.file_player.generate_sheet_text(transpose=self.engine.transpose)

        # Popup window for Roblox Sheet exporter
        win = ctk.CTkToplevel(self)
        win.title("Exported Roblox Piano Sheet Notation")
        win.geometry("700 x 480")
        win.transient(self)

        ctk.CTkLabel(win, text="📄 Roblox Virtual Piano Sheet Notation:", font=ctk.CTkFont(size=14, weight="bold"), text_color="#00E5FF").pack(anchor="w", padx=15, pady=(15, 5))

        txt = ctk.CTkTextbox(win, font=ctk.CTkFont(family="Consolas", size=12))
        txt.pack(fill="both", expand=True, padx=15, pady=5)
        txt.insert("1.0", sheet_text)

        def copy_clip():
            self.clipboard_clear()
            self.clipboard_append(sheet_text)
            copy_btn.configure(text="✅ Copied to Clipboard!")
            self.after(2000, lambda: copy_btn.configure(text="📋 Copy Sheet to Clipboard"))

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=15, pady=(5, 15))

        copy_btn = ctk.CTkButton(btn_row, text="📋 Copy Sheet to Clipboard", fg_color="#28A745", hover_color="#218838", command=copy_clip)
        copy_btn.pack(side="right", padx=5)

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
        self.after(0, lambda: self._update_switch_ui(enabled))

    def _update_switch_ui(self, enabled: bool):
        if enabled:
            self.enable_switch.select()
        else:
            self.enable_switch.deselect()

    def _on_trigger_mode_changed(self, val: str):
        trigger_type = "TAP" if "Tap" in val else "HOLD"
        self.simulator.set_trigger_type(trigger_type)
        self.log_message(f"Trigger Mode set to: {val}")

    def _on_mode_changed(self, val: str):
        mode = "UNICODE" if "Unicode" in val else "VIRTUAL_KEY"
        self.simulator.set_mode(mode)
        self.log_message(f"Input Engine set to: {val}")

    def _on_transpose_changed(self, val):
        semitones = int(val)
        self.engine.transpose = semitones
        self.file_player.transpose = semitones
        sign = "+" if semitones > 0 else ""
        self.transpose_val_label.configure(text=f"{sign}{semitones} Semi")
        self.visualizer._draw_keyboard()

    def _reset_transpose(self):
        self.transpose_slider.set(0)
        self._on_transpose_changed(0)

    def _on_midi_note_on(self, note: int, velocity: int, mapped_key: Optional[str]):
        self.after(0, lambda: self.visualizer.set_note_state(note + self.engine.transpose, True))

    def _on_midi_note_off(self, note: int, mapped_key: Optional[str]):
        self.after(0, lambda: self.visualizer.set_note_state(note + self.engine.transpose, False))

    def log_message(self, text: str):
        if not self.logging_enabled:
            return
        timestamp = time.strftime("[%H:%M:%S] ")
        self.after(0, lambda: self._append_log(timestamp + text + "\n"))

    def _append_log(self, full_text: str):
        self.log_textbox.insert("end", full_text)
        self.log_textbox.see("end")

    def _clear_log(self):
        self.log_textbox.delete("1.0", "end")

    def on_closing(self):
        self.file_player.stop()
        self.engine.stop()
        self.destroy()
