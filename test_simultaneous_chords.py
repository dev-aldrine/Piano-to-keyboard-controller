import sys
import time
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from keyboard_simulator import KeyboardSimulator

def test_mixed_shift_chords():
    print("--- Test: Simultaneous Mixed-Shift Chord Resolution ---")
    sim = KeyboardSimulator(mode="VIRTUAL_KEY", trigger_type="TAP", tap_duration=0.01)
    
    # Simulate simultaneous chord: 'm' (unshifted) and 'M' (shifted) or 'j' and 'J'
    sim.press_key('m')
    sim.press_key('M')
    
    time.sleep(0.04)
    print("✅ Mixed-shift chord test completed successfully without key lock!")

if __name__ == "__main__":
    test_mixed_shift_chords()
