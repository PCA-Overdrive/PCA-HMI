# PCA-HMI

PCA-HMI는 PCA(Parking Collision Avoidance) 프로젝트에서 운전자에게 차량 상태를 보여주고, Android 앱에서 들어온 자동출차 명령을 판단 ECU로 전달하는 HMI 서버입니다.

Flask 기반 웹 HMI가 속도, 기어, PCA 상태, PDW(Parking Distance Warning), 후방 카메라, 주차선 인식 결과를 실시간으로 표시합니다. 동시에 Bluetooth SPP로 Android 앱의 자동출차 명령을 수신하고, CAN을 통해 판단 ECU와 차량 제어 정보를 주고받습니다.

## 핵심 역할

- 차량 상태 표시: 속도, 기어, PCA ON/OFF, Emergency Stop, 출차 상태
- PDW 표시: CAN `0x400`에서 수신한 10방향 장애물 레벨을 HMI에 표시
- 후방 카메라 표시: R 기어 상태에서 MJPEG 후방 카메라 스트림 활성화
- 후방 가이드라인: 조향 입력을 기반으로 후방 주차 가이드라인 표시
- 주차선 인식: OpenCV로 주차선 후보를 검출하고 각도를 CAN `0x201`에 반영
- Android 연동: Bluetooth SPP로 자동출차 명령을 받고 CAN `0x300`으로 ECU에 전달
- ECU 상태 회신: CAN `0x401` 출차 상태를 Android 앱으로 다시 전송
- 조이스틱 연동: 속도, 조향, 기어, PCA 토글 입력을 CAN 제어 명령으로 변환

## 전체 구조

```text
[Android App]
    |
    | Bluetooth SPP
    v
[app/bluetooth_spp.py] -- auto parking command --> [app/can_controller.py]
                                                        |
[Joystick] --------------------------------------------+---- CAN TX 0x201 / 0x300
                                                        |
[Judgment ECU] -- CAN RX 0x400 / 0x401 -----------------+
                                                        |
[Camera] --> [app/camera.py] --> [app/parking_line_detector.py]
                                                        |
                                                        v
                                                [app/main.py]
                                                    Flask API
                                                        |
                                                        v
                              [templates/index.html + static/js + static/css]
                                                   Web HMI
```

## 데이터 흐름

1. 판단 ECU가 CAN `0x400`으로 PDW 레벨, PCA 상태, 속도, 기어, Emergency Stop 상태를 송신합니다.
2. `VehicleCanController`가 CAN RX 데이터를 읽고 Flask 서버의 차량 상태와 PDW 데이터를 갱신합니다.
3. 웹 HMI는 `/api/vehicle-state`, `/api/pdw-data`를 100ms 주기로 조회해 화면을 갱신합니다.
4. Android 앱이 Bluetooth SPP로 `STRAIGHT_EXIT`, `LEFT_EXIT` 같은 자동출차 명령을 보냅니다.
5. `BluetoothSppServer`가 명령을 정수 코드로 변환하고 `VehicleCanController`가 CAN `0x300`으로 판단 ECU에 전달합니다.
6. 판단 ECU가 CAN `0x401`로 출차 진행/완료/취소 상태를 보내면 서버가 Android 앱으로 `EXIT_IN_PROGRESS`, `EXIT_DONE`, `EXIT_CANCELED` 메시지를 회신합니다.
7. 카메라 프레임에서 주차선 각도를 계산하고, 계산된 각도는 CAN `0x201`의 `LineAngleCmd`에 포함됩니다.

## 프로젝트 구조

```text
PCA-HMI/
├── app/
│   ├── main.py                   # Flask 서버, API, 전체 상태 관리
│   ├── can_controller.py         # CAN RX/TX, 조이스틱, 부저, 제어 명령 처리
│   ├── can_interface.py          # CAN 프레임 파싱/더미 프레임 유틸리티
│   ├── bluetooth_spp.py          # Android Bluetooth SPP 명령 수신/상태 송신
│   ├── camera.py                 # 카메라 캡처, MJPEG 스트림, 주차선 각도 갱신
│   ├── parking_line_detector.py  # OpenCV 기반 주차선 후보 검출
│   ├── sensors.py                # 센서 관련 유틸리티
│   └── utils.py                  # 공통 유틸리티
├── templates/
│   └── index.html                # HMI 화면 템플릿
├── static/
│   ├── css/style.css             # HMI 스타일
│   ├── js/main.js                # 화면 갱신, PDW, 카메라, 가이드라인 제어
│   ├── js/vehicle-positions.js   # 차량/PDW 위치 보정
│   └── images/                   # 차량 이미지, 카메라 대체 이미지
├── test_app.py                   # API, CAN 파서, 주차선 검출 테스트
├── vehicle.env                   # 기본 실행 환경 변수
├── requirements.txt              # Python 의존성
├── requirements-bluetooth.txt    # Bluetooth 관련 안내
├── run_windows.ps1               # Windows 실행 스크립트
├── run_raspberry_pi.sh           # Raspberry Pi 실행 스크립트
└── run.sh                        # Linux 간단 실행 스크립트
```

## 실행 환경

- Python 3.7 이상
- Flask, Flask-CORS
- OpenCV, NumPy
- python-can
- pygame 또는 Linux joystick device
- Raspberry Pi GPIO 사용 시 `RPi.GPIO`, `gpiozero`, `pinctrl` 중 사용 가능한 방식
- CAN 사용 시 Linux SocketCAN 환경
- Bluetooth SPP 사용 시 RFCOMM을 지원하는 Linux/Raspberry Pi 환경

## 설치

```bash
pip install -r requirements.txt
```

Bluetooth SPP는 Raspberry Pi/Linux의 내장 Bluetooth RFCOMM socket을 우선 사용합니다. 별도 pip 패키지가 필요한 구조는 아니며, 자세한 내용은 `requirements-bluetooth.txt`를 참고합니다.

## 실행

### Windows 개발 환경

```powershell
.\run_windows.ps1
```

`run_windows.ps1`는 `.venv-windows` 가상환경을 만들고 `requirements.txt`를 설치한 뒤 Flask 서버를 실행합니다.

### Raspberry Pi

```bash
chmod +x run_raspberry_pi.sh
./run_raspberry_pi.sh
```

`run_raspberry_pi.sh`는 `vehicle.env`를 로드하고, 가상환경을 준비한 뒤 CAN 설정을 시도합니다. `CAN_ENABLED=True`이고 `can0`가 존재하면 CAN FD/bitrate/txqueuelen 설정까지 수행합니다.

### Linux 간단 실행

```bash
chmod +x run.sh
./run.sh
```

### 직접 실행

```bash
python app/main.py
```

서버 실행 후 브라우저에서 접속합니다.

```text
http://localhost:5000
http://<raspberry-pi-ip>:5000
```

## 환경 변수

기본 설정은 `vehicle.env`에서 관리합니다. 필요하면 실행 전에 값을 수정하거나 `ENV_FILE`로 다른 env 파일을 지정할 수 있습니다.

```env
# Flask
FLASK_ENV=production
DEBUG=False
HOST=0.0.0.0
PORT=5000

# Camera
CAMERA_SOURCE=0
LANE_DETECTION_ENABLED=True
LANE_DETECTION_INTERVAL=0.1
LANE_ANGLE_UPDATE_INTERVAL=0.05

# CAN / controller
CAN_ENABLED=True
CAN_CHANNEL=can0
CAN_INTERFACE=socketcan
CAN_FD=True
CAN_TX_201_INTERVAL=0.012
CAN_TX_300_INTERVAL=0.1
CONTROLLER_ENABLED=True
CONTROLLER_GUIDE_MAX_ANGLE=60
CONTROLLER_STEER_INVERT=True

# Bluetooth SPP
BLUETOOTH_ENABLED=True
BLUETOOTH_BIND_ADDRESS=00:00:00:00:00:00
BLUETOOTH_RFCOMM_CHANNEL=1
BLUETOOTH_RESTART_DELAY=2

# Buzzer
BUZZER_ENABLED=True
BUZZER_GPIO_PIN=18

# Runtime
SIMULATION_MODE=False
```

개발 PC에서 CAN이나 카메라 없이 UI만 확인하려면 다음처럼 설정합니다.

```env
CAN_ENABLED=False
SIMULATION_MODE=True
CAMERA_SOURCE=-1
BLUETOOTH_ENABLED=False
BUZZER_ENABLED=False
```

## CAN 명세

### CAN RX

| CAN ID | 이름 | 길이 | 설명 |
| --- | --- | ---: | --- |
| `0x400` | `DistanceLevelCmd` | 14 bytes 이상 | PDW 10방향 레벨, PCA 상태, 속도, 기어, Emergency Stop |
| `0x401` | `ExitCompleteCmd` | 1 byte 이상 | 자동출차 진행/완료/취소 상태 |

### CAN `0x400` payload

| Byte | 의미 |
| ---: | --- |
| B0 | Front |
| B1 | Front Right |
| B2 | Right Front |
| B3 | Right Behind |
| B4 | Behind Right |
| B5 | Behind |
| B6 | Behind Left |
| B7 | Left Behind |
| B8 | Left Front |
| B9 | Front Left |
| B10 | PCA state |
| B11 | Vehicle speed |
| B12 | Gear status (`0=P`, `1=D`, `2=R`, `3=N`) |
| B13 | Emergency Stop |

PDW 레벨은 `0=감지 없음`, `1=안전`, `2=주의`, `3=근접`, `4=위험`으로 표시합니다.

### CAN `0x401` payload

| 값 | 의미 | Android 회신 메시지 |
| ---: | --- | --- |
| `0x01` | 출차 진행 중 | `EXIT_IN_PROGRESS` |
| `0x02` | 출차 완료 | `EXIT_DONE` |
| `0x03` | 출차 취소 | `EXIT_CANCELED` |

`0x401` 상태가 `2` 또는 `3`이면 서버는 다음 `0x300` 자동출차 명령 값을 `0`으로 초기화합니다.

### CAN TX

| CAN ID | 이름 | 주기 | 설명 |
| --- | --- | ---: | --- |
| `0x201` | Vehicle control/status command | 기본 12ms | 속도 명령, 조향 명령, 기어, PCA ON/OFF, 주차선 각도 |
| `0x300` | Auto parking command | 기본 100ms | Android 앱에서 받은 자동출차 명령 |

### CAN `0x201` payload

| Byte | 의미 |
| ---: | --- |
| B0 | Speed command |
| B1 | Steer command |
| B2 | Gear command |
| B3 | PCA enabled |
| B4-B5 | Line angle command, little-endian signed int16 |

### CAN `0x300` payload

| Byte | 의미 |
| ---: | --- |
| B0 | Auto parking command |

## Bluetooth SPP 명령

Android 앱은 RFCOMM 채널로 줄바꿈(`\n`) 단위 텍스트 명령을 전송합니다.

| Android 명령 | CAN `0x300` 값 | 의미 |
| --- | ---: | --- |
| `NORMAL` | `0` | 일반 상태 |
| `NORMAL_EXIT` | `0` | 일반 출차 |
| `STRAIGHT_EXIT` | `1` | 직진 출차 |
| `LEFT_EXIT` | `2` | 좌측 출차 |
| `RIGHT_EXIT` | `3` | 우측 출차 |
| `CANCEL_EXIT` | `4` | 출차 취소 |

ECU에서 CAN `0x401` 상태가 들어오면 Android 앱으로 다음 메시지를 전송합니다.

```text
EXIT_IN_PROGRESS
EXIT_DONE
EXIT_CANCELED
```

## API

### `GET /api/vehicle-state`

현재 차량 상태와 조향 정보를 반환합니다.

```json
{
  "speed": 0,
  "gear": "P",
  "collision_avoidance": true,
  "rear_camera_active": false,
  "emergency_stop": false,
  "emergency_stop_activated": false,
  "exit_status": 0,
  "can_last_rx_id": 1024,
  "can_last_rx_at": 1710000000.0,
  "steer_cmd": 127,
  "steer_axis": 0.0,
  "steering_angle": 0
}
```

### `GET /api/pdw-data`

PDW 10방향 데이터를 반환합니다. API 필드명은 CAN 신호명 기준입니다.

```json
{
  "FrontLevelCmd": {
    "distance": 150,
    "level": 1,
    "raw_level": 1,
    "color": "#00ff00",
    "description": "안전"
  }
}
```

### `GET /api/camera-stream`

후방 카메라 MJPEG 스트림을 반환합니다. 카메라가 없으면 대체 이미지로 연결됩니다.

### `GET /api/camera-frame`

현재 카메라 프레임 1장을 JPEG로 반환합니다.

### `GET /api/parking-line-debug-stream`

주차선 검출 결과를 오버레이한 MJPEG 디버그 스트림을 반환합니다.

### `GET /api/parking-line-debug-frame`

주차선 검출 결과를 오버레이한 JPEG 1장을 반환합니다.

### `GET /api/parking-line-angle`

현재 주차선 검출 결과와 각도를 반환합니다.

```json
{
  "detected": true,
  "line_count": 2,
  "best_score": 0.82,
  "candidate_type": "white_component",
  "y_axis_angle_deg": -12.4,
  "line_angle_cmd": -12,
  "timestamp": 1710000000.0
}
```

### `POST /api/toggle-collision-avoidance`

PCA 기능 ON/OFF 명령을 토글합니다. CAN 컨트롤러가 활성화되어 있으면 다음 CAN `0x201` 송신에 반영됩니다.

```json
{
  "status": "success",
  "collision_avoidance": true
}
```

## 주차선 인식 로직

주차선 인식은 OpenCV 기반으로 동작합니다. 단순히 화면의 모든 선을 잡는 것이 아니라, 밝은 흰색 영역과 선형 후보를 단계적으로 필터링합니다.

1. 카메라 프레임을 HSV 색공간으로 변환합니다.
2. 흰색에 가까운 영역만 마스크로 추출합니다.
3. 주차선이 주로 나타나는 화면 하단 영역만 ROI로 사용합니다.
4. Morphology 연산으로 작은 노이즈를 제거합니다.
5. Connected Component와 Hough Line으로 후보 선을 찾습니다.
6. 길이, 두께 대비, 각도, 점수를 기준으로 반사광과 큰 흰색 덩어리를 제외합니다.
7. 가장 점수가 높은 후보의 각도를 주차선 기준 각도로 선택합니다.
8. 선택된 각도는 `/api/parking-line-angle`에 표시되고 CAN `0x201`의 `LineAngleCmd`로 전달됩니다.

디버깅이 필요하면 다음 엔드포인트를 브라우저에서 확인합니다.

```text
http://localhost:5000/api/parking-line-debug-stream
http://localhost:5000/api/parking-line-angle
```

## 조이스틱 입력

`CONTROLLER_ENABLED=True`이면 서버가 pygame joystick 또는 Linux `/dev/input/js*` 장치를 탐색합니다.

| 입력 | 역할 |
| --- | --- |
| Axis 1 | Speed command |
| Axis 2 | Steer command |
| Button 0 | P gear |
| Button 1 | D gear |
| Button 3 | R gear |
| Button 4 | PCA toggle |

Emergency Stop 상태이거나 P 기어인 경우 속도/조향 명령은 중립값 `127`로 제한됩니다.

## 개발 및 테스트

API 동작 확인:

```bash
curl http://localhost:5000/api/vehicle-state
curl http://localhost:5000/api/pdw-data
curl http://localhost:5000/api/parking-line-angle
```

테스트 실행:

```bash
python test_app.py
```

문법 확인:

```bash
python -m py_compile app/main.py app/can_controller.py app/camera.py app/parking_line_detector.py app/bluetooth_spp.py app/can_interface.py
```

Git 커밋 메시지는 문서 수정이므로 다음 형식을 사용합니다.

```text
chore: README 문서 정리
```

## 문제 해결

### 화면은 뜨지만 CAN 데이터가 갱신되지 않는 경우

- `vehicle.env`의 `CAN_ENABLED`, `CAN_CHANNEL`, `CAN_INTERFACE`, `CAN_FD` 값을 확인합니다.
- Raspberry Pi/Linux에서 `ip -details link show can0`로 CAN 인터페이스 상태를 확인합니다.
- UI만 확인할 때는 `CAN_ENABLED=False`, `SIMULATION_MODE=True`로 실행합니다.

### Bluetooth SPP 연결이 되지 않는 경우

- `BLUETOOTH_ENABLED=True`인지 확인합니다.
- Android 앱이 같은 RFCOMM channel을 사용하는지 확인합니다.
- Linux/Raspberry Pi 환경에서 Bluetooth socket 또는 RFCOMM 지원이 가능한지 확인합니다.
- 서버 로그에서 `Waiting for Android connection on RFCOMM channel 1` 메시지를 확인합니다.

### 카메라가 열리지 않는 경우

- `CAMERA_SOURCE` 값을 확인합니다. 기본 USB 카메라는 `0`, 비활성화는 `-1`, PiCamera는 `pi`를 사용합니다.
- Windows에서는 필요 시 `CAMERA_BACKEND=DSHOW` 또는 `CAMERA_BACKEND=MSMF`를 지정합니다.
- OpenCV가 카메라를 열지 못하면 HMI에는 대체 이미지가 표시됩니다.

### 주차선이 너무 많이 검출되는 경우

`app/parking_line_detector.py`의 다음 파라미터를 조정합니다.

- `white_value_threshold`
- `max_white_saturation`
- `roi_top_ratio`
- `min_candidate_score`
- `max_reference_line_angle`
- `min_component_aspect_ratio`
- `max_component_area_ratio`

반사광이 강한 환경에서는 ROI를 더 아래로 제한하거나 후보 점수 기준을 높이는 것이 효과적입니다.

### 부저가 동작하지 않는 경우

- `BUZZER_ENABLED=True`와 `BUZZER_GPIO_PIN` 값을 확인합니다.
- Raspberry Pi에서 GPIO 권한과 `RPi.GPIO`, `gpiozero`, `pinctrl` 설치 여부를 확인합니다.
- `BUZZER_GPIO_PIN`은 BCM GPIO 번호 기준입니다.

## 기술 스택

- Backend: Python, Flask, Flask-CORS
- Frontend: HTML, CSS, Vanilla JavaScript
- Vision: OpenCV, NumPy
- Vehicle I/O: python-can, SocketCAN
- Controller: pygame, Linux joystick device
- Hardware: Raspberry Pi GPIO, gpiozero/RPi.GPIO/pinctrl
- Communication: REST API, MJPEG Stream, Bluetooth SPP, CAN
