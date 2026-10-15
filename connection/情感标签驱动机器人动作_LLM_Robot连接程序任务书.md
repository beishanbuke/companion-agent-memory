# 情感标签驱动机器人动作：LLM–Robot 连接程序任务书

> 本文是给代码生成模型的**完整任务说明书**。目标是一次生成一个正确、可部署、可测试的连接程序，把对话系统产出的情感标签变成机器人真机上的挥手动作。
>
> 阅读顺序建议：先读第 1、2、4 节建立全局认识，再按第 6 节逐模块实现，最后按第 11 节验收。**所有路径、字段名、标签值都以本文为准，不要自行发明或改动。**

---

# 1. 任务总览

## 1.1 一句话目标

对话系统每轮对用户情绪做出判断并写入 `current_emotion.json`；连接程序监听该文件，当标签为 `开心` 时调用 `cheer` 动作，当标签为 `难过` 时调用 `hello` 动作，**取代原来手柄按键触发的方式**。

## 1.2 目标链路

```text
用户说话（文字 / 语音）
    ↓
companion-agent-memory 对话服务（8787）
    ↓ 每轮自动写入
prototype_demo/.run/current_emotion.json
    ↓ 轮询读取 + 去重 + 全量投递（含 None）← 本任务新增
EmotionWatcher（机器人 Orin 上）
    ↓ HTTP POST（127.0.0.1:8790，本机回环）
RobotGateway（机器人 Orin 上）
    ↓ 白名单 / 执行状态机：不抢占 · 最新情绪优先
RobotActionClient.trigger_action("hello")
    ↓ 调用 Sim2Real 已有的动作切换接口（Phase 0 确认具体形式）
hello → 手柄按键 rt+x → 动作执行
    ↓
机器人完成打招呼动作，回到默认模式
```

## 1.3 核心原则（生成代码时必须遵守）

1. **连接程序工作在"动作选择层"**：只传递动作名称 `hello`，绝不直接触碰 TRT 推理、Future JSON、119 维 observation、22 维 action 或电机。底层执行完全交给已在运行的 Sim2Real 系统。
2. **零侵入 + 可回退**：不修改 `companion-agent-memory` 与 `/home/nvidia/sim2real` 的任何现有文件，只读取 `current_emotion.json`、只调用已有的动作触发接口。连接程序是**纯新增**的独立进程——回退 = 停掉这两个进程，两侧系统立即恢复原状（对话照常、手柄照常），不需要恢复任何文件。部署前仍必须按第 10 节第 8 条对两侧做备份，形成双保险。
3. **不自动启动机器人主控**：`joy_control_pi_plus_orin.launch` 由人工预先启动，连接程序只做触发，不做系统启停。
4. **安全优先**：白名单、动作不可抢占、同动作抑制、dry-run 模式缺一不可；任何异常都只记日志并跳过，绝不能让对话链路或机器人控制链路崩溃。

---

# 2. 系统现状（已核实的事实，直接引用，不要重新假设）

## 2.1 情绪侧：companion-agent-memory

### 2.1.1 数据源文件

```text
<对话服务运行目录>/prototype_demo/.run/current_emotion.json
```

- 对话服务是 `prototype_demo/server.py`（HTTP 8787，语音后端 7860）。
- 在本系统上的运行目录为
  `/home/nvidia/Desktop/companion-agent-memory`，
  因此默认绝对路径为
  `/home/nvidia/Desktop/companion-agent-memory/prototype_demo/.run/current_emotion.json`。
- 路径可被环境变量 `EMOTION_OUTPUT_PATH` 覆盖（支持相对/绝对路径，相对时基于项目目录）。
- **注意**：watcher 部署在机器人上（见 3.2），它读到的路径是"该文件在机器人上可见的位置"——要么对话服务与 watcher 同机（文件本就在本地），要么对话服务器的 `.run` 目录已挂载到机器人（见 3.2 前提）。

### 2.1.2 写入时机

`server.py` 中的 `persist_emotion_output()` 在**每个用户轮次结束时**被调用，共三个调用点：普通文本对话、流式对话、语音转写路径。也就是说：

> 用户每说一句话（无论文字还是语音），该文件就被整体重写一次，包括标签为 `None` 的轮次。

### 2.1.3 写入方式

原子写：先写 `current_emotion.json.tmp`，再 `replace()` 覆盖目标文件。读取方永远不会读到半个 JSON。但仍需容忍极少数读取瞬间的 `JSONDecodeError`（跳过本轮轮询即可）。

### 2.1.4 文件精确格式（schema）

```json
{
  "updated_at": "2026-08-16T15:30:12+0800",
  "user_message": "今天面试通过了，太开心了！",
  "emotion": {
    "label": "开心",
    "intensity": 0.7,
    "confidence": 0.85,
    "reason": "用户表达强烈正面情绪;llm_judge",
    "signals": ["开心", "llm_judge"],
    "trend": "新出现",
    "context_turns": 3
  }
}
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `updated_at` | str | 写入时刻，格式 `%Y-%m-%dT%H:%M:%S%z`（如 `+0800`） |
| `user_message` | str | 触发本轮情绪判断的用户原话 |
| `emotion.label` | str | **只有三个合法值：`None`、`开心`、`难过`**（代码常量 `EMOTION_NONE/HAPPY/SAD`） |
| `emotion.intensity` | float | 0–1 |
| `emotion.confidence` | float | 0–1 |
| `emotion.reason` | str | 判断依据 |
| `emotion.signals` | list[str] | 命中的证据词 |
| `emotion.trend` | str | 新出现/持续/加重/缓解中/趋于平稳/波动 |
| `emotion.context_turns` | int | 参考的上下文轮数 |

生成代码时：`label` 以**字符串精确匹配**判断，注意 `None` 是字符串 `"None"`，不是 JSON `null`；`开心`/`难过` 是中文，文件为 UTF-8 编码，读取时必须显式 `encoding="utf-8"`。

## 2.2 机器人侧：Mini Pi Plus Pro（Orin）

以下事实来自《Mini_Pi_Plus_真机单动作执行流程与LLM接入.md》，均已确认：

| 项 | 值 |
|---|---|
| 系统总目录 | `/home/nvidia/sim2real` |
| 总启动入口 | `roslaunch sim2real_master joy_control_pi_plus_orin.launch`（先 `source ./install/setup.bash`） |
| 启动参数 | `model_type=pi_plus`，`dof_type=26`，`production_type=custom`（**不要改成 22**） |
| 动作注册表 | `/home/nvidia/sim2real/install/share/sim2real/config/pi_plus_26dof_config/pi_plus_26dof_rl_config_custom.yaml` |
| 动作触发配置目录 | `/home/nvidia/sim2real/install/share/sim2real/action_config/config/pi_plus_26dof/`（`base_policy.yaml` / `custom_action.yaml`） |
| 当前可用动作 | `hello`（rt+x）、`cheer`（rt+a）、`dance2_10_16s`（rt+y）、`small_kick`（x） |
| 当前触发方式 | 手柄（joy）按键 |
| TensorRT policy | `/home/nvidia/sim2real/install/share/sim2real/policy/motion/model_49999_action.trt`（通用动作策略） |
| 动作时长 | **根据具体动作确定**，控制频率 50 Hz |

**唯一未确认的接口**：手柄究竟通过哪个 ROS topic / service / 内部函数触发 policy 切换到 `hello`。这由第 9 节的 Phase 0 在真机上探测，生成代码时必须把该细节隔离在 `RobotActionClient` 一个模块内（见 6.3）。

---

# 3. 系统架构与部署拓扑

## 3.1 组件划分

生成程序由三个模块 + 一个测试工具组成：

```text
emotion_robot_bridge/
├── README.md                # 部署与使用说明
├── bridge_config.json       # 全部可调参数（见第 7 节）
├── emotion_watcher.py       # 组件1：对话服务器侧，监听情感文件
├── robot_gateway.py         # 组件2：机器人侧 HTTP 网关
├── robot_action_client.py   # 组件3：机器人侧动作触发抽象（含 A/B 两实现）
├── simulate_emotion.py      # 测试工具：手工写入伪造的 current_emotion.json
└── logs/                    # 运行日志目录（自动创建）
```

## 3.2 部署拓扑（已定方案：两个进程都跑在机器人 Orin 上）

`emotion_watcher.py` 和 `robot_gateway.py` **都部署在机器人的操作系统里**，互相之间走本机回环 `127.0.0.1:8790`，不跨机器通信：

```text
┌─────────────────────┐                     ┌────────────────────────────────┐
│ 对话服务器           │                     │ 机器人 Orin（两个进程都在这里）  │
│ server.py (8787)    │  每轮写入            │                                │
│ 每轮写入             │ ────────────────→   │ current_emotion.json           │
│ current_emotion.json│ 文件到达方式见下方    │   ↓ 轮询 + 去重 + 标签映射       │
└─────────────────────┘   前提              │ emotion_watcher.py             │
                                          │   ↓ HTTP POST 127.0.0.1:8790   │
                                          │ robot_gateway.py               │
                                          │   ↓ 白名单 / 执行状态机：不抢占 · 最新情绪优先        │
                                          │ robot_action_client.py         │
                                          │   ↓ ROS topic/service          │
                                          │ Sim2Real（人工预先启动）         │
                                          │   → hello 执行            │
                                          └────────────────────────────────┘
```

### 部署前提：机器人上必须能看到 `current_emotion.json`

对话服务默认跑在另一台服务器上，而 watcher 跑在机器人上，因此必须先解决文件可见性，二选一（写入 README 的部署步骤）：

1. **方式一（对话服务就在机器人上运行）**：`emotion_file` 直接配本地绝对路径，无额外工作。
2. **方式二（对话服务在别的服务器）**：把对话服务器的 `prototype_demo/.run` 目录通过 NFS / SSHFS 挂载到机器人上的固定路径（如 `/mnt/emotion/.run`），`emotion_file` 配该挂载路径。也可以反过来在对话服务器上把 `EMOTION_OUTPUT_PATH` 指向一个双方同步的目录。轮询 + SHA-256 指纹对挂载文件同样安全（原子写在 NFS 上依然保证读到完整内容）。

### 为什么同机了还拆 watcher / gateway 两个进程

- 职责分离：文件监听（对话侧语义）与机器人执行串行化（机器人侧安全）各自独立，可单独重启、单独调试；
- gateway 保留 HTTP 入口，开发机上仍可 `curl` 直接调试触发链路；
- 将来若要把 watcher 移回对话服务器（免挂载），只需改 `gateway_url` 并把 gateway 绑回 `0.0.0.0`，两个模块的代码零改动。

## 3.3 技术约束

- **Python 3.10+，仅用标准库**（`json / time / pathlib / hashlib / urllib.request / http.server / threading / argparse / logging / subprocess`）。不得引入 requests / flask / rospy 之外的第三方包；`rospy` 仅允许出现在 `robot_action_client.py` 的实现 B 中，且必须做**惰性导入**（`import` 放进函数体内，并用配置项选择实现），保证没有 ROS 的机器上 dry-run 模式仍可运行。
- 两个常驻进程都要支持 `--dry-run` 命令行参数覆盖配置，并打印醒目的 `=== DRY-RUN 模式，不会真正触发机器人 ===` 横幅。
- 所有异常捕获后记日志继续运行，进程不允许因单次错误退出。

---

# 4. 核心业务规则（必须逐条实现）

## 4.1 标签 → 动作映射

```python
EMOTION_ACTION_MAP = {
    "开心": "cheer",
    "难过": "hello",
}
# "None" 及一切未知标签 → 不触发任何动作
```

说明：当前阶段开心/难过都映射到同一个挥手动作（这是需求方明确要求的）。映射表必须放在 `bridge_config.json` 中可配置，将来加 `nod`、`comfort_low` 等动作时只改配置。

## 4.2 触发条件与去重（watcher 侧：只负责可靠投递）

每个轮次文件都会重写（含 `None` 轮次），因此 watcher：

1. 每 `poll_interval`（默认 0.5 s）读一次文件。
2. 计算**整个文件原始字节**的 SHA-256 作为指纹；指纹与上一次相同 → 跳过（什么都不做）。用内容指纹而不是只比 `updated_at`，因为同一秒内连续两轮会碰撞。
3. 指纹变化 → 解析 JSON；解析失败 → 记 warning，跳过本轮（原子写保证下轮正常）。
4. **每一个新结果都原样发给 gateway——包括标签为 `None` 的轮次**。标签过滤、映射、触发决策全部在 gateway 侧完成（机器人侧是唯一决策点），watcher 只做"文件变化 → HTTP 投递"。`None` 更新同样重要：它是执行状态机的"情绪平复"信号（见 4.3 规则 4）。
5. 发送超时/失败 → 记 error 后丢弃该次，不重试。丢弃一条 `None` 更新最坏的后果是机器人多执行一次本可省略的动作，属可接受退化，不影响安全。

## 4.3 执行状态机：不抢占 + 最新情绪优先（gateway 侧，需求方指定的核心行为）

需求原话："动作能完整执行完；label 变了再切换；对话过快时先完整处理完动作，再重新接受 label。"逐条落实为以下状态机：

**状态**：`idle`（待机）/ `busy`（动作执行中）；辅助量 `pending`（待执行槽，至多一条）、`last_executed_action`（刚执行过的动作）、`emotion_reset`（自上次执行后是否出现过平静期）。

**规则**：

1. **动作绝不被打断（硬性）**：动作一旦开始就执行到完整结束（时长按动作表 `duration`），期间收到的任何更新都不能中断它。
2. **执行中收到更新（busy）**：不排队、不丢弃，写入 `pending` 槽，**后来的覆盖先来的**（latest-wins）。机器人永远只关心最新情绪，不会积压一串过期动作——这就是"先完整处理完动作，再重新接受 label"。
3. **动作结束后消费 `pending`**（先等 `settle_gap` 让机器人回到默认姿态并稳定）：
   - 槽为空 → 回到 `idle`；
   - 槽内标签无映射（`None` 或未知标签）→ 不动作，置 `emotion_reset = true`；
   - 槽内标签映射的动作 == `last_executed_action` 且 `emotion_reset == false` → 跳过（该情绪已表达过，防止长段同情绪独白导致机器人反复挥手）；
   - 否则 → 执行该动作（这就是"label 变了再切换"）。
4. **`None` 的双重作用**：情绪回到平静既清空 `pending` 又置位 `emotion_reset`。因此 `开心 →（几句中性话）→ 开心` 会**再次**挥手，而连续的 `开心、开心、开心` 只挥**一次**。
5. **idle 时收到更新**：直接按第 3 条的消费规则即时决策（与完成后消费走同一个决策函数，行为完全一致）。
6. **比较基准是动作而非标签**：当前 `开心`/`难过` 都映射 `hello`，忙期间 `开心→难过` 翻转不会再追加一次挥手；将来 `难过` 绑定独立动作（如 `comfort_low`）后，同样的翻转就会真正切换动作。

**行为时间线（默认配置）**：

```text
t=0.0  "我面试过了，太开心了！"  → 开心 → 开始挥手（busy，约 5.4 s + 余量）
t=2.0  "真的超开心！"            → 开心 → pending=开心（覆盖写入）
t=4.0  "唉，不过也有点难过"       → 难过 → pending=难过（覆盖写入）
t=6.5  挥手结束 → settle 2 s → 消费 pending：难过映射的动作==刚执行的挥手，且未经历平静期 → 跳过，回 idle
t=9.0  "没事了没事了"            → None → 情绪平复，emotion_reset=true
t=20.0 "又开心了！"              → 开心 → 平静期后同情绪视为新表达 → 再挥手一次
```

（若 `难过` 将来绑定独立动作，t=6.5 处就会切换执行该动作——由扩展指南场景 B/C 打开。）

## 4.4 白名单

gateway 在调用 `RobotActionClient` 前校验动作名：

```python
ACTION_WHITELIST = ["hello"]   # 配置项，初始只有这一个
```

不在白名单 → HTTP 400，记 warning。这是防止配置错误或未来上游变更导致机器人执行未验证动作的最后一道闸。

## 4.5 扩展性（新增动作 / 新增情感标签）

桥接层自身**只改配置不改代码**：`emotion_map` 加映射、`actions.whitelist` 加动作名、`actions.<动作名>.duration` 填时长。但"新增动作"和"新增情感标签"分别还有机器人侧、对话侧的先行改动，**完整改动清单见同目录独立文档**：

> **《情感标签与动作扩展_两侧改动指南.md》**

生成代码时只需遵守一条铁律：`emotion_map` 的值是**动作名**（如 `hello`），**不是动作文件路径**——动作名 → motion YAML → TRT + future JSON 的解析由 Sim2Real 注册表完成，桥接层从头到尾不出现任何机器人文件路径。

---

# 5. 接口与数据格式

## 5.1 Watcher → Gateway：HTTP 协议

Gateway 监听 `127.0.0.1:8790`（本机回环；监听地址与端口可配置，仅当需要从开发机远程 curl 调试时才改绑 `0.0.0.0`），两个端点：

### `POST /emotion`

watcher 对**每一个新情绪结果**（含 `None`）调用一次。请求体（UTF-8 JSON）：

```json
{
  "label": "开心",
  "intensity": 0.7,
  "confidence": 0.85,
  "updated_at": "2026-08-16T15:30:12+0800",
  "user_message": "今天面试通过了！"
}
```

动作名由 gateway 根据 `emotion_map` 解析（映射与白名单都在机器人侧，watcher 不持有）。响应：

| 状态码 | 场景 | 响应体 |
|---|---|---|
| 200 | 已按状态机决策 | `{"status": "triggered"/"queued_latest"/"skipped_same_action"/"reset", "state": "idle"/"busy", "last_action": "hello"}` |
| 400 | 请求体非法，或映射出的动作不在白名单（配置错误） | `{"status": "rejected", "reason": "..."}` |
| 503 | 本应触发但机器人主控未检测到在线 | `{"status": "robot_offline"}` |

`status` 含义：`triggered`=已开始执行；`queued_latest`=执行中，已作为最新情绪记入待执行槽；`skipped_same_action`=与刚执行动作相同且未经历平静期，跳过；`reset`=平静/无映射标签，清槽并重置。

watcher 对超时（默认 3 s）和网络错误的处理：记 error 日志，丢弃该次（不重试；后续轮次自然补上）。

可选简单鉴权：配置 `auth_token` 非空时，请求头须带 `X-Bridge-Token: <token>`，不匹配返回 401。

### `GET /health`

响应 `{"status": "ok", "mode": "real", "busy": false, "robot_online": true, "last_action": "hello", "last_trigger_at": "..."}`。供部署检查和监控用。

## 5.2 RobotActionClient 抽象（关键隔离层）

```python
class RobotActionClient(Protocol):
    def is_robot_online(self) -> bool: ...
    def trigger_action(self, action_name: str) -> bool: ...
```

两个实现，由配置 `trigger_impl`（`"A"` / `"B"`）选择，默认 `"A"`：

### 实现A（首选）：直接调用 policy 切换接口

调用 Phase 0（第 9 节）探测出的 ROS topic / service。生成代码时按下面的占位结构写，探测完成后只填空：

```python
class DirectSwitchClient:
    def trigger_action(self, action_name: str) -> bool:
        # TODO(Phase-0): 替换为真实接口，三选一：
        # 1. rospy Publisher → topic（填 topic 名、消息类型、字段）
        # 2. rospy ServiceProxy → service（填 service 名、srv 类型、请求字段）
        # 3. subprocess 调 rostopic/rosservice pub
        ...
```

### 实现B（兜底）：模拟手柄按键

发布与手柄触发 `hello` 完全相同的 `sensor_msgs/Joy` 消息序列。根据 `custom_action.yaml`，`hello` 对应按键 `rt+x`（右扳机 + X键）。注意事项写进代码注释：

- 需要确认物理手柄与软件发布不冲突（物理手柄断开，或 joy 输入有 mux）；
- 按下/释放需要按真实间隔分多条消息发送（间隔值来自 `rostopic echo /joy` 抓包）。

### 机器人在线检测

`is_robot_online()`：执行配置中的 `robot_check_cmd`（默认 `rosnode list`，超时 2 s），检查输出中是否包含 `robot_node_keyword`（Phase 0 确认后填入主控节点名关键字；为空则跳过检测直接返回 True）。检测结果缓存 5 s，避免每次触发都起子进程。

---

# 6. 各模块详细需求

## 6.1 `emotion_watcher.py`（机器人侧常驻，与 gateway 同机）

主循环伪代码：

```python
last_hash = None
while True:
    try:
        raw = emotion_file.read_bytes()          # 文件不存在 → info 日志后 sleep
        h = sha256(raw)
        if h == last_hash:
            continue
        last_hash = h
        data = json.loads(raw.decode("utf-8"))  # 失败 → warning，跳过本轮
        resp = http_post(f"{gateway}/emotion", { # None 也照发
            "label": data["emotion"]["label"],
            "intensity": data["emotion"]["intensity"],
            "confidence": data["emotion"]["confidence"],
            "updated_at": data["updated_at"],
            "user_message": data["user_message"],
        })
        log_update(resp)    # triggered / queued_latest / skipped_same_action / reset
    except Exception as e:
        log_error(e)                              # 只记日志，绝不退出
    time.sleep(config.poll_interval)
```

补充要求：
- 启动时打印一条含全部关键配置（文件路径、gateway 地址、模式）的 summary 日志。
- 启动时若 `current_emotion.json` 已存在，**不要**对启动前的旧结果发送更新（初始化 `last_hash` 为当前文件指纹后再进入循环）。
- watcher 不做任何标签过滤和映射决策（那是 gateway 的职责），保证决策逻辑单点。
- 支持 `--dry-run`：只做读取和日志，不发送 HTTP。
- 优雅退出：捕获 `KeyboardInterrupt`，打印统计（观察轮数、投递次数、各标签计数）。

## 6.2 `robot_gateway.py`（机器人侧常驻，核心状态机）

- 用 `http.server.ThreadingHTTPServer` + `BaseHTTPRequestHandler` 实现 5.1 协议。
- 4.3 状态机的全部状态（`idle/busy`、`pending`、`last_executed_action`、`emotion_reset`）由一把 `threading.Lock` 保护。
- HTTP 线程只做决策和状态转移并立即返回；动作执行（含 `settle_gap` 等待和 `pending` 消费循环）在独立执行线程中进行。**idle 即时决策与完成后消费必须共用同一个 `consume()` 决策函数**，保证两条路径行为完全一致。
- 每次状态转移写一条结构化日志：时间、来源 label、决策（triggered/queued/skipped/reset）、当前状态、动作名。
- dry-run：状态机照常运转，仅"调用 RobotActionClient"这一步替换为记 `DRY-RUN: 将触发 hello` 日志。
- `--dry-run` 与配置文件 `dry_run` 同时存在时，命令行优先。

## 6.3 `robot_action_client.py`

- 实现 5.2 的抽象与 A/B 两实现、在线检测。
- 所有 ROS 相关 import 一律函数内惰性导入。
- 每个实现独立可测：构造时传入配置，方法无隐藏全局状态。

## 6.4 `simulate_emotion.py`（测试工具）

```bash
# 用法示例
python simulate_emotion.py --label 开心                       # 写入开心标签
python simulate_emotion.py --label 难过 --message "今天好累"
python simulate_emotion.py --label None
python simulate_emotion.py --file /path/to/current_emotion.json --label 开心
```

按 2.1.4 的 schema 生成合法 JSON（`updated_at` 用当前时间、`intensity/confidence` 给合理值），同样走原子写。它是端到端测试的驱动器，也可用于不改动对话服务的情况下演示。

---

# 7. 配置文件 `bridge_config.json`

```json
{
  "watcher": {
    "emotion_file": "<<<该文件在机器人上的可见路径：本机对话服务则为 .run 绝对路径，跨机则为挂载点，见 3.2>>>",
    "poll_interval": 0.5,
    "gateway_url": "http://127.0.0.1:8790",
    "request_timeout": 3.0,
    "dry_run": false
  },
  "gateway": {
    "listen_host": "127.0.0.1",
    "listen_port": 8790,
    "auth_token": "",
    "settle_gap": 2.0,
    "dry_run": false
  },
  "robot": {
    "trigger_impl": "A",
    "action_duration": 3.0,
    "robot_check_cmd": "rosnode list",
    "robot_node_keyword": "",
    "joy_topic": "/joy",
    "joy_button_sequence": []
  },
  "actions": {
    "hello": { "duration": 3.0 },
    "cheer": { "duration": 3.0 },
    "whitelist": ["hello", "cheer"]
  },
  "emotion_map": {
    "开心": "cheer",
    "难过": "hello"
  },
  "log_dir": "logs"
}
```

要求：
- 程序启动时校验配置（必填项缺失、端口非法、`trigger_impl` 不在 {A,B}、`emotion_map` 的值必须在 whitelist 中——否则启动失败并给出清晰错误）。
- 两个进程共用同一份配置文件，各自只读自己需要的段；`--config <path>` 可指定路径，默认脚本同目录。

---

# 8. 日志规范

- 同时输出到控制台和 `logs/watcher_YYYYMMDD.log` / `logs/gateway_YYYYMMDD.log`。
- 格式：`%(asctime)s [%(levelname)s] %(message)s`。
- 触发相关日志必须一行讲完整因果，例如：
  ```text
  UPDATE triggered     emotion=开心 action=hello updated_at=2026-08-16T15:30:12+0800 intensity=0.7
  UPDATE queued_latest emotion=难过 state=busy（已记入待执行槽）
  UPDATE skipped_same_action emotion=开心 action=hello（同动作且无平静期）
  UPDATE reset         label=None updated_at=2026-08-16T15:31:40+0800
  ```
- 日志文件按天滚动，保留最近 7 天（标准库 `TimedRotatingFileHandler`）。

---

# 9. Phase 0：机器人触发接口探测（部署前必须在真机执行）

生成代码时把本节原样保留在 README 的"部署步骤"里。**本节所有命令均为只读操作（cat / rosnode / rostopic echo / grep），不修改机器人上的任何文件。**步骤：

1. **人工启动主控**：
   ```bash
   cd /home/nvidia/sim2real && source ./install/setup.bash
   roslaunch sim2real_master joy_control_pi_plus_orin.launch
   ```
2. **读动作触发配置**：查看
   `/home/nvidia/sim2real/install/share/sim2real/action_config/config/pi_plus_26dof/custom_action.yaml`，确认 `hello` 对应的按键组合（已知：`rt+x`）。
3. **抓包**：另开终端 `rostopic echo /joy`，按 `rt+x` 触发一次 hello 动作，记录按钮序列与时间间隔 → 得到实现 B 所需数据。
4. **找真实接口（实现 A 的目标）**：
   ```bash
   rosnode list
   rqt_graph                       # 观察 joy → 哪个节点 → 哪个 topic/service
   grep -R "custom_action\|hello\|policy" \
     /home/nvidia/sim2real/src --include=*.cpp --include=*.h --include=*.py | head -50
   ```
   目标是找到消费 joy 输入、执行 policy 切换的节点及其输入接口（topic/service/参数）。找到后填入 `DirectSwitchClient`，并把 `trigger_impl` 保持为 `"A"`。
5. **记录主控节点名** → 填入 `robot_node_keyword`。
6. 找不到实现 A 的接口时，退回实现 B（`trigger_impl: "B"`，并填 `joy_button_sequence`）。

---

# 10. 安全要求（硬性）

1. 白名单之外的动作一律拒绝（4.4）。
2. 动作不可抢占 + 同动作抑制 + `settle_gap`（4.3）：执行频率上限由动作时长天然决定，对话再快也不会导致动作中断或堆叠；`settle_gap` 不得小于 0。
3. dry-run 是第一测试形态：**真机第一次联调必须在 dry-run 下确认日志正确后**，再切 real。
4. 真机测试环境要求（来自部署指南，写入 README）：开阔防滑地面、周边无人和障碍物、有人值守、手柄急停可用、首次测试者不站在机器人正前方。
5. 不修改 `dof_type=26`，不改动 `/home/nvidia/sim2real` 下任何配置文件——连接程序是**只读触发者**。
6. gateway 默认只绑 `127.0.0.1`（watcher 与其同机）；确需从开发机远程调试时才改绑 `0.0.0.0`，且此时**必须**配置 `auth_token` 并校验；不要以 root 运行。
7. 禁止在代码或文档中出现 `kill -9` 大范围清理进程之类的高危命令。
8. **既有系统保护与回退（硬性，需求方明确要求）**——"不能把原来的代码改坏，原程序必须保留且可正常使用"：
   - 生成代码中**禁止出现**任何针对 `companion-agent-memory` 和 `/home/nvidia/sim2real` 两个目录的写操作（写入 / 覆盖 / 移动 / 删除 / `sed -i` 等）；连接程序自身产生的数据（日志、配置、指纹缓存）只允许落在 `emotion_robot_bridge/` 自己的目录内。
   - **部署前备份两侧**（写入 README 部署步骤，作为第 1 步）：
     - 对话侧：在 git 仓库中则确认工作区干净并 `git tag` 打备份点；无 git 则 `tar czf companion_backup_$(date +%Y%m%d_%H%M%S).tar.gz` 整目录快照；
     - 机器人侧：对本任务会接触的配置（`action_config/config/` 下当前机型目录、`pi_plus_26dof_rl_config_custom.yaml`）逐一做 `.bak_$(date +%Y%m%d_%H%M%S)` 拷贝，launch 与其余文件不碰。
   - **回退步骤写入 README**：停止 watcher 与 gateway 两个进程即完成回退；随后验证两侧原有功能恢复正常——对话服务跑一轮确认 `current_emotion.json` 正常更新、手柄触发一次 `hello` 确认动作链路正常。
   - 由于连接程序零写入，正常情况下回退**不需要**动任何文件；备份仅用于应对误操作等意外，是最后防线。

---

# 11. 测试与验收标准

## 11.1 分层测试

| 层级 | 做法 | 通过标准 |
|---|---|---|
| T1 离线单测 | 直接调用 watcher 的解析/映射逻辑，覆盖 3 种标签、坏 JSON、缺字段 | 映射正确：None→无动作，开心/难过→hello；坏输入不抛异常 |
| T2 watcher dry-run | `simulate_emotion.py` 依次写 None/开心/难过/开心 | 日志显示：4 个新结果各产生一次投递（None 也投递）、重复写同一内容不重复投递 |
| T3 gateway dry-run（无 ROS 的机器） | 启动 `robot_gateway.py --dry-run`，用 curl 打 `/emotion` | 200 的四种 status 与 400 路径全部按 5.1 响应；busy 时连发两条更新，第二条返回 `queued_latest` 且只保留最后一条 |
| T4 真机 dry-run | 机器人上跑 gateway dry-run + 全链路 | `/health` 正常、日志出现 `DRY-RUN: 将触发 hello` |
| T5 真机 real | 移除 dry-run，`simulate_emotion.py --label 开心` | 机器人完整执行一次约 5.44 s 挥手并回到默认模式 |
| T6 全链路 | 真实对话："我太开心了"（语音或文字） | 一次对话 → 一次完整挥手；挥手期间再说两句开心 → 不中断、结束后也不重复挥（`skipped_same_action` 日志）；说几句中性话后再说开心 → 再挥一次 |

## 11.2 验收清单

- [ ] 三标签行为：None 不动、开心挥手、难过挥手
- [ ] 内容指纹去重：文件未变绝不重复触发
- [ ] 不抢占：动作执行中的任何更新都不中断当前动作
- [ ] 最新情绪优先：busy 期间多次更新只保留最后一条，动作结束后按其决策
- [ ] 同动作抑制：连续同情绪只执行一次；中间出现 None 后同情绪再出现会再次执行
- [ ] 白名单：改映射到未授权动作名时 gateway 返回 400
- [ ] 对话服务崩溃/文件被删：watcher 只记日志不退出；文件恢复后自动继续
- [ ] gateway 掉线：watcher 记 error 并继续轮询，不堆积、不崩溃
- [ ] 回退验证：停掉 watcher + gateway 两个进程后，对话服务正常产出情绪标签、手柄可正常触发 `hello`，两侧零残留
- [ ] dry-run 与 real 行为差异仅限最后一步触发
- [ ] 全部参数可经 `bridge_config.json` 配置，无需改代码

---

# 12. 明确不做的事（out of scope）

1. 不解析/加载 TRT、Future JSON，不生成关节角，不控制电机。
2. 不修改 `companion-agent-memory` 与 `/home/nvidia/sim2real` 的任何现有文件。
3. 不实现多任务队列（仅单一 latest-wins 待执行槽，见 4.3）。
4. 不做开机自启、systemd 服务、看门狗（README 里说明手工启动即可，留作后续）。
5. 不新增开心/难过之外的情绪识别逻辑。

---

# 13. 交付物清单

1. `emotion_robot_bridge/` 目录：4 个 Python 模块 + `bridge_config.json` + `README.md`（含部署前两侧备份步骤、Phase 0 部署步骤、回退步骤与回退后验证、安全要求、T1–T6 测试操作说明）。
2. 代码可直接在 Python 3.10+ 标准库环境运行（实现 A/B 中的 rospy 惰性导入除外）。
3. README 中明确标注两个"待 Phase 0 回填"的占位点：`DirectSwitchClient.trigger_action` 的真实接口、`robot_node_keyword`。

---

# 14. 已定的默认决策与可调项

| 决策点 | 默认值 | 可调方式 |
|---|---|---|
| 部署位置 | watcher 与 gateway **都在机器人 Orin 上**，走 127.0.0.1 | watcher 移回对话服务器：改 `gateway_url` + gateway 绑 `0.0.0.0`，代码零改动 |
| 情感文件获取 | 对话服务位置决定：同机直读 / 跨机挂载（NFS/SSHFS） | `emotion_file` 配实际可见路径，见 3.2 前提 |
| 触发语义 | 动作完整执行，label 变化才切换；经历 None 平静期后同情绪可再次触发 | 状态机规则见 4.3 |
| 忙时行为 | 不抢占 + latest-wins 待执行槽（不排队、不丢弃） | — |
| 去重依据 | 文件内容 SHA-256 | — |
| 动作间隔/占用 | settle 2 s / 6.5 s | `settle_gap`、动作表 `duration` |
| 触发实现 | A（直连接口），探测不成退 B | `trigger_impl` |
| 扩展新动作/新标签 | 桥接层只改配置；两侧先行改动见《情感标签与动作扩展_两侧改动指南.md》 | — |

---

# 15. 一句话总结

```text
读 current_emotion.json → 指纹去重 → 每个新结果（含 None）投递给机器人网关
→ 状态机决策：动作完整执行不打断，忙时只记最新情绪，完成后按最新情绪切换（同动作且无平静期则跳过）
→ 调用 Sim2Real 已有动作切换接口 → 机器人挥手 5.44 s → 回到默认模式
```

连接程序自始至终只是一个**安全、克制的动作名称搬运工**，所有底层执行信任并复用已在真机上跑通的 Sim2Real 系统。
