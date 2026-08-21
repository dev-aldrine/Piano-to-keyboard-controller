import sys
import io

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from keymap_config import KeymapManager, DEFAULT_ROBLOX_61KEY_MAP, midi_note_to_name
from keyboard_simulator import KeyboardSimulator, SYMBOL_TO_BASE

def test_keymap_completeness():
    print("--- Test 1: Keymap Completeness ---")
    km = KeymapManager()
    assert len(km.mapping) == 61, f"Expected 61 mapped notes, got {len(km.mapping)}"
    
    # Check range 36 to 96
    for note in range(36, 97):
        char_val = km.get_key_for_note(note)
        assert char_val is not None, f"Missing mapping for MIDI note {note} ({midi_note_to_name(note)})"
    print("✅ All 61 notes (C2 to C7 | MIDI 36 to 96) successfully mapped!")

def test_shift_resolution():
    print("--- Test 2: Shift Key Resolution ---")
    sim = KeyboardSimulator()
    
    # Check symbols
    char, needs_shift = sim._resolve_char('!')
    assert char == '1' and needs_shift is True, f"Expected ('1', True), got ({char}, {needs_shift})"
    
    char, needs_shift = sim._resolve_char('@')
    assert char == '2' and needs_shift is True, f"Expected ('2', True), got ({char}, {needs_shift})"
    
    # Check uppercase
    char, needs_shift = sim._resolve_char('Q')
    assert char == 'q' and needs_shift is True, f"Expected ('q', True), got ({char}, {needs_shift})"
    
    # Check lowercase
    char, needs_shift = sim._resolve_char('t')
    assert char == 't' and needs_shift is False, f"Expected ('t', False), got ({char}, {needs_shift})"
    
    print("✅ Key resolution & Shift detection passed successfully!")

def test_transpose_offset():
    print("--- Test 3: Transpose Calculations ---")
    km = KeymapManager()
    # Middle C (60) with transpose 0 -> 't'
    assert km.get_key_for_note(60, transpose=0) == 't'
    # C3 (48) + 12 transpose = 60 -> 't'
    assert km.get_key_for_note(48, transpose=12) == 't'
    # C5 (72) - 12 transpose = 60 -> 't'
    assert km.get_key_for_note(72, transpose=-12) == 't'
    print("✅ Transpose offset calculation passed successfully!")

if __name__ == "__main__":
    try:
        test_keymap_completeness()
        test_shift_resolution()
        test_transpose_offset()
        print("\n🎉 ALL UNIT VERIFICATION TESTS PASSED SUCCESSFULLY!")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
