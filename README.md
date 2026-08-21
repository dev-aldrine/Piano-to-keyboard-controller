# 🎹 Roblox MIDI Keyboard Mapper & File Player

A high-performance desktop application that maps physical MIDI controllers and plays back `.mid` / `.midi` files directly into Roblox Virtual Piano keyboard inputs with exact musical timing.

---

## 🌟 Features

- **Live MIDI Controller Input**: Plug in any USB MIDI Keyboard or Digital Piano and play live in Roblox.
- **📁 MIDI File Player & Auto-Play**: Load any `.mid` or `.midi` song file and play it back with exact note timing, velocity, speed control (`0.5x` to `2.0x`), and real-time progress bar tracking!
- **📄 Export Roblox Piano Sheets (.txt)**: Automatically converts uploaded `.mid` files into text sheet music format (e.g. `[tY] u i [op]`) that you can copy to your clipboard with one click!
- **Standard 61-Key Roblox Mapping**: Pre-configured with the standard Virtual Piano (VP) 61-key layout (C2 to C7 | MIDI 36–96) used in Roblox piano games (*Virtual Piano*, *RoPiano*, *Auto Piano*, *Piano Visualizer*).
- **Interactive 61-Key Visualizer**: Real-time visual keyboard layout that highlights keys in bright cyan & neon pink as you play.
- **Micro-Stagger & Same-Key Pulse Engine**: Flawless handling for simultaneous white & black key chords (e.g. `[jJ]`, `[cC]`, `[mM]`) without key collision or ghosting.
- **Octave & Transpose Shift**: Shift notes up or down (-24 to +24 semitones) so any 25-key, 49-key, or 88-key controller can play in any octave range.
- **Global Toggle Hotkey (`F8`)**: Mute MIDI mapping instantly when you want to chat in Roblox.

---

## 🚀 How to Run

1. Open your terminal in this directory:
   ```bash
   python main.py
   ```

2. **To Play Live**:
   - Select your MIDI device from the **MIDI Input Device** dropdown and click **Connect**.

3. **To Play a `.mid` File**:
   - Click **📁 Load MIDI File...** and select your song.
   - Click **▶ Play** to start playback directly into Roblox!
   - Click **📄 Export Sheet (.txt)** to convert the MIDI song into Roblox text notation.
