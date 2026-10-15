#!/usr/bin/env python3
"""
机器人动作触发抽象层

提供两种实现：
- 实现A：直接调用ROS topic/service（需要Phase 0探测后填入真实接口）
- 实现B：模拟手柄按键（发布 sim2real_msg/Joy 到 /joy_msg）

实现B已通过反汇编 sim2real_master_node 二进制（MasterNode::joyMsgCallback）
与 fsm.h 源码，完整还原了 FSM 模式切换按键序列，见本文件末尾的说明。

所有ROS相关代码使用惰性导入/子进程，确保在没有ROS的环境中也能运行dry-run模式。
"""

import subprocess
import json
import time
import re
from typing import Protocol, runtime_checkable, Optional, Dict, Any
from dataclasses import dataclass
from logging import getLogger


logger = getLogger(__name__)


@runtime_checkable
class RobotActionClient(Protocol):
    """机器人动作触发客户端接口"""

    def is_robot_online(self) -> bool:
        """检测机器人主控是否在线"""
        ...

    def trigger_action(self, action_name: str) -> bool:
        """触发指定动作，返回是否成功"""
        ...


@dataclass
class RobotConfig:
    """机器人配置"""
    trigger_impl: str = "A"  # "A" 或 "B"
    action_duration: float = 5.44
    robot_check_cmd: str = "rosnode list"
    robot_node_keyword: str = ""
    joy_topic: str = "/joy_msg"
    fsm_state_topic: str = "/fsm_state"
    joy_button_sequence: list = None

    # 实现B：模式切换与动作触发参数
    ensure_custom_mode: bool = True   # 触发动作前自动切换到 ExecCustom
    ensure_standing: bool = True      # 触发动作前自动站起（INIT -> STANDBY）
    stand_up_duration: float = 4.0    # 站起等待时间（秒，覆盖 "zero" 单轨迹时长）
    mode_switch_interval: float = 0.5  # 模式切换按键之间的间隔（秒）
    action_hold: float = 0.3          # 动作按键保持时间（秒）

    # 实现A所需的ROS接口信息（Phase 0探测后填入）
    ros_topic_name: Optional[str] = None  # 如 "/action_trigger"
    ros_service_name: Optional[str] = None  # 如 "/trigger_action"
    ros_use_service: bool = False  # True=用service，False=用topic
    ros_msg_type: Optional[str] = None  # 如 "sim2real_msgs/ActionTrigger"

    def __post_init__(self):
        if self.joy_button_sequence is None:
            self.joy_button_sequence = []


class DirectSwitchClient:
    """
    实现A：直接调用策略切换接口

    Phase 0 探测完成后，需要填入真实的ROS topic或service信息。
    当前提供两种触发方式：
    1. ROS Topic：发布消息到指定topic
    2. ROS Service：调用指定service
    """

    def __init__(self, config: RobotConfig):
        self.config = config
        self._last_online_check = 0
        self._last_online_result = False

    def is_robot_online(self) -> bool:
        """通过ROS节点检测机器人是否在线"""
        # 缓存检测结果5秒
        now = time.time()
        if now - self._last_online_check < 5:
            return self._last_online_result

        self._last_online_check = now
        self._last_online_result = self._check_robot_online()
        return self._last_online_result

    def _check_robot_online(self) -> bool:
        """执行机器人在线检测"""
        try:
            # source ROS 环境后执行检测命令
            ros_setup = "/home/nvidia/sim2real/install/setup.bash"
            cmd = f"source {ros_setup} && {self.config.robot_check_cmd}"
            result = subprocess.run(
                cmd,
                shell=True,
                executable="/bin/bash",
                capture_output=True,
                text=True,
                timeout=3
            )
            output = result.stdout.strip()

            # 如果配置了节点关键字，检查是否包含该节点
            if self.config.robot_node_keyword:
                return self.config.robot_node_keyword in output

            # 没有关键字时，只要命令成功执行就认为在线
            return result.returncode == 0
        except (subprocess.TimeoutExpired, Exception) as e:
            logger.debug(f"Robot online check failed: {e}")
            return False

    def trigger_action(self, action_name: str) -> bool:
        """
        触发指定动作

        TODO(Phase-0): 根据探测结果替换为真实接口调用
        当前使用 subprocess 方式调用 rostopic pub，避免 ROS 线程问题。
        """
        # 检查ROS master是否在线
        if not self._is_ros_master_available():
            logger.warning("ROS master not available")
            return False

        try:
            cmd = [
                "rostopic", "pub", "-1",
                "/emotion_bridge/action",
                "std_msgs/String",
                f"data: '{action_name}'"
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                logger.info(f"Published action '{action_name}' to /emotion_bridge/action")
                return True
            else:
                logger.error(f"Failed to publish: {result.stderr.strip()}")
                return False

        except Exception as e:
            logger.error(f"Failed to trigger action '{action_name}': {e}")
            return False

    def _is_ros_master_available(self) -> bool:
        """检查ROS master是否可用"""
        try:
            import rospy
            return not rospy.is_shutdown()
        except ImportError:
            return False


class JoyEmulatorClient:
    """
    实现B：软件模拟手柄按键（发布 sim2real_msg/Joy 到 /joy_msg）

    以下映射已通过反汇编 sim2real_master_node（aarch64，未strip）中的
    MasterNode::joyMsgCallback 完整确认：

    按键 -> FSM 事件（joyMsgCallback 内，字段与 sim2real_msg/Joy.msg 一致）：
      center == 1.0            -> DefaultModeEvt        （任何状态 -> ExecDefault 行走）
      dpad_horizontal == +1.0  -> LastOptionEvt          （菜单上一项）
      dpad_horizontal == -1.0  -> NextOptionEvt          （菜单下一项）
      a == 1.0（扳机松开时）    -> ConfirmEvt             （确认进入）
      b == 1.0                 -> ProtectionShutdownEvt  （保护关机）
      菜单导航要求 lt 与 rt 都 < -0.1（左右扳机完全松开）

    FSM 菜单结构（fsm.h joy_table1）：
      Init -Next-> CandidateDefault -Next-> CandidateCustom -Confirm-> ExecCustom

    从 ExecDefault（行走，启动默认状态）切到 ExecCustom 的按键序列：
      b -> ProtectionShutdown -> b -> Init
        -> dpad(-1) -> CandidateDefault
        -> dpad(-1) -> CandidateCustom
        -> a -> ExecCustom

    动作按键（custom_action.yaml，仅在 ExecCustom 执行）：
      cheer = rt + a
      hello = rt + x

    安全提示：切换过程会经过 Init 状态（电机置零、失力），
    切换前必须让机器人处于稳定姿态（坐姿/跪姿/由人扶住），
    切勿在行走或站立不稳时切换。
    """

    # FSM 状态枚举（fsm.h FsmNodeType）
    FSM_EXEC_DEFAULT = 5
    FSM_EXEC_CUSTOM = 6

    # sim2real_msg/Joy.msg 全部字段（顺序一致）
    JOY_FIELDS = [
        "l_horizontal", "l_vertical", "lt",
        "r_horizontal", "r_vertical", "rt",
        "dpad_horizontal", "dpad_vertical",
        "a", "b", "x", "y", "lb", "rb",
        "back", "start", "center", "L", "R",
    ]

    # 摇杆/按键的中立值。
    # 关键（2026-08-19 由 default_controller.cpp 源码确认）：
    # 扳机 lt/rt 的「按下」= -1.0，「松开」= +1.0（F710 扳机轴反相，rest=+1.0）。
    # - master_node 菜单导航门控：bothPressed = (lt < -0.1 && rt < -0.1)，
    #   即「双扳机按下」时才处理 dpad/a/b —— 所以 NEUTRAL 里 lt/rt 取 -1.0（按下）。
    # - default_controller 动作键匹配：rt < -0.5 才把 "rt" 加入 keySet，
    #   因此 cheer/hello（key "rt+a"/"rt+x"）需要 rt=-1.0（按下）。
    NEUTRAL = {
        "l_horizontal": 0.0, "l_vertical": 0.0,
        "lt": -1.0,  # 左扳机按下（-1.0）
        "r_horizontal": 0.0, "r_vertical": 0.0,
        "rt": -1.0,  # 右扳机按下（-1.0）
        "dpad_horizontal": 0.0, "dpad_vertical": 0.0,
        "a": 0.0, "b": 0.0, "x": 0.0, "y": 0.0,
        "lb": 0.0, "rb": 0.0, "back": 0.0, "start": 0.0,
        "center": 0.0, "L": 0.0, "R": 0.0,
    }

    # 动作 -> 按键组合（custom_action.yaml）
    # 注意：动作键要求 lt 松开（+1.0）以免 "lt" 混入 keySet 导致失配；
    #       rt 必须按下（-1.0）才能把 "rt" 加入 keySet。
    ACTION_BUTTONS = {
        "hello": {"lt": 1.0, "rt": -1.0, "x": 1.0},   # rt(按下)+x
        "cheer": {"lt": 1.0, "rt": -1.0, "a": 1.0},   # rt(按下)+a
    }

    # 站起（LT+RT+start）：把控制器从 INIT 拉到 STANDING→STANDBY。
    # 仅当控制器仍处于 INIT（电机置零失力）时才需要。
    STAND_UP_BUTTONS = {"lt": -1.0, "rt": -1.0, "start": 1.0}

    # ExecDefault -> ExecCustom 模式切换按键序列（顺序按下）
    MODE_SWITCH_SEQUENCE = [
        {"b": 1.0},                 # ExecDefault -> ProtectionShutdown
        {"b": 1.0},                 # ProtectionShutdown -> Init
        {"dpad_horizontal": -1.0},  # Init -> CandidateDefault
        {"dpad_horizontal": -1.0},  # CandidateDefault -> CandidateCustom
        {"a": 1.0},                 # CandidateCustom -> ExecCustom
    ]

    def __init__(self, config: RobotConfig):
        self.config = config
        self._last_online_check = 0
        self._last_online_result = False
        self.ros_setup = "/home/nvidia/sim2real/install/setup.bash"

        # 惰性 rospy 快速发布路径（避免每个按键都起 subprocess + 3s latch）
        self._rospy_ready = False
        self._rospy_failed = False
        self._joy_pub = None
        self._Joy = None    # sim2real_msg.msg.Joy
        self._Int32 = None  # std_msgs.msg.Int32

    # ------------------------------------------------------------------
    # 在线检测
    # ------------------------------------------------------------------

    def is_robot_online(self) -> bool:
        """检测机器人是否在线"""
        now = time.time()
        if now - self._last_online_check < 5:
            return self._last_online_result

        self._last_online_check = now
        self._last_online_result = self._check_robot_online()
        return self._last_online_result

    def _check_robot_online(self) -> bool:
        """执行机器人在线检测"""
        try:
            cmd = f"source {self.ros_setup} && {self.config.robot_check_cmd}"
            result = subprocess.run(
                cmd,
                shell=True,
                executable="/bin/bash",
                capture_output=True,
                text=True,
                timeout=3
            )

            if self.config.robot_node_keyword:
                return self.config.robot_node_keyword in result.stdout

            return result.returncode == 0
        except (subprocess.TimeoutExpired, Exception):
            return False

    # ------------------------------------------------------------------
    # Joy 消息发布
    # ------------------------------------------------------------------

    def _build_yaml(self, overrides: Dict[str, float]) -> str:
        """构造 sim2real_msg/Joy 的 YAML 参数字符串，基于 NEUTRAL 中立值"""
        fields = dict(self.NEUTRAL)
        fields.update(overrides)
        return "{" + ", ".join(f"{k}: {v}" for k, v in fields.items()) + "}"

    def _run_ros_cmd(self, cmd: str, timeout: int = 6) -> Optional[subprocess.CompletedProcess]:
        """在 ROS 环境中执行一条命令，返回 CompletedProcess 或 None"""
        full = f"source {self.ros_setup} && {cmd}"
        try:
            return subprocess.run(
                full,
                shell=True,
                executable="/bin/bash",
                capture_output=True,
                text=True,
                timeout=timeout
            )
        except (subprocess.TimeoutExpired, Exception) as e:
            logger.debug(f"ROS command failed: {cmd!r}: {e}")
            return None

    def _publish_joy(self, overrides: Dict[str, float], hold: float = 0.0) -> bool:
        """
        发布一次 Joy 按键（按下 + 保持 hold 秒 + 释放）。

        FSM 事件只在字段值精确等于阈值（1.0 或 -1.0）的那条消息上触发，
        释放（全 0）不会触发 FSM 事件；但保留释放是为了让 Sim2Real 控制器
        也能正确识别按键组合的边沿。
        """
        if self._ensure_rospy():
            return self._publish_joy_rospy(overrides, hold)
        return self._publish_joy_subprocess(overrides, hold)

    def _publish_joy_rospy(self, overrides: Dict[str, float], hold: float = 0.0) -> bool:
        """快速路径：常驻 rospy Publisher（无 subprocess、无 3s latch）"""
        try:
            fields = dict(self.NEUTRAL)
            fields.update(overrides)

            press = self._Joy()
            for k, v in fields.items():
                setattr(press, k, float(v))
            self._joy_pub.publish(press)

            if hold > 0:
                time.sleep(hold)
                release = self._Joy()
                for k, v in self.NEUTRAL.items():
                    setattr(release, k, float(v))
                self._joy_pub.publish(release)
            return True
        except Exception as e:
            logger.error(f"rospy joy publish failed: {e}; falling back")
            self._rospy_ready = False
            self._rospy_failed = True
            return self._publish_joy_subprocess(overrides, hold)

    def _publish_joy_subprocess(self, overrides: Dict[str, float], hold: float = 0.0) -> bool:
        """慢速兜底：subprocess rostopic pub -1（每个约 3s latch）"""
        press = self._build_yaml(overrides)
        release = self._build_yaml({})

        result = self._run_ros_cmd(
            f"rostopic pub -1 {self.config.joy_topic} sim2real_msg/Joy '{press}'"
        )
        if result is None or result.returncode != 0:
            logger.error(f"Failed to publish joy press: {overrides}")
            return False

        if hold > 0:
            time.sleep(hold)
            self._run_ros_cmd(
                f"rostopic pub -1 {self.config.joy_topic} sim2real_msg/Joy '{release}'"
            )

        return True

    def _ensure_rospy(self) -> bool:
        """惰性初始化 rospy 发布器（ROS 环境可用时才生效）。"""
        if self._rospy_ready:
            return True
        if self._rospy_failed:
            return False
        try:
            import rospy
            from sim2real_msg.msg import Joy
            from std_msgs.msg import Int32

            if not rospy.core.is_initialized():
                rospy.init_node("emotion_bridge_joy", anonymous=True, disable_signals=True)

            self._joy_pub = rospy.Publisher(self.config.joy_topic, Joy, queue_size=10)
            self._Joy = Joy
            self._Int32 = Int32

            # 等待订阅者连接（否则刚创建发布器就发消息，前几条会被丢弃）
            for _ in range(30):
                if self._joy_pub.get_num_connections() > 0:
                    break
                time.sleep(0.1)

            self._rospy_ready = True
            logger.info(
                f"rospy fast-publish path initialized "
                f"(connections={self._joy_pub.get_num_connections()})"
            )
            return True
        except Exception as e:
            logger.debug(f"rospy unavailable, using subprocess fallback: {e}")
            self._rospy_failed = True
            return False

    # ------------------------------------------------------------------
    # FSM 状态读取与模式切换
    # ------------------------------------------------------------------

    def _read_fsm_state(self) -> Optional[int]:
        """读取 /fsm_state 当前值（std_msgs/Int32），失败返回 None"""
        if self._ensure_rospy():
            try:
                import rospy
                msg = rospy.wait_for_message(
                    self.config.fsm_state_topic, self._Int32, timeout=2.0
                )
                if msg is not None:
                    return int(msg.data)
            except Exception as e:
                logger.debug(f"rospy fsm read failed, falling back: {e}")
                self._rospy_ready = False
                self._rospy_failed = True

        result = self._run_ros_cmd(
            f"rostopic echo -n 1 {self.config.fsm_state_topic}",
            timeout=5
        )
        if result is None or result.returncode != 0:
            return None

        # 匹配 "data: N"
        m = re.search(r"data:\s*(-?\d+)", result.stdout)
        if m:
            return int(m.group(1))
        return None

    def switch_to_custom_mode(self) -> bool:
        """
        把机器人从 ExecDefault 切换到 ExecCustom（cheer/hello 所在模式）。

        按键序列：b -> b -> dpad(-1) -> dpad(-1) -> a
        返回：最终 /fsm_state 是否为 ExecCustom(6)。
        """
        # 已在 ExecCustom，直接返回
        current = self._read_fsm_state()
        if current == self.FSM_EXEC_CUSTOM:
            logger.info("Robot already in ExecCustom mode")
            return True

        logger.warning(
            "Switching robot to ExecCustom mode "
            "(机器人将经过 ProtectionShutdown/Init，请确认处于稳定姿态)"
        )

        for i, btn in enumerate(self.MODE_SWITCH_SEQUENCE):
            if not self._publish_joy(btn, hold=0.05):
                logger.error(f"Mode switch step {i + 1}/{len(self.MODE_SWITCH_SEQUENCE)} failed: {btn}")
                return False
            time.sleep(self.config.mode_switch_interval)

        # 验证最终状态
        final = self._read_fsm_state()
        if final == self.FSM_EXEC_CUSTOM:
            logger.info("Mode switch to ExecCustom succeeded (fsm_state=6)")
            return True

        logger.warning(f"Mode switch may have failed, fsm_state={final} (expected {self.FSM_EXEC_CUSTOM})")
        return final == self.FSM_EXEC_CUSTOM

    def switch_to_default_mode(self) -> bool:
        """
        切回 ExecDefault（行走模式）。

        任何状态下按下 center 都会回到 ExecDefault（DefaultModeEvt）。
        """
        if not self._publish_joy({"center": 1.0}, hold=0.1):
            return False
        time.sleep(self.config.mode_switch_interval)
        final = self._read_fsm_state()
        return final == self.FSM_EXEC_DEFAULT

    # ------------------------------------------------------------------
    # 动作触发
    # ------------------------------------------------------------------

    def stand_up(self) -> bool:
        """
        让机器人站起（LT+RT+start），把控制器从 INIT 拉到 STANDING→STANDBY。

        背景：DefaultControllerNode 启动后 state_=INIT（execPdLoop 会持续给所有电机
        发零输出，机器人失力）。只有进入 STANDING/STANDBY/RUNNING 后，multi_waypoint
        动作（cheer/hello）的按键匹配才会生效。站起用 "zero" 单轨迹，耗时约 3s。

        安全：会让机器人主动站立，务必确保机器人处于可站立姿态（双脚着地）。
        """
        logger.warning(
            "Standing robot up (LT+RT+start). 请确保机器人处于可站立姿态"
        )
        if not self._publish_joy(self.STAND_UP_BUTTONS, hold=0.1):
            logger.error("Failed to publish stand-up command")
            return False
        # 等待 "zero" 单轨迹完成（STANDING -> STANDBY），默认 4s
        time.sleep(getattr(self.config, "stand_up_duration", 4.0))
        return True

    def recover_to_stand(self) -> bool:
        """
        让机器人回到中立站立姿态（LT+RT+start，"zero" 轨迹）。

        用于动作执行结束后主动"归位"，替代仅靠等待。与 stand_up() 同套按键，
        但这里不长睡——zero 轨迹的等待由网关负责（recover_duration）。
        """
        logger.info("Recovering robot to stand status (LT+RT+start)")
        if not self._publish_joy(self.STAND_UP_BUTTONS, hold=0.1):
            logger.error("Failed to publish recover-to-stand command")
            return False
        return True

    def trigger_action(self, action_name: str) -> bool:
        """
        触发指定动作（cheer / hello）。

        流程：
        1. 若配置 ensure_custom_mode，先切换到 ExecCustom（若尚未进入）
        2. 若配置 ensure_standing，先站起（INIT -> STANDBY）
        3. 发布动作按键组合（rt+a 或 rt+x，rt 需按下=-1.0）
        """
        if action_name not in self.ACTION_BUTTONS:
            logger.error(f"Unknown action for joy emulation: {action_name}")
            return False

        if not self._check_robot_online():
            logger.warning("ROS master not available")
            return False

        # 确保处于 ExecCustom 模式（cheer/hello 仅在此模式执行）
        if self.config.ensure_custom_mode:
            if not self.switch_to_custom_mode():
                logger.error(
                    f"Failed to switch to ExecCustom, aborting action '{action_name}'"
                )
                return False

        # 站起（控制器处于 INIT 时动作按键不会被识别）
        if getattr(self.config, "ensure_standing", True):
            if not self.stand_up():
                logger.error("Failed to stand up, aborting action")
                return False

        button = self.ACTION_BUTTONS[action_name]
        if not self._publish_joy(button, hold=self.config.action_hold):
            logger.error(f"Failed to trigger action '{action_name}'")
            return False

        logger.info(
            f"Action triggered: {action_name} "
            f"(lt={button.get('lt', 0)}, rt={button.get('rt', 0)}, "
            f"a={button.get('a', 0)}, x={button.get('x', 0)})"
        )
        return True


def create_robot_client(config: Dict[str, Any]) -> RobotActionClient:
    """
    根据配置创建机器人客户端

    Args:
        config: 从bridge_config.json读取的robot配置段

    Returns:
        RobotActionClient实例
    """
    robot_config = RobotConfig(
        trigger_impl=config.get("trigger_impl", "A"),
        action_duration=config.get("action_duration", 5.44),
        robot_check_cmd=config.get("robot_check_cmd", "rosnode list"),
        robot_node_keyword=config.get("robot_node_keyword", ""),
        joy_topic=config.get("joy_topic", "/joy_msg"),
        fsm_state_topic=config.get("fsm_state_topic", "/fsm_state"),
        joy_button_sequence=config.get("joy_button_sequence", []),
        ensure_custom_mode=config.get("ensure_custom_mode", True),
        ensure_standing=config.get("ensure_standing", True),
        stand_up_duration=config.get("stand_up_duration", 4.0),
        mode_switch_interval=config.get("mode_switch_interval", 0.5),
        action_hold=config.get("action_hold", 0.3),
    )

    if robot_config.trigger_impl == "A":
        logger.info("Using DirectSwitchClient (implementation A)")
        return DirectSwitchClient(robot_config)
    elif robot_config.trigger_impl == "B":
        logger.info("Using JoyEmulatorClient (implementation B)")
        return JoyEmulatorClient(robot_config)
    else:
        raise ValueError(f"Invalid trigger_impl: {robot_config.trigger_impl}. Must be 'A' or 'B'")
