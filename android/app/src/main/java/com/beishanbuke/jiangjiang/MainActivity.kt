package com.beishanbuke.jiangjiang

import android.Manifest
import android.content.Context
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.util.concurrent.TimeUnit

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            JiangJiangApp()
        }
    }
}

private val WarmBackground = Color(0xFFF4EFE8)
private val WarmSurface = Color(0xFFFFFDF9)
private val WarmInset = Color(0xFFF7F1E8)
private val WarmBorder = Color(0xFFE4D8CB)
private val TextPrimary = Color(0xFF332D2A)
private val TextSecondary = Color(0xFF625852)
private val TextMuted = Color(0xFF9A8F85)
private val Accent = Color(0xFFB76F54)
private val Sage = Color(0xFF8AAA8C)

private data class ChatMessage(val role: String, val content: String)
private data class MemoryItem(val title: String, val body: String)
private data class CharacterCard(
    val id: String,
    val name: String,
    val prompt: String,
    val voiceType: String,
    val active: Boolean,
)

private enum class Screen(val label: String, val icon: String) {
    Chat("聊天", "✦"),
    Memory("记忆", "◌"),
    Cards("角色", "◇"),
    Settings("设置", "⌁"),
}

@Composable
private fun JiangJiangApp() {
    val scheme = lightColorScheme(
        primary = Accent,
        secondary = Sage,
        background = WarmBackground,
        surface = WarmSurface,
        onPrimary = Color.White,
        onSurface = TextPrimary,
    )
    MaterialTheme(colorScheme = scheme) {
        Surface(color = WarmBackground, modifier = Modifier.fillMaxSize()) {
            JiangJiangHome()
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun JiangJiangHome() {
    val context = androidx.compose.ui.platform.LocalContext.current
    val scope = rememberCoroutineScope()
    val api = remember { JiangJiangApi(context) }
    val recorder = remember { AudioRecorder(context) }

    var screen by remember { mutableStateOf(Screen.Chat) }
    var baseUrl by remember { mutableStateOf(api.baseUrl) }
    var status by remember { mutableStateOf("同一 Wi-Fi 下，把后端地址设成电脑局域网 IP。") }
    var input by remember { mutableStateOf("") }
    var pending by remember { mutableStateOf(false) }
    var recording by remember { mutableStateOf(false) }
    var speakerEnabled by remember { mutableStateOf(true) }
    var memoryEnabled by remember { mutableStateOf(true) }
    var memoryPreview by remember { mutableStateOf("暂无") }
    var activeCardName by remember { mutableStateOf("姜姜") }
    val messages = remember { mutableStateListOf<ChatMessage>() }
    val memoryItems = remember { mutableStateListOf<MemoryItem>() }
    val cards = remember { mutableStateListOf<CharacterCard>() }

    val micPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        if (granted) {
            scope.launch {
                runCatching {
                    recorder.start()
                    recording = true
                    status = "正在听你说话。再次点击麦克风结束并转文字。"
                }.onFailure {
                    status = "录音启动失败：${it.message ?: "未知错误"}"
                }
            }
        } else {
            status = "没有麦克风权限，暂时只能文字输入。"
        }
    }

    fun refreshState() {
        scope.launch {
            runCatching { api.fetchState() }
                .onSuccess { state ->
                    memoryPreview = state.memoryPreview
                    activeCardName = state.activeCardName.ifBlank { activeCardName }
                    memoryItems.clear()
                    memoryItems.addAll(state.memoryItems)
                    if (state.messages.isNotEmpty()) {
                        messages.clear()
                        messages.addAll(state.messages)
                    }
                }
                .onFailure { status = "读取状态失败：${it.message}" }
        }
    }

    fun refreshCards() {
        scope.launch {
            runCatching { api.fetchCards() }
                .onSuccess {
                    cards.clear()
                    cards.addAll(it)
                    it.firstOrNull { card -> card.active }?.let { card -> activeCardName = card.name }
                }
                .onFailure { status = "读取角色卡失败：${it.message}" }
        }
    }

    fun sendMessage(text: String) {
        val message = text.trim()
        if (message.isEmpty() || pending) return
        pending = true
        input = ""
        messages.add(ChatMessage("user", message))
        scope.launch {
            runCatching { api.chat(message, memoryEnabled) }
                .onSuccess { result ->
                    messages.clear()
                    messages.addAll(result.messages)
                    memoryPreview = result.memoryPreview
                    memoryItems.clear()
                    memoryItems.addAll(result.memoryItems)
                    status = "姜姜回复了。"
                    if (speakerEnabled) {
                        runCatching { api.speak(result.reply) }
                            .onFailure { status = "回复已生成，但播放失败：${it.message}" }
                    }
                }
                .onFailure {
                    messages.add(ChatMessage("assistant", "请求失败：${it.message}"))
                    status = "聊天请求失败：${it.message}"
                }
            pending = false
        }
    }

    LaunchedEffect(Unit) {
        refreshState()
        refreshCards()
    }

    DisposableEffect(Unit) {
        onDispose {
            recorder.stopSilently()
            api.release()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("姜姜", fontSize = 24.sp, fontWeight = FontWeight.SemiBold)
                        Text(
                            "正在使用 $activeCardName",
                            fontSize = 12.sp,
                            color = TextMuted,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                },
                actions = {
                    FilterChip(
                        selected = memoryEnabled,
                        onClick = { memoryEnabled = !memoryEnabled },
                        label = { Text(if (memoryEnabled) "记得我" else "只聊这次") },
                    )
                    IconButton(onClick = {
                        speakerEnabled = !speakerEnabled
                        if (!speakerEnabled) api.stopAudio()
                    }) {
                        Text(if (speakerEnabled) "🔊" else "🔇", fontSize = 20.sp)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = WarmBackground),
            )
        },
        bottomBar = {
            NavigationBar(containerColor = WarmSurface, tonalElevation = 0.dp) {
                Screen.entries.forEach { item ->
                    NavigationBarItem(
                        selected = screen == item,
                        onClick = { screen = item },
                        icon = { Text(item.icon, fontSize = 18.sp) },
                        label = { Text(item.label) },
                    )
                }
            }
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp)
                .navigationBarsPadding()
                .imePadding(),
        ) {
            StatusCard(status = status, baseUrl = baseUrl)
            Spacer(Modifier.height(12.dp))
            when (screen) {
                Screen.Chat -> ChatScreen(
                    messages = messages,
                    input = input,
                    pending = pending,
                    recording = recording,
                    onInputChange = { input = it },
                    onSend = { sendMessage(input) },
                    onMic = {
                        if (recording) {
                            scope.launch {
                                runCatching {
                                    val audio = recorder.stop()
                                    recording = false
                                    status = "正在转写语音..."
                                    val transcript = api.transcribe(audio)
                                    input = transcript
                                    status = if (transcript.isBlank()) "没听清，可以再试一次。" else "已转成文字。"
                                }.onFailure {
                                    recording = false
                                    status = "语音转写失败：${it.message}"
                                }
                            }
                        } else {
                            micPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                        }
                    },
                )
                Screen.Memory -> MemoryScreen(memoryItems, memoryPreview) { refreshState() }
                Screen.Cards -> CardsScreen(
                    cards = cards,
                    onRefresh = { refreshCards() },
                    onSelect = { cardId ->
                        scope.launch {
                            runCatching { api.selectCard(cardId) }
                                .onSuccess {
                                    status = "已切换角色。"
                                    refreshCards()
                                    refreshState()
                                }
                                .onFailure { status = "切换失败：${it.message}" }
                        }
                    },
                    onCreate = { name, prompt ->
                        scope.launch {
                            runCatching { api.upsertCard(name, prompt) }
                                .onSuccess {
                                    status = "角色卡已保存。"
                                    refreshCards()
                                }
                                .onFailure { status = "保存角色失败：${it.message}" }
                        }
                    },
                )
                Screen.Settings -> SettingsScreen(
                    baseUrl = baseUrl,
                    onBaseUrlChange = { baseUrl = it },
                    onSave = {
                        api.baseUrl = baseUrl
                        status = "后端地址已保存。"
                        refreshState()
                        refreshCards()
                    },
                )
            }
        }
    }
}

@Composable
private fun StatusCard(status: String, baseUrl: String) {
    Card(
        colors = CardDefaults.cardColors(containerColor = WarmSurface),
        shape = RoundedCornerShape(22.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(10.dp)
                        .clip(CircleShape)
                        .background(Sage),
                )
                Spacer(Modifier.width(8.dp))
                Text(status, color = TextSecondary, fontSize = 13.sp)
            }
            Spacer(Modifier.height(6.dp))
            Text(baseUrl, color = TextMuted, fontSize = 12.sp, fontFamily = FontFamily.Monospace)
        }
    }
}

@Composable
private fun ChatScreen(
    messages: List<ChatMessage>,
    input: String,
    pending: Boolean,
    recording: Boolean,
    onInputChange: (String) -> Unit,
    onSend: () -> Unit,
    onMic: () -> Unit,
) {
    Column(Modifier.fillMaxSize()) {
        LazyColumn(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (messages.isEmpty()) {
                item {
                    EmptyWarmCard(
                        title = "把今天放在这里就好",
                        body = "可以直接和姜姜说近况，也可以点麦克风说一句。",
                    )
                }
            }
            items(messages) { message ->
                MessageBubble(message)
            }
        }
        Spacer(Modifier.height(10.dp))
        Row(verticalAlignment = Alignment.Bottom) {
            OutlinedTextField(
                value = input,
                onValueChange = onInputChange,
                modifier = Modifier.weight(1f),
                minLines = 2,
                maxLines = 5,
                placeholder = { Text("比如：我今天有点累，但不想被说教。") },
                shape = RoundedCornerShape(20.dp),
            )
            Spacer(Modifier.width(8.dp))
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = onMic, shape = CircleShape) {
                    Text(if (recording) "■" else "🎙")
                }
                Button(
                    onClick = onSend,
                    enabled = !pending && input.trim().isNotEmpty(),
                    shape = CircleShape,
                    colors = ButtonDefaults.buttonColors(containerColor = Accent),
                ) {
                    Text(if (pending) "..." else "发")
                }
            }
        }
        Spacer(Modifier.height(12.dp))
    }
}

@Composable
private fun MessageBubble(message: ChatMessage) {
    val isUser = message.role == "user"
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth(0.84f)
                .clip(RoundedCornerShape(24.dp))
                .background(if (isUser) Accent else WarmSurface)
                .border(1.dp, if (isUser) Accent else WarmBorder, RoundedCornerShape(24.dp))
                .padding(16.dp),
        ) {
            Text(
                if (isUser) "你" else "姜姜",
                color = if (isUser) Color.White.copy(alpha = 0.72f) else TextMuted,
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.height(6.dp))
            Text(message.content, color = if (isUser) Color.White else TextPrimary, lineHeight = 22.sp)
        }
    }
}

@Composable
private fun MemoryScreen(items: List<MemoryItem>, preview: String, onRefresh: () -> Unit) {
    LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("记忆看板", fontSize = 24.sp, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.weight(1f))
                TextButton(onClick = onRefresh) { Text("刷新") }
            }
        }
        item {
            WarmSection(title = "本次回答参考") {
                Text(preview.ifBlank { "暂无" }, color = TextSecondary, lineHeight = 21.sp)
            }
        }
        if (items.isEmpty()) {
            item { EmptyWarmCard("还没有记忆", "聊几轮以后，姜姜会在这里整理与你有关的事实、偏好和最近事件。") }
        } else {
            items(items) { item ->
                WarmSection(title = item.title) {
                    Text(item.body, color = TextSecondary, lineHeight = 21.sp)
                }
            }
        }
    }
}

@Composable
private fun CardsScreen(
    cards: List<CharacterCard>,
    onRefresh: () -> Unit,
    onSelect: (String) -> Unit,
    onCreate: (String, String) -> Unit,
) {
    var name by remember { mutableStateOf("") }
    var prompt by remember { mutableStateOf("") }

    LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("角色卡", fontSize = 24.sp, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.weight(1f))
                TextButton(onClick = onRefresh) { Text("刷新") }
            }
        }
        items(cards) { card ->
            WarmSection(title = if (card.active) "${card.name} · 使用中" else card.name) {
                Text(card.prompt.ifBlank { "暂无描述" }, maxLines = 3, overflow = TextOverflow.Ellipsis)
                Spacer(Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    AssistChip(onClick = {}, label = { Text(card.voiceType.ifBlank { "默认音色" }) })
                    Spacer(Modifier.weight(1f))
                    OutlinedButton(onClick = { onSelect(card.id) }, enabled = !card.active) {
                        Text(if (card.active) "已选择" else "切换")
                    }
                }
            }
        }
        item {
            WarmSection(title = "新建角色") {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("角色命名") },
                    shape = RoundedCornerShape(18.dp),
                )
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = prompt,
                    onValueChange = { prompt = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("角色描述 / 说话风格") },
                    minLines = 4,
                    shape = RoundedCornerShape(18.dp),
                )
                Spacer(Modifier.height(10.dp))
                Button(
                    onClick = {
                        onCreate(name.trim(), prompt.trim())
                        name = ""
                        prompt = ""
                    },
                    enabled = name.isNotBlank() && prompt.isNotBlank(),
                    colors = ButtonDefaults.buttonColors(containerColor = Accent),
                ) {
                    Text("保存角色卡")
                }
            }
        }
    }
}

@Composable
private fun SettingsScreen(baseUrl: String, onBaseUrlChange: (String) -> Unit, onSave: () -> Unit) {
    LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Text("同 Wi‑Fi 调试", fontSize = 24.sp, fontWeight = FontWeight.SemiBold)
        }
        item {
            WarmSection(title = "后端地址") {
                Text(
                    "把电脑和安卓手机连到同一个 Wi‑Fi。在电脑上运行 ipconfig/ifconfig 查局域网 IP，然后填入 http://电脑IP:8765。",
                    color = TextSecondary,
                    lineHeight = 21.sp,
                )
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = baseUrl,
                    onValueChange = onBaseUrlChange,
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    label = { Text("API Base URL") },
                    shape = RoundedCornerShape(18.dp),
                )
                Spacer(Modifier.height(10.dp))
                Button(onClick = onSave, colors = ButtonDefaults.buttonColors(containerColor = Accent)) {
                    Text("保存并重连")
                }
            }
        }
    }
}

@Composable
private fun WarmSection(title: String, content: @Composable () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = WarmSurface),
        shape = RoundedCornerShape(24.dp),
    ) {
        Column(Modifier.padding(16.dp)) {
            Text(title, color = TextPrimary, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(10.dp))
            content()
        }
    }
}

@Composable
private fun EmptyWarmCard(title: String, body: String) {
    WarmSection(title = title) {
        Text(body, color = TextSecondary, lineHeight = 22.sp)
    }
}

private data class AppStateResult(
    val messages: List<ChatMessage>,
    val memoryItems: List<MemoryItem>,
    val memoryPreview: String,
    val activeCardName: String,
)

private data class ChatResult(
    val messages: List<ChatMessage>,
    val memoryItems: List<MemoryItem>,
    val memoryPreview: String,
    val reply: String,
)

private class JiangJiangApi(private val context: Context) {
    private val prefs = context.getSharedPreferences("jiangjiang", Context.MODE_PRIVATE)
    private val client = OkHttpClient.Builder()
        .connectTimeout(12, TimeUnit.SECONDS)
        .readTimeout(90, TimeUnit.SECONDS)
        .build()
    private var player: MediaPlayer? = null

    var baseUrl: String
        get() = prefs.getString("base_url", "http://192.168.1.2:8765") ?: "http://192.168.1.2:8765"
        set(value) {
            prefs.edit().putString("base_url", value.trim().trimEnd('/')).apply()
        }

    suspend fun fetchState(): AppStateResult = withContext(Dispatchers.IO) {
        val json = getJson("/api/state")
        AppStateResult(
            messages = parseMessages(json.optJSONArray("messages")),
            memoryItems = parseMemoryItems(json),
            memoryPreview = json.optString("memory_preview", "暂无"),
            activeCardName = json.optString("active_card_name", "姜姜"),
        )
    }

    suspend fun chat(message: String, memoryEnabled: Boolean): ChatResult = withContext(Dispatchers.IO) {
        val body = JSONObject()
            .put("message", message)
            .put("memory_enabled", memoryEnabled)
            .put("context_engine_v2", true)
            .put("use_v2_brain", true)
            .put("debug", false)
        val json = postJson("/api/chat", body)
        ChatResult(
            messages = parseMessages(json.optJSONArray("messages")),
            memoryItems = parseMemoryItems(json),
            memoryPreview = json.optString("memory_preview", "暂无"),
            reply = json.optString("reply"),
        )
    }

    suspend fun fetchCards(): List<CharacterCard> = withContext(Dispatchers.IO) {
        val json = getJson("/api/cards")
        val activeId = json.optString("active_card_id")
        val cards = json.optJSONArray("cards") ?: JSONArray()
        buildList {
            for (index in 0 until cards.length()) {
                val card = cards.optJSONObject(index) ?: continue
                val voice = card.optJSONObject("voice")
                add(
                    CharacterCard(
                        id = card.optString("id"),
                        name = card.optString("name", card.optString("id")),
                        prompt = card.optString("system_prompt"),
                        voiceType = voice?.optString("voice_type").orEmpty(),
                        active = card.optString("id") == activeId,
                    ),
                )
            }
        }
    }

    suspend fun selectCard(cardId: String) = withContext(Dispatchers.IO) {
        postJson("/api/cards/select", JSONObject().put("card_id", cardId))
    }

    suspend fun upsertCard(name: String, prompt: String) = withContext(Dispatchers.IO) {
        val id = name.lowercase()
            .replace(Regex("[^a-z0-9\\u4e00-\\u9fa5]+"), "-")
            .trim('-')
            .ifBlank { "android-card-${System.currentTimeMillis()}" }
        val card = JSONObject()
            .put("id", id)
            .put("name", name)
            .put("system_prompt", prompt)
            .put("voice", JSONObject().put("voice_type", "zh_female_vv_uranus_bigtts"))
        postJson("/api/cards/upsert", JSONObject().put("card", card))
    }

    suspend fun transcribe(file: File): String = withContext(Dispatchers.IO) {
        val body = file.readBytes().toRequestBody("audio/mp4".toMediaType())
        val request = Request.Builder()
            .url("${baseUrl}/api/transcribe-audio")
            .post(body)
            .build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("HTTP ${response.code}")
            JSONObject(response.body?.string().orEmpty()).optString("transcript")
        }
    }

    suspend fun speak(text: String) = withContext(Dispatchers.IO) {
        if (text.isBlank()) return@withContext
        val body = JSONObject().put("text", text)
            .toString()
            .toRequestBody("application/json; charset=utf-8".toMediaType())
        val request = Request.Builder()
            .url("${baseUrl}/api/synthesize-audio")
            .post(body)
            .build()
        val bytes = client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("HTTP ${response.code}")
            response.body?.bytes() ?: ByteArray(0)
        }
        if (bytes.isEmpty()) return@withContext
        val file = File(context.cacheDir, "jiangjiang-reply.wav")
        file.writeBytes(bytes)
        withContext(Dispatchers.Main) {
            stopAudio()
            player = MediaPlayer().apply {
                setDataSource(file.absolutePath)
                setOnCompletionListener { stopAudio() }
                prepare()
                start()
            }
        }
    }

    fun stopAudio() {
        player?.let {
            runCatching { it.stop() }
            runCatching { it.release() }
        }
        player = null
    }

    fun release() {
        stopAudio()
    }

    private fun getJson(path: String): JSONObject {
        val request = Request.Builder().url("${baseUrl}${path}").get().build()
        return client.newCall(request).execute().use { response ->
            val raw = response.body?.string().orEmpty()
            if (!response.isSuccessful) throw IOException(raw.ifBlank { "HTTP ${response.code}" })
            JSONObject(raw)
        }
    }

    private fun postJson(path: String, json: JSONObject): JSONObject {
        val request = Request.Builder()
            .url("${baseUrl}${path}")
            .post(json.toString().toRequestBody("application/json; charset=utf-8".toMediaType()))
            .build()
        return client.newCall(request).execute().use { response ->
            val raw = response.body?.string().orEmpty()
            if (!response.isSuccessful) throw IOException(raw.ifBlank { "HTTP ${response.code}" })
            JSONObject(raw)
        }
    }

    private fun parseMessages(array: JSONArray?): List<ChatMessage> {
        if (array == null) return emptyList()
        return buildList {
            for (index in 0 until array.length()) {
                val item = array.optJSONObject(index) ?: continue
                add(ChatMessage(item.optString("role"), item.optString("content")))
            }
        }
    }

    private fun parseMemoryItems(json: JSONObject): List<MemoryItem> {
        val result = mutableListOf<MemoryItem>()
        fun addArray(title: String, key: String, labelKey: String = "label") {
            val array = json.optJSONArray(key) ?: return
            for (index in 0 until array.length()) {
                val item = array.optJSONObject(index) ?: continue
                val label = item.optString(labelKey, title)
                val body = item.optString("value", item.optString("summary", item.toString()))
                result.add(MemoryItem(label.ifBlank { title }, body))
            }
        }
        addArray("Persona", "persona")
        addArray("Preference", "preferences")
        addArray("Recent Event", "events", "summary")
        addArray("Conflict", "conflicts", "summary")
        return result
    }
}

private class AudioRecorder(private val context: Context) {
    private var recorder: MediaRecorder? = null
    private var outputFile: File? = null

    fun start() {
        stopSilently()
        val file = File(context.cacheDir, "jiangjiang-recording.m4a")
        outputFile = file
        val mediaRecorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            MediaRecorder(context)
        } else {
            @Suppress("DEPRECATION")
            MediaRecorder()
        }
        recorder = mediaRecorder.apply {
            setAudioSource(MediaRecorder.AudioSource.MIC)
            setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            setAudioSamplingRate(44100)
            setAudioEncodingBitRate(128000)
            setOutputFile(file.absolutePath)
            prepare()
            start()
        }
    }

    fun stop(): File {
        val file = outputFile ?: throw IOException("No recording file")
        recorder?.let {
            runCatching { it.stop() }
            runCatching { it.release() }
        }
        recorder = null
        outputFile = null
        return file
    }

    fun stopSilently() {
        recorder?.let {
            runCatching { it.stop() }
            runCatching { it.release() }
        }
        recorder = null
        outputFile = null
    }
}
