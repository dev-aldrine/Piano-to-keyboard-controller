import os
import sys
import urllib.request
import io
import json
import soundfile as sf
import numpy as np

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), 'samples', 'salamander')
os.makedirs(SAMPLE_DIR, exist_ok=True)

# 61-Key standard piano notes mapped to Salamander recording notes
# Salamander records every minor 3rd (A, C, D#, F#) across all octaves
RECORDED_NOTES = [
    'C1', 'D#1', 'F#1', 'A1',
    'C2', 'D#2', 'F#2', 'A2',
    'C3', 'D#3', 'F#3', 'A3',
    'C4', 'D#4', 'F#4', 'A4',
    'C5', 'D#5', 'F#5', 'A5',
    'C6', 'D#6', 'F#6', 'A6',
    'C7', 'D#7', 'F#7', 'A7'
]

# Medium forte (v8) & Fortissimo (v14) velocity layers
VELOCITIES = ['v8', 'v14']

print(f'Downloading authentic Yamaha C5 Grand Piano samples into: {SAMPLE_DIR}')

base_url = 'https://raw.githubusercontent.com/sfzinstruments/SalamanderGrandPiano/master/Samples/'
total = len(RECORDED_NOTES) * len(VELOCITIES)
count = 0

for note in RECORDED_NOTES:
    for vel in VELOCITIES:
        filename = f'{note}{vel}.flac'
        filepath = os.path.join(SAMPLE_DIR, filename)
        if not os.path.exists(filepath):
            file_url = base_url + filename
            try:
                req = urllib.request.Request(file_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req) as resp:
                    data = resp.read()
                    with open(filepath, 'wb') as f:
                        f.write(data)
            except Exception as e:
                print(f'Error downloading {filename}: {e}')
        count += 1
        sys.stdout.write(f'\rDownloaded Yamaha C5 samples: {count}/{total} ({filename})')
        sys.stdout.flush()

print('\nYamaha C5 Grand Piano samples ready!')
