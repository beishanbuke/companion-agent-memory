# Mini Pi Plus `wave_v73_rt` 正常速度招手动作：从部署包到真机执行的完整部署流程

## 1. 部署目标

本文记录 `wave_v73_rt` 正常速度招手动作从部署包进入 Orin，到最终在 Mini Pi Plus Pro 真机上通过 `RT + B` 独立触发执行的完整文件流转、文件转换、安装位置和操作顺序。

当前该动作的训练参考数据为：

```text
272 frames
50 FPS
duration ≈ 5.44 s
```

action-only policy 接口为：

```text
INPUT:
obs [1, 119]

OUTPUT:
actions [1, 22]
```

真机 BeyondMimic 控制频率：

```text
50 Hz
```

即约每 20 ms 推理一次。

---

# 2. 最初的部署包

最初用于部署的文件：

```text
wave_v73_rt_deploy.tar.gz
```

Windows 上大小约：

```text
8.2 MB
```

包内结构：

```text
wave_v73_rt_deploy/
│
├── wave_v73_rt_action.onnx
├── wave_v73_rt.json
├── README.txt
├── SHA256SUMS.txt
│
└── archive/
    ├── model_39999.pt
    ├── wave_v73_rt_full.onnx
    └── wave_v73_rt_train.npz
```

真正进入真机运行链的核心源文件只有：

```text
wave_v73_rt_action.onnx
wave_v73_rt.json
```

以下文件仅用于训练、调试和归档：

```text
model_39999.pt
wave_v73_rt_full.onnx
wave_v73_rt_train.npz
```

---

# 3. Windows → Orin

## 3.1 上传到 Orin

Windows CMD：

```bat
scp -F NUL "%USERPROFILE%\Desktop\wave_v73_rt_deploy.tar.gz" nvidia@机器人IP:/home/nvidia/
```

本次机器人 IP 示例：

```text
10.88.51.115
```

因此实际命令：

```bat
scp -F NUL "%USERPROFILE%\Desktop\wave_v73_rt_deploy.tar.gz" nvidia@10.88.51.115:/home/nvidia/
```

上传完成后，Orin 上得到：

```text
/home/nvidia/wave_v73_rt_deploy.tar.gz
```

---

# 4. Orin 解压部署包

创建临时目录：

```bash
cd /home/nvidia
set +e

rm -rf /home/nvidia/wave_v73_rt_deploy_tmp
mkdir -p /home/nvidia/wave_v73_rt_deploy_tmp

tar -xzf \
  /home/nvidia/wave_v73_rt_deploy.tar.gz \
  -C /home/nvidia/wave_v73_rt_deploy_tmp
```

解压后：

```text
/home/nvidia/wave_v73_rt_deploy_tmp/
└── wave_v73_rt_deploy/
```

核心临时文件：

```text
/home/nvidia/wave_v73_rt_deploy_tmp/wave_v73_rt_deploy/wave_v73_rt_action.onnx

/home/nvidia/wave_v73_rt_deploy_tmp/wave_v73_rt_deploy/wave_v73_rt.json
```

---

# 5. SHA256 校验

执行：

```bash
PKG="/home/nvidia/wave_v73_rt_deploy_tmp/wave_v73_rt_deploy"

cd "$PKG"

sha256sum -c SHA256SUMS.txt
```

本次全部通过：

```text
wave_v73_rt_action.onnx: OK
wave_v73_rt.json: OK
archive/wave_v73_rt_full.onnx: OK
archive/model_39999.pt: OK
archive/wave_v73_rt_train.npz: OK
```

说明文件传输完整。

---

# 6. Action ONNX → TensorRT

## 6.1 输入模型

输入：

```text
wave_v73_rt_action.onnx
```

临时位置：

```text
/home/nvidia/wave_v73_rt_deploy_tmp/
wave_v73_rt_deploy/
wave_v73_rt_action.onnx
```

## 6.2 TensorRT 工具

Orin 使用：

```text
/usr/src/tensorrt/bin/trtexec
```

## 6.3 转换命令

```bash
BASE="/home/nvidia/sim2real/install/share/sim2real"
PKG="/home/nvidia/wave_v73_rt_deploy_tmp/wave_v73_rt_deploy"

ONNX="$PKG/wave_v73_rt_action.onnx"
TRT="$BASE/policy/motion/wave_v73_rt_action.trt"

mkdir -p "$BASE/policy/motion"

/usr/src/tensorrt/bin/trtexec \
  --onnx="$ONNX" \
  --saveEngine="$TRT"
```

转换过程：

```text
wave_v73_rt_action.onnx
        ↓
      trtexec
        ↓
wave_v73_rt_action.trt
```

本次 TensorRT 输出：

```text
&&&& PASSED TensorRT.trtexec
```

生成的 TRT 大约：

```text
2.0 MB
```

最终安装位置：

```text
/home/nvidia/sim2real/install/share/sim2real/
policy/motion/wave_v73_rt_action.trt
```

注意：

```text
wave_v73_rt_full.onnx
```

不会用于真机 TensorRT。

真机使用的是：

```text
wave_v73_rt_action.onnx
→ wave_v73_rt_action.trt
```

---

# 7. 安装 Future JSON

JSON 不需要转换，只需要复制到 Sim2Real 正式目录。

源文件：

```text
/home/nvidia/wave_v73_rt_deploy_tmp/
wave_v73_rt_deploy/
wave_v73_rt.json
```

目标位置：

```text
/home/nvidia/sim2real/install/share/sim2real/
config/future/motion/wave_v73_rt.json
```

执行：

```bash
BASE="/home/nvidia/sim2real/install/share/sim2real"
PKG="/home/nvidia/wave_v73_rt_deploy_tmp/wave_v73_rt_deploy"

mkdir -p "$BASE/config/future/motion"

cp -av \
  "$PKG/wave_v73_rt.json" \
  "$BASE/config/future/motion/wave_v73_rt.json"
```

本次 SHA256：

```text
193771424403817589350d57c9382bf927e6cb14c8d6a2638d863edc12f1bc9f
```

该 JSON 对应正常速度：

```text
272 frames
50 FPS
≈ 5.44 s
```

---

# 8. 创建 `wave_v73_rt.yaml`

这个文件不在最初部署包中，是在 Orin 上新生成的。

最终位置：

```text
/home/nvidia/sim2real/install/share/sim2real/
config/motion/wave_v73_rt.yaml
```

生成方式：

```text
复制已经真机成功的 dance2_10_16s.yaml
        ↓
保留其已验证的控制参数
        ↓
替换 policy / future 文件
        ↓
形成 wave_v73_rt.yaml
```

模板：

```text
/home/nvidia/sim2real/install/share/sim2real/
config/motion/dance2_10_16s.yaml
```

核心修改后：

```yaml
policy_name: "motion/wave_v73_rt_action.trt"

detect_falls: false

algorithm: "bydmmc"

future_file_name: "motion/wave_v73_rt.json"

motor_group: "all-pi_plus_bydmmc"

dofs: 22

num_single_obs: 119

rl_ctrl_f: 50
```

继续沿用原成功模板中的：

```text
joint_names
action_scales
kp
kd
urdf_offset
default_pose
clip_actions
clip_output
pd_ctrl_f
rl_ctrl_f
```

等参数。

当前完整运动配置仍使用：

```text
22 DoF policy
119-dimensional observation
50 Hz RL control
```

---

# 9. 注册到 RL Custom Config

文件：

```text
/home/nvidia/sim2real/install/share/sim2real/
config/pi_plus_26dof_config/
pi_plus_26dof_rl_config_custom.yaml
```

原有：

```yaml
motion:
  - name: "dance2_10_16s"
    path: "motion/dance2_10_16s.yaml"
```

新增：

```yaml
motion:
  - name: "dance2_10_16s"
    path: "motion/dance2_10_16s.yaml"

  - name: "wave_v73_rt"
    path: "motion/wave_v73_rt.yaml"
```

因此：

```text
dance2_10_16s
```

继续保留。

新动作独立注册为：

```text
wave_v73_rt
```

---

# 10. 注册到 Base Policy

文件：

```text
/home/nvidia/sim2real/install/share/sim2real/
action_config/config/pi_plus_26dof/
base_policy.yaml
```

新增动作：

```yaml
- name: "wave_v73_rt"
  policy: "wave_v73_rt"
  path: "motion/wave_v73_rt.yaml"
  remark: "wave_v73_rt"
  back_to_walk: true
  back_to_zero: true
  loop: false
```

作用：

```text
动作名称
wave_v73_rt
       ↓
找到
motion/wave_v73_rt.yaml
```

---

# 11. 注册到 Custom Action

文件：

```text
/home/nvidia/sim2real/install/share/sim2real/
action_config/config/pi_plus_26dof/
custom_action.yaml
```

最终新增：

```yaml
- name: "wave_v73_rt"
  remark: "wave_v73_rt"
  key: "rt+b"
```

现有按键保持：

```text
RT + A → cheer

RT + X → hello

RT + Y → dance2_10_16s

X      → small_kick
```

新增：

```text
RT + B → wave_v73_rt
```

因此旧动作没有被占用。

---

# 12. YAML 修复与检查

部署时曾出现：

```text
key: "rt+b"    - name: "small_kick"
```

的换行粘连问题。

已修复为：

```yaml
- name: "wave_v73_rt"
  remark: "wave_v73_rt"
  key: "rt+b"

- name: "small_kick"
  remark: "小脚踢球"
  key: "x"
```

最终以下四个 YAML 全部通过 PyYAML：

```text
custom_action.yaml
base_policy.yaml
pi_plus_26dof_rl_config_custom.yaml
wave_v73_rt.yaml
```

检查结果：

```text
[OK] YAML syntax
[OK] YAML syntax
[OK] YAML syntax
[OK] YAML syntax

[OK] ALL YAML FILES PASSED
```

---

# 13. 机器人最终运行目录

所有正式运行文件集中在：

```text
/home/nvidia/sim2real/install/share/sim2real/
```

最终结构：

```text
/home/nvidia/sim2real/install/share/sim2real/
│
├── policy/
│   └── motion/
│       └── wave_v73_rt_action.trt
│
├── config/
│   │
│   ├── future/
│   │   └── motion/
│   │       └── wave_v73_rt.json
│   │
│   ├── motion/
│   │   └── wave_v73_rt.yaml
│   │
│   └── pi_plus_26dof_config/
│       └── pi_plus_26dof_rl_config_custom.yaml
│
└── action_config/
    └── config/
        └── pi_plus_26dof/
            ├── base_policy.yaml
            └── custom_action.yaml
```

---

# 14. 为安全回滚生成的备份

在修改注册文件之前生成了备份：

```text
/home/nvidia/
pi_plus_26dof_rl_config_custom.yaml.before_wave_20260818_031903

/home/nvidia/
base_policy.yaml.before_wave_20260818_031903

/home/nvidia/
custom_action.yaml.before_wave_20260818_031903
```

另外在修复 `custom_action.yaml` 换行前，还生成了新的备份。

这些不是运行文件，只用于回滚。

---

# 15. 文件转换与部署总流程

```text
wave_v73_rt_deploy.tar.gz
          │
          ↓
Windows → SCP → Orin
          │
          ↓
/home/nvidia/wave_v73_rt_deploy.tar.gz
          │
          ↓
解压
          │
          ↓
/home/nvidia/wave_v73_rt_deploy_tmp/
wave_v73_rt_deploy/
          │
          ├───────────────────────────────┐
          │                               │
          ↓                               ↓
wave_v73_rt_action.onnx             wave_v73_rt.json
          │                               │
          │ trtexec                       │ 直接复制
          ↓                               ↓
wave_v73_rt_action.trt             wave_v73_rt.json
          │                               │
          ↓                               ↓
policy/motion/                  config/future/motion/
          │                               │
          └──────────────┬────────────────┘
                         ↓
                 wave_v73_rt.yaml
                         ↓
                  config/motion/
                         │
                         ↓
            pi_plus_26dof_rl_config_custom.yaml
                         ↓
                  base_policy.yaml
                         ↓
                 custom_action.yaml
                         ↓
                  RT+B → wave
```

---

# 16. 标准部署操作顺序

以后部署任何新的 BeyondMimic 动作，都可以按下面顺序执行。

## Step 1：准备部署包

服务器端应至少准备：

```text
xxx_action.onnx
xxx.json
```

建议同时归档：

```text
model_xxx.pt
xxx_train.npz
xxx_full.onnx
```

---

## Step 2：上传到 Orin

```bat
scp -F NUL xxx_deploy.tar.gz nvidia@机器人IP:/home/nvidia/
```

---

## Step 3：解压

```bash
mkdir -p /home/nvidia/xxx_deploy_tmp

tar -xzf \
  /home/nvidia/xxx_deploy.tar.gz \
  -C /home/nvidia/xxx_deploy_tmp
```

---

## Step 4：SHA256 校验

```bash
cd /home/nvidia/xxx_deploy_tmp/xxx_deploy

sha256sum -c SHA256SUMS.txt
```

要求：

```text
全部 OK
```

---

## Step 5：Action ONNX → TRT

```bash
/usr/src/tensorrt/bin/trtexec \
  --onnx=/临时目录/xxx_action.onnx \
  --saveEngine=/home/nvidia/sim2real/install/share/sim2real/policy/motion/xxx_action.trt
```

必须看到：

```text
&&&& PASSED TensorRT.trtexec
```

---

## Step 6：安装 Future JSON

```bash
cp xxx.json \
/home/nvidia/sim2real/install/share/sim2real/config/future/motion/xxx.json
```

---

## Step 7：创建 Motion YAML

复制已经在真机上成功运行的模板：

```bash
cp \
/home/nvidia/sim2real/install/share/sim2real/config/motion/dance2_10_16s.yaml \
/home/nvidia/sim2real/install/share/sim2real/config/motion/xxx.yaml
```

修改：

```text
policy_name
future_file_name
```

并根据 policy 确认：

```text
dofs
num_single_obs
algorithm
motor_group
```

已经真机验证的控制参数尽量保持不变：

```text
kp
kd
joint_names
action_scales
default_pose
urdf_offset
```

---

## Step 8：注册 RL Motion

修改：

```text
/home/nvidia/sim2real/install/share/sim2real/
config/pi_plus_26dof_config/
pi_plus_26dof_rl_config_custom.yaml
```

新增：

```yaml
- name: "xxx"
  path: "motion/xxx.yaml"
```

---

## Step 9：注册 Base Policy

修改：

```text
/home/nvidia/sim2real/install/share/sim2real/
action_config/config/pi_plus_26dof/
base_policy.yaml
```

新增：

```yaml
- name: "xxx"
  policy: "xxx"
  path: "motion/xxx.yaml"
  remark: "xxx"
  back_to_walk: true
  back_to_zero: true
  loop: false
```

---

## Step 10：绑定触发方式

修改：

```text
/home/nvidia/sim2real/install/share/sim2real/
action_config/config/pi_plus_26dof/
custom_action.yaml
```

例如：

```yaml
- name: "wave_v73_rt"
  remark: "wave_v73_rt"
  key: "rt+b"
```

---

## Step 11：YAML 语法检查

```bash
python3 - <<'PY'
import yaml

files = [
"/home/nvidia/sim2real/install/share/sim2real/action_config/config/pi_plus_26dof/custom_action.yaml",
"/home/nvidia/sim2real/install/share/sim2real/action_config/config/pi_plus_26dof/base_policy.yaml",
"/home/nvidia/sim2real/install/share/sim2real/config/pi_plus_26dof_config/pi_plus_26dof_rl_config_custom.yaml",
"/home/nvidia/sim2real/install/share/sim2real/config/motion/wave_v73_rt.yaml",
]

for p in files:
    with open(p) as f:
        yaml.safe_load(f)

    print("[OK]", p)
PY
```

全部必须通过。

---

# 17. 启动 Sim2Real

系统总目录：

```text
/home/nvidia/sim2real
```

环境：

```text
/home/nvidia/sim2real/install/setup.bash
```

启动文件：

```text
/home/nvidia/sim2real/install/share/
sim2real_master/launch/
joy_control_pi_plus_orin.launch
```

启动命令：

```bash
cd /home/nvidia/sim2real

source ./install/setup.bash

roslaunch sim2real_master joy_control_pi_plus_orin.launch
```

---

# 18. 真机操作顺序

系统启动正常后：

```text
LT + RT + START
        ↓
机器人站起
```

然后：

```text
LT + RT + LB
        ↓
解锁
```

等待机器人稳定站立。

执行新动作：

```text
RT + B
        ↓
wave_v73_rt
```

原动作仍然：

```text
RT + Y
        ↓
dance2_10_16s
```

---

# 19. 按下 `RT+B` 后机器人内部调用顺序

```text
RT + B
   ↓
custom_action.yaml
   ↓
wave_v73_rt
   ↓
base_policy.yaml
   ↓
pi_plus_26dof_rl_config_custom.yaml
   ↓
wave_v73_rt.yaml
   ↓
┌──────────────────────────────┬────────────────────────────┐
│                              │                            │
↓                              ↓
wave_v73_rt_action.trt         wave_v73_rt.json
│                              │
│                              ↓
│                        Future Reference
│                              │
└───────────────┬──────────────┘
                ↓
        BYDMMCFuturePolicy
                ↓
当前机器人状态 + Future Reference
                ↓
       119维 Observation
                ↓
       TensorRT Inference
                ↓
          22维 Action
                ↓
     all-pi_plus_bydmmc
                ↓
             电机
                ↓
      完成约 5.44 秒招手
```

---

# 20. 一句话版本

```text
部署包
→ Orin 解压
→ Action ONNX 转 TRT
→ Future JSON 安装
→ 创建 Motion YAML
→ 注册 RL Config
→ 注册 Base Policy
→ Custom Action 绑定按键
→ YAML 检查
→ 重启 Sim2Real
→ 站起
→ 解锁
→ RT+B
→ TRT + JSON 驱动 BYDMMC
→ 真机执行正常速度招手
```
