/* 차량 디스플레이 메인 JavaScript */

class VehicleDisplay {
  constructor() {
    this.updateInterval = 100; // 100ms마다 업데이트
    this.cameraActive = false;
    this.lastGuideAngle = null;
    this.cameraFallbackSrc = "/static/images/CAMERA_NOT_FUN.png";
    this.autoStopWarningActive = false;
    this.autoStopPopupTimeout = null;
    this.init();
  }

  init() {
    this.setupEventListeners();
    this.startDataUpdates();
  }

  setupEventListeners() {
    // 충돌방지 기능 클릭 (필요시)
    document
      .querySelector(".collision-indicator")
      ?.addEventListener("click", () => {
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
      const response = await fetch("/api/vehicle-state");
      const data = await response.json();

      // 속도 업데이트
      document.querySelector(".speed-value").textContent = data.speed;

      // 기어 업데이트
      this.updateGearDisplay(data.gear);

      // 후방 카메라 활성화 여부
      this.updateCameraDisplay(data.rear_camera_active, data.camera_available);
      this.updateRearGuidelines(
        data.rear_camera_active,
        data.steering_angle || 0,
      );

      // 충돌방지 상태 업데이트
      this.updateCollisionAvoidanceDisplay(data.collision_avoidance);
    } catch (error) {
      console.error("차량 상태 업데이트 실패:", error);
    }
  }

  updateGearDisplay(gear) {
    document.querySelectorAll(".gear-option").forEach((option) => {
      const gearChar = option.textContent.trim();
      if (gearChar === gear) {
        option.classList.add("active");
      } else {
        option.classList.remove("active");
      }
    });
  }

  updateCameraDisplay(isActive, isCameraAvailable) {
    const cameraContainer = document.getElementById("cameraContainer");
    const cameraStatus = document.getElementById("cameraStatus");
    const cameraFeed = document.getElementById("cameraFeed");
    cameraFeed.onerror = () => {
      cameraFeed.onerror = null;
      cameraFeed.src = this.cameraFallbackSrc;
      cameraStatus.style.display = "block";
      cameraStatus.textContent = "카메라 연결 안됨";
    };

    if (isActive && isCameraAvailable) {
      cameraContainer.classList.remove("inactive");
      cameraStatus.style.display = "none";

      // Motion JPEG 스트림을 직접 연결 (연속 스트리밍)
      if (
        !this.cameraActive ||
        cameraFeed.getAttribute("src") !== "/api/camera-stream"
      ) {
        cameraFeed.src = "/api/camera-stream";
      }
    } else {
      cameraContainer.classList.remove("inactive");
      cameraStatus.style.display = "block";
      cameraStatus.textContent = isActive ? "카메라 연결 안됨" : "카메라 대기 중...";
      if (cameraFeed.getAttribute("src") !== this.cameraFallbackSrc) {
        cameraFeed.src = this.cameraFallbackSrc;
      }

      // 카메라 업데이트 중지
      if (this.cameraUpdateInterval) {
        clearInterval(this.cameraUpdateInterval);
        this.cameraUpdateInterval = null;
      }
    }

    this.cameraActive = isActive;
  }

  updateRearGuidelines(isActive, steeringAngle) {
    const overlay = document.getElementById("rearGuideOverlay");
    const guideLines = document.getElementById("rearGuideLines");
    if (!overlay || !guideLines) return;

    const normalizedAngle = this.clamp(Number(steeringAngle) || 0, -20, 20);
    if (!isActive) {
      overlay.classList.remove("active");
      this.lastGuideAngle = null;
      return;
    }

    overlay.classList.add("active");
    if (
      this.lastGuideAngle === normalizedAngle &&
      guideLines.childElementCount > 0
    ) {
      return;
    }

    this.lastGuideAngle = normalizedAngle;
    guideLines.replaceChildren();

    const turnShift = (normalizedAngle / 20) * 170;
    const leftBottom = { x: 250, y: 590 };
    const rightBottom = { x: 750, y: 590 };
    const leftTop = { x: 405 + turnShift, y: 70 };
    const rightTop = { x: 595 + turnShift, y: 70 };

    const segments = [
      { className: "danger", from: 0.02, to: 0.28 },
      { className: "warning", from: 0.33, to: 0.62 },
      { className: "safe", from: 0.68, to: 0.96 },
    ];

    segments.forEach((segment) => {
      guideLines.appendChild(
        this.createGuideSegment(leftBottom, leftTop, segment),
      );
      guideLines.appendChild(
        this.createGuideSegment(rightBottom, rightTop, segment),
      );
    });

    [
      { className: "danger", at: 0.18, length: 120 },
      { className: "warning", at: 0.5, length: 100 },
      { className: "safe", at: 0.83, length: 80 },
    ].forEach((tick) => {
      guideLines.appendChild(
        this.createGuideTick(leftBottom, leftTop, tick, 1),
      );
      guideLines.appendChild(
        this.createGuideTick(rightBottom, rightTop, tick, -1),
      );
    });
  }

  createGuideSegment(bottom, top, segment) {
    const start = this.pointOnLine(bottom, top, segment.from);
    const end = this.pointOnLine(bottom, top, segment.to);
    const path = this.createSvgElement("path");
    path.setAttribute("class", `rear-guide-line ${segment.className}`);
    path.setAttribute("d", `M ${start.x} ${start.y} L ${end.x} ${end.y}`);
    return path;
  }

  createGuideTick(bottom, top, tick, direction) {
    const start = this.pointOnLine(bottom, top, tick.at);
    const line = this.createSvgElement("line");
    line.setAttribute("class", `rear-guide-tick ${tick.className}`);
    line.setAttribute("x1", start.x);
    line.setAttribute("y1", start.y);
    line.setAttribute("x2", start.x + tick.length * direction);
    line.setAttribute("y2", start.y);
    return line;
  }

  pointOnLine(bottom, top, ratio) {
    return {
      x: bottom.x + (top.x - bottom.x) * ratio,
      y: bottom.y + (top.y - bottom.y) * ratio,
    };
  }

  createSvgElement(tagName) {
    return document.createElementNS("http://www.w3.org/2000/svg", tagName);
  }

  clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  updateCollisionAvoidanceDisplay(isActive) {
    const statusCircle = document.querySelector(".status-circle");
    const statusText = document.querySelector(".status-text");

    if (isActive) {
      statusCircle.classList.remove("off");
      statusCircle.classList.add("on");
      statusText.classList.remove("off");
      statusText.textContent = "ON";
    } else {
      statusCircle.classList.remove("on");
      statusCircle.classList.add("off");
      statusText.classList.add("off");
      statusText.textContent = "OFF";
    }
  }

  async updatePDWData() {
    try {
      const response = await fetch("/api/pdw-data");
      const pdwData = await response.json();
      const hasDangerLevel = Object.values(pdwData).some(
        (data) => data.level === 3,
      );

      for (const [direction, data] of Object.entries(pdwData)) {
        this.updatePDWZone(direction, data);
      }
      this.handleAutoStopWarning(hasDangerLevel);
    } catch (error) {
      console.error("PDW 데이터 업데이트 실패:", error);
    }
  }

  handleAutoStopWarning(hasDangerLevel) {
    if (!hasDangerLevel) {
      this.autoStopWarningActive = false;
      return;
    }

    if (this.autoStopWarningActive) return;

    this.autoStopWarningActive = true;
    this.showAutoStopPopup();
  }

  showAutoStopPopup() {
    let popup = document.querySelector(".auto-stop-popup");
    if (!popup) {
      popup = document.createElement("div");
      popup.className = "auto-stop-popup";
      popup.setAttribute("role", "alert");
      popup.textContent = "위험 ! 자동 정차합니다.";
      document.body.appendChild(popup);
    }

    popup.classList.add("visible");

    if (this.autoStopPopupTimeout) {
      clearTimeout(this.autoStopPopupTimeout);
    }

    this.autoStopPopupTimeout = setTimeout(() => {
      popup.classList.remove("visible");
    }, 2000);
  }

  updatePDWZone(direction, data) {
    const zone = document.querySelector(`[data-direction="${direction}"]`);
    if (!zone) return;

    // 이전 레벨 제거
    zone.classList.remove("level-0", "level-1", "level-2", "level-3");

    // 새로운 레벨 추가
    zone.classList.add(`level-${data.level}`);

    zone.dataset.level = data.level;
  }

  async toggleCollisionAvoidance() {
    try {
      const response = await fetch("/api/toggle-collision-avoidance", {
        method: "POST",
      });
      const data = await response.json();
      this.updateCollisionAvoidanceDisplay(data.collision_avoidance);
    } catch (error) {
      console.error("충돌방지 기능 토글 실패:", error);
    }
  }
}

// 페이지 로드 시 초기화
document.addEventListener("DOMContentLoaded", () => {
  new VehicleDisplay();
});

// 추가: 시뮬레이션을 위한 키 이벤트 처리 (개발용)
document.addEventListener("keydown", (e) => {
  // 개발용 단축키
  // W: 속도 증가, S: 속도 감소
  // R: 후진, D: 전진, P: 주차
  // 필요시 추가 구현
});
