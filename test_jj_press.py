import ctypes
from ctypes import wintypes
import time

ULONG_PTR = ctypes.c_ulong if ctypes.sizeof(ctypes.c_void_p) == 4 else ctypes.c_ulonglong

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

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

user32 = ctypes.windll.user32

def win32_send_unicode(char: str, is_press: bool):
    flags = KEYEVENTF_UNICODE if is_press else (KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki = KEYBDINPUT(wVk=0, wScan=ord(char), dwFlags=flags, time=0, dwExtraInfo=0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

if __name__ == "__main__":
    print("Testing simultaneous j and J via Unicode mode...")
    win32_send_unicode('j', True)
    time.sleep(0.01)
    win32_send_unicode('J', True)
    time.sleep(0.1)
    win32_send_unicode('j', False)
    time.sleep(0.01)
    win32_send_unicode('J', False)
    print("Done!")
