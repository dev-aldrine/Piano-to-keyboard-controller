import ctypes
from ctypes import wintypes
import time
import threading
from typing import Set, Dict, Tuple
from pynput.keyboard import Controller as PynputController, Key

kernel32 = getattr(ctypes.windll, 'kernel32', None) if hasattr(ctypes, 'windll') else None
user32 = getattr(ctypes.windll, 'user32', None) if hasattr(ctypes, 'windll') else None

# Request 1ms OS Timer Granularity and High Process Priority from Windows Kernel
HIGH_PRIORITY_CLASS = 0x00000080
THREAD_PRIORITY_HIGHEST = 2

try:
    if ctypes.windll.winmm:
        ctypes.windll.winmm.timeBeginPeriod(1)
    if kernel32:
        proc = kernel32.GetCurrentProcess()
        kernel32.SetPriorityClass(proc, HIGH_PRIORITY_CLASS)
        thread = kernel32.GetCurrentThread()
        kernel32.SetThreadPriority(thread, THREAD_PRIORITY_HIGHEST)
except Exception:
    pass

ULONG_PTR = ctypes.c_ulong if ctypes.sizeof(ctypes.c_void_p) == 4 else ctypes.c_ulonglong

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

VK_LSHIFT = 0xA0
VK_SHIFT = 0x10

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", INPUT_UNION),
    ]

SYMBOL_TO_BASE: Dict[str, Tuple[str, bool]] = {
    '!': ('1', True),
    '@': ('2', True),
    '$': ('4', True),
    '%': ('5', True),
    '^': ('6', True),
    '*': ('8', True),
    '(': ('9', True),
}


class KeyboardSimulator:
    """Hyper-speed Windows keyboard simulator with pre-allocated memory buffers and real-time process priority."""

    def __init__(self, mode: str = "VIRTUAL_KEY", trigger_type: str = "HOLD", tap_duration: float = 0.010):
        self.mode = mode
        self.trigger_type = trigger_type
        self.tap_duration = tap_duration
        self.pynput_controller = PynputController()
        self.active_keys: Set[str] = set()
        self.shift_pressed: bool = False
        self.enabled: bool = True
        self._lock = threading.Lock()

        # Pre-allocated dynamic C-struct buffer array for atomic SendInput batches
        self._input_buf = (INPUT * 4)()
        for i in range(4):
            self._input_buf[i].type = INPUT_KEYBOARD

        # Pre-cache Virtual Key codes and Scan Codes
        self._vk_cache: Dict[str, int] = {}
        self._scan_cache: Dict[int, int] = {}
        self._precache_keys()

    def _precache_keys(self):
        if not user32:
            return
        base_chars = "abcdefghijklmnopqrstuvwxyz0123456789"
        for ch in base_chars:
            try:
                vk = user32.VkKeyScanW(ch) & 0xFF
                scan = user32.MapVirtualKeyW(vk, 0)
                self._vk_cache[ch] = vk
                self._scan_cache[vk] = scan
            except Exception:
                pass
        
        try:
            self._scan_cache[VK_LSHIFT] = user32.MapVirtualKeyW(VK_LSHIFT, 0)
        except Exception:
            pass

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        if not enabled:
            self.release_all()

    def set_mode(self, mode: str):
        self.release_all()
        self.mode = mode

    def set_trigger_type(self, trigger_type: str):
        self.release_all()
        self.trigger_type = trigger_type

    def _resolve_char(self, char_str: str) -> Tuple[str, bool]:
        if char_str in SYMBOL_TO_BASE:
            return SYMBOL_TO_BASE[char_str]
        elif char_str.isupper():
            return char_str.lower(), True
        return char_str, False

    def press_key(self, char_str: str):
        """Triggers key press event instantly."""
        if not self.enabled or not char_str:
            return

        if self.trigger_type == "TAP":
            # Fire tap in background without blocking caller
            threading.Thread(target=self._tap_pulse, args=(char_str,), daemon=True).start()
        else:
            self._do_press(char_str)

    def release_key(self, char_str: str):
        """Releases key if in HOLD mode."""
        if self.trigger_type == "HOLD":
            self._do_release(char_str)

    def _tap_pulse(self, char_str: str):
        """Performs a fast tap and release."""
        with self._lock:
            self._do_press(char_str)
        time.sleep(self.tap_duration)
        with self._lock:
            self._do_release(char_str)

    def _send_atomic_inputs(self, events: list):
        """Dispatches multiple keyboard events in a single atomic kernel call (0ms delay)."""
        if not user32 or not events:
            return
        n = len(events)
        buf = (INPUT * n)()
        for i, (vk, scan, flags) in enumerate(events):
            buf[i].type = INPUT_KEYBOARD
            buf[i].u.ki.wVk = vk
            buf[i].u.ki.wScan = scan
            buf[i].u.ki.dwFlags = flags
            buf[i].u.ki.time = 0
            buf[i].u.ki.dwExtraInfo = 0
        user32.SendInput(n, ctypes.byref(buf), ctypes.sizeof(INPUT))

    def _do_press(self, char_str: str):
        base_char, needs_shift = self._resolve_char(char_str)
        counterpart = base_char if char_str.isupper() or char_str in SYMBOL_TO_BASE else char_str.upper()

        try:
            if user32 and self.mode == "VIRTUAL_KEY":
                vk_code = self._vk_cache.get(base_char)
                if vk_code is None:
                    vk_code = user32.VkKeyScanW(base_char) & 0xFF
                scan_code = self._scan_cache.get(vk_code, 0)
                shift_scan = self._scan_cache.get(VK_LSHIFT, 0)

                events = []

                # If counterpart key is already held, release it first in the same batch
                if counterpart in self.active_keys:
                    counterpart_base, _ = self._resolve_char(counterpart)
                    cp_vk = self._vk_cache.get(counterpart_base, vk_code)
                    cp_scan = self._scan_cache.get(cp_vk, 0)
                    events.append((cp_vk, cp_scan, KEYEVENTF_KEYUP))

                # Handle Shift state transition atomically
                if needs_shift and not self.shift_pressed:
                    events.append((VK_LSHIFT, shift_scan, 0))
                    self.shift_pressed = True
                elif not needs_shift and self.shift_pressed:
                    events.append((VK_LSHIFT, shift_scan, KEYEVENTF_KEYUP))
                    self.shift_pressed = False

                # If key was already marked active, release it to trigger a new strike
                if char_str in self.active_keys:
                    events.append((vk_code, scan_code, KEYEVENTF_KEYUP))

                # Press key
                events.append((vk_code, scan_code, 0))
                self.active_keys.add(char_str)

                # Send all batched events atomically to the Windows kernel
                self._send_atomic_inputs(events)

            elif user32 and self.mode == "UNICODE":
                self._win32_unicode_event(char_str, is_press=True)
                self.active_keys.add(char_str)

            else:
                if needs_shift:
                    self.pynput_controller.press(Key.shift)
                self.pynput_controller.press(base_char)
                self.active_keys.add(char_str)

        except Exception:
            if needs_shift:
                self.pynput_controller.press(Key.shift)
            self.pynput_controller.press(base_char)
            self.active_keys.add(char_str)

    def _do_release(self, char_str: str):
        if not char_str or char_str not in self.active_keys:
            return

        base_char, needs_shift = self._resolve_char(char_str)

        try:
            if user32 and self.mode == "VIRTUAL_KEY":
                vk_code = self._vk_cache.get(base_char)
                if vk_code is None:
                    vk_code = user32.VkKeyScanW(base_char) & 0xFF
                scan_code = self._scan_cache.get(vk_code, 0)
                shift_scan = self._scan_cache.get(VK_LSHIFT, 0)

                events = []
                # Release key
                events.append((vk_code, scan_code, KEYEVENTF_KEYUP))
                self.active_keys.discard(char_str)

                # Check if other active keys still require Shift
                other_shift_needed = any(self._resolve_char(k)[1] for k in self.active_keys)
                if self.shift_pressed and not other_shift_needed:
                    events.append((VK_LSHIFT, shift_scan, KEYEVENTF_KEYUP))
                    self.shift_pressed = False

                self._send_atomic_inputs(events)

            elif user32 and self.mode == "UNICODE":
                self._win32_unicode_event(char_str, is_press=False)
                self.active_keys.discard(char_str)

            else:
                self.pynput_controller.release(base_char)
                self.active_keys.discard(char_str)

        except Exception:
            self.pynput_controller.release(base_char)
            self.active_keys.discard(char_str)

    def _win32_unicode_event(self, char_str: str, is_press: bool):
        if not user32 or not char_str:
            return
        flags = KEYEVENTF_UNICODE if is_press else (KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
        buf = INPUT()
        buf.type = INPUT_KEYBOARD
        buf.u.ki.wVk = 0
        buf.u.ki.wScan = ord(char_str[0])
        buf.u.ki.dwFlags = flags
        buf.u.ki.time = 0
        buf.u.ki.dwExtraInfo = 0
        user32.SendInput(1, ctypes.byref(buf), ctypes.sizeof(INPUT))

    def release_all(self):
        events = []
        shift_scan = self._scan_cache.get(VK_LSHIFT, 0)
        for char_str in list(self.active_keys):
            base_char, _ = self._resolve_char(char_str)
            vk_code = self._vk_cache.get(base_char, 0)
            scan_code = self._scan_cache.get(vk_code, 0)
            if vk_code:
                events.append((vk_code, scan_code, KEYEVENTF_KEYUP))
        self.active_keys.clear()

        if user32 and self.shift_pressed:
            events.append((VK_LSHIFT, shift_scan, KEYEVENTF_KEYUP))
            self.shift_pressed = False
        elif not user32:
            self.pynput_controller.release(Key.shift)

        if events:
            self._send_atomic_inputs(events)
