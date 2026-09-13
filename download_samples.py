import os
import sys
import urllib.request
import argparse

BASE_DIR = os.path.join(os.path.dirname(__file__), 'samples')

PRESETS = {
    'salamander': {
        'name': 'Yamaha C5 (Salamander Grand Piano)',
        'dir': os.path.join(BASE_DIR, 'salamander'),
        'base_url': 'https://raw.githubusercontent.com/sfzinstruments/SalamanderGrandPiano/master/Samples/',
        'files': [
            f'{note}{vel}.flac'
            for note in [
                'C1', 'D#1', 'F#1', 'A1',
                'C2', 'D#2', 'F#2', 'A2',
                'C3', 'D#3', 'F#3', 'A3',
                'C4', 'D#4', 'F#4', 'A4',
                'C5', 'D#5', 'F#5', 'A5',
                'C6', 'D#6', 'F#6', 'A6',
                'C7', 'D#7', 'F#7', 'A7'
            ]
            for vel in ['v8', 'v14']
        ]
    },
    'maestro': {
        'name': 'Mats Helgesson Maestro Concert Grand Piano (Steinway Model B)',
        'dir': os.path.join(BASE_DIR, 'maestro'),
        'base_url': 'https://raw.githubusercontent.com/sfzinstruments/MatsHelgesson.MaestroConcertGrandPiano/master/Samples/',
        # Download every minor 3rd (21, 24, 27, 30, ...) across medium (mf) & fortissimo (f) layers
        'files': [
            f'mcg_{layer}_{midi:03d}.flac'
            for midi in range(21, 109, 3) # Anchors every 3 semitones (MIDI 21 to 108)
            for layer in ['mf', 'f']
        ]
    },
    'headroom': {
        'name': 'Bengt Nilsson Headroom Piano (Intimate Close-Mic)',
        'dir': os.path.join(BASE_DIR, 'headroom'),
        'base_url': 'https://raw.githubusercontent.com/sfzinstruments/BengtNilsson.HeadroomPiano/master/Samples/',
        # Download close-mic level 2 (medium) and level 4 (forte) across minor 3rd anchors
        'files': [
            f'HEADROOM PIANO {level} CLOSE {midi}.flac'
            for midi in range(21, 109, 3)
            for level in ['LEVEL2', 'LEVEL4']
        ]
    },
    'alesis_grand_x': {
        'name': 'Alesis Grand X Piano',
        'dir': os.path.join(BASE_DIR, 'alesis_grand_x'),
        'base_url': 'https://raw.githubusercontent.com/Softy107/Alesis-Soundfonts/main/Samples/Alesis%20Grand%20X/',
        'files': [
            f'AGX {midi}.wav'
            for midi in range(21, 109, 3)
        ]
    },
    'alesis_bright': {
        'name': 'Alesis Bright Piano',
        'dir': os.path.join(BASE_DIR, 'alesis_bright'),
        'base_url': 'https://raw.githubusercontent.com/Softy107/Alesis-Soundfonts/main/Samples/Bright%20Piano/',
        'files': [
            'Bright 23.wav', 'Bright 29.wav', 'Bright 35.wav', 'Bright 41.wav', 'Bright 47.wav',
            'Bright 53.wav', 'Bright 59.wav', 'Bright 65.wav', 'Bright 71.wav', 'Bright 77.wav',
            'Bright 83.wav', 'Bright 89.wav', 'Bright 95.wav', 'Bright 101.wav', 'Bright 107.wav'
        ]
    },
    'alesis_ep': {
        'name': 'Alesis Electric Piano',
        'dir': os.path.join(BASE_DIR, 'alesis_ep'),
        'base_url': 'https://raw.githubusercontent.com/Softy107/Alesis-Soundfonts/main/Samples/Electric%20Piano/',
        'files': [
            'EP24.wav', 'EP30.wav', 'EP36.wav', 'EP42.wav', 'EP48.wav', 'EP54.wav',
            'EP60.wav', 'EP66.wav', 'EP72.wav', 'EP78.wav', 'EP84.wav', 'EP96.wav'
        ]
    },
    'alesis_harpsichord': {
        'name': 'Alesis Harpsichord',
        'dir': os.path.join(BASE_DIR, 'alesis_harpsichord'),
        'base_url': 'https://raw.githubusercontent.com/Softy107/Alesis-Soundfonts/main/Samples/Harpsichord/',
        'files': [
            '8bh - 24.wav', '8bh - 36.wav', '8bh - 48.wav', '8bh - 60.wav',
            '8bh - 72.wav', '8bh - 84.wav', '8bh - 96.wav', '8bh - 108.wav'
        ]
    }
}

def _download_file(args):
    filename, preset_dir, base_url = args
    filepath = os.path.join(preset_dir, filename)
    if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
        return True, filename
    
    file_url = base_url + urllib.parse.quote(filename)
    try:
        req = urllib.request.Request(file_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            with open(filepath, 'wb') as f:
                f.write(data)
        return True, filename
    except Exception as e:
        return False, f"{filename}: {e}"

def download_preset(preset_key):
    preset = PRESETS[preset_key]
    os.makedirs(preset['dir'], exist_ok=True)
    print(f"\n=======================================================")
    print(f" Downloading: {preset['name']}")
    print(f" Target folder: {preset['dir']}")
    print(f" Total samples: {len(preset['files'])}")
    print(f"=======================================================")

    total = len(preset['files'])
    tasks = [(fn, preset['dir'], preset['base_url']) for fn in preset['files']]
    
    from concurrent.futures import ThreadPoolExecutor, as_completed
    count = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_download_file, t): t[0] for t in tasks}
        for future in as_completed(futures):
            count += 1
            success, res = future.result()
            sys.stdout.write(f"\r[{preset_key.upper()}] Progress: {count}/{total} ({res[:35]})")
            sys.stdout.flush()

    print(f"\n[OK] {preset['name']} ready!")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Download Grand Piano Sample Banks for Keyboard-MIDI')
    parser.add_argument('--preset', choices=['salamander', 'maestro', 'headroom', 'all'], default='all',
                        help='Which sound sample preset to download (default: all)')
    args = parser.parse_args()

    if args.preset == 'all':
        for p in PRESETS:
            download_preset(p)
    else:
        download_preset(args.preset)

    print("\nAll selected sound presets are downloaded and ready to play!")
