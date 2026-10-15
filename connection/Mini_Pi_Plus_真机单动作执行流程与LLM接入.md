# Mini Pi Plus 真机单动作执行流程与 LLM 接入说明

## 1. 目标

本文以 `wave_v73_rt` 挥手动作为例，说明 Mini Pi Plus Pro 真机上一个完整动作从程序启动、动作注册、动作触发，到 TensorRT 推理和电机执行的完整工作流，并明确 LLM 应该接入的位置。

---

## 2. 真机总目录

机器人端 Sim2Real 系统总目录：

```bash
/home/nvidia/sim2real
```

主要运行文件集中在：

```text
/home/nvidia/sim2real/
├── install/
│   ├── setup.bash
│   └── share/
│       ├── sim2real/
│       │   ├── config/
│       │   ├── policy/
│       │   └── action_config/
│       └── sim2real_master/
│           └── launch/
└── src/
```

其中：

- `install/setup.bash`：ROS / Sim2Real 环境初始化。
- `sim2real_master/launch/`：机器人总启动文件。
- `sim2real/config/`：动作、RL、future 等配置。
- `sim2real/policy/`：TensorRT 策略文件。
- `sim2real/action_config/`：动作触发/按键配置。
- `src/`：底层 ROS / C++ 源码，用于后续寻找真正的 policy switch 接口。

---

# 3. 第一步：启动机器人控制程序

## 3.1 启动文件

当前机器人使用的总启动文件：

```text
/home/nvidia/sim2real/install/share/sim2real_master/launch/joy_control_pi_plus_orin.launch
```

当前确认的核心参数：

```text
model_type = pi_plus
dof_type = 26
production_type = custom
```

注意：

- 真机硬件启动配置是 `26 DoF`。
- 当前 BeyondMimic 动作 policy 输出仍然是 `22 DoF`。
- 不应为了动作 policy 把 launch 中的 26 DoF 改成 22 DoF。

## 3.2 启动命令

```bash
cd /home/nvidia/sim2real
source ./install/setup.bash
roslaunch sim2real_master joy_control_pi_plus_orin.launch
```

这个 launch 是整个机器人动作系统的总入口。

---

# 4. 第二步：启动时加载动作注册表

因为当前：

```text
production_type = custom
dof_type = 26
```

所以当前重点使用的 RL 配置文件为：

```text
/home/nvidia/sim2real/install/share/sim2real/config/pi_plus_26dof_config/pi_plus_26dof_rl_config_custom.yaml
```

这个文件负责告诉系统：

> 当前机器人有哪些可执行的 RL / motion 动作，以及每个动作对应哪个 motion YAML。

例如逻辑上会有：

```yaml
motion:
  - name: "wave_v73_rt"
    path: "motion/wave_v73_rt.yaml"
```

因此形成：

```text
wave_v73_rt
    ↓
config/motion/wave_v73_rt.yaml
```

系统启动以后，就已经知道存在一个名为：

```text
wave_v73_rt
```

的动作。

---

# 5. 第三步：动作被触发

目前动作可以由手柄触发。

以后接入 LLM 后，LLM 只需要输出动作名称，例如：

```json
{
  "action": "wave_v73_rt"
}
```

这一步的本质是：

```text
请求 Sim2Real 执行 / 切换到 wave_v73_rt
```

而不是让 LLM 直接生成 22 个关节角。

---

# 6. 第四步：Sim2Real 加载单动作 YAML

`wave_v73_rt` 对应的单动作配置文件：

```text
/home/nvidia/sim2real/install/share/sim2real/config/motion/wave_v73_rt.yaml
```

这个文件相当于一个动作的“总配置入口”。

其核心逻辑类似：

```yaml
policy_name: "motion/wave_v73_rt_action.trt"
future_file_name: "motion/wave_v73_rt.json"
algorithm: "bydmmc"
motor_group: "all-pi_plus_bydmmc"
dofs: 22
```

它完成的核心绑定是：

```text
wave_v73_rt.yaml
    │
    ├── policy → wave_v73_rt_action.trt
    ├── future → wave_v73_rt.json
    ├── algorithm → bydmmc
    └── motor_group → all-pi_plus_bydmmc
```

---

# 7. 第五步：加载 TensorRT policy

动作 YAML 会指向：

```text
/home/nvidia/sim2real/install/share/sim2real/policy/motion/wave_v73_rt_action.trt
```

这个 TRT 文件来自训练服务器上的：

```text
model_39999.pt
    ↓
model_39999_action.onnx
    ↓ Orin 上 trtexec
wave_v73_rt_action.trt
```

当前 action-only ONNX 已确认：

```text
INPUT:
obs [1, 119]

OUTPUT:
actions [1, 22]
```

因此 TensorRT policy 的核心映射是：

```text
119维 observation
        ↓
TensorRT policy
        ↓
22维 action
```

---

# 8. 第六步：加载 Future JSON

动作 YAML 同时会指向：

```text
/home/nvidia/sim2real/install/share/sim2real/config/future/motion/wave_v73_rt.json
```

这个 JSON 来自训练服务器上的：

```text
wave_v73_rt_train.npz
        ↓
sim2sim.py --save_json
        ↓
wave_v73_rt.json
```

当前 `wave_v73_rt` 已确认：

```text
272 frames
50 FPS
duration ≈ 5.44 s
```

Future JSON 为 BeyondMimic policy 提供动作未来时刻的参考状态。

---

# 9. 第七步：BYDMMC 实时执行

动作启动后，BYDMMC 控制链开始运行。

当前控制频率：

```text
50 Hz
```

即每：

```text
20 ms
```

执行一次策略推理。

每个控制周期的逻辑：

```text
机器人当前状态
        +
Future JSON 当前/未来参考
        ↓
构造 119维 observation
        ↓
wave_v73_rt_action.trt
        ↓
得到 22维 action
        ↓
all-pi_plus_bydmmc
        ↓
对应机器人关节
```

时间轴类似：

```text
t = 0.00 s
t = 0.02 s
t = 0.04 s
t = 0.06 s
...
```

一直执行到动作结束。

---

# 10. 第八步：动作执行完成

`wave_v73_rt` 的 reference motion 约为：

```text
5.44 s
```

因此一个完整的挥手动作执行链为：

```text
joy_control_pi_plus_orin.launch
        ↓
pi_plus_26dof_rl_config_custom.yaml
        ↓
注册 wave_v73_rt
        ↓
等待动作触发
        ↓
手柄 / LLM
        ↓
"wave_v73_rt"
        ↓
wave_v73_rt.yaml
        ↓
┌─────────────────────────┬──────────────────────────┐
│                         │                          │
↓                         ↓
wave_v73_rt_action.trt     wave_v73_rt.json
│                         │
↓                         ↓
TensorRT policy            Future reference
│                         │
└──────────────┬──────────┘
               ↓
       BYDMMCFuturePolicy
               ↓
      119 obs → 22 action
               ↓
     all-pi_plus_bydmmc
               ↓
          机器人关节
               ↓
      完成约 5.44 s 挥手
```

---

# 11. 一个具体动作涉及的文件路径

| 层级 | 文件 | 完整路径 |
|---|---|---|
| ROS / Sim2Real 环境 | `setup.bash` | `/home/nvidia/sim2real/install/setup.bash` |
| 总启动入口 | `joy_control_pi_plus_orin.launch` | `/home/nvidia/sim2real/install/share/sim2real_master/launch/joy_control_pi_plus_orin.launch` |
| Custom RL 动作注册表 | `pi_plus_26dof_rl_config_custom.yaml` | `/home/nvidia/sim2real/install/share/sim2real/config/pi_plus_26dof_config/pi_plus_26dof_rl_config_custom.yaml` |
| 单动作配置 | `wave_v73_rt.yaml` | `/home/nvidia/sim2real/install/share/sim2real/config/motion/wave_v73_rt.yaml` |
| TensorRT policy | `wave_v73_rt_action.trt` | `/home/nvidia/sim2real/install/share/sim2real/policy/motion/wave_v73_rt_action.trt` |
| Future trajectory | `wave_v73_rt.json` | `/home/nvidia/sim2real/install/share/sim2real/config/future/motion/wave_v73_rt.json` |
| 动作触发配置目录 | `base_policy.yaml` / `custom_action.yaml` | `/home/nvidia/sim2real/install/share/sim2real/action_config/config/` 下的当前机器人配置目录 |

---

# 12. LLM 应该接入的位置

LLM 不应直接控制：

```text
TRT
Future JSON
119维 observation
22维 action
电机
```

LLM 应该工作在“动作选择层”。

推荐架构：

```text
用户语言
   ↓
LLM
   ↓
动作语义判断
   ↓
action = "wave_v73_rt"
   ↓
LLM → Robot Bridge
   ↓
调用 Sim2Real 已有的 policy / action 切换接口
   ↓
wave_v73_rt.yaml
   ↓
TRT + JSON
   ↓
BYDMMC
   ↓
机器人执行动作
```

例如：

```text
用户：
“跟他打个招呼”

LLM：
action = "wave_v73_rt"

Bridge：
检查动作是否在白名单中

白名单：
[
    "wave_v73_rt",
    "nod",
    "comfort_low",
    "comfort_high"
]

通过后：
调用 Sim2Real 动作切换接口
```

---

# 13. 推荐的 LLM 动作调用抽象

上层 LLM 最终只需要调用类似：

```python
execute_action("wave_v73_rt")
```

其中 `execute_action()` 不负责：

```text
关节轨迹生成
TensorRT 推理
Future trajectory
电机控制
```

它只负责：

```text
动作名称
    ↓
调用 Sim2Real 动作切换接口
```

底层已有系统继续负责：

```text
motion YAML
    ↓
TRT + JSON
    ↓
BYDMMC
    ↓
22维 action
    ↓
机器人
```

---

# 14. 推荐的最终系统结构

```text
                     用户输入
                        ↓
                       LLM
                        ↓
                Action Selector
                        ↓
               Safety / Whitelist
                        ↓
                Robot Bridge Node
                        ↓
             Sim2Real Action Interface
                        ↓
                  wave_v73_rt
                        ↓
              wave_v73_rt.yaml
                 ┌──────┴──────┐
                 ↓             ↓
              TRT Policy    Future JSON
                 └──────┬──────┘
                        ↓
                BYDMMCFuturePolicy
                        ↓
                   22维 Action
                        ↓
                     Robot
```

---

# 15. 后续还需要确认的关键接口

当前动作执行链已经明确。

为了真正实现 LLM → Robot Bridge，下一步最重要的是确认：

> 手柄当前究竟通过哪个 ROS topic、service、action 或内部函数触发 `wave_v73_rt`。

最终目标是找到：

```text
LLM
 ↓
Python Bridge
 ↓
具体 ROS topic / service
 ↓
Sim2Real policy switch
 ↓
wave_v73_rt
 ↓
wave_v73_rt.yaml
 ↓
TRT + JSON
 ↓
BYDMMC
 ↓
Robot
```

找到这个 policy switch 接口以后，就不需要模拟手柄按键，可以让 LLM Bridge 直接调用现有动作系统。

---

# 16. 一句话总结

一个具体动作在真机上的完整执行过程是：

```text
启动 Sim2Real
→ 注册动作
→ 手柄/LLM选择动作名称
→ 加载 motion YAML
→ YAML加载 TRT + Future JSON
→ BYDMMC按50Hz构造119维 observation
→ TensorRT输出22维 action
→ motor group执行
→ 完成动作
```

对于 LLM 接入，最合适的接口位置是：

```text
LLM → 动作名称 → Sim2Real policy/action switch
```

而不是：

```text
LLM → 关节角 / 电机
```
