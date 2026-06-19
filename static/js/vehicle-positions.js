/**
 * 차량 센서 위치 정의
 * 차량 상단뷰 기준 센서 좌표 (픽셀 단위, 컨테이너 기준 %)
 */

const VEHICLE_SENSOR_POSITIONS = {
    // 전방 센서 (Front)
    'FL': {
        x: 25,      // 좌측
        y: 8,       // 상단
        label: 'FL'
    },
    'FC': {
        x: 50,      // 중앙
        y: 5,       // 상단
        label: 'FC'
    },
    'FR': {
        x: 75,      // 우측
        y: 8,       // 상단
        label: 'FR'
    },
    
    // 측면 센서 (Side)
    'SL': {
        x: 8,       // 좌측
        y: 40,      // 중앙
        label: 'SL'
    },
    'SR': {
        x: 92,      // 우측
        y: 40,      // 중앙
        label: 'SR'
    },
    
    // 후방 센서 (Rear)
    'RL': {
        x: 25,      // 좌측
        y: 92,      // 하단
        label: 'RL'
    },
    'RC': {
        x: 50,      // 중앙
        y: 95,      // 하단
        label: 'RC'
    },
    'RR': {
        x: 75,      // 우측
        y: 92,      // 하단
        label: 'RR'
    }
};

/**
 * 센서 위치를 픽셀 좌표로 변환
 * @param {string} sensorId - 센서 ID (FL, FC 등)
 * @param {number} containerWidth - 컨테이너 너비
 * @param {number} containerHeight - 컨테이너 높이
 * @returns {Object} {x, y} 픽셀 좌표
 */
function getSensorPixelPosition(sensorId, containerWidth, containerHeight) {
    const pos = VEHICLE_SENSOR_POSITIONS[sensorId];
    if (!pos) return null;
    
    return {
        x: (containerWidth * pos.x) / 100,
        y: (containerHeight * pos.y) / 100,
        label: pos.label
    };
}

/**
 * 모든 센서 위치 업데이트
 */
function updateSensorPositions() {
    const container = document.querySelector('.vehicle-overlay-container');
    if (!container) return;
    
    const width = container.offsetWidth;
    const height = container.offsetHeight;
    
    Object.entries(VEHICLE_SENSOR_POSITIONS).forEach(([sensorId, pos]) => {
        const pixelPos = getSensorPixelPosition(sensorId, width, height);
        if (!pixelPos) return;
        
        // SVG 요소 업데이트
        const circle = document.querySelector(`.pdw-zone[data-direction="${sensorId}"] circle`);
        const text = document.querySelector(`.pdw-zone[data-direction="${sensorId}"] text`);
        
        if (circle) {
            circle.setAttribute('cx', pixelPos.x / (width / 400)); // SVG viewBox 기준으로 변환
            circle.setAttribute('cy', pixelPos.y / (height / 500));
        }
        if (text) {
            text.setAttribute('x', pixelPos.x / (width / 400));
            text.setAttribute('y', (pixelPos.y / (height / 500)) + 5);
        }
    });
}

// 윈도우 리사이즈 시 센서 위치 업데이트
window.addEventListener('resize', updateSensorPositions);
document.addEventListener('DOMContentLoaded', updateSensorPositions);
