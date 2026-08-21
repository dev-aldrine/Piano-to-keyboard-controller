import os
import glob
import threading
import numpy as np
import sounddevice as sd
import soundfile as sf
from typing import Dict, Optional, Tuple, List

def get_all_output_devices() -> List[Tuple[int, str]]:
    '''Returns all audio output devices.'''
    try:
        apis = sd.query_hostapis()
        devices = []
        for i, d in enumerate(sd.query_devices()):
            if d['max_output_channels'] > 0:
                api_name = apis[d['hostapi']]['name']
                d_name = d['name']
                devices.append((i, f'{d_name} [{api_name}]'))
        return devices
    except Exception:
        return []

def get_low_latency_output_devices() -> List[Tuple[int, str]]:
    '''Returns audio output devices prioritized by lowest hardware latency (WASAPI / WDM-KS / ASIO).'''
    try:
        apis = sd.query_hostapis()
        devices = []
        for i, d in enumerate(sd.query_devices()):
            if d['max_output_channels'] > 0:
                api_name = apis[d['hostapi']]['name']
                d_name = d['name']
                if api_name in ['Windows WASAPI', 'ASIO', 'Windows WDM-KS']:
                    devices.append((i, f'{d_name} [{api_name}]'))
        
        if not devices:
            devices = get_all_output_devices()
        return devices
    except Exception:
        return []

class SalamanderGrandPianoEngine:
    '''Hardware-accelerated low-latency Yamaha C5 engine supporting Dual Audio Outputs (Headphones + Virtual Mic).'''

    def __init__(self, sample_dir: Optional[str] = None, sample_rate: int = 48000, device_id: Optional[int] = None):
        self.sr = sample_rate
        if sample_dir is None:
            sample_dir = os.path.join(os.path.dirname(__file__), 'samples', 'salamander')
        self.sample_dir = sample_dir

        self.samples: Dict[int, Dict[str, np.ndarray]] = {}
        self.active_voices: Dict[int, list] = {}
        self.lock = threading.Lock()
        self.volume: float = 0.85
        self.enabled: bool = True
        self.sustain_pedal: bool = False
        self.sustained_released_notes: set = set()

        # Primary stream (Monitoring / Headphones)
        self.stream: Optional[sd.OutputStream] = None
        if device_id is None:
            devs = get_low_latency_output_devices()
            self.device_id = devs[0][0] if devs else None
        else:
            self.device_id = device_id

        # Virtual Mic secondary stream
        self.virtual_mic_enabled: bool = False
        self.virtual_mic_device_id: Optional[int] = None
        self.virtual_mic_stream: Optional[sd.OutputStream] = None
        self.virtual_mic_volume: float = 0.85

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
        flac_files = glob.glob(os.path.join(self.sample_dir, '*.flac'))
        loaded_anchors = {}

        for fpath in flac_files:
            fname = os.path.basename(fpath).replace('.flac', '')
            vel = 'v14' if 'v14' in fname else 'v8'
            note_str = fname.replace(vel, '')
            try:
                midi_num = self._note_name_to_midi(note_str)
                data, orig_sr = sf.read(fpath, dtype='float32')
                if len(data.shape) == 1:
                    data = np.column_stack((data, data))
                if midi_num not in loaded_anchors:
                    loaded_anchors[midi_num] = {}
                loaded_anchors[midi_num][vel] = data
            except Exception:
                pass

        anchor_notes = sorted(loaded_anchors.keys())
        if not anchor_notes:
            return

        for note in range(21, 109):
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
                        orig_len = len(base_audio)
                        new_len = int(orig_len / pitch_ratio)
                        if new_len > 0:
                            indices = np.linspace(0, orig_len - 1, new_len)
                            left = np.interp(indices, np.arange(orig_len), base_audio[:, 0])
                            right = np.interp(indices, np.arange(orig_len), base_audio[:, 1])
                            self.samples[note][vel_layer] = np.column_stack((left, right)).astype(np.float32)
                        else:
                            self.samples[note][vel_layer] = base_audio

    def _start_audio_stream(self):
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass

        try:
            self.stream = sd.OutputStream(
                samplerate=self.sr,
                channels=2,
                dtype='float32',
                device=self.device_id,
                blocksize=64,
                latency='low',
                callback=self._audio_callback
            )
            self.stream.start()
        except Exception as e:
            try:
                self.stream = sd.OutputStream(
                    samplerate=44100,
                    channels=2,
                    dtype='float32',
                    blocksize=128,
                    callback=self._audio_callback
                )
                self.stream.start()
            except Exception:
                self.stream = None

    def _start_virtual_mic_stream(self):
        if self.virtual_mic_stream:
            try:
                self.virtual_mic_stream.stop()
                self.virtual_mic_stream.close()
            except Exception:
                pass
            self.virtual_mic_stream = None

        if not self.virtual_mic_enabled or self.virtual_mic_device_id is None:
            return

        try:
            self.virtual_mic_stream = sd.OutputStream(
                samplerate=self.sr,
                channels=2,
                dtype='float32',
                device=self.virtual_mic_device_id,
                blocksize=128,
                callback=self._virtual_mic_audio_callback
            )
            self.virtual_mic_stream.start()
        except Exception as e:
            print(f'Warning: Could not start virtual mic output stream: {e}')
            self.virtual_mic_stream = None

    def set_virtual_mic_device(self, device_id: Optional[int]):
        self.virtual_mic_device_id = device_id
        if self.virtual_mic_enabled:
            self._start_virtual_mic_stream()

    def set_virtual_mic_enabled(self, enabled: bool):
        self.virtual_mic_enabled = enabled
        if enabled:
            self._start_virtual_mic_stream()
        else:
            if self.virtual_mic_stream:
                try:
                    self.virtual_mic_stream.stop()
                    self.virtual_mic_stream.close()
                except Exception:
                    pass
                self.virtual_mic_stream = None

    def set_virtual_mic_volume(self, volume: float):
        self.virtual_mic_volume = max(0.0, min(volume, 1.0))

    def set_device(self, device_id: int):
        self.device_id = device_id
        self._start_audio_stream()

    def _render_audio_buffer(self, frames: int, advance_voices: bool = True) -> np.ndarray:
        out = np.zeros((frames, 2), dtype=np.float32)
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

                if not v['is_on']:
                    rel_frames = np.arange(v['rel_pos'], v['rel_pos'] + avail)
                    decay = np.exp(-rel_frames / 3500.0)
                    chunk = chunk * decay[:, np.newaxis]
                    if advance_voices:
                        v['rel_pos'] += avail
                    if decay[-1] < 0.005:
                        continue

                out[:avail] += chunk
                if advance_voices:
                    v['pos'] += avail

                if v['pos'] < total_len:
                    alive_voices.append(v)

            if alive_voices:
                if advance_voices:
                    self.active_voices[note] = alive_voices
            else:
                dead_notes.append(note)

        if advance_voices:
            for d in dead_notes:
                if d in self.active_voices:
                    del self.active_voices[d]

        return np.clip(out, -1.0, 1.0)

    def _audio_callback(self, outdata, frames, time_info, status):
        if not self.enabled:
            outdata.fill(0.0)
            return

        with self.lock:
            # Advance voices on primary output stream
            outdata[:] = self._render_audio_buffer(frames, advance_voices=True)

    def _virtual_mic_audio_callback(self, outdata, frames, time_info, status):
        if not self.enabled or not self.virtual_mic_enabled:
            outdata.fill(0.0)
            return

        with self.lock:
            outdata[:] = self._render_audio_buffer(frames, advance_voices=False) * self.virtual_mic_volume

    def set_sustain_pedal(self, is_pressed: bool):
        with self.lock:
            self.sustain_pedal = is_pressed
            if not is_pressed:
                for note in list(self.sustained_released_notes):
                    if note in self.active_voices:
                        for v in self.active_voices[note]:
                            v['is_on'] = False
                self.sustained_released_notes.clear()

    def note_on(self, note: int, velocity: int = 100):
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
            if note in self.sustained_released_notes:
                self.sustained_released_notes.discard(note)

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
        with self.lock:
            if self.sustain_pedal:
                self.sustained_released_notes.add(note)
            else:
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
            self.sustained_released_notes.clear()

    def close(self):
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        if self.virtual_mic_stream:
            try:
                self.virtual_mic_stream.stop()
                self.virtual_mic_stream.close()
            except Exception:
                pass
            self.virtual_mic_stream = None
