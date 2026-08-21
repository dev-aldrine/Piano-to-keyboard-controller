import threading
import time
from typing import List, Callable, Optional, Tuple
import mido

from keymap_config import KeymapManager, midi_note_to_name
from keyboard_simulator import KeyboardSimulator


class MidiFilePlayer:
    """Plays back .mid/.midi files with exact timing and converts notes into Roblox keyboard keystrokes."""

    def __init__(self, keymap_mgr: KeymapManager, simulator: KeyboardSimulator):
        self.keymap_mgr = keymap_mgr
        self.simulator = simulator

        self.current_filepath: Optional[str] = None
        self.midi_file: Optional[mido.MidiFile] = None
        self.total_duration: float = 0.0

        self.is_playing: bool = False
        self.is_paused: bool = False
        self.stop_requested: bool = False
        self.speed_multiplier: float = 1.0

        self.transpose: int = 0
        self.play_thread: Optional[threading.Thread] = None

        # Callbacks for UI updates
        self.on_note_on_cb: Optional[Callable[[int, int, Optional[str]], None]] = None
        self.on_note_off_cb: Optional[Callable[[int, Optional[str]], None]] = None
        self.on_progress_cb: Optional[Callable[[float, float], None]] = None
        self.on_playback_finished_cb: Optional[Callable[[], None]] = None
        self.on_log_cb: Optional[Callable[[str], None]] = None

    def _log(self, text: str):
        if self.on_log_cb:
            self.on_log_cb(text)

    def load_file(self, filepath: str) -> bool:
        """Loads a .mid/.midi file and calculates duration."""
        self.stop()
        try:
            self.midi_file = mido.MidiFile(filepath)
            self.current_filepath = filepath
            self.total_duration = self.midi_file.length
            self._log(f"Loaded MIDI file: '{filepath}' (Duration: {self.format_time(self.total_duration)})")
            return True
        except Exception as e:
            self._log(f"Error loading MIDI file: {e}")
            self.midi_file = None
            self.current_filepath = None
            self.total_duration = 0.0
            return False

    @staticmethod
    def format_time(seconds: float) -> str:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    def play(self):
        """Starts or resumes MIDI file playback."""
        if not self.midi_file:
            self._log("No MIDI file loaded.")
            return

        if self.is_paused:
            self.is_paused = False
            self.is_playing = True
            self._log("Resumed playback.")
            return

        if self.is_playing:
            return

        self.is_playing = True
        self.is_paused = False
        self.stop_requested = False
        self.play_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self.play_thread.start()

    def pause(self):
        """Pauses MIDI file playback."""
        if self.is_playing and not self.is_paused:
            self.is_paused = True
            self.is_playing = False
            self.simulator.release_all()
            self._log("Paused playback.")

    def stop(self):
        """Stops MIDI file playback and releases held keys."""
        self.stop_requested = True
        self.is_playing = False
        self.is_paused = False
        self.simulator.release_all()
        if self.play_thread and self.play_thread.is_alive():
            self.play_thread.join(timeout=0.2)
        self.play_thread = None

    def set_speed(self, speed: float):
        """Sets playback speed multiplier (e.g. 0.5x to 2.0x)."""
        self.speed_multiplier = max(0.1, min(speed, 5.0))

    def _playback_loop(self):
        """Background playback thread iterating through MIDI messages with high-precision timing."""
        if not self.midi_file:
            return

        self._log("Started MIDI file playback...")
        elapsed_time = 0.0

        try:
            for msg in self.midi_file.play(meta_messages=True):
                if self.stop_requested:
                    break

                # Handle pause loop
                while self.is_paused and not self.stop_requested:
                    time.sleep(0.05)

                if self.stop_requested:
                    break

                # Account for speed multiplier
                if msg.time > 0:
                    delay = msg.time / self.speed_multiplier
                    time.sleep(delay)
                    elapsed_time += msg.time

                if self.on_progress_cb:
                    self.on_progress_cb(elapsed_time, self.total_duration)

                # Process MIDI note events
                if msg.type == 'note_on' and msg.velocity > 0:
                    note = msg.note
                    velocity = msg.velocity
                    mapped_key = self.keymap_mgr.get_key_for_note(note, transpose=self.transpose)

                    if mapped_key:
                        self.simulator.press_key(mapped_key)

                    if self.on_note_on_cb:
                        self.on_note_on_cb(note, velocity, mapped_key)

                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    note = msg.note
                    mapped_key = self.keymap_mgr.get_key_for_note(note, transpose=self.transpose)

                    if mapped_key:
                        self.simulator.release_key(mapped_key)

                    if self.on_note_off_cb:
                        self.on_note_off_cb(note, mapped_key)

        except Exception as e:
            self._log(f"Playback error: {e}")

        self.is_playing = False
        self.is_paused = False
        self.simulator.release_all()
        self._log("Finished MIDI file playback.")

        if self.on_playback_finished_cb:
            self.on_playback_finished_cb()

    def generate_sheet_text(self, transpose: int = 0) -> str:
        """Converts the loaded MIDI file into text sheet notation (e.g. [tY] u i [op])."""
        if not self.midi_file:
            return ""

        sheet_tokens = []
        # Quantize events into time frames
        current_time = 0.0
        time_notes: List[Tuple[float, str]] = []

        for msg in self.midi_file:
            current_time += msg.time
            if msg.type == 'note_on' and msg.velocity > 0:
                mapped_char = self.keymap_mgr.get_key_for_note(msg.note, transpose=transpose)
                if mapped_char:
                    time_notes.append((current_time, mapped_char))

        # Group notes played within 0.05 seconds of each other into chords []
        if not time_notes:
            return "No printable notes found in MIDI file."

        grouped_chords: List[List[str]] = []
        current_group: List[str] = [time_notes[0][1]]
        last_t = time_notes[0][0]

        for t, char_str in time_notes[1:]:
            if t - last_t < 0.06:
                if char_str not in current_group:
                    current_group.append(char_str)
            else:
                grouped_chords.append(current_group)
                current_group = [char_str]
                last_t = t

        if current_group:
            grouped_chords.append(current_group)

        # Build sheet string
        result_words = []
        for group in grouped_chords:
            if len(group) == 1:
                result_words.append(group[0])
            else:
                result_words.append(f"[{''.join(group)}]")

        return " ".join(result_words)
