"""Camera stream and lane-angle detection."""

import math
import os
import threading
import time
from glob import glob
from io import BytesIO

try:
    import cv2
    import numpy as np
except Exception as exc:
    cv2 = None
    np = None
    print(f"OpenCV/Numpy import failed. Camera is disabled: {exc}", flush=True)

try:
    from parking_line_detector import ParkingLineDetector
except ImportError:
    try:
        from .parking_line_detector import ParkingLineDetector
    except ImportError:
        ParkingLineDetector = None


class CameraManager:
    """Manage a Pi/USB camera stream and estimate the current lane angle."""

    def __init__(
        self,
        source=0,
        resolution=(1280, 720),
        fps=30,
        backend=None,
        lane_detection_enabled=None,
        name="Camera",
    ):
        self.source = source
        self.resolution = resolution
        self.fps = fps
        self.backend = backend
        self.name = name
        self.frame = None
        self.is_running = False
        self.lock = threading.Lock()
        self.jpeg_quality = 80

        self.lane_angle = 0
        self.lane_angle_updated_at = None
        self.parking_line_result = None
        if lane_detection_enabled is None:
            lane_detection_enabled = self._env_bool("LANE_DETECTION_ENABLED", True)
        self.lane_detection_enabled = lane_detection_enabled
        self.lane_detection_interval = float(os.getenv("LANE_DETECTION_INTERVAL", "0.1"))
        self.parking_line_log_interval = float(os.getenv("PARKING_LINE_LOG_INTERVAL", "0.5"))
        self.parking_line_log_enabled = self._env_bool("PARKING_LINE_LOG_ENABLED", False)
        self.last_lane_detection = 0
        self.last_parking_line_log_at = 0
        self.parking_line_detector = ParkingLineDetector() if ParkingLineDetector else None

        try:
            if self._source_disabled(source):
                self.camera = None
                print(f"{self.name} disabled by source.", flush=True)
            elif source == "pi":
                self._init_pi_camera()
            else:
                self._init_opencv_camera()
        except Exception as exc:
            print(f"{self.name} init failed: {exc}", flush=True)
            self.camera = None

    @staticmethod
    def _env_bool(name, default=False):
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _source_disabled(source):
        return str(source).strip().lower() in {"-1", "none", "disabled", "off", "false"}

    def _init_pi_camera(self):
        try:
            from picamera import PiCamera
        except ImportError:
            print("picamera is not installed.", flush=True)
            self.camera = None
            return

        self.camera = PiCamera()
        self.camera.resolution = self.resolution
        self.camera.framerate = self.fps
        print(f"{self.name} initialized: Pi {self.resolution} @ {self.fps}fps", flush=True)

    def _init_opencv_camera(self):
        if cv2 is None:
            raise RuntimeError("OpenCV is not available")

        self.opened_source = None
        self.camera = self._open_video_capture()
        if not self.camera.isOpened():
            raise RuntimeError(f"OpenCV could not open source {self.source!r}")
        self._configure_capture(self.camera)

        print(
            f"{self.name} initialized: OpenCV source={self.source!r} "
            f"opened={self.opened_source!r} "
            f"{self.resolution} @ {self.fps}fps",
            flush=True,
        )

    def _open_video_capture(self):
        backend = (self.backend or os.getenv("CAMERA_BACKEND", "")).strip().upper()
        if not backend and self._looks_like_windows_device_name(self.source):
            backend = "DSHOW"
        backend_map = {
            "ANY": cv2.CAP_ANY,
            "MSMF": cv2.CAP_MSMF,
            "DSHOW": cv2.CAP_DSHOW,
        }
        requires_frame_probe = self._is_usb_source_spec(self.source)
        failed_capture = None
        for candidate in self._opencv_source_candidates(self.source, backend):
            if backend in backend_map:
                capture = cv2.VideoCapture(candidate, backend_map[backend])
            else:
                capture = cv2.VideoCapture(candidate)

            if capture.isOpened():
                self._configure_capture(capture)
                if requires_frame_probe and not self._capture_can_grab_frame(capture):
                    if failed_capture is not None:
                        failed_capture.release()
                    failed_capture = capture
                    continue
                self.opened_source = candidate
                return capture
            if failed_capture is not None:
                failed_capture.release()
            failed_capture = capture

        self.opened_source = None
        return failed_capture if failed_capture is not None else cv2.VideoCapture(self.source)

    def _opencv_source_candidates(self, source, backend):
        candidates = self._video_devices_for_usb_source(source)
        if not candidates:
            candidates = [source]
        return [self._opencv_source_for_backend(candidate, backend) for candidate in candidates]

    def _opencv_source_for_backend(self, source, backend):
        if backend == "DSHOW" and isinstance(source, str):
            normalized = source.strip()
            if normalized and not normalized.lower().startswith("video="):
                return f"video={normalized}"
        return source

    def _video_devices_for_usb_source(self, source):
        if not isinstance(source, str):
            return []

        normalized = source.strip().lower()
        if not self._is_usb_source_spec(normalized):
            return []

        parts = normalized.split(":")
        if len(parts) not in {3, 4}:
            raise ValueError("USB camera source must be usb:VID:PID or usb:VID:PID:INDEX")

        vid = parts[1].zfill(4)
        pid = parts[2].zfill(4)
        selected_index = int(parts[3]) if len(parts) == 4 else None
        devices = self._find_video_devices_by_usb_id(vid, pid)

        if selected_index is not None:
            try:
                return [devices[selected_index]]
            except IndexError as exc:
                raise RuntimeError(
                    f"No video device index {selected_index} for USB camera {vid}:{pid}"
                ) from exc

        if not devices:
            raise RuntimeError(f"No video device found for USB camera {vid}:{pid}")
        return devices

    def _find_video_devices_by_usb_id(self, vid, pid):
        matches = []
        for video_path in sorted(glob("/sys/class/video4linux/video*")):
            device_path = os.path.realpath(os.path.join(video_path, "device"))
            usb_id = self._read_usb_id_from_device_path(device_path)
            if usb_id != (vid, pid):
                continue

            video_name = os.path.basename(video_path)
            matches.append(os.path.join("/dev", video_name))
        return matches

    @staticmethod
    def _is_usb_source_spec(source):
        return isinstance(source, str) and source.strip().lower().startswith("usb:")

    def _configure_capture(self, capture):
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        capture.set(cv2.CAP_PROP_FPS, self.fps)
        try:
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

    def _capture_can_grab_frame(self, capture):
        for _ in range(5):
            if capture.grab():
                return True
            time.sleep(0.02)
        return False

    def _read_usb_id_from_device_path(self, device_path):
        current = device_path
        while current and current != os.path.dirname(current):
            vendor_path = os.path.join(current, "idVendor")
            product_path = os.path.join(current, "idProduct")
            if os.path.exists(vendor_path) and os.path.exists(product_path):
                with open(vendor_path, "r", encoding="ascii") as vendor_file:
                    vendor = vendor_file.read().strip().lower()
                with open(product_path, "r", encoding="ascii") as product_file:
                    product = product_file.read().strip().lower()
                return vendor, product
            current = os.path.dirname(current)
        return None

    @staticmethod
    def _looks_like_windows_device_name(source):
        if os.name != "nt" or not isinstance(source, str):
            return False
        normalized = source.strip()
        if not normalized or normalized.lower() == "pi":
            return False
        return not any(separator in normalized for separator in ("/", "\\", ":"))

    def start(self):
        if self.camera is None:
            print("Camera is not initialized.", flush=True)
            return False

        self.is_running = True
        threading.Thread(target=self._capture_frames, daemon=True).start()
        return True

    def stop(self):
        self.is_running = False
        if self.camera:
            if hasattr(self.camera, "close"):
                self.camera.close()
            else:
                self.camera.release()

    def _capture_frames(self):
        while self.is_running:
            try:
                if hasattr(self.camera, "capture"):
                    stream = BytesIO()
                    self.camera.capture(stream, format="jpeg")
                    stream.seek(0)
                    jpeg_bytes = stream.getvalue()
                    self._update_lane_angle_from_jpeg(jpeg_bytes)
                    with self.lock:
                        self.frame = jpeg_bytes
                else:
                    ret, frame = self.camera.read()
                    if ret:
                        self._update_lane_angle(frame)
                        encode_param = [
                            int(cv2.IMWRITE_JPEG_QUALITY),
                            getattr(self, "jpeg_quality", 80),
                        ]
                        _, jpeg = cv2.imencode(".jpg", frame, encode_param)
                        with self.lock:
                            self.frame = jpeg.tobytes()

                time.sleep(1.0 / self.fps)
            except Exception as exc:
                print(f"Frame capture failed: {exc}", flush=True)
                time.sleep(0.1)

    def get_frame(self):
        with self.lock:
            return self.frame

    def get_lane_angle(self):
        with self.lock:
            return self.lane_angle

    def get_lane_angle_updated_at(self):
        with self.lock:
            return self.lane_angle_updated_at

    def get_parking_line_result(self):
        with self.lock:
            return self.parking_line_result.copy() if self.parking_line_result else None

    def get_mjpeg_frame(self):
        frame = self.get_frame()
        if frame is None:
            return self._get_placeholder_frame()
        return frame

    def get_debug_mjpeg_frame(self):
        frame = self.get_frame()
        if frame is None:
            return self._get_placeholder_frame("Camera Not Available")
        return self._draw_parking_line_overlay(frame)

    def _get_placeholder_frame(self, message="Camera Not Available"):
        if cv2 is None or np is None:
            return None

        img = np.zeros((self.resolution[1], self.resolution[0], 3), dtype=np.uint8)
        cv2.putText(
            img,
            message,
            (50, 100),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (255, 255, 255),
            2,
        )
        _, jpeg = cv2.imencode(".jpg", img)
        return jpeg.tobytes()

    def _draw_parking_line_overlay(self, jpeg_bytes):
        if cv2 is None or np is None:
            return jpeg_bytes

        frame_array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
        if frame is None:
            return jpeg_bytes

        result = self.get_parking_line_result()
        height, width = frame.shape[:2]
        cv2.line(frame, (width // 2, 0), (width // 2, height), (255, 180, 0), 1)
        cv2.line(frame, (0, height // 2), (width, height // 2), (255, 180, 0), 1)

        if result and result.get("detected"):
            line = result.get("reference_line")
            angle = result.get("y_axis_angle_deg")
            if line:
                x1, y1, x2, y2 = [int(value) for value in line]
                cv2.line(frame, (x1, y1), (x2, y2), (0, 255, 255), 6)
                cv2.circle(frame, (x1, y1), 7, (0, 255, 0), -1)
                cv2.circle(frame, (x2, y2), 7, (0, 0, 255), -1)
                dx = x2 - x1
                dy = y2 - y1
                length = max(math.hypot(dx, dy), 1.0)
                normal_x = -dy / length
                normal_y = dx / length
                center_x = int(round((x1 + x2) / 2))
                center_y = int(round((y1 + y2) / 2))
                arrow_length = int(max(70, min(width, height) * 0.18))
                end_x = int(round(center_x + normal_x * arrow_length))
                end_y = int(round(center_y + normal_y * arrow_length))
                cv2.arrowedLine(
                    frame,
                    (center_x, center_y),
                    (end_x, end_y),
                    (255, 0, 255),
                    4,
                    tipLength=0.22,
                )
            label = f"normal-y {angle:+.2f} deg" if angle is not None else "normal-y n/a"
            color = (0, 255, 255)
        else:
            label = "parking line not detected"
            color = (0, 0, 255)

        cv2.rectangle(frame, (12, 14), (360, 58), (0, 0, 0), -1)
        cv2.putText(
            frame,
            label,
            (24, 44),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            color,
            2,
        )

        _, jpeg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
        return jpeg.tobytes()

    def _update_lane_angle_from_jpeg(self, jpeg_bytes):
        if cv2 is None or np is None:
            return
        frame_array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
        self._update_lane_angle(frame)

    def _update_lane_angle(self, frame):
        if not self.lane_detection_enabled or cv2 is None or np is None or frame is None:
            return

        now = time.time()
        if now - self.last_lane_detection < self.lane_detection_interval:
            return

        self.last_lane_detection = now
        angle = None
        result = None

        if self.parking_line_detector is not None:
            result = self.parking_line_detector.detect(frame)
            with self.lock:
                self.parking_line_result = result
            if result.get("detected") and result.get("y_axis_angle_deg") is not None:
                angle = int(round(result["y_axis_angle_deg"]))

            if self.parking_line_log_enabled and now - self.last_parking_line_log_at >= self.parking_line_log_interval:
                print(self.parking_line_detector.format_log_message(result), flush=True)
                self.last_parking_line_log_at = now

        if angle is None:
            angle = self._detect_lane_angle(frame)
        if angle is None:
            return

        with self.lock:
            self.lane_angle = max(-180, min(180, int(angle)))
            self.lane_angle_updated_at = now

    def _detect_lane_angle(self, frame):
        height, width = frame.shape[:2]
        if height <= 0 or width <= 0:
            return None

        roi_top = int(height * 0.55)
        roi = frame[roi_top:height, :]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 60, 160)

        lines = cv2.HoughLinesP(
            edges,
            1,
            np.pi / 180,
            threshold=40,
            minLineLength=max(30, width // 12),
            maxLineGap=40,
        )
        if lines is None:
            return None

        weighted_sum = 0.0
        weight_total = 0.0
        for line in lines[:, 0]:
            x1, y1, x2, y2 = [int(value) for value in line]
            dx = x2 - x1
            dy = y2 - y1
            length = math.hypot(dx, dy)
            if length < 20:
                continue

            angle_from_horizontal = math.degrees(math.atan2(-dy, dx))
            abs_angle = abs(angle_from_horizontal)
            if abs_angle < 15 or abs_angle > 85:
                continue

            lane_angle = angle_from_horizontal - 90 if angle_from_horizontal > 0 else angle_from_horizontal + 90
            weighted_sum += lane_angle * length
            weight_total += length

        if weight_total == 0:
            return None

        return max(-180, min(180, int(round(weighted_sum / weight_total))))


class CameraStreamGenerator:
    """Generate MJPEG frames for Flask streaming."""

    def __init__(self, camera_manager):
        self.camera = camera_manager

    def generate(self):
        while True:
            frame = self.camera.get_mjpeg_frame()
            if frame:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: "
                    + str(len(frame)).encode()
                    + b"\r\n\r\n"
                    + frame
                    + b"\r\n"
                )
            time.sleep(1.0 / self.camera.fps)

    def generate_debug(self):
        while True:
            frame = self.camera.get_debug_mjpeg_frame()
            if frame:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: "
                    + str(len(frame)).encode()
                    + b"\r\n\r\n"
                    + frame
                    + b"\r\n"
                )
            time.sleep(1.0 / self.camera.fps)
