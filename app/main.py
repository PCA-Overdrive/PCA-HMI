"""
Vehicle Display Web Server
라즈베리파이 차량 제어 및 센서 데이터 표시 웹 서버
"""

from flask import Flask, redirect, render_template, jsonify, request, url_for
from flask_cors import CORS
import os
import threading
import time
from datetime import datetime
import json
from camera import CameraManager, CameraStreamGenerator

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
CORS(app)

RELOAD_WATCH_FILES = (
    'css/style.css',
    'js/main.js',
    'js/vehicle-positions.js',
)

def get_asset_version(filename):
    path = os.path.join(app.static_folder, filename)
    return int(os.path.getmtime(path)) if os.path.exists(path) else int(time.time())

def get_reload_version():
    return max(get_asset_version(filename) for filename in RELOAD_WATCH_FILES)

@app.context_processor
def static_asset_helpers():
    def static_url(filename):
        return url_for('static', filename=filename, v=get_asset_version(filename))

    return {'static_url': static_url}

@app.after_request
def disable_static_cache(response):
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# 카메라 관리자 초기화 (C920 웹캠 사용)
# 해상도를 낮춰서 프레임레이트 향상
camera_manager = CameraManager(source=0, resolution=(640, 480), fps=60)
camera_manager.start()
camera_stream_generator = CameraStreamGenerator(camera_manager)

# 차량 상태 데이터
vehicle_state = {
    'speed': 0,  # km/h
    'gear': 'P',  # P, R, D
    'steering_angle': 0,  # 조향각 (-20~20도)
    'collision_avoidance': True,  # 충돌방지 기능 On/Off
    'rear_camera_active': False,  # 후방 카메라 활성화 여부
}

# PDW (Parking Distance Warning) 센서 데이터 (8개 방향)
pdw_data = {
    'FL': {'distance': 150, 'level': 0},  # Front Left
    'FC': {'distance': 200, 'level': 0},  # Front Center
    'FR': {'distance': 150, 'level': 0},  # Front Right
    'SL': {'distance': 100, 'level': 1},  # Side Left
    'SR': {'distance': 120, 'level': 0},  # Side Right
    'RL': {'distance': 80, 'level': 2},   # Rear Left
    'RC': {'distance': 60, 'level': 3},   # Rear Center
    'RR': {'distance': 90, 'level': 1},   # Rear Right
}

# 위험 단계: 0=감지안됨, 1=안전, 2=근접, 3=위험
RISK_LEVELS = {
    0: {'name': 'not_detected', 'color': '#666666', 'description': '감지 안됨'},
    1: {'name': 'safe', 'color': '#00ff00', 'description': '안전'},
    2: {'name': 'proximity', 'color': '#ffaa00', 'description': '근접'},
    3: {'name': 'danger', 'color': '#ff0000', 'description': '위험'},
}

def update_pdw_levels():
    """거리를 기반으로 PDW 위험 단계 업데이트 (거리 기준은 임의 설정)"""
    for direction in pdw_data:
        distance = pdw_data[direction]['distance']
        if distance == 0:
            pdw_data[direction]['level'] = 0  # 감지안됨
        elif distance > 120:
            pdw_data[direction]['level'] = 1  # 안전
        elif distance > 60:
            pdw_data[direction]['level'] = 2  # 근접
        else:
            pdw_data[direction]['level'] = 3  # 위험

def simulate_sensor_data():
    """센서 데이터 시뮬레이션 (실제로는 GPIO/센서에서 읽음)"""
    global vehicle_state, pdw_data
    
    # 차량 상태 시뮬레이션
    speeds = [0, 10, 20, 30, 0, 0, 0, 20, 0]
    gears = ['R', 'R', 'R', 'R', 'R', 'R', 'R', 'R', 'R']  # R단 고정 (카메라 테스트용)
    steering_angles = [-20, -10, 0, 10, 20, 10, 0, -10, -20]
    
    cycle = 0
    while True:
        idx = cycle % len(speeds)
        vehicle_state['speed'] = speeds[idx]
        vehicle_state['gear'] = gears[idx]
        vehicle_state['steering_angle'] = steering_angles[idx]
        vehicle_state['rear_camera_active'] = (gears[idx] == 'R')
        
        # PDW 데이터 시뮬레이션 (실제는 센서에서)
        import random
        for direction in pdw_data:
            if random.random() > 0.3:
                pdw_data[direction]['distance'] = random.randint(30, 200)
            else:
                pdw_data[direction]['distance'] = 0
        
        update_pdw_levels()
        
        cycle += 1
        time.sleep(0.5)  # 0.5초마다 업데이트

@app.route('/')
def index():
    """메인 페이지"""
    return render_template('index.html')

@app.route('/api/vehicle-state', methods=['GET'])
def get_vehicle_state():
    """현재 차량 상태 조회"""
    return jsonify({
        'speed': vehicle_state['speed'],
        'gear': vehicle_state['gear'],
        'steering_angle': vehicle_state['steering_angle'],
        'collision_avoidance': vehicle_state['collision_avoidance'],
        'rear_camera_active': vehicle_state['rear_camera_active'],
        'camera_available': camera_manager.get_frame() is not None,
    })

@app.route('/api/pdw-data', methods=['GET'])
def get_pdw_data():
    """PDW 센서 데이터 조회"""
    pdw_with_levels = {}
    for direction, data in pdw_data.items():
        level = data['level']
        pdw_with_levels[direction] = {
            'distance': data['distance'],
            'level': level,
            'color': RISK_LEVELS[level]['color'],
            'description': RISK_LEVELS[level]['description'],
        }
    return jsonify(pdw_with_levels)

@app.route('/api/static-version', methods=['GET'])
def get_static_version():
    """Return a changing version for frontend assets."""
    return jsonify({'version': get_reload_version()})

@app.route('/api/camera-stream')
def camera_stream():
    """후방 카메라 스트림 (Motion JPEG)
    C920 웹캠에서 실시간 스트림 제공
    """
    if camera_manager.get_frame() is None:
        return redirect(url_for('static', filename='images/CAMERA_NOT_FUN.png'))

    def generate():
        for frame in camera_stream_generator.generate():
            yield frame
    
    return app.response_class(
        generate(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/api/camera-frame')
def camera_frame():
    """단일 카메라 프레임을 JPEG로 반환"""
    frame = camera_manager.get_mjpeg_frame()
    if frame:
        response = app.make_response(frame)
        response.headers['Content-Type'] = 'image/jpeg'
        response.headers['Content-Length'] = len(frame)
        return response
    else:
        # 카메라를 사용할 수 없을 때 기본 이미지 반환
        return jsonify({'error': 'Camera not available'}), 503

@app.route('/api/toggle-collision-avoidance', methods=['POST'])
def toggle_collision_avoidance():
    """충돌방지 기능 토글"""
    vehicle_state['collision_avoidance'] = not vehicle_state['collision_avoidance']
    return jsonify({'status': 'success', 'collision_avoidance': vehicle_state['collision_avoidance']})

def simulate_sensor_data():
    """Simulation data updates for display testing."""
    global vehicle_state, pdw_data

    gears = ['P', 'R', 'D']
    steering_angles = [-20, -10, 0, 10, 20, 10, 0, -10, -20]
    level_distances = {
        0: 0,
        1: 150,
        2: 90,
        3: 40,
    }
    started_at = time.monotonic()

    while True:
        elapsed = time.monotonic() - started_at
        sensor_level = int(elapsed // 3) % 4
        gear = gears[int(elapsed // 10) % len(gears)]
        steering_angle = steering_angles[int(elapsed // 3) % len(steering_angles)]
        is_auto_stopped = sensor_level == 3

        for direction in pdw_data:
            pdw_data[direction]['distance'] = level_distances[sensor_level]
            pdw_data[direction]['level'] = sensor_level

        vehicle_state['speed'] = 0 if is_auto_stopped or gear == 'P' else 10
        vehicle_state['gear'] = gear
        vehicle_state['steering_angle'] = steering_angle
        vehicle_state['rear_camera_active'] = (gear == 'R')

        time.sleep(0.1)

if __name__ == '__main__':
    # 센서 데이터 시뮬레이션 스레드 시작
    sensor_thread = threading.Thread(target=simulate_sensor_data, daemon=True)
    sensor_thread.start()
    
    # Flask 서버 시작 (라즈베리파이의 모든 인터페이스에서 접근 가능)
    app.run(host='0.0.0.0', port=5000, debug=False)
