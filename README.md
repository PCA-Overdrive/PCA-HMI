# 차량 디스플레이 웹 서버 (Vehicle Display Web Server)

라즈베리파이에서 실행하는 자동 주차 및 후진 지원 시스템 웹 인터페이스입니다.

## 프로젝트 구조

```
vehicle-display/
├── app/
│   └── main.py              # Flask 메인 애플리케이션
├── templates/
│   └── index.html           # HTML 템플릿
├── static/
│   ├── css/
│   │   └── style.css        # 스타일시트
│   ├── js/
│   │   └── main.js          # 클라이언트 JavaScript
│   └── images/              # 이미지 파일
├── requirements.txt         # Python 의존성
├── README.md               # 이 파일
└── run.sh                  # 실행 스크립트
```

## 기능

### 1. 상단 헤더
- **속도**: 현재 차량 속도 (km/h) 표시
- **기어**: P(주차), R(후진), D(주행) 상태 표시
- **충돌방지**: 충돌 방지 보조 기능 On/Off 상태 표시

### 2. 좌측 패널 - 후방 카메라
- R(후진) 기어 선택 시 후방 카메라 영상 표시
- 실시간 카메라 스트림 (Motion JPEG)

### 3. 우측 패널 - PDW (Parking Distance Warning)
- **8방향 센서 표시**:
  - 전방: FL(좌), FC(중앙), FR(우)
  - 측면: SL(좌), SR(우)
  - 후방: RL(좌), RC(중앙), RR(우)
  
- **위험도 색상 표시**:
  - 회색: 감지 안됨
  - 초록색: 안전 (120cm 이상)
  - 주황색: 근접 (60~120cm)
  - 빨강색: 위험 (60cm 이하)

- **인터랙티브 기능**:
  - 센서 클릭 시 거리 정보 표시
  - 근접/위험 단계에서 펄싱 애니메이션

## 설치 방법

### 필수 요구사항
- Python 3.7 이상
- Raspberry Pi (또는 Linux 기반 컴퓨터)

### 설치 단계

1. **저장소 클론 또는 파일 다운로드**
```bash
cd vehicle-display
```

2. **Python 의존성 설치**
```bash
pip install -r requirements.txt
```

3. **실행**
```bash
python app/main.py
```

또는 실행 스크립트 사용:
```bash
chmod +x run.sh
./run.sh
```

## 웹 접근

Flask 서버 시작 후 웹 브라우저에서 다음 URL로 접근:
```
http://localhost:5000
```

라즈베리파이의 IP 주소로 원격 접근:
```
http://<raspberry-pi-ip>:5000
```

## API 엔드포인트

### GET /api/vehicle-state
현재 차량 상태 조회
```json
{
  "speed": 0,
  "gear": "P",
  "collision_avoidance": true,
  "rear_camera_active": false
}
```

### GET /api/pdw-data
PDW 센서 데이터 조회
```json
{
  "FL": {
    "distance": 150,
    "level": 1,
    "color": "#00ff00",
    "description": "안전"
  },
  ...
}
```

### POST /api/toggle-collision-avoidance
충돌방지 기능 토글
```json
{
  "status": "success",
  "collision_avoidance": true
}
```

### GET /api/camera-stream
후방 카메라 스트림 (Motion JPEG)

## 실제 센서 연결

### 초음파 센서 (Ultrasonic Sensor)
라즈베리파이 GPIO를 통해 8개의 초음파 센서를 연결하고, `main.py`의 `simulate_sensor_data()` 함수를 실제 센서 읽기 코드로 교체합니다.

### 후방 카메라
```python
# app/camera.py에서 구현
from picamera import PiCamera
import io
import time

class CameraManager:
    def __init__(self):
        self.camera = PiCamera()
        self.camera.resolution = (1280, 720)
    
    def get_frame(self):
        stream = io.BytesIO()
        self.camera.capture(stream, format='jpeg')
        stream.seek(0)
        return stream.getvalue()
```

## 개발 및 테스트

### 시뮬레이션 모드
현재 코드는 시뮬레이션 모드로 동작하므로 실제 센서나 카메라 없이도 테스트 가능합니다.

### 클라이언트 테스트
```bash
# 다른 터미널에서
curl http://localhost:5000/api/vehicle-state
curl http://localhost:5000/api/pdw-data
```

## 주의사항

1. **라즈베리파이 환경**:
   - GPIO 권한 설정 필요
   - 카메라 활성화 필수 (raspi-config)

2. **성능 최적화**:
   - 업데이트 간격: 100ms (조정 가능)
   - 카메라 프레임 레이트: 30fps

3. **보안**:
   - 프로덕션 환경에서는 HTTPS 사용 권장
   - 인증 메커니즘 추가 권장

## 카스터마이징

### 센서 거리 기준 변경
`main.py`의 `update_pdw_levels()` 함수에서 거리 기준 수정:
```python
elif distance > 120:  # 안전 거리 임계값
    pdw_data[direction]['level'] = 1
elif distance > 60:   # 근접 거리 임계값
    pdw_data[direction]['level'] = 2
```

### UI 색상 변경
`static/css/style.css`에서 색상 코드 수정:
```css
.pdw-zone.level-1 circle { fill: #00ff00; } /* 안전 색상 */
.pdw-zone.level-2 circle { fill: #ffaa00; } /* 근접 색상 */
.pdw-zone.level-3 circle { fill: #ff0000; } /* 위험 색상 */
```

## 기술 스택

- **Backend**: Flask (Python)
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Communication**: RESTful API, CORS
- **Styling**: 차량 디스플레이 스타일 (Modern Dark Theme)

## 라이센스

MIT License

## 문의 및 지원

문제가 발생하면 다음을 확인하세요:
1. Python 버전 확인: `python --version`
2. 의존성 설치 확인: `pip list`
3. 포트 사용 여부 확인: `lsof -i :5000`
4. 브라우저 개발자 콘솔 확인: F12

## 향후 기능

- [ ] WebSocket을 통한 실시간 양방향 통신
- [ ] 부저 경고 시스템 통합
- [ ] 스마트폰 앱 연동
- [ ] 주차 기록 저장 및 재생
- [ ] AI 기반 장애물 감지 개선
