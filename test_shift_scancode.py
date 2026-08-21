import ctypes

user32 = ctypes.windll.user32

VK_SHIFT = 0x10
VK_LSHIFT = 0xA0

scan_shift = user32.MapVirtualKeyW(VK_SHIFT, 0)
scan_lshift = user32.MapVirtualKeyW(VK_LSHIFT, 0)

print(f"MapVirtualKeyW(VK_SHIFT 0x10): {scan_shift}")
print(f"MapVirtualKeyW(VK_LSHIFT 0xA0): {scan_lshift}")
