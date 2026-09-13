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
from websocket_bridge import WebSocketMidiBroadcaster

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "user_settings.json")


class DesktopAppBridge:
    """JS-to-Python bridge exposed to pywebview window."""

    def __init__(self):
        self._window = None
        self._config = self._load_config()

        # Core Engines (marked private with _ to prevent pywebview introspection recursion)
        self._keymap_mgr = KeymapManager()
        self._simulator = KeyboardSimulator(
            mode=self._config.get("input_mode", "VIRTUAL_KEY"),
            trigger_type=self._config.get("trigger_type", "HOLD")
        )
        self._simulator.set_enabled(self._config.get("keystrokes_enabled", True))

        self._piano_engine = SalamanderGrandPianoEngine()
        self._piano_engine.set_enabled(self._config.get("piano_sound_enabled", True))
        self._piano_engine.set_volume(self._config.get("piano_volume", 0.85))
        self._piano_engine.set_virtual_mic_enabled(self._config.get("virtual_mic_enabled", False))
        self._piano_engine.set_virtual_mic_volume(self._config.get("virtual_mic_volume", 0.85))
        if "soundbank" in self._config:
            self._piano_engine.set_soundbank(self._config["soundbank"])

        self._engine = MidiEngine(self._keymap_mgr, self._simulator, piano_engine=self._piano_engine)
        self._engine.transpose = self._config.get("transpose", 0)
        self._engine.velocity_curve = self._config.get("velocity_curve", "linear")

        self._file_player = MidiFilePlayer(self._keymap_mgr, self._simulator, piano_engine=self._piano_engine)
        self._file_player.transpose = self._config.get("transpose", 0)
        self._file_player.velocity_curve = self._config.get("velocity_curve", "linear")

        # WebSocket Broadcaster (ws://localhost:8765 for PianoWeb and other web apps)
        self._ws_broadcaster = WebSocketMidiBroadcaster(host="127.0.0.1", port=8765)
        self._ws_broadcaster.on_log_cb = self._on_log
        self._ws_broadcaster.on_client_count_change_cb = self._on_ws_clients_changed
        self._ws_broadcaster.start()

        # Hook engine callbacks
        self._engine.on_note_on_cb = self._on_midi_note_on
        self._engine.on_note_off_cb = self._on_midi_note_off
        self._engine.on_sustain_cb = self._on_midi_sustain
        self._engine.on_log_cb = self._on_log
        self._engine.on_toggle_state_cb = self._on_toggle_state_changed

        self._file_player.on_note_on_cb = self._on_midi_note_on
        self._file_player.on_note_off_cb = self._on_midi_note_off
        self._file_player.on_sustain_cb = self._on_midi_sustain
        self._file_player.on_log_cb = self._on_log
        self._file_player.on_progress_cb = self._on_player_progress
        self._file_player.on_playback_finished_cb = self._on_player_finished

        self._audio_devices: List[Tuple[int, str]] = []
        self._all_devices: List[Tuple[int, str]] = []

    def set_window(self, window):
        self._window = window

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
                json.dump(self._config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    # ================= JS Callable Methods =================

    def get_initial_state(self):
        ports = get_available_midi_ports()
        self._audio_devices = get_low_latency_output_devices()
        self._all_devices = get_all_output_devices()

        audio_names = [name for _, name in self._audio_devices]
        all_names = [name for _, name in self._all_devices]

        # Determine default devices
        saved_audio = self._config.get("last_audio_device")
        current_audio = saved_audio if saved_audio in audio_names else (audio_names[0] if audio_names else "")
        if current_audio:
            self.set_audio_device(current_audio)

        saved_vmic = self._config.get("last_virtual_mic_device")
        cable_matches = [n for n in all_names if "cable" in n.lower() or "virtual" in n.lower()]
        current_vmic = saved_vmic if saved_vmic in all_names else (cable_matches[0] if cable_matches else (all_names[0] if all_names else ""))
        if current_vmic:
            self.set_vmic_device(current_vmic)

        saved_port = self._config.get("last_midi_port")
        current_port = saved_port if saved_port in ports else (ports[0] if ports else "")

        # Auto-connect if enabled
        if self._config.get("auto_connect", True) and current_port:
            self._engine.start(current_port)

        return {
            "midi_ports": ports,
            "current_midi_port": current_port,
            "is_connected": self._engine.is_running,
            "ws_server_url": f"ws://{self._ws_broadcaster.host}:{self._ws_broadcaster.port}",
            "ws_clients_count": len(self._ws_broadcaster.clients),
            "audio_devices": audio_names,
            "current_audio_dev": current_audio,
            "all_audio_devices": all_names,
            "current_vmic_dev": current_vmic,
            "current_soundbank": self._config.get("soundbank", "salamander"),
            "piano_sound_enabled": self._config.get("piano_sound_enabled", True),
            "piano_volume": self._config.get("piano_volume", 0.85),
            "virtual_mic_enabled": self._config.get("virtual_mic_enabled", False),
            "virtual_mic_volume": self._config.get("virtual_mic_volume", 0.85),
            "keystrokes_enabled": self._config.get("keystrokes_enabled", True),
            "transpose": self._config.get("transpose", 0),
            "velocity_curve": self._config.get("velocity_curve", "linear"),
            "auto_connect": self._config.get("auto_connect", True),
            "logging_enabled": self._config.get("logging_enabled", True),
            "keymap": {int(n): k for n, k in self._keymap_mgr.mapping.items()}
        }

    def set_soundbank(self, bank_name: str) -> bool:
        success = self._piano_engine.set_soundbank(bank_name)
        if success:
            self._config["soundbank"] = bank_name
            self._save_config()
            self._on_log(f"Grand Piano Soundbank switched to: {bank_name.upper()}")
            return True
        else:
            self._on_log(f"Soundbank '{bank_name}' samples not found. Run 'python download_samples.py --preset {bank_name}' first.")
            return False

    def set_velocity_curve(self, curve_name: str):
        self._engine.velocity_curve = curve_name
        self._file_player.velocity_curve = curve_name
        self._config["velocity_curve"] = curve_name
        self._save_config()
        self._on_log(f"Velocity Response Curve switched to: {curve_name.upper()}")

    def refresh_midi_ports(self):
        ports = get_available_midi_ports()
        self._on_log(f"Found {len(ports)} MIDI device(s): {', '.join(ports) if ports else 'None'}")
        return ports

    def toggle_midi_connection(self, port_name: str):
        if self._engine.is_running:
            self._engine.stop()
            self._on_log("MIDI Engine Disconnected.")
            return False
        else:
            if port_name and port_name != "No Devices Found":
                success = self._engine.start(port_name)
                if success:
                    self._config["last_midi_port"] = port_name
                    self._save_config()
                    self._on_log(f"Connected to MIDI device: {port_name}")
                    return True
            self._on_log("Select a valid MIDI device port to connect.")
            return False

    def toggle_piano_sound(self, enabled: bool):
        self._piano_engine.set_enabled(enabled)
        self._config["piano_sound_enabled"] = enabled
        self._save_config()
        self._on_log(f"Direct Grand Piano Output: {'ENABLED' if enabled else 'MUTED'}")

    def set_audio_device(self, chosen_name: str):
        for dev_id, name in self._audio_devices:
            if name == chosen_name:
                self._piano_engine.set_device(dev_id)
                self._config["last_audio_device"] = chosen_name
                self._save_config()
                self._on_log(f"Active WASAPI monitoring: {chosen_name}")
                break

    def set_piano_volume(self, volume: float):
        self._piano_engine.set_volume(volume)
        self._config["piano_volume"] = volume
        self._save_config()

    def toggle_virtual_mic(self, enabled: bool):
        self._piano_engine.set_virtual_mic_enabled(enabled)
        self._config["virtual_mic_enabled"] = enabled
        self._save_config()
        self._on_log(f"Virtual Mic Broadcast: {'ENABLED' if enabled else 'MUTED'}")

    def set_vmic_device(self, chosen_name: str):
        for dev_id, name in self._all_devices:
            if name == chosen_name:
                self._piano_engine.set_virtual_mic_device(dev_id)
                self._config["last_virtual_mic_device"] = chosen_name
                self._save_config()
                self._on_log(f"Active Virtual Mic target: {chosen_name}")
                break

    def set_vmic_volume(self, volume: float):
        self._piano_engine.set_virtual_mic_volume(volume)
        self._config["virtual_mic_volume"] = volume
        self._save_config()

    def toggle_keystrokes(self, enabled: bool):
        self._simulator.set_enabled(enabled)
        self._config["keystrokes_enabled"] = enabled
        self._save_config()
        self._on_log(f"Roblox Keyboard Mapping: {'ENABLED' if enabled else 'MUTED'}")

    def set_transpose(self, semitones: int):
        self._engine.transpose = semitones
        self._file_player.transpose = semitones
        self._config["transpose"] = semitones
        self._save_config()
        sign = "+" if semitones > 0 else ""
        self._on_log(f"Pitch Transposition adjusted to {sign}{semitones} semitones.")

    def save_setting(self, key: str, value):
        self._config[key] = value
        self._save_config()

    def open_midi_file(self):
        if not self._window:
            return
        file_types = ('MIDI Files (*.mid;*.midi)', 'All files (*.*)')
        # Support FileDialog.OPEN enum while remaining backwards compatible
        open_dialog_mode = getattr(webview, 'OPEN_DIALOG', 10)
        try:
            from webview import FileDialog
            open_dialog_mode = FileDialog.OPEN
        except Exception:
            pass
        result = self._window.create_file_dialog(open_dialog_mode, allow_multiple=False, file_types=file_types)
        if result and len(result) > 0:
            file_path = result[0]
            success = self._file_player.load_file(file_path)
            if success:
                fname = os.path.basename(file_path)
                total_str = MidiFilePlayer.format_time(self._file_player.total_duration)
                fname_js = json.dumps(fname)
                total_js = json.dumps(total_str)
                self._safe_eval_js(f"window.py_onFileLoaded && window.py_onFileLoaded({fname_js}, {total_js})")
                self._on_log(f"Loaded MIDI file: {fname} ({total_str})")

    def play_midi_file(self):
        self._file_player.play()

    def pause_midi_file(self):
        self._file_player.pause()

    def stop_midi_file(self):
        self._file_player.stop()
        self._safe_eval_js("window.py_onProgress && window.py_onProgress(0, '00:00', '00:00')")

    def get_sheet_text(self) -> str:
        sheet_text = self._file_player.generate_sheet_text(transpose=self._engine.transpose)
        if not sheet_text:
            self._on_log("Please open a MIDI file first to generate sheet notation.")
            return ""
        return sheet_text

    # ================= Callbacks to Frontend JS =================

    def _safe_eval_js(self, script: str):
        if not self._window:
            return
        try:
            self._window.evaluate_js(script)
        except Exception:
            pass

    def _on_midi_note_on(self, note: int, velocity: int, mapped_key: Optional[str]):
        effective = note + self._engine.transpose
        self._safe_eval_js(f"window.py_onNoteOn && window.py_onNoteOn({effective})")
        # Broadcast to connected Web apps (PianoWeb)
        if self._ws_broadcaster:
            self._ws_broadcaster.note_on(effective, velocity)

    def _on_midi_note_off(self, note: int, mapped_key: Optional[str]):
        effective = note + self._engine.transpose
        self._safe_eval_js(f"window.py_onNoteOff && window.py_onNoteOff({effective})")
        # Broadcast to connected Web apps (PianoWeb)
        if self._ws_broadcaster:
            self._ws_broadcaster.note_off(effective)

    def _on_midi_sustain(self, value: int):
        # Broadcast sustain to connected Web apps (PianoWeb)
        if self._ws_broadcaster:
            self._ws_broadcaster.sustain(value)

    def _on_ws_clients_changed(self, count: int):
        self._safe_eval_js(f"window.py_onWsClientsChanged && window.py_onWsClientsChanged({count})")

    def _on_log(self, text: str):
        safe_text = json.dumps(text)
        self._safe_eval_js(f"window.py_onLog && window.py_onLog({safe_text})")

    def _on_toggle_state_changed(self, enabled: bool):
        self._safe_eval_js(f"window.py_onToggleKeystrokes && window.py_onToggleKeystrokes({str(enabled).lower()})")
        self._config["keystrokes_enabled"] = enabled
        self._save_config()

    def _on_player_progress(self, elapsed: float, total: float):
        if total > 0:
            frac = min(1.0, elapsed / total)
            elapsed_str = MidiFilePlayer.format_time(elapsed)
            total_str = MidiFilePlayer.format_time(total)
            self._safe_eval_js(f"window.py_onProgress && window.py_onProgress({frac}, '{elapsed_str}', '{total_str}')")

    def _on_player_finished(self):
        total_str = MidiFilePlayer.format_time(self._file_player.total_duration)
        self._safe_eval_js(f"window.py_onProgress && window.py_onProgress(0, '00:00', '{total_str}')")

    def cleanup(self):
        self._save_config()
        self._file_player.stop()
        self._engine.stop()
        if self._ws_broadcaster:
            self._ws_broadcaster.stop()
        if self._piano_engine:
            self._piano_engine.close()
