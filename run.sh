#!/bin/bash

# 차량 디스플레이 웹 서버 실행 스크립트

echo "======================================"
echo "차량 디스플레이 웹 서버 시작"
echo "======================================"

# Python 버전 확인
echo "Python 버전 확인..."
python3 --version

# 가상 환경 설정 (선택사항)
if [ -d "venv" ]; then
    echo "가상 환경 활성화..."
    source venv/bin/activate
fi

# 의존성 설치
echo "의존성 설치 중..."
pip install -r requirements.txt

# Flask 앱 실행
echo "Flask 서버 시작 중..."
echo "웹 접근: http://localhost:5000"
echo "라즈베리파이 접근: http://<raspberry-pi-ip>:5000"
echo ""
echo "종료하려면 Ctrl+C 입력"
echo "======================================"
echo ""

python3 app/main.py
