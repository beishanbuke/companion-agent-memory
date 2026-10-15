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
  inspectorTab: "route",
  lastCompanionDebug: null,
  mcpCards: [],
  horoscopeCard: null,
  tarotDraw: null,
  calendarDays: {},
  calendarAnalysis: "",
  calendarAnalysisDate: "",
  calendarSeries: [],
  moodForecast: [],
  tarotHistory: [],
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
const emotionBadge = document.getElementById("emotionBadge");
const emotionText = document.getElementById("emotionText");
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
const fortuneCard = document.getElementById("fortuneCard");
const fortuneModalOverlay = document.getElementById("fortuneModalOverlay");
const fortuneModalClose = document.getElementById("fortuneModalClose");
const fortuneModalBody = document.getElementById("fortuneModalBody");
const tarotSingleBtn = document.getElementById("tarotSingleBtn");
const tarotThreeBtn = document.getElementById("tarotThreeBtn");
const tarotStatus = document.getElementById("tarotStatus");
const tarotDraw = document.getElementById("tarotDraw");
const tarotModalOverlay = document.getElementById("tarotModalOverlay");
const tarotModalClose = document.getElementById("tarotModalClose");
const tarotModalBody = document.getElementById("tarotModalBody");
const calendarAnalyzeBtn = document.getElementById("calendarAnalyzeBtn");
const calendarGrid = document.getElementById("calendarGrid");
const calendarDetail = document.getElementById("calendarDetail");
const calendarAnalysis = document.getElementById("calendarAnalysis");
const moodTrendCanvas = document.getElementById("moodTrendCanvas");
const tarotJournal = document.getElementById("tarotJournal");
const eventTimeline = document.getElementById("eventTimeline");
const conflictTimeline = document.getElementById("conflictTimeline");
const memoryPreview = document.getElementById("memoryPreview");
const routeInspectorTab = document.getElementById("routeInspectorTab");
const lifecycleInspectorTab = document.getElementById("lifecycleInspectorTab");
const routeInspectorPanel = document.getElementById("routeInspectorPanel");
const lifecycleInspectorPanel = document.getElementById("lifecycleInspectorPanel");
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
const quickVoiceSelect = document.getElementById("quickVoiceSelect");
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
// 流式 TTS：文本直灌火山双向 TTS（无切句），音频连续播放
let ttsWs = null;
let ttsWsOpen = false;
let ttsAudioCtx = null;
let ttsNextPlayTime = 0;
let ttsActiveSources = [];
let ttsStreamSessionOpen = false;
let ttsStreamSentLen = 0;

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

function ensureTtsStream() {
  if (ttsWs && (ttsWs.readyState === WebSocket.OPEN || ttsWs.readyState === WebSocket.CONNECTING)) {
    return;
  }
  try {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    ttsWs = new WebSocket(`${proto}://${window.location.host}/api/tts-ws`);
    ttsWs.binaryType = "arraybuffer";
    ttsWs.onopen = () => {
      ttsWsOpen = true;
    };
    ttsWs.onclose = () => {
      ttsWsOpen = false;
      ttsWs = null;
      ttsStreamSessionOpen = false;
    };
    ttsWs.onerror = () => {
      ttsWsOpen = false;
    };
    ttsWs.onmessage = (ev) => {
      if (typeof ev.data === "string") {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.event === "session") {
            ttsStreamSessionOpen = true;
          } else if (msg.event === "finished") {
            ttsStreamSessionOpen = false;
          } else if (msg.event === "error") {
            console.error("tts stream:", msg.message);
          }
        } catch (_e) {}
        return;
      }
      scheduleTtsPcm(ev.data);
    };
  } catch (_e) {
    ttsWs = null;
  }
}

function ttsStreamReady() {
  return ttsWsOpen && ttsWs && ttsWs.readyState === WebSocket.OPEN;
}

function sendTtsStream(cmd) {
  if (!ttsStreamReady()) {
    return false;
  }
  try {
    ttsWs.send(JSON.stringify(cmd));
    return true;
  } catch (_e) {
    return false;
  }
}

function ensureTtsAudioCtx() {
  if (!ttsAudioCtx) {
    const Ctor = window.AudioContext || window.webkitAudioContext;
    ttsAudioCtx = new Ctor();
  }
  if (ttsAudioCtx.state === "suspended") {
    ttsAudioCtx.resume().catch(() => {});
  }
  return ttsAudioCtx;
}

function scheduleTtsPcm(buf) {
  try {
    const ctx = ensureTtsAudioCtx();
    const samples = new Int16Array(buf);
    const f32 = new Float32Array(samples.length);
    for (let i = 0; i < samples.length; i += 1) {
      f32[i] = samples[i] / 32768;
    }
    const audioBuffer = ctx.createBuffer(1, f32.length, 24000);
    audioBuffer.getChannelData(0).set(f32);
    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);
    const now = ctx.currentTime;
    if (ttsNextPlayTime < now) {
      ttsNextPlayTime = now;
    }
    source.start(ttsNextPlayTime);
    ttsNextPlayTime += audioBuffer.duration;
    ttsActiveSources.push(source);
    source.onended = () => {
      const idx = ttsActiveSources.indexOf(source);
      if (idx >= 0) {
        ttsActiveSources.splice(idx, 1);
      }
    };
  } catch (err) {
    console.error("scheduleTtsPcm failed:", err);
  }
}

function cancelScheduledTtsAudio() {
  ttsNextPlayTime = 0;
  ttsActiveSources.forEach((s) => {
    try {
      s.stop();
    } catch (_e) {}
  });
  ttsActiveSources = [];
}

function stopReplyAudio() {
  cancelScheduledTtsAudio();
  if (ttsStreamSessionOpen) {
    sendTtsStream({ type: "finish" });
    ttsStreamSessionOpen = false;
  }
  ttsStreamSentLen = 0;
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

async function speakReply(text, prefetchedAudio) {
  if (!text) {
    return;
  }

  try {
    const audioBlob = prefetchedAudio ? await prefetchedAudio : await synthesizeReplyAudio(text);
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
  // 只在主要句读处切句：火山 bidirection v3 会自行整理句子边界（见官方接入文档），
  // 分号/冒号等次要标点交给引擎处理， Prosody 更自然、情绪更饱满。
  const punctuation = /[。！？!?\n]/;

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
  let prefetched = null;
  try {
    while (ttsChunkQueue.length) {
      const chunk = ttsChunkQueue.shift();
      if (!chunk) {
        continue;
      }
      // 预取下一句：当前句播放期间并行请求下一句的合成，消除句间 1s 停顿
      const audioPromise =
        prefetched && prefetched.text === chunk
          ? prefetched.promise
          : synthesizeReplyAudio(chunk);
      const nextText = ttsChunkQueue.find((item) => item && item.trim());
      prefetched = nextText ? { text: nextText, promise: synthesizeReplyAudio(nextText) } : null;
      await speakReply(chunk, audioPromise);
    }
  } finally {
    ttsChunkPlaying = false;
    prefetched = null;
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

  characterList.innerHTML = cards.map((card, index) => {
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
    
    return `
      <div class="character-list-item ${isActive ? "is-active" : ""}" data-card-id="${escapeHtml(card.id)}" data-card-name="${escapeHtml(card.name || card.id)}" style="animation: msg-in 200ms ease ${index * 40}ms both;">
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
    `;
  }).join("");

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
          resource_id: "",
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

async function setMemoryEnabled(enabled) {
  const previous = state.memoryEnabled;
  state.memoryEnabled = enabled;
  setToggleUi();

  try {
    const payload = await apiRequest("/api/memory-mode", {
      method: "POST",
      body: JSON.stringify({ memory_enabled: enabled }),
    });
    if (typeof payload.memory_enabled === "boolean") {
      state.memoryEnabled = payload.memory_enabled;
    }
    renderMemoryPanel(payload);
    setToggleUi();
  } catch (error) {
    state.memoryEnabled = previous;
    setToggleUi();
    alert(`切换记忆模式失败：${error.message}`);
  }
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

function percent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round(numeric * 100)));
}

function inspectorBadge(label, variant = "") {
  const className = variant ? `inspector-badge ${variant}` : "inspector-badge";
  return `<span class="${className}">${escapeHtml(label)}</span>`;
}

function renderScoreBar(label, value) {
  const score = percent(value);
  return `
    <div class="inspector-score-row">
      <div class="inspector-score-meta">
        <span>${escapeHtml(label)}</span>
        <span>${score}%</span>
      </div>
      <div class="inspector-score-track">
        <span class="inspector-score-fill" style="width: ${score}%"></span>
      </div>
    </div>
  `;
}

function renderRouteInspector(companion) {
  if (!routeInspectorPanel) {
    return;
  }
  const route = companion?.memory_route;
  if (!route) {
    routeInspectorPanel.innerHTML = `<p class="muted">发送一条消息后，会显示 Memory Router v2 的路由决策。</p>`;
    return;
  }

  const confidence = percent(route.confidence);
  const tiers = Array.isArray(route.tiers) ? route.tiers : [];
  const signals = Array.isArray(route.signals) ? route.signals : [];
  const tierScores = route.tier_scores && typeof route.tier_scores === "object"
    ? Object.entries(route.tier_scores)
    : [];
  const maxPerTier = route.max_per_tier && typeof route.max_per_tier === "object"
    ? Object.entries(route.max_per_tier)
    : [];
  const verifier = companion?.memory_use_verifier || null;

  routeInspectorPanel.innerHTML = `
    <div class="inspector-summary-grid">
      <article class="inspector-summary-card">
        <span class="inspector-label">Need Memory</span>
        <strong>${route.need_memory ? "Yes" : "No"}</strong>
      </article>
      <article class="inspector-summary-card">
        <span class="inspector-label">Mode</span>
        <strong>${escapeHtml(route.retrieval_mode || "none")}</strong>
      </article>
      <article class="inspector-summary-card">
        <span class="inspector-label">Mention</span>
        <strong>${escapeHtml(route.mention_policy || "forbid")}</strong>
      </article>
      <article class="inspector-summary-card">
        <span class="inspector-label">Budget</span>
        <strong>${Number(route.max_items || 0)}</strong>
      </article>
    </div>

    <div class="inspector-meter">
      <div class="inspector-score-meta">
        <span>Route Confidence</span>
        <span>${confidence}%</span>
      </div>
      <div class="inspector-score-track">
        <span class="inspector-score-fill" style="width: ${confidence}%"></span>
      </div>
    </div>

    <div class="inspector-block">
      <span class="inspector-label">Reason</span>
      <p class="inspector-copy">${escapeHtml(route.reason || "无")}</p>
    </div>

    <div class="inspector-block">
      <span class="inspector-label">Signals</span>
      <div class="inspector-chip-row">
        ${signals.length ? signals.map((signal) => inspectorBadge(signal, "info")).join("") : inspectorBadge("none")}
      </div>
    </div>

    <div class="inspector-block">
      <span class="inspector-label">Selected Tiers</span>
      <div class="inspector-chip-row">
        ${tiers.length ? tiers.map((tier) => inspectorBadge(tier, "active")).join("") : inspectorBadge("none")}
      </div>
    </div>

    <div class="inspector-block">
      <span class="inspector-label">Tier Scores</span>
      <div class="inspector-score-list">
        ${tierScores.length ? tierScores.map(([tier, score]) => renderScoreBar(tier, score)).join("") : `<p class="muted">没有 tier score。</p>`}
      </div>
    </div>

    <div class="inspector-block">
      <span class="inspector-label">Per-tier Budget</span>
      <div class="inspector-chip-row">
        ${maxPerTier.length ? maxPerTier.map(([tier, limit]) => inspectorBadge(`${tier}: ${limit}`)).join("") : inspectorBadge("none")}
      </div>
    </div>

    <div class="inspector-block">
      <span class="inspector-label">Memory Use Verifier</span>
      ${
        verifier
          ? `
            <div class="inspector-chip-row">
              ${inspectorBadge(verifier.status || "unknown", verifier.status === "ok" ? "active" : verifier.status === "missed" ? "blocked" : "info")}
              ${verifier.rewrite_applied ? inspectorBadge("rewrite", "active") : ""}
              ${(verifier.matched_terms || []).map((term) => inspectorBadge(`hit: ${term}`, "active")).join("")}
              ${(verifier.missing_terms || []).slice(0, 4).map((term) => inspectorBadge(`miss: ${term}`, "warning")).join("")}
            </div>
            <p class="inspector-copy">${escapeHtml(verifier.reason || "")}</p>
          `
          : `<p class="muted">回答完成后显示是否用上了注入记忆。</p>`
      }
    </div>

    <p class="inspector-footnote">${escapeHtml(route.strategy_version || "rule_based_v2")}</p>
  `;
}

function flattenLifecycleTrace(trace) {
  if (!trace || typeof trace !== "object") {
    return [];
  }
  const rows = [];
  Object.entries(trace).forEach(([tier, items]) => {
    if (!Array.isArray(items)) {
      return;
    }
    items.forEach((item) => {
      rows.push({ tier, ...item });
    });
  });
  return rows;
}

function lifecycleVariant(stateName, injectable) {
  if (!injectable) {
    return "blocked";
  }
  if (stateName === "active") {
    return "active";
  }
  if (stateName === "stale") {
    return "warning";
  }
  if (stateName === "historical") {
    return "historical";
  }
  return "";
}

function renderLifecycleInspector(companion) {
  if (!lifecycleInspectorPanel) {
    return;
  }
  const rows = flattenLifecycleTrace(companion?.lifecycle_trace);
  if (!rows.length) {
    lifecycleInspectorPanel.innerHTML = `<p class="muted">这轮没有候选记忆进入 Lifecycle 过滤。</p>`;
    return;
  }

  lifecycleInspectorPanel.innerHTML = rows
    .map((row) => {
      const stateName = row.lifecycle_state || "active";
      const label = row.label || row.value || row.key || row.note || `#${row.index ?? ""}`;
      const injected = Boolean(row.injectable);
      const variant = lifecycleVariant(stateName, injected);
      const memoryId = row.memory_id || "";
      return `
        <article class="lifecycle-row ${injected ? "is-injected" : "is-hidden-memory"}" data-lifecycle-memory-id="${escapeHtml(memoryId)}">
          <div class="lifecycle-row-head">
            <div>
              <div class="lifecycle-title">${escapeHtml(String(label || "memory"))}</div>
              <div class="lifecycle-meta">${escapeHtml(row.tier || "")}${row.key ? ` · ${escapeHtml(row.key)}` : ""}</div>
            </div>
            <div class="lifecycle-status-group">
              ${inspectorBadge(stateName, variant)}
              ${inspectorBadge(injected ? "Injected" : "Hidden", injected ? "active" : "blocked")}
            </div>
          </div>
          <div class="lifecycle-score-grid">
            ${renderScoreBar("confidence", row.confidence)}
            ${renderScoreBar("freshness", row.freshness)}
            ${renderScoreBar("final", row.final_score)}
          </div>
          ${
            memoryId
              ? `<div class="lifecycle-actions">
                  <button class="memory-delete-button" type="button" data-memory-status-id="${escapeHtml(memoryId)}" data-memory-status="historical">历史化</button>
                  <button class="memory-delete-button" type="button" data-memory-status-id="${escapeHtml(memoryId)}" data-memory-status="active">恢复</button>
                  <button class="memory-delete-button" type="button" data-delete-memory-id="${escapeHtml(memoryId)}" data-delete-memory-label="${escapeHtml(String(label || "这条记忆"))}">删除</button>
                </div>`
              : ""
          }
          <div class="lifecycle-reason">${escapeHtml(row.lifecycle_reason || "")}</div>
        </article>
      `;
    })
    .join("");
}

function renderMemoryInspector(companion, { clear = false } = {}) {
  if (clear) {
    state.lastCompanionDebug = null;
  } else if (companion) {
    state.lastCompanionDebug = companion;
  }
  const activeCompanion = companion || state.lastCompanionDebug;
  renderRouteInspector(activeCompanion);
  renderLifecycleInspector(activeCompanion);
}

function setInspectorTab(tab) {
  state.inspectorTab = tab === "lifecycle" ? "lifecycle" : "route";
  routeInspectorTab?.classList.toggle("active", state.inspectorTab === "route");
  lifecycleInspectorTab?.classList.toggle("active", state.inspectorTab === "lifecycle");
  routeInspectorPanel?.classList.toggle("is-hidden", state.inspectorTab !== "route");
  lifecycleInspectorPanel?.classList.toggle("is-hidden", state.inspectorTab !== "lifecycle");
}

const FORTUNE_THEME_CHIPS = [
  { key: "general", label: "综合" },
  { key: "study", label: "学习工作" },
  { key: "love", label: "感情" },
  { key: "social", label: "社交" },
  { key: "health", label: "健康" },
  { key: "wealth", label: "财务" },
];

function fortuneStars(score) {
  const filled = Math.max(1, Math.min(5, Math.round(((score || 0) / 100) * 5)));
  return "★".repeat(filled) + "☆".repeat(5 - filled);
}

function fortuneThemeChipsHtml(card) {
  return FORTUNE_THEME_CHIPS.map((theme) => {
    const active = theme.key === card.theme ? " active" : "";
    return `<button class="fortune-theme-chip${active}" type="button" data-fortune-theme="${theme.key}">${theme.label}</button>`;
  }).join("");
}

function fortuneModalHtml(card) {
  return `
    <div class="fortune-modal-grid">
      <div class="fortune-modal-visual">
        ${card.image ? `<img src="${escapeHtml(card.image)}" alt="${escapeHtml(card.sign_name)}星座图" onerror="this.remove()">` : `<span class="fortune-modal-symbol">${escapeHtml(card.symbol || "✦")}</span>`}
      </div>
      <div class="fortune-modal-content">
        <div class="fortune-head">
          <div class="fortune-head-text">
            <div class="fortune-title fortune-modal-title">${escapeHtml(card.sign_name)} · ${escapeHtml(card.theme_name || "今日运势")}</div>
            <div class="fortune-sub">${escapeHtml(card.date)} ${escapeHtml(card.weekday || "")} · ${escapeHtml(card.element || "")} · ${escapeHtml(card.sign_keywords || "")}</div>
          </div>
          <div class="fortune-score">
            <span class="fortune-score-value">${Number(card.overall_score) || 0}%</span>
            <span class="fortune-score-stars">${fortuneStars(Number(card.overall_score) || 0)}</span>
          </div>
        </div>
        <p class="fortune-overall">${escapeHtml(card.overall_fortune || "")}</p>
        <ul class="fortune-rows">
          <li><span class="fortune-row-label">${escapeHtml(card.theme_name === "感情" ? "感情提示" : "学习/工作")}</span><span>${escapeHtml(card.advice || "")}</span></li>
          <li><span class="fortune-row-label">感情社交</span><span>${escapeHtml(card.love_social_tips || "")}</span></li>
          <li><span class="fortune-row-label">幸运色</span><span><i class="fortune-color-dot" style="background:${escapeHtml(card.lucky_color_hex || "#ccc")}"></i>${escapeHtml(card.lucky_color || "")}</span></li>
          <li><span class="fortune-row-label">幸运数字</span><span>${escapeHtml(String(card.lucky_number ?? ""))}</span></li>
          <li><span class="fortune-row-label">适合活动</span><span>${escapeHtml(card.lucky_activity || "")}</span></li>
        </ul>
        <p class="fortune-summary">${escapeHtml(card.companion_summary || "")}</p>
        <div class="fortune-themes">${fortuneThemeChipsHtml(card)}</div>
        <p class="fortune-disclaimer">${escapeHtml(card.disclaimer || "运势内容仅供娱乐参考。")}</p>
      </div>
    </div>
  `;
}

function openFortuneModal() {
  if (!state.horoscopeCard || !fortuneModalOverlay) {
    return;
  }
  renderFortuneModal();
  fortuneModalOverlay.classList.add("is-open");
  fortuneModalOverlay.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}

function closeFortuneModal() {
  if (!fortuneModalOverlay) {
    return;
  }
  fortuneModalOverlay.classList.remove("is-open");
  fortuneModalOverlay.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

function renderFortuneModal() {
  if (!fortuneModalBody || !state.horoscopeCard) {
    return;
  }
  fortuneModalBody.innerHTML = fortuneModalHtml(state.horoscopeCard);
}

function renderFortuneCard() {
  if (!fortuneCard) {
    return;
  }
  const card = state.horoscopeCard;
  if (!card) {
    fortuneCard.innerHTML = `<p class="muted">在对话里告诉我你的星座，例如“我是天秤座，帮我看看今日运势”。</p>`;
    return;
  }

  fortuneCard.innerHTML = `
    <div class="fortune-card-inner">
      <span class="fortune-expand-hint" title="点击放大查看">⤢ 展开</span>
      ${card.image ? `<img class="fortune-illustration" src="${escapeHtml(card.image)}" alt="${escapeHtml(card.sign_name)}星座图" loading="lazy" onerror="this.remove()">` : ""}
      <div class="fortune-head">
        <span class="fortune-symbol">${escapeHtml(card.symbol || "✦")}</span>
        <div class="fortune-head-text">
          <div class="fortune-title">${escapeHtml(card.sign_name)} · ${escapeHtml(card.theme_name || "今日运势")}</div>
          <div class="fortune-sub">${escapeHtml(card.date)} ${escapeHtml(card.weekday || "")} · ${escapeHtml(card.element || "")}</div>
        </div>
        <div class="fortune-score">
          <span class="fortune-score-value">${Number(card.overall_score) || 0}%</span>
          <span class="fortune-score-stars">${fortuneStars(Number(card.overall_score) || 0)}</span>
        </div>
      </div>
      <p class="fortune-overall">${escapeHtml(card.overall_fortune || "")}</p>
      <ul class="fortune-rows">
        <li><span class="fortune-row-label">${escapeHtml(card.theme_name === "感情" ? "感情提示" : "学习/工作")}</span><span>${escapeHtml(card.advice || "")}</span></li>
        <li><span class="fortune-row-label">感情社交</span><span>${escapeHtml(card.love_social_tips || "")}</span></li>
        <li><span class="fortune-row-label">幸运色</span><span><i class="fortune-color-dot" style="background:${escapeHtml(card.lucky_color_hex || "#ccc")}"></i>${escapeHtml(card.lucky_color || "")}</span></li>
        <li><span class="fortune-row-label">幸运数字</span><span>${escapeHtml(String(card.lucky_number ?? ""))}</span></li>
        <li><span class="fortune-row-label">适合活动</span><span>${escapeHtml(card.lucky_activity || "")}</span></li>
      </ul>
      <p class="fortune-summary">${escapeHtml(card.companion_summary || "")}</p>
      <div class="fortune-themes">${fortuneThemeChipsHtml(card)}</div>
      <p class="fortune-disclaimer">${escapeHtml(card.disclaimer || "运势内容仅供娱乐参考。")}</p>
    </div>
  `;
}

async function refreshFortuneTheme(theme) {
  const card = state.horoscopeCard;
  if (!card || !card.sign) {
    return;
  }
  try {
    const payload = await apiRequest("/api/horoscope", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sign: card.sign, theme }),
    });
    if (payload?.card) {
      state.horoscopeCard = payload.card;
      renderFortuneCard();
      if (fortuneModalOverlay?.classList.contains("is-open")) {
        renderFortuneModal();
      }
    }
  } catch (error) {
    console.error("fortune theme refresh failed", error);
  }
}

function clearMcpChatCards() {
  chatStream.querySelectorAll(".mcp-chat-cards").forEach((node) => node.remove());
}

function weatherChatCardHtml(card) {
  const current = card.data?.current || {};
  const forecast = card.data?.forecast || [];
  const forecastRows = forecast
    .map((row) => {
      const rain = row.chance_of_rain ? ` · 降雨 ${row.chance_of_rain}%` : "";
      return `<div class="mcp-weather-forecast-row">
        <span class="mcp-weather-date">${escapeHtml(row.date || "")}</span>
        <span>${escapeHtml(row.description || "")}</span>
        <span class="mcp-weather-temp">${escapeHtml(String(row.min_temp_c ?? "-"))}° / ${escapeHtml(String(row.max_temp_c ?? "-"))}°${rain}</span>
      </div>`;
    })
    .join("");
  return `
    <div class="mcp-card mcp-weather-card">
      <div class="mcp-card-kicker">天气 MCP</div>
      <div class="mcp-weather-head">
        <span class="mcp-weather-city">${escapeHtml(current.resolved_area || current.city || "")}</span>
        <span class="mcp-weather-temp-big">${escapeHtml(String(current.temperature_c ?? "-"))}°C</span>
        <span class="mcp-weather-desc">${escapeHtml(current.description || "")}</span>
      </div>
      <div class="mcp-weather-meta">
        <span>体感 ${escapeHtml(String(current.feels_like_c ?? "-"))}°C</span>
        <span>湿度 ${escapeHtml(String(current.humidity ?? "-"))}%</span>
        <span>风速 ${escapeHtml(String(current.wind_kmph ?? "-"))} km/h</span>
      </div>
      ${forecastRows ? `<div class="mcp-weather-forecast">${forecastRows}</div>` : ""}
    </div>
  `;
}

function horoscopeChatCardHtml(card) {
  const data = card.data || {};
  return `
    <div class="mcp-card mcp-horoscope-card">
      <div class="mcp-card-kicker">星座运势 MCP</div>
      <div class="mcp-horoscope-head">
        ${data.image ? `<img class="mcp-horoscope-thumb" src="${escapeHtml(data.image)}" alt="${escapeHtml(data.sign_name || "")}" loading="lazy" onerror="this.remove()">` : `<span class="fortune-symbol">${escapeHtml(data.symbol || "✦")}</span>`}
        <span class="mcp-horoscope-title">${escapeHtml(data.sign_name || "")} · ${escapeHtml(data.theme_name || "今日运势")}</span>
        <span class="mcp-horoscope-score">${Number(data.overall_score) || 0}%</span>
      </div>
      <p class="mcp-horoscope-line">${escapeHtml(data.overall_fortune || "")}</p>
      <p class="mcp-horoscope-line">${escapeHtml(data.advice || "")}</p>
      <p class="mcp-horoscope-disclaimer">${escapeHtml(data.disclaimer || "")}</p>
    </div>
  `;
}

function renderMcpChatCards() {
  clearMcpChatCards();
  const cards = state.mcpCards || [];
  if (!cards.length) {
    return;
  }
  const lastAssistant = [...chatStream.querySelectorAll(".message.assistant")].pop();
  if (!lastAssistant) {
    return;
  }
  const wrap = document.createElement("div");
  wrap.className = "mcp-chat-cards";
  wrap.innerHTML = cards
    .map((card) => {
      if (card.type === "weather") {
        return weatherChatCardHtml(card);
      }
      if (card.type === "horoscope") {
        return horoscopeChatCardHtml(card);
      }
      if (card.type === "tarot") {
        return tarotChatCardHtml(card);
      }
      return "";
    })
    .join("");
  lastAssistant.insertAdjacentElement("afterend", wrap);
}

function tarotDrawHtml(draw) {
  const cards = (draw.cards || [])
    .map((card) => {
      const isReversed = card.orientation === "reversed";
      return `
      <article class="tarot-card ${isReversed ? "is-reversed" : ""}">
        <div class="tarot-card-image-wrap">
          <img class="tarot-card-image${isReversed ? " reversed" : ""}" src="${escapeHtml(card.image || "")}" alt="${escapeHtml(card.name)}" loading="lazy" onerror="this.parentElement.classList.add('is-missing')">
          <span class="tarot-orientation">${escapeHtml(card.orientation_name)}</span>
        </div>
        <div class="tarot-card-position">${escapeHtml(card.position)}</div>
        <div class="tarot-card-name">《${escapeHtml(card.name)}》</div>
        <div class="tarot-card-sub">${escapeHtml(card.arcana_name || "")}${card.suit_name ? " · " + escapeHtml(card.suit_name) : ""}${card.subtitle ? " · " + escapeHtml(card.subtitle) : ""}</div>
        <div class="tarot-card-keywords">${(card.keywords || []).map((k) => `<span>${escapeHtml(k)}</span>`).join("")}</div>
        <p class="tarot-card-meaning">${escapeHtml(card.meaning || "")}</p>
      </article>
    `;
    })
    .join("");

  return `
    <div class="tarot-draw-head">${escapeHtml(draw.spread_name || "")}${draw.question ? `<span class="tarot-draw-question">问：${escapeHtml(draw.question)}</span>` : ""}</div>
    <div class="tarot-cards">${cards}</div>
    ${draw.analysis ? `<div class="tarot-analysis"><div class="tarot-analysis-kicker">姜姜的解读</div><p>${escapeHtml(draw.analysis).replace(/\n/g, "<br>")}</p></div>` : ""}
    ${draw.analysis_error ? `<div class="tarot-analysis"><p class="muted">解读生成失败：${escapeHtml(draw.analysis_error)}</p></div>` : ""}
    <p class="fortune-disclaimer">${escapeHtml(draw.disclaimer || "塔罗解读仅供娱乐与自我反思参考。")}</p>
  `;
}

function renderTarotSection() {
  if (!tarotDraw) {
    return;
  }
  const draw = state.tarotDraw;
  if (!draw) {
    tarotDraw.classList.add("is-hidden");
    tarotDraw.innerHTML = "";
    return;
  }
  tarotDraw.innerHTML = tarotDrawHtml(draw);
  tarotDraw.classList.remove("is-hidden");
}

async function requestTarotDraw(spread) {
  if (state.tarotPending) {
    return;
  }
  state.tarotPending = true;
  tarotSingleBtn.disabled = true;
  tarotThreeBtn.disabled = true;
  tarotStatus.textContent = "正在洗牌、抽牌并生成解读...";
  try {
    const payload = await apiRequest("/api/tarot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spread }),
    });
    if (payload?.draw) {
      state.tarotDraw = payload.draw;
      renderTarotSection();
      tarotStatus.textContent = "抽牌完成。想再抽一次，或到对话里聊聊这副牌？";
    }
  } catch (error) {
    tarotStatus.textContent = `抽牌失败：${error.message}`;
  } finally {
    state.tarotPending = false;
    tarotSingleBtn.disabled = false;
    tarotThreeBtn.disabled = false;
  }
}

function tarotChatCardHtml(card) {
  const data = card.data || {};
  const cards = (data.cards || [])
    .map(
      (c) => `
      <div class="tarot-mini-card ${c.orientation === "reversed" ? "is-reversed" : ""}">
        <img src="${escapeHtml(c.image || "")}" alt="${escapeHtml(c.name)}" loading="lazy" onerror="this.remove()">
        <span class="tarot-mini-position">${escapeHtml(c.position)}</span>
        <span class="tarot-mini-name">《${escapeHtml(c.name)}》 ${escapeHtml(c.orientation_name)}</span>
      </div>
    `
    )
    .join("");
  return `
    <div class="mcp-card mcp-tarot-card">
      <div class="mcp-card-kicker">塔罗 MCP · ${escapeHtml(data.spread_name || "")}</div>
      <div class="tarot-mini-cards">${cards}</div>
      <p class="mcp-horoscope-disclaimer">${escapeHtml(data.disclaimer || "")}</p>
    </div>
  `;
}

function renderMemoryPanel(payload) {
  const panel = payload.memory_panel || {};
  if (payload.horoscope_card) {
    state.horoscopeCard = payload.horoscope_card;
  }
  if (Object.prototype.hasOwnProperty.call(payload, "tarot_draw")) {
    state.tarotDraw = payload.tarot_draw;
  }
  if (payload.calendar_analysis && payload.calendar_analysis.text) {
    state.calendarAnalysis = payload.calendar_analysis.text;
    state.calendarAnalysisDate = payload.calendar_analysis.date || "";
    renderCalendarAnalysis();
  }
  renderTarotSection();
  if (payload.mcp_cards) {
    state.mcpCards = payload.mcp_cards;
  } else if (Object.prototype.hasOwnProperty.call(payload, "mcp_cards")) {
    state.mcpCards = [];
  }
  renderFortuneCard();
  renderMcpChatCards();
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

  const emotion = payload.companion?.emotion || null;
  if (emotionBadge && emotionText) {
    const label = emotion?.label || "None";
    const confidence = Math.round((emotion?.confidence || 0) * 100);
    emotionText.textContent = label === "None" ? "情绪：None" : `情绪：${label} (${confidence}%)`;
    emotionBadge.dataset.emotion = label;
  }

  renderMemoryInspector(payload.companion || null, {
    clear: Object.prototype.hasOwnProperty.call(payload, "companion") && !payload.companion,
  });

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
  if (typeof payload.memory_enabled === "boolean") {
    state.memoryEnabled = payload.memory_enabled;
  }
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
  state.mcpCards = [];
  clearMcpChatCards();
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
    let ttsReplyUsesStream = null;

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
            if (ttsReplyUsesStream === null) {
              // 每轮回复只选一次路径：WS 直灌优先，失败则回退切句合成
              ttsReplyUsesStream = ttsStreamReady();
              if (!ttsReplyUsesStream) {
                ensureTtsStream();
              }
            }
            if (ttsReplyUsesStream) {
              const pending = streamTtsBuffer.slice(ttsStreamSentLen);
              if (pending) {
                sendTtsStream({ type: ttsStreamSentLen === 0 ? "text" : "append", text: pending });
                ttsStreamSentLen = streamTtsBuffer.length;
              }
            } else {
              const { chunks, rest } = splitSpeakableChunks(streamTtsBuffer, false);
              streamTtsBuffer = rest;
              chunks.forEach((chunk) => enqueueTtsChunk(chunk));
            }
          }
          continue;
        }
        if (event.type === "final") {
          renderMessages(event.payload?.messages || []);
          renderMemoryPanel(event.payload || {});
          if (state.shouldSpeakReply) {
            if (ttsReplyUsesStream === null) {
              ttsReplyUsesStream = ttsStreamReady();
              if (!ttsReplyUsesStream) {
                ensureTtsStream();
              }
            }
            if (seenDelta) {
              if (ttsReplyUsesStream) {
                const pending = streamTtsBuffer.slice(ttsStreamSentLen);
                if (pending) {
                  sendTtsStream({ type: ttsStreamSentLen === 0 ? "text" : "append", text: pending });
                }
                sendTtsStream({ type: "finish" });
                ttsStreamSessionOpen = false;
              } else {
                const { chunks } = splitSpeakableChunks(streamTtsBuffer, true);
                chunks.forEach((chunk) => enqueueTtsChunk(chunk));
              }
            } else {
              const reply = event.payload?.reply || "";
              if (ttsReplyUsesStream) {
                sendTtsStream({ type: "text", text: reply });
                sendTtsStream({ type: "finish" });
                ttsStreamSessionOpen = false;
              } else {
                enqueueTtsChunk(reply);
              }
            }
            ttsStreamSentLen = 0;
          }
          state.shouldSpeakReply = false;
          assistantContent = "";
          streamTtsBuffer = "";
          await reader.cancel().catch(() => {});
          return;
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
          if (ttsStreamReady()) {
            ensureTtsStream();
            sendTtsStream({ type: "text", text: event.payload?.reply || "" });
            sendTtsStream({ type: "finish" });
            ttsStreamSessionOpen = false;
          } else {
            ensureTtsStream();
            enqueueTtsChunk(event.payload?.reply || "");
          }
        }
        state.shouldSpeakReply = false;
        await reader.cancel().catch(() => {});
        return;
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

async function setMemoryStatus(memoryId, status) {
  if (!memoryId || !status) {
    return;
  }
  await apiRequest("/api/memory/status", {
    method: "POST",
    body: JSON.stringify({ memory_id: memoryId, status }),
  });
  await refreshState();
}

sendBtn.addEventListener("click", () => sendMessage(messageInput.value.trim()));

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage(messageInput.value.trim());
  }
});

toggleOn.addEventListener("click", () => setMemoryEnabled(true));

toggleOff.addEventListener("click", () => setMemoryEnabled(false));

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
  const statusButton = event.target.closest("[data-memory-status-id]");
  if (statusButton) {
    setMemoryStatus(
      statusButton.dataset.memoryStatusId || "",
      statusButton.dataset.memoryStatus || ""
    ).catch((error) => {
      alert(error.message);
    });
    return;
  }

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

routeInspectorTab?.addEventListener("click", () => {
  setInspectorTab("route");
});

lifecycleInspectorTab?.addEventListener("click", () => {
  setInspectorTab("lifecycle");
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
  
  // Click on the item itself to select
  const item = event.target.closest(".character-list-item");
  if (item && !event.target.closest(".character-list-actions")) {
    const cardId = item.dataset.cardId;
    if (cardId && cardId !== state.activeCharacterCardId) {
      applyCharacterCardSelection(cardId).catch((error) => {
        if (characterCardStatus) {
          characterCardStatus.textContent = `应用失败：${error.message}`;
        }
      });
    }
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
renderFortuneCard();
loadCalendar().catch(() => {});

fortuneCard?.addEventListener("click", (event) => {
  const chip = event.target.closest("[data-fortune-theme]");
  if (chip) {
    refreshFortuneTheme(chip.dataset.fortuneTheme);
    return;
  }
  openFortuneModal();
});

fortuneModalClose?.addEventListener("click", closeFortuneModal);
fortuneModalOverlay?.addEventListener("click", (event) => {
  if (event.target === fortuneModalOverlay) {
    closeFortuneModal();
  }
});
fortuneModalBody?.addEventListener("click", (event) => {
  const chip = event.target.closest("[data-fortune-theme]");
  if (chip) {
    refreshFortuneTheme(chip.dataset.fortuneTheme);
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && fortuneModalOverlay?.classList.contains("is-open")) {
    closeFortuneModal();
  }
});

tarotSingleBtn?.addEventListener("click", () => requestTarotDraw("single"));
tarotThreeBtn?.addEventListener("click", () => requestTarotDraw("three"));

function tarotModalCardHtml(card) {
  const isReversed = card.orientation === "reversed";
  return `
    <article class="tarot-modal-card ${isReversed ? "is-reversed" : ""}">
      <div class="tarot-modal-card-image">
        <img class="${isReversed ? "reversed" : ""}" src="${escapeHtml(card.image || "")}" alt="${escapeHtml(card.name)}" onerror="this.parentElement.classList.add('is-missing')">
        <span class="tarot-orientation">${escapeHtml(card.orientation_name)}</span>
      </div>
      <div class="tarot-modal-card-body">
        <div class="tarot-card-position">${escapeHtml(card.position)}</div>
        <div class="tarot-modal-card-name">《${escapeHtml(card.name)}》</div>
        <div class="tarot-card-sub">${escapeHtml(card.arcana_name || "")}${card.suit_name ? " · " + escapeHtml(card.suit_name) : ""}${card.element_planet ? " · " + escapeHtml(card.element_planet) : ""}${card.subtitle ? " · " + escapeHtml(card.subtitle) : ""}</div>
        <div class="tarot-card-keywords">${(card.keywords || []).map((k) => `<span>${escapeHtml(k)}</span>`).join("")}</div>
        <p class="tarot-modal-meaning">${escapeHtml(card.meaning || "")}</p>
        ${card.affirmation ? `<p class="tarot-modal-affirmation">肯定语：“${escapeHtml(card.affirmation)}”</p>` : ""}
        ${card.love ? `<p class="tarot-modal-extra"><strong>爱情运</strong>${escapeHtml(card.love)}</p>` : ""}
        ${card.career ? `<p class="tarot-modal-extra"><strong>事业与工作</strong>${escapeHtml(card.career)}</p>` : ""}
      </div>
    </article>
  `;
}

function tarotModalHtml(draw) {
  return `
    <div class="tarot-modal-head">
      <div class="fortune-title tarot-modal-title">${escapeHtml(draw.spread_name || "塔罗解读")}</div>
      ${draw.question ? `<div class="tarot-draw-question">问：${escapeHtml(draw.question)}</div>` : ""}
    </div>
    <div class="tarot-modal-cards">${(draw.cards || []).map(tarotModalCardHtml).join("")}</div>
    ${draw.analysis ? `<div class="tarot-analysis tarot-modal-analysis"><div class="tarot-analysis-kicker">姜姜的解读</div><p>${escapeHtml(draw.analysis).replace(/\n/g, "<br>")}</p></div>` : ""}
    <p class="fortune-disclaimer">${escapeHtml(draw.disclaimer || "塔罗解读仅供娱乐与自我反思参考。")}</p>
  `;
}

function openTarotModal() {
  if (!state.tarotDraw || !tarotModalOverlay) {
    return;
  }
  tarotModalBody.innerHTML = tarotModalHtml(state.tarotDraw);
  tarotModalOverlay.classList.add("is-open");
  tarotModalOverlay.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}

function closeTarotModal() {
  if (!tarotModalOverlay) {
    return;
  }
  tarotModalOverlay.classList.remove("is-open");
  tarotModalOverlay.setAttribute("aria-hidden", "true");
  if (!fortuneModalOverlay?.classList.contains("is-open")) {
    document.body.classList.remove("modal-open");
  }
}

tarotDraw?.addEventListener("click", openTarotModal);
tarotModalClose?.addEventListener("click", closeTarotModal);
tarotModalOverlay?.addEventListener("click", (event) => {
  if (event.target === tarotModalOverlay) {
    closeTarotModal();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && tarotModalOverlay?.classList.contains("is-open")) {
    closeTarotModal();
  }
});

/* ===== Mood calendar ===== */
const MOOD_META = {
  "开心": { color: "#8aaa8c", label: "开心" },
  "难过": { color: "#c4706a", label: "难过" },
  "None": { color: "#c9bfb4", label: "平静" },
};

function moodMeta(mood) {
  return MOOD_META[mood] || MOOD_META.None;
}

function isRainyDay(entry) {
  const desc = String((entry || {}).weather_desc || "");
  return /雨|Rain|Drizzle|Shower|Thunder/.test(desc);
}

function renderCalendarGrid() {
  if (!calendarGrid) {
    return;
  }
  const today = new Date();
  const year = today.getFullYear();
  const month = today.getMonth();
  const first = new Date(year, month, 1);
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const lead = (first.getDay() + 6) % 7; // Monday-first

  const weekdayRow = ["一", "二", "三", "四", "五", "六", "日"]
    .map((w) => `<div class="calendar-weekday">${w}</div>`)
    .join("");
  let cells = "";
  for (let i = 0; i < lead; i += 1) {
    cells += `<div class="calendar-cell is-empty"></div>`;
  }
  for (let d = 1; d <= daysInMonth; d += 1) {
    const key = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    const entry = state.calendarDays[key];
    const isToday = key === state.todayKey;
    let inner = "";
    if (entry) {
      const meta = moodMeta(entry.mood);
      const icons = [];
      if (isRainyDay(entry)) icons.push('<span class="calendar-icon rain" title="雨天">雨</span>');
      else if (entry.weather_desc) icons.push('<span class="calendar-icon" title="有天气记录">晴</span>');
      if (entry.horoscope_score != null) icons.push(`<span class="calendar-icon star" title="运势 ${entry.horoscope_score}%">★</span>`);
      if (entry.tarot_cards && entry.tarot_cards.length) icons.push('<span class="calendar-icon tarot" title="抽了塔罗">✦</span>');
      inner = `
        <span class="calendar-mood-dot" style="background:${meta.color}" title="心情：${meta.label}"></span>
        <span class="calendar-icons">${icons.join("")}</span>
      `;
    }
    cells += `<button class="calendar-cell${isToday ? " is-today" : ""}" type="button" data-calendar-day="${key}">
      <span class="calendar-day-num">${d}</span>${inner}
    </button>`;
  }
  calendarGrid.innerHTML = weekdayRow + cells;
}

function renderCalendarDetail(dayKey) {
  if (!calendarDetail) {
    return;
  }
  const entry = state.calendarDays[dayKey];
  if (!entry) {
    calendarDetail.classList.add("is-hidden");
    calendarDetail.innerHTML = "";
    return;
  }
  const meta = moodMeta(entry.mood);
  const hasJournal = Array.isArray(state.tarotHistory) && state.tarotHistory.some((rec) => rec.date === dayKey);
  const rows = [
    entry.mood ? `<li><span>心情</span><b style="color:${meta.color}">${escapeHtml(meta.label)}${entry.mood_intensity != null ? " · 强度 " + Math.round(entry.mood_intensity * 100) + "%" : ""}</b></li>` : "",
    entry.weather_desc ? `<li><span>天气</span><b>${escapeHtml(entry.weather_desc)} · ${escapeHtml(String(entry.weather_temp_c ?? "-"))}°C${entry.weather_city ? " · " + escapeHtml(entry.weather_city) : ""}</b></li>` : "",
    entry.horoscope_score != null ? `<li><span>运势</span><b>${escapeHtml(entry.horoscope_theme || "综合")} ${entry.horoscope_score}%${entry.zodiac_sign ? " · " + escapeHtml(entry.zodiac_sign) : ""}</b></li>` : "",
    entry.tarot_cards && entry.tarot_cards.length ? `<li><span>塔罗</span><b>${escapeHtml(entry.tarot_spread || "")} ${entry.tarot_cards.map(escapeHtml).join("、")}</b></li>` : "",
  ].filter(Boolean).join("");
  calendarDetail.innerHTML = `
    <div class="calendar-detail-head">${dayKey}${dayKey === state.todayKey ? " · 今天" : ""}</div>
    <ul class="calendar-detail-rows">${rows || '<li><span class="muted">当天暂无详细记录</span></li>'}</ul>
    ${hasJournal ? `<button class="btn btn-secondary calendar-journal-link" type="button" data-journal-date="${dayKey}">在手札中查看这次占卜 ✦</button>` : ""}
  `;
  calendarDetail.classList.remove("is-hidden");
}

function renderCalendarAnalysis() {
  if (!calendarAnalysis) {
    return;
  }
  if (!state.calendarAnalysis) {
    calendarAnalysis.classList.add("is-hidden");
    return;
  }
  calendarAnalysis.innerHTML = `
    <div class="tarot-analysis-kicker">日历分析${state.calendarAnalysisDate ? " · " + escapeHtml(state.calendarAnalysisDate) : ""}</div>
    <p>${escapeHtml(state.calendarAnalysis).replace(/\n/g, "<br>")}</p>
  `;
  calendarAnalysis.classList.remove("is-hidden");
}

async function loadCalendar(analyze = false) {
  try {
    const payload = await apiRequest("/api/calendar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(analyze ? { action: "analyze" } : {}),
    });
    if (payload?.days) {
      state.calendarDays = payload.days;
      state.todayKey = payload.today;
      state.calendarAnalysis = payload.analysis || "";
      state.calendarAnalysisDate = payload.analysis_date || "";
      state.calendarSeries = Array.isArray(payload.series) ? payload.series : [];
      state.moodForecast = Array.isArray(payload.mood_forecast) ? payload.mood_forecast : [];
      state.tarotHistory = Array.isArray(payload.tarot_history) ? payload.tarot_history : [];
      renderCalendarGrid();
      renderCalendarAnalysis();
      renderMoodTrendChart();
      renderTarotJournal();
    }
  } catch (error) {
    console.error("calendar load failed", error);
  }
}

calendarGrid?.addEventListener("click", (event) => {
  const cell = event.target.closest("[data-calendar-day]");
  if (cell) {
    renderCalendarDetail(cell.dataset.calendarDay);
  }
});
calendarAnalyzeBtn?.addEventListener("click", async () => {
  calendarAnalyzeBtn.disabled = true;
  calendarAnalyzeBtn.textContent = "分析中...";
  await loadCalendar(true);
  calendarAnalyzeBtn.disabled = false;
  calendarAnalyzeBtn.textContent = "生成分析";
});

/* ===== Mood trend chart ===== */
const WEEKDAY_NAMES = ["日", "一", "二", "三", "四", "五", "六"];

function moodScoreColor(score) {
  const t = Math.max(0, Math.min(1, (score - 30) / 60));
  const low = [232, 176, 138]; // 柔杏色
  const high = [138, 170, 140]; // 鼠尾草绿
  const mix = low.map((v, i) => Math.round(v + (high[i] - v) * t));
  return `rgb(${mix[0]}, ${mix[1]}, ${mix[2]})`;
}

function weatherIcon(desc) {
  const d = String(desc || "").toLowerCase();
  if (/thunder|雷/.test(d)) return "⛈";
  if (/rain|drizzle|shower|雨/.test(d)) return "🌧";
  if (/sunny|clear|晴/.test(d)) return "☀️";
  if (/partly|多云/.test(d)) return "⛅";
  if (/cloudy|overcast|阴/.test(d)) return "☁️";
  return "🌤";
}

function smoothCurve(ctx, pts) {
  if (pts.length < 2) return;
  ctx.moveTo(pts[0].x, pts[0].y);
  for (let i = 0; i < pts.length - 1; i += 1) {
    const p0 = pts[Math.max(0, i - 1)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(pts.length - 1, i + 2)];
    ctx.bezierCurveTo(
      p1.x + (p2.x - p0.x) / 6,
      p1.y + (p2.y - p0.y) / 6,
      p2.x - (p3.x - p1.x) / 6,
      p2.y - (p3.y - p1.y) / 6,
      p2.x,
      p2.y
    );
  }
}

let moodChartPoints = [];

function renderMoodTrendChart() {
  const canvas = moodTrendCanvas;
  if (!canvas) return;
  const past = state.calendarSeries || [];
  const future = state.moodForecast || [];
  const wrap = canvas.parentElement;
  const cssWidth = wrap ? wrap.clientWidth : 640;
  const cssHeight = 240;
  if (!past.length && !future.length) {
    canvas.style.display = "none";
    if (wrap) wrap.classList.add("is-empty");
    return;
  }
  canvas.style.display = "";
  if (wrap) wrap.classList.remove("is-empty");

  const dpr = window.devicePixelRatio || 1;
  canvas.width = cssWidth * dpr;
  canvas.height = cssHeight * dpr;
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${cssHeight}px`;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const padL = 18;
  const padR = 18;
  const padT = 26;
  const padB = 46;
  const innerW = cssWidth - padL - padR;
  const innerH = cssHeight - padT - padB;

  const all = [
    ...past.map((r) => ({ ...r, future: false })),
    ...future.map((r) => ({ ...r, future: true, mood_score: r.predicted_mood_score })),
  ];
  const scores = all.map((r) => r.mood_score ?? 60);
  let yMin = Math.min(...scores) - 8;
  let yMax = Math.max(...scores) + 8;
  yMin = Math.max(5, Math.floor(yMin));
  yMax = Math.min(100, Math.ceil(yMax));
  if (yMax - yMin < 20) {
    const mid = (yMax + yMin) / 2;
    yMin = Math.max(5, Math.floor(mid - 10));
    yMax = Math.min(100, Math.ceil(mid + 10));
  }
  const xAt = (i) => padL + (all.length === 1 ? innerW / 2 : (innerW * i) / (all.length - 1));
  const yAt = (s) => padT + innerH - ((s - yMin) / (yMax - yMin)) * innerH;
  const pts = all.map((r, i) => ({ x: xAt(i), y: yAt(r.mood_score ?? 60), row: r, i }));

  // 柔和横向网格线
  ctx.strokeStyle = "rgba(61, 53, 48, 0.06)";
  ctx.lineWidth = 1;
  ctx.setLineDash([2, 5]);
  for (let g = 0; g <= 3; g += 1) {
    const gy = padT + (innerH * g) / 3;
    ctx.beginPath();
    ctx.moveTo(padL, gy);
    ctx.lineTo(cssWidth - padR, gy);
    ctx.stroke();
  }
  ctx.setLineDash([]);

  const pastPts = pts.filter((p) => !p.row.future);
  const futurePts = pts.filter((p) => p.row.future);

  // 面积填充（过去实 + 未来淡）
  const fillFor = (segment, alphaTop) => {
    if (segment.length < 2) return;
    const grad = ctx.createLinearGradient(0, padT, 0, padT + innerH);
    grad.addColorStop(0, `rgba(138, 170, 140, ${alphaTop})`);
    grad.addColorStop(1, "rgba(138, 170, 140, 0)");
    ctx.beginPath();
    smoothCurve(ctx, segment);
    ctx.lineTo(segment[segment.length - 1].x, padT + innerH);
    ctx.lineTo(segment[0].x, padT + innerH);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();
  };
  fillFor(pastPts, 0.32);
  fillFor(futurePts, 0.14);

  // 曲线本体
  const drawLine = (segment, dashed) => {
    if (segment.length < 2) return;
    ctx.beginPath();
    smoothCurve(ctx, segment);
    ctx.strokeStyle = dashed ? "rgba(138, 170, 140, 0.85)" : "#8aaa8c";
    ctx.lineWidth = 3;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.setLineDash(dashed ? [7, 6] : []);
    ctx.stroke();
    ctx.setLineDash([]);
  };
  drawLine(pastPts, false);
  drawLine(futurePts, true);

  // 今天分隔
  if (pastPts.length && futurePts.length) {
    const x = pastPts[pastPts.length - 1].x;
    ctx.strokeStyle = "rgba(198, 125, 94, 0.45)";
    ctx.lineWidth = 1.4;
    ctx.setLineDash([3, 4]);
    ctx.beginPath();
    ctx.moveTo(x, padT - 8);
    ctx.lineTo(x, padT + innerH + 6);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "rgba(198, 125, 94, 0.9)";
    ctx.font = "11px 'DM Sans', sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("今天", x, padT - 12);
  }

  // 数据点
  pts.forEach((p) => {
    if (p.row.future) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 4.5, 0, Math.PI * 2);
      ctx.fillStyle = "#fffcfa";
      ctx.fill();
      ctx.strokeStyle = "rgba(138, 170, 140, 0.9)";
      ctx.lineWidth = 2;
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 4.5, 0, Math.PI * 2);
      ctx.fillStyle = moodScoreColor(p.row.mood_score ?? 60);
      ctx.fill();
      ctx.strokeStyle = "#fffcfa";
      ctx.lineWidth = 1.6;
      ctx.stroke();
    }
    if (p.row.has_tarot) {
      ctx.font = "13px serif";
      ctx.textAlign = "center";
      ctx.fillStyle = "#c99a4e";
      ctx.fillText("✦", p.x, p.y - 10);
    }
  });

  // 天气小图标 + 日期标签
  ctx.textAlign = "center";
  pts.forEach((p) => {
    ctx.font = "13px serif";
    ctx.fillText(weatherIcon(p.row.weather_desc), p.x, padT + innerH + 18);
    const d = String(p.row.date || "").slice(5).replace("-", "/");
    ctx.font = "10px 'DM Sans', sans-serif";
    ctx.fillStyle = p.row.future ? "rgba(107, 96, 88, 0.55)" : "rgba(107, 96, 88, 0.85)";
    ctx.fillText(d, p.x, padT + innerH + 34);
  });

  moodChartPoints = pts;
}

moodTrendCanvas?.addEventListener("click", (event) => {
  if (!moodChartPoints.length) return;
  const rect = moodTrendCanvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  let nearest = moodChartPoints[0];
  let best = Infinity;
  moodChartPoints.forEach((p) => {
    const d = Math.abs(p.x - x);
    if (d < best) {
      best = d;
      nearest = p;
    }
  });
  if (best > 40) return;
  if (nearest.row.has_tarot) {
    const rec = (state.tarotHistory || []).find((r) => r.date === nearest.row.date);
    if (rec) {
      openTarotRecordModal(rec);
      return;
    }
  }
  renderCalendarDetail(nearest.row.date);
});

let moodChartResizeTimer = null;
window.addEventListener("resize", () => {
  if (!moodTrendCanvas || moodTrendCanvas.style.display === "none") return;
  clearTimeout(moodChartResizeTimer);
  moodChartResizeTimer = setTimeout(renderMoodTrendChart, 150);
});

/* ===== Tarot journal（占卜手札）===== */
function formatJournalDate(iso) {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getMonth() + 1}月${d.getDate()}日 周${WEEKDAY_NAMES[d.getDay()]}`;
}

function tarotRecordHtml(record) {
  const cards = (record.cards || [])
    .map((c) => `《${escapeHtml(c.name)}》${c.orientation_name === "逆位" ? " · 逆位" : ""}`)
    .join("　");
  return `
    <div class="tarot-modal-head">
      <div class="fortune-title tarot-modal-title">${escapeHtml(record.spread_name || "塔罗占卜")}</div>
      <div class="tarot-journal-meta">${escapeHtml(formatJournalDate(record.date))}${record.question ? ` · 问：${escapeHtml(record.question)}` : ""}</div>
    </div>
    ${record.event ? `<p class="tarot-journal-event"><span>那天的小事</span>${escapeHtml(record.event)}</p>` : ""}
    <div class="tarot-journal-cards-line">${cards}</div>
    <div class="tarot-modal-cards">${(record.cards || []).map(tarotModalCardHtml).join("")}</div>
  `;
}

function openTarotRecordModal(record) {
  if (!tarotModalOverlay || !tarotModalBody) return;
  tarotModalBody.innerHTML = tarotRecordHtml(record);
  tarotModalOverlay.classList.add("is-open");
  tarotModalOverlay.setAttribute("aria-hidden", "false");
}

function renderTarotJournal() {
  if (!tarotJournal) return;
  const list = state.tarotHistory || [];
  if (!list.length) {
    tarotJournal.innerHTML = '<p class="muted tarot-journal-empty">还没有占卜记录。去抽一张牌，姜姜会替你收好每一页手札。</p>';
    return;
  }
  tarotJournal.innerHTML = list
    .map((rec, idx) => {
      const cards = (rec.cards || [])
        .map((c) => `<span class="journal-card-chip${c.orientation === "reversed" ? " is-reversed" : ""}">${escapeHtml(c.name)}<i>${c.orientation_name === "逆位" ? "逆" : "正"}</i></span>`)
        .join("");
      return `
        <button class="journal-entry" type="button" data-journal-index="${idx}">
          <span class="journal-entry-head">
            <span class="journal-date">${escapeHtml(formatJournalDate(rec.date))}</span>
            <span class="journal-spread">${escapeHtml(rec.spread_name || "塔罗占卜")}</span>
          </span>
          <span class="journal-cards">${cards}</span>
          ${rec.question ? `<span class="journal-q">问：${escapeHtml(rec.question)}</span>` : ""}
          ${rec.event ? `<span class="journal-event">${escapeHtml(rec.event)}</span>` : ""}
        </button>
      `;
    })
    .join("");
}

tarotJournal?.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-journal-index]");
  if (!btn) return;
  const rec = (state.tarotHistory || [])[Number(btn.dataset.journalIndex)];
  if (rec) openTarotRecordModal(rec);
});

calendarDetail?.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-journal-date]");
  if (!btn) return;
  const rec = (state.tarotHistory || []).find((r) => r.date === btn.dataset.journalDate);
  if (rec) openTarotRecordModal(rec);
});

refreshVoiceStatus().catch(() => {
  setMicUi();
});
state.speechEnabled = loadSpeechEnabledPreference();
updateVoicePills();
setMemoryImportUi();
setSpeechToggleUi();
setInspectorTab(state.inspectorTab);
updateCharacterCardPreview();

window.setInterval(() => {
  if (!state.pending) {
    refreshState().catch(() => {});
  }
}, 1200);

window.setInterval(() => {
  refreshCharacterCards().catch(() => {});
}, 12000);

window.setInterval(() => {
  refreshVoiceStatus().catch(() => {});
}, 10000);

window.setInterval(() => {
  refreshRuntimeCardStatus().catch(() => {});
}, 3000);
