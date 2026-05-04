# 姜姜 Android

原生 Android 客户端，Kotlin + Jetpack Compose。目标设备支持 Android 13，包名：

```text
com.beishanbuke.jiangjiang
```

## 当前能力

- 聊天：对接后端 `POST /api/chat`
- 语音输入：本机录音后上传 `POST /api/transcribe-audio`
- 回复朗读：调用 `POST /api/synthesize-audio` 并在手机播放 WAV
- 记忆看板：读取 `GET /api/state`
- 角色卡：读取、切换、创建角色卡，对接 `/api/cards/*`
- 同 Wi-Fi 调试：App 内可配置后端地址

## 同 Wi-Fi 调试

1. 在电脑上启动后端：

   ```bash
   ./start_prototype_demo.sh restart
   ```

2. 找到电脑局域网 IP，例如 macOS：

   ```bash
   ipconfig getifaddr en0
   ```

3. 确认手机和电脑连在同一个 Wi-Fi。

4. 用 Android Studio 打开本目录 `android/`，运行到手机。

5. 打开 App 的「设置」，把后端地址改成：

   ```text
   http://电脑局域网IP:8765
   ```

   例如：

   ```text
   http://192.168.1.23:8765
   ```

## 注意

- 不要把 OpenAI/Kimi/火山/Deepgram 等密钥放进 Android App。App 只连接你的本地后端，密钥继续留在后端 `.env`。
- 当前为局域网调试版，`AndroidManifest.xml` 已启用 cleartext HTTP 以支持 `http://局域网IP:8765`。
- 发布正式版时建议改为 HTTPS 后端，并关闭全局 cleartext。
