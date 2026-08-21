import ctypes
from ctypes import wintypes
import time
import gc
from typing import List, Callable, Optional, Dict
from pynput import keyboard as pynput_keyboard

from keymap_config import KeymapManager, midi_note_to_name
from keyboard_simulator import KeyboardSimulator
from salamander_engine import SalamanderGrandPianoEngine

winmm = getattr(ctypes.windll, 'winmm', None)

CALLBACK_FUNCTION = 0x00030000
MIM_DATA = 0x3C3
MIM_OPEN = 0x3C1
MIM_CLOSE = 0x3C2

HMIDIIN = wintypes.HANDLE
DWORD_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else wintypes.DWORD

class MIDIINCAPSW(ctypes.Structure):
    _fields_ = [
        ('wMid', wintypes.WORD),
        ('wPid', wintypes.WORD),
        ('vDriverVersion', wintypes.DWORD),
        ('szPname', wintypes.WCHAR * 32),
        ('dwSupport', wintypes.DWORD),
    ]

MIDIINPROC = ctypes.WINFUNCTYPE(None, HMIDIIN, wintypes.UINT, DWORD_PTR, DWORD_PTR, DWORD_PTR)


def get_available_midi_ports() -> List[str]:
    if not winmm:
        return []
    num_devs = winmm.midiInGetNumDevs()
    devices = []
    caps = MIDIINCAPSW()
    for i in range(num_devs):
        if winmm.midiInGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
            devices.append(caps.szPname)
    return devices


class MidiEngine:
    '''Ultra-low latency MIDI engine connecting WinMM C interrupts, keystrokes, and Salamander Grand Piano.'''

    def __init__(self, keymap_mgr: KeymapManager, simulator: KeyboardSimulator, piano_engine: Optional[SalamanderGrandPianoEngine] = None):
        self.keymap_mgr = keymap_mgr
        self.simulator = simulator
        self.piano_engine = piano_engine

        self.selected_port_name: Optional[str] = None
        self.h_midi_in: Optional[HMIDIIN] = None
        self.is_running: bool = False

        self.transpose: int = 0
        self.min_velocity: int = 1

        self.on_note_on_cb: Optional[Callable[[int, int, Optional[str]], None]] = None
        self.on_note_off_cb: Optional[Callable[[int, Optional[str]], None]] = None
        self.on_log_cb: Optional[Callable[[str], None]] = None
        self.on_toggle_state_cb: Optional[Callable[[bool], None]] = None

        self._c_callback = MIDIINPROC(self._midi_in_proc)

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
                    status_str = 'ENABLED' if new_state else 'MUTED'
                    self._log(f'[HOTKEY F8] Mapper status changed to: {status_str}')
                    if self.on_toggle_state_cb:
                        self.on_toggle_state_cb(new_state)
            except Exception:
                pass

        self.hotkey_listener = pynput_keyboard.Listener(on_press=on_press)
        self.hotkey_listener.daemon = True
        self.hotkey_listener.start()

    def start(self, port_name: str) -> bool:
        self.stop()
        if not winmm:
            self._log('Error: winmm.dll is not available on this platform.')
            return False

        ports = get_available_midi_ports()
        device_id = -1
        for i, name in enumerate(ports):
            if name == port_name:
                device_id = i
                break

        if device_id == -1 and ports:
            device_id = 0
            port_name = ports[0]

        if device_id == -1:
            self._log('No valid MIDI input port found.')
            return False

        try:
            gc.collect()
            gc.disable()

            h_in = HMIDIIN()
            res = winmm.midiInOpen(
                ctypes.byref(h_in),
                device_id,
                self._c_callback,
                0,
                CALLBACK_FUNCTION
            )
            if res != 0:
                gc.enable()
                self._log(f'Failed to open MIDI port (Error code {res})')
                return False

            winmm.midiInStart(h_in)
            self.h_midi_in = h_in
            self.selected_port_name = port_name
            self.is_running = True
            self._log(f'Connected (WinMM Direct C-Interrupt <0.1ms): {port_name}')
            return True
        except Exception as e:
            gc.enable()
            self._log(f'MIDI start error: {e}')
            return False

    def stop(self):
        self.is_running = False
        if self.h_midi_in and winmm:
            try:
                winmm.midiInStop(self.h_midi_in)
                winmm.midiInReset(self.h_midi_in)
                winmm.midiInClose(self.h_midi_in)
            except Exception:
                pass
            self.h_midi_in = None
        gc.enable()
        self.simulator.release_all()
        if self.piano_engine:
            self.piano_engine.stop_all()
        if self.selected_port_name:
            self._log(f'Disconnected from {self.selected_port_name}')
            self.selected_port_name = None

    def _midi_in_proc(self, hMidiIn, wMsg, dwInstance, dwParam1, dwParam2):
        if wMsg != MIM_DATA:
            return

        status = dwParam1 & 0xFF
        note = (dwParam1 >> 8) & 0xFF
        velocity = (dwParam1 >> 16) & 0xFF
        msg_type = status & 0xF0

        if msg_type == 0x90 and velocity >= self.min_velocity:
            # 1. Trigger authentic Yamaha C5 sound instantly in RAM (<0.2ms)
            if self.piano_engine and self.piano_engine.enabled:
                self.piano_engine.note_on(note + self.transpose, velocity)

            # 2. Trigger Roblox keystroke simulation (<0.1ms)
            mapped_key = self.keymap_mgr.get_key_for_note(note, transpose=self.transpose)
            if mapped_key:
                self.simulator.press_key(mapped_key)

            # 3. Asynchronous UI Visualizer update
            if self.on_note_on_cb:
                self.on_note_on_cb(note, velocity, mapped_key)

        elif msg_type == 0x80 or (msg_type == 0x90 and velocity < self.min_velocity):
            if self.piano_engine and self.piano_engine.enabled:
                self.piano_engine.note_off(note + self.transpose)

            mapped_key = self.keymap_mgr.get_key_for_note(note, transpose=self.transpose)
            if mapped_key:
                self.simulator.release_key(mapped_key)

            if self.on_note_off_cb:
                self.on_note_off_cb(note, mapped_key)
