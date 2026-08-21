import json
import os
from typing import Dict, Tuple, Optional

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

def midi_note_to_name(note: int) -> str:
    """Converts a MIDI note number (e.g. 60) to pitch name (e.g. 'C4')."""
    octave = (note // 12) - 1
    name = NOTE_NAMES[note % 12]
    return f"{name}{octave}"

# Standard Roblox Virtual Piano 61-Key Mapping (C2 to C7 | MIDI 36 to 96)
# Format: midi_note -> key_character
# Capital letters or symbols (like !, @, $, %, ^, *, () imply Shift is active.
DEFAULT_ROBLOX_61KEY_MAP: Dict[int, str] = {
    # Octave 2 (C2 - B2 | MIDI 36 - 47)
    36: '1',  # C2
    37: '!',  # C#2
    38: '2',  # D2
    39: '@',  # D#2
    40: '3',  # E2
    41: '4',  # F2
    42: '$',  # F#2
    43: '5',  # G2
    44: '%',  # G#2
    45: '6',  # A2
    46: '^',  # A#2
    47: '7',  # B2

    # Octave 3 (C3 - B3 | MIDI 48 - 59)
    48: '8',  # C3
    49: '*',  # C#3
    50: '9',  # D3
    51: '(',  # D#3
    52: '0',  # E3
    53: 'q',  # F3
    54: 'Q',  # F#3
    55: 'w',  # G3
    56: 'W',  # G#3
    57: 'e',  # A3
    58: 'E',  # A#3
    59: 'r',  # B3

    # Octave 4 (C4 - B4 | MIDI 60 - 71) - Middle C
    60: 't',  # C4
    61: 'T',  # C#4
    62: 'y',  # D4
    63: 'Y',  # D#4
    64: 'u',  # E4
    65: 'i',  # F4
    66: 'I',  # F#4
    67: 'o',  # G4
    68: 'O',  # G#4
    69: 'p',  # A4
    70: 'P',  # A#4
    71: 'a',  # B4

    # Octave 5 (C5 - B5 | MIDI 72 - 83)
    72: 's',  # C5
    73: 'S',  # C#5
    74: 'd',  # D5
    75: 'D',  # D#5
    76: 'f',  # E5
    77: 'g',  # F5
    78: 'G',  # F#5
    79: 'h',  # G5
    80: 'H',  # G#5
    81: 'j',  # A5
    82: 'J',  # A#5
    83: 'k',  # B5

    # Octave 6 (C6 - B6 | MIDI 84 - 95)
    84: 'l',  # C6
    85: 'L',  # C#6
    86: 'z',  # D6
    87: 'Z',  # D#6
    88: 'x',  # E6
    89: 'c',  # F6
    90: 'C',  # F#6
    91: 'v',  # G6
    92: 'V',  # G#6
    93: 'b',  # A6
    94: 'B',  # A#6
    95: 'n',  # B6

    # Octave 7 (C7 | MIDI 96)
    96: 'm'   # C7
}


class KeymapManager:
    """Manages active MIDI note-to-key mappings and custom user presets."""

    def __init__(self, mapping: Optional[Dict[int, str]] = None):
        self.mapping: Dict[int, str] = dict(mapping if mapping is not None else DEFAULT_ROBLOX_61KEY_MAP)

    def get_key_for_note(self, note: int, transpose: int = 0) -> Optional[str]:
        """Returns character mapped to a MIDI note accounting for transpose offset."""
        target_note = note + transpose
        return self.mapping.get(target_note)

    def set_mapping(self, note: int, char_str: str):
        self.mapping[note] = char_str

    def reset_to_default(self):
        self.mapping = dict(DEFAULT_ROBLOX_61KEY_MAP)

    def save_to_file(self, filepath: str):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({str(k): v for k, v in self.mapping.items()}, f, indent=2)

    def load_from_file(self, filepath: str):
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.mapping = {int(k): v for k, v in data.items()}
