import os
import sys
import json
import time
import webview
from typing import Dict, Optional, List, Tuple

from keymap_config import KeymapManager, midi_note_to_name
from keyboard_simulator import KeyboardSimulator
from salamander_engine import SalamanderGrandPianoEngine, get_low_latency_output_devices, get_all_output_devices
from midi_engine import MidiEngine, get_available_midi_ports
from midi_file_player import MidiFilePlayer

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "user_settings.json")


class DesktopAppBridge:
    """JS-to-Python bridge exposed to pywebview window."""

    def __init__(self):
        self.window = None
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
        self.engine.velocity_curve = self.config.get("velocity_curve", "linear")

        self.file_player = MidiFilePlayer(self.keymap_mgr, self.simulator, piano_engine=self.piano_engine)
        self.file_player.transpose = self.config.get("transpose", 0)
        self.file_player.velocity_curve = self.config.get("velocity_curve", "linear")

        # Hook engine callbacks
        self.engine.on_note_on_cb = self._on_midi_note_on
        self.engine.on_note_off_cb = self._on_midi_note_off
        self.engine.on_log_cb = self._on_log
        self.engine.on_toggle_state_cb = self._on_toggle_state_changed

        self.file_player.on_note_on_cb = self._on_midi_note_on
        self.file_player.on_note_off_cb = self._on_midi_note_off
        self.file_player.on_log_cb = self._on_log
        self.file_player.on_progress_cb = self._on_player_progress
        self.file_player.on_playback_finished_cb = self._on_player_finished

        self.audio_devices: List[Tuple[int, str]] = []
        self.all_devices: List[Tuple[int, str]] = []

    def set_window(self, window):
        self.window = window

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
                    default_config.update(json.load(f))
            except Exception as e:
                print(f"Error loading config: {e}")
        return default_config

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    # ================= JS Callable Methods =================

    def get_initial_state(self):
        ports = get_available_midi_ports()
        self.audio_devices = get_low_latency_output_devices()
        self.all_devices = get_all_output_devices()

        audio_names = [name for _, name in self.audio_devices]
        all_names = [name for _, name in self.all_devices]

        # Determine default devices
        saved_audio = self.config.get("last_audio_device")
        current_audio = saved_audio if saved_audio in audio_names else (audio_names[0] if audio_names else "")
        if current_audio:
            self.set_audio_device(current_audio)

        saved_vmic = self.config.get("last_virtual_mic_device")
        cable_matches = [n for n in all_names if "cable" in n.lower() or "virtual" in n.lower()]
        current_vmic = saved_vmic if saved_vmic in all_names else (cable_matches[0] if cable_matches else (all_names[0] if all_names else ""))
        if current_vmic:
            self.set_vmic_device(current_vmic)

        saved_port = self.config.get("last_midi_port")
        current_port = saved_port if saved_port in ports else (ports[0] if ports else "")

        # Auto-connect if enabled
        if self.config.get("auto_connect", True) and current_port:
            self.engine.start(current_port)

        return {
            "midi_ports": ports,
            "current_midi_port": current_port,
            "is_connected": self.engine.is_running,
            "audio_devices": audio_names,
            "current_audio_dev": current_audio,
            "all_audio_devices": all_names,
            "current_vmic_dev": current_vmic,
            "piano_sound_enabled": self.config.get("piano_sound_enabled", True),
            "piano_volume": self.config.get("piano_volume", 0.85),
            "virtual_mic_enabled": self.config.get("virtual_mic_enabled", False),
            "virtual_mic_volume": self.config.get("virtual_mic_volume", 0.85),
            "keystrokes_enabled": self.config.get("keystrokes_enabled", True),
            "transpose": self.config.get("transpose", 0),
            "velocity_curve": self.config.get("velocity_curve", "linear"),
            "auto_connect": self.config.get("auto_connect", True),
            "logging_enabled": self.config.get("logging_enabled", True),
            "keymap": {int(n): k for n, k in self.keymap_mgr.mapping.items()}
        }

    def set_velocity_curve(self, curve_name: str):
        self.engine.velocity_curve = curve_name
        self.file_player.velocity_curve = curve_name
        self.config["velocity_curve"] = curve_name
        self._save_config()
        self._on_log(f"Velocity Response Curve switched to: {curve_name.upper()}")

    def refresh_midi_ports(self):
        ports = get_available_midi_ports()
        self._on_log(f"Found {len(ports)} MIDI device(s): {', '.join(ports) if ports else 'None'}")
        return ports

    def toggle_midi_connection(self, port_name: str):
        if self.engine.is_running:
            self.engine.stop()
            self._on_log("MIDI Engine Disconnected.")
            return False
        else:
            if port_name and port_name != "No Devices Found":
                success = self.engine.start(port_name)
                if success:
                    self.config["last_midi_port"] = port_name
                    self._save_config()
                    self._on_log(f"Connected to MIDI device: {port_name}")
                    return True
            self._on_log("Select a valid MIDI device port to connect.")
            return False

    def toggle_piano_sound(self, enabled: bool):
        self.piano_engine.set_enabled(enabled)
        self.config["piano_sound_enabled"] = enabled
        self._save_config()
        self._on_log(f"Direct Grand Piano Output: {'ENABLED' if enabled else 'MUTED'}")

    def set_audio_device(self, chosen_name: str):
        for dev_id, name in self.audio_devices:
            if name == chosen_name:
                self.piano_engine.set_device(dev_id)
                self.config["last_audio_device"] = chosen_name
                self._save_config()
                self._on_log(f"Active WASAPI monitoring: {chosen_name}")
                break

    def set_piano_volume(self, volume: float):
        self.piano_engine.set_volume(volume)
        self.config["piano_volume"] = volume
        self._save_config()

    def toggle_virtual_mic(self, enabled: bool):
        self.piano_engine.set_virtual_mic_enabled(enabled)
        self.config["virtual_mic_enabled"] = enabled
        self._save_config()
        self._on_log(f"Virtual Mic Broadcast: {'ENABLED' if enabled else 'MUTED'}")

    def set_vmic_device(self, chosen_name: str):
        for dev_id, name in self.all_devices:
            if name == chosen_name:
                self.piano_engine.set_virtual_mic_device(dev_id)
                self.config["last_virtual_mic_device"] = chosen_name
                self._save_config()
                self._on_log(f"Active Virtual Mic target: {chosen_name}")
                break

    def set_vmic_volume(self, volume: float):
        self.piano_engine.set_virtual_mic_volume(volume)
        self.config["virtual_mic_volume"] = volume
        self._save_config()

    def toggle_keystrokes(self, enabled: bool):
        self.simulator.set_enabled(enabled)
        self.config["keystrokes_enabled"] = enabled
        self._save_config()
        self._on_log(f"Roblox Keyboard Mapping: {'ENABLED' if enabled else 'MUTED'}")

    def set_transpose(self, semitones: int):
        self.engine.transpose = semitones
        self.file_player.transpose = semitones
        self.config["transpose"] = semitones
        self._save_config()
        sign = "+" if semitones > 0 else ""
        self._on_log(f"Pitch Transposition adjusted to {sign}{semitones} semitones.")

    def save_setting(self, key: str, value):
        self.config[key] = value
        self._save_config()

    def open_midi_file(self):
        if not self.window:
            return
        file_types = ('MIDI Files (*.mid;*.midi)', 'All files (*.*)')
        result = self.window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
        if result and len(result) > 0:
            file_path = result[0]
            success = self.file_player.load_file(file_path)
            if success:
                fname = os.path.basename(file_path)
                total_str = MidiFilePlayer.format_time(self.file_player.total_duration)
                self.window.evaluate_js(f"window.py_onFileLoaded('{fname}', '{total_str}')")
                self._on_log(f"Loaded MIDI file: {fname} ({total_str})")

    def play_midi_file(self):
        self.file_player.play()

    def pause_midi_file(self):
        self.file_player.pause()

    def stop_midi_file(self):
        self.file_player.stop()
        if self.window:
            self.window.evaluate_js("window.py_onProgress(0, '00:00', '00:00')")

    def get_sheet_text(self) -> str:
        sheet_text = self.file_player.generate_sheet_text(transpose=self.engine.transpose)
        if not sheet_text:
            self._on_log("Please open a MIDI file first to generate sheet notation.")
            return ""
        return sheet_text

    # ================= Callbacks to Frontend JS =================

    def _on_midi_note_on(self, note: int, velocity: int, mapped_key: Optional[str]):
        if self.window:
            effective = note + self.engine.transpose
            self.window.evaluate_js(f"window.py_onNoteOn({effective})")

    def _on_midi_note_off(self, note: int, mapped_key: Optional[str]):
        if self.window:
            effective = note + self.engine.transpose
            self.window.evaluate_js(f"window.py_onNoteOff({effective})")

    def _on_log(self, text: str):
        if self.window:
            clean_text = text.replace("'", "\\'").replace("\n", " ")
            self.window.evaluate_js(f"window.py_onLog('{clean_text}')")

    def _on_toggle_state_changed(self, enabled: bool):
        if self.window:
            self.window.evaluate_js(f"window.py_onToggleKeystrokes({str(enabled).lower()})")
        self.config["keystrokes_enabled"] = enabled
        self._save_config()

    def _on_player_progress(self, elapsed: float, total: float):
        if self.window and total > 0:
            frac = min(1.0, elapsed / total)
            elapsed_str = MidiFilePlayer.format_time(elapsed)
            total_str = MidiFilePlayer.format_time(total)
            self.window.evaluate_js(f"window.py_onProgress({frac}, '{elapsed_str}', '{total_str}')")

    def _on_player_finished(self):
        if self.window:
            total_str = MidiFilePlayer.format_time(self.file_player.total_duration)
            self.window.evaluate_js(f"window.py_onProgress(0, '00:00', '{total_str}')")

    def cleanup(self):
        self._save_config()
        self.file_player.stop()
        self.engine.stop()
        if self.piano_engine:
            self.piano_engine.close()
