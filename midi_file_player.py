import threading
import time
from typing import List, Callable, Optional, Tuple
import mido

from keymap_config import KeymapManager, midi_note_to_name
from keyboard_simulator import KeyboardSimulator
from salamander_engine import SalamanderGrandPianoEngine
from velocity_curve import transform_velocity


class MidiFilePlayer:
    '''Plays back .mid/.midi files with exact timing, Yamaha C5 audio playback, and Roblox keystrokes.'''

    def __init__(self, keymap_mgr: KeymapManager, simulator: KeyboardSimulator, piano_engine: Optional[SalamanderGrandPianoEngine] = None):
        self.keymap_mgr = keymap_mgr
        self.simulator = simulator
        self.piano_engine = piano_engine

        self.current_filepath: Optional[str] = None
        self.midi_file: Optional[mido.MidiFile] = None
        self.total_duration: float = 0.0

        self.is_playing: bool = False
        self.is_paused: bool = False
        self.stop_requested: bool = False
        self.speed_multiplier: float = 1.0

        self.transpose: int = 0
        self.velocity_curve: str = "linear"
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
        self.stop()
        try:
            self.midi_file = mido.MidiFile(filepath)
            self.current_filepath = filepath
            self.total_duration = self.midi_file.length
            self._log(f'Loaded MIDI file: {filepath} (Duration: {self.format_time(self.total_duration)})')
            return True
        except Exception as e:
            self._log(f'Error loading MIDI file: {e}')
            self.midi_file = None
            self.current_filepath = None
            self.total_duration = 0.0
            return False

    @staticmethod
    def format_time(seconds: float) -> str:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f'{mins:02d}:{secs:02d}'

    def play(self):
        if not self.midi_file:
            self._log('No MIDI file loaded.')
            return

        if self.is_paused:
            self.is_paused = False
            self.is_playing = True
            self._log('Resumed playback.')
            return

        if self.is_playing:
            return

        self.is_playing = True
        self.is_paused = False
        self.stop_requested = False
        self.play_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self.play_thread.start()

    def pause(self):
        if self.is_playing and not self.is_paused:
            self.is_paused = True
            self.is_playing = False
            self.simulator.release_all()
            if self.piano_engine:
                self.piano_engine.stop_all()
            self._log('Paused playback.')

    def stop(self):
        self.stop_requested = True
        self.is_playing = False
        self.is_paused = False
        self.simulator.release_all()
        if self.piano_engine:
            self.piano_engine.stop_all()
        if self.play_thread and self.play_thread.is_alive():
            self.play_thread.join(timeout=0.2)
        self.play_thread = None

    def set_speed(self, speed: float):
        self.speed_multiplier = max(0.1, min(speed, 5.0))

    def _playback_loop(self):
        if not self.midi_file:
            return

        self._log('Started MIDI file playback...')
        elapsed_time = 0.0

        try:
            for msg in self.midi_file.play(meta_messages=True):
                if self.stop_requested:
                    break

                while self.is_paused and not self.stop_requested:
                    time.sleep(0.05)

                if self.stop_requested:
                    break

                if msg.time > 0:
                    delay = msg.time / self.speed_multiplier
                    time.sleep(delay)
                    elapsed_time += msg.time

                if self.on_progress_cb:
                    self.on_progress_cb(elapsed_time, self.total_duration)

                # Process MIDI note events
                if msg.type == 'note_on' and msg.velocity > 0:
                    note = msg.note
                    velocity = transform_velocity(msg.velocity, self.velocity_curve)

                    if self.piano_engine and self.piano_engine.enabled:
                        self.piano_engine.note_on(note + self.transpose, velocity)

                    mapped_key = self.keymap_mgr.get_key_for_note(note, transpose=self.transpose)
                    if mapped_key:
                        self.simulator.press_key(mapped_key)

                    if self.on_note_on_cb:
                        self.on_note_on_cb(note, velocity, mapped_key)

                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    note = msg.note

                    if self.piano_engine and self.piano_engine.enabled:
                        self.piano_engine.note_off(note + self.transpose)

                    mapped_key = self.keymap_mgr.get_key_for_note(note, transpose=self.transpose)
                    if mapped_key:
                        self.simulator.release_key(mapped_key)

                    if self.on_note_off_cb:
                        self.on_note_off_cb(note, mapped_key)

                elif msg.type == 'control_change' and msg.control == 64:
                    is_down = (msg.value >= 64)
                    if self.piano_engine:
                        self.piano_engine.set_sustain_pedal(is_down)
                    if is_down:
                        self.simulator.press_key(' ')
                    else:
                        self.simulator.release_key(' ')

        except Exception as e:
            self._log(f'Playback error: {e}')

        self.is_playing = False
        self.is_paused = False
        self.simulator.release_all()
        if self.piano_engine:
            self.piano_engine.stop_all()
        self._log('Finished MIDI file playback.')

        if self.on_playback_finished_cb:
            self.on_playback_finished_cb()

    def generate_sheet_text(self, transpose: int = 0) -> str:
        if not self.midi_file:
            return ''

        current_time = 0.0
        time_notes: List[Tuple[float, str]] = []

        for msg in self.midi_file:
            current_time += msg.time
            if msg.type == 'note_on' and msg.velocity > 0:
                mapped_char = self.keymap_mgr.get_key_for_note(msg.note, transpose=transpose)
                if mapped_char:
                    time_notes.append((current_time, mapped_char))

        if not time_notes:
            return 'No printable notes found in MIDI file.'

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

        result_words = []
        for group in grouped_chords:
            if len(group) == 1:
                result_words.append(group[0])
            else:
                chord_str = ''.join(group)
                result_words.append(f'[{chord_str}]')

        return ' '.join(result_words)
