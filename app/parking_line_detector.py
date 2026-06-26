"""Parking line detection helpers."""

import math
import time

import cv2
import numpy as np


class ParkingLineDetector:
    """Detect bright parking/reference lines and estimate their angle."""

    def __init__(
        self,
        min_line_length=28,
        white_value_threshold=145,
        max_white_saturation=120,
        roi_top_ratio=0.45,
        min_candidate_score=0.25,
        max_reference_line_angle=65,
        min_component_aspect_ratio=2.6,
        max_component_area_ratio=0.20,
    ):
        self.min_line_length = min_line_length
        self.white_value_threshold = white_value_threshold
        self.max_white_saturation = max_white_saturation
        self.roi_top_ratio = roi_top_ratio
        self.min_candidate_score = min_candidate_score
        self.max_reference_line_angle = max_reference_line_angle
        self.min_component_aspect_ratio = min_component_aspect_ratio
        self.max_component_area_ratio = max_component_area_ratio

    def detect(self, frame):
        """Return parking line detection data for a BGR frame."""
        if frame is None or frame.size == 0:
            return self._not_detected({"reason": "empty_frame"})

        mask, roi_top = self._white_mask(frame)
        height, width = frame.shape[:2]
        component_candidates, component_debug, line_mask = self._component_candidates(mask, frame.shape)
        edges = cv2.Canny(line_mask, 60, 160)
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
            "accepted_white_pixels": int(np.count_nonzero(line_mask)),
            "line_count": 0 if lines is None else int(len(lines)),
            **component_debug,
        }
        candidates = list(component_candidates)
        candidates.extend(self._hough_candidates(lines, width, height))

        debug["candidate_count"] = len(candidates)
        if not candidates:
            return self._not_detected(debug)

        weighted_sum = sum(candidate["angle"] * candidate["weight"] for candidate in candidates)
        weight_total = sum(candidate["weight"] for candidate in candidates)
        weighted_angle_deg = max(-180, min(180, weighted_sum / max(weight_total, 1.0)))
        best_candidate = max(candidates, key=lambda candidate: (candidate["score"], candidate["length"]))
        y_axis_angle_deg = max(-180, min(180, best_candidate["angle"]))

        return {
            "detected": True,
            "line_count": len(candidates),
            "best_score": best_candidate["score"],
            "candidate_type": best_candidate["type"],
            "reference_line": best_candidate.get("line"),
            "weighted_angle_deg": weighted_angle_deg,
            "debug": debug,
            "reference_line_angle_deg": y_axis_angle_deg,
            "normal_y_axis_angle_deg": y_axis_angle_deg,
            "x_axis_angle_deg": y_axis_angle_deg,
            "x_axis_slope": self._slope_from_degrees(y_axis_angle_deg),
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
            return "주차선 검출안됨"

        return (
            "주차선 검출: "
            f"y_axis_angle={result['y_axis_angle_deg']:.2f}deg, "
            f"score={result['best_score']:.2f}, "
            f"type={result['candidate_type']}"
        )

    def _component_candidates(self, mask, frame_shape):
        height, width = frame_shape[:2]
        accepted_mask = np.zeros_like(mask)
        candidate_count = 0
        rejected_count = 0
        candidates = []

        component_count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        min_area = max(40, int(self.min_line_length * 2))
        max_area = max(min_area, int(width * height * self.max_component_area_ratio))

        for label in range(1, component_count):
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area < min_area or area > max_area:
                rejected_count += 1
                continue

            component_mask = labels == label
            ys, xs = np.where(component_mask)
            if len(xs) < 2:
                rejected_count += 1
                continue

            points = np.column_stack((xs.astype(np.float32), ys.astype(np.float32)))
            _, eigenvectors, eigenvalues = cv2.PCACompute2(points, mean=None)
            primary_value = max(float(eigenvalues[0, 0]), 0.0)
            secondary_value = max(float(eigenvalues[1, 0]), 1e-6)
            length = math.sqrt(primary_value * 12.0)
            thickness = math.sqrt(secondary_value * 12.0)
            aspect_ratio = length / max(thickness, 1e-6)
            angle = self._vector_angle_from_image_x_axis(
                float(eigenvectors[0, 0]),
                float(eigenvectors[0, 1]),
            )

            if (
                length < self.min_line_length
                or aspect_ratio < self.min_component_aspect_ratio
                or abs(angle) > self.max_reference_line_angle
            ):
                rejected_count += 1
                continue

            score = min(
                0.65 * (length / max(width * 0.45, 1.0))
                + 0.35 * min(aspect_ratio / 8.0, 1.0),
                1.0,
            )
            if score < self.min_candidate_score:
                rejected_count += 1
                continue

            accepted_mask[component_mask] = 255
            line = self._component_line_endpoints(points, eigenvectors[0])
            candidate_count += 1
            candidates.append(
                {
                    "angle": angle,
                    "length": length,
                    "score": score,
                    "weight": max(length * score, 1.0),
                    "type": "white_component",
                    "line": line,
                }
            )

        debug = {
            "component_count": int(component_count - 1),
            "accepted_component_count": candidate_count,
            "rejected_component_count": rejected_count,
        }
        return candidates, debug, accepted_mask

    def _hough_candidates(self, lines, width, height):
        if lines is None:
            return []

        candidates = []
        for line in lines[:, 0]:
            x1, y1, x2, y2 = [int(value) for value in line]
            dx = x2 - x1
            dy = y2 - y1
            length = math.hypot(dx, dy)
            if length < self.min_line_length:
                continue

            angle = self._line_angle_from_image_x_axis(x1, y1, x2, y2)
            if abs(angle) > self.max_reference_line_angle:
                continue

            score = min(length / max(min(width, height) * 0.45, 1.0), 1.0)
            if score < self.min_candidate_score:
                continue

            candidates.append(
                {
                    "angle": angle,
                    "length": length,
                    "score": score,
                    "weight": max(length * score, 1.0),
                    "type": "hough_line",
                    "line": [int(x1), int(y1), int(x2), int(y2)],
                }
            )

        return candidates

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

    def _line_angle_from_image_x_axis(self, x1, y1, x2, y2):
        return self._vector_angle_from_image_x_axis(x2 - x1, y2 - y1)

    def _component_line_endpoints(self, points, direction):
        direction = np.asarray(direction, dtype=np.float32)
        norm = float(np.linalg.norm(direction))
        if norm < 1e-6:
            x_min, y_min = np.min(points, axis=0)
            x_max, y_max = np.max(points, axis=0)
            return [int(x_min), int(y_min), int(x_max), int(y_max)]

        direction /= norm
        center = np.mean(points, axis=0)
        projections = (points - center) @ direction
        start = center + direction * float(np.min(projections))
        end = center + direction * float(np.max(projections))
        if start[0] > end[0] or (start[0] == end[0] and start[1] > end[1]):
            start, end = end, start

        return [
            int(round(start[0])),
            int(round(start[1])),
            int(round(end[0])),
            int(round(end[1])),
        ]

    def _vector_angle_from_image_x_axis(self, dx, dy):
        if dx < 0 or (dx == 0 and dy < 0):
            dx *= -1
            dy *= -1
        angle = math.degrees(math.atan2(dy, dx))
        if angle > 90:
            angle -= 180
        elif angle < -90:
            angle += 180
        return angle

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
            "reference_line": None,
            "weighted_angle_deg": None,
            "normal_y_axis_angle_deg": None,
            "x_axis_angle_deg": None,
            "x_axis_slope": None,
            "y_axis_angle_deg": None,
            "y_axis_slope": None,
            "line_angle_deg": None,
            "perpendicular_angle_deg": None,
            "perpendicular_slope": None,
            "timestamp": time.time(),
        }
