import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from keyboard_simulator import KeyboardSimulator

def test_simultaneous_j_and_J():
    print("--- Test: Simultaneous j and J chord support ---")
    sim = KeyboardSimulator(mode="UNICODE")
    
    # Press 'j'
    sim.press_key('j')
    assert 'j' in sim.active_keys, "Expected 'j' in active_keys"
    
    # Press 'J' simultaneously
    sim.press_key('J')
    assert 'J' in sim.active_keys, "Expected 'J' in active_keys"
    assert 'j' in sim.active_keys, "Expected 'j' still in active_keys"
    
    print(f"Active keys count: {len(sim.active_keys)} -> {sim.active_keys}")
    
    # Release 'j'
    sim.release_key('j')
    assert 'j' not in sim.active_keys, "'j' should be released"
    assert 'J' in sim.active_keys, "'J' should still be active"
    
    # Release 'J'
    sim.release_key('J')
    assert len(sim.active_keys) == 0, "All keys should be released"
    
    print("✅ Simultaneous j and J chord test passed successfully!")

if __name__ == "__main__":
    test_simultaneous_j_and_J()
