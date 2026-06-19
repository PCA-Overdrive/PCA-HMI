"""
센서 데이터 관리 모듈
초음파 센서(Ultrasonic), 기타 센서 데이터 처리
"""

import threading
import time
from collections import deque
import json

class UltrasonicSensor:
    """초음파 센서 클래스"""
    
    def __init__(self, trig_pin, echo_pin, sensor_id):
        """
        초음파 센서 초기화
        
        Args:
            trig_pin: 트리거 GPIO 핀 번호
            echo_pin: 에코 GPIO 핀 번호
            sensor_id: 센서 식별자 (FL, FC, FR 등)
        """
        self.trig_pin = trig_pin
        self.echo_pin = echo_pin
        self.sensor_id = sensor_id
        self.distance = 0  # cm
        self.distance_history = deque(maxlen=10)  # 최근 10개 데이터
        
        try:
            import RPi.GPIO as GPIO
            self.GPIO = GPIO
            self.GPIO.setmode(GPIO.BCM)
            self.GPIO.setup(self.trig_pin, GPIO.OUT)
            self.GPIO.setup(self.echo_pin, GPIO.IN)
            self.initialized = True
        except ImportError:
            print("RPi.GPIO 모듈이 설치되지 않았습니다. (개발 모드)")
            self.initialized = False
        except Exception as e:
            print(f"GPIO 초기화 실패: {e}")
            self.initialized = False
    
    def measure_distance(self):
        """거리 측정"""
        if not self.initialized:
            return None
        
        try:
            # 트리거 신호 전송
            self.GPIO.output(self.trig_pin, False)
            time.sleep(0.00001)  # 10 마이크로초
            self.GPIO.output(self.trig_pin, True)
            time.sleep(0.00001)
            self.GPIO.output(self.trig_pin, False)
            
            # 에코 신호 대기
            timeout = time.time() + 0.1  # 100ms 타임아웃
            while self.GPIO.input(self.echo_pin) == 0:
                pulse_start = time.time()
                if time.time() > timeout:
                    return None
            
            while self.GPIO.input(self.echo_pin) == 1:
                pulse_end = time.time()
                if time.time() > timeout + 0.1:
                    return None
            
            # 거리 계산 (음속 = 34300 cm/s)
            pulse_duration = pulse_end - pulse_start
            distance = pulse_duration * 34300 / 2
            
            self.distance = distance
            self.distance_history.append(distance)
            return distance
        
        except Exception as e:
            print(f"거리 측정 오류 ({self.sensor_id}): {e}")
            return None
    
    def get_average_distance(self):
        """평균 거리 반환"""
        if not self.distance_history:
            return 0
        return sum(self.distance_history) / len(self.distance_history)
    
    def cleanup(self):
        """GPIO 정리"""
        if self.initialized:
            self.GPIO.cleanup([self.trig_pin, self.echo_pin])


class PDWSensorArray:
    """PDW 센서 배열 관리"""
    
    # 센서 배치: GPIO 핀 번호 매핑
    # (실제로는 라즈베리파이의 실제 핀 번호로 설정)
    SENSOR_PINS = {
        'FL': {'trig': 17, 'echo': 27},   # Front Left
        'FC': {'trig': 22, 'echo': 23},   # Front Center
        'FR': {'trig': 24, 'echo': 25},   # Front Right
        'SL': {'trig': 12, 'echo': 13},   # Side Left
        'SR': {'trig': 16, 'echo': 18},   # Side Right
        'RL': {'trig': 20, 'echo': 21},   # Rear Left
        'RC': {'trig': 5, 'echo': 6},     # Rear Center
        'RR': {'trig': 7, 'echo': 8},     # Rear Right
    }
    
    # 위험 단계 기준 거리 (cm)
    DISTANCE_THRESHOLDS = {
        'safe': 120,      # 안전 거리 이상
        'proximity': 60,  # 근접 거리
        'danger': 30,     # 위험 거리
    }
    
    def __init__(self, use_gpio=False):
        """
        센서 배열 초기화
        
        Args:
            use_gpio: GPIO 사용 여부 (False=시뮬레이션)
        """
        self.use_gpio = use_gpio
        self.sensors = {}
        self.sensor_data = {}
        self.is_running = False
        
        self._init_sensors()
    
    def _init_sensors(self):
        """센서 초기화"""
        for sensor_id, pins in self.SENSOR_PINS.items():
            if self.use_gpio:
                self.sensors[sensor_id] = UltrasonicSensor(
                    pins['trig'], pins['echo'], sensor_id
                )
            else:
                # 시뮬레이션 모드
                self.sensors[sensor_id] = None
            
            self.sensor_data[sensor_id] = {
                'distance': 0,
                'level': 0,  # 0=감지안됨, 1=안전, 2=근접, 3=위험
            }
    
    def start(self):
        """센서 읽기 시작"""
        self.is_running = True
        thread = threading.Thread(target=self._read_loop, daemon=True)
        thread.start()
    
    def stop(self):
        """센서 읽기 중지"""
        self.is_running = False
        for sensor in self.sensors.values():
            if sensor:
                sensor.cleanup()
    
    def _read_loop(self):
        """센서 읽기 루프"""
        while self.is_running:
            for sensor_id, sensor in self.sensors.items():
                if sensor:
                    distance = sensor.measure_distance()
                    if distance is not None:
                        self.sensor_data[sensor_id]['distance'] = distance
                        self.sensor_data[sensor_id]['level'] = self._get_risk_level(distance)
            
            time.sleep(0.1)  # 100ms마다 업데이트 (REQ-005 기준)
    
    def _get_risk_level(self, distance):
        """거리를 기반으로 위험 단계 반환"""
        if distance == 0:
            return 0  # 감지 안됨
        elif distance > self.DISTANCE_THRESHOLDS['safe']:
            return 1  # 안전
        elif distance > self.DISTANCE_THRESHOLDS['proximity']:
            return 2  # 근접
        else:
            return 3  # 위험
    
    def get_sensor_data(self):
        """모든 센서 데이터 반환"""
        return self.sensor_data.copy()
    
    def get_sensor_by_id(self, sensor_id):
        """특정 센서 데이터 반환"""
        return self.sensor_data.get(sensor_id, None)
    
    def export_json(self):
        """JSON 형식으로 센서 데이터 내보내기"""
        return json.dumps(self.sensor_data, indent=2)


class VehicleState:
    """차량 상태 관리"""
    
    def __init__(self):
        self.speed = 0  # km/h
        self.gear = 'P'  # P, R, D, N
        self.collision_avoidance_enabled = True
        self.engine_running = False
        
        self.state_history = deque(maxlen=100)  # 상태 기록
    
    def update_speed(self, speed):
        """속도 업데이트"""
        self.speed = max(0, min(speed, 200))  # 0~200 범위
    
    def set_gear(self, gear):
        """기어 설정"""
        if gear in ['P', 'R', 'D', 'N']:
            self.gear = gear
        else:
            raise ValueError(f"유효하지 않은 기어: {gear}")
    
    def toggle_collision_avoidance(self):
        """충돌방지 기능 토글"""
        self.collision_avoidance_enabled = not self.collision_avoidance_enabled
    
    def get_state(self):
        """현재 상태 반환"""
        return {
            'speed': self.speed,
            'gear': self.gear,
            'collision_avoidance_enabled': self.collision_avoidance_enabled,
            'engine_running': self.engine_running,
        }
    
    def record_state(self):
        """상태 기록"""
        self.state_history.append({
            'timestamp': time.time(),
            'state': self.get_state(),
        })


class BuzzerAlert:
    """부저 경고 시스템"""
    
    ALERT_PATTERNS = {
        'proximity': {
            'frequency': 1000,  # Hz
            'pattern': [0.1, 0.1, 0.1, 0.1],  # [on, off, on, off]
        },
        'danger': {
            'frequency': 1500,
            'pattern': [0.05, 0.05, 0.05, 0.05],  # 더 빠른 속도
        },
        'critical': {
            'frequency': 2000,
            'pattern': [0.02, 0.02, 0.02, 0.02],  # 매우 빠른 속도
        },
    }
    
    def __init__(self, gpio_pin=None):
        """부저 초기화"""
        self.gpio_pin = gpio_pin
        self.is_active = False
        
        if gpio_pin:
            try:
                import RPi.GPIO as GPIO
                self.GPIO = GPIO
                self.GPIO.setmode(GPIO.BCM)
                self.GPIO.setup(gpio_pin, GPIO.OUT)
            except Exception as e:
                print(f"부저 초기화 실패: {e}")
    
    def play_alert(self, alert_type='proximity'):
        """경고음 재생"""
        if not self.gpio_pin:
            # 시뮬레이션 모드
            print(f"부저 경고: {alert_type}")
            return
        
        pattern = self.ALERT_PATTERNS.get(alert_type, {}).get('pattern', [])
        for duration in pattern:
            self.GPIO.output(self.gpio_pin, True)
            time.sleep(duration)
            self.GPIO.output(self.gpio_pin, False)
            time.sleep(duration)
    
    def stop(self):
        """부저 중지"""
        if self.gpio_pin:
            self.GPIO.output(self.gpio_pin, False)
            self.is_active = False
