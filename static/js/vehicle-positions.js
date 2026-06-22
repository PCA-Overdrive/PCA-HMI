/**
 * 차량 센서 위치 정의
 * 차량 상단뷰 기준 센서 좌표 (픽셀 단위, 컨테이너 기준 %)
 */

const VEHICLE_SENSOR_POSITIONS = {
  // 전방 센서 (Front)
  FL: {
    x: 20, // 좌측
    y: 9.7, // 상단
    label: "FL",
  },
  FC: {
    x: 50, // 중앙
    y: 4.2, // 상단
    label: "FC",
  },
  FR: {
    x: 80, // 우측
    y: 9.7, // 상단
    label: "FR",
  },

  // 측면 센서 (Side)
  SL: {
    x: 8, // 좌측
    y: 50, // 중앙
    label: "SL",
  },
  SR: {
    x: 92, // 우측
    y: 50, // 중앙
    label: "SR",
  },

  // 후방 센서 (Rear)
  RL: {
    x: 20, // 좌측
    y: 90.3, // 하단
    label: "RL",
  },
  RC: {
    x: 50, // 중앙
    y: 95.8, // 하단
    label: "RC",
  },
  RR: {
    x: 80, // 우측
    y: 90.3, // 하단
    label: "RR",
  },
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
    label: pos.label,
  };
}

/**
 * 모든 센서 위치 업데이트
 */
function updateSensorPositions() {
  const container = document.querySelector(".vehicle-overlay-container");
  if (!container) return;

  const width = container.offsetWidth;
  const height = container.offsetHeight;

  Object.entries(VEHICLE_SENSOR_POSITIONS).forEach(([sensorId]) => {
    const pixelPos = getSensorPixelPosition(sensorId, width, height);
    if (!pixelPos) return;

    // SVG 요소 업데이트
    const circle = document.querySelector(
      `.pdw-zone[data-direction="${sensorId}"] circle`,
    );
    const rect = document.querySelector(
      `.pdw-zone[data-direction="${sensorId}"] rect`,
    );
    const text = document.querySelector(
      `.pdw-zone[data-direction="${sensorId}"] text`,
    );
    const svgX = pixelPos.x / (width / 400);
    const svgY = pixelPos.y / (height / 500);

    if (circle) {
      circle.setAttribute("cx", svgX);
      circle.setAttribute("cy", svgY);
    }
    if (rect) {
      const rectWidth = Number(rect.getAttribute("width")) || 64;
      const rectHeight = Number(rect.getAttribute("height")) || 44;
      const rotation = Number(rect.dataset.rotation) || 0;
      rect.setAttribute("x", svgX - rectWidth / 2);
      rect.setAttribute("y", svgY - rectHeight / 2);
      rect.setAttribute("transform", `rotate(${rotation} ${svgX} ${svgY})`);
    }
    if (text) {
      text.setAttribute("x", svgX);
      text.setAttribute("y", svgY + 5);
    }
  });
}

// 윈도우 리사이즈 시 센서 위치 업데이트
window.addEventListener("resize", updateSensorPositions);
document.addEventListener("DOMContentLoaded", updateSensorPositions);
