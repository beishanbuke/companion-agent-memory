# 快速开始（收到压缩包的同学看这里）

本包已包含全部代码和配置好 key 的 `.env`，理论上三步即可跑起来。

## 环境要求

- macOS 或 Linux（Windows 建议在 WSL 里跑）
- Python 3.10+
- [uv](https://docs.astral.sh/uv/)（包管理器，安装依赖用）

## 三步启动

```bash
# 1. 解压（如果还没解压；文件名以实际收到的为准）
tar -xzf companion-agent-memory-share-20260814.tar.gz
cd companion-agent-memory

# 2. 安装依赖（首次约需几分钟，会自动创建 .venv）
uv sync

# 3. 一键启动
./start_prototype_demo.sh
```

启动成功后访问：

- **演示页面**: http://127.0.0.1:8787 （文字对话 + 记忆看板）
- **语音服务**: http://127.0.0.1:7860/client （可选，浏览器需允许麦克风）

## 常用命令

```bash
./start_prototype_demo.sh status    # 查看运行状态
./start_prototype_demo.sh restart   # 重启
./start_prototype_demo.sh stop      # 停止
```

## 说明与注意

1. `.env` 已包含可用的 API key，请勿外传、勿提交到任何公开仓库。
2. 首次启动需要加载模型，约 20 秒，请耐心等待。
3. 记忆数据保存在项目根目录 `prototype_memory_store.json`（首次运行自动生成），删除该文件即清空记忆。
4. 如果只想跑文字对话，`voice_bot` 起不来不影响 8787 页面使用。
5. 更多细节见 `README_USAGE.md` 和 `AGENTS.md`（注意：那两份文档里的绝对路径是原作者机器的，以本文为准）。

## 常见问题

- **`Missing virtualenv python`**: 先执行 `uv sync` 创建 `.venv`。
- **`uv: command not found`**: `curl -LsSf https://astral.sh/uv/install.sh | sh` 后重开终端。
- **页面能开但语音连不上**: 检查 `./start_prototype_demo.sh status`，看日志 `prototype_demo/logs/voice_bot.log`，并确认浏览器麦克风权限。
- **改了前端没生效**: 强制刷新浏览器缓存（Cmd+Shift+R）。
