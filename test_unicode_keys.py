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

def send_unicode_char(char: str):
    code = ord(char)
    # Key Down
    inp1 = INPUT()
    inp1.type = INPUT_KEYBOARD
    inp1.u.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)
    user32.SendInput(1, ctypes.byref(inp1), ctypes.sizeof(INPUT))
    
    time.sleep(0.01)
    
    # Key Up
    inp2 = INPUT()
    inp2.type = INPUT_KEYBOARD
    inp2.u.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
    user32.SendInput(1, ctypes.byref(inp2), ctypes.sizeof(INPUT))

if __name__ == "__main__":
    print("Testing Unicode input...")
    # Test sending 'j' and 'J'
    send_unicode_char('j')
    send_unicode_char('J')
    print("Done test!")
