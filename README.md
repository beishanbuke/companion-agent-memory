# 姜姜 - Companion Agent Core

## 项目概述

**姜姜** 是一个长期陪伴型 AI Agent，具备分层记忆管理、情境路由、人格管理和技能系统。

### 核心特性

- **分层记忆系统** (5 层)：用户档案、偏好、长期目标、事件记忆、安全笔记
- **情境路由**：自动识别 10 种对话情境并路由到对应处理逻辑
- **人格管理**：支持多角色卡切换，每个角色有独立的语音音色和描述
- **记忆策略**：智能决策是否存储、更新或删除记忆，支持隐私保护
- **技能系统**：3 级技能架构（内置/领域/外部），可动态扩展
- **安全边界**：不伪装人类、不制造情感依赖、敏感信息需确认

## 技术栈

- **Backend**: Python 3.10+, FastAPI-style HTTP server
- **Memory Engine**: StructuredLongTermMemory (JSON-based, local)
- **LLM**: OpenAI-compatible API (GPT-4o-mini / 自定义端点)
- **Voice**: VolcEngine TTS + WebRTC real-time voice
- **Frontend**: Vanilla HTML/CSS/JS (无框架依赖)

## 快速启动

### 环境准备

```bash
# 安装依赖
uv sync

# 配置环境变量
cp env.example .env
# 编辑 .env 填入：
# - OPENAI_API_KEY
# - DEEPGRAM_API_KEY (语音识别)
# - VOLCENGINE_APP_ID / VOLCENGINE_ACCESS_KEY (语音合成)
```

### 启动服务

```bash
# 一键启动（记忆演示页 + 语音服务）
./start_prototype_demo.sh

# 服务地址：
# - 记忆演示页: http://127.0.0.1:8787
# - 语音客户端: http://127.0.0.1:7860/client
```

## 架构文档

### Companion Agent Core 架构

```
CompanionAgentCore
├── SystemPersonaLayer          # 固定人格、语气、安全规则
├── MemoryLayerAdapter          # 5层记忆读取接口 (Adapter模式)
├── MemoryUpdatePolicy          # 每轮记忆更新决策
├── SituationRouter             # 意图分类与路由
├── SkillRegistry               # 技能加载与执行
└── ResponsePolicy              # 响应编排
```

### 记忆 5 层模型

- **profile**: 用户档案 (persona_slots) - 稳定事实
- **preferences**: 用户偏好 (preference_slots + profiles) - 可带场景/极性
- **long_term_goals**: 长期目标 - 从事件和显式目标中提取
- **episodic_events**: 事件记忆 - 时间线记录
- **safety_notes**: 安全笔记 - 敏感/重要标记记忆

### 10 种情境分类

1. `casual_chat` - 普通聊天
2. `emotional_support` - 情绪陪伴
3. `planning` - 计划制定
4. `music_companion` - 音乐推荐/播放
5. `learning_coach` - 学习辅导
6. `coding_helper` - 编程帮助
7. `memory_query` - 记忆查询 ("你还记得吗")
8. `tool_task` - 工具调用
9. `safety_sensitive` - 安全敏感
10. `personal_routine` - 日常生活

### 技能 3 级体系

- **Tier 1 (内置)**: emotional-companion, memory-manager, safety-handler
- **Tier 2 (领域)**: music-dj, study-coach, coding-helper, planning-helper
- **Tier 3 (外部)**: tool-caller (MCP)

## API 接口

### 对话接口

```bash
# 流式对话
POST /api/chat-stream
Body: { "message": "用户消息", "memory_enabled": true }

# 非流式对话
POST /api/chat
Body: { "message": "用户消息", "memory_enabled": true }
```

### 记忆接口

```bash
# 检索记忆
POST /api/memory/retrieve
Body: { "query": "查询", "limit": 6 }

# 存储记忆
POST /api/memory/store
Body: { "role": "user", "content": "内容" }

# 删除记忆
POST /api/memory/delete
Body: { "memory_id": "xxx" }
```

### 角色卡接口

```bash
# 获取角色卡列表
GET /api/cards

# 切换角色
POST /api/cards/select
Body: { "card_id": "xxx" }

# 创建/更新角色
POST /api/cards/upsert
Body: { "card": { "id": "", "name": "", "system_prompt": "", "voice": {...} } }

# 删除角色
POST /api/cards/delete
Body: { "card_id": "xxx" }
```

### Agent 状态接口

```bash
# 获取 Agent 状态
POST /api/companion/status

# 获取情境和技能列表
POST /api/companion/situations
```

## 项目结构

```
├── companion_agent/              # Companion Agent Core 模块
│   ├── __init__.py
│   ├── core.py                   # 主 orchestrator
│   ├── persona.py                # 人格层
│   ├── memory_adapter.py         # 记忆适配器 (5层模型)
│   ├── memory_policy.py          # 记忆更新策略
│   ├── situation_router.py       # 情境路由
│   ├── skill_registry.py         # 技能注册表
│   └── response_policy.py        # 响应策略
│
├── memory/                       # 记忆引擎 (不可修改)
│   ├── __init__.py
│   ├── base.py
│   ├── structured.py             # 核心结构化记忆实现
│   ├── simple.py
│   ├── semantic.py
│   ├── llm_extractor.py
│   └── update_resolver.py
│
├── prototype_demo/               # 演示服务
│   ├── server.py                 # HTTP 服务器 + Session 管理
│   ├── voice_bot.py              # WebRTC 语音服务
│   ├── static/                   # 前端文件
│   │   ├── index.html
│   │   ├── styles.css
│   │   └── app.js
│   └── logs/
│
├── context_engine.py             # 上下文打包引擎
├── mcp/                          # MCP 工具目录
├── tests/                        # 测试用例
├── env.example                   # 环境变量模板
├── start_prototype_demo.sh       # 启动脚本
└── README.md                     # 本文件
```

## 更新日志

### v2.0 - Companion Agent Core 重构

**新增模块**

- [x] `companion_agent/` - 完整的 Agent Core 架构
- [x] System Persona Layer - 固定人格 + 安全规则
- [x] Memory Layer Adapter - 5层记忆读取接口
- [x] Memory Update Policy - 智能记忆更新决策
- [x] Situation Router - 10种情境自动分类
- [x] Skill Registry - 3级技能体系
- [x] Response Policy - 响应编排与安全检查

**前端改进**

- [x] 温馨暖色调 UI (Cormorant Garamond + DM Sans)
- [x] 角色卡可视化预览 + 图片下载
- [x] 对话角色列表（记忆面板上方）
- [x] 情境标签显示 (如：情绪陪伴 85%)
- [x] 删除 NCP 独立输入（由 Agent 自动推断）

**后端改进**

- [x] 集成 CompanionAgentCore 到 DemoSession
- [x] 新增 `/api/companion/status` 和 `/api/companion/situations`
- [x] 删除 NCP 相关代码（build_ncp_payload 等）
- [x] 新增 `/api/cards/delete` 接口
- [x] 响应中增加 companion 元数据（情境、记忆决策、技能激活）

**设计原则**

- 不修改 `memory/` 模块（Adapter 模式）
- 每轮对话自动决策记忆更新
- 敏感记忆需要用户确认
- 安全降级策略（危机场景）

## 开发规范

### 记忆模块保护

**不可修改 `memory/` 目录下的任何文件。** 所有记忆操作通过 `companion_agent/memory_adapter.py` 的适配器完成。

### 新增技能

在 `companion_agent/skill_registry.py` 中注册：

```python
self.register(Skill(
    name="my-skill",
    description="技能描述",
    tier=2,
    situations=["casual_chat"],
    handler=my_handler,  # 可选
))
```

### 新增情境

在 `companion_agent/situation_router.py` 的 `SITUATIONS` 中添加：

```python
"my_situation": {
    "description": "描述",
    "keywords": ["关键词"],
    "retrieve_memory": True,
    "memory_tiers": ["profile", "preferences"],
    "skills": ["my-skill"],
    "call_tools": False,
    "style": "casual",
}
```

## 安全与隐私

1. **不伪装人类** - Agent 明确声明自己是 AI
2. **不制造依赖** - 鼓励用户寻求真人社交
3. **记忆透明** - 用户可查看、修改、删除任何记忆
4. **敏感确认** - 健康/财务/身份类信息存储前需确认
5. **危机降级** - 检测到自伤/伤害风险时提供专业热线

## 许可证

私有项目，未经授权不得使用。

## 联系方式

如有问题或建议，请联系项目维护者。
