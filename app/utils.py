"""
로깅 및 유틸리티 모듈
"""

import logging
import logging.handlers
import os
from datetime import datetime

class Logger:
    """로깅 관리 클래스"""
    
    _instance = None
    _loggers = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.log_dir = 'logs'
        
        # 로그 디렉토리 생성
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
    
    def get_logger(self, name, level=logging.INFO):
        """로거 인스턴스 반환"""
        if name in self._loggers:
            return self._loggers[name]
        
        logger = logging.getLogger(name)
        logger.setLevel(level)
        
        # 파일 핸들러
        log_file = os.path.join(self.log_dir, f'{name}.log')
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10485760,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(level)
        
        # 콘솔 핸들러
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # 포매터
        formatter = logging.Formatter(
            '[%(asctime)s] %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # 핸들러 추가
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        self._loggers[name] = logger
        return logger


def get_logger(name):
    """로거 반환"""
    return Logger().get_logger(name)


class DataBuffer:
    """원형 버퍼를 이용한 데이터 저장"""
    
    def __init__(self, size=100):
        self.size = size
        self.buffer = []
        self.index = 0
    
    def append(self, data):
        """데이터 추가"""
        if len(self.buffer) < self.size:
            self.buffer.append(data)
        else:
            self.buffer[self.index] = data
        
        self.index = (self.index + 1) % self.size
    
    def get_all(self):
        """모든 데이터 반환"""
        return self.buffer.copy()
    
    def get_last(self, count=10):
        """최근 데이터 반환"""
        return self.buffer[-count:]
    
    def clear(self):
        """버퍼 초기화"""
        self.buffer.clear()
        self.index = 0


class TimeoutHandler:
    """타임아웃 처리"""
    
    @staticmethod
    def set_timeout(func, timeout_seconds):
        """타임아웃 설정"""
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError(f'{timeout_seconds}초 초과')
        
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout_seconds)
        
        try:
            result = func()
            signal.alarm(0)  # 타임아웃 취소
            return result
        except TimeoutError as e:
            print(f"타임아웃: {e}")
            return None


class RollingAverage:
    """이동 평균 계산"""
    
    def __init__(self, window_size=10):
        self.window_size = window_size
        self.values = []
    
    def add(self, value):
        """값 추가"""
        self.values.append(value)
        if len(self.values) > self.window_size:
            self.values.pop(0)
    
    def average(self):
        """평균 반환"""
        if not self.values:
            return 0
        return sum(self.values) / len(self.values)
    
    def clear(self):
        """초기화"""
        self.values.clear()


class PerformanceMonitor:
    """성능 모니터링"""
    
    def __init__(self):
        self.metrics = {}
        self.logger = get_logger('performance')
    
    def record_execution_time(self, name, duration):
        """실행 시간 기록"""
        if name not in self.metrics:
            self.metrics[name] = {
                'count': 0,
                'total_time': 0,
                'min_time': float('inf'),
                'max_time': 0,
            }
        
        metric = self.metrics[name]
        metric['count'] += 1
        metric['total_time'] += duration
        metric['min_time'] = min(metric['min_time'], duration)
        metric['max_time'] = max(metric['max_time'], duration)
    
    def get_average_time(self, name):
        """평균 실행 시간 반환"""
        if name not in self.metrics:
            return 0
        metric = self.metrics[name]
        return metric['total_time'] / metric['count']
    
    def print_report(self):
        """성능 리포트 출력"""
        self.logger.info("=== 성능 리포트 ===")
        for name, metric in self.metrics.items():
            avg_time = metric['total_time'] / metric['count']
            self.logger.info(
                f"{name}: count={metric['count']}, "
                f"avg={avg_time:.4f}s, min={metric['min_time']:.4f}s, "
                f"max={metric['max_time']:.4f}s"
            )
