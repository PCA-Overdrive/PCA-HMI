"""
빠른 시작 가이드 - Quick Start
"""

# ============================================
# 1단계: 설치 (Installation)
# ============================================

# 1.1 저장소 복제 또는 파일 다운로드
cd vehicle-display

# 1.2 Python 3.7 이상 버전 확인
python3 --version

# 1.3 필수 패키지 설치
pip install -r requirements.txt

# ============================================
# 2단계: 구성 설정 (Configuration)
# ============================================

# 2.1 환경 파일 생성
cp .env.example .env

# 2.2 필요한 경우 .env 파일 수정
# - CAMERA_SOURCE: 카메라 선택 (0=기본, 'pi'=라즈베리파이)
# - USE_GPIO: GPIO 사용 여부 (False=시뮬레이션, True=실제 센서)
# - SIMULATION_MODE: True=시뮬레이션, False=실제 데이터

# ============================================
# 3단계: 실행 (Run)
# ============================================

# 방법 1: 직접 실행
python3 app/main.py

# 방법 2: 실행 스크립트 사용
bash run.sh

# ============================================
# 4단계: 접근 (Access)
# ============================================

# 로컬 머신에서:
# http://localhost:5000

# 라즈베리파이 IP로 접근:
# http://<raspberry-pi-ip>:5000
# 예: http://192.168.1.100:5000

# ============================================
# 5단계: 테스트 (Testing)
# ============================================

# API 테스트
curl http://localhost:5000/api/vehicle-state
curl http://localhost:5000/api/pdw-data

# 단위 테스트 실행
python3 test_app.py

# ============================================
# 실제 센서 연결 (실제 구현)
# ============================================

# 1. 라즈베리파이 GPIO 설정
sudo raspi-config
# - Interface Options > Camera: Enable
# - Interface Options > I2C/SPI: Enable (필요시)

# 2. RPi.GPIO 패키지 설치 (라즈베리파이 환경)
pip install RPi.GPIO
pip install picamera

# 3. .env 파일 수정
# USE_GPIO=True
# SIMULATION_MODE=False
# BUZZER_GPIO_PIN=26 (부저 GPIO 핸들러)

# 4. GPIO 권한 설정
sudo usermod -a -G gpio $USER

# ============================================
# 문제 해결 (Troubleshooting)
# ============================================

# 포트 이미 사용 중
# 해결: 포트 번호 변경
# .env 파일에서 PORT=5001로 변경

# 모듈 없음 에러
# 해결: 의존성 재설치
pip install --upgrade -r requirements.txt

# GPIO 오류
# 해결: 관리자 권한 실행
sudo python3 app/main.py

# 카메라 오류
# 해결: 카메라 활성화 확인
# raspi-config > Interface Options > Camera: Enable

# ============================================
# 개발 팁 (Development Tips)
# ============================================

# 실시간 로그 보기
tail -f logs/app.log

# 디버그 모드 활성화
FLASK_ENV=development python3 app/main.py

# 성능 모니터링
python3 -c "from test_app import run_performance_test; run_performance_test()"

# ============================================
# 배포 (Deployment)
# ============================================

# Systemd 서비스 생성 (자동 시작)
sudo nano /etc/systemd/system/vehicle-display.service

# 다음 내용 입력:
"""
[Unit]
Description=Vehicle Display Web Server
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/vehicle-display
Environment="FLASK_ENV=production"
ExecStart=/usr/bin/python3 app/main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
"""

# 서비스 활성화 및 시작
sudo systemctl daemon-reload
sudo systemctl enable vehicle-display
sudo systemctl start vehicle-display

# 서비스 상태 확인
sudo systemctl status vehicle-display

# ============================================
# Nginx 리버스 프록시 설정 (선택사항)
# ============================================

# Nginx 설치
sudo apt-get install nginx

# 설정 파일 생성
sudo nano /etc/nginx/sites-available/vehicle-display

# 다음 내용 입력:
"""
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
"""

# 심볼릭 링크 생성
sudo ln -s /etc/nginx/sites-available/vehicle-display /etc/nginx/sites-enabled/

# Nginx 재시작
sudo systemctl restart nginx

# ============================================
# SSL/HTTPS 설정 (선택사항)
# ============================================

# Let's Encrypt Certbot 설치
sudo apt-get install certbot python3-certbot-nginx

# 인증서 발급
sudo certbot certonly --nginx -d yourdomain.com

# Nginx 설정에 SSL 추가
listen 443 ssl http2;
ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
