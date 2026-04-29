# Companion Agent Memory - 项目长期记忆

> 本文档供 AI Agent 执行操作时参考，包含项目架构、凭据、开发规范等关键上下文。

## 项目基础信息

- **名称**: 姜姜 (Companion Agent Memory)
- **类型**: 长期陪伴型 AI Agent
- **仓库**: https://github.com/beishanbuke/companion-agent-memory (私密)
- **本地路径**: `/Users/niuniu/Downloads/quickstart`
- **Git 分支**: `main`
- **远程**: `git@github.com:beishanbuke/companion-agent-memory.git` (SSH)

## 凭据信息

### GitHub SSH
- **用户名**: beishanbuke
- **SSH 私钥**: `~/.ssh/id_ed25519`
- **SSH 公钥**: `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM50g7oCLMreVSrfQZHoOqis2JQM1vcFXmz1GiGtaTVg beishanbuke@github.com`
- **known_hosts**: 已添加 github.com

### Git 配置
```bash
git config user.email "beishanbuke@github.com"
git config user.name "姜姜"
git remote -v
# origin  git@github.com:beishanbuke/companion-agent-memory.git (fetch)
# origin  git@github.com:beishanbuke/companion-agent-memory.git (push)
```

> **注意**: GitHub Token 存储在 macOS 钥匙串中，需通过 GUI 访问。Token 权限：repo (完整仓库访问)

### 环境变量 (.env)
关键配置项（请勿提交到 git）：
- `OPENAI_API_KEY` - LLM API
- `DEEPGRAM_API_KEY` - 语音识别
- `VOLCENGINE_APP_ID` / `VOLCENGINE_ACCESS_KEY` - 火山引擎语音
- `MEMORY_LLM_API_KEY` / `MEMORY_LLM_URL` - 记忆抽取 LLM（可选）

## 技术架构

### Companion Agent Core (v2.0)

```
companion_agent/
├── core.py              # 主 orchestrator
├── persona.py           # System Persona Layer
├── memory_adapter.py    # Memory Layer Adapter (5层)
├── memory_policy.py     # Memory Update Policy
├── situation_router.py  # Situation Router (10种情境)
├── skill_registry.py    # Skill Registry (3级技能)
└── response_policy.py   # Response Policy
```

### 记忆 5 层模型
1. **profile**: 用户档案 (persona_slots)
2. **preferences**: 用户偏好 (preference_slots + profiles)
3. **long_term_goals**: 长期目标
4. **episodic_events**: 事件记忆
5. **safety_notes**: 安全笔记

### 情境分类 (10种)
- casual_chat, emotional_support, planning
- music_companion, learning_coach, coding_helper
- memory_query, tool_task, safety_sensitive, personal_routine

### 技能 3 级
- **Tier 1**: emotional-companion, memory-manager, safety-handler
- **Tier 2**: music-dj, study-coach, coding-helper, planning-helper
- **Tier 3**: tool-caller (MCP)

## 核心模块（不可修改）

### memory/ 目录
**规则**: 只能通过 `companion_agent/memory_adapter.py` 访问，**绝不直接修改**。

- `structured.py` - StructuredLongTermMemory (2029 行)
- `base.py` - BaseMemory 接口
- `simple.py` - SimpleMemory (FIFO)
- `semantic.py` - HashingEmbedder
- `llm_extractor.py` - LLM 记忆提取
- `update_resolver.py` - 写入冲突解决

### context_engine.py
上下文打包引擎，负责：
- 场景路由 (scene routing)
- 记忆过滤 (memory filters)
- 历史窗口管理

## API 端点

### 对话
- `POST /api/chat-stream` - 流式对话
- `POST /api/chat` - 非流式对话
- Body: `{ message, memory_enabled }`

### 记忆
- `POST /api/memory/retrieve` - 检索
- `POST /api/memory/store` - 存储
- `POST /api/memory/delete` - 删除

### 角色卡
- `GET /api/cards` - 列表
- `POST /api/cards/select` - 切换
- `POST /api/cards/upsert` - 创建/更新
- `POST /api/cards/delete` - 删除

### Agent 状态
- `POST /api/companion/status` - Agent 状态
- `POST /api/companion/situations` - 情境/技能列表

### 其他
- `POST /api/reset-session` - 重置会话
- `POST /api/clear-memory` - 清空记忆
- `POST /api/voice-status` - 语音状态

## 前端结构

```
prototype_demo/static/
├── index.html    # 主页面 (温馨暖色调 UI)
├── styles.css    # Cormorant Garamond + DM Sans 字体
└── app.js        # 前端逻辑
```

**UI 特性**:
- 顶部：品牌名"姜姜" + Memory 开关 + 状态
- 左侧：对话区 (聊天流 + 语音连接 + 输入框)
- 右侧：记忆看板 (对话角色 + Persona + Preference + Events)
- 底部：新建角色卡 (命名 + 音色 + 描述 + 预览)

**前端元素 ID**:
- `chatStream`, `messageInput`, `sendBtn`
- `memoryPanel`, `personaGrid`, `preferenceGrid`
- `characterList`, `characterCardSelect`
- `characterCardNameInput`, `characterCardVoiceSelect`, `characterCardDescriptionInput`
- `situationBadge`, `memoryUsageBadge`

## 启动命令

```bash
# 一键启动
cd /Users/niuniu/Downloads/quickstart
./start_prototype_demo.sh

# 常用
./start_prototype_demo.sh status    # 查看状态
./start_prototype_demo.sh restart   # 重启
./start_prototype_demo.sh stop      # 停止

# 服务地址
# - 演示页: http://127.0.0.1:8787
# - 语音: http://127.0.0.1:7860/client
```

## 开发规范

### 修改记忆模块
**禁止直接修改 `memory/` 目录。** 通过 `MemoryLayerAdapter` 操作：
```python
from companion_agent.memory_adapter import MemoryLayerAdapter
adapter = MemoryLayerAdapter(memory_engine)
context = await adapter.retrieve_tiered(query="...")
```

### 新增情境
在 `companion_agent/situation_router.py` 的 `SITUATIONS` 中添加配置。

### 新增技能
在 `companion_agent/skill_registry.py` 中注册 Skill 对象。

### 修改前端
1. 编辑 `prototype_demo/static/index.html` 结构
2. 编辑 `prototype_demo/static/styles.css` 样式
3. 编辑 `prototype_demo/static/app.js` 逻辑
4. 确保 DOM ID 与 JS 中的 `document.getElementById` 匹配

### 提交代码
```bash
git add .
git commit -m "type: 描述"
git push origin main
```

## 关键设计决策

1. **不修改 memory/ 模块** - 使用 Adapter 模式封装
2. **删除 NCP 输入** - Agent 自动推断工具和技能
3. **温馨暖色调 UI** - Cormorant Garamond + DM Sans，奶油白背景
4. **角色卡管理** - 记忆面板上方显示角色列表，底部只保留新建
5. **删除角色需二次确认** - 防止误操作
6. **安全边界** - 不伪装人类、不制造依赖、敏感信息需确认

## 常见操作

### 重启服务
```bash
./start_prototype_demo.sh restart
```

### 查看日志
```bash
tail -f prototype_demo/logs/server.log
tail -f prototype_demo/logs/voice_bot.log
```

### 检查 API
```bash
curl -X POST http://127.0.0.1:8787/api/companion/status
curl -X POST http://127.0.0.1:8787/api/cards
```

### 清理记忆文件
```bash
rm prototype_memory_store.json
rm prototype_character_cards.json
```

## 项目依赖

主要依赖（见 `pyproject.toml`）：
- `openai` - LLM API 客户端
- `websockets` - WebSocket 连接
- `numpy` - 向量化计算
- `scipy` - 科学计算

安装：
```bash
uv sync
```

## 注意事项

1. `.env` 和敏感文件已加入 `.gitignore`，不会提交到仓库
2. 语音服务 (`voice_bot.py`) 需要单独启动
3. 首次启动可能需要 ~20 秒加载模型
4. 记忆文件 (`prototype_memory_store.json`) 是本地 JSON，无需数据库

## 更新历史

- **v2.0** - Companion Agent Core 重构：5层记忆、情境路由、人格管理
- **v1.x** - 基础记忆演示：Persona/Preference/Events/Conflicts

---

*最后更新: 2026-04-29*
*维护者: 姜姜*
