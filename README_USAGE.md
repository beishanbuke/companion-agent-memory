# Quickstart Usage

这份文档说明 `examples/quickstart` 目录的最简单使用方法。

如果你只想快速跑起来，优先看“启动原型 Demo”这一节。

## 目录说明

- `bot.py`: 官方 quickstart 语音示例
- `prototype_demo/server.py`: 8787 的记忆演示前端
- `prototype_demo/voice_bot.py`: 7860 的 realtime voice backend
- `start_prototype_demo.sh`: 一键启动 `8787 + 7860`

## 环境准备

要求：

- Python 3.10 或更高版本
- 推荐安装 `uv`

安装依赖：

```bash
cd /mnt/dengzhijie/mydata/memory/pipecat/examples/quickstart
uv sync
```

如果目录里已经有可用的 `.venv`，也可以直接使用，不一定要重新执行 `uv sync`。

## 配置 `.env`

先复制模板：

```bash
cp env.example .env
```

最少需要配置这些 key：

```ini
DEEPGRAM_API_KEY=your_deepgram_api_key
OPENAI_API_KEY=your_openai_api_key
CARTESIA_API_KEY=your_cartesia_api_key
```

可选项：

- `MEMORY_LLM_API_KEY` / `MEMORY_LLM_URL` / `MEMORY_LLM_MODEL`
  用于两阶段长期记忆抽取
- `DAILY_API_KEY`
  只在你要接 Daily 时使用

如果你使用的是火山引擎 STT/TTS，而不是 `env.example` 里的默认组合，需要在你自己的 `.env` 里补对应的 VolcEngine 配置。

## 启动原型 Demo

这是当前目录里最推荐的启动方式，会同时拉起：

- `8787`: 记忆演示页面
- `7860`: 语音服务

启动：

```bash
cd /mnt/dengzhijie/mydata/memory/pipecat/examples/quickstart
./start_prototype_demo.sh
```

常用命令：

```bash
./start_prototype_demo.sh status
./start_prototype_demo.sh restart
./start_prototype_demo.sh stop
```

启动后访问：

- 本机打开：
  `http://127.0.0.1:8787`
- 如果跑在远程服务器上：
  `http://<服务器IP>:8787`

语音底层服务地址：

- `http://127.0.0.1:7860/client`

日志位置：

- `prototype_demo/logs/server.log`
- `prototype_demo/logs/voice_bot.log`

## 单独启动基础语音 Bot

如果你不需要 `8787` 的记忆演示页，只想跑一个最基础的 voice bot：

```bash
cd /mnt/dengzhijie/mydata/memory/pipecat/examples/quickstart
uv run bot.py
```

如果你已经有 `.venv`，也可以：

```bash
cd /mnt/dengzhijie/mydata/memory/pipecat/examples/quickstart
./.venv/bin/python bot.py
```

启动后访问：

- `http://127.0.0.1:7860/client`

## 使用流程

原型 Demo 的推荐使用顺序：

1. 打开 `8787` 页面
2. 确认页面显示 voice 服务在线
3. 点击 `Connect` 或 `Mic`
4. 允许浏览器麦克风权限
5. 直接说话，转写和回复会同步显示在页面里

## 常见问题

### 1. 页面能打开，但语音连不上

优先检查：

- `prototype_demo/voice_bot.py` 是否已经启动
- 浏览器是否允许麦克风权限
- 服务器的 `7860` 端口是否可访问
- 是否有防火墙、VPN、内网策略影响 WebRTC

先看状态和日志：

```bash
cd /mnt/dengzhijie/mydata/memory/pipecat/examples/quickstart
./start_prototype_demo.sh status
tail -n 50 prototype_demo/logs/voice_bot.log
```

### 2. 出现 `ICE gathering timed out`

这通常是网络环境导致的 WebRTC candidate 收集不完整，不一定是代码本身错误。

优先排查：

- 服务器是否对外开放了正确地址
- 浏览器和服务器之间是否隔着严格防火墙
- 当前网络是否限制 STUN / WebRTC

### 3. 对方机器拿到项目后能不能直接运行

不建议把 `.venv` 一起打包给别人直接跑。

更稳的方式是：

1. 发送代码
2. 不发送真实 `.env`
3. 让对方执行 `uv sync`
4. 让对方自己填写 `.env`
5. 让对方运行 `./start_prototype_demo.sh`

## 备注

- 如果你修改了前端代码但页面没变化，先强制刷新浏览器缓存。
- 如果是在远程服务器运行，记得开放 `8787` 和 `7860` 相关访问。
