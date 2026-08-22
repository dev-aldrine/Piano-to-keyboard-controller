/**
 * HZWU • Neumorphic MIDI Studio - Frontend Client Logic
 * Interacts with Python backend via pywebview JS Bridge
 */

let currentTransposition = 0;
let keymapTable = {};

// 61-Key Virtual Piano Note Boundaries (C2 to C7 -> 36 to 96)
const START_NOTE = 36;
const END_NOTE = 96;
const BLACK_KEY_OFFSETS = [1, 3, 6, 8, 10]; // Semitone offsets for C#, D#, F#, G#, A#

document.addEventListener('DOMContentLoaded', () => {
  renderPianoKeyboard();
  // Wait for pywebview API to be ready
  window.addEventListener('pywebviewready', () => {
    initBackend();
  });
});

/**
 * Toggle Left-Hand Controls Sidebar
 */
function toggleSidebar() {
  const grid = document.getElementById('workspaceGrid');
  const btn = document.getElementById('sidebarToggleBtn');
  grid.classList.toggle('sidebar-collapsed');
  const isCollapsed = grid.classList.contains('sidebar-collapsed');
  if (btn) {
    btn.classList.toggle('active', isCollapsed);
  }
}

/**
 * Render 61 keys (36 white keys + 25 black keys)
 */
function renderPianoKeyboard() {
  const container = document.getElementById('pianoKeyboard');
  container.innerHTML = '';

  const whiteNotes = [];
  for (let n = START_NOTE; n <= END_NOTE; n++) {
    if (!BLACK_KEY_OFFSETS.includes(n % 12)) {
      whiteNotes.push(n);
    }
  }

  const whiteKeyPercent = 100 / whiteNotes.length;
  const noteToLeftPercent = {};

  // 1. Render White Keys
  whiteNotes.forEach((note, index) => {
    const keyEl = document.createElement('div');
    keyEl.className = 'piano-key white';
    keyEl.id = `key-${note}`;
    keyEl.dataset.note = note;

    const charSpan = document.createElement('span');
    charSpan.className = 'key-char';
    charSpan.id = `char-${note}`;
    charSpan.innerText = keymapTable[note] || '';
    keyEl.appendChild(charSpan);

    container.appendChild(keyEl);
    noteToLeftPercent[note] = index * whiteKeyPercent;
  });

  // 2. Render Black Keys
  for (let note = START_NOTE; note <= END_NOTE; note++) {
    if (BLACK_KEY_OFFSETS.includes(note % 12)) {
      const prevWhiteNote = note - 1;
      if (noteToLeftPercent[prevWhiteNote] !== undefined) {
        const leftPos = noteToLeftPercent[prevWhiteNote] + whiteKeyPercent - 1.1;

        const blackEl = document.createElement('div');
        blackEl.className = 'piano-key black';
        blackEl.id = `key-${note}`;
        blackEl.dataset.note = note;
        blackEl.style.left = `${leftPos}%`;

        const charSpan = document.createElement('span');
        charSpan.className = 'key-char';
        charSpan.id = `char-${note}`;
        charSpan.innerText = keymapTable[note] || '';
        blackEl.appendChild(charSpan);

        container.appendChild(blackEl);
      }
    }
  }
}

/**
 * Initialize state from Python API
 */
async function initBackend() {
  try {
    const initData = await window.pywebview.api.get_initial_state();
    if (initData) {
      keymapTable = initData.keymap || {};
      updateKeymapDisplay();

      // Populate MIDI ports
      populateSelect('midiPortSelect', initData.midi_ports, initData.current_midi_port);

      // Populate Audio devices
      populateSelect('audioDeviceSelect', initData.audio_devices, initData.current_audio_dev);

      // Populate Virtual Mic devices
      populateSelect('vmicDeviceSelect', initData.all_audio_devices, initData.current_vmic_dev);

      // Set switches & sliders
      document.getElementById('pianoSoundSwitch').checked = initData.piano_sound_enabled;
      document.getElementById('pianoVolSlider').value = Math.round(initData.piano_volume * 100);
      document.getElementById('pianoVolVal').innerText = `${Math.round(initData.piano_volume * 100)}%`;

      document.getElementById('vmicSwitch').checked = initData.virtual_mic_enabled;
      document.getElementById('vmicVolSlider').value = Math.round(initData.virtual_mic_volume * 100);
      document.getElementById('vmicVolVal').innerText = `${Math.round(initData.virtual_mic_volume * 100)}%`;

      document.getElementById('keystrokeSwitch').checked = initData.keystrokes_enabled;
      document.getElementById('autoConnectCheck').checked = initData.auto_connect;
      document.getElementById('loggingCheck').checked = initData.logging_enabled;

      currentTransposition = initData.transpose || 0;
      document.getElementById('transposeSlider').value = currentTransposition;
      document.getElementById('transposeVal').innerText = `${currentTransposition > 0 ? '+' : ''}${currentTransposition} Semi`;

      // Set velocity curve
      const savedCurve = initData.velocity_curve || 'linear';
      document.getElementById('velocityCurveSelect').value = savedCurve;
      updateVelocityCurveDisplay(savedCurve);

      updateConnectionBadge(initData.is_connected);
    }
  } catch (err) {
    console.error('Failed to initialize state from Python:', err);
  }
}

/**
 * Draw interactive 2D graph of velocity transfer curve
 */
function drawVelocityCurveGraph(curveName) {
  const canvas = document.getElementById('curveCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;

  ctx.clearRect(0, 0, w, h);

  const pad = 12;
  const graphW = w - pad * 2;
  const graphH = h - pad * 2;

  // 1. Draw subtle grid lines
  ctx.strokeStyle = 'rgba(163, 177, 198, 0.4)';
  ctx.lineWidth = 1;
  ctx.setLineDash([3, 3]);

  // Diagonal reference guide (linear 1:1)
  ctx.beginPath();
  ctx.moveTo(pad, h - pad);
  ctx.lineTo(w - pad, pad);
  ctx.stroke();

  // Horizontal mid-line
  ctx.beginPath();
  ctx.moveTo(pad, pad + graphH / 2);
  ctx.lineTo(w - pad, pad + graphH / 2);
  ctx.stroke();
  ctx.setLineDash([]);

  // 2. Compute curve points
  const points = [];
  const steps = 60;
  for (let i = 0; i <= steps; i++) {
    const xNorm = i / steps;
    let yNorm = xNorm;

    switch (curveName) {
      case 'ease_in':
        yNorm = Math.pow(xNorm, 2);
        break;
      case 'ease_out':
        yNorm = Math.sqrt(xNorm);
        break;
      case 'ease_in_out':
        yNorm = xNorm < 0.5 ? 2 * xNorm * xNorm : 1 - Math.pow(-2 * xNorm + 2, 2) / 2;
        break;
      case 'exponential':
        yNorm = Math.pow(xNorm, 3);
        break;
      case 'logarithmic':
        yNorm = Math.pow(xNorm, 0.3333);
        break;
      case 'compressed':
        yNorm = 0.35 + (xNorm * 0.6);
        break;
      case 'linear':
      default:
        yNorm = xNorm;
        break;
    }

    const canvasX = pad + xNorm * graphW;
    const canvasY = (h - pad) - yNorm * graphH;
    points.push({ x: canvasX, y: canvasY });
  }

  // 3. Draw gradient fill beneath the curve
  const gradient = ctx.createLinearGradient(0, pad, 0, h - pad);
  gradient.addColorStop(0, 'rgba(108, 99, 255, 0.35)');
  gradient.addColorStop(1, 'rgba(108, 99, 255, 0.02)');

  ctx.beginPath();
  ctx.moveTo(pad, h - pad);
  points.forEach(pt => ctx.lineTo(pt.x, pt.y));
  ctx.lineTo(w - pad, h - pad);
  ctx.closePath();
  ctx.fillStyle = gradient;
  ctx.fill();

  // 4. Draw stroke curve
  ctx.beginPath();
  ctx.strokeStyle = '#6C63FF';
  ctx.lineWidth = 3;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  points.forEach((pt, i) => {
    if (i === 0) ctx.moveTo(pt.x, pt.y);
    else ctx.lineTo(pt.x, pt.y);
  });
  ctx.stroke();

  // 5. Draw endpoint markers
  [points[0], points[points.length - 1]].forEach(pt => {
    ctx.beginPath();
    ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
    ctx.fillStyle = '#6C63FF';
    ctx.fill();
    ctx.strokeStyle = '#FFFFFF';
    ctx.lineWidth = 1.5;
    ctx.stroke();
  });
}

function updateVelocityCurveDisplay(curveName) {
  const badge = document.getElementById('velocityCurveTag');
  const labels = {
    'linear': 'Linear',
    'ease_in': 'Ease-In',
    'ease_out': 'Ease-Out',
    'ease_in_out': 'Ease-In-Out',
    'exponential': 'Exponential',
    'logarithmic': 'Logarithmic',
    'compressed': 'Compressed'
  };
  if (badge) badge.innerText = labels[curveName] || 'Linear';
  drawVelocityCurveGraph(curveName);
}

function onVelocityCurveChanged(curveName) {
  updateVelocityCurveDisplay(curveName);
  window.pywebview.api.set_velocity_curve(curveName);
}

function populateSelect(id, items, selectedValue) {
  const select = document.getElementById(id);
  select.innerHTML = '';
  if (!items || items.length === 0) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.innerText = 'No Devices Found';
    select.appendChild(opt);
    return;
  }

  items.forEach(item => {
    const opt = document.createElement('option');
    opt.value = item;
    opt.innerText = item;
    if (item === selectedValue) {
      opt.selected = true;
    }
    select.appendChild(opt);
  });
}

function updateKeymapDisplay() {
  for (let note = START_NOTE; note <= END_NOTE; note++) {
    const charEl = document.getElementById(`char-${note}`);
    if (charEl) {
      const effectiveNote = note - currentTransposition;
      charEl.innerText = keymapTable[effectiveNote] || '';
    }
  }
}

/* ================= PyWebView Events Called From Python ================= */

window.py_onNoteOn = function(note) {
  const keyEl = document.getElementById(`key-${note}`);
  if (keyEl) {
    keyEl.classList.add('active');
  }
};

window.py_onNoteOff = function(note) {
  const keyEl = document.getElementById(`key-${note}`);
  if (keyEl) {
    keyEl.classList.remove('active');
  }
};

window.py_onLog = function(msg) {
  if (!document.getElementById('loggingCheck').checked) return;
  const consoleEl = document.getElementById('logConsole');
  const now = new Date();
  const timeStr = now.toTimeString().split(' ')[0];

  const entry = document.createElement('div');
  entry.className = 'log-entry';
  entry.innerHTML = `<span class="log-timestamp">[${timeStr}]</span><span class="log-msg">${escapeHtml(msg)}</span>`;
  consoleEl.appendChild(entry);
  consoleEl.parentElement.scrollTop = consoleEl.parentElement.scrollHeight;
};

window.py_onProgress = function(fraction, elapsedStr, totalStr) {
  document.getElementById('progressBar').style.width = `${Math.min(100, fraction * 100)}%`;
  document.getElementById('currentTime').innerText = elapsedStr;
  document.getElementById('totalTime').innerText = totalStr;
};

window.py_onConnectionChanged = function(isConnected) {
  updateConnectionBadge(isConnected);
};

window.py_onFileLoaded = function(fileName, totalTimeStr) {
  document.getElementById('loadedFileLabel').innerText = fileName || 'No file loaded';
  document.getElementById('totalTime').innerText = totalTimeStr || '00:00';
  document.getElementById('currentTime').innerText = '00:00';
  document.getElementById('progressBar').style.width = '0%';
};

window.py_onToggleKeystrokes = function(enabled) {
  document.getElementById('keystrokeSwitch').checked = enabled;
};

/* ================= User Actions (Calls to Python) ================= */

async function toggleConnection() {
  const isConnected = await window.pywebview.api.toggle_midi_connection(
    document.getElementById('midiPortSelect').value
  );
  updateConnectionBadge(isConnected);
}

function updateConnectionBadge(isConnected) {
  const badge = document.getElementById('statusBadge');
  const text = document.getElementById('statusText');
  const btn = document.getElementById('connectBtn');

  if (isConnected) {
    badge.className = 'status-pill connected';
    text.innerText = 'CONNECTED & LISTENING';
    btn.innerText = 'Disconnect';
    btn.className = 'neu-btn neu-btn-danger';
  } else {
    badge.className = 'status-pill disconnected';
    text.innerText = 'DISCONNECTED';
    btn.innerText = 'Connect';
    btn.className = 'neu-btn neu-btn-primary';
  }
}

async function refreshMidiPorts() {
  const ports = await window.pywebview.api.refresh_midi_ports();
  populateSelect('midiPortSelect', ports, document.getElementById('midiPortSelect').value);
}

function onMidiPortChanged() {
  window.pywebview.api.save_setting('last_midi_port', document.getElementById('midiPortSelect').value);
}

function togglePianoSound() {
  const enabled = document.getElementById('pianoSoundSwitch').checked;
  window.pywebview.api.toggle_piano_sound(enabled);
}

function onAudioDeviceChanged() {
  window.pywebview.api.set_audio_device(document.getElementById('audioDeviceSelect').value);
}

function onPianoVolChanged(val) {
  document.getElementById('pianoVolVal').innerText = `${val}%`;
  window.pywebview.api.set_piano_volume(val / 100);
}

function toggleVirtualMic() {
  const enabled = document.getElementById('vmicSwitch').checked;
  window.pywebview.api.toggle_virtual_mic(enabled);
}

function onVmicDeviceChanged() {
  window.pywebview.api.set_vmic_device(document.getElementById('vmicDeviceSelect').value);
}

function onVmicVolChanged(val) {
  document.getElementById('vmicVolVal').innerText = `${val}%`;
  window.pywebview.api.set_vmic_volume(val / 100);
}

function toggleKeystrokes() {
  const enabled = document.getElementById('keystrokeSwitch').checked;
  window.pywebview.api.toggle_keystrokes(enabled);
}

function onTransposeChanged(val) {
  const semitones = parseInt(val, 10);
  currentTransposition = semitones;
  document.getElementById('transposeVal').innerText = `${semitones > 0 ? '+' : ''}${semitones} Semi`;
  updateKeymapDisplay();
  window.pywebview.api.set_transpose(semitones);
}

function toggleAutoConnect() {
  window.pywebview.api.save_setting('auto_connect', document.getElementById('autoConnectCheck').checked);
}

function toggleLogging() {
  window.pywebview.api.save_setting('logging_enabled', document.getElementById('loggingCheck').checked);
}

async function openMidiFile() {
  await window.pywebview.api.open_midi_file();
}

function playMidiFile() {
  window.pywebview.api.play_midi_file();
}

function pauseMidiFile() {
  window.pywebview.api.pause_midi_file();
}

function stopMidiFile() {
  window.pywebview.api.stop_midi_file();
}

async function viewSheetNotation() {
  const sheetText = await window.pywebview.api.get_sheet_text();
  if (sheetText) {
    document.getElementById('sheetContentText').value = sheetText;
    document.getElementById('sheetModal').style.display = 'flex';
  }
}

function closeSheetModal() {
  document.getElementById('sheetModal').style.display = 'none';
}

function copySheetToClipboard() {
  const textarea = document.getElementById('sheetContentText');
  textarea.select();
  document.execCommand('copy');
  py_onLog('Copied sheet music notation to clipboard!');
}

function clearLogs() {
  document.getElementById('logConsole').innerHTML = '';
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.innerText = text;
  return div.innerHTML;
}
