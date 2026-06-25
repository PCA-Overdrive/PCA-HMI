"""Parking line detection helpers."""

import math
import time

import cv2
import numpy as np


class ParkingLineDetector:
    """Detect bright parking/lane lines and estimate their angle."""

    def __init__(
        self,
        min_line_length=28,
        white_value_threshold=145,
        max_white_saturation=120,
        roi_top_ratio=0.45,
        min_candidate_score=0.25,
    ):
        self.min_line_length = min_line_length
        self.white_value_threshold = white_value_threshold
        self.max_white_saturation = max_white_saturation
        self.roi_top_ratio = roi_top_ratio
        self.min_candidate_score = min_candidate_score

    def detect(self, frame):
        """Return parking line detection data for a BGR frame."""
        if frame is None or frame.size == 0:
            return self._not_detected({"reason": "empty_frame"})

        mask, roi_top = self._white_mask(frame)
        edges = cv2.Canny(mask, 60, 160)
        height, width = frame.shape[:2]
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=40,
            minLineLength=max(self.min_line_length, width // 12),
            maxLineGap=40,
        )

        debug = {
            "roi_top": roi_top,
            "white_pixels": int(np.count_nonzero(mask)),
            "line_count": 0 if lines is None else int(len(lines)),
        }
        if lines is None:
            return self._not_detected(debug)

        candidates = []
        for line in lines[:, 0]:
            x1, y1, x2, y2 = [int(value) for value in line]
            dx = x2 - x1
            dy = y2 - y1
            length = math.hypot(dx, dy)
            if length < self.min_line_length:
                continue

            angle = math.degrees(math.atan2(-dy, dx))
            abs_angle = abs(angle)
            if abs_angle < 15 or abs_angle > 85:
                continue

            lane_angle = angle - 90 if angle > 0 else angle + 90
            score = min(length / max(height * 0.45, 1), 1.0)
            if score < self.min_candidate_score:
                continue

            candidates.append(
                {
                    "angle": lane_angle,
                    "length": length,
                    "score": score,
                    "type": "hough_line",
                }
            )

        debug["candidate_count"] = len(candidates)
        if not candidates:
            return self._not_detected(debug)

        weighted_sum = sum(candidate["angle"] * candidate["length"] for candidate in candidates)
        weight_total = sum(candidate["length"] for candidate in candidates)
        y_axis_angle_deg = max(-180, min(180, weighted_sum / max(weight_total, 1.0)))
        best_candidate = max(candidates, key=lambda candidate: candidate["score"])

        return {
            "detected": True,
            "line_count": len(candidates),
            "best_score": best_candidate["score"],
            "candidate_type": best_candidate["type"],
            "debug": debug,
            "x_axis_angle_deg": y_axis_angle_deg + 90,
            "x_axis_slope": self._slope_from_degrees(y_axis_angle_deg + 90),
            "y_axis_angle_deg": y_axis_angle_deg,
            "y_axis_slope": self._slope_from_degrees(y_axis_angle_deg),
            "line_angle_deg": y_axis_angle_deg,
            "perpendicular_angle_deg": y_axis_angle_deg,
            "perpendicular_slope": self._slope_from_degrees(y_axis_angle_deg),
            "timestamp": time.time(),
        }

    def format_log_message(self, result):
        """Create a compact server log message."""
        if not result.get("detected"):
            return "Parking line not detected"

        return (
            "Parking line detected: "
            f"y_axis_angle={result['y_axis_angle_deg']:.2f}deg, "
            f"score={result['best_score']:.2f}, "
            f"type={result['candidate_type']}"
        )

    def _white_mask(self, frame):
        height = frame.shape[0]
        roi_top = int(height * self.roi_top_ratio)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower_white = np.array([0, 0, self.white_value_threshold], dtype=np.uint8)
        upper_white = np.array([180, self.max_white_saturation, 255], dtype=np.uint8)
        mask = cv2.inRange(hsv, lower_white, upper_white)

        roi_mask = np.zeros_like(mask)
        roi_mask[roi_top:, :] = 255
        mask = cv2.bitwise_and(mask, roi_mask)

        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        return mask, roi_top

    def _slope_from_degrees(self, angle):
        radians = math.radians(angle)
        cos_value = math.cos(radians)
        if abs(cos_value) < 1e-6:
            return math.inf
        return math.tan(radians)

    def _not_detected(self, debug=None):
        return {
            "detected": False,
            "line_count": 0,
            "debug": debug or {},
            "x_axis_angle_deg": None,
            "x_axis_slope": None,
            "y_axis_angle_deg": None,
            "y_axis_slope": None,
            "line_angle_deg": None,
            "perpendicular_angle_deg": None,
            "perpendicular_slope": None,
            "timestamp": time.time(),
        }
