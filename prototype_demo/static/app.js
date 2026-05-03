const state = {
  memoryEnabled: true,
  pending: false,
  messages: [],
  voiceClientUrl: "",
  voiceProxyUrl: "",
  voiceAvailable: false,
  shouldSpeakReply: false,
  activeAudio: null,
  activeAudioUrl: "",
  voiceConnecting: false,
  voiceConnected: false,
  voiceSessionId: "",
  voicePcId: "",
  applyingVoiceChoice: false,
  micEnabled: true,
  speechEnabled: true,
  memoryImportOpen: false,
  memoryImportPending: false,
  deletingMemoryIds: new Set(),
  contextEngineV2: true,
  showContextTrace: true,
  lastContextDebug: null,
  characterCards: [],
  activeCharacterCardId: "",
  characterVoiceOptions: [],
  availableModels: [],
  currentModel: "",
};

const chatStream = document.getElementById("chatStream");
const messageInput = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const toggleOn = document.getElementById("toggleOn");
const toggleOff = document.getElementById("toggleOff");
const resetSessionBtn = document.getElementById("resetSessionBtn");
const clearMemoryBtn = document.getElementById("clearMemoryBtn");
const memoryModeLabel = document.getElementById("memoryModeLabel");
const memoryStatusCard = document.getElementById("memoryStatusCard");
const memoryPanel = document.getElementById("memoryPanel");
const panelModeHint = document.getElementById("panelModeHint");
const memoryUsageBadge = document.getElementById("memoryUsageBadge");
const situationBadge = document.getElementById("situationBadge");
const toggleMemoryImportBtn = document.getElementById("toggleMemoryImportBtn");
const memoryImportPanel = document.getElementById("memoryImportPanel");
const closeMemoryImportBtn = document.getElementById("closeMemoryImportBtn");
const memoryImportInput = document.getElementById("memoryImportInput");
const submitMemoryImportBtn = document.getElementById("submitMemoryImportBtn");
const memoryImportStatus = document.getElementById("memoryImportStatus");
const updateList = document.getElementById("updateList");
const runtimeCardApplied = document.getElementById("runtimeCardApplied");
const runtimeCardSelected = document.getElementById("runtimeCardSelected");
const runtimeCardSync = document.getElementById("runtimeCardSync");
const personaGrid = document.getElementById("personaGrid");
const preferenceGrid = document.getElementById("preferenceGrid");
const eventTimeline = document.getElementById("eventTimeline");
const conflictTimeline = document.getElementById("conflictTimeline");
const memoryPreview = document.getElementById("memoryPreview");
const voiceInlineDock = document.getElementById("voiceInlineDock");
const voiceInlineFrameShell = document.getElementById("voiceInlineFrameShell");
const voiceStatusIndicator = document.getElementById("voiceStatusIndicator");
const voiceRemoteAudio = document.getElementById("voiceRemoteAudio");
const micBtn = document.getElementById("micBtn");
const speechToggleBtn = document.getElementById("speechToggleBtn");
const characterCardSelect = document.getElementById("characterCardSelect");
const applyCharacterCardBtn = document.getElementById("applyCharacterCardBtn");
const characterCardStatus = document.getElementById("characterCardStatus");
const characterList = document.getElementById("characterList");
const characterCardNameInput = document.getElementById("characterCardNameInput");
const characterCardDescriptionInput = document.getElementById("characterCardDescriptionInput");
const characterCardVoiceSelect = document.getElementById("characterCardVoiceSelect");
const quickVoiceSelect = document.getElementById("quickVoiceSelect");
const saveCharacterCardBtn = document.getElementById("saveCharacterCardBtn");
const modelSelect = document.getElementById("modelSelect");

// Character Card Visual Elements
const cardVisualAvatar = document.getElementById("cardVisualAvatar");
const cardVisualAvatarText = document.getElementById("cardVisualAvatarText");
const cardVisualName = document.getElementById("cardVisualName");
const cardVisualVoice = document.getElementById("cardVisualVoice");
const cardVisualDesc = document.getElementById("cardVisualDesc");
const cardVisualId = document.getElementById("cardVisualId");
const downloadCardBtn = document.getElementById("downloadCardBtn");
const cardCanvas = document.getElementById("cardCanvas");

const SPEECH_ENABLED_STORAGE_KEY = "memory_demo_speech_enabled";

function loadSpeechEnabledPreference() {
  try {
    const stored = window.localStorage.getItem(SPEECH_ENABLED_STORAGE_KEY);
    if (stored === "0" || stored === "false") {
      return false;
    }
    if (stored === "1" || stored === "true") {
      return true;
    }
  } catch (_error) {}
  return true;
}

function persistSpeechEnabledPreference(enabled) {
  try {
    window.localStorage.setItem(SPEECH_ENABLED_STORAGE_KEY, enabled ? "1" : "0");
  } catch (_error) {}
}

// Character Card Visual Generation - Warm cozy palette
const CARD_COLOR_PAIRS = [
  { bg: [198, 125, 94], grad: [217, 154, 126] },   // warm coral
  { bg: [201, 154, 78], grad: [217, 176, 112] },   // warm amber
  { bg: [138, 170, 140], grad: [166, 191, 168] },  // sage green
  { bg: [176, 130, 130], grad: [196, 156, 156] },  // dusty rose
  { bg: [150, 130, 170], grad: [174, 156, 192] },  // dusty lavender
  { bg: [160, 140, 110], grad: [184, 166, 138] },  // warm taupe
  { bg: [130, 160, 180], grad: [156, 182, 200] },  // dusty blue
  { bg: [190, 140, 100], grad: [210, 166, 128] },  // warm bronze
  { bg: [140, 170, 150], grad: [166, 192, 176] },  // soft mint
  { bg: [180, 120, 120], grad: [200, 148, 148] },  // warm brick
];

function stringToColorIndex(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  return Math.abs(hash) % CARD_COLOR_PAIRS.length;
}

function getInitials(name) {
  if (!name) return "?";
  const cleaned = name.trim();
  if (!cleaned) return "?";
  const char = cleaned.charAt(0);
  return char.toUpperCase();
}

function updateCharacterCardPreview() {
  const name = characterCardNameInput?.value || "";
  const voiceType = characterCardVoiceSelect?.value || "";
  const description = characterCardDescriptionInput?.value || "";
  const voiceOption = state.characterVoiceOptions.find(v => v.voice_type === voiceType);
  const voiceName = voiceOption?.name || voiceType || "选择音色";
  
  if (cardVisualName) cardVisualName.textContent = name.trim() || "未命名角色";
  if (cardVisualVoice) cardVisualVoice.textContent = voiceName;
  if (cardVisualDesc) cardVisualDesc.textContent = description.trim() || "暂无描述";
  
  const cardId = normalizeCardId(name) || "—";
  if (cardVisualId) cardVisualId.textContent = `ID: ${cardId}`;
  
  const initials = getInitials(name);
  if (cardVisualAvatarText) cardVisualAvatarText.textContent = initials;
  
  const colorIdx = stringToColorIndex(name || "default");
  const colors = CARD_COLOR_PAIRS[colorIdx];
  if (cardVisualAvatar && colors) {
    cardVisualAvatar.style.background = `linear-gradient(135deg, rgb(${colors.bg.join(",")}), rgb(${colors.grad.join(",")}))`;
    cardVisualAvatar.style.boxShadow = `0 4px 12px rgba(${colors.bg.join(",")}, 0.4)`;
  }
}

function drawCardToCanvas() {
  const canvas = cardCanvas;
  if (!canvas) return null;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  
  const width = 600;
  const height = 340;
  canvas.width = width;
  canvas.height = height;
  
  const name = characterCardNameInput?.value || "未命名角色";
  const voiceType = characterCardVoiceSelect?.value || "";
  const voiceOption = state.characterVoiceOptions.find(v => v.voice_type === voiceType);
  const voiceName = voiceOption?.name || voiceType || "选择音色";
  const description = characterCardDescriptionInput?.value || "暂无描述";
  const cardId = normalizeCardId(name) || "—";
  const initials = getInitials(name);
  const colorIdx = stringToColorIndex(name || "default");
  const colors = CARD_COLOR_PAIRS[colorIdx];
  
  // Background - warm cozy gradient
  const grad = ctx.createLinearGradient(0, 0, width, height);
  grad.addColorStop(0, "#2d2520");
  grad.addColorStop(0.5, "#3d3028");
  grad.addColorStop(1, "#4a3a30");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, width, height);
  
  // Warm glow
  const glowGrad = ctx.createRadialGradient(width - 60, 40, 0, width - 60, 40, 150);
  glowGrad.addColorStop(0, "rgba(198, 125, 94, 0.1)");
  glowGrad.addColorStop(1, "transparent");
  ctx.fillStyle = glowGrad;
  ctx.fillRect(0, 0, width, height);
  
  // Avatar circle
  const avatarX = 40;
  const avatarY = 40;
  const avatarR = 36;
  const avatarGrad = ctx.createLinearGradient(avatarX - avatarR, avatarY - avatarR, avatarX + avatarR, avatarY + avatarR);
  if (colors) {
    avatarGrad.addColorStop(0, `rgb(${colors.bg.join(",")})`);
    avatarGrad.addColorStop(1, `rgb(${colors.grad.join(",")})`);
  } else {
    avatarGrad.addColorStop(0, "#e94560");
    avatarGrad.addColorStop(1, "#ff6b6b");
  }
  ctx.beginPath();
  ctx.arc(avatarX + avatarR, avatarY + avatarR, avatarR, 0, Math.PI * 2);
  ctx.fillStyle = avatarGrad;
  ctx.fill();
  
  // Avatar shadow
  ctx.shadowColor = colors ? `rgba(${colors.bg.join(",")}, 0.4)` : "rgba(233, 69, 96, 0.4)";
  ctx.shadowBlur = 20;
  ctx.shadowOffsetX = 0;
  ctx.shadowOffsetY = 4;
  ctx.beginPath();
  ctx.arc(avatarX + avatarR, avatarY + avatarR, avatarR, 0, Math.PI * 2);
  ctx.fill();
  ctx.shadowColor = "transparent";
  
  // Avatar text
  ctx.fillStyle = "#fff";
  ctx.font = "bold 28px 'DM Sans', sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(initials, avatarX + avatarR, avatarY + avatarR);
  
  // Name
  ctx.textAlign = "left";
  ctx.fillStyle = "#fff";
  ctx.font = "bold 22px 'DM Sans', sans-serif";
  ctx.fillText(name.trim() || "未命名角色", 110, 58);
  
  // Voice
  ctx.fillStyle = "rgba(255,255,255,0.6)";
  ctx.font = "13px 'IBM Plex Mono', monospace";
  ctx.fillText(voiceName, 110, 82);
  
  // Divider
  ctx.beginPath();
  ctx.moveTo(40, 115);
  ctx.lineTo(560, 115);
  const divGrad = ctx.createLinearGradient(40, 115, 560, 115);
  divGrad.addColorStop(0, "rgba(255,255,255,0.2)");
  divGrad.addColorStop(1, "transparent");
  ctx.strokeStyle = divGrad;
  ctx.lineWidth = 1;
  ctx.stroke();
  
  // Description
  ctx.fillStyle = "rgba(255,255,255,0.75)";
  ctx.font = "15px 'DM Sans', sans-serif";
  const maxWidth = 520;
  const lineHeight = 24;
  const maxLines = 5;
  const words = (description.trim() || "暂无描述").split("");
  let line = "";
  let lines = [];
  for (let n = 0; n < words.length; n++) {
    const testLine = line + words[n];
    const metrics = ctx.measureText(testLine);
    if (metrics.width > maxWidth && n > 0) {
      lines.push(line);
      line = words[n];
    } else {
      line = testLine;
    }
  }
  lines.push(line);
  for (let k = 0; k < Math.min(lines.length, maxLines); k++) {
    ctx.fillText(lines[k], 40, 150 + k * lineHeight);
  }
  
  // Footer
  ctx.fillStyle = "rgba(255,255,255,0.08)";
  ctx.beginPath();
  ctx.roundRect(40, height - 50, 90, 26, 4);
  ctx.fill();
  ctx.fillStyle = "rgba(255,255,255,0.5)";
  ctx.font = "10px 'IBM Plex Mono', monospace";
  ctx.textAlign = "center";
  ctx.fillText("AI Character", 85, height - 34);
  
  ctx.textAlign = "right";
  ctx.fillStyle = "rgba(255,255,255,0.35)";
  ctx.font = "11px 'IBM Plex Mono', monospace";
  ctx.fillText(`ID: ${cardId}`, width - 40, height - 34);
  
  return canvas;
}

function downloadCharacterCard() {
  const canvas = drawCardToCanvas();
  if (!canvas) return;
  const link = document.createElement("a");
  link.download = `character-card-${normalizeCardId(characterCardNameInput?.value) || "card"}.png`;
  link.href = canvas.toDataURL("image/png");
  link.click();
}

let permissionProbeStream = null;
let localVoiceStream = null;
let localVoiceRawStream = null;
let remoteVoiceStream = null;
let voicePeerConnection = null;
let voiceDataChannel = null;
let voicePingTimer = null;
let voiceAudioContext = null;
let voiceSourceNode = null;
let voiceGainNode = null;
let voiceDestinationNode = null;
let ttsChunkQueue = [];
let ttsChunkPlaying = false;

const MIC_CONSTRAINTS = {
  audio: {
    channelCount: 1,
    sampleRate: 48000,
    sampleSize: 16,
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  },
};

const MIC_INPUT_GAIN = 1.8;

async function requestMicrophonePermission() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("当前浏览器不支持麦克风权限请求");
  }

  releasePermissionProbeStream();
  permissionProbeStream = await navigator.mediaDevices.getUserMedia(MIC_CONSTRAINTS);
  return permissionProbeStream;
}

function releasePermissionProbeStream() {
  if (!permissionProbeStream) {
    return;
  }
  permissionProbeStream.getTracks().forEach((track) => track.stop());
  permissionProbeStream = null;
}

function cleanupVoiceInputNodes() {
  if (voiceSourceNode) {
    try {
      voiceSourceNode.disconnect();
    } catch (_error) {}
    voiceSourceNode = null;
  }
  if (voiceGainNode) {
    try {
      voiceGainNode.disconnect();
    } catch (_error) {}
    voiceGainNode = null;
  }
  if (voiceDestinationNode) {
    try {
      voiceDestinationNode.disconnect();
    } catch (_error) {}
    voiceDestinationNode = null;
  }
  if (voiceAudioContext) {
    try {
      voiceAudioContext.close();
    } catch (_error) {}
    voiceAudioContext = null;
  }
}

function createProcessedVoiceStream(rawStream) {
  cleanupVoiceInputNodes();

  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) {
    return rawStream;
  }

  voiceAudioContext = new AudioContextClass();
  voiceSourceNode = voiceAudioContext.createMediaStreamSource(rawStream);
  voiceGainNode = voiceAudioContext.createGain();
  voiceGainNode.gain.value = MIC_INPUT_GAIN;
  voiceDestinationNode = voiceAudioContext.createMediaStreamDestination();

  voiceSourceNode.connect(voiceGainNode);
  voiceGainNode.connect(voiceDestinationNode);
  return voiceDestinationNode.stream;
}

function stopVoicePing() {
  if (voicePingTimer) {
    window.clearInterval(voicePingTimer);
    voicePingTimer = null;
  }
}

function startVoicePing() {
  stopVoicePing();
  voicePingTimer = window.setInterval(() => {
    if (voiceDataChannel?.readyState === "open") {
      voiceDataChannel.send(`ping:${Date.now()}`);
    }
  }, 1000);
}

function updateVoiceIndicator() {
  if (!voiceStatusIndicator) return;
  
  if (state.voiceConnected) {
    voiceStatusIndicator.classList.add("is-connected");
    voiceStatusIndicator.title = "语音已连接";
  } else {
    voiceStatusIndicator.classList.remove("is-connected");
    voiceStatusIndicator.title = state.voiceAvailable ? "语音服务在线，点击连接" : "语音服务离线";
  }
}

function setVoiceStatus(message) {
  // Status now shown via indicator only
  console.log("Voice status:", message);
}

function resetVoiceState() {
  state.voiceConnecting = false;
  state.voiceConnected = false;
  state.voiceSessionId = "";
  state.voicePcId = "";
  updateVoiceIndicator();
}

async function waitForIceGatheringComplete(pc, timeoutMs = 8000) {
  if (pc.iceGatheringState === "complete") {
    return { completed: true, timedOut: false };
  }
  return await new Promise((resolve) => {
    const timeoutId = window.setTimeout(() => {
      cleanup();
      resolve({ completed: false, timedOut: true });
    }, timeoutMs);

    function cleanup() {
      window.clearTimeout(timeoutId);
      pc.removeEventListener("icegatheringstatechange", handleStateChange);
    }

    function handleStateChange() {
      if (pc.iceGatheringState === "complete") {
        cleanup();
        resolve({ completed: true, timedOut: false });
      }
    }

    pc.addEventListener("icegatheringstatechange", handleStateChange);
  });
}

function localDescriptionHasIceCandidate(pc) {
  const sdp = pc?.localDescription?.sdp || "";
  return /\na=candidate:/m.test(`\n${sdp}`);
}

async function createVoiceSession() {
  const response = await fetch("/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      createDailyRoom: false,
      enableDefaultIceServers: true,
      transport: "webrtc",
    }),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || payload.error || "Failed to create voice session");
  }
  return payload;
}

async function createVoiceOffer(sessionId, payload) {
  const response = await fetch(`/sessions/${sessionId}/api/offer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const answer = await response.json();
  if (!response.ok) {
    throw new Error(answer.detail || answer.error || "Failed to negotiate WebRTC");
  }
  return answer;
}

function setupVoicePeerConnection(iceServers) {
  const pc = new RTCPeerConnection({ iceServers });

  remoteVoiceStream = new MediaStream();
  voiceRemoteAudio.srcObject = remoteVoiceStream;
  voiceRemoteAudio.muted = false;

  pc.addEventListener("track", (event) => {
    if (event.track.kind !== "audio") {
      return;
    }
    remoteVoiceStream.addTrack(event.track);
    // autoplay on the audio element handles playback; explicit play() can
    // cause duplicate playback streams in some browsers.
  });

  pc.addEventListener("connectionstatechange", () => {
    const stateName = pc.connectionState;
    if (stateName === "connected") {
      state.voiceConnecting = false;
      state.voiceConnected = true;
      updateVoiceIndicator();
      setMicUi();
      return;
    }
    if (stateName === "connecting") {
      return;
    }
    if (stateName === "failed" || stateName === "disconnected" || stateName === "closed") {
      disconnectVoice({ keepStatus: stateName === "closed" }).catch(() => {});
    }
  });

  voiceDataChannel = pc.createDataChannel("signalling");
  voiceDataChannel.addEventListener("open", () => {
    startVoicePing();
  });
  voiceDataChannel.addEventListener("close", () => {
    stopVoicePing();
  });

  return pc;
}

function stopReplyAudio() {
  ttsChunkQueue = [];
  ttsChunkPlaying = false;
  const synth = window.speechSynthesis;
  if (synth) {
    synth.cancel();
  }
  if (state.activeAudio) {
    state.activeAudio.pause();
    state.activeAudio.src = "";
    state.activeAudio = null;
  }
  if (state.activeAudioUrl) {
    URL.revokeObjectURL(state.activeAudioUrl);
    state.activeAudioUrl = "";
  }
}

function setLocalMicEnabled(enabled) {
  const nextEnabled = Boolean(enabled);
  state.micEnabled = nextEnabled;

  if (localVoiceStream) {
    localVoiceStream.getAudioTracks().forEach((track) => {
      track.enabled = nextEnabled;
    });
  }
  if (localVoiceRawStream) {
    localVoiceRawStream.getAudioTracks().forEach((track) => {
      track.enabled = nextEnabled;
    });
  }
}

function setSpeechToggleUi() {
  if (!speechToggleBtn) {
    return;
  }
  speechToggleBtn.classList.toggle("is-active", state.speechEnabled);
  speechToggleBtn.classList.toggle("is-muted", !state.speechEnabled);
  speechToggleBtn.disabled = state.pending;
  
  // Toggle icon visibility
  const iconOn = speechToggleBtn.querySelector(".icon-voice-on");
  const iconOff = speechToggleBtn.querySelector(".icon-voice-off");
  if (iconOn) iconOn.style.display = state.speechEnabled ? "block" : "none";
  if (iconOff) iconOff.style.display = state.speechEnabled ? "none" : "block";
}

function setMicUi() {
  if (!micBtn) {
    return;
  }

  // Update mic icon state
  const isListening = state.voiceConnecting || state.voiceConnected;
  const isMuted = state.voiceConnected && !state.micEnabled;
  micBtn.classList.toggle("is-active", isListening);
  micBtn.classList.toggle("is-muted", isMuted);
  micBtn.disabled = state.pending || state.applyingVoiceChoice || !state.voiceAvailable || state.voiceConnecting;

  // Toggle icon visibility
  const iconOn = micBtn.querySelector(".icon-mic-on");
  const iconOff = micBtn.querySelector(".icon-mic-off");
  if (iconOn) iconOn.style.display = isMuted ? "none" : "block";
  if (iconOff) iconOff.style.display = isMuted ? "block" : "none";

  if (quickVoiceSelect) {
    quickVoiceSelect.disabled = state.pending || state.applyingVoiceChoice;
  }

  updateVoiceIndicator();
}

async function synthesizeReplyAudio(text) {
  const response = await fetch("/api/synthesize-audio", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });

  if (!response.ok) {
    const rawText = await response.text();
    let errorMessage = "Speech synthesis failed";
    if (rawText) {
      try {
        const payload = JSON.parse(rawText);
        errorMessage = payload.error || errorMessage;
      } catch (_error) {
        errorMessage = rawText;
      }
    }
    throw new Error(errorMessage);
  }

  return response.blob();
}

async function speakReply(text) {
  if (!text) {
    return;
  }

  try {
    const audioBlob = await synthesizeReplyAudio(text);
    if (audioBlob.size) {
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      state.activeAudio = audio;
      state.activeAudioUrl = audioUrl;
      await audio.play();
      await new Promise((resolve) => {
        const finalize = () => {
          if (state.activeAudio === audio) {
            state.activeAudio = null;
          }
          if (state.activeAudioUrl === audioUrl) {
            URL.revokeObjectURL(audioUrl);
            state.activeAudioUrl = "";
          }
          resolve();
        };
        audio.addEventListener("ended", finalize, { once: true });
        audio.addEventListener("error", finalize, { once: true });
      });
      return;
    }
  } catch (error) {
    console.error("Backend TTS failed, falling back to browser synthesis:", error);
  }

  const synth = window.speechSynthesis;
  if (!synth) {
    return;
  }
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "zh-CN";
  utterance.rate = 1;
  utterance.pitch = 1;
  await new Promise((resolve) => {
    utterance.addEventListener("end", () => resolve(), { once: true });
    utterance.addEventListener("error", () => resolve(), { once: true });
    synth.speak(utterance);
  });
}

function splitSpeakableChunks(text, flush = false) {
  const chunks = [];
  let cursor = 0;
  // Primary split points: sentence endings
  const sentenceEnd = /[。！？!?；;：:\n]/;
  // Secondary split points: commas (used when chunk gets too long)
  const comma = /[，、]/;
  const MIN_CHUNK_LENGTH = 12;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const currentLength = index - cursor + 1;

    // Always split at sentence endings
    if (sentenceEnd.test(char)) {
      const sentence = text.slice(cursor, index + 1).trim();
      if (sentence) {
        chunks.push(sentence);
      }
      cursor = index + 1;
      continue;
    }

    // Split at commas only if chunk is long enough (prevents cutting too early)
    if (comma.test(char) && currentLength >= MIN_CHUNK_LENGTH) {
      const sentence = text.slice(cursor, index + 1).trim();
      if (sentence) {
        chunks.push(sentence);
      }
      cursor = index + 1;
    }
  }

  let rest = text.slice(cursor);
  if (flush) {
    const tail = rest.trim();
    if (tail) {
      chunks.push(tail);
    }
    rest = "";
  }

  return { chunks, rest };
}

async function playTtsQueue() {
  if (ttsChunkPlaying) {
    return;
  }
  ttsChunkPlaying = true;
  try {
    while (ttsChunkQueue.length) {
      const chunk = ttsChunkQueue.shift();
      if (!chunk) {
        continue;
      }
      await speakReply(chunk);
    }
  } finally {
    ttsChunkPlaying = false;
  }
}

function enqueueTtsChunk(text) {
  const normalized = String(text || "").trim();
  if (!normalized) {
    return;
  }
  ttsChunkQueue.push(normalized);
  playTtsQueue().catch((error) => {
    console.error("Streaming TTS queue failed:", error);
  });
}

async function connectVoice() {
  if (!state.voiceAvailable || state.voiceConnecting || state.voiceConnected || voicePeerConnection) {
    return;
  }

  state.voiceConnecting = true;
  updateVoiceIndicator();
  setMicUi();
  setVoiceStatus("正在请求麦克风权限...");

  try {
    localVoiceRawStream = await requestMicrophonePermission();
    localVoiceStream = createProcessedVoiceStream(localVoiceRawStream);
    setLocalMicEnabled(true);
    const session = await createVoiceSession();
    state.voiceSessionId = session.sessionId || "";
    updateVoiceIndicator();

    const iceServers = session.iceConfig?.iceServers || [];
    voicePeerConnection = setupVoicePeerConnection(iceServers);

    for (const track of localVoiceStream.getTracks()) {
      voicePeerConnection.addTrack(track, localVoiceStream);
    }

    const offer = await voicePeerConnection.createOffer({
      offerToReceiveAudio: true,
    });
    await voicePeerConnection.setLocalDescription(offer);
    const iceGathering = await waitForIceGatheringComplete(voicePeerConnection);
    const hasLocalCandidate = localDescriptionHasIceCandidate(voicePeerConnection);

    if (iceGathering.timedOut && !hasLocalCandidate) {
      throw new Error("ICE gathering timed out");
    }

    if (iceGathering.timedOut) {
      setVoiceStatus("ICE gathering 超时，已使用当前候选继续协商...");
    }

    const answer = await createVoiceOffer(state.voiceSessionId, {
      sdp: voicePeerConnection.localDescription.sdp,
      type: voicePeerConnection.localDescription.type,
    });
    state.voicePcId = answer.pc_id || "";
    await voicePeerConnection.setRemoteDescription(
      new RTCSessionDescription({
        sdp: answer.sdp,
        type: answer.type,
      })
    );

    setVoiceStatus("语音会话已创建，正在等待连接建立...");
  } catch (error) {
    await disconnectVoice({ keepStatus: true });
    setVoiceStatus(`语音连接失败：${error.message}`);
    console.error("Voice connection failed:", error);
  } finally {
    state.voiceConnecting = false;
    updateVoiceIndicator();
    setMicUi();
  }
}

async function disconnectVoice(options = {}) {
  stopVoicePing();
  voiceDataChannel = null;

  if (voicePeerConnection) {
    try {
      voicePeerConnection.close();
    } catch (_error) {
    }
    voicePeerConnection = null;
  }

  if (localVoiceStream) {
    localVoiceStream.getTracks().forEach((track) => track.stop());
    localVoiceStream = null;
  }
  if (localVoiceRawStream) {
    localVoiceRawStream.getTracks().forEach((track) => track.stop());
    localVoiceRawStream = null;
  }
  cleanupVoiceInputNodes();
  releasePermissionProbeStream();
  state.micEnabled = true;

  if (remoteVoiceStream) {
    remoteVoiceStream.getTracks().forEach((track) => track.stop());
    remoteVoiceStream = null;
  }
  if (voiceRemoteAudio) {
    voiceRemoteAudio.pause();
    voiceRemoteAudio.srcObject = null;
  }

  resetVoiceState();
  // Reset auto-connect flag so reconnection can happen after manual disconnect
  autoConnectAttempted = false;
  setMicUi();
  if (!options.keepStatus) {
    setVoiceStatus("语音已断开。重新点击 Connect 或 Mic 可再次连接。");
  }
}

// Character self-introductions (social platform bio style)
const CHARACTER_INTROS = {
  "default_companion": "深夜型选手，常年和台灯、耳机、半杯水共处一室。话不多，但在线；不太会热场，但很会一起沉默。喜欢把复杂的日子过慢一点，也喜欢听人讲那些没头没尾的小事。",

  "sprite_girl": "脑内常驻八百个小剧场，随机播放，拒绝预告。喜欢奇怪比喻、冷门小梗、突然跑偏又突然绕回来。看起来不太正经，但关键时刻还挺靠谱。人生目标：把无聊聊天变成连续剧。",

  "gentle_sister": "图书馆角落常驻人口，奶茶半糖，耳机降噪。喜欢慢慢讲话，也喜欢把事情想清楚再开口。不爱热闹，但不冷淡；不太锋利，但有自己的判断。偶尔成熟，偶尔也会被生活绊一跤。",

  "energetic_youth": "少内耗，多行动。咖啡可以不喝，事情不能不干。喜欢把大问题拆成小步骤，拆完就开始动手。人生信条：先搞起来，边跑边修。",

  "gd_uncle": "老广体质，看到「附近有什么好吃的」会自动开机。肠粉、烧腊、糖水、茶餐厅，都有一点个人偏见。周末可能在老城区乱逛，也可能在深圳地铁里赶路。做人最紧要：舒服、实在、食好啲。",

  "wanqu_uncle": "长期出没于广深港澳之间，熟悉地铁、口岸、写字楼和夜宵摊。喜欢听城市的声音：广州的烟火气、深圳的速度、香港的边界感、澳门的慢。不爱讲大道理，比较相信真实经验。湾区生存关键词：会走位，识变通。",

  "daimeng_chuanmei": "重庆妹儿一枚，嘴快心软，脑壳头想法有点多。爱摆龙门阵，爱吃辣，也爱突然发出「啷个会这样」的感叹。有时元气满满，有时原地犯懵。人生原则：莫慌，先吃点东西再说。",

  "yuzhou_zixuan": "河南来的，主打一个实在。话不花，但管用；人不酷，但靠谱。喜欢把事儿摊开说，不喜欢绕来绕去。常用语：中，咱慢慢唠。",

  "guangxi_yuanzhou": "广西人，慢热，爱笑，存在感不高但很好相处。喜欢安安静静待着，也喜欢突然下楼买点吃的。不太会讲漂亮话，但一般都是真话。宿舍氛围组编外成员，主打一个自然舒服。",

  "zhoujielun_style": "台湾交换生，讲话有节奏，脑子转得比语速还快一点。喜欢轻松的聊天、突然冒出的观点、还有不太尴尬的幽默。看起来松弛，其实很会观察。日常状态：欸？好像蛮有意思的。",

  "wanwan_xiaohe": "小何，台湾来的。喜欢咖啡馆、手写字、慢慢散步和把话讲清楚。不太赶时间，也不太喜欢太吵的场合。日常信念：有些事慢慢说，反而比较接近真实。"
};

function getCharacterIntro(cardId, systemPrompt) {
  // Return cached intro if available
  if (CHARACTER_INTROS[cardId]) {
    return CHARACTER_INTROS[cardId];
  }
  // Fallback: extract description from system prompt (last paragraph)
  const paragraphs = systemPrompt.split("\n\n").filter(p => p.trim());
  const lastPara = paragraphs[paragraphs.length - 1] || "";
  return lastPara.replace(/^你是/, "").trim() || "一个有趣的对话伙伴";
}

async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed");
  }
  return payload;
}

function renderCharacterList() {
  if (!characterList) return;
  const cards = state.characterCards;
  
  if (!cards.length) {
    characterList.innerHTML = `<p class="muted">还没有可用角色卡。</p>`;
    return;
  }

  // Build new HTML
  const newHtml = cards.map((card, index) => {
    const isActive = card.id === state.activeCharacterCardId;
    const voiceType = card?.voice?.voice_type || "";
    const voiceLabel = state.characterVoiceOptions.find(v => v.voice_type === voiceType)?.name || voiceType;
    const initials = getInitials(card.name || card.id);
    const colorIdx = stringToColorIndex(card.name || card.id);
    const colors = CARD_COLOR_PAIRS[colorIdx];
    const avatarStyle = colors 
      ? `background: linear-gradient(135deg, rgb(${colors.bg.join(",")}), rgb(${colors.grad.join(",")})); box-shadow: 0 2px 8px rgba(${colors.bg.join(",")}, 0.25);`
      : "";
    
    // Use generated self-introduction instead of raw prompt
    const intro = getCharacterIntro(card.id, card.system_prompt || "");
    const shortIntro = intro.length > 50 ? intro.slice(0, 50) + "..." : intro;
    
    return `
      <div class="character-list-item ${isActive ? "is-active is-expanded" : ""}" data-card-id="${escapeHtml(card.id)}" data-card-name="${escapeHtml(card.name || card.id)}">
        <div class="character-list-main">
          <div class="character-list-avatar" style="${escapeHtml(avatarStyle)}">${escapeHtml(initials)}</div>
          <div class="character-list-info">
            <div class="character-list-name">${escapeHtml(card.name || card.id)}</div>
            ${voiceLabel ? `<div class="character-list-voice">${escapeHtml(voiceLabel)}</div>` : ""}
            ${shortIntro ? `<div class="character-list-desc">${escapeHtml(shortIntro)}</div>` : ""}
          </div>
          <div class="character-list-actions">
            <button class="character-list-btn select-btn" data-select-card-id="${escapeHtml(card.id)}" title="切换为当前角色">切换</button>
            ${cards.length > 1 ? `<button class="character-list-btn delete" data-delete-card-id="${escapeHtml(card.id)}" data-delete-card-name="${escapeHtml(card.name || card.id)}" title="删除角色">删除</button>` : ""}
          </div>
        </div>
        <div class="character-list-detail">
          <div class="character-list-detail-image" style="${escapeHtml(avatarStyle)}">${escapeHtml(initials)}</div>
          <div class="character-list-detail-desc">${escapeHtml(intro)}</div>
        </div>
      </div>
    `;
  }).join("");

  // Only update if content changed to avoid flicker
  if (characterList.dataset.lastHtml !== newHtml) {
    characterList.dataset.lastHtml = newHtml;
    characterList.innerHTML = newHtml;
  }

  // Update status
  const active = cards.find((card) => card.id === state.activeCharacterCardId) || cards[0];
  if (characterCardStatus) {
    characterCardStatus.textContent = `当前角色卡：${active?.name || active?.id || "未知"}。切换后会重连语音，新的 prompt 与音色立即生效。`;
  }
}

function renderCharacterCards(payload) {
  const cards = Array.isArray(payload?.cards) ? payload.cards : [];
  const voiceOptions = Array.isArray(payload?.voice_options) ? payload.voice_options : [];
  state.characterCards = cards;
  state.activeCharacterCardId = payload?.active_card_id || "";
  state.characterVoiceOptions = voiceOptions;

  // Render character list in memory panel
  renderCharacterList();

  // Update voice select in editor
  if (characterCardVoiceSelect) {
    const options = state.characterVoiceOptions.length
      ? state.characterVoiceOptions
      : [{ name: "默认音色", voice_type: "zh_female_vv_uranus_bigtts", scene: "通用" }];
    characterCardVoiceSelect.innerHTML = options
      .map((option) => {
        const label = `${option.name || option.voice_type} | ${option.voice_type}`;
        return `<option value="${escapeHtml(option.voice_type || "")}">${escapeHtml(label)}</option>`;
      })
      .join("");
  }

  const active = cards.find((card) => card.id === state.activeCharacterCardId) || cards[0];
  if (characterCardVoiceSelect && active?.voice?.voice_type) {
    characterCardVoiceSelect.value = active.voice.voice_type;
  }
}

async function refreshCharacterCards() {
  const payload = await apiRequest("/api/cards");
  renderCharacterCards(payload);
}

async function applyCharacterCardSelection(cardId) {
  const nextCardId = cardId || "";
  if (!nextCardId) {
    return;
  }
  await apiRequest("/api/cards/select", {
    method: "POST",
    body: JSON.stringify({ card_id: nextCardId }),
  });
  await refreshCharacterCards();
  if (state.voiceConnected || state.voiceConnecting) {
    await disconnectVoice({ keepStatus: true });
  }
  if (characterCardStatus) {
    characterCardStatus.textContent = "角色卡已应用。点击 Mic 或 Connect 重新建立语音会话。";
  }
}

async function deleteCharacterCard(cardId, cardName) {
  if (!cardId) return;
  const confirmed = window.confirm(`确定要删除角色「${cardName || cardId}」吗？\n\n此操作不可恢复，角色卡将被永久删除。`);
  if (!confirmed) return;
  
  try {
    await apiRequest("/api/cards/delete", {
      method: "POST",
      body: JSON.stringify({ card_id: cardId }),
    });
    await refreshCharacterCards();
    if (characterCardStatus) {
      characterCardStatus.textContent = `角色「${cardName || cardId}」已删除。`;
    }
  } catch (error) {
    alert(`删除失败：${error.message}`);
    if (characterCardStatus) {
      characterCardStatus.textContent = `删除失败：${error.message}`;
    }
  }
}

function normalizeCardId(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 64);
}

async function saveCharacterCardFromForm() {
  const name = (characterCardNameInput?.value || "").trim();
  const description = (characterCardDescriptionInput?.value || "").trim();
  const voiceType = (characterCardVoiceSelect?.value || "").trim();

  if (!name) {
    characterCardStatus.textContent = "请先填写角色命名。";
    return;
  }
  if (!description) {
    characterCardStatus.textContent = "请先填写角色描述。";
    return;
  }
  if (!voiceType) {
    characterCardStatus.textContent = "请先选择音色。";
    return;
  }

  const cardId = normalizeCardId(name) || `card_${Date.now()}`;
  const generatedPrompt = [
    `你将扮演角色「${name}」。`,
    `角色设定：${description}`,
    "对话目标：让聊天像在和一个真实、稳定、会接话的人说话，而不是在调用模板助手。",
    "回复要求：自然口语、简洁、有生活感；先顺着用户当下的话头回，不要上来总结或分析。",
    "建议策略：只有用户真的在求建议时，再给一个具体判断或下一步；别一开口就是大道理。",
    "边界要求：不说教，不强行建议，不编造记忆，不装成心理咨询师或客服。",
    "提问策略：每轮最多一个问题；如果不问也能成立，那就别硬问。",
  ].join("\n");

  await apiRequest("/api/cards/upsert", {
    method: "POST",
    body: JSON.stringify({
      card: {
        id: cardId,
        name,
        system_prompt: generatedPrompt,
        llm: { model: "" },
        voice: {
          provider: "volcengine",
          voice_type: voiceType,
          resource_id: "seed-tts-1.0",
          model: "",
        },
      },
    }),
  });
  await apiRequest("/api/cards/select", {
    method: "POST",
    body: JSON.stringify({ card_id: cardId }),
  });
  await refreshCharacterCards();
  if (characterCardNameInput) characterCardNameInput.value = "";
  if (characterCardDescriptionInput) characterCardDescriptionInput.value = "";
  if (state.voiceConnected || state.voiceConnecting) {
    await disconnectVoice({ keepStatus: true });
  }
  characterCardStatus.textContent = "角色卡已生成并应用。已自动加入前置说明，点击 Mic 或 Connect 可用新角色对话。";
}

async function applyQuickVoiceSelectionAndReconnect({ connectAfter = true } = {}) {
  if (state.applyingVoiceChoice) {
    return;
  }

  const selectedCardId = (quickVoiceSelect?.value || "").trim();
  if (!selectedCardId) {
    return;
  }

  if (selectedCardId === state.activeCharacterCardId) {
    if (connectAfter && !state.voiceConnected && !state.voiceConnecting && state.voiceAvailable) {
      await connectVoice();
    }
    return;
  }

  state.applyingVoiceChoice = true;
  setMicUi();
  setVoiceStatus("正在应用音色并重连语音...");

  try {
    await apiRequest("/api/cards/select", {
      method: "POST",
      body: JSON.stringify({ card_id: selectedCardId }),
    });

    await refreshCharacterCards();

    if (state.voiceConnected || state.voiceConnecting) {
      await disconnectVoice({ keepStatus: true });
    }

    if (connectAfter && state.voiceAvailable) {
      await connectVoice();
      characterCardStatus.textContent = "已切换到对应角色卡并自动重连语音。";
    } else {
      characterCardStatus.textContent = "已切换到对应角色卡。";
    }
  } finally {
    state.applyingVoiceChoice = false;
    setMicUi();
  }
}

function setToggleUi() {
  toggleOn.classList.toggle("active", state.memoryEnabled);
  toggleOff.classList.toggle("active", !state.memoryEnabled);
  memoryModeLabel.textContent = state.memoryEnabled ? "Memory ON" : "Memory OFF";
  panelModeHint.textContent = state.memoryEnabled
    ? "当前会读写长期记忆"
    : "当前已关闭长期记忆：只看当前聊天，不读写记忆";
  memoryPanel.classList.toggle("is-disabled", !state.memoryEnabled);
}

function setMemoryImportUi() {
  if (!memoryImportPanel) {
    return;
  }

  memoryImportPanel.classList.toggle("is-hidden", !state.memoryImportOpen);
  toggleMemoryImportBtn.textContent = state.memoryImportOpen ? "收起导入区" : "手动导入记忆";
  closeMemoryImportBtn.disabled = state.memoryImportPending;
  submitMemoryImportBtn.disabled = state.memoryImportPending;
  memoryImportInput.disabled = state.memoryImportPending;

  if (!state.memoryImportPending && !memoryImportStatus.textContent.trim()) {
    memoryImportStatus.textContent = "支持一次输入多句，系统会统一抽取并写入。";
  }
}

function renderMessages(messages) {
  state.messages = Array.isArray(messages) ? [...messages] : [];
  if (!state.messages.length) {
    chatStream.innerHTML = `
      <div class="empty-state">
        <p>先点上面的演示按钮，或者自己输入一句话开始。</p>
        <p>推荐先试：“我叫小雨，是一名插画师，住在上海。我喜欢喝拿铁。”</p>
      </div>
    `;
    return;
  }

  chatStream.innerHTML = state.messages
    .map(
      (message) => {
        const content = message.content
          ? escapeHtml(message.content).replace(/\n/g, "<br>")
          : `<span class="typing-dots">正在输入...</span>`;
        return `
        <article class="message ${message.role}">
          <span class="message-role">${message.role === "user" ? "User" : "Assistant"}</span>
          <div>${content}</div>
        </article>
      `;
      }
    )
    .join("");

  chatStream.scrollTop = chatStream.scrollHeight;
}

function messagesEqual(nextMessages) {
  const normalizedNext = Array.isArray(nextMessages) ? nextMessages : [];
  if (normalizedNext.length !== state.messages.length) {
    return false;
  }

  for (let index = 0; index < normalizedNext.length; index += 1) {
    const current = state.messages[index] || {};
    const next = normalizedNext[index] || {};
    if (current.role !== next.role || current.content !== next.content) {
      return false;
    }
  }

  return true;
}

function appendMessage(role, content) {
  renderMessages([...state.messages, { role, content }]);
}

function renderMemoryDeleteButton(item, label) {
  const memoryId = item?.memory_id;
  if (!memoryId) {
    return "";
  }

  const isDeleting = state.deletingMemoryIds.has(memoryId);
  const buttonLabel = isDeleting ? "删除中" : "删除";
  return `
    <button
      class="memory-delete-button"
      type="button"
      data-delete-memory-id="${escapeHtml(memoryId)}"
      data-delete-memory-label="${escapeHtml(label || item.value || item.summary || "这条记忆")}"
      ${isDeleting ? "disabled" : ""}
    >${buttonLabel}</button>
  `;
}

function updateLastAssistantMessage(content) {
  const messages = [...state.messages];
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === "assistant") {
      messages[index] = { ...messages[index], content };
      renderMessages(messages);
      return;
    }
  }
}

function renderTiles(container, items, emptyText) {
  if (!items.length) {
    container.innerHTML = `<p class="muted">${emptyText}</p>`;
    return;
  }

  container.innerHTML = items
    .map(
      (item) => `
        <article class="memory-tile">
          <div class="memory-card-head">
            <p class="memory-label">${escapeHtml(item.label)}</p>
            ${renderMemoryDeleteButton(item, item.label)}
          </div>
          <p class="memory-value">${escapeHtml(item.value || "暂无")}</p>
        </article>
      `
    )
    .join("");
}

function renderTimeline(container, items, emptyText, kind) {
  if (!items.length) {
    container.innerHTML = `<p class="muted">${emptyText}</p>`;
    return;
  }

  container.innerHTML = items
    .map((item) => {
      if (kind === "conflict") {
        return `
          <article class="timeline-item">
            <strong>${escapeHtml(item.slot_key || "slot")}</strong>
            <div>${escapeHtml(item.previous_value || "空")} → ${escapeHtml(item.new_value || "空")}</div>
            <div class="timeline-meta">${escapeHtml(item.resolved_at || "")}</div>
          </article>
        `;
      }
      return `
        <article class="timeline-item">
          <div class="memory-card-head">
            <strong>${escapeHtml(item.summary || "事件")}</strong>
            ${renderMemoryDeleteButton(item, item.summary || "事件")}
          </div>
          <div class="timeline-meta">${escapeHtml(item.updated_at || "")}</div>
          ${
            item.tags?.length
              ? `<div class="tag-row">${item.tags
                  .map((tag) => `<span class="mini-tag">${escapeHtml(tag)}</span>`)
                  .join("")}</div>`
              : ""
          }
        </article>
      `;
    })
    .join("");
}

function renderUpdates(updates) {
  if (!updates.length) {
    updateList.innerHTML = `<p class="muted">还没有新的记忆变化。</p>`;
    return;
  }

  updateList.innerHTML = updates
    .map(
      (item) => {
        const changeTag = item.change_type === "added"
          ? "新增"
          : item.change_type === "deleted"
            ? "删除"
            : "更新";
        const detail = item.change_type === "deleted"
          ? `<strong>${escapeHtml(item.before || item.label || "")}</strong>`
          : `${item.before ? `${escapeHtml(item.before)} → ` : ""}<strong>${escapeHtml(item.after || "")}</strong>`;
        return `
          <article class="spotlight-item">
            <span class="change-tag">${changeTag}</span>
            <div><strong>${escapeHtml(item.label)}</strong></div>
            <div>${detail}</div>
          </article>
        `;
      }
    )
    .join("");
}

function renderMemoryPanel(payload) {
  const panel = payload.memory_panel || {};
  renderTiles(personaGrid, panel.persona || [], "还没有记住用户身份信息。");
  renderTiles(preferenceGrid, panel.preferences || [], "还没有记住用户偏好。");
  renderTimeline(eventTimeline, panel.events || [], "还没有重要事件记忆。", "event");
  renderTimeline(conflictTimeline, panel.conflicts || [], "还没有发生记忆冲突。", "conflict");
  renderUpdates(payload.updates || []);
  memoryPreview.textContent = payload.memory_preview || "本次回答没有使用长期记忆。";

  if (payload.memory_used) {
    memoryUsageBadge.textContent = `本次回答使用了 ${payload.memory_used_count || 0} 条长期记忆`;
  } else {
    memoryUsageBadge.textContent = "当前回答未使用长期记忆";
  }

  // Render companion agent info
  if (payload.companion) {
    const companion = payload.companion;
    const situation = companion.situation || "casual_chat";
    const confidence = companion.situation_confidence || 0;
    const memoryDecision = companion.memory_decision || {};
    const skills = companion.skills_activated || [];

    // Update situation badge
    if (situationBadge) {
      situationBadge.style.display = "flex";
      const situationNames = {
        casual_chat: "闲聊",
        emotional_support: "情绪陪伴",
        planning: "计划",
        music_companion: "音乐",
        learning_coach: "学习",
        coding_helper: "编程",
        memory_query: "记忆查询",
        tool_task: "工具调用",
        safety_sensitive: "安全敏感",
        personal_routine: "日常",
      };
      const situationTextEl = document.getElementById("situationText");
      if (situationTextEl) {
        const name = situationNames[situation] || situation;
        const confPercent = Math.round(confidence * 100);
        situationTextEl.textContent = `${name} (${confPercent}%)`;
      }
    }

    // Update memory decision display in panel
    if (companion.memory_decision) {
      const action = companion.memory_decision.action;
      const reason = companion.memory_decision.reason;
      const requiresConfirmation = companion.memory_decision.requires_confirmation;

      // Add memory decision to updates if not already there
      if (action !== "ignore" && action !== "pending") {
        const decisionUpdate = {
          change_type: action,
          label: "记忆决策",
          after: reason,
        };
        // Only add if not present
        const existingUpdates = payload.updates || [];
        const hasDecision = existingUpdates.some(u => u.label === "记忆决策");
        if (!hasDecision) {
          renderUpdates([...existingUpdates, decisionUpdate]);
        }
      }
    }
  }

  // Render review summary if available
  const reviewSummarySection = document.getElementById("reviewSummarySection");
  const reviewSummaryScope = document.getElementById("reviewSummaryScope");
  const reviewSummaryContent = document.getElementById("reviewSummaryContent");
  if (payload.review_summary && reviewSummarySection) {
    reviewSummarySection.style.display = "block";
    const scopeNames = { day: "今日复盘", week: "本周复盘", phase: "阶段复盘" };
    const scope = payload.review_summary.scope || "";
    const structured = payload.review_summary.structured || {};
    
    if (reviewSummaryScope) {
      reviewSummaryScope.textContent = scopeNames[scope] || "复盘";
    }
    if (reviewSummaryContent) {
      const parts = [];
      if (structured.dominant_emotion) {
        parts.push(`主导情绪: ${structured.dominant_emotion}`);
      }
      if (structured.energy_pattern) {
        parts.push(`能量模式: ${structured.energy_pattern}`);
      }
      if (structured.blockers && structured.blockers.length) {
        parts.push(`卡点: ${structured.blockers.join(", ")}`);
      }
      if (structured.wins && structured.wins.length) {
        parts.push(`小成就: ${structured.wins.join(", ")}`);
      }
      if (structured.next_actions && structured.next_actions.length) {
        parts.push(`下一步: ${structured.next_actions.join("; ")}`);
      }
      if (structured.key_events && structured.key_events.length) {
        parts.push(`关键事件: ${structured.key_events.join("; ")}`);
      }
      reviewSummaryContent.innerHTML = parts.map(p => `<div class="review-summary-item">${escapeHtml(p)}</div>`).join("");
    }
  } else if (reviewSummarySection) {
    reviewSummarySection.style.display = "none";
  }
}

async function refreshState() {
  const payload = await apiRequest("/api/state");
  if (!messagesEqual(payload.messages)) {
    renderMessages(payload.messages || []);
  }
  if (payload.active_card_id) {
    state.activeCharacterCardId = payload.active_card_id;
  }
  renderMemoryPanel(payload);
  setToggleUi();
  setMemoryImportUi();
}

function renderVoiceStatus(payload) {
  state.voiceAvailable = Boolean(payload.available);
  state.voiceClientUrl = payload.client_url || "";
  state.voiceProxyUrl = payload.proxy_client_url || "";

  if (state.voiceAvailable && state.voiceClientUrl) {
    updateVoiceIndicator();
    setMicUi();
    // Auto-connect on first availability
    tryAutoConnectVoice();
    return;
  }

  disconnectVoice({ keepStatus: true }).catch(() => {});
  updateVoiceIndicator();
  setMicUi();
}

async function refreshVoiceStatus() {
  const payload = await apiRequest("/api/voice-status");
  renderVoiceStatus(payload);
}

// ---- Model Selection ----
// Provider SVG icons
const PROVIDER_ICONS = {
  siliconflow: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 17L12 22L22 17" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 12L12 17L22 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  kimi: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 3C7.5 3 4 6.5 4 11C4 15.5 7.5 19 12 19C16.5 19 20 15.5 20 11" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="20" cy="11" r="1.5" fill="currentColor"/></svg>`,
  openai: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2"/><path d="M12 7V12L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`,
};

function getProviderIcon(provider) {
  return PROVIDER_ICONS[provider] || PROVIDER_ICONS.openai;
}

function renderModelSelector() {
  if (!modelSelect) return;
  
  const models = state.availableModels;
  const currentModel = state.currentModel;
  
  if (!models.length) {
    modelSelect.innerHTML = '<option value="">暂无可用模型</option>';
    return;
  }
  
  modelSelect.innerHTML = models.map((model) => {
    const isSelected = model.id === currentModel;
    const isAvailable = model.available;
    const iconSvg = getProviderIcon(model.provider);
    return `<option value="${escapeHtml(model.id)}" ${isSelected ? "selected" : ""} ${!isAvailable ? "disabled" : ""}>
      ${model.name} · ${model.provider_name}
    </option>`;
  }).join("");
  
  // Add custom dropdown with icons
  const wrapper = modelSelect.parentElement;
  let customSelect = wrapper.querySelector('.model-select-custom');
  if (!customSelect) {
    customSelect = document.createElement('div');
    customSelect.className = 'model-select-custom';
    wrapper.appendChild(customSelect);
  }
  
  const currentModelData = models.find(m => m.id === currentModel) || models[0];
  customSelect.innerHTML = `
    <div class="model-select-trigger">
      <span class="model-select-icon">${getProviderIcon(currentModelData?.provider || 'openai')}</span>
      <span class="model-select-text">${escapeHtml(currentModelData?.name || '选择模型')}</span>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
    </div>
    <div class="model-select-dropdown">
      ${models.map((model) => `
        <div class="model-select-option ${model.id === currentModel ? 'is-selected' : ''} ${!model.available ? 'is-disabled' : ''}" data-model-id="${escapeHtml(model.id)}">
          <span class="model-select-icon">${getProviderIcon(model.provider)}</span>
          <span class="model-select-name">${escapeHtml(model.name)}</span>
          <span class="model-select-provider">${escapeHtml(model.provider_name)}</span>
        </div>
      `).join('')}
    </div>
  `;
  
  // Hide native select
  modelSelect.style.display = 'none';
  
  // Add click handlers
  const trigger = customSelect.querySelector('.model-select-trigger');
  const dropdown = customSelect.querySelector('.model-select-dropdown');
  
  trigger.addEventListener('click', () => {
    dropdown.classList.toggle('is-open');
  });
  
  customSelect.querySelectorAll('.model-select-option').forEach((option) => {
    option.addEventListener('click', () => {
      const modelId = option.dataset.modelId;
      if (modelId && !option.classList.contains('is-disabled')) {
        selectModel(modelId);
        dropdown.classList.remove('is-open');
      }
    });
  });
  
  // Close dropdown on outside click
  document.addEventListener('click', (e) => {
    if (!customSelect.contains(e.target)) {
      dropdown.classList.remove('is-open');
    }
  });
}

async function refreshModels() {
  try {
    const payload = await apiRequest("/api/models");
    state.availableModels = payload.models || [];
    state.currentModel = payload.current_model || "";
    renderModelSelector();
  } catch (error) {
    console.error("Failed to load models:", error);
  }
}

async function selectModel(modelId) {
  if (!modelId || modelId === state.currentModel) return;
  
  try {
    const payload = await apiRequest("/api/models/select", {
      method: "POST",
      body: JSON.stringify({ model_id: modelId }),
    });
    state.currentModel = payload.model_id;
    renderModelSelector();
    console.log(`Switched to model: ${payload.name} (${payload.provider})`);
  } catch (error) {
    console.error("Failed to select model:", error);
    alert(`切换模型失败：${error.message}`);
    await refreshModels();
  }
}

function renderRuntimeCardStatus(payload) {
  if (!runtimeCardApplied || !runtimeCardSelected || !runtimeCardSync) {
    return;
  }

  const runtimeCard = payload?.runtime_card || {};
  const activeCard = payload?.active_card || {};

  const runtimeName = runtimeCard.card_name || runtimeCard.card_id || "未上报";
  const runtimeVoice = runtimeCard.voice_type || "-";
  runtimeCardApplied.textContent = `${runtimeName} · ${runtimeVoice}`;

  const activeName = activeCard.card_name || activeCard.card_id || "未知";
  const activeVoice = activeCard.voice_type || "-";
  runtimeCardSelected.textContent = `${activeName} · ${activeVoice}`;

  runtimeCardSync.textContent = payload?.is_runtime_synced ? "已同步" : "未同步（请重连语音）";
}

async function refreshRuntimeCardStatus() {
  const payload = await apiRequest("/api/voice/runtime-card");
  renderRuntimeCardStatus(payload);
}

async function sendMessage(message, options = {}) {
  if (!message || state.pending) {
    return;
  }

  state.pending = true;
  sendBtn.disabled = true;
  state.shouldSpeakReply =
    options.speakReply === undefined
      ? state.speechEnabled && !state.voiceConnected
      : state.speechEnabled && Boolean(options.speakReply);
  if (state.shouldSpeakReply) {
    stopReplyAudio();
  }
  setMicUi();
  setSpeechToggleUi();
  const userMessage = message;
  messageInput.value = "";
  appendMessage("user", userMessage);
  appendMessage("assistant", "");

  try {
    const response = await fetch("/api/chat-stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: userMessage,
        memory_enabled: state.memoryEnabled,
        context_engine_v2: state.contextEngineV2,
        debug: state.showContextTrace,
      }),
    });
    if (!response.ok || !response.body) {
      let errorMessage = "Request failed";
      const rawText = await response.text();
      if (rawText) {
        try {
          const payload = JSON.parse(rawText);
          errorMessage = payload.error || errorMessage;
        } catch (_error) {
          errorMessage = rawText;
        }
      }
      throw new Error(errorMessage);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let assistantContent = "";
    let streamTtsBuffer = "";
    let seenDelta = false;

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.trim()) {
          continue;
        }
        const event = JSON.parse(line);
        if (event.type === "assistant_delta") {
          const deltaText = event.delta || "";
          assistantContent += deltaText;
          updateLastAssistantMessage(assistantContent);
          if (state.shouldSpeakReply && deltaText) {
            seenDelta = true;
            streamTtsBuffer += deltaText;
            const { chunks, rest } = splitSpeakableChunks(streamTtsBuffer, false);
            streamTtsBuffer = rest;
            chunks.forEach((chunk) => enqueueTtsChunk(chunk));
          }
          continue;
        }
        if (event.type === "final") {
          renderMessages(event.payload?.messages || []);
          renderMemoryPanel(event.payload || {});
          if (event.payload?.debug) {
            state.lastContextDebug = event.payload.debug;
            renderContextTrace(event.payload.debug);
          }
          // Render MCP tool results (e.g., playlist with play button)
          if (event.payload?.mcp_tool_results?.length) {
            for (const toolResult of event.payload.mcp_tool_results) {
              if (toolResult.skill === "radio_dj" && toolResult.tool_results?.length) {
                const playlist = toolResult.tool_results[0];
                if (playlist?.tracks) {
                  renderPlaylistPlayer(playlist);
                }
              }
            }
          }
          if (state.shouldSpeakReply) {
            if (seenDelta) {
              const { chunks } = splitSpeakableChunks(streamTtsBuffer, true);
              chunks.forEach((chunk) => enqueueTtsChunk(chunk));
            } else {
              enqueueTtsChunk(event.payload?.reply || "");
            }
          }
          state.shouldSpeakReply = false;
          assistantContent = "";
          streamTtsBuffer = "";
          continue;
        }
        if (event.type === "error") {
          throw new Error(event.error || "Stream failed");
        }
      }
    }

    if (buffer.trim()) {
      const event = JSON.parse(buffer);
      if (event.type === "final") {
        renderMessages(event.payload?.messages || []);
        renderMemoryPanel(event.payload || {});
        if (event.payload?.debug) {
          state.lastContextDebug = event.payload.debug;
          renderContextTrace(event.payload.debug);
        }
        // Render MCP tool results (e.g., playlist with play button)
        if (event.payload?.mcp_tool_results?.length) {
          for (const toolResult of event.payload.mcp_tool_results) {
            if (toolResult.skill === "radio_dj" && toolResult.tool_results?.length) {
              const playlist = toolResult.tool_results[0];
              if (playlist?.tracks) {
                renderPlaylistPlayer(playlist);
              }
            }
          }
        }
        if (state.shouldSpeakReply) {
          enqueueTtsChunk(event.payload?.reply || "");
        }
        state.shouldSpeakReply = false;
      }
    }
  } catch (error) {
    updateLastAssistantMessage(`请求失败：${error.message}`);
    state.shouldSpeakReply = false;
    alert(error.message);
  } finally {
    state.pending = false;
    sendBtn.disabled = false;
    setMicUi();
    setSpeechToggleUi();
    messageInput.focus();
  }
}

async function importMemoryManually() {
  if (state.memoryImportPending) {
    return;
  }

  const content = memoryImportInput.value.trim();
  if (!content) {
    memoryImportStatus.textContent = "请先输入想导入的记忆内容。";
    memoryImportInput.focus();
    return;
  }

  state.memoryImportPending = true;
  memoryImportStatus.textContent = "正在导入长期记忆...";
  setMemoryImportUi();

  try {
    await apiRequest("/api/memory/store", {
      method: "POST",
      body: JSON.stringify({
        role: "user",
        content,
      }),
    });

    memoryImportInput.value = "";
    memoryImportStatus.textContent = "记忆导入完成，右侧看板已更新。";
    await refreshState();
  } catch (error) {
    memoryImportStatus.textContent = `记忆导入失败：${error.message}`;
    throw error;
  } finally {
    state.memoryImportPending = false;
    setMemoryImportUi();
  }
}

async function deleteMemory(memoryId, label) {
  if (!memoryId || state.deletingMemoryIds.has(memoryId)) {
    return;
  }

  const confirmed = window.confirm(`确定要删除这条记忆吗？\n${label || "这条记忆"}`);
  if (!confirmed) {
    return;
  }

  state.deletingMemoryIds.add(memoryId);
  await refreshState().catch(() => {});

  try {
    await apiRequest("/api/memory/delete", {
      method: "POST",
      body: JSON.stringify({ memory_id: memoryId }),
    });
    await refreshState();
  } finally {
    state.deletingMemoryIds.delete(memoryId);
    await refreshState().catch(() => {});
  }
}

sendBtn.addEventListener("click", () => sendMessage(messageInput.value.trim()));

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage(messageInput.value.trim());
  }
});

toggleOn.addEventListener("click", () => {
  state.memoryEnabled = true;
  setToggleUi();
});

toggleOff.addEventListener("click", () => {
  state.memoryEnabled = false;
  setToggleUi();
});

resetSessionBtn.addEventListener("click", async () => {
  try {
    const payload = await apiRequest("/api/reset-session", { method: "POST", body: "{}" });
    renderMessages(payload.messages || []);
    renderMemoryPanel(payload);
  } catch (error) {
    alert(error.message);
  }
});

clearMemoryBtn.addEventListener("click", async () => {
  const confirmed = window.confirm("确定要清空长期记忆和当前会话吗？");
  if (!confirmed) return;
  try {
    const payload = await apiRequest("/api/clear-memory", { method: "POST", body: "{}" });
    renderMessages(payload.messages || []);
    renderMemoryPanel(payload);
  } catch (error) {
    alert(error.message);
  }
});

toggleMemoryImportBtn.addEventListener("click", () => {
  state.memoryImportOpen = !state.memoryImportOpen;
  if (state.memoryImportOpen) {
    memoryImportStatus.textContent = "支持一次输入多句，系统会统一抽取并写入。";
  }
  setMemoryImportUi();
  if (state.memoryImportOpen) {
    window.setTimeout(() => memoryImportInput.focus(), 0);
  }
});

closeMemoryImportBtn.addEventListener("click", () => {
  state.memoryImportOpen = false;
  setMemoryImportUi();
});

submitMemoryImportBtn.addEventListener("click", () => {
  importMemoryManually().catch((error) => {
    alert(error.message);
  });
});

memoryPanel.addEventListener("click", (event) => {
  const button = event.target.closest("[data-delete-memory-id]");
  if (!button) {
    return;
  }

  deleteMemory(
    button.dataset.deleteMemoryId || "",
    button.dataset.deleteMemoryLabel || "这条记忆"
  ).catch((error) => {
    alert(error.message);
  });
});

memoryImportInput.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
    event.preventDefault();
    importMemoryManually().catch((error) => {
      alert(error.message);
    });
  }
});

function renderContextTrace(debug) {
  const panel = document.getElementById("contextTracePanel");
  const body = document.getElementById("contextTraceBody");
  if (!panel || !body) return;

  // Always show panel, even if showContextTrace is false - just show different content
  panel.style.display = "block";

  if (!debug) {
    body.innerHTML = `<p class="muted">等待消息处理完成... 发送消息后将显示链路追踪。</p>`;
    return;
  }

  const trace = debug.trace || [];
  const blocks = debug.blocks || [];
  const tokenSummary = debug.token_summary || {};

  let html = "";

  // === Companion Runtime Brain Architecture ===
  html += `
    <div class="trace-section">
      <div class="trace-section-title">理解链路</div>
      <div class="trace-stat">
        <strong>处理流程：</strong> 状态捕捉 → 策略选择 → 能力调用 → 回复生成
      </div>
    </div>
  `;

  // === Step 1: Detected Signals ===
  const signalStep = trace.find(t => t.step === "Signal Detection");
  if (signalStep && signalStep.data) {
    const signals = signalStep.data;
    html += `
      <div class="trace-section">
        <div class="trace-section-title">它捕捉到什么状态</div>
        <div class="trace-signals">
    `;

    // Mood
    if (signals.mood && signals.mood.active) {
      html += renderSignalBadge("mood", signals.mood.type, signals.mood.confidence);
    }
    // Food
    if (signals.food && signals.food.active) {
      html += renderSignalBadge("food", signals.food.intent, 0.85);
    }
    // Music
    if (signals.music && signals.music.active) {
      html += renderSignalBadge("music", signals.music.intent, 0.85);
    }
    // Outfit
    if (signals.outfit && signals.outfit.active) {
      html += renderSignalBadge("outfit", signals.outfit.intent, 0.85);
    }
    // Campus
    if (signals.campus && signals.campus.active) {
      html += renderSignalBadge("campus", signals.campus.location, 0.8);
    }
    // Robot
    if (signals.robot && signals.robot.active) {
      html += renderSignalBadge("robot", signals.robot.trigger || "explicit", signals.robot.trigger === "implicit" ? 0.6 : 0.85);
    }
    // Easter Eggs
    if (signals.easter_eggs && signals.easter_eggs.length > 0) {
      for (const egg of signals.easter_eggs) {
        html += renderSignalBadge("easter_egg", egg, 0.9);
      }
    }

    html += `</div></div>`;
  }

  // === Step 2: Response Policy ===
  const policyStep = trace.find(t => t.step === "Response Policy");
  if (policyStep && policyStep.data) {
    const p = policyStep.data;
    const forbidden = (p.forbidden_patterns || []).join("、") || "无";
    html += `
      <div class="trace-section">
        <div class="trace-section-title">这轮为什么这样说</div>
        <div class="trace-state">
          <div class="trace-stat"><strong>策略模式：</strong>${escapeHtml(p.mode)}</div>
          <div class="trace-stat"><strong>回复长度：</strong>最多 ${p.max_sentences} 句</div>
          <div class="trace-stat"><strong>温暖度：</strong>${p.warmth}/3 · <strong>幽默度：</strong>${p.humor}/2</div>
          <div class="trace-stat"><strong>避免说：</strong>${escapeHtml(forbidden)}</div>
        </div>
      </div>
    `;
  }

  // === Step 3: Selected Skills ===
  const skillStep = trace.find(t => t.step === "Skill Selection");
  if (skillStep && skillStep.data) {
    html += `
      <div class="trace-section">
        <div class="trace-section-title">这轮用了哪些能力</div>
        <div class="trace-skills">
    `;
    for (const skill of skillStep.data) {
      const modeLabel = skill.mode === "primary" ? "主要" :
                        skill.mode === "support" ? "辅助" : "背景";
      const modeColor = skill.mode === "primary" ? "var(--accent-warm)" :
                        skill.mode === "support" ? "var(--info)" : "var(--text-muted)";
      html += `
        <div class="trace-skill-card">
          <div class="trace-skill-header">
            <span class="trace-skill-name">${escapeHtml(skill.name)}</span>
            <span class="trace-skill-mode" style="color: ${modeColor}">${escapeHtml(modeLabel)}</span>
          </div>
          <div class="trace-skill-meta">
            ${escapeHtml(skill.category)} · 匹配度 ${Math.round(skill.score * 100)}%
          </div>
        </div>
      `;
    }
    html += `</div></div>`;
  }

  // === Step 4: History Window ===
  const historyStep = trace.find(t => t.step === "History Window");
  if (historyStep && historyStep.data) {
    html += `
      <div class="trace-section">
        <div class="trace-section-title">参考了最近对话</div>
        <div class="trace-stat">使用了最近 ${historyStep.data.length} 条消息作为上下文</div>
      </div>
    `;
  }

  // === Step 5: Token Budget ===
  html += `
    <div class="trace-section">
      <div class="trace-section-title">上下文用量</div>
      <div class="trace-stat">
        已用 ${tokenSummary.used_tokens || 0} / ${tokenSummary.max_input_tokens || 9000} tokens
      </div>
      <div class="trace-stat">
        因容量限制移除了 ${(tokenSummary.removed_blocks || []).length} 个上下文块
      </div>
    </div>
  `;

  body.innerHTML = html;
}

function renderSignalBadge(type, label, confidence) {
  const confidencePercent = Math.round((confidence || 0) * 100);
  const typeColors = {
    mood: "#c67d5e",
    food: "#8aaa8c",
    music: "#7a9ab0",
    outfit: "#c99a4e",
    campus: "#b08d6a",
    robot: "#a080a0",
    easter_egg: "#e07070"
  };
  const color = typeColors[type] || "#888";

  return `
    <div class="trace-signal-badge" style="border-color: ${color}; background: ${color}12;">
      <span class="trace-signal-type" style="color: ${color}">${escapeHtml(type)}</span>
      <span class="trace-signal-label">${escapeHtml(label)}</span>
      <span class="trace-signal-confidence">${confidencePercent}%</span>
    </div>
  `;
}

// Context Engine toggles
const contextEngineV2Toggle = document.getElementById("contextEngineV2Toggle");
const showContextTraceToggle = document.getElementById("showContextTraceToggle");

contextEngineV2Toggle?.addEventListener("change", (e) => {
  state.contextEngineV2 = e.target.checked;
});

showContextTraceToggle?.addEventListener("change", (e) => {
  state.showContextTrace = e.target.checked;
  if (!state.showContextTrace) {
    const panel = document.getElementById("contextTracePanel");
    if (panel) panel.style.display = "none";
  } else if (state.lastContextDebug) {
    renderContextTrace(state.lastContextDebug);
  }
});

document.querySelectorAll(".demo-chip").forEach((button) => {
  button.addEventListener("click", async () => {
    const mode = button.dataset.mode;
    const text = button.dataset.text || "";
    try {
      if (mode === "resetThenSend") {
        const payload = await apiRequest("/api/reset-session", { method: "POST", body: "{}" });
        renderMessages(payload.messages || []);
        renderMemoryPanel(payload);
      }
      await sendMessage(text);
    } catch (error) {
      alert(error.message);
    }
  });
});

micBtn.addEventListener("click", async () => {
  if (!state.voiceAvailable) {
    return;
  }

  try {
    if (!state.voiceConnected) {
      await connectVoice();
      setLocalMicEnabled(true);
    } else {
      setLocalMicEnabled(!state.micEnabled);
    }
    setMicUi();
  } catch (error) {
    console.error("Voice connection failed:", error);
  }
});

speechToggleBtn?.addEventListener("click", () => {
  state.speechEnabled = !state.speechEnabled;
  persistSpeechEnabledPreference(state.speechEnabled);
  if (!state.speechEnabled) {
    stopReplyAudio();
  }
  setSpeechToggleUi();
});

// Auto-connect voice when service is available
let autoConnectAttempted = false;

async function tryAutoConnectVoice() {
  if (autoConnectAttempted || !state.voiceAvailable || state.voiceConnected || state.voiceConnecting) {
    return;
  }
  autoConnectAttempted = true;
  try {
    await connectVoice();
    setLocalMicEnabled(true);
  } catch (error) {
    console.error("Auto-connect voice failed:", error);
    autoConnectAttempted = false;
  }
}

// Character list event delegation
characterList?.addEventListener("click", (event) => {
  const selectBtn = event.target.closest("[data-select-card-id]");
  if (selectBtn) {
    const cardId = selectBtn.dataset.selectCardId;
    const cardName = selectBtn.closest(".character-list-item")?.dataset.cardName;
    applyCharacterCardSelection(cardId).catch((error) => {
      if (characterCardStatus) {
        characterCardStatus.textContent = `应用失败：${error.message}`;
      }
    });
    return;
  }

  const deleteBtn = event.target.closest("[data-delete-card-id]");
  if (deleteBtn) {
    const cardId = deleteBtn.dataset.deleteCardId;
    const cardName = deleteBtn.dataset.deleteCardName;
    deleteCharacterCard(cardId, cardName);
    return;
  }

  // Click on the item itself to toggle expand/collapse
  const item = event.target.closest(".character-list-item");
  if (item && !event.target.closest(".character-list-actions")) {
    const cardId = item.dataset.cardId;
    const isActive = cardId === state.activeCharacterCardId;

    // Double-click to switch character (only for non-active items)
    if (item.dataset.clickCount === "1" && !isActive) {
      // This is a double-click
      clearTimeout(item.dataset.clickTimer);
      item.dataset.clickCount = "0";
      applyCharacterCardSelection(cardId).catch((error) => {
        if (characterCardStatus) {
          characterCardStatus.textContent = `应用失败：${error.message}`;
        }
      });
      return;
    }

    // Single-click: expand/collapse
    item.dataset.clickCount = "1";
    item.dataset.clickTimer = setTimeout(() => {
      item.dataset.clickCount = "0";
      const isExpanded = item.classList.contains("is-expanded");
      // Collapse all other items
      document.querySelectorAll(".character-list-item.is-expanded").forEach((el) => {
        if (el !== item) el.classList.remove("is-expanded");
      });
      // Toggle current
      item.classList.toggle("is-expanded", !isExpanded);
    }, 250);
    return;
  }
});

saveCharacterCardBtn?.addEventListener("click", () => {
  saveCharacterCardFromForm().catch((error) => {
    characterCardStatus.textContent = `导入失败：${error.message}`;
  });
});

// Model selector
modelSelect?.addEventListener("change", (event) => {
  const modelId = event.target.value;
  if (modelId) {
    selectModel(modelId);
  }
});

// Character card preview live update
characterCardNameInput?.addEventListener("input", updateCharacterCardPreview);
characterCardDescriptionInput?.addEventListener("input", updateCharacterCardPreview);
characterCardVoiceSelect?.addEventListener("change", updateCharacterCardPreview);
downloadCardBtn?.addEventListener("click", downloadCharacterCard);

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

// ---- MCP Tool Result Rendering ----
function renderPlaylistPlayer(playlist) {
  if (!playlist || !playlist.tracks) return;

  const container = document.createElement("div");
  container.className = "playlist-player";

  let html = `
    <div class="playlist-header">
      <div class="playlist-icon">🎵</div>
      <div class="playlist-info">
        <div class="playlist-name">${escapeHtml(playlist.playlist_name || "歌单")}</div>
        <div class="playlist-intro">${escapeHtml(playlist.dj_intro || "为你推荐")}</div>
      </div>
    </div>
    <div class="playlist-tracks">
  `;

  for (const track of playlist.tracks) {
    html += `
      <div class="playlist-track" data-artist="${escapeHtml(track.artist)}" data-title="${escapeHtml(track.title)}">
        <div class="track-info">
          <div class="track-title">${escapeHtml(track.title)}</div>
          <div class="track-artist">${escapeHtml(track.artist)} · ${escapeHtml(track.duration || "")}</div>
        </div>
        <button class="track-play-btn" onclick="playTrack('${escapeHtml(track.artist)}', '${escapeHtml(track.title)}')">
          ▶
        </button>
      </div>
    `;
  }

  html += `</div>`;
  container.innerHTML = html;

  // Insert after the last assistant message
  const lastAssistantMsg = chatStream.querySelector(".message.assistant:last-child");
  if (lastAssistantMsg) {
    lastAssistantMsg.appendChild(container);
  } else {
    chatStream.appendChild(container);
  }
}

// Global function for play button
window.playTrack = function(artist, title) {
  // For demo purposes, show a toast notification instead of actual playback
  showToast(`正在播放: ${artist} - ${title}`);
};

function showToast(message) {
  const toast = document.createElement("div");
  toast.className = "toast-notification";
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.classList.add("show");
  }, 10);
  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => {
      document.body.removeChild(toast);
    }, 300);
  }, 3000);
}

refreshState().catch((error) => {
  alert(error.message);
});
refreshCharacterCards().catch((error) => {
  characterCardStatus.textContent = `角色卡加载失败：${error.message}`;
});
refreshRuntimeCardStatus().catch(() => {});

refreshVoiceStatus().catch(() => {
  setMicUi();
});
refreshModels().catch(() => {});
state.speechEnabled = loadSpeechEnabledPreference();
updateVoiceIndicator();
setMemoryImportUi();
setSpeechToggleUi();
updateCharacterCardPreview();

// Cleanup voice connection on page unload to prevent ghost sessions
window.addEventListener("beforeunload", () => {
  disconnectVoice({ keepStatus: true }).catch(() => {});
});

window.setInterval(() => {
  if (!state.pending) {
    refreshState().catch(() => {});
  }
}, 1200);

// ---- SSE for real-time memory updates ----
function connectEventSource() {
  const evtSource = new EventSource("/api/events");
  evtSource.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      if (payload.type === "memory_updates") {
        renderMemoryPanel({
          memory_panel: payload.data.memory_panel,
          updates: payload.data.updates,
          memory_preview: "记忆已实时更新",
          memory_used: true,
          memory_used_count: payload.data.updates.length,
        });
      }
    } catch (_error) {
      // Ignore parse errors
    }
  };
  evtSource.onerror = () => {
    // Reconnect after a delay
    setTimeout(connectEventSource, 3000);
  };
}
connectEventSource();

window.setInterval(() => {
  refreshCharacterCards().catch(() => {});
}, 60000);

window.setInterval(() => {
  refreshVoiceStatus().catch(() => {});
}, 10000);

window.setInterval(() => {
  refreshRuntimeCardStatus().catch(() => {});
}, 3000);
