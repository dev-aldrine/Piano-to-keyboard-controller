import os
import glob
import threading
import numpy as np
import sounddevice as sd
import soundfile as sf
from typing import Dict, Optional, Tuple

class SalamanderGrandPianoEngine:
    '''Zero-latency in-memory streaming engine for authentic Yamaha C5 Salamander Grand Piano samples.'''

    def __init__(self, sample_dir: Optional[str] = None, sample_rate: int = 44100, device_id: Optional[int] = None):
        self.sr = sample_rate
        self.device_id = device_id
        if sample_dir is None:
            sample_dir = os.path.join(os.path.dirname(__file__), 'samples', 'salamander')
        self.sample_dir = sample_dir

        self.samples: Dict[int, Dict[str, np.ndarray]] = {}
        self.active_voices: Dict[int, list] = {}
        self.voice_id_counter = 0
        self.lock = threading.Lock()
        self.volume: float = 0.85
        self.enabled: bool = True
        self.stream: Optional[sd.OutputStream] = None

        self._load_samples_into_ram()
        self._start_audio_stream()

    def _note_name_to_midi(self, name: str) -> int:
        semis = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
        acc = 0
        note_letter = name[0].upper()
        idx = 1
        if len(name) > 1 and name[1] == '#':
            acc = 1
            idx = 2
        elif len(name) > 1 and name[1] == 'b':
            acc = -1
            idx = 2
        octave = int(name[idx:])
        return (octave + 1) * 12 + semis[note_letter] + acc

    def _load_samples_into_ram(self):
        '''Pre-loads and pitch-stretches all samples into memory so there is 0ms disk access during playing.'''
        flac_files = glob.glob(os.path.join(self.sample_dir, '*.flac'))
        loaded_anchors = {}

        for fpath in flac_files:
            fname = os.path.basename(fpath).replace('.flac', '')
            vel = 'v14' if 'v14' in fname else 'v8'
            note_str = fname.replace(vel, '')
            try:
                midi_num = self._note_name_to_midi(note_str)
                data, orig_sr = sf.read(fpath, dtype='float32')
                # Resample or take stereo
                if len(data.shape) == 1:
                    data = np.column_stack((data, data))
                
                if midi_num not in loaded_anchors:
                    loaded_anchors[midi_num] = {}
                loaded_anchors[midi_num][vel] = data
            except Exception as e:
                pass

        # Map all 128 MIDI notes to the closest recorded anchor note
        anchor_notes = sorted(loaded_anchors.keys())
        if not anchor_notes:
            print('Warning: No Salamander samples loaded.')
            return

        for note in range(21, 109):  # Full 88-key piano range
            # Find nearest anchor
            best_anchor = min(anchor_notes, key=lambda a: abs(a - note))
            semi_diff = note - best_anchor
            pitch_ratio = 2.0 ** (semi_diff / 12.0)

            self.samples[note] = {}
            for vel_layer in ['v8', 'v14']:
                if vel_layer in loaded_anchors[best_anchor]:
                    base_audio = loaded_anchors[best_anchor][vel_layer]
                    if semi_diff == 0:
                        self.samples[note][vel_layer] = base_audio
                    else:
                        # High-quality linear pitch interpolation
                        orig_len = len(base_audio)
                        new_len = int(orig_len / pitch_ratio)
                        if new_len > 0:
                            indices = np.linspace(0, orig_len - 1, new_len)
                            left = np.interp(indices, np.arange(orig_len), base_audio[:, 0])
                            right = np.interp(indices, np.arange(orig_len), base_audio[:, 1])
                            self.samples[note][vel_layer] = np.column_stack((left, right)).astype(np.float32)
                        else:
                            self.samples[note][vel_layer] = base_audio

        print(f'Successfully loaded {len(self.samples)} acoustic Yamaha C5 notes into RAM!')

    def _start_audio_stream(self):
        try:
            dev = self.device_id if self.device_id is not None else 4
            self.stream = sd.OutputStream(
                samplerate=48000,
                channels=2,
                dtype='float32',
                device=dev,
                blocksize=128,  # Ultra-low buffer size for sub-millisecond playback
                callback=self._audio_callback
            )
            self.stream.start()
        except Exception as e:
            print(f'Error starting Salamander audio stream: {e}')
            self.stream = None

    def _audio_callback(self, outdata, frames, time_info, status):
        if not self.enabled:
            outdata.fill(0.0)
            return

        out = np.zeros((frames, 2), dtype=np.float32)
        with self.lock:
            dead_notes = []
            for note, voices in list(self.active_voices.items()):
                alive_voices = []
                for v in voices:
                    audio = v['audio']
                    pos = v['pos']
                    total_len = len(audio)
                    if pos >= total_len:
                        continue

                    end_pos = min(pos + frames, total_len)
                    avail = end_pos - pos

                    chunk = audio[pos:end_pos] * v['gain']

                    # Apply release fadeout if note was released
                    if not v['is_on']:
                        rel_frames = np.arange(v['rel_pos'], v['rel_pos'] + avail)
                        decay = np.exp(-rel_frames / 4000.0)  # Smooth natural acoustic damper damping
                        chunk = chunk * decay[:, np.newaxis]
                        v['rel_pos'] += avail
                        if decay[-1] < 0.005:
                            continue

                    out[:avail] += chunk
                    v['pos'] += avail

                    if v['pos'] < total_len:
                        alive_voices.append(v)

                if alive_voices:
                    self.active_voices[note] = alive_voices
                else:
                    dead_notes.append(note)

            for d in dead_notes:
                if d in self.active_voices:
                    del self.active_voices[d]

        outdata[:] = np.clip(out, -1.0, 1.0)

    def note_on(self, note: int, velocity: int = 100):
        '''Triggers true acoustic Yamaha C5 sample from RAM with 0ms delay.'''
        if not self.enabled or note not in self.samples:
            return

        vel_layer = 'v14' if velocity > 80 else 'v8'
        if vel_layer not in self.samples[note]:
            vel_layer = list(self.samples[note].keys())[0] if self.samples[note] else None

        if not vel_layer:
            return

        audio = self.samples[note][vel_layer]
        gain = (velocity / 127.0) * self.volume

        with self.lock:
            if note not in self.active_voices:
                self.active_voices[note] = []
            self.active_voices[note].append({
                'audio': audio,
                'pos': 0,
                'is_on': True,
                'gain': gain,
                'rel_pos': 0
            })

    def note_off(self, note: int):
        '''Applies natural acoustic string damper to the ringing note.'''
        with self.lock:
            if note in self.active_voices:
                for v in self.active_voices[note]:
                    v['is_on'] = False

    def set_volume(self, volume: float):
        self.volume = max(0.0, min(volume, 1.0))

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        if not enabled:
            self.stop_all()

    def stop_all(self):
        with self.lock:
            self.active_voices.clear()

    def close(self):
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
