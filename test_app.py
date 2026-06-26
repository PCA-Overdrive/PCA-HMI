"""
테스트 및 디버깅 모듈
"""

import unittest
import json
import math
import os
import cv2
import numpy as np

os.environ.setdefault('CAMERA_SOURCE', '-1')

from app.main import app, vehicle_state, pdw_data
from app.can_interface import DISTANCE_LEVEL_FIELDS, decode_can_frame
from app.can_controller import VehicleCanController
from app.parking_line_detector import ParkingLineDetector


class TestVehicleDisplay(unittest.TestCase):
    """API 테스트"""
    
    def setUp(self):
        """테스트 클라이언트 설정"""
        self.app = app.test_client()
        self.app.testing = True
    
    def test_index_page(self):
        """메인 페이지 테스트"""
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<!doctype html>', response.data)
    
    def test_vehicle_state_api(self):
        """차량 상태 API 테스트"""
        response = self.app.get('/api/vehicle-state')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertIn('speed', data)
        self.assertIn('gear', data)
        self.assertIn('steering_angle', data)
        self.assertIn('collision_avoidance', data)
        self.assertIn('rear_camera_active', data)
    
    def test_pdw_data_api(self):
        """PDW 데이터 API 테스트"""
        response = self.app.get('/api/pdw-data')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        # 설계서 0x400의 10개 방향 필드 확인
        for direction in DISTANCE_LEVEL_FIELDS:
            self.assertIn(direction, data)
            sensor_data = data[direction]
            self.assertIn('distance', sensor_data)
            self.assertIn('level', sensor_data)
            self.assertIn('color', sensor_data)
    
    def test_collision_avoidance_toggle(self):
        """충돌방지 기능 토글 테스트"""
        # 초기 상태 가져오기
        response1 = self.app.get('/api/vehicle-state')
        data1 = json.loads(response1.data)
        initial_state = data1['collision_avoidance']
        
        # 토글
        response2 = self.app.post('/api/toggle-collision-avoidance')
        data2 = json.loads(response2.data)
        self.assertEqual(data2['status'], 'success')
        self.assertNotEqual(data2['collision_avoidance'], initial_state)
    
    def test_gear_values(self):
        """기어 값 검증"""
        valid_gears = ['P', 'R', 'D', 'N']
        response = self.app.get('/api/vehicle-state')
        data = json.loads(response.data)
        self.assertIn(data['gear'], valid_gears)
    
    def test_speed_range(self):
        """속도 범위 검증"""
        response = self.app.get('/api/vehicle-state')
        data = json.loads(response.data)
        speed = data['speed']
        self.assertGreaterEqual(speed, 0)
        self.assertLessEqual(speed, 200)

    def test_steering_angle_range(self):
        """조향각 범위 검증"""
        response = self.app.get('/api/vehicle-state')
        data = json.loads(response.data)
        steering_angle = data['steering_angle']
        self.assertGreaterEqual(steering_angle, -20)
        self.assertLessEqual(steering_angle, 20)
    
    def test_pdw_risk_levels(self):
        """PDW 위험 단계 검증"""
        response = self.app.get('/api/pdw-data')
        data = json.loads(response.data)
        
        valid_colors = ['#666666', '#00ff00', '#ffaa00', '#ff7a00', '#ff0000']
        for sensor_data in data.values():
            self.assertIn(sensor_data['level'], [0, 1, 2, 3, 4])
            self.assertIn(sensor_data['color'], valid_colors)


class SensorSimulationTest(unittest.TestCase):
    """센서 시뮬레이션 테스트"""
    
    def test_pdw_color_mapping(self):
        """위험 단계별 색상 매핑 테스트"""
        from app.main import RISK_LEVELS
        
        color_map = {
            0: '#666666',  # 감지안됨
            1: '#00ff00',  # 안전
            2: '#ffaa00',  # 주의
            3: '#ff7a00',  # 근접
            4: '#ff0000',  # 위험
        }
        
        for level, color in color_map.items():
            self.assertEqual(RISK_LEVELS[level]['color'], color)

    def test_distance_level_can_frame_decode(self):
        """0x400 DistanceLevelCmd 페이로드 디코딩 검증"""
        payload = [1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 35, 2, 1]
        decoded = decode_can_frame({'can_id': 0x400, 'data': payload})

        self.assertEqual(decoded['message_name'], 'DistanceLevelCmd')
        self.assertEqual(decoded['levels']['FrontLevelCmd'], 1)
        self.assertEqual(decoded['levels']['RightBehindLevelCmd'], 4)
        self.assertTrue(decoded['emergency_stop_activated'])
        self.assertEqual(decoded['speed'], 3.5)
        self.assertEqual(decoded['gear'], 'R')
        self.assertTrue(decoded['collision_avoidance'])

    def test_exit_status_2_or_3_resets_auto_parking_cmd(self):
        """0x401 status 2/3 수신 시 0x300 송신 명령을 0으로 복귀."""
        controller = VehicleCanController()

        for status in (2, 3):
            controller.set_auto_parking_cmd(4)
            msg = type("CanMessage", (), {
                "arbitration_id": 0x401,
                "data": bytes([status]),
            })()

            changed = controller._handle_can_rx_message(msg)

            self.assertTrue(changed)
            self.assertEqual(controller.exit_status, status)
            self.assertEqual(controller.auto_parking_cmd, 0)

    def test_other_exit_status_keeps_auto_parking_cmd(self):
        """0x401 status 2/3 외 값은 0x300 송신 명령을 유지."""
        controller = VehicleCanController()
        controller.set_auto_parking_cmd(4)
        msg = type("CanMessage", (), {
            "arbitration_id": 0x401,
            "data": bytes([1]),
        })()

        changed = controller._handle_can_rx_message(msg)

        self.assertTrue(changed)
        self.assertEqual(controller.exit_status, 1)
        self.assertEqual(controller.auto_parking_cmd, 4)


class ParkingLineDetectorTest(unittest.TestCase):
    """Parking line detection tests."""

    def test_detects_white_parking_line_perpendicular_slope(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.line(frame, (80, 220), (220, 100), (255, 255, 255), 8)

        detector = ParkingLineDetector(min_line_length=30)
        result = detector.detect(frame)

        self.assertTrue(result['detected'])
        self.assertGreater(result['line_count'], 0)
        self.assertIsNotNone(result['x_axis_slope'])
        self.assertIsNotNone(result['x_axis_angle_deg'])
        self.assertIsNotNone(result['y_axis_angle_deg'])
        self.assertIsNotNone(result['perpendicular_slope'])
        self.assertFalse(math.isnan(result['perpendicular_slope']))

    def test_reports_not_detected_without_white_line(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)

        detector = ParkingLineDetector(min_line_length=30)
        result = detector.detect(frame)

        self.assertFalse(result['detected'])
        self.assertEqual(detector.format_log_message(result), '주차선 검출안됨')

    def test_detects_close_thick_parking_line_blob(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.line(frame, (90, 230), (220, 80), (255, 255, 255), 34)

        detector = ParkingLineDetector(min_line_length=30)
        result = detector.detect(frame)

        self.assertTrue(result['detected'])
        self.assertEqual(result['candidate_type'], 'white_component')
        self.assertIsNotNone(result['x_axis_slope'])
        self.assertIsNotNone(result['y_axis_angle_deg'])
        self.assertLess(abs(result['y_axis_angle_deg']), 70)

    def test_rejects_large_white_reflection_blob(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.rectangle(frame, (80, 120), (240, 230), (255, 255, 255), -1)

        detector = ParkingLineDetector(min_line_length=30)
        result = detector.detect(frame)

        self.assertFalse(result['detected'])


def run_performance_test():
    """성능 테스트"""
    import time
    
    print("=== 성능 테스트 ===")
    
    app = app.test_client()
    
    # API 응답 시간 측정
    start_time = time.time()
    for _ in range(100):
        app.get('/api/vehicle-state')
    elapsed = time.time() - start_time
    print(f"차량 상태 API: {elapsed/100*1000:.2f}ms/call")
    
    start_time = time.time()
    for _ in range(100):
        app.get('/api/pdw-data')
    elapsed = time.time() - start_time
    print(f"PDW 데이터 API: {elapsed/100*1000:.2f}ms/call")


if __name__ == '__main__':
    # 단위 테스트 실행
    print("단위 테스트 실행 중...")
    unittest.main(argv=[''], verbosity=2, exit=False)
    
    # 성능 테스트 실행
    print("\n성능 테스트 실행 중...")
    run_performance_test()
