# Mini Pi Plus 自采动作：从动作采集到真机部署完整指南

> 适用对象：Ziyi 当前使用的 HighTorque Mini Pi Plus Pro、GMR、Isaac Lab、BeyondMimic、MuJoCo sim2sim 与 Orin 真机部署流程。  
> 当前已验证环境：`Mini-Pi-Plus_BeyondMimic`、Isaac Sim 5.1.0、Isaac Lab、22 DoF Mini Pi Plus。  
> 本指南以已经验证效果良好的 `wave_v73` 招手动作为示例。

---

## 0. 总流程

```text
动作采集
  ↓
原始 BVH 检查与裁剪
  ↓
T-pose / 骨架 / 坐标系确认
  ↓
使用泛化 JSON + IKConfig 做 GMR 重定向
  ↓
输出 Mini Pi Plus 关节 CSV
  ↓
CSV 格式标准化：7 root + 22 joints
  ↓
CSV → NPZ
  ↓
replay_npz 检查参考动作
  ↓
BeyondMimic 强化学习训练
  ↓
play.py 检查策略效果
  ↓
导出 action-only ONNX
  ↓
MuJoCo sim2sim + future JSON
  ↓
上传 ONNX / JSON 到 Orin
  ↓
Orin 使用 trtexec 转 TRT
  ↓
motion YAML 指向 TRT 和 future JSON
  ↓
在 rl_config / custom_action 中注册动作
  ↓
重启 ROS 启动文件
  ↓
低风险真机测试
```

---

# 1. 固定环境与关键路径

## 1.1 6K 服务器

项目目录：

```bash
/home/ziyi/daima/Mini-Pi-Plus_BeyondMimic
```

GMR / 动作调试目录：

```bash
/home/ziyi/daima/motions
```

Isaac Lab Conda 环境：

```bash
isaaclab311
```

Isaac Sim 5.1.0：

```bash
/home/ziyi/isaac-sim-standalone-5.1.0-linux-x86_64
```

Isaac Lab：

```bash
/home/ziyi/daima/IsaacLab
```

已建立链接：

```bash
/home/ziyi/daima/IsaacLab/_isaac_sim
  -> /home/ziyi/isaac-sim-standalone-5.1.0-linux-x86_64
```

## 1.2 Mini Pi Plus 关键约束

- 训练与部署按 **22 DoF** 处理。
- 不能误用默认 26 DoF 配置。
- MuJoCo XML：

```bash
GMR/assets/pi_plus_24dof_250826/xml/pi_22dof_0826.xml
```

- 真机 ROS 启动文件：

```bash
joy_control_pi_plus_orin.launch
```

- 启动时需要确认：

```text
dof_type = 22
```

---

# 2. 版本命名规范

每一个动作全链路统一使用同一个名字。

以招手为例：

```text
wave_v73.bvh
wave_v73.csv
wave_v73.npz
wave_v73.pt
wave_v73_action.onnx
wave_v73_action.trt
wave_v73.json
wave_v73.yaml
```

建议含义：

```text
wave       动作类别
v73        当前泛化 JSON / IKConfig 版本
known_good 已人工确认效果良好
```

禁止使用模糊名字：

```text
new.csv
final2.csv
test_ok.csv
motion_latest.csv
```

---

# 3. 动作采集

## 3.1 采集前准备

每次自采动作建议同时录制：

1. 3–5 秒标准 T-pose。
2. 2–3 秒自然站立。
3. 正式动作。
4. 2–3 秒结束站立。

一个片段推荐结构：

```text
T-pose
  ↓
自然站立
  ↓
动作开始
  ↓
完整动作
  ↓
回到自然站立
```

## 3.2 采集要求

- 双脚尽量固定，除非动作本身包含移动。
- 避免遮挡肩、肘、手腕和髋部。
- 动作不要贴近身体，避免动捕系统混淆。
- 正式招手建议先做低速、清晰、大幅版本。
- 保留原始高帧率 BVH，不要覆盖。
- 每次采集记录：
  - 动捕设备；
  - 原始 FPS；
  - 坐标系；
  - 骨架名称；
  - 动作说明；
  - 是否有 T-pose；
  - 是否出现丢帧或骨架跳变。

## 3.3 原始动作不等于可训练动作

强化学习需要的不是原始人类动作，而是：

```text
已经重定向到 Mini Pi Plus 22 DoF 结构的动作
```

因此原始 BVH 不能直接送入训练。

---

# 4. GMR 重定向

## 4.1 目的

将人类骨架动作转换为 Mini Pi Plus 可以表达的：

- root 位置；
- root 四元数；
- 22 个机器人关节角。

## 4.2 当前已验证的泛化配置

当前招手动作使用的 7.3 版本已验证效果良好。

已保存示例：

```bash
/home/ziyi/daima/motions/presets/eiri_pi_plus_v73/examples/eiri_wave_v73_known_good.csv
```

跑步示例：

```bash
/home/ziyi/daima/motions/presets/eiri_pi_plus_v73/examples/eiri_running_v73_known_good.csv
```

这两个 `known_good` 文件可作为以后判断新动作是否异常的参考。

## 4.3 重定向命令模板

进入 GMR 环境：

```bash
cd /home/ziyi/daima/Mini-Pi-Plus_BeyondMimic
conda activate gmr
```

命令模板：

```bash
python scripts/bvh_to_robot.py \
  --bvh_file "/你的原始动作路径/your_motion.bvh" \
  --robot pi_football \
  --save_path "/home/ziyi/daima/motions/ik_debug/your_motion_v73.csv" \
  --rate_limit
```

注意：

- 真实命令需要使用当前项目中已经验证的 v7.3 JSON / IKConfig。
- 不同仓库版本对 JSON 参数的传入方式可能不同。
- 应优先复制你已经成功生成 `eiri_wave_v73_known_good.csv` 时使用的命令。
- 不要临时改动泛化 JSON 后覆盖 `known_good` 配置。

## 4.4 重定向阶段重点检查

### 躯干

- 初始是否后仰；
- 动作中是否无理由侧倾；
- root 朝向是否正确；
- 结束是否回到站立。

### 下肢

- 膝盖是否反折；
- 脚底是否穿地；
- 两脚是否漂移；
- 髋关节是否突然旋转；
- 静态动作中腿部是否抖动。

### 上肢

- 肩 pitch / roll 是否对应正确；
- 肘部弯曲方向是否正确；
- 手腕是否突然翻转；
- 招手是否由手臂完成，而不是全身侧倾代偿。

## 4.5 什么时候不能进入训练

出现以下任意情况，不要直接靠强化学习“修”：

- 关节旋转方向明显错误；
- root 朝向错误；
- 身体折叠；
- 脚底严重漂移；
- 动作速度相差数倍；
- 第一帧或最后一帧突然跳变；
- CSV 关节顺序与 22 DoF 模型不一致。

这些都属于数据或重定向问题，不是奖励函数问题。

---

# 5. CSV 标准化

## 5.1 Mini Pi Plus 训练 CSV 标准格式

训练脚本需要：

```text
7 root 列 + 22 joint 列 = 29 列
```

root 列：

```text
root pos x
root pos y
root pos z
root rot x
root rot y
root rot z
root rot w
```

22 个关节列：

```text
l_hip_pitch
l_hip_roll
l_thigh
l_calf
l_ankle_pitch
l_ankle_roll
r_hip_pitch
r_hip_roll
r_thigh
r_calf
r_ankle_pitch
r_ankle_roll
l_shoulder_pitch
l_shoulder_roll
l_upper_arm
l_elbow
l_wrist
r_shoulder_pitch
r_shoulder_roll
r_upper_arm
r_elbow
r_wrist
```

## 5.2 `frame` 列问题

部分 GMR 输出会生成：

```text
frame + 7 root + 22 joints = 30 列
```

而 `csv_to_npz.py` 不会自动忽略 `frame`，会把数据解析成 23 个关节，报错：

```text
RuntimeError: shape mismatch:
value tensor of shape [23]
cannot be broadcast to indexing result of shape [1, 22]
```

因此，进入 NPZ 转换前必须移除最前面的 `frame` 列。

## 5.3 安全删除 `frame` 列

这段命令不会覆盖原始 `known_good` 文件：

```bash
cd /home/ziyi/daima/Mini-Pi-Plus_BeyondMimic

SOURCE_CSV="/home/ziyi/daima/motions/presets/eiri_pi_plus_v73/examples/eiri_wave_v73_known_good.csv"
TARGET_CSV="source/motion/hightorque/pi_plus/csv/wave_v73.csv"

mkdir -p "$(dirname "${TARGET_CSV}")"

python - "${SOURCE_CSV}" "${TARGET_CSV}" <<'PY'
import csv
import os
import sys

source = sys.argv[1]
target = sys.argv[2]

if not os.path.isfile(source):
    raise SystemExit(f"[ERROR] 输入文件不存在：{source}")

with open(source, "r", newline="", encoding="utf-8-sig") as f:
    rows = list(csv.reader(f))

if not rows:
    raise SystemExit("[ERROR] CSV 是空文件")

header = rows[0]

if header[0].strip().lower() == "frame":
    rows = [row[1:] for row in rows]
elif len(header) == 29:
    print("[INFO] CSV 已经没有 frame 列，不重复删除")
else:
    raise SystemExit(
        f"[ERROR] 无法安全识别格式：第一列={header[0]!r}，总列数={len(header)}"
    )

if len(rows[0]) != 29:
    raise SystemExit(f"[ERROR] 标准格式应为29列，实际为{len(rows[0])}列")

for i, row in enumerate(rows[1:], start=2):
    if len(row) != 29:
        raise SystemExit(f"[ERROR] 第{i}行列数异常：{len(row)}")

with open(target, "w", newline="", encoding="utf-8") as f:
    csv.writer(f).writerows(rows)

print("[SUCCESS] 输出：", target)
print("列数：", len(rows[0]))
print("数据帧数：", len(rows) - 1)
PY
```

## 5.4 检查 CSV

```bash
python - <<'PY'
import csv

path = "source/motion/hightorque/pi_plus/csv/wave_v73.csv"

with open(path, newline="", encoding="utf-8-sig") as f:
    reader = csv.reader(f)
    header = next(reader)
    first = next(reader)

print("表头列数：", len(header))
print("首帧列数：", len(first))
print("第一列：", header[0])
print("最后一列：", header[-1])

assert len(header) == 29
assert len(first) == 29
assert header[0] == "root pos x"

print("[SUCCESS] 7 root + 22 joints")
PY
```

---

# 6. Isaac Lab 环境初始化

每次新开 SSH 或 tmux 后，先执行：

```bash
cd /home/ziyi/daima/Mini-Pi-Plus_BeyondMimic

source /home/ziyi/miniconda3/etc/profile.d/conda.sh
conda activate isaaclab311

source /home/ziyi/isaac-sim-standalone-5.1.0-linux-x86_64/setup_conda_env.sh

export ISAACSIM_PATH="/home/ziyi/isaac-sim-standalone-5.1.0-linux-x86_64"
export ISAACSIM_PYTHON_EXE="${ISAACSIM_PATH}/python.sh"
```

当前已验证版本：

```text
Python       3.11.15
NumPy        1.26.4
PyTorch      2.7.0+cu128
CUDA runtime 12.8
Isaac Sim    5.1.0
GPU          NVIDIA RTX PRO 6000 Blackwell
```

## 6.1 为什么不能直接 `import whole_body_tracking`

直接运行：

```bash
python -c "import whole_body_tracking"
```

可能报：

```text
No module named 'omni'
```

这不一定代表扩展损坏，而是 Isaac Sim AppLauncher 尚未启动。

应通过：

```bash
python scripts/csv_to_npz.py ...
python scripts/rsl_rl/train.py ...
python scripts/rsl_rl/play.py ...
```

等正式入口启动 Isaac Sim。

---

# 7. CSV 转 NPZ

## 7.1 当前招手动作

```bash
cd /home/ziyi/daima/Mini-Pi-Plus_BeyondMimic

source /home/ziyi/miniconda3/etc/profile.d/conda.sh
conda activate isaaclab311
source /home/ziyi/isaac-sim-standalone-5.1.0-linux-x86_64/setup_conda_env.sh

INPUT_CSV="source/motion/hightorque/pi_plus/csv/wave_v73.csv"
OUTPUT_NPZ="source/motion/hightorque/pi_plus/npz/wave_v73"

mkdir -p "$(dirname "${OUTPUT_NPZ}")"
rm -f "${OUTPUT_NPZ}.npz"

python scripts/csv_to_npz.py \
  --robot pi_plus \
  --input_file "${INPUT_CSV}" \
  --input_fps 30 \
  --output_fps 50 \
  --output_name "${OUTPUT_NPZ}" \
  --no_wandb \
  --headless

RC=$?

echo "实际退出码：${RC}"

if [ "${RC}" -eq 0 ] && [ -f "${OUTPUT_NPZ}.npz" ]; then
    echo "[SUCCESS]"
    ls -lh "${OUTPUT_NPZ}.npz"
else
    echo "[FAILED]"
fi
```

## 7.2 FPS 原则

`--input_fps` 必须对应当前 CSV 的实际采样率。

例如：

- 原始 BVH 是 120 FPS；
- GMR 输出时已限制为 30 FPS；
- 那么 CSV → NPZ 应使用 `--input_fps 30`。

如果把 120 FPS 数据误写成 30 FPS，动作可能慢四倍。反之则可能快四倍。

---

# 8. NPZ 回放验证

```bash
cd /home/ziyi/daima/Mini-Pi-Plus_BeyondMimic

source /home/ziyi/miniconda3/etc/profile.d/conda.sh
conda activate isaaclab311
source /home/ziyi/isaac-sim-standalone-5.1.0-linux-x86_64/setup_conda_env.sh

python scripts/replay_npz.py \
  --robot pi_plus \
  --motion_file source/motion/hightorque/pi_plus/npz/wave_v73.npz
```

## 8.1 必须检查

- 动作速度是否正确；
- 第一帧是否正常；
- 最后一帧是否正常；
- 循环回第一帧时是否跳变；
- 双脚是否稳定；
- root 高度是否正确；
- 躯干是否过度倾斜；
- 手臂轨迹是否符合人类动作；
- 手腕是否翻转；
- 腿部是否出现无意义动作。

## 8.2 判断原则

```text
NPZ 回放错误
→ 优先修 CSV / FPS / IK / root / 关节顺序

NPZ 回放正确，但训练策略错误
→ 再检查训练、奖励和策略
```

---

# 9. 强化学习训练

## 9.1 第一轮训练原则

对一个新动作，第一轮建议：

- 使用官方 baseline；
- 不修改 PPO；
- 不修改 observation；
- 不修改 reward；
- 不修改 PD；
- 不恢复舞蹈 checkpoint；
- 从头训练一个独立 run。

招手动作是双脚稳定、上肢局部动作为主，通常比跑步和大幅舞蹈更容易训练。

## 9.2 建立 tmux

```bash
tmux new -s wave_v73_train
```

## 9.3 开始训练

在 tmux 内执行：

```bash
cd /home/ziyi/daima/Mini-Pi-Plus_BeyondMimic

source /home/ziyi/miniconda3/etc/profile.d/conda.sh
conda activate isaaclab311
source /home/ziyi/isaac-sim-standalone-5.1.0-linux-x86_64/setup_conda_env.sh

export ISAACSIM_PATH="/home/ziyi/isaac-sim-standalone-5.1.0-linux-x86_64"
export ISAACSIM_PYTHON_EXE="${ISAACSIM_PATH}/python.sh"

export CUDA_VISIBLE_DEVICES=0

MOTION_FILE="source/motion/hightorque/pi_plus/npz/wave_v73.npz"
LOG_FILE="train_wave_v73_$(date +%Y%m%d_%H%M%S).log"

python scripts/rsl_rl/train.py \
  --task=Tracking-Flat-PI-Plus-Wo-v0 \
  --motion_file "${MOTION_FILE}" \
  --headless \
  --log_project_name pi_plus_beyondmimic \
  --run_name wave_v73 \
  2>&1 | tee "${LOG_FILE}"
```

## 9.4 从 tmux 退出但保持训练

按：

```text
Ctrl+B
松开
D
```

重新进入：

```bash
tmux attach -t wave_v73_train
```

查看：

```bash
tmux ls
```

## 9.5 检查训练是否仍在运行

```bash
ps -ef | grep -E "scripts/rsl_rl/train.py|wave_v73" | grep -v grep
```

查看 GPU：

```bash
watch -n 2 nvidia-smi
```

退出：

```text
Ctrl+C
```

## 9.6 查看训练日志

```bash
cd /home/ziyi/daima/Mini-Pi-Plus_BeyondMimic

ls -lt train_wave_v73_*.log | head

tail -n 100 "$(ls -t train_wave_v73_*.log | head -n 1)"
```

---

# 10. 查找 checkpoint

```bash
cd /home/ziyi/daima/Mini-Pi-Plus_BeyondMimic

LATEST_RUN="$(
  find logs/rsl_rl \
    -mindepth 2 -maxdepth 3 \
    -type d \
    -printf '%T@ %p\n' 2>/dev/null \
  | sort -nr \
  | head -n 1 \
  | cut -d' ' -f2-
)"

echo "最新 run：${LATEST_RUN}"

find "${LATEST_RUN}" \
  -maxdepth 1 \
  -type f \
  -name "model_*.pt" \
  | sort -V \
  | tail -n 20
```

注意：不同版本的日志层级可能不同。若没找到，使用：

```bash
find logs/rsl_rl -type f -name "model_*.pt" \
  -printf '%T@ %TY-%Tm-%Td %TH:%TM:%TS %p\n' \
  | sort -nr \
  | head -n 30
```

---

# 11. 中途播放训练策略

选择一个 checkpoint 后：

```bash
cd /home/ziyi/daima/Mini-Pi-Plus_BeyondMimic

source /home/ziyi/miniconda3/etc/profile.d/conda.sh
conda activate isaaclab311
source /home/ziyi/isaac-sim-standalone-5.1.0-linux-x86_64/setup_conda_env.sh

MOTION_FILE="source/motion/hightorque/pi_plus/npz/wave_v73.npz"
RUN_NAME="替换为真实run目录"
CHECKPOINT="替换为真实model_xxx.pt"

python scripts/rsl_rl/play.py \
  --task=Tracking-Flat-PI-Plus-Wo-v0 \
  --play_full_motion \
  --num_envs=2 \
  --load_run="${RUN_NAME}" \
  --checkpoint="${CHECKPOINT}" \
  --motion_file="${MOTION_FILE}"
```

若当前版本接受 checkpoint 完整路径，可直接使用：

```bash
python scripts/rsl_rl/play.py \
  --task=Tracking-Flat-PI-Plus-Wo-v0 \
  --play_full_motion \
  --num_envs=2 \
  --checkpoint="/完整路径/model_xxx.pt" \
  --motion_file="${MOTION_FILE}"
```

以实际 `--help` 为准：

```bash
python scripts/rsl_rl/play.py --help
```

---

# 12. 判断训练效果

## 12.1 成功表现

- 能稳定站立；
- 手臂能跟踪招手轨迹；
- 身体只有合理的小幅重心调整；
- 双脚基本不滑；
- 腿部没有高频抖动；
- 动作开始和结束自然；
- 多次循环不会快速失稳。

## 12.2 常见现象与原因

| 现象 | 更可能的问题 |
|---|---|
| 策略立即倒地 | 初始姿态、root 高度、参考速度、termination |
| 能站但不挥手 | 上肢跟踪奖励相对不足 |
| 手臂动但幅度小 | 关节位置跟踪权重不足或动作太难 |
| 身体严重侧倾 | 参考动作躯干倾斜或 base 姿态约束不足 |
| 脚滑 | 足部接触、root 轨迹、下肢参考、摩擦或奖励 |
| 腿部抖动 | action rate、joint acceleration、PD 或参考噪声 |
| 仿真正常但 sim2sim 差 | XML、关节顺序、PD、观测或延迟差异 |
| sim2sim 正常但真机保护 | TRT、22/26 DoF、YAML、控制入口、安全阈值 |

## 12.3 第一轮不要急着改 reward

先确认：

1. NPZ 正常；
2. checkpoint 足够后期；
3. play 使用了正确 run 和 NPZ；
4. 训练没有加载旧舞蹈模型；
5. 训练任务与官方 baseline 一致。

之后再考虑调整：

- 上肢关节跟踪；
- base orientation；
- feet slip；
- action rate；
- joint acceleration；
- contact stability。

---

# 13. 导出 ONNX

## 13.1 原则

真机部署建议使用：

```text
action-only ONNX
```

不要误传仅用于普通推理测试、输出结构不同的 ONNX。

## 13.2 建议做法

先使用当前仓库已经验证过的官方导出流程。不同提交版本可能：

- 在 `play.py` 运行时自动导出；
- 使用独立 export 参数；
- 将文件保存到 `logs/exported/`。

先检查：

```bash
python scripts/rsl_rl/play.py --help | grep -i -E "export|onnx|policy"
```

然后在播放最终 checkpoint 时观察输出目录：

```bash
find logs -type f -name "*.onnx" \
  -printf '%T@ %TY-%Tm-%Td %TH:%TM:%TS %p\n' \
  | sort -nr \
  | head -n 30
```

最终统一命名：

```text
wave_v73_action.onnx
```

并单独保存 checkpoint 对应关系：

```text
wave_v73_action.onnx
← model_XXXXX.pt
← wave_v73.npz
← v7.3 JSON / IKConfig
```

---

# 14. MuJoCo sim2sim 与 future JSON

## 14.1 作用

sim2sim 用于检查：

```text
Isaac Lab 策略
→ MuJoCo 动力学
→ 真机部署前兼容性
```

同时生成真机需要的 future motion JSON。

## 14.2 命令模板

```bash
cd /home/ziyi/daima/Mini-Pi-Plus_BeyondMimic
conda activate mujoco_tg

python scripts/sim2sim.py \
  --robot pi_plus \
  --motion_file source/motion/hightorque/pi_plus/npz/wave_v73.npz \
  --xml_path GMR/assets/pi_plus_24dof_250826/xml/pi_22dof_0826.xml \
  --policy_path logs/exported/wave_v73_action.onnx \
  --save_json
```

确认输出：

```text
wave_v73.json
```

## 14.3 sim2sim 检查

- 机器人是否能站住；
- 动作速度是否一致；
- 上肢是否跟踪；
- 腿部是否抖动；
- root 是否漂移；
- 动作循环是否稳定；
- 策略输入输出维度是否正确；
- 关节顺序是否一致。

---

# 15. 部署文件清单

真机至少需要：

```text
wave_v73_action.onnx
wave_v73_action.trt
wave_v73.json
wave_v73.yaml
```

以及已有系统中的：

```text
pi_plus_22dof_rl_config.yaml
custom_action / base_policy 动作入口
joy_control_pi_plus_orin.launch
```

---

# 16. 从 6K 传输到笔记本，再传到 Orin

由于 6K 是 SSH 环境，可使用笔记本中转。

## 16.1 6K → Windows 笔记本

在 Windows CMD 或 PowerShell 中执行，示例：

```powershell
scp -F F:\ssh_config\config `
  pro6k:/home/ziyi/daima/Mini-Pi-Plus_BeyondMimic/logs/exported/wave_v73_action.onnx `
  "$env:USERPROFILE\Desktop\"
```

传 future JSON：

```powershell
scp -F F:\ssh_config\config `
  pro6k:/home/ziyi/daima/Mini-Pi-Plus_BeyondMimic/你的JSON输出目录/wave_v73.json `
  "$env:USERPROFILE\Desktop\"
```

实际主机别名以你的 SSH config 为准。

## 16.2 Windows 笔记本 → Orin

```powershell
scp "$env:USERPROFILE\Desktop\wave_v73_action.onnx" `
  nvidia@机器人IP:/home/nvidia/sim2real/policies/
```

```powershell
scp "$env:USERPROFILE\Desktop\wave_v73.json" `
  nvidia@机器人IP:/home/nvidia/sim2real/motions/
```

目录名称以机器人当前已运行的 dance2 文件所在位置为准。部署新动作时，最安全的方法是：

```text
复制已成功运行的 dance2 文件到同级目录
然后只替换动作名称和对应文件
```

---

# 17. Orin 上将 ONNX 转 TRT

SSH 到机器人：

```bash
ssh nvidia@机器人IP
```

进入策略目录：

```bash
cd /home/nvidia/sim2real/policies
```

转换模板：

```bash
/usr/src/tensorrt/bin/trtexec \
  --onnx=wave_v73_action.onnx \
  --saveEngine=wave_v73_action.trt \
  --fp16
```

如果系统中的 `trtexec` 不在该路径：

```bash
which trtexec
find /usr -type f -name trtexec 2>/dev/null | head
```

确认输出：

```bash
ls -lh wave_v73_action.onnx wave_v73_action.trt
```

---

# 18. 创建 motion YAML

不要从零编造 YAML。应复制一个已经成功运行的动作配置，例如 `dance2_10_16s.yaml`：

```bash
cp dance2_10_16s.yaml wave_v73.yaml
```

只修改与动作绑定相关的字段：

```yaml
policy_name: wave_v73_action.trt
future_file_name: wave_v73.json
```

如果原 YAML 含有：

- `motion_len`
- `action_scale`
- `control_frequency`
- `num_single_obs`
- `algorithm`
- `motor_group`

第一轮先保留官方可用配置，不随意改动。

当前已知系统参数示例：

```text
algorithm: bydmmc
motor_group: all-pi_plus_bydmmc
num_single_obs: 119
dof_type: 22
```

`motion_len` 应根据当前系统实际单位和 future JSON 长度设置，不要直接复制旧动作的 `1000.2`，除非已经确认系统就是这样解释该字段。

---

# 19. 在 rl_config / custom_action 中注册动作

## 19.1 RL 配置

当前使用：

```text
pi_plus_22dof_rl_config.yaml
```

将新 motion 添加到与 `dance2_10_16s` 同级的位置。

推荐操作：

1. 先备份；
2. 复制已有动作条目；
3. 仅修改动作名称和 YAML 路径；
4. 保持缩进完全一致。

备份：

```bash
cp pi_plus_22dof_rl_config.yaml \
   pi_plus_22dof_rl_config.yaml.bak_$(date +%Y%m%d_%H%M%S)
```

## 19.2 custom_action / base_policy

机器人手柄动作入口可能在：

```text
base_policy
custom_action
rl_config
```

新动作必须注册到实际被 ROS 节点读取的入口。

判断是否注册成功：

- 默认模式仍能正常进入；
- 手柄组合键能切换到新动作；
- 日志中能看到 `wave_v73`；
- 不再提示找不到 motion / policy；
- 不会因为错误入口直接进入保护。

---

# 20. 启动文件

使用：

```bash
joy_control_pi_plus_orin.launch
```

确认：

```text
dof_type = 22
```

不要保留默认 26 DoF。

启动前检查：

```bash
grep -R "dof_type" \
  /home/nvidia/sim2real/src \
  /home/nvidia/sim2real/config \
  2>/dev/null | head -n 50
```

---

# 21. 真机测试前安全检查

## 21.1 机械安全

- 机器人放在开阔、防滑地面；
- 周围没有电线和障碍物；
- 旁边有人可以扶住；
- 手柄停止键明确；
- 电池电量足够；
- 关节没有机械卡滞；
- 上肢招手范围不会碰撞身体；
- 首次测试不要站在机器人正前方。

## 21.2 软件安全

确认：

```text
22 DoF
正确 TRT
正确 future JSON
正确 YAML
正确动作入口
正确 motor group
正确 algorithm
默认模式正常
```

## 21.3 第一次测试原则

1. 重启机器人。
2. 等待进入正常默认模式。
3. 先测试默认站立和行走。
4. 确认机器人没有异常报警。
5. 再切换到新动作。
6. 第一次只运行一个短周期。
7. 观察：
   - 是否立即保护；
   - 是否腿部异常；
   - 是否上肢方向正确；
   - 是否身体过度倾斜；
   - 是否完成后返回默认模式。

---

# 22. 不要使用危险的进程清理命令

不要直接执行：

```bash
pkill -f ros
```

它可能把机器人本身正常运行的关键节点全部关闭，导致：

- 无法进入默认模式；
- 控制器失联；
- 机器人停在 loading；
- 必须重启恢复。

更安全的做法：

```bash
ps -ef | grep ros
```

找到明确的测试节点后，只终止指定 PID：

```bash
kill PID
```

若不确定，优先重启机器人并恢复已验证配置，而不是批量杀 ROS。

---

# 23. 真机失败时的定位顺序

## 23.1 进入保护模式

依次检查：

1. TRT 是否能加载；
2. ONNX 输入输出是否与部署框架一致；
3. `dof_type` 是否为 22；
4. YAML 是否指向正确 TRT；
5. YAML 是否指向正确 JSON；
6. JSON 是否与该动作 NPZ 对应；
7. RL 配置是否注册；
8. 手柄入口是否调用了正确动作；
9. action scale 是否过大；
10. 策略是否在 sim2sim 已经稳定。

## 23.2 新动作无法被手柄调用

表现：

```text
默认模式正常
但按键后没有动作
```

更可能是：

- motion 未注册；
- custom_action 没有入口；
- 按键映射错误；
- YAML 名称与注册名称不一致。

## 23.3 按键后立即保护

更可能是：

- 22/26 DoF 冲突；
- TRT 输入输出不匹配；
- future JSON 不对应；
- action scale 不合理；
- 控制模式或 motor group 错误；
- 真机初始姿态与训练初始姿态差异过大。

## 23.4 仿真好、真机差

优先检查：

- sim2sim 是否真的使用 22 DoF XML；
- PD 参数；
- observation 维度；
- `num_single_obs=119`；
- action-only ONNX；
- TRT 转换；
- 关节顺序；
- 真机控制频率；
- 推理延迟；
- 初始站姿；
- 电机限制和保护阈值。

---

# 24. 当前 `wave_v73` 的已完成状态

截至本指南生成时：

- 自采动作完成；
- 泛化 JSON 完成；
- IKConfig 完成；
- GMR 重定向完成；
- `eiri_wave_v73_known_good.csv` 已保存；
- `frame` 列问题已识别；
- 标准 29 列 CSV 已生成；
- `wave_v73.npz` 已生成；
- NPZ 回放效果很好；
- 下一阶段：BeyondMimic 强化学习训练。

当前正式 NPZ：

```bash
/home/ziyi/daima/Mini-Pi-Plus_BeyondMimic/source/motion/hightorque/pi_plus/npz/wave_v73.npz
```

当前建议训练命令：

```bash
cd /home/ziyi/daima/Mini-Pi-Plus_BeyondMimic

source /home/ziyi/miniconda3/etc/profile.d/conda.sh
conda activate isaaclab311
source /home/ziyi/isaac-sim-standalone-5.1.0-linux-x86_64/setup_conda_env.sh

export CUDA_VISIBLE_DEVICES=0

python scripts/rsl_rl/train.py \
  --task=Tracking-Flat-PI-Plus-Wo-v0 \
  --motion_file source/motion/hightorque/pi_plus/npz/wave_v73.npz \
  --headless \
  --log_project_name pi_plus_beyondmimic \
  --run_name wave_v73
```

---

# 25. 每个动作的最小验收清单

## A. 数据

- [ ] 原始 BVH 已备份
- [ ] 原始 FPS 已记录
- [ ] 有 T-pose
- [ ] GMR 输出已检查
- [ ] root 朝向正确
- [ ] 22 个关节顺序正确
- [ ] CSV 无多余 `frame` 列
- [ ] CSV 共 29 列
- [ ] NPZ 成功生成
- [ ] NPZ 回放正确

## B. 训练

- [ ] 使用正确任务
- [ ] 使用正确 NPZ
- [ ] 新 run 从头训练
- [ ] checkpoint 正常保存
- [ ] play 动作稳定
- [ ] 双脚无明显滑动
- [ ] 身体无过度倾斜
- [ ] 动作循环稳定

## C. 导出

- [ ] 记录最终 checkpoint
- [ ] 导出 action-only ONNX
- [ ] ONNX 与该 checkpoint 对应
- [ ] sim2sim 正常
- [ ] future JSON 已生成
- [ ] 文件统一命名

## D. 真机

- [ ] ONNX 已上传
- [ ] JSON 已上传
- [ ] TRT 转换成功
- [ ] YAML 指向正确 TRT
- [ ] YAML 指向正确 JSON
- [ ] 22 DoF
- [ ] RL config 已注册
- [ ] custom_action 已注册
- [ ] 默认模式正常
- [ ] 低风险测试成功

---

# 26. 每次动作建议保存的归档包

建议每个完成动作单独保存：

```text
wave_v73_release/
├── README.md
├── source/
│   ├── raw.bvh
│   ├── retarget_config.json
│   └── ik_config.json
├── motion/
│   ├── wave_v73_known_good.csv
│   └── wave_v73.npz
├── training/
│   ├── model_XXXXX.pt
│   ├── train_log.txt
│   └── config_snapshot/
├── export/
│   ├── wave_v73_action.onnx
│   ├── wave_v73_action.trt
│   └── wave_v73.json
├── deployment/
│   ├── wave_v73.yaml
│   └── rl_config_entry.txt
└── validation/
    ├── replay_npz.mp4
    ├── play.mp4
    ├── sim2sim.mp4
    └── real_robot.mp4
```

这样以后可以明确追溯：

```text
某个真机动作
对应哪一个 BVH
哪套 JSON / IKConfig
哪一个 NPZ
哪一个 checkpoint
哪一个 ONNX / TRT / JSON
哪一版真机配置
```

---

# 27. 最小版 SOP

```text
1. 自采 BVH，并保留 T-pose
2. 使用当前稳定泛化 JSON + IKConfig 做 GMR
3. 检查重定向动作
4. 标准化 CSV 为 7 root + 22 joints
5. csv_to_npz.py 转 NPZ
6. replay_npz.py 检查
7. train.py 从头训练
8. play.py 检查 checkpoint
9. 导出 action-only ONNX
10. sim2sim.py 验证并生成 future JSON
11. 上传 ONNX 和 JSON 到 Orin
12. trtexec 转 action TRT
13. motion YAML 指向 TRT 和 JSON
14. rl_config / custom_action 注册动作
15. 确认 dof_type=22
16. 重启 roslaunch
17. 默认模式测试
18. 低风险执行新动作
```

---

## 最重要的原则

```text
重定向错误，不要用强化学习硬修。
NPZ 错误，不要进入训练。
Isaac 仿真未稳定，不要进入 sim2sim。
sim2sim 未稳定，不要进入真机。
真机配置不确定，不要批量杀 ROS。
每次只修改一层，并保留可恢复版本。
```
