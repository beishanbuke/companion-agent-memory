# 姜姜 - Companion Agent Memory

**姜姜** 是一个本科生陪伴型 AI Agent，具备双脑模式（陪伴/任务）、显式状态机、主线管理和 5 层记忆系统。不是工具调用集合，而是有脾气、有边界、会成长的对话搭子。

## 核心特性

### v2.1 架构升级
- **双脑路由**：Chat Mode（纯陪伴/接话/玩梗）vs Task Mode（学习/饮食/工具调用）
- **显式状态机**：7 种状态（light_chat / support_crisis / pushable_low / task_exec / task_done / quiet / clarify）
- **主线管理**：前台/后台/休眠主线，自动话题切换和主线恢复
- **策略规划器**：每轮显式策略（goal / pull_main_thread / allow_humor / allow_advice / tool_calls）
- **关系记忆**：每轮学习用户偏好（接话风格/互怼容忍度/建议阈值/梗感），持久化到 JSON

### 记忆系统（5 层）
- **profile**: 用户档案 - 稳定事实
- **preferences**: 用户偏好 - 可带场景/极性
- **long_term_goals**: 长期目标
- **episodic_events**: 事件记忆 - 时间线记录
- **safety_notes**: 安全笔记 - 敏感/重要标记

### 本科生生活能力包
- **饮食分析**：当前时段推荐 + 克制提醒（不是无限纵容）
- **学习规划**：自然语言任务解析 → 微计划（15分钟起步）
- **社交回复**：情感回复建议 + 拒绝脚本 + 边界检查

### 技能系统（3 级）
- **Tier 1**: emotional-companion, memory-manager, safety-handler
- **Tier 2**: music-dj, study-coach, coding-helper, planning-helper
- **Tier 3**: tool-caller (MCP)

## 快速启动

### 环境准备

```bash
# 克隆仓库
git clone https://github.com/beishanbuke/companion-agent-memory.git
cd companion-agent-memory

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
# 一键启动（演示页 + 语音服务）
./start_prototype_demo.sh

# 服务地址：
# - 演示页: http://127.0.0.1:7897
# - 语音客户端: http://127.0.0.1:7860/client
```

## 架构文档

### v2 架构总览

```
companion_agent/
├── core_v2.py              # 主编排器（状态机版）
├── v2/
│   ├── intent_engine.py    # LLM意图理解（信号提取器）
│   ├── state_tracker.py    # 显式状态机
│   ├── thread_manager.py   # 前台/后台主线管理
│   ├── policy_planner.py   # 策略规划器
│   ├── context_assembler.py # 渐进式上下文装配
│   ├── tool_contract.py    # 工具注册与执行
│   ├── llm_runtime.py      # 统一 LLM 运行时
│   ├── persona_v2.py       # 带风格检索的角色系统
│   ├── relationship_memory.py # 关系感数据层
│   ├── life_skills.py      # 本科生生活能力包
│   └── response_judge.py   # 回复后评审
```

### v2 处理流程

```
用户消息
  → IntentEngine（信号提取）
    → ThreadManager（话题切换检测）
      → StateTracker（显式状态机转移）
        → PolicyPlanner（本轮策略决策）
          → MemoryAdapter（记忆检索）
            → ToolRegistry（工具执行）
              → ContextAssembler（渐进式装配）
                → LLMRuntime（生成回复）
                  → ResponseJudge（回复评审）
                    → RelationshipMemory（关系学习）
                      → 返回回复
```

### 显式状态机

| 状态 | 触发条件 | 行为约束 |
|------|----------|----------|
| `light_chat` | 情绪稳定，无紧急任务 | 自然接话，允许玩梗 |
| `support_crisis` | 情绪强度 > 0.7 | 只陪伴，不给建议，不玩梗 |
| `pushable_low` | 低能量但 action_receptivity > 0.3 | 先共情，再试探性建议 |
| `task_exec` | 明确任务 + urgency > 0.5 | 专注高效，完成后过渡 |
| `task_done` | 任务刚完成 | 正向反馈，自然回到闲聊 |
| `quiet` | 用户明确想安静 | 简短回复，温暖收尾 |
| `clarify` | clarification_confidence > 0.6 | 礼貌请用户说明 |

### 信号提取器（IntentEngine）

除基础意图外，提取 5 个关键信号：
- **action_receptivity**: 0-1，用户接受行动的意愿
- **topic_shift_type**: emotional_escape / functional_detour / new_thread / return_to_thread / none
- **pressure_signal**: 0-1，压力信号强度
- **thread_candidates**: 可能的主线话题列表
- **clarification_confidence**: 0-1，是否需要澄清

### 主线管理（ThreadManager）

- **前台主线**：当前对话焦点，只有一个
- **后台主线**：最多保留 3 个，分数衰减
- **休眠主线**：超出容量后降级
- **拉回规则**：light_chat 状态下，后台存在高压未解决主线，用户情绪稳定时自动拉回

### 关系记忆（RelationshipMemory）

每轮学习并持久化：
- **comfort_style**: gentle / direct / balanced
- **banter_tolerance**: 0-1，互怼容忍度
- **advice_threshold**: 0-1，建议接受度
- **humor_mode**: off / light / active

文件：`relationship_memory_{user_id}.json`

## API 接口

### 对话接口

```bash
# 流式对话（推荐）
POST /api/chat-stream
Body: { "message": "用户消息", "memory_enabled": true, "use_v2_brain": true }

# 非流式对话
POST /api/chat
Body: { "message": "用户消息", "memory_enabled": true, "use_v2_brain": true }
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
```

### Agent 状态

```bash
# 获取 v2 状态
POST /api/companion/status
```

## 开发规范

### 修改记忆模块
**禁止直接修改 `memory/` 目录。** 通过 `MemoryLayerAdapter` 操作：
```python
from companion_agent.memory_adapter import MemoryLayerAdapter
adapter = MemoryLayerAdapter(memory_engine)
context = await adapter.retrieve_tiered(query="...")
```

### 新增工具
在 `companion_agent/v2/tool_contract.py` 中注册 `ToolContract`：
```python
MY_TOOL = ToolContract(
    name="my_tool",
    description="工具描述",
    tool_type="reasoning",  # reasoning / lookup / action
    input_schema={...},
    output_schema={...},
)
```

### 修改前端
1. 编辑 `prototype_demo/static/index.html` 结构
2. 编辑 `prototype_demo/static/styles.css` 样式
3. 编辑 `prototype_demo/static/app.js` 逻辑
4. 确保 DOM ID 与 JS 中的 `document.getElementById` 匹配

## 项目结构

```
├── companion_agent/              # Agent Core 模块
│   ├── core.py                   # 旧版 orchestrator
│   ├── core_v2.py                # v2 状态机编排器
│   ├── v2/                       # v2 架构组件
│   │   ├── intent_engine.py
│   │   ├── state_tracker.py
│   │   ├── thread_manager.py
│   │   ├── policy_planner.py
│   │   ├── context_assembler.py
│   │   ├── tool_contract.py
│   │   ├── llm_runtime.py
│   │   ├── persona_v2.py
│   │   ├── relationship_memory.py
│   │   ├── life_skills.py
│   │   └── response_judge.py
│   ├── memory_adapter.py         # 记忆适配器
│   ├── memory_policy.py          # 记忆更新策略
│   ├── situation_router.py       # 情境路由
│   └── skill_registry.py         # 技能注册表
│
├── memory/                       # 记忆引擎（不可修改）
│   └── structured.py             # 核心结构化记忆
│
├── prototype_demo/               # 演示服务
│   ├── server.py                 # HTTP 服务器
│   ├── voice_bot.py              # WebRTC 语音服务
│   ├── static/                   # 前端文件
│   └── logs/
│
├── prototype_demo/context_engine_v2/  # 上下文引擎（legacy）
├── mcp/                          # MCP 工具目录
├── tests/                        # 测试用例
├── env.example                   # 环境变量模板
├── start_prototype_demo.sh       # 启动脚本
├── .gitignore                    # Git 忽略规则
└── README.md                     # 本文件
```

## 安全与隐私

1. **不伪装人类** - Agent 明确声明自己是 AI
2. **不制造依赖** - 鼓励用户寻求真人社交
3. **记忆透明** - 用户可查看、修改、删除任何记忆
4. **敏感确认** - 健康/财务/身份类信息存储前需确认
5. **危机降级** - 检测到自伤/伤害风险时提供专业热线

## 更新日志

### v2.1 - 状态机与主线管理
- 新增显式状态机（7 种状态）
- 新增前台/后台主线管理
- 新增策略规划器（TurnPolicy）
- 关系记忆支持持久化和 per-session 隔离
- 统一 LLMRuntime 接管所有 v2 LLM 调用

### v2.0 - Companion Agent Core 重构
- 5 层记忆架构
- 情境路由（10 种情境）
- 双脑模式（chat/task）
- 角色卡系统
- 本科生生活能力包

## 许可证

私有项目，未经授权不得使用。

## 联系方式

如有问题或建议，请联系项目维护者。
