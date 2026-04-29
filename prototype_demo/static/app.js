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
  characterCards: [],
  activeCharacterCardId: "",
  characterVoiceOptions: [],
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
const voiceInlineStatus = document.getElementById("voiceInlineStatus");
const voiceInlineFrameShell = document.getElementById("voiceInlineFrameShell");
const connectVoiceBtn = document.getElementById("connectVoiceBtn");
const disconnectVoiceBtn = document.getElementById("disconnectVoiceBtn");
const refreshVoiceBtn = document.getElementById("refreshVoiceBtn");
const voiceServicePill = document.getElementById("voiceServicePill");
const voiceSessionPill = document.getElementById("voiceSessionPill");
const voiceRemoteAudio = document.getElementById("voiceRemoteAudio");
const micBtn = document.getElementById("micBtn");
const speechToggleBtn = document.getElementById("speechToggleBtn");
const voiceInlineHint = document.getElementById("voiceInlineHint");
const characterCardSelect = document.getElementById("characterCardSelect");
const applyCharacterCardBtn = document.getElementById("applyCharacterCardBtn");
const characterCardStatus = document.getElementById("characterCardStatus");
const characterList = document.getElementById("characterList");
const characterCardNameInput = document.getElementById("characterCardNameInput");
const characterCardDescriptionInput = document.getElementById("characterCardDescriptionInput");
const characterCardVoiceSelect = document.getElementById("characterCardVoiceSelect");
const saveCharacterCardBtn = document.getElementById("saveCharacterCardBtn");

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

function updateVoicePills() {
  voiceServicePill.textContent = state.voiceAvailable ? "Service online" : "Service offline";
  voiceServicePill.className = `voice-pill ${state.voiceAvailable ? "is-online" : "is-offline"}`;

  let sessionLabel = "Session idle";
  let sessionClass = "";
  if (state.voiceConnecting) {
    sessionLabel = "Connecting";
    sessionClass = "is-busy";
  } else if (state.voiceConnected) {
    sessionLabel = "Connected";
    sessionClass = "is-online";
  } else if (state.voiceSessionId) {
    sessionLabel = "Session created";
    sessionClass = "is-busy";
  }
  voiceSessionPill.textContent = sessionLabel;
  voiceSessionPill.className = `voice-pill ${sessionClass}`.trim();
}

function setVoiceStatus(message) {
  voiceInlineStatus.textContent = message;
}

function resetVoiceState() {
  state.voiceConnecting = false;
  state.voiceConnected = false;
  state.voiceSessionId = "";
  state.voicePcId = "";
  updateVoicePills();
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
    voiceRemoteAudio.play().catch(() => {});
  });

  pc.addEventListener("connectionstatechange", () => {
    const stateName = pc.connectionState;
    if (stateName === "connected") {
      state.voiceConnecting = false;
      state.voiceConnected = true;
      updateVoicePills();
      setVoiceStatus("语音已连接。现在可以直接说话，实时转写会同步到聊天流。");
      voiceInlineHint.textContent = "语音已连接。直接说话即可；再次点 Disconnect 可断开。";
      return;
    }
    if (stateName === "connecting") {
      setVoiceStatus("正在建立语音连接...");
      return;
    }
    if (stateName === "failed" || stateName === "disconnected" || stateName === "closed") {
      disconnectVoice({ keepStatus: stateName === "closed" }).catch(() => {});
      if (stateName !== "closed") {
        setVoiceStatus(`语音连接已${stateName === "failed" ? "失败" : "断开"}。`);
      }
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
  speechToggleBtn.textContent = state.speechEnabled ? "语音播报：开" : "语音播报：关";
  speechToggleBtn.classList.toggle("is-active", state.speechEnabled);
  speechToggleBtn.disabled = state.pending;
}

function setMicUi() {
  if (!micBtn) {
    return;
  }

  micBtn.classList.toggle("is-listening", state.voiceConnecting || state.voiceConnected);
  micBtn.disabled = state.pending || state.applyingVoiceChoice || !state.voiceAvailable || state.voiceConnecting;

  if (state.voiceConnecting) {
    micBtn.textContent = "连接中";
  } else if (state.voiceConnected) {
    micBtn.textContent = state.micEnabled ? "关麦" : "开麦";
  } else {
    micBtn.textContent = "开麦";
  }

  if (quickVoiceSelect) {
    quickVoiceSelect.disabled = state.pending || state.applyingVoiceChoice;
  }

  connectVoiceBtn.disabled = !state.voiceAvailable || state.voiceConnecting || state.voiceConnected;
  disconnectVoiceBtn.disabled = !state.voiceConnected && !state.voiceConnecting;

  if (state.voiceAvailable) {
    voiceInlineHint.textContent =
      state.voiceConnected
        ? "语音已连接。直接说话即可；回复会语音播报，转写会同步进聊天流。"
        : "实时语音已在线。点击 Mic 或 Connect 建立连接。";
    return;
  }

  voiceInlineHint.textContent =
    "实时语音服务当前离线。先在 quickstart 根目录运行 prototype_demo/voice_bot.py，再刷新页面。";
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
  const punctuation = /[。！？!?；;：:\n]/;

  for (let index = 0; index < text.length; index += 1) {
    if (!punctuation.test(text[index])) {
      continue;
    }
    const sentence = text.slice(cursor, index + 1).trim();
    if (sentence) {
      chunks.push(sentence);
    }
    cursor = index + 1;
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
  if (!state.voiceAvailable || state.voiceConnecting || state.voiceConnected) {
    return;
  }

  state.voiceConnecting = true;
  updateVoicePills();
  setMicUi();
  setVoiceStatus("正在请求麦克风权限...");

  try {
    localVoiceRawStream = await requestMicrophonePermission();
    localVoiceStream = createProcessedVoiceStream(localVoiceRawStream);
    setLocalMicEnabled(true);
    const session = await createVoiceSession();
    state.voiceSessionId = session.sessionId || "";
    updateVoicePills();

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
    voiceInlineHint.textContent = `语音连接失败：${error.message}`;
  } finally {
    state.voiceConnecting = false;
    updateVoicePills();
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
  setMicUi();
  if (!options.keepStatus) {
    setVoiceStatus("语音已断开。重新点击 Connect 或 Mic 可再次连接。");
  }
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
    const desc = card.system_prompt || "";
    // Extract description part after the role name
    const descLines = desc.split("\n").filter(l => l.trim());
    const shortDesc = descLines.length > 1 ? descLines[1].replace("角色设定：", "").trim() : "";
    const fullDesc = descLines.slice(1).join("\n").trim() || "暂无详细描述";
    
    return `
      <div class="character-list-item ${isActive ? "is-active" : ""}" data-card-id="${escapeHtml(card.id)}" data-card-name="${escapeHtml(card.name || card.id)}">
        <div class="character-list-main">
          <div class="character-list-avatar" style="${escapeHtml(avatarStyle)}">${escapeHtml(initials)}</div>
          <div class="character-list-info">
            <div class="character-list-name">${escapeHtml(card.name || card.id)}</div>
            ${voiceLabel ? `<div class="character-list-voice">${escapeHtml(voiceLabel)}</div>` : ""}
            ${shortDesc ? `<div class="character-list-desc">${escapeHtml(shortDesc)}</div>` : ""}
          </div>
          <div class="character-list-actions">
            <button class="character-list-btn select-btn" data-select-card-id="${escapeHtml(card.id)}" title="切换为当前角色">切换</button>
            ${cards.length > 1 ? `<button class="character-list-btn delete" data-delete-card-id="${escapeHtml(card.id)}" data-delete-card-name="${escapeHtml(card.name || card.id)}" title="删除角色">删除</button>` : ""}
          </div>
        </div>
        <div class="character-list-detail">
          <div class="character-list-detail-image" style="${escapeHtml(avatarStyle)}">${escapeHtml(initials)}</div>
          <div class="character-list-detail-desc">${escapeHtml(fullDesc).replace(/\n/g, "<br>")}</div>
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
    "对话目标：优先提升陪伴感与可持续聊天体验，让用户愿意继续聊下去。",
    "回复要求：自然口语、简洁有温度，先接住情绪或话头，再补充一个可延展点。",
    "边界要求：不说教，不强行建议，不编造记忆；未被请求时避免长篇步骤化输出。",
    "提问策略：每轮最多一个问题，优先使用开放式、轻压力追问。",
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
    setVoiceStatus(
      state.voiceConnected
        ? "语音已连接。直接说话即可；实时转写和语音回复都会同步工作。"
        : "realtime voice 服务已在线。点击 Connect 或 Mic 建立语音连接。"
    );
    updateVoicePills();
    setMicUi();
    return;
  }

  disconnectVoice({ keepStatus: true }).catch(() => {});
  setVoiceStatus(
    `realtime voice 服务离线。${payload.run_hint || "先启动 prototype_demo/voice_bot.py。"}`
      .trim()
  );
  updateVoicePills();
  setMicUi();
}

async function refreshVoiceStatus() {
  const payload = await apiRequest("/api/voice-status");
  renderVoiceStatus(payload);
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
    voiceInlineHint.textContent = "实时语音服务当前不可用。";
    return;
  }

  try {
    if (!state.voiceConnected) {
      await connectVoice();
      setLocalMicEnabled(true);
      setVoiceStatus("语音已连接，麦克风已开启。");
    } else {
      setLocalMicEnabled(!state.micEnabled);
      setVoiceStatus(state.micEnabled ? "麦克风已开启。" : "麦克风已关闭（语音连接保持）。");
    }
    setMicUi();
  } catch (error) {
    setVoiceStatus(`语音连接失败：${error.message}`);
    voiceInlineHint.textContent = `语音连接失败：${error.message}`;
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

connectVoiceBtn.addEventListener("click", () => {
  connectVoice().catch(() => {});
});

disconnectVoiceBtn.addEventListener("click", () => {
  disconnectVoice().catch(() => {});
});

refreshVoiceBtn.addEventListener("click", () => {
  refreshVoiceStatus().catch(() => {
    voiceInlineStatus.textContent = "语音状态刷新失败。请稍后再试。";
  });
});

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
    const isExpanded = item.classList.contains("is-expanded");
    // Collapse all other items
    document.querySelectorAll(".character-list-item.is-expanded").forEach((el) => {
      if (el !== item) el.classList.remove("is-expanded");
    });
    // Toggle current
    item.classList.toggle("is-expanded", !isExpanded);
    return;
  }
});

saveCharacterCardBtn?.addEventListener("click", () => {
  saveCharacterCardFromForm().catch((error) => {
    characterCardStatus.textContent = `导入失败：${error.message}`;
  });
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
state.speechEnabled = loadSpeechEnabledPreference();
updateVoicePills();
setMemoryImportUi();
setSpeechToggleUi();
updateCharacterCardPreview();

window.setInterval(() => {
  if (!state.pending) {
    refreshState().catch(() => {});
  }
}, 1200);

window.setInterval(() => {
  refreshCharacterCards().catch(() => {});
}, 60000);

window.setInterval(() => {
  refreshVoiceStatus().catch(() => {});
}, 10000);

window.setInterval(() => {
  refreshRuntimeCardStatus().catch(() => {});
}, 3000);
