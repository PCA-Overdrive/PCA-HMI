"""
CAN, joystick, and buzzer integration for the vehicle display server.

The module is intentionally hardware-optional: imports for python-can, pygame,
and RPi.GPIO happen at runtime so the Flask app can still run in development.
"""

import os
import glob
import shutil
import struct
import subprocess
import sys
import threading
import time


GEAR_P = 0
GEAR_D = 1
GEAR_R = 2
GEAR_N = 3

CAN_GEAR_LABELS = {
    GEAR_P: "P",
    GEAR_D: "D",
    GEAR_R: "R",
    GEAR_N: "N",
}

BUTTON_P = 0
BUTTON_D = 1
BUTTON_R = 3
BUTTON_PCA = 4

LEVEL_NO_OBSTACLE = 0
LEVEL_SAFE = 1
LEVEL_CAUTION = 2
LEVEL_CLOSE = 3
LEVEL_DANGER = 4

PDW_DIRECTIONS = (
    "F",
    "FR",
    "RF",
    "RB",
    "BR",
    "B",
    "BL",
    "LB",
    "LF",
    "FL",
)
DISPLAY_DISTANCE_BY_RAW_LEVEL = {
    LEVEL_NO_OBSTACLE: 0,
    LEVEL_SAFE: 150,
    LEVEL_CAUTION: 90,
    LEVEL_CLOSE: 45,
    LEVEL_DANGER: 20,
}


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def axis_to_byte(axis_value):
    value = int((axis_value + 1.0) * 127.5)
    return clamp(value, 0, 255)


def steer_byte_to_angle(steer_byte):
    return int(round(((int(steer_byte) - 127) / 128.0) * 20))


def raw_level_to_display_level(raw_level):
    raw_level = int(raw_level)
    if raw_level <= LEVEL_NO_OBSTACLE:
        return 0
    if raw_level == LEVEL_SAFE:
        return 1
    if raw_level == LEVEL_CAUTION:
        return 2
    return 3


class VehicleCanController:
    """Bridge joystick input, CAN RX/TX, and buzzer alerts."""

    def __init__(self, on_state_update=None, on_controller_update=None):
        self.on_state_update = on_state_update
        self.on_controller_update = on_controller_update
        self.channel = os.getenv("CAN_CHANNEL", "can0")
        self.interface = os.getenv("CAN_INTERFACE", "socketcan")
        self.use_can_fd = env_bool("CAN_FD", True)
        self.tx_201_interval = float(os.getenv("CAN_TX_201_INTERVAL", "0.012"))
        self.tx_300_interval = float(os.getenv("CAN_TX_300_INTERVAL", "0.1"))
        self.log_can_tx = env_bool("CAN_LOG_ENABLED", False)
        self.log_can_rx = env_bool("CAN_RX_LOG_ENABLED", env_bool("CAN_LOG_ENABLED", False))
        self.log_interval = float(os.getenv("CAN_LOG_INTERVAL", "0.2"))
        self.joystick_enabled = env_bool("CONTROLLER_ENABLED", True)
        self.buzzer_enabled = env_bool("BUZZER_ENABLED", False)
        self.buzzer_pin = self._read_optional_int("BUZZER_GPIO_PIN")

        self.lock = threading.Lock()
        self.running = False
        self.bus = None
        self.can = None
        self.can_available = False
        self.pygame = None
        self.joystick = None
        self.gpio = None
        self.buzzer = None

        self.obstacle_levels = [0] * 10
        self.pca_state = 0
        self.vehicle_speed = 0
        self.gear_status_from_ecu = GEAR_P
        self.emergency_stop = 0
        self.exit_status = 0

        self.gear_state = GEAR_P
        self.prev_pca_button = 0
        self.pca_enabled = 0
        self.auto_parking_cmd = 0
        self.line_angle_cmd = 0
        self.speed_cmd = 127
        self.steer_cmd = 127
        self.last_201_log = 0
        self.last_300_log = 0
        self.last_rx_log = 0
        self.last_rx_id = None
        self.last_rx_at = None

    @staticmethod
    def _read_optional_int(name):
        value = os.getenv(name)
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def start(self):
        if self.running:
            return True

        self.can_available = self._init_can_bus()

        self.running = True
        if self.can_available:
            threading.Thread(target=self._can_rx_loop, daemon=True).start()
        else:
            print("CAN unavailable. Controller detection will run without CAN TX.", flush=True)

        threading.Thread(target=self._controller_tx_loop, daemon=True).start()

        if not self.buzzer_enabled:
            print("Buzzer disabled: BUZZER_ENABLED is false.", flush=True)
        elif self.buzzer_pin is None:
            print("Buzzer disabled: BUZZER_GPIO_PIN is empty or invalid.", flush=True)
        else:
            self._start_buzzer()

        return True

    def stop(self):
        self.running = False
        if self.buzzer:
            self._close_buzzer()
        if self.gpio:
            self.gpio.cleanup()
        if self.pygame:
            self.pygame.quit()
        if self.bus and hasattr(self.bus, "shutdown"):
            self.bus.shutdown()

    def set_pca_enabled(self, enabled):
        with self.lock:
            self.pca_enabled = 1 if enabled else 0

    def set_auto_parking_cmd(self, command):
        with self.lock:
            self.auto_parking_cmd = clamp(int(command), 0, 255)

    def set_line_angle_cmd(self, angle):
        with self.lock:
            self.line_angle_cmd = clamp(int(angle), -180, 180)

    def snapshot(self):
        with self.lock:
            return {
                "obstacle_levels": list(self.obstacle_levels),
                "pca_state": self.pca_state,
                "vehicle_speed": self.vehicle_speed,
                "gear_status_from_ecu": self.gear_status_from_ecu,
                "emergency_stop": self.emergency_stop,
                "exit_status": self.exit_status,
                "gear_cmd": self.gear_state,
                "pca_enabled": self.pca_enabled,
                "auto_parking_cmd": self.auto_parking_cmd,
                "line_angle_cmd": self.line_angle_cmd,
                "speed_cmd": self.speed_cmd,
                "steer_cmd": self.steer_cmd,
                "joystick_connected": self.joystick is not None,
                "can_available": self.can_available,
                "last_rx_id": self.last_rx_id,
                "last_rx_at": self.last_rx_at,
            }

    def _init_can_bus(self):
        try:
            import can
        except ImportError:
            print("python-can is not installed. CAN integration is disabled.")
            return False

        self.can = can
        kwargs = {
            "channel": self.channel,
            "interface": self.interface,
        }
        if self.use_can_fd:
            kwargs["fd"] = True

        try:
            self.bus = can.interface.Bus(**kwargs)
        except TypeError:
            kwargs["bustype"] = kwargs.pop("interface")
            self.bus = can.interface.Bus(**kwargs)
        except Exception as exc:
            print(f"CAN init failed: {exc}")
            return False

        print(f"CAN connected: {self.interface}/{self.channel}, fd={self.use_can_fd}")
        return True

    def _can_rx_loop(self):
        while self.running:
            try:
                msg = self.bus.recv(timeout=1.0)
            except Exception as exc:
                print(f"CAN RX failed: {exc}")
                time.sleep(0.2)
                continue

            if msg is None:
                continue

            data = bytes(msg.data)
            changed = False
            self._log_can_rx(msg, data)

            if msg.arbitration_id == 0x400 and len(data) >= 14:
                with self.lock:
                    self.obstacle_levels[:] = list(data[0:10])
                    self.pca_state = data[10]
                    self.vehicle_speed = data[11]
                    self.gear_status_from_ecu = data[12]
                    self.emergency_stop = data[13]
                    self.last_rx_id = msg.arbitration_id
                    self.last_rx_at = time.time()
                changed = True
            elif msg.arbitration_id == 0x401 and len(data) > 0:
                with self.lock:
                    self.exit_status = data[0]
                    self.last_rx_id = msg.arbitration_id
                    self.last_rx_at = time.time()
                changed = True
            elif msg.arbitration_id == 0x400:
                print(f"CAN RX 0x400 ignored: expected >=14 bytes, got {len(data)}", flush=True)

            if changed and self.on_state_update:
                self.on_state_update(self.snapshot())

    def _controller_tx_loop(self):
        last_201 = 0
        last_300 = 0

        while self.running:
            if not self.joystick_enabled:
                time.sleep(0.5)
                continue

            joystick = self._get_joystick()
            if joystick is None:
                time.sleep(1.0)
                continue

            try:
                if self.pygame is not None:
                    self.pygame.event.pump()
                speed = axis_to_byte(joystick.get_axis(1))
                steer = axis_to_byte(joystick.get_axis(2))
                self._read_gear_buttons(joystick)
                self._read_pca_button(joystick)
            except Exception as exc:
                print(f"Joystick read failed: {exc}")
                self.joystick = None
                time.sleep(0.5)
                continue

            with self.lock:
                gear_state = self.gear_state
                emergency_stop = self.emergency_stop
                pca_enabled = self.pca_enabled
                line_angle_cmd = self.line_angle_cmd
                auto_parking_cmd = self.auto_parking_cmd

            speed, steer = self._apply_drive_limits(speed, steer, gear_state, emergency_stop)

            with self.lock:
                self.speed_cmd = speed
                self.steer_cmd = steer

            if self.on_controller_update:
                self.on_controller_update(self.snapshot())

            now = time.time()
            if now - last_201 >= self.tx_201_interval:
                if self.can_available:
                    self._send_vehicle_status(speed, steer, gear_state, pca_enabled, line_angle_cmd)
                else:
                    self._log_controller_state(speed, steer, gear_state, pca_enabled, line_angle_cmd)
                last_201 = now

            if now - last_300 >= self.tx_300_interval:
                if self.can_available:
                    self._send_auto_parking(auto_parking_cmd)
                last_300 = now

            time.sleep(0.005)

    def _get_joystick(self):
        if self.joystick is not None:
            return self.joystick

        try:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            import pygame
        except ImportError:
            print("pygame is not installed. Trying Linux joystick devices...", flush=True)
            return self._get_linux_joystick()

        self.pygame = pygame
        pygame.init()
        pygame.joystick.init()

        joystick_count = pygame.joystick.get_count()
        if joystick_count == 0:
            print("Joystick not found. Waiting for controller...", flush=True)
            return self._get_linux_joystick()

        print(f"Joystick count: {joystick_count}", flush=True)
        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()
        print(f"Joystick connected: {self.joystick.get_name()}")
        return self.joystick

    def _get_linux_joystick(self):
        for path in sorted(glob.glob("/dev/input/js*")):
            try:
                joystick = LinuxJoystick(path)
            except PermissionError:
                print(f"Joystick permission denied: {path}", flush=True)
                continue
            except OSError as exc:
                print(f"Joystick open failed: {path}: {exc}", flush=True)
                continue

            print(f"Linux joystick connected: {joystick.get_name()}", flush=True)
            return joystick

        print("No /dev/input/js* joystick device found.", flush=True)
        return None

    def _read_gear_buttons(self, joystick):
        with self.lock:
            if joystick.get_button(BUTTON_P):
                self.gear_state = GEAR_P
            if joystick.get_button(BUTTON_D):
                self.gear_state = GEAR_D
            if joystick.get_button(BUTTON_R):
                self.gear_state = GEAR_R

    def _read_pca_button(self, joystick):
        current = joystick.get_button(BUTTON_PCA)
        with self.lock:
            if current == 1 and self.prev_pca_button == 0:
                self.pca_enabled = 1 - self.pca_enabled
            self.prev_pca_button = current

    def _apply_drive_limits(self, speed, steer, gear_state, emergency_stop):
        if gear_state == GEAR_P:
            return 127, 127
        if gear_state == GEAR_D and speed > 127:
            speed = 127
        elif gear_state == GEAR_R and speed < 127:
            speed = 127

        if emergency_stop == 1:
            return 127, 127

        return speed, steer

    def _send_vehicle_status(self, speed, steer, gear, pca_enabled, line_angle):
        line_bytes = struct.pack("<h", int(line_angle))
        msg = self.can.Message(
            arbitration_id=0x201,
            data=bytes([speed, steer, gear, pca_enabled, line_bytes[0], line_bytes[1]]),
            is_extended_id=False
        )
        if not self._safe_can_send(msg, "0x201"):
            return
        self._log_can_201(speed, steer, gear, pca_enabled, line_angle, msg.data)

    def _send_auto_parking(self, command):
        msg = self.can.Message(
            arbitration_id=0x300,
            data=bytes([command]),
            is_extended_id=False,
        )
        if not self._safe_can_send(msg, "0x300"):
            return
        self._log_can_300(command, msg.data)

    def _safe_can_send(self, msg, label):
        try:
            self.bus.send(msg)
            return True
        except Exception as exc:
            print(f"CAN TX {label} failed: {exc}. Disabling CAN TX.", flush=True)
            self.can_available = False
            return False

    def _log_can_201(self, speed, steer, gear, pca_enabled, line_angle, data):
        if not self.log_can_tx:
            return

        now = time.time()
        if now - self.last_201_log < self.log_interval:
            return

        self.last_201_log = now
        gear_label = CAN_GEAR_LABELS.get(gear, str(gear))
        data_hex = " ".join(f"{byte:02X}" for byte in data)
        print(
            "[CAN TX 0x201] "
            f"speed={speed} steer={steer} gear={gear_label}({gear}) "
            f"pca={pca_enabled} line_angle={line_angle} data=[{data_hex}]",
            flush=True,
        )

    def _log_can_rx(self, msg, data):
        if not self.log_can_rx:
            return

        now = time.time()
        if now - self.last_rx_log < self.log_interval:
            return

        self.last_rx_log = now
        data_hex = " ".join(f"{byte:02X}" for byte in data)
        frame_type = "FD" if getattr(msg, "is_fd", False) else "CAN"
        print(
            f"[CAN RX 0x{msg.arbitration_id:X}] type={frame_type} "
            f"len={len(data)} data=[{data_hex}]",
            flush=True,
        )

    def _log_can_300(self, command, data):
        if not self.log_can_tx:
            return

        now = time.time()
        if now - self.last_300_log < self.log_interval:
            return

        self.last_300_log = now
        data_hex = " ".join(f"{byte:02X}" for byte in data)
        print(
            f"[CAN TX 0x300] auto_parking_cmd={command} data=[{data_hex}]",
            flush=True,
        )

    def _log_controller_state(self, speed, steer, gear, pca_enabled, line_angle):
        if not self.log_can_tx:
            return

        now = time.time()
        if now - self.last_201_log < self.log_interval:
            return

        self.last_201_log = now
        gear_label = CAN_GEAR_LABELS.get(gear, str(gear))
        print(
            "[CONTROLLER] "
            f"speed={speed} steer={steer} gear={gear_label}({gear}) "
            f"pca={pca_enabled} line_angle={line_angle} can=unavailable "
            f"{self._describe_joystick_inputs()}",
            flush=True,
        )

    def _describe_joystick_inputs(self):
        joystick = self.joystick
        if joystick is None:
            return ""

        axes = []
        buttons = []

        try:
            axis_count = joystick.get_numaxes()
        except AttributeError:
            axis_count = 8

        try:
            button_count = joystick.get_numbuttons()
        except AttributeError:
            button_count = 16

        for index in range(axis_count):
            try:
                value = joystick.get_axis(index)
            except Exception:
                continue
            if abs(value) > 0.08:
                axes.append(f"{index}:{value:.2f}")

        for index in range(button_count):
            try:
                pressed = joystick.get_button(index)
            except Exception:
                continue
            if pressed:
                buttons.append(str(index))

        return f"axes=[{', '.join(axes)}] buttons=[{', '.join(buttons)}]"

    def _start_buzzer(self):
        self._add_system_gpio_paths()
        try:
            import RPi.GPIO as GPIO
        except ImportError:
            GPIO = None

        if GPIO is not None:
            self.gpio = GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.buzzer_pin, GPIO.OUT)
            self.buzzer = GPIO.PWM(self.buzzer_pin, 2000)
            self.buzzer.start(0)
            threading.Thread(target=self._buzzer_loop, daemon=True).start()
            print(f"Buzzer started with RPi.GPIO on BCM GPIO {self.buzzer_pin}", flush=True)
            return

        try:
            from gpiozero import PWMOutputDevice
            self.buzzer = PWMOutputDevice(self.buzzer_pin, initial_value=0, frequency=2000)
        except Exception as exc:
            print(f"gpiozero buzzer init failed: {exc}", flush=True)
            if self._start_command_gpio_buzzer():
                return
            print(
                "GPIO library is not available. Buzzer is disabled. "
                "Install on Raspberry Pi: sudo apt install python3-rpi.gpio python3-gpiozero python3-lgpio",
                flush=True,
            )
            return

        threading.Thread(target=self._buzzer_loop, daemon=True).start()
        print(f"Buzzer started with gpiozero on BCM GPIO {self.buzzer_pin}", flush=True)

    def _add_system_gpio_paths(self):
        for path in (
            "/usr/lib/python3/dist-packages",
            f"/usr/local/lib/python{sys.version_info.major}.{sys.version_info.minor}/dist-packages",
        ):
            if os.path.isdir(path) and path not in sys.path:
                sys.path.append(path)

    def _start_command_gpio_buzzer(self):
        if shutil.which("pinctrl") is None:
            return False

        try:
            buzzer = CommandGpioBuzzer(self.buzzer_pin)
            buzzer.start(0)
        except Exception as exc:
            print(f"pinctrl buzzer init failed: {exc}", flush=True)
            return False

        self.buzzer = buzzer
        threading.Thread(target=self._buzzer_loop, daemon=True).start()
        print(f"Buzzer started with pinctrl on BCM GPIO {self.buzzer_pin}", flush=True)
        return True

    def _buzzer_loop(self):
        while self.running:
            with self.lock:
                level = max(self.obstacle_levels)

            if level in (LEVEL_NO_OBSTACLE, LEVEL_SAFE):
                self._set_buzzer_duty(0)
                time.sleep(0.05)
            elif level == LEVEL_CAUTION:
                self._beep(0.08, 0.8)
            elif level == LEVEL_CLOSE:
                self._beep(0.08, 0.25)
            elif level >= LEVEL_DANGER:
                self._set_buzzer_duty(50)
                time.sleep(0.05)
            else:
                self._set_buzzer_duty(0)
                time.sleep(0.05)

    def _beep(self, on_seconds, off_seconds):
        self._set_buzzer_duty(50)
        time.sleep(on_seconds)
        self._set_buzzer_duty(0)
        time.sleep(off_seconds)

    def _set_buzzer_duty(self, duty):
        if self.buzzer is None:
            return
        if hasattr(self.buzzer, "ChangeDutyCycle"):
            self.buzzer.ChangeDutyCycle(duty)
        elif hasattr(self.buzzer, "value"):
            self.buzzer.value = clamp(float(duty) / 100.0, 0.0, 1.0)

    def _close_buzzer(self):
        try:
            self._set_buzzer_duty(0)
            if hasattr(self.buzzer, "stop"):
                self.buzzer.stop()
            if hasattr(self.buzzer, "close"):
                self.buzzer.close()
        except Exception:
            pass


class LinuxJoystick:
    """Minimal reader for Linux /dev/input/js* devices."""

    JS_EVENT_BUTTON = 0x01
    JS_EVENT_AXIS = 0x02
    JS_EVENT_INIT = 0x80
    EVENT_SIZE = struct.calcsize("IhBB")

    def __init__(self, path):
        self.path = path
        self.axes = {}
        self.buttons = {}
        self.file = open(path, "rb", buffering=0)
        os.set_blocking(self.file.fileno(), False)

    def get_name(self):
        return self.path

    def get_axis(self, index):
        self._poll()
        return self.axes.get(index, 0.0)

    def get_button(self, index):
        self._poll()
        return self.buttons.get(index, 0)

    def get_numaxes(self):
        self._poll()
        return max(self.axes.keys(), default=7) + 1

    def get_numbuttons(self):
        self._poll()
        return max(self.buttons.keys(), default=15) + 1

    def _poll(self):
        while True:
            try:
                data = self.file.read(self.EVENT_SIZE)
            except BlockingIOError:
                return

            if not data or len(data) < self.EVENT_SIZE:
                return

            _, value, event_type, number = struct.unpack("IhBB", data)
            event_type = event_type & ~self.JS_EVENT_INIT

            if event_type == self.JS_EVENT_AXIS:
                self.axes[number] = max(-1.0, min(1.0, value / 32767.0))
            elif event_type == self.JS_EVENT_BUTTON:
                self.buttons[number] = 1 if value else 0


class CommandGpioBuzzer:
    """Fallback GPIO output using Raspberry Pi OS pinctrl."""

    def __init__(self, bcm_pin):
        self.bcm_pin = int(bcm_pin)
        self.value = 0.0
        self._run("op", "dl")

    def start(self, duty):
        self.ChangeDutyCycle(duty)

    def stop(self):
        self.ChangeDutyCycle(0)

    def close(self):
        self.ChangeDutyCycle(0)

    def ChangeDutyCycle(self, duty):
        self.value = clamp(float(duty) / 100.0, 0.0, 1.0)
        self._run("dh" if self.value > 0 else "dl")

    def _run(self, *args):
        subprocess.run(
            ["pinctrl", "set", str(self.bcm_pin), *args],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
