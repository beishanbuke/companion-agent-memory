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

### 架构升级：v2 双脑模式

v2 架构解决了"路由器调模板"问题，核心改进：

1. **LLM 意图理解** (`intent_engine.py`) - 替代关键词匹配
   - 理解用户真实意图（陪伴/玩笑/建议/执行/安静）
   - 情绪语境分析，不是关键词命中
   - 隐式需求识别

2. **双脑路由** (`dual_brain.py`)
   - **Chat Mode**: 纯陪伴、接话、玩梗、情绪承接
   - **Task Mode**: 学习、饮食、工具调用
   - 自动判断模式切换

3. **角色系统升级** (`persona_v2.py`)
   - 20+ 条真实示例对话（few-shot 风格）
   - 说话习惯、禁忌、梗感定义
   - 关系张力保持

4. **隐式状态跟踪** (`state_tracker.py`)
   - 连续对话模式（吐槽/倾诉/犯贱/规划）
   - 情绪趋势追踪
   - 关系亲密度动态变化

5. **本科生生活能力包** (`life_skills.py`)
   - 饮食分析、学习规划、社交恋爱建议
   - 校园生活工具
   - 真实可执行建议

6. **回复后评审** (`response_judge.py`)
   - 模板味检测
   - 说教检测
   - 自动重写

### 使用 v2 架构

API 请求添加 `use_v2_brain: true`：
```bash
curl -X POST http://127.0.0.1:7897/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "我今天好累", "use_v2_brain": true}'
```

### Companion Agent Core (v2.0) - 统一运行时

```
companion_agent/
├── core.py              # 主 orchestrator (legacy)
├── persona.py           # System Persona Layer (legacy)
├── memory_adapter.py    # Memory Layer Adapter (5层)
├── memory_policy.py     # Memory Update Policy
├── situation_router.py  # Situation Router (10种情境)
├── skill_registry.py    # Skill Registry (3级技能)
├── response_policy.py   # Response Policy
└── v2/                  # v2 架构升级 (本科生陪伴 Agent)
    ├── core_v2.py          # 新 orchestrator (双脑模式)
    ├── llm_runtime.py      # 统一 LLM 运行时
    ├── intent_engine.py    # LLM意图理解 (替代关键词匹配)
    ├── dual_brain.py       # 双脑路由 (chat/task mode)
    ├── persona_v2.py       # 带风格检索的角色系统
    ├── state_tracker.py    # 隐式状态跟踪 (多会话隔离)
    ├── relationship_memory.py # 关系感数据层
    ├── life_skills.py      # 本科生生活能力包
    └── response_judge.py   # 分级重写评审
```

**v2 架构升级（已完成）**：

1. **统一 LLM Runtime** (`llm_runtime.py`)
   - 统一 client / retry / timeout / logging / fallback
   - 支持按任务类型配置不同模型（chat/intent/review/tool）
   - 取代分散在各处的 `openai.AsyncOpenAI`

2. **状态生命周期** (`state_tracker.py`)
   - 多会话隔离（按 session_id）
   - 会话重置：清空所有状态
   - 角色切换：保留亲密度，重置模式和话题
   - LRU 清理防止内存泄漏

3. **关系感数据层** (`relationship_memory.py`)
   - `comfort_style`: 用户喜欢被怎么接话（gentle/direct/balanced）
   - `banter_tolerance`: 互怼容忍度（0-1）
   - `advice_threshold`: 建议接受度（0-1）
   - `humor_mode`: 梗感开关（off/light/active）
   - 从对话中自动学习，不是写死

4. **风格检索系统** (`persona_v2.py`)
   - 不再硬编码塞 5 条示例
   - 按场景检索（情绪承接/犯贱互怼/认真规划/吐槽不求解/恋爱社交）
   - 每轮只注入最相关的 2-3 条，避免 prompt 膨胀

5. **ResponseJudge 分级重写** (`response_judge.py`)
   - 轻问题：只改语气（tone_fix），规则层处理
   - 重问题：整句重写（rewrite），LLM 层处理
   - 记录打回原因，形成 prompt 调优闭环

6. **梗感开关** (`relationship_memory.py`)
   - 综合用户长期偏好 + 当前情绪 + 对话模式
   - 情绪高/认真规划时自动降梗

7. **记忆写入规则** (`core_v2.py`)
   - 编排层只决策，不直接写入
   - 调用方（server.py）统一通过 `commit_memory()` 提交
   - 避免双写和脏历史

### 废弃代码

`prototype_demo/context_engine_v2/` 中的重叠模块已标记为 **LEGACY**：
- `companion_mode.py`, `llm_router.py`, `persona_examples.py`
- `response_reviewer.py`, `skills.py`
- 保留 `context_engine_v3.py` 和 `types.py` 供旧版兼容

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
# - 演示页: http://127.0.0.1:7897
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
curl -X POST http://127.0.0.1:7897/api/companion/status
curl -X POST http://127.0.0.1:7897/api/cards
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
