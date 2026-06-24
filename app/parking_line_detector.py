"""Parking line detection helpers."""

import math
import time

import cv2
import numpy as np


class ParkingLineDetector:
    """Detect white parking lines and estimate the perpendicular vector slope."""

    def __init__(
        self,
        min_line_length=28,
        white_value_threshold=145,
        max_white_saturation=120,
        roi_top_ratio=0.25,
        min_candidate_score=0.42,
    ):
        self.min_line_length = min_line_length
        self.white_value_threshold = white_value_threshold
        self.max_white_saturation = max_white_saturation
        self.roi_top_ratio = roi_top_ratio
        self.min_candidate_score = min_candidate_score
        self._lsd = self._create_lsd()

    def detect(self, frame):
        """Return parking line detection data for a BGR frame."""
        if frame is None or frame.size == 0:
            return self._not_detected({"reason": "empty_frame"})

        mask, roi_top = self._white_mask(frame)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.bitwise_and(gray, gray, mask=mask)

        segments = self._detect_segments(gray)
        line_candidates = self._score_segments(segments, mask, frame, roi_top)
        component_candidates = self._score_components(mask, roi_top)
        candidates = line_candidates + component_candidates
        debug = {
            "roi_top": roi_top,
            "white_pixels": int(np.count_nonzero(mask)),
            "segment_count": len(segments),
            "line_candidate_count": len(line_candidates),
            "component_candidate_count": len(component_candidates),
            "candidate_count": len(candidates),
        }
        if not candidates:
            return self._not_detected(debug)

        best_candidate = max(candidates, key=lambda candidate: candidate["score"])
        if best_candidate["score"] < self.min_candidate_score:
            debug["best_score"] = best_candidate["score"]
            return self._not_detected(debug)

        angle = best_candidate["angle"]
        x_axis_angle = self._normalize_angle(angle)
        x_axis_slope = self._slope_from_angle(x_axis_angle)
        y_axis_angle = self._normalize_angle(x_axis_angle - (math.pi / 2.0))
        y_axis_slope = self._slope_from_angle(y_axis_angle)
        perpendicular_angle = self._normalize_angle(x_axis_angle + (math.pi / 2.0))
        perpendicular_slope = self._slope_from_angle(perpendicular_angle)

        return {
            "detected": True,
            "line_count": len(candidates),
            "best_score": best_candidate["score"],
            "candidate_type": best_candidate["type"],
            "white_support": best_candidate["white_support"],
            "reflection_ratio": best_candidate["reflection_ratio"],
            "component_thickness": best_candidate["component_thickness"],
            "debug": debug,
            "x_axis_angle_deg": math.degrees(x_axis_angle),
            "x_axis_slope": x_axis_slope,
            "y_axis_angle_deg": math.degrees(y_axis_angle),
            "y_axis_slope": y_axis_slope,
            "line_angle_deg": math.degrees(x_axis_angle),
            "perpendicular_angle_deg": math.degrees(perpendicular_angle),
            "perpendicular_slope": perpendicular_slope,
            "timestamp": time.time(),
        }

    def format_log_message(self, result):
        """Create the server log message requested by the UI server."""
        if not result.get("detected"):
            return "주차선 검출안됨"

        return (
            "주차선 검출됨: "
            f"Y축 기준 각도={result['y_axis_angle_deg']:.2f}deg, "
            f"점수={result['best_score']:.2f}, "
            f"후보={result['candidate_type']}"
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

    def _detect_segments(self, gray):
        if self._lsd is not None:
            lines = self._lsd.detect(gray)[0]
            if lines is None:
                return []
            return [line[0] for line in lines]

        lines = cv2.HoughLinesP(
            gray,
            rho=1,
            theta=np.pi / 180,
            threshold=32,
            minLineLength=self.min_line_length,
            maxLineGap=20,
        )
        if lines is None:
            return []
        return [line[0] for line in lines]

    def _score_segments(self, segments, mask, frame, roi_top):
        candidates = []
        height, width = mask.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        _, component_labels, component_stats, _ = cv2.connectedComponentsWithStats(mask, 8)

        for segment in segments:
            x1, y1, x2, y2 = [float(value) for value in segment]
            dx = x2 - x1
            dy = y2 - y1
            length = math.hypot(dx, dy)
            if length < self.min_line_length:
                continue

            midpoint_y = (y1 + y2) / 2.0
            if midpoint_y < roi_top:
                continue

            sample_count = max(8, min(24, int(length / 8)))
            xs = np.linspace(x1, x2, sample_count).astype(np.int32)
            ys = np.linspace(y1, y2, sample_count).astype(np.int32)
            xs = np.clip(xs, 0, width - 1)
            ys = np.clip(ys, 0, height - 1)
            white_ratio = float(np.count_nonzero(mask[ys, xs])) / sample_count
            if white_ratio < 0.38:
                continue

            angle = math.atan2(dy, dx)
            band_scores = self._band_scores(mask, edges, (x1, y1, x2, y2))
            component_scores = self._component_scores(
                component_labels,
                component_stats,
                xs,
                ys,
                length,
                min(height, width),
            )
            max_line_component_thickness = max(55.0, min(height, width) * 0.25)
            if component_scores["component_thickness"] > max_line_component_thickness:
                continue

            length_score = min(length / max(height * 0.45, self.min_line_length), 1.0)
            roi_score = self._clamp((midpoint_y - roi_top) / max(height - roi_top, 1), 0.0, 1.0)
            vertical_score = abs(math.sin(angle))

            score = (
                0.24 * length_score
                + 0.24 * white_ratio
                + 0.18 * band_scores["edge_score"]
                + 0.17 * roi_score
                + 0.17 * vertical_score
                - 0.28 * band_scores["reflection_penalty"]
                - 0.36 * component_scores["component_penalty"]
            )

            if score <= 0:
                continue

            candidates.append(
                {
                    "type": "line_segment",
                    "angle": angle,
                    "length": length,
                    "score": score,
                    "white_support": white_ratio,
                    "reflection_ratio": band_scores["reflection_ratio"],
                    "reflection_penalty": band_scores["reflection_penalty"],
                    "component_thickness": component_scores["component_thickness"],
                    "component_penalty": component_scores["component_penalty"],
                }
            )

        return candidates

    def _score_components(self, mask, roi_top):
        candidates = []
        height, width = mask.shape[:2]
        _, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
        min_area = max(90, int(height * width * 0.0006))
        max_area = int(height * width * 0.45)

        for label in range(1, stats.shape[0]):
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area < min_area or area > max_area:
                continue

            x = int(stats[label, cv2.CC_STAT_LEFT])
            y = int(stats[label, cv2.CC_STAT_TOP])
            w = int(stats[label, cv2.CC_STAT_WIDTH])
            h = int(stats[label, cv2.CC_STAT_HEIGHT])
            center_y = float(centroids[label][1])
            if center_y < roi_top:
                continue

            component_mask = labels == label
            points = np.column_stack(np.where(component_mask))
            if points.shape[0] < 2:
                continue

            points_xy = points[:, ::-1].astype(np.float32)
            mean, eigenvectors, eigenvalues = cv2.PCACompute2(points_xy, mean=None)
            major = eigenvectors[0]
            angle = math.atan2(float(major[1]), float(major[0]))
            length = math.sqrt(float(eigenvalues[0][0])) * 4.0
            minor = math.sqrt(max(float(eigenvalues[1][0]), 1e-6)) * 4.0
            if length < self.min_line_length:
                continue

            aspect_score = self._clamp((length / max(minor, 1.0) - 1.2) / 4.0, 0.0, 1.0)
            area_score = self._clamp(area / max(height * width * 0.012, 1), 0.0, 1.0)
            length_score = self._clamp(length / max(height * 0.45, self.min_line_length), 0.0, 1.0)
            roi_score = self._clamp((center_y - roi_top) / max(height - roi_top, 1), 0.0, 1.0)
            vertical_score = abs(math.sin(angle))
            fill_ratio = area / max(w * h, 1)
            blob_penalty = self._clamp((fill_ratio - 0.78) / 0.22, 0.0, 1.0)

            score = (
                0.26 * aspect_score
                + 0.22 * length_score
                + 0.18 * roi_score
                + 0.16 * vertical_score
                + 0.14 * area_score
                - 0.18 * blob_penalty
            )

            if score <= 0:
                continue

            candidates.append(
                {
                    "type": "white_component",
                    "angle": angle,
                    "length": length,
                    "score": score,
                    "white_support": 1.0,
                    "reflection_ratio": 0.0,
                    "component_thickness": area / max(length, 1.0),
                    "component_penalty": blob_penalty,
                }
            )

        return candidates

    def _component_scores(self, labels, stats, xs, ys, length, min_frame_size):
        sampled_labels = labels[ys, xs]
        sampled_labels = sampled_labels[sampled_labels > 0]
        if sampled_labels.size == 0:
            return {"component_thickness": 0.0, "component_penalty": 0.0}

        label_counts = np.bincount(sampled_labels)
        dominant_label = int(np.argmax(label_counts))
        component_area = float(stats[dominant_label, cv2.CC_STAT_AREA])
        component_thickness = component_area / max(length, 1.0)
        max_expected_thickness = max(20.0, min_frame_size * 0.08)
        component_penalty = self._clamp(
            (component_thickness - max_expected_thickness) / max_expected_thickness,
            0.0,
            1.0,
        )

        return {
            "component_thickness": component_thickness,
            "component_penalty": component_penalty,
        }

    def _band_scores(self, mask, edges, segment):
        height, width = mask.shape[:2]
        x1, y1, x2, y2 = [int(round(value)) for value in segment]
        narrow_thickness = max(3, int(min(height, width) * 0.010))
        wide_thickness = max(14, narrow_thickness * 5)

        narrow_band = np.zeros_like(mask)
        wide_band = np.zeros_like(mask)
        cv2.line(narrow_band, (x1, y1), (x2, y2), 255, narrow_thickness)
        cv2.line(wide_band, (x1, y1), (x2, y2), 255, wide_thickness)

        narrow_pixels = max(int(np.count_nonzero(narrow_band)), 1)
        wide_pixels = max(int(np.count_nonzero(wide_band)), 1)
        narrow_white = int(np.count_nonzero(cv2.bitwise_and(mask, narrow_band)))
        wide_white = int(np.count_nonzero(cv2.bitwise_and(mask, wide_band)))
        wide_edges = int(np.count_nonzero(cv2.bitwise_and(edges, wide_band)))

        reflection_ratio = wide_white / max(narrow_white, 1)
        reflection_penalty = self._clamp((reflection_ratio - 2.25) / 2.25, 0.0, 1.0)
        wide_fill_ratio = wide_white / wide_pixels
        if wide_fill_ratio > 0.68:
            reflection_penalty = max(
                reflection_penalty,
                self._clamp((wide_fill_ratio - 0.68) / 0.22, 0.0, 1.0),
            )

        edge_ratio = wide_edges / wide_pixels
        edge_score = self._clamp(edge_ratio / 0.08, 0.0, 1.0)
        narrow_support = narrow_white / narrow_pixels

        return {
            "edge_score": edge_score,
            "narrow_support": narrow_support,
            "reflection_ratio": reflection_ratio,
            "reflection_penalty": reflection_penalty,
        }

    def _weighted_angle(self, candidates):
        # Double-angle averaging treats opposite line directions as the same line.
        sin_sum = 0.0
        cos_sum = 0.0
        for candidate in candidates:
            weight = candidate["length"]
            angle = candidate["angle"] * 2.0
            sin_sum += math.sin(angle) * weight
            cos_sum += math.cos(angle) * weight

        return 0.5 * math.atan2(sin_sum, cos_sum)

    def _normalize_angle(self, angle):
        while angle <= -math.pi / 2.0:
            angle += math.pi
        while angle > math.pi / 2.0:
            angle -= math.pi
        return angle

    def _slope_from_angle(self, angle):
        cos_value = math.cos(angle)
        if abs(cos_value) < 1e-6:
            return math.inf
        return math.tan(angle)

    def _clamp(self, value, minimum, maximum):
        return max(minimum, min(value, maximum))

    def _create_lsd(self):
        try:
            return cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
        except AttributeError:
            return None

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
