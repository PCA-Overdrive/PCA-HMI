/* 차량 디스플레이 메인 JavaScript */

class VehicleDisplay {
    constructor() {
        this.updateInterval = 100; // 100ms마다 업데이트
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.startDataUpdates();
    }

    setupEventListeners() {
        // PDW 센서 클릭 이벤트
        document.querySelectorAll('.pdw-zone').forEach(zone => {
            zone.addEventListener('click', (e) => this.onPDWZoneClick(e));
            zone.addEventListener('mouseenter', (e) => this.onPDWZoneHover(e));
        });

        // 충돌방지 기능 클릭 (필요시)
        document.querySelector('.collision-indicator')?.addEventListener('click', () => {
            this.toggleCollisionAvoidance();
        });
    }

    startDataUpdates() {
        setInterval(() => {
            this.updateVehicleState();
            this.updatePDWData();
        }, this.updateInterval);
    }

    async updateVehicleState() {
        try {
            const response = await fetch('/api/vehicle-state');
            const data = await response.json();
            
            // 속도 업데이트
            document.querySelector('.speed-value').textContent = data.speed;
            
            // 기어 업데이트
            this.updateGearDisplay(data.gear);
            
            // 후방 카메라 활성화 여부
            this.updateCameraDisplay(data.rear_camera_active);
            
            // 충돌방지 상태 업데이트
            this.updateCollisionAvoidanceDisplay(data.collision_avoidance);
        } catch (error) {
            console.error('차량 상태 업데이트 실패:', error);
        }
    }

    updateGearDisplay(gear) {
        document.querySelectorAll('.gear-option').forEach(option => {
            const gearChar = option.textContent.trim();
            if (gearChar === gear) {
                option.classList.add('active');
            } else {
                option.classList.remove('active');
            }
        });
    }

    updateCameraDisplay(isActive) {
        const cameraContainer = document.getElementById('cameraContainer');
        const cameraStatus = document.getElementById('cameraStatus');
        const cameraFeed = document.getElementById('cameraFeed');
        
        if (isActive) {
            cameraContainer.classList.remove('inactive');
            cameraStatus.style.display = 'none';
            
            // Motion JPEG 스트림을 직접 연결 (연속 스트리밍)
            cameraFeed.src = '/api/camera-stream';
        } else {
            cameraStatus.style.display = 'block';
            cameraStatus.textContent = '카메라 대기 중...';
            cameraFeed.src = '';
            
            // 카메라 업데이트 중지
            if (this.cameraUpdateInterval) {
                clearInterval(this.cameraUpdateInterval);
                this.cameraUpdateInterval = null;
            }
        }
    }

    updateCollisionAvoidanceDisplay(isActive) {
        const statusCircle = document.querySelector('.status-circle');
        const statusText = document.querySelector('.status-text');
        
        if (isActive) {
            statusCircle.classList.remove('off');
            statusCircle.classList.add('on');
            statusText.classList.remove('off');
            statusText.textContent = 'ON';
        } else {
            statusCircle.classList.remove('on');
            statusCircle.classList.add('off');
            statusText.classList.add('off');
            statusText.textContent = 'OFF';
        }
    }

    async updatePDWData() {
        try {
            const response = await fetch('/api/pdw-data');
            const pdwData = await response.json();
            
            for (const [direction, data] of Object.entries(pdwData)) {
                this.updatePDWZone(direction, data);
            }
        } catch (error) {
            console.error('PDW 데이터 업데이트 실패:', error);
        }
    }

    updatePDWZone(direction, data) {
        const zone = document.querySelector(`[data-direction="${direction}"]`);
        if (!zone) return;
        
        // 이전 레벨 제거
        zone.classList.remove('level-0', 'level-1', 'level-2', 'level-3');
        
        // 새로운 레벨 추가
        zone.classList.add(`level-${data.level}`);
        
        // 호버시 거리 정보 표시를 위해 data 속성 저장
        zone.dataset.distance = data.distance;
        zone.dataset.level = data.level;
    }

    onPDWZoneClick(event) {
        const zone = event.currentTarget;
        const direction = zone.dataset.direction;
        const distance = zone.dataset.distance;
        const level = zone.dataset.level;
        
        const levelNames = ['감지 안됨', '안전', '근접', '위험'];
        const levelName = levelNames[level];
        
        console.log(`${direction}: ${distance}cm (${levelName})`);
        
        // 선택된 센서 정보 표시
        const distanceInfo = document.getElementById('selectedDistance');
        if (distance === '0') {
            distanceInfo.textContent = `선택된 센서: ${direction} - 감지 안됨`;
        } else {
            distanceInfo.textContent = `선택된 센서: ${direction} - ${distance}cm (${levelName})`;
        }
    }

    onPDWZoneHover(event) {
        // 호버 시 추가 시각 효과 (필요시 구현)
    }

    async toggleCollisionAvoidance() {
        try {
            const response = await fetch('/api/toggle-collision-avoidance', {
                method: 'POST'
            });
            const data = await response.json();
            this.updateCollisionAvoidanceDisplay(data.collision_avoidance);
        } catch (error) {
            console.error('충돌방지 기능 토글 실패:', error);
        }
    }
}

// 페이지 로드 시 초기화
document.addEventListener('DOMContentLoaded', () => {
    new VehicleDisplay();
});

// 추가: 시뮬레이션을 위한 키 이벤트 처리 (개발용)
document.addEventListener('keydown', (e) => {
    // 개발용 단축키
    // W: 속도 증가, S: 속도 감소
    // R: 후진, D: 전진, P: 주차
    // 필요시 추가 구현
});
