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

// Full 88-Key MIDI Note to GLB Mesh Node Mapping (MIDI 21 / A0 to MIDI 108 / C8)
const MIDI_TO_NODE_MAP = {
  21: "white_A1",  22: "black_A#1", 23: "white_B1",  24: "white_C1",  25: "black_C#1",
  26: "white_D1",  27: "black_D#1", 28: "white_E1",  29: "white_F1",  30: "black_F#1",
  31: "white_G1",  32: "black_G#1", 33: "white_A2",  34: "black_A#2", 35: "white_B2",
  36: "white_C2",  37: "black_C#2", 38: "white_D2",  39: "black_D#2", 40: "white_E2",
  41: "white_F2",  42: "black_F#2", 43: "white_G2",  44: "black_G#2", 45: "white_A3",
  46: "black_A#3", 47: "white_B3",  48: "white_C3",  49: "black_C#3", 50: "white_D3",
  51: "black_D#3", 52: "white_E3",  53: "white_F3",  54: "black_F#3", 55: "white_G3",
  56: "black_G#3", 57: "white_A4",  58: "black_A#4", 59: "white_B4",  60: "white_C4",
  61: "black_C#4", 62: "white_D4",  63: "black_D#4", 64: "white_E4",  65: "white_F4",
  66: "black_F#4", 67: "white_G4",  68: "black_G#4", 69: "white_A5",  70: "black_A#5",
  71: "white_B5",  72: "white_C5",  73: "black_C#5", 74: "white_D5",  75: "black_D#5",
  76: "white_E5",  77: "white_F5",  78: "black_F#5", 79: "white_G5",  80: "black_G#5",
  81: "white_A6",  82: "black_A#6", 83: "white_B6",  84: "white_C6",  85: "black_C#6",
  86: "white_D6",  87: "black_D#6", 88: "white_E6",  89: "white_F6",  90: "black_F#6",
  91: "white_G6",  92: "black_G#6", 93: "white_A7",  94: "black_A#7", 95: "white_B7",
  96: "white_C7",  97: "black_C#7", 98: "white_D7",  99: "black_D#7", 100: "white_E7",
  101: "white_F7", 102: "black_F#7", 103: "white_G7", 104: "black_G#7", 105: "white_A8",
  106: "black_A#8", 107: "white_B8", 108: "white_C8"
};

// 3D Visualizer State
let threeScene, threeCamera, threeRenderer, threeControls;
let pianoModel = null;
const keyMeshMap = {};        // midiNote -> THREE.Object3D
const keyRestTransforms = {};  // midiNote -> { rotX, posY }
const activeKeyAnimations = {};// midiNote -> { targetDip: number, currentDip: number }
let currentVisualizerMode = '3d';

document.addEventListener('DOMContentLoaded', () => {
  renderPianoKeyboard();
  initThreePianoVisualizer();

  // Wait for pywebview API to be ready
  window.addEventListener('pywebviewready', () => {
    initBackend();
  });
});

/**
 * Initialize 3D Three.js Scene for 88-Key Grand Piano
 */
function initThreePianoVisualizer() {
  const canvas = document.getElementById('threeCanvas');
  const container = document.getElementById('piano3DViewport');
  if (!canvas || !container) return;

  const width = container.clientWidth || 800;
  const height = container.clientHeight || 220;

  // Scene
  threeScene = new THREE.Scene();
  threeScene.background = new THREE.Color(0xE0E5EC);

  // Camera
  threeCamera = new THREE.PerspectiveCamera(38, width / height, 0.1, 100);
  // Default perspective angle focused on center of keyboard
  threeCamera.position.set(0.0, 2.2, 3.2);

  // Renderer
  threeRenderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
  threeRenderer.setSize(width, height);
  threeRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  threeRenderer.toneMapping = THREE.ACESFilmicToneMapping;
  threeRenderer.toneMappingExposure = 1.15;
  threeRenderer.shadowMap.enabled = true;
  threeRenderer.shadowMap.type = THREE.PCFSoftShadowMap;

  // OrbitControls
  if (typeof THREE.OrbitControls !== 'undefined') {
    threeControls = new THREE.OrbitControls(threeCamera, threeRenderer.domElement);
    threeControls.enableDamping = true;
    threeControls.dampingFactor = 0.08;
    threeControls.target.set(0.0, 0.25, 0.0);
    threeControls.maxPolarAngle = Math.PI / 2 + 0.05;
    threeControls.minDistance = 1.0;
    threeControls.maxDistance = 8.0;
    threeControls.update();
  }

  // Soft Studio Lighting
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.85);
  threeScene.add(ambientLight);

  const keyLight = new THREE.DirectionalLight(0xffffff, 0.9);
  keyLight.position.set(-1.5, 5, 4);
  threeScene.add(keyLight);

  const fillLight = new THREE.DirectionalLight(0x9fa8da, 0.45);
  fillLight.position.set(3, 3, 2);
  threeScene.add(fillLight);

  const backLight = new THREE.DirectionalLight(0xb0bec5, 0.35);
  backLight.position.set(-5, 3, -3);
  threeScene.add(backLight);

  // Load GLB Model
  loadPianoModel();

  // Animation Loop
  function animate() {
    requestAnimationFrame(animate);
    updateKeyAnimations();
    if (threeControls) threeControls.update();
    threeRenderer.render(threeScene, threeCamera);
  }
  animate();

  // Resize handler
  window.addEventListener('resize', onThreeResize);
}

/**
 * Handle canvas resize
 */
function onThreeResize() {
  const container = document.getElementById('piano3DViewport');
  if (!container || !threeCamera || !threeRenderer) return;
  const width = container.clientWidth;
  const height = container.clientHeight;
  if (width === 0 || height === 0) return;

  threeCamera.aspect = width / height;
  threeCamera.updateProjectionMatrix();
  threeRenderer.setSize(width, height);
}

/**
 * Load GLB 88-Key Grand Piano model
 */
function loadPianoModel() {
  if (typeof THREE.GLTFLoader === 'undefined') {
    console.warn('GLTFLoader not loaded yet.');
    return;
  }

  const loader = new THREE.GLTFLoader();
  loader.load(
    'model.glb',
    (gltf) => {
      pianoModel = gltf.scene;
      threeScene.add(pianoModel);

      // Build node map for rapid note lookups
      const nodeDict = {};
      pianoModel.traverse((child) => {
        if (child.name) {
          nodeDict[child.name] = child;
        }
        if (child.isMesh) {
          child.castShadow = true;
          child.receiveShadow = true;
          if (child.material) {
            child.material = child.material.clone();
            child.material.roughness = 0.35;
          }
        }
      });

      // Map MIDI numbers (21 to 108) to corresponding Key Nodes using their native model pivots
      for (const [midiStr, nodeName] of Object.entries(MIDI_TO_NODE_MAP)) {
        const midiNum = parseInt(midiStr, 10);
        const node = nodeDict[nodeName];
        if (node) {
          const isBlack = nodeName.startsWith('black_');
          keyMeshMap[midiNum] = {
            node: node,
            origRotX: node.rotation.x,
            isBlack: isBlack
          };
          activeKeyAnimations[midiNum] = { targetDip: 0, currentDip: 0 };
        }
      }

      // Hide loading overlay
      const overlay = document.getElementById('modelLoadingOverlay');
      if (overlay) {
        overlay.style.opacity = '0';
        setTimeout(() => overlay.style.display = 'none', 400);
      }
    },
    (xhr) => {
      // Progress
    },
    (error) => {
      console.error('Error loading 3D piano model:', error);
      const overlay = document.getElementById('modelLoadingOverlay');
      if (overlay) overlay.innerText = 'Unable to load 3D Piano Model';
    }
  );
}

/**
 * Camera Presets (Perspective, Top, Player)
 */
function setCameraPreset(preset) {
  if (!threeCamera || !threeControls) return;

  const targetCenter = new THREE.Vector3(0.0, 0.25, 0.0);
  threeControls.target.copy(targetCenter);

  document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));

  if (preset === 'perspective') {
    threeCamera.position.set(0.0, 2.2, 3.2);
    document.querySelectorAll('.view-btn')[0]?.classList.add('active');
  } else if (preset === 'top') {
    threeCamera.position.set(0.0, 4.2, 0.1);
    document.querySelectorAll('.view-btn')[1]?.classList.add('active');
  } else if (preset === 'player') {
    threeCamera.position.set(0.0, 1.2, 2.2);
    document.querySelectorAll('.view-btn')[2]?.classList.add('active');
  }
  threeControls.update();
}

function reset3DCamera() {
  setCameraPreset('perspective');
}

/**
 * Switch Visualizer Mode (3D vs 2D)
 */
function switchVisualizerMode(mode) {
  currentVisualizerMode = mode;
  const view3D = document.getElementById('piano3DViewport');
  const view2D = document.getElementById('piano2DViewport');
  const btn3D = document.getElementById('btnMode3D');
  const btn2D = document.getElementById('btnMode2D');
  const badge = document.getElementById('visualizerModeBadge');
  const camControls = document.getElementById('cameraControls3D');

  if (mode === '3d') {
    view3D.style.display = 'block';
    view2D.style.display = 'none';
    btn3D.classList.add('active');
    btn2D.classList.remove('active');
    if (camControls) camControls.style.display = 'flex';
    if (badge) badge.innerText = '3D GRAND 88-KEY';
    setTimeout(onThreeResize, 50);
  } else {
    view3D.style.display = 'none';
    view2D.style.display = 'block';
    btn2D.classList.add('active');
    btn3D.classList.remove('active');
    if (camControls) camControls.style.display = 'none';
    if (badge) badge.innerText = '2D KEYMAP 61-KEY';
  }
}

/**
 * Smooth Realistic Key Pivot Rotation Animation Loop
 * Key rotates downward around the updated native node pivot
 */
function updateKeyAnimations() {
  const whiteDipAngle = -0.11; // ~6.3 degrees downward rotation for distinct visual keystrokes
  const blackDipAngle = -0.09; // ~5.2 degrees downward rotation for black keys
  const lerpSpeed = 0.38;

  for (const [midiStr, anim] of Object.entries(activeKeyAnimations)) {
    const midi = parseInt(midiStr, 10);
    const keyData = keyMeshMap[midi];
    if (!keyData || !keyData.node) continue;

    const maxDip = keyData.isBlack ? blackDipAngle : whiteDipAngle;
    const baseRotX = keyData.origRotX || 0;

    // Smoothly interpolate current dip to target dip
    if (Math.abs(anim.currentDip - anim.targetDip) > 0.0005) {
      anim.currentDip += (anim.targetDip - anim.currentDip) * lerpSpeed;
      keyData.node.rotation.x = baseRotX + (anim.currentDip * maxDip);
    } else if (anim.currentDip !== anim.targetDip) {
      anim.currentDip = anim.targetDip;
      keyData.node.rotation.x = baseRotX + (anim.targetDip * maxDip);
    }
  }
}

/**
 * 3D Key Trigger Action with Vibrant Illumination Glow
 */
function trigger3DKey(note, isPressed) {
  const anim = activeKeyAnimations[note];
  const keyData = keyMeshMap[note];
  if (anim) {
    anim.targetDip = isPressed ? 1.0 : 0.0;
  }

  // Highlight key mesh with vibrant emissive illumination glow
  if (keyData && keyData.node) {
    const isBlack = keyData.isBlack;
    // Radiant violet glow for white keys, cyan/violet illumination for black keys
    const glowColor = isBlack ? new THREE.Color(0x8B84FF) : new THREE.Color(0x6C63FF);
    const glowIntensity = isBlack ? 1.4 : 1.1;

    keyData.node.traverse((child) => {
      if (child.isMesh && child.material) {
        if (!child.userData.origMatSetup) {
          child.userData.origMatSetup = true;
          child.userData.origColor = child.material.color ? child.material.color.clone() : new THREE.Color(0xffffff);
          child.userData.origEmissive = child.material.emissive ? child.material.emissive.clone() : new THREE.Color(0x000000);
        }

        if (isPressed) {
          child.material.emissive = glowColor;
          child.material.emissiveIntensity = glowIntensity;
          if (child.material.color) {
            child.material.color.set(isBlack ? 0x9fa8da : 0xd1c4e9);
          }
        } else {
          if (child.userData.origEmissive) {
            child.material.emissive.copy(child.userData.origEmissive);
            child.material.emissiveIntensity = 0.0;
          }
          if (child.userData.origColor && child.material.color) {
            child.material.color.copy(child.userData.origColor);
          }
        }
      }
    });
  }
}

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
      if (initData.current_soundbank) {
        document.getElementById('soundbankSelect').value = initData.current_soundbank;
      }
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

      // WebSocket status
      if (initData.ws_server_url) {
        const endpointEl = document.getElementById('wsEndpointText');
        if (endpointEl) endpointEl.innerText = initData.ws_server_url;
      }
      if (typeof initData.ws_clients_count !== 'undefined') {
        const countBadge = document.getElementById('wsClientsCountBadge');
        if (countBadge) countBadge.innerText = `${initData.ws_clients_count} Connected`;
      }

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
  // Trigger 2D Visualizer
  const keyEl = document.getElementById(`key-${note}`);
  if (keyEl) {
    keyEl.classList.add('active');
  }
  // Trigger 3D 88-Key Model
  trigger3DKey(note, true);
};

window.py_onNoteOff = function(note) {
  // Trigger 2D Visualizer
  const keyEl = document.getElementById(`key-${note}`);
  if (keyEl) {
    keyEl.classList.remove('active');
  }
  // Trigger 3D 88-Key Model
  trigger3DKey(note, false);
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

window.py_onWsClientsChanged = function(count) {
  const countBadge = document.getElementById('wsClientsCountBadge');
  if (countBadge) {
    countBadge.innerText = `${count} Connected`;
  }
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

function onSoundbankChanged() {
  const bank = document.getElementById('soundbankSelect').value;
  window.pywebview.api.set_soundbank(bank);
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
