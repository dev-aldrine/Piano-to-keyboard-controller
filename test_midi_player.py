import sys
import os
import time
import mido

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from keymap_config import KeymapManager
from keyboard_simulator import KeyboardSimulator
from midi_file_player import MidiFilePlayer

def create_sample_midi_file(filepath: str):
    """Creates a sample .mid file for unit testing."""
    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)

    # Add notes: C4 (60 -> 't') and E4 (64 -> 'u')
    track.append(mido.Message('note_on', note=60, velocity=64, time=0))
    track.append(mido.Message('note_on', note=64, velocity=64, time=0)) # chord [tu]
    track.append(mido.Message('note_off', note=60, velocity=0, time=480))
    track.append(mido.Message('note_off', note=64, velocity=0, time=0))
    
    track.append(mido.Message('note_on', note=72, velocity=64, time=240)) # 's'
    track.append(mido.Message('note_off', note=72, velocity=0, time=480))

    mid.save(filepath)

def test_midi_player():
    print("--- Test: MIDI File Player & Sheet Converter ---")
    test_filepath = "test_song.mid"
    create_sample_midi_file(test_filepath)

    km = KeymapManager()
    sim = KeyboardSimulator(mode="VIRTUAL_KEY")
    player = MidiFilePlayer(km, sim)

    success = player.load_file(test_filepath)
    assert success is True, "Failed to load MIDI file"
    assert player.total_duration > 0, "Total duration should be > 0"
    print(f"Loaded MIDI file successfully. Total duration: {player.total_duration:.2f}s")

    # Test sheet generation
    sheet_text = player.generate_sheet_text()
    print(f"Generated Roblox Sheet Notation: {sheet_text}")
    assert "[tu]" in sheet_text or "[ut]" in sheet_text, "Expected chord bracket [tu] in sheet text"

    # Cleanup
    if os.path.exists(test_filepath):
        os.remove(test_filepath)

    print("✅ MIDI File Player & Sheet Converter test passed successfully!")

if __name__ == "__main__":
    test_midi_player()
