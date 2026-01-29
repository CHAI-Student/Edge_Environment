/**
 * PM2 Ecosystem Configuration
 *
 * Edge_Environment + Python 마이크로서비스 통합 관리
 *
 * 사용법:
 *   pm2 start ecosystem.config.js
 *   pm2 start ecosystem.config.js --only orchestrator
 *   pm2 logs
 *   pm2 stop all
 *
 * 모든 Python 서비스는 통일된 구조를 사용합니다:
 *   - main.py: PM2 래퍼 (runpy로 src/main.py 실행)
 *   - src/: 실제 서비스 코드
 *   - src/core/config.py: Pydantic BaseSettings (env_prefix 패턴)
 *
 * 환경변수 패턴:
 *   {SERVICE_NAME}__{SECTION}__{FIELD}
 *   예: IO_BOARD__API__PORT, MODEL__VISION__YOLO_MODEL_PATH
 */

module.exports = {
  apps: [
    // Node.js Orchestrator (기존 Express 서버)
    {
      name: "orchestrator",
      script: "./server/index.js",
      cwd: __dirname,
      env: {
        NODE_ENV: "development",
      },
      env_production: {
        NODE_ENV: "production",
      },
      watch: false,
      instances: 1,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 1000,
    },

    // React Client (포트 3000) - 프론트엔드 웹 애플리케이션
    {
      name: "client",
      cwd: "./client",
      script: "npm",
      args: "start",
      interpreter: "none",
      env: {
        BROWSER: "none",
        PORT: "3000",
      },
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
    },

    // Python io_board 서비스 (포트 8000) - CRK-IO-BOARD
    {
      name: "io-board",
      cwd: "./services/io_board",
      script: "python",
      args: "main.py",
      interpreter: "none",
      env: {
        PYTHONUNBUFFERED: "1",
        // API 설정
        IO_BOARD__API__HOST: "0.0.0.0",
        IO_BOARD__API__PORT: "8000",
        IO_BOARD__API__LOG_LEVEL: "info",
        // 시리얼 설정 (Windows: COM3, Linux/Jetson: /dev/ttyUSB0)
        // IO_BOARD__SERIAL__PORT: "COM3",
        // IO_BOARD__SERIAL__BAUDRATE: "38400",
        // 폴링 설정
        IO_BOARD__POLLING__LOADCELLS_POLL_INTERVAL: "0.1",
        IO_BOARD__POLLING__IO_STATUS_POLL_INTERVAL: "0.5",
      },
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
    },

    // Python card_terminal 서비스 (포트 8001/5001) - 결제 터미널
    {
      name: "card-terminal",
      cwd: "./services/card_terminal",
      script: "python",
      args: "main.py",
      interpreter: "none",
      env: {
        PYTHONUNBUFFERED: "1",
        // API 설정
        CARD_TERMINAL__API__HOST: "0.0.0.0",
        CARD_TERMINAL__API__PORT: "8001",
        CARD_TERMINAL__API__LOG_LEVEL: "info",
        // CAT 디바이스 설정
        CARD_TERMINAL__CAT__HOST: "0.0.0.0",
        CARD_TERMINAL__CAT__PORT: "5001",
        // 타임아웃 설정
        CARD_TERMINAL__COMM_TIMEOUT: "30.0",
        CARD_TERMINAL__SHUTDOWN_TIMEOUT: "10.0",
      },
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
    },

    // Python model 서비스 (포트 8002) - AI 상품 판단
    {
      name: "model",
      cwd: "./services/model",
      script: "python",
      args: "main.py",
      interpreter: "none",
      env: {
        PYTHONUNBUFFERED: "1",
        // API 설정
        MODEL__API__HOST: "0.0.0.0",
        MODEL__API__PORT: "8002",
        MODEL__API__LOG_LEVEL: "info",
        // Vision 설정 (상대 경로 사용 - 자동 fallback 지원)
        // Windows 개발: models/siyeon_best.pt
        // Jetson 배포: models/siyeon_best.engine (CUDA 감지 시 자동 사용)
        MODEL__VISION__YOLO_MODEL_PATH: "models/siyeon_best.pt",
        // Node.js 연동
        MODEL__NODEJS_URL: "http://localhost:8889",
      },
      // Jetson 배포 환경 (pm2 start ecosystem.config.js --env production)
      env_production: {
        PYTHONUNBUFFERED: "1",
        MODEL__API__HOST: "0.0.0.0",
        MODEL__API__PORT: "8002",
        MODEL__API__LOG_LEVEL: "info",
        // Jetson: TensorRT 엔진 사용 (절대 경로 또는 상대 경로)
        MODEL__VISION__YOLO_MODEL_PATH: "models/siyeon_best.engine",
        MODEL__NODEJS_URL: "http://localhost:8889",
      },
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
    },

    // Python camera_driver 서비스 (포트 8003) - 6대 카메라 관리
    {
      name: "camera-driver",
      cwd: "./services/camera_driver",
      script: "python",
      args: "main.py",
      interpreter: "none",
      env: {
        PYTHONUNBUFFERED: "1",
        // API 설정
        CAMERA__API_HOST: "0.0.0.0",
        CAMERA__API_PORT: "8003",
        // 카메라 설정
        CAMERA__NVIDIA_MODE: "true",
        CAMERA__RESOLUTION_WIDTH: "640",
        CAMERA__RESOLUTION_HEIGHT: "480",
        CAMERA__FPS: "30",
        // 서비스 연동
        CAMERA__IO_BOARD_URL: "http://localhost:8000",
        CAMERA__NODEJS_CALLBACK_URL: "http://localhost:8889",
      },
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
    },

    // Python mqtt_client 서비스 (포트 8006) - MQTT IF04 프로토콜
    {
      name: "mqtt-client",
      cwd: "./services/mqtt_client",
      script: "python",
      args: "main.py",
      interpreter: "none",
      env: {
        PYTHONUNBUFFERED: "1",
        // API 설정
        MQTT__API_HOST: "0.0.0.0",
        MQTT__API_PORT: "8006",
        // MQTT 브로커 설정
        MQTT__MQTT_BROKER_HOST: "localhost",
        MQTT__MQTT_BROKER_PORT: "1883",
        // 디바이스 식별자
        MQTT__DIVISION_IDX: "DIV001",
        MQTT__DEVICE_IDX: "DEV001",
      },
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
    },
  ],
};
