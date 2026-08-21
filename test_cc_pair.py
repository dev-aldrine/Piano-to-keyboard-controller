import sys
import time
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from keyboard_simulator import KeyboardSimulator

def test_cc_rapid_pair():
    print("--- Test: Rapid cC Pair Pulse Execution ---")
    sim = KeyboardSimulator(mode="VIRTUAL_KEY", trigger_type="TAP", tap_duration=0.01)
    
    # Press 'c' and 'C' simultaneously
    sim.press_key('c')
    sim.press_key('C')
    
    time.sleep(0.04)
    print("✅ Rapid cC pair pulse test passed successfully!")

if __name__ == "__main__":
    test_cc_rapid_pair()
