import sys
import time
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from keyboard_simulator import KeyboardSimulator

def test_tap_mode():
    print("--- Test: TAP Mode Instant Pulse ---")
    sim = KeyboardSimulator(mode="UNICODE", trigger_type="TAP", tap_duration=0.01)
    
    # Press key in TAP mode
    sim.press_key('t')
    time.sleep(0.03)  # Wait for tap pulse to finish
    
    assert 't' not in sim.active_keys, "Key 't' should be automatically released after tap!"
    
    print("✅ TAP mode instant pulse test passed successfully!")

if __name__ == "__main__":
    test_tap_mode()
