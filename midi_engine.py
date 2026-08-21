import threading
import time
import gc
from typing import List, Callable, Optional
import mido
from pynput import keyboard as pynput_keyboard

from keymap_config import KeymapManager, midi_note_to_name
from keyboard_simulator import KeyboardSimulator


def get_available_midi_ports() -> List[str]:
    """Returns list of all available MIDI input port names."""
    try:
        return mido.get_input_names()
    except Exception as e:
        print(f"Error reading MIDI ports: {e}")
        return []


class MidiEngine:
    """Zero-latency MIDI input listener using native rtmidi C++ callbacks and GC tuning."""

    def __init__(self, keymap_mgr: KeymapManager, simulator: KeyboardSimulator):
        self.keymap_mgr = keymap_mgr
        self.simulator = simulator

        self.selected_port_name: Optional[str] = None
        self.in_port: Optional[mido.ports.BaseInput] = None
        self.is_running: bool = False

        self.transpose: int = 0
        self.min_velocity: int = 1

        # Callbacks for UI visualizer and log updates
        self.on_note_on_cb: Optional[Callable[[int, int, Optional[str]], None]] = None
        self.on_note_off_cb: Optional[Callable[[int, Optional[str]], None]] = None
        self.on_log_cb: Optional[Callable[[str], None]] = None
        self.on_toggle_state_cb: Optional[Callable[[bool], None]] = None

        # Global hotkey listener for F8 toggle
        self.hotkey_listener: Optional[pynput_keyboard.Listener] = None
        self._start_global_hotkey_listener()

    def _log(self, text: str):
        if self.on_log_cb:
            self.on_log_cb(text)

    def _start_global_hotkey_listener(self):
        def on_press(key):
            try:
                if key == pynput_keyboard.Key.f8:
                    new_state = not self.simulator.enabled
                    self.simulator.set_enabled(new_state)
                    status_str = "ENABLED" if new_state else "MUTED"
                    self._log(f"[HOTKEY F8] Mapper status changed to: {status_str}")
                    if self.on_toggle_state_cb:
                        self.on_toggle_state_cb(new_state)
            except Exception as e:
                pass

        self.hotkey_listener = pynput_keyboard.Listener(on_press=on_press)
        self.hotkey_listener.daemon = True
        self.hotkey_listener.start()

    def start(self, port_name: str) -> bool:
        """Starts listening on specified MIDI port with zero-latency C++ callback mode."""
        self.stop()

        if not port_name:
            self._log("No MIDI port selected.")
            return False

        try:
            # Disable GC during active performance to prevent random 2-10ms GC latency spikes
            gc.collect()
            gc.disable()

            # Native C++ callback mode for zero polling latency (<0.5ms)
            self.in_port = mido.open_input(port_name, callback=self._process_midi_message)
            self.selected_port_name = port_name
            self.is_running = True
            self._log(f"Connected to MIDI device (Zero-Latency Callback & GC Tuning): {port_name}")
            return True
        except Exception as e:
            gc.enable()
            self._log(f"Failed to open MIDI port '{port_name}': {e}")
            return False

    def stop(self):
        """Stops the MIDI listener and closes port."""
        self.is_running = False
        if self.in_port:
            try:
                self.in_port.close()
            except Exception:
                pass
            self.in_port = None
        gc.enable()
        self.simulator.release_all()
        if self.selected_port_name:
            self._log(f"Disconnected from {self.selected_port_name}")
            self.selected_port_name = None

    def _process_midi_message(self, msg: mido.Message):
        """Processes Note On / Note Off MIDI messages with top priority."""
        if msg.type == 'note_on' and msg.velocity >= self.min_velocity:
            note = msg.note
            velocity = msg.velocity
            mapped_key = self.keymap_mgr.get_key_for_note(note, transpose=self.transpose)

            # High priority: Simulate keystroke instantly
            if mapped_key:
                self.simulator.press_key(mapped_key)

            # Asynchronous UI notification
            if self.on_log_cb or self.on_note_on_cb:
                note_name = midi_note_to_name(note)
                if mapped_key:
                    self._log(f"NOTE ON: {note_name} (MIDI {note}) -> Roblox Key: '{mapped_key}' (Vel: {velocity})")
                else:
                    self._log(f"NOTE ON: {note_name} (MIDI {note}) -> Unmapped (Transpose: {self.transpose})")

                if self.on_note_on_cb:
                    self.on_note_on_cb(note, velocity, mapped_key)

        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity < self.min_velocity):
            note = msg.note
            mapped_key = self.keymap_mgr.get_key_for_note(note, transpose=self.transpose)

            if mapped_key:
                self.simulator.release_key(mapped_key)

            if self.on_note_off_cb:
                self.on_note_off_cb(note, mapped_key)
