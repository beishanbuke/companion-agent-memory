# Companion Agent Memory 机制技术文档

更新时间：2026-05-12

本文介绍 `companion-agent-memory` 项目的记忆机制。范围包括底层 `memory/` 引擎、Companion Agent 的五层记忆适配、Web Demo/语音 Demo 的接入方式，以及写入、更新、冲突处理、检索和提示词注入的完整链路。

## 1. 总体结论

这个项目的记忆系统分成两层：

- 底层记忆引擎：`memory/` 目录，实现统一的 `BaseMemory` 接口，负责抽取、写入、更新、检索、删除和 JSON 持久化。
- Agent 编排层：`companion_agent/` 和 `prototype_demo/`，负责判断当前对话是否需要记忆、把底层记忆整理成更适合陪伴型 Agent 使用的五层上下文，再注入给 LLM。

当前主力长期记忆实现是 `StructuredLongTermMemory`。它不是简单保存聊天记录，而是把用户消息转成结构化长期记忆：

- `persona`：用户稳定事实，例如姓名、职业、年龄、所在城市、关系状态。
- `preference`：用户偏好，例如饮品、食物、口味、音乐、活动、社交方式、居住偏好。
- `event`：可回忆事件，例如搬家、工作变化、关系变化、情绪事件、长期困扰。

Companion 层又把这些底层结构映射成五层陪伴型记忆：

- `profile`：用户档案。
- `preferences`：用户偏好。
- `long_term_goals`：长期目标。
- `episodic_events`：事件时间线。
- `safety_notes`：安全/敏感记忆。

## 2. 关键文件地图

| 文件 | 作用 |
| --- | --- |
| `memory/base.py` | 定义可插拔记忆接口：`store`、`retrieve`、`clear`。 |
| `memory/simple.py` | 简单短期记忆，保存最近 N 轮对话到 JSON，主要用于 CLI 示例。 |
| `memory/structured.py` | 核心长期记忆引擎，负责结构化抽取、更新、冲突处理、检索和持久化。 |
| `memory/semantic.py` | 本地 hashing embedding 和相似度计算，无需外部向量库。 |
| `memory/llm_extractor.py` | 可选的 LLM 记忆候选抽取器。 |
| `memory/update_resolver.py` | 可选的 LLM 写入冲突决策器。 |
| `memory_processor.py` | Pipecat pipeline 中的记忆注入处理器。 |
| `companion_agent/memory_adapter.py` | 把 `StructuredLongTermMemory` snapshot 映射成五层陪伴记忆。 |
| `companion_agent/memory_policy.py` | 每轮用户消息的记忆写入策略：add/update/delete/ignore。 |
| `companion_agent/core.py` | Agent 总编排：情境路由、记忆检索、技能、提示词、记忆写入。 |
| `prototype_demo/server.py` | Web Demo HTTP 服务、Session、记忆 API、前端记忆面板。 |
| `prototype_demo/http_memory.py` | 语音服务到 Web Demo 共享记忆服务的 HTTP bridge。 |
| `prototype_demo/voice_bot.py` | 语音 pipeline，使用 `HTTPMemoryBackend` 和 `MemoryProcessor`。 |

## 3. 统一接口：BaseMemory

所有记忆后端都实现 `BaseMemory`：

```python
async def store(role: str, content: str) -> None
async def retrieve(query: str = "", filters: dict | None = None, limit: int = 6) -> str
async def clear() -> None
```

这个接口让上层 pipeline 不关心底层实现。`SimpleMemory`、`StructuredLongTermMemory`、`HTTPMemoryBackend` 都能被同一个 `MemoryProcessor` 或 Agent Core 使用。

## 4. 两类记忆实现

### 4.1 SimpleMemory

`SimpleMemory` 是最小可用版本：

- 保存最近 `max_turns * 2` 条 user/assistant 消息。
- 默认落盘到 `memory_store.json`。
- `retrieve()` 返回完整历史文本，格式以 `[Conversation history from previous turns]` 开头。
- 不做结构化抽取、冲突管理或语义检索。

它主要用于 `chat.py` 的 CLI 演示。注意：`chat.py` 目前是示例代码，凭据管理方式不适合生产使用，真实服务应从 `.env` 读取 API key。

### 4.2 StructuredLongTermMemory

`StructuredLongTermMemory` 是当前项目的核心长期记忆引擎：

- 只处理 `role == "user"` 的内容，assistant 回复不会进入长期记忆。
- 默认落盘到 `long_term_memory_store.json`，Web Demo 使用 `prototype_memory_store.json`。
- 使用 LLM 抽取和本地规则抽取结合的方式生成候选记忆。
- 使用本地保守策略和可选 LLM resolver 决定 add/update/delete/noop。
- 保存 slot 当前值、偏好历史、事件列表、冲突记录和本地 embedding。
- 支持按 query、memory type、slot key、scene 做检索和重排。

## 5. 底层数据模型

`memory/structured.py` 里的核心数据结构如下。

### 5.1 SlotValue

用于当前有效的单值 slot，例如 `name`、`occupation`、`home_city`：

```python
{
  "key": "home_city",
  "value": "杭州",
  "updated_at": "...",
  "source_memory_id": "...",
  "confidence": 1.0,
  "first_seen_at": "..."
}
```

`persona_slots` 和兼容用的 `preference_slots` 都是这种结构。

### 5.2 PreferenceProfileItem

用于更细粒度的偏好画像。它解决了“偏好不是简单覆盖”的问题。

例如用户先说：

```text
我喜欢拿铁和美式
```

后来又说：

```text
我现在讨厌拿铁了
```

系统会把复合偏好拆开，最终保留：

- `喜欢美式`
- `不喜欢拿铁`

而不是把整个饮品偏好粗暴覆盖掉。

字段包括：

- `key`：偏好槽位，例如 `favorite_beverage`。
- `value`：原始偏好值，例如 `喜欢美式`。
- `normalized_value`：归一化主体，例如 `美式`。
- `polarity`：`positive`、`negative`、`neutral`。
- `scope`：作用范围，例如 `global`、`breakfast`、`nighttime`。
- `status`：`active`、`historical`、`deleted`。
- `evidence_count`：重复证据次数。

### 5.3 MemoryItem

所有写入的长期记忆都会有一条 `MemoryItem`：

```python
{
  "id": "mem_xxx",
  "memory_type": "persona | preference | event",
  "summary": "...",
  "content": "...",
  "role": "user",
  "created_at": "...",
  "updated_at": "...",
  "slot_key": "favorite_beverage",
  "value": "喜欢美式",
  "status": "active",
  "tags": ["food"],
  "metadata": {},
  "vector": [...]
}
```

其中 `vector` 由本地 hashing embedder 生成，不依赖外部 embedding 服务。

### 5.4 ConflictRecord

当 slot 被更新、删除或偏好被替换时，会记录冲突：

```python
{
  "slot_key": "home_city",
  "previous_value": "上海",
  "new_value": "杭州",
  "resolved_to": "杭州",
  "resolved_at": "...",
  "reason": "local_update"
}
```

这让前端可以展示“之前是什么、后来变成了什么”，也方便 debug。

### 5.5 持久化 JSON

当前存储文件版本是 `version: 3`，结构大致如下：

```json
{
  "version": 3,
  "persona_slots": {},
  "preference_slots": {},
  "preference_profiles": {},
  "conflicts": [],
  "memories": []
}
```

`_load()` 会兼容旧格式，并在缺少 `preference_profiles` 时从旧的 `preference_slots` 做迁移。

## 6. 写入流程

长期记忆写入不是“把用户原话全存下来”，而是先抽取候选，再决策如何写入。

整体流程：

```text
用户消息
  -> MemoryUpdatePolicy.evaluate()        # Companion/Web Demo 层，可选前置门控
  -> StructuredLongTermMemory.store()
  -> 抽取候选记忆：LLM extractor + 本地规则
  -> 去重、扩展偏好、补事件
  -> 写入决策：本地 resolver + 可选 LLM resolver
  -> add / update / delete / noop
  -> 更新 slot、preference profile、memory item、conflict
  -> trim + save JSON
```

### 6.1 Companion 层的前置策略

Web Demo 走 `CompanionAgentCore.process_message()`，它会先用 `MemoryUpdatePolicy` 判断用户消息：

- `add`：新增长期有用信息。
- `update`：修改已有信息。
- `delete`：明确要求忘记或删除。
- `ignore`：日常寒暄、一次性信息、低价值内容。

敏感信息会设置 `requires_confirmation = true`。当前 Demo 中，如果需要确认，就不会自动写入，而是把“记忆待确认”返回给前端。

Pipecat 语音链路中的 `MemoryProcessor` 不使用这个前置 policy，而是直接调用 `memory.store()`。真正是否写入仍由 `StructuredLongTermMemory` 内部抽取和 resolver 决定。

### 6.2 候选记忆抽取

`StructuredLongTermMemory._extract_candidates_for_write()` 会组合两类抽取结果。

第一类是 LLM 抽取。`RemoteLLMMemoryExtractor` 会调用 OpenAI-compatible chat completion，要求输出 JSON：

```json
{
  "candidates": [
    {
      "memory_type": "persona | preference | event",
      "slot_key": "name",
      "value": "...",
      "summary": "...",
      "tags": [],
      "metadata": {}
    }
  ]
}
```

如果没有配置 `MEMORY_LLM_API_KEY`，LLM 抽取会直接返回空列表。

第二类是本地规则抽取。规则覆盖：

- 中文姓名、年龄、职业、居住城市、工作城市。
- 英文姓名、职业、工作场景、关系状态。
- 中英文偏好表达，例如“喜欢”“不喜欢”“更喜欢”“讨厌”“prefer”“hate”。
- 饮品、食物、辣度、口味、音乐、活动、社交、居住偏好等 slot 推断。
- “昨天、上周、最近、上次”等时间线索触发的事件记忆。
- 情绪、关系、睡眠、压力、职业、搬家、食物等 tags。

如果 LLM 抽取为空，但本地判断这句话像一个可回忆事件，会写入 fallback event。

### 6.3 偏好拆分和扩展

偏好写入是这个项目里最重要的细节之一。

系统会尝试把复合偏好拆成多个独立 item：

```text
我喜欢拿铁和美式
```

会变成：

- `favorite_beverage = 喜欢拿铁`
- `favorite_beverage = 喜欢美式`

后续如果用户说：

```text
我现在讨厌拿铁了
```

系统只会把“拿铁”相关 item 置为 historical/deleted，并新增 `不喜欢拿铁`，不会误伤“美式”。

对应测试在 `tests/test_structured_memory_preferences.py`。

### 6.4 写入决策

写入决策由两层组成。

本地 resolver 是默认路径，原则偏保守：

- 用户在问问题时不写入。
- 用户在测试记忆时不写入，例如“你还记得我叫什么吗”。
- 表达不确定时不写入，例如“可能、也许、maybe”。
- slot value 是占位词或无效值时不写入，例如“什么、哪里、what、where”。
- 新 slot 没有旧值时 add。
- 有明确更新语义时 update。
- 有明确删除语义时 delete。
- 值等价时 noop。

可选 LLM resolver 只在配置了 `MEMORY_LLM_API_KEY` 且消息需要额外校验时参与。它的职责是辅助判断冲突、覆盖、删除，不是唯一决策来源。

### 6.5 状态变更

写入后可能出现以下状态：

- `active`：当前有效。
- `superseded`：被新事实替代。
- `historical`：偏好历史项，不再是当前有效偏好。
- `deleted`：用户删除或系统判定删除。

persona slot 更新时，旧 `MemoryItem` 会被标记为 `superseded`，新 item 成为 slot 的 source。

preference 更新时，会尽量只更新相关主体，保留同一 slot 下其他不冲突偏好。

## 7. 检索流程

检索入口是：

```python
await memory.retrieve(query=user_message, filters=filters, limit=6)
```

返回值是给 LLM 注入用的文本，典型格式：

```text
[Long-term memory]
Persona slots:
- name: 小雨

Preference slots:
- favorite_beverage: 喜欢美式

Relevant long-term memories:
- 上周用户搬到了杭州
```

如果没有相关记忆，返回空字符串。

### 7.1 filter 归一化

`_normalize_filters()` 会合并显式 filters 和 query 推断：

- 看到“喜欢、偏好、推荐、想吃、口味”，偏向 `preference` 和 `event`。
- 看到“住、工作、名字、职业、我是谁”，偏向 `persona` 和 `event`。
- 看到“上次、之前、最近、那天、心情、发生”，加入 `event`。
- 看到饮品、城市、职业等关键词，会补充对应 `slot_keys`。

支持的 filters 主要包括：

```json
{
  "memory_types": ["persona", "preference", "event"],
  "slot_keys": ["home_city", "favorite_beverage"],
  "active_only": true,
  "scene": "emotional_support"
}
```

### 7.2 排序信号

检索不是纯关键词匹配，而是综合排序：

- 本地 hashing embedding 的 cosine similarity。
- query token overlap。
- slot key 命中 boost。
- event boost。
- active 状态 boost。
- scene boost，例如情绪陪伴场景更重视事件、关系、压力、睡眠。
- freshness score，新近记忆略有加权。

### 7.3 输出控制

`retrieve()` 会分别取：

- persona slots：最多 2 条。
- preference slots/profiles：最多 3 到 4 条。
- relevant memories：按 `limit` 控制，默认 6。

这样可以避免把整个记忆库塞进 prompt。

## 8. 五层记忆适配

底层引擎只有 `persona`、`preference`、`event` 三类主结构。Companion Agent 使用 `MemoryLayerAdapter` 把 snapshot 映射成五层：

```text
StructuredLongTermMemory.snapshot()
  -> MemoryLayerAdapter.retrieve_tiered()
  -> TieredMemoryContext
  -> TieredMemoryContext.to_prompt_section()
```

五层含义：

| 层 | 来源 | 用途 |
| --- | --- | --- |
| `profile` | `persona_slots` | 稳定用户事实，给 persona 层做轻量画像。 |
| `preferences` | `preference_slots` + `preference_profiles` | 当前有效偏好，支持同类多个 active item。 |
| `long_term_goals` | 带 goal tag 的 memories 或 goal 类 slot | 计划、学习、长期陪伴场景使用。 |
| `episodic_events` | `memory_type == event` 或 event tags | 情绪陪伴、记忆查询、连续性对话使用。 |
| `safety_notes` | safety/health/crisis 等 tags | 安全敏感场景使用。 |

`to_prompt_section()` 会生成中文结构化片段，例如：

```text
【用户档案】
  - name: 小雨

【用户偏好】
  - favorite_beverage: positive 喜欢美式

【近期事件】
  - [2026-05-12T...] 用户上周搬家
```

注意：`SituationRouter` 会返回希望检索的 `memory_tiers`，但当前 `MemoryLayerAdapter.retrieve_tiered()` 主要根据 query 检索 raw memory，并从 snapshot 中整理可用 tier；它没有严格按 `memory_tiers` 裁剪所有 tier。实际注入量由 `to_prompt_section()` 内部限制。

## 9. 对话链路中的注入位置

### 9.1 Web Demo / Companion Core

Web Demo 的主要链路：

```text
POST /api/chat 或 /api/chat-stream
  -> DemoSession.send_message() / stream_message()
  -> CompanionAgentCore.process_message()
      1. SituationRouter.classify()
      2. MemoryLayerAdapter.retrieve_tiered()
      3. SkillRegistry.resolve/execute()
      4. SystemPersonaLayer.build_system_prompt()
      5. ResponsePolicy.build_prompt_suffix()
      6. MemoryUpdatePolicy.evaluate()
      7. memory.store()，如无需用户确认
  -> CompanionAgentCore.build_messages_for_llm()
  -> call_chat_completion()
  -> ResponsePolicy.format_response()
  -> 更新 short_history 和前端 memory panel
```

这里有一个重要设计：当前用户消息的长期记忆写入发生在检索之后，因此当前轮不会把“刚刚说的话”作为长期记忆再注入给自己，避免自我回声。写入成功后，前端记忆面板可以立即展示更新。

最终传给 LLM 的 messages 大致是：

```text
system: persona + 角色卡 + 用户画像 + 情境风格
system: 记忆提示和技能/安全提示
system: 五层记忆上下文
history: 最近对话
user: 当前用户消息
```

### 9.2 Pipecat 语音链路

语音 Demo 走 `prototype_demo/voice_bot.py`：

```text
transport.input()
  -> STT
  -> UserTranscriptMirrorProcessor
  -> user_aggregator
  -> MemoryProcessor
  -> LLM
  -> AssistantTranscriptMirrorProcessor
  -> TTS
  -> transport.output()
  -> assistant_aggregator
```

这里的记忆后端是 `HTTPMemoryBackend`，它把 `store/retrieve/clear` 转成 HTTP 请求，访问 Web Demo 的共享服务：

- `POST /api/memory/store`
- `POST /api/memory/retrieve`
- `POST /api/clear-memory`
- `GET /api/memory-mode`

这样 Web 聊天和语音聊天共享同一份 `prototype_memory_store.json`。

### 9.3 MemoryProcessor 的细节

`MemoryProcessor` 专门处理 Pipecat 的 `LLMContextFrame`：

1. 删除之前注入过的 `[Long-term memory]` system message，避免重复累积。
2. 找到最新 user message。
3. 如果 memory mode 关闭，则只更新内部 `_stored_count`，不检索、不写入。
4. 写入尚未保存的已完成 user/assistant turn。
5. 用最新 user message 检索长期记忆。
6. 把检索文本作为 system message 注入。
7. 检索完成后再保存当前 user turn，供下一轮使用。

因为 `StructuredLongTermMemory` 只处理 user role，所以即使 processor 把 assistant turn 也传给 `store()`，长期记忆引擎也会忽略。

## 10. HTTP API

Web Demo 暴露的记忆相关接口如下。

### 10.1 读取状态

```http
GET /api/state
GET /api/memory-mode
```

返回当前短对话历史、记忆开关、前端面板数据、最近使用的记忆预览等。

### 10.2 检索记忆

```http
POST /api/memory/retrieve
Content-Type: application/json

{
  "query": "你还记得我喜欢喝什么吗",
  "filters": {
    "memory_types": ["preference"],
    "slot_keys": ["favorite_beverage"],
    "active_only": true
  },
  "limit": 6
}
```

返回：

```json
{
  "memory_text": "...",
  "memory_panel": {},
  "memory_used": true,
  "memory_used_count": 3
}
```

### 10.3 存储记忆

```http
POST /api/memory/store
Content-Type: application/json

{
  "role": "user",
  "content": "我现在住在杭州，最近更喜欢美式"
}
```

返回写入后的面板数据和 diff。

### 10.4 删除记忆

```http
POST /api/memory/delete
Content-Type: application/json

{
  "memory_id": "mem_xxx"
}
```

删除不是直接从 JSON 里物理移除，而是优先标记为 `deleted`，并同步清理对应 slot/profile 当前值。

### 10.5 关闭/开启记忆

```http
POST /api/memory-mode
Content-Type: application/json

{
  "memory_enabled": false
}
```

关闭后，Web Demo 不检索也不写入长期记忆；语音链路通过 `HTTPMemoryBackend.is_memory_enabled()` 读取同一个开关。

### 10.6 清空记忆

```http
POST /api/clear-memory
```

会清空短会话、最近更新记录、长期记忆 JSON 文件。

## 11. 前端记忆面板

`prototype_demo/server.py` 的 `serialize_memory()` 会把底层 snapshot 转成前端友好的结构：

- `persona`：按 slot 展示稳定事实。
- `preferences`：优先展示 `preference_profiles` 中 active 的细粒度偏好。
- `events`：展示最近 8 条 active event。
- `conflicts`：展示最近 8 条冲突记录，倒序。

`diff_snapshots()` 会比较写入前后 `persona_slots` 和 `preference_slots`，生成前端更新提示，例如 added、updated、deleted。

## 12. 配置项

### 12.1 记忆抽取和写入 resolver

| 环境变量 | 作用 |
| --- | --- |
| `MEMORY_LLM_API_KEY` | 记忆抽取器和写入 resolver 的 API key。未配置时走本地规则。 |
| `MEMORY_LLM_URL` | OpenAI-compatible chat completion endpoint。 |
| `MEMORY_LLM_MODEL` | 记忆抽取/决策模型，默认逻辑使用 `gpt-4o-mini`。 |

### 12.2 对话 LLM

| 环境变量 | 作用 |
| --- | --- |
| `OPENAI_API_KEY` | Companion/Web/Voice 对话模型 API key。 |
| `OPENAI_BASE_URL` | OpenAI-compatible endpoint。 |
| `OPENAI_MODEL` | 对话模型名。 |

### 12.3 原型服务和语音共享记忆

| 环境变量 | 作用 |
| --- | --- |
| `PROTOTYPE_HOST` | Web Demo host，默认 `127.0.0.1`。 |
| `PROTOTYPE_PORT` | Web Demo port，默认 `8787`。 |
| `MEMORY_API_BASE_URL` | 语音 bot 显式指定记忆 HTTP 服务地址。 |
| `ENABLE_MEMORY_RERANK_V2` | 保留的场景重排开关，主要服务旧版 context packer。 |

### 12.4 当前情绪 LLM Judge

| 环境变量 | 作用 |
| --- | --- |
| `EMOTION_LLM_API_KEY` | 当前轮用户情绪判断的 API key；未配置时依次复用 `CHAT_API_KEY`、`OPENAI_API_KEY`、`MEMORY_LLM_API_KEY`。 |
| `EMOTION_LLM_URL` | OpenAI-compatible chat completion endpoint；未配置时依次复用 `CHAT_API_URL`、`MEMORY_LLM_URL`、`OPENAI_BASE_URL`。 |
| `EMOTION_LLM_MODEL` | 情绪判断模型；未配置时依次复用 `CHAT_API_MODEL`、`MEMORY_LLM_MODEL`、`OPENAI_MODEL`，默认 `gpt-4o-mini`。 |
| `EMOTION_LLM_TIMEOUT` | 情绪判断请求超时时间，默认 `3.5` 秒。 |
| `EMOTION_OUTPUT_PATH` | 当前轮情绪结果本地输出路径；默认 `prototype_demo/.run/current_emotion.json`。 |

`companion_agent/emotion_detector.py` 当前把 LLM 输出限制在 `None`、`开心`、`难过` 三个标签。LLM 调用失败或返回非法标签时，会回退到本地规则判断，避免 demo 对话链路中断。

## 13. 隐私和安全策略

当前系统有几层保护：

- `MemoryUpdatePolicy` 会识别密码、账号、身份证、银行卡、地址、电话、医疗等敏感信息。
- 敏感信息默认需要确认，不自动写入。
- 用户可以通过 API 删除单条记忆或清空全部记忆。
- `StructuredLongTermMemory` 会忽略记忆探测问题，避免把“你还记得我叫什么”误写成用户事实。
- `SystemPersonaLayer` 明确要求不编造记忆、不过度强调“我记得你”、不制造情感依赖。
- `ResponsePolicy` 在安全敏感场景追加危机帮助提示。

需要注意的是，当前 JSON 存储文件是本地明文文件。如果用于真实用户，需要补充权限隔离、加密、用户级 namespace、审计日志和数据保留策略。

## 14. 已知边界

- 本地规则能覆盖常见中英文表达，但复杂语义仍依赖 LLM extractor。
- hashing embedding 轻量、稳定、无外部依赖，但不如真实 embedding 模型精确。
- 当前 `MemoryLayerAdapter` 会从 snapshot 整理多层记忆，未严格按 router 返回的 `memory_tiers` 做硬裁剪。
- `delete_memory()` 以状态标记和 slot 清理为主，不是全量物理删除历史痕迹。
- `SimpleMemory` 是短期历史记忆，不具备结构化长期记忆能力。
- Web Demo 当前使用单个全局 `DemoSession` 和单个 JSON 文件，不支持多用户隔离。

## 15. 调试建议

常用检查路径：

```bash
# 查看当前持久化记忆
python -m json.tool prototype_memory_store.json

# 运行记忆相关测试
python -m pytest tests/test_memory_policy.py tests/test_structured_memory_preferences.py tests/test_context_engine.py

# 启动 Web Demo
python prototype_demo/server.py
```

调试一条记忆为什么没写入时，优先检查：

1. `memory_enabled` 是否为 true。
2. 用户消息是否被 `MemoryUpdatePolicy` 判成 `ignore` 或 `requires_confirmation`。
3. `StructuredLongTermMemory._extract_candidates_for_write()` 是否产生候选。
4. resolver 是否因为问题句、记忆探测、不确定表达、无效 slot value 判成 `noop`。
5. JSON 文件里对应 `MemoryItem.status` 是否已经变成 `superseded`、`historical` 或 `deleted`。

调试一条记忆为什么没召回时，优先检查：

1. query 是否触发了正确的 `memory_types` 和 `slot_keys`。
2. 目标记忆是否是 `active`。
3. filters 是否过窄。
4. `limit` 是否太小。
5. scene boost 是否把其他事件排到了前面。

## 16. 推荐扩展方向

如果要把这个项目推进到更接近生产的形态，建议优先做：

- 多用户 namespace：存储文件或数据库按 user/session 隔离。
- 存储后端替换：把 JSON 文件替换成 SQLite/Postgres + 向量索引。
- 明确的用户确认流：对 sensitive/private 记忆提供前端确认、拒绝、编辑。
- 物理删除能力：满足“彻底删除”语义。
- 更强的观察日志：记录每次候选抽取、resolver 决策、检索排序分数。
- 更严格的 tier 裁剪：让 `SituationRouter.memory_tiers` 真正控制 Adapter 输出。
