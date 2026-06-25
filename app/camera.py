"""
카메라 모듈 - 라즈베리파이 카메라 또는 USB 카메라 관리
"""

import threading
import time
from io import BytesIO

try:
    import cv2
    import numpy as np
except Exception as exc:
    cv2 = None
    np = None
    print(f"OpenCV/Numpy import failed. Camera is disabled: {exc}")

class CameraManager:
    """카메라 스트림 관리 클래스"""
    
    def __init__(self, source=0, resolution=(1280, 720), fps=30):
        """
        카메라 초기화
        
        Args:
            source: 카메라 소스 (0=기본 카메라, 'pi'=라즈베리파이)
            resolution: 해상도 (width, height)
            fps: 프레임 레이트
        """
        self.source = source
        self.resolution = resolution
        self.fps = fps
        self.frame = None
        self.is_running = False
        self.lock = threading.Lock()
        self.jpeg_quality = 80  # JPEG 품질 (0-100, 낮을수록 빠름)
        
        try:
            if source == 'pi':
                self._init_pi_camera()
            else:
                self._init_opencv_camera()
        except Exception as e:
            print(f"카메라 초기화 실패: {e}")
            self.camera = None
    
    def _init_pi_camera(self):
        """라즈베리파이 카메라 초기화"""
        try:
            from picamera import PiCamera
            self.camera = PiCamera()
            self.camera.resolution = self.resolution
            self.camera.framerate = self.fps
            print(f"라즈베리파이 카메라 초기화 완료: {self.resolution} @ {self.fps}fps")
        except ImportError:
            print("picamera 모듈이 설치되지 않았습니다.")
            self.camera = None
    
    def _init_opencv_camera(self):
        """OpenCV를 통한 USB/기본 카메라 초기화"""
        if cv2 is None:
            raise RuntimeError("OpenCV is not available")

        self.camera = cv2.VideoCapture(self.source)
        
        # 기본 카메라 설정
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        self.camera.set(cv2.CAP_PROP_FPS, self.fps)
        
        # 버퍼 최소화 (낮은 지연시간)
        try:
            self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except:
            pass  # 속성을 지원하지 않으면 무시
        
        print(f"OpenCV 카메라 초기화 완료: {self.resolution} @ {self.fps}fps")
    
    def start(self):
        """카메라 스트림 시작"""
        if self.camera is None:
            print("카메라가 초기화되지 않았습니다.")
            return False
        
        self.is_running = True
        thread = threading.Thread(target=self._capture_frames, daemon=True)
        thread.start()
        return True
    
    def stop(self):
        """카메라 스트림 중지"""
        self.is_running = False
        if self.camera:
            if hasattr(self.camera, 'close'):
                self.camera.close()
            else:
                self.camera.release()
    
    def _capture_frames(self):
        """프레임 캡처 루프"""
        while self.is_running:
            try:
                if hasattr(self.camera, 'capture'):
                    # 라즈베리파이 카메라
                    stream = BytesIO()
                    self.camera.capture(stream, format='jpeg')
                    stream.seek(0)
                    with self.lock:
                        self.frame = stream.getvalue()
                else:
                    # OpenCV 카메라
                    ret, frame = self.camera.read()
                    if ret:
                        # JPEG 품질 설정으로 인코딩 속도 향상
                        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 
                                       getattr(self, 'jpeg_quality', 80)]
                        _, jpeg = cv2.imencode('.jpg', frame, encode_param)
                        with self.lock:
                            self.frame = jpeg.tobytes()
                
                # FPS 조절
                time.sleep(1.0 / self.fps)
            except Exception as e:
                print(f"프레임 캡처 오류: {e}")
    
    def get_frame(self):
        """현재 프레임 반환"""
        with self.lock:
            return self.frame
    
    def get_mjpeg_frame(self):
        """MJPEG 형식의 프레임 반환"""
        frame = self.get_frame()
        if frame is None:
            # 기본 이미지 반환
            return self._get_placeholder_frame()
        return frame
    
    def _get_placeholder_frame(self):
        """플레이스홀더 프레임 생성"""
        if cv2 is None or np is None:
            return None

        img = np.zeros((self.resolution[1], self.resolution[0], 3), dtype=np.uint8)
        cv2.putText(img, 'Camera Not Available', (50, 100), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        _, jpeg = cv2.imencode('.jpg', img)
        return jpeg.tobytes()


class CameraStreamGenerator:
    """MJPEG 스트림 생성기"""
    
    def __init__(self, camera_manager):
        self.camera = camera_manager
    
    def generate(self):
        """MJPEG 스트림 생성"""
        while True:
            frame = self.camera.get_mjpeg_frame()
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + str(len(frame)).encode() + b'\r\n\r\n' +
                       frame + b'\r\n')
            time.sleep(1.0 / self.camera.fps)
