import sys
import time
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from keyboard_simulator import KeyboardSimulator

def test_black_keys():
    print("--- Test: Black Key Virtual Key Shift Resolution ---")
    sim = KeyboardSimulator(mode="VIRTUAL_KEY")
    base, needs_shift = sim._resolve_char('T')
    print(f"DEBUG: 'T' resolved -> base: {base}, needs_shift: {needs_shift}")
    
    # Test black key 'T' (C#4)
    sim.press_key('T')
    print(f"DEBUG: shift_pressed: {sim.shift_pressed}, active_keys: {sim.active_keys}")
    assert sim.shift_pressed is True, "Shift should be active when pressing black key 'T'"
    assert 'T' in sim.active_keys
    sim.release_key('T')
    assert sim.shift_pressed is False, "Shift should be released after releasing 'T'"
    
    # Test black key symbol '!' (C#2)
    sim.press_key('!')
    assert sim.shift_pressed is True, "Shift should be active when pressing black key '!'"
    sim.release_key('!')
    assert sim.shift_pressed is False, "Shift should be released after releasing '!'"
    
    print("✅ Black key Shift state management test passed successfully!")

if __name__ == "__main__":
    test_black_keys()
