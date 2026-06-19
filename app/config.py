"""
구성 파일 - 애플리케이션 설정
"""

import os
from datetime import timedelta

class Config:
    """기본 구성"""
    
    # Flask 설정
    FLASK_ENV = os.getenv('FLASK_ENV', 'production')
    DEBUG = os.getenv('DEBUG', False)
    
    # 서버 설정
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 5000))
    THREADED = True
    
    # CORS 설정
    CORS_ALLOW_ALL = True
    
    # 세션 설정
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # 파일 업로드 설정
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB


class DevelopmentConfig(Config):
    """개발 환경 설정"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """프로덕션 환경 설정"""
    DEBUG = False
    TESTING = False


class TestingConfig(Config):
    """테스트 환경 설정"""
    TESTING = True
    DEBUG = True


class VehicleConfig:
    """차량 관련 설정"""
    
    # 차량 정보
    VEHICLE_MODEL = "Test Vehicle"
    VEHICLE_YEAR = 2024
    
    # 카메라 설정
    CAMERA_ENABLED = True
    CAMERA_SOURCE = 0  # 0=기본 카메라, 'pi'=라즈베리파이
    CAMERA_RESOLUTION = (1280, 720)
    CAMERA_FPS = 30
    CAMERA_FLIP_H = False
    CAMERA_FLIP_V = False
    
    # 센서 설정
    SENSORS_ENABLED = True
    USE_GPIO = False  # GPIO 사용 여부 (라즈베리파이)
    
    # PDW 센서 거리 기준 (cm)
    PDW_SAFE_DISTANCE = 120
    PDW_PROXIMITY_DISTANCE = 60
    PDW_DANGER_DISTANCE = 30
    
    # 부저 설정
    BUZZER_ENABLED = True
    BUZZER_GPIO_PIN = None  # 라즈베리파이 GPIO 핀 번호
    
    # 데이터 업데이트 간격
    SENSOR_UPDATE_INTERVAL = 0.1  # 100ms (REQ-005)
    DISPLAY_UPDATE_INTERVAL = 0.1  # 100ms
    
    # 속도 범위 (km/h)
    MIN_SPEED = 0
    MAX_SPEED = 200
    
    # 기어 상태
    GEARS = ['P', 'R', 'D', 'N']
    
    # 실행 모드
    SIMULATION_MODE = True  # 센서 시뮬레이션 모드
    
    # 로깅 설정
    LOG_LEVEL = 'INFO'
    LOG_FILE = 'vehicle_display.log'


class DisplayConfig:
    """디스플레이 관련 설정"""
    
    # 색상 정의
    COLORS = {
        'not_detected': '#666666',
        'safe': '#00ff00',
        'proximity': '#ffaa00',
        'danger': '#ff0000',
        'primary': '#00bfff',
        'text': '#ffffff',
        'background': '#1a1a1a',
        'warning': '#ffaa00',
        'error': '#ff0000',
    }
    
    # 폰트 설정
    FONTS = {
        'family': "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif",
        'title_size': '36px',
        'label_size': '12px',
        'value_size': '36px',
    }
    
    # 애니메이션 설정
    ANIMATIONS_ENABLED = True
    PULSE_DURATION = '1s'  # 근접 경고 애니메이션
    DANGER_PULSE_DURATION = '0.5s'  # 위험 경고 애니메이션


# 환경별 설정 선택
def get_config():
    """현재 환경에 맞는 설정 반환"""
    env = os.getenv('FLASK_ENV', 'production')
    
    if env == 'development':
        return DevelopmentConfig()
    elif env == 'testing':
        return TestingConfig()
    else:
        return ProductionConfig()
