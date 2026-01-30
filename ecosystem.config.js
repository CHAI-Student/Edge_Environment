/**
 * PM2 Ecosystem Configuration
 *
 * Camera Driver + Model 서비스 전용 (경량화 버전)
 *
 * 사용법:
 *   npm run services              # camera-driver + model 실행
 *   npm run client                # React 클라이언트 실행
 *   npm run all                   # 전체 실행
 *   pm2 logs
 *   pm2 stop all
 *
 * 참고: io_board, card_terminal, mqtt_client, server는
 *       다른 레포(Edge_Environment)에서 관리됩니다.
 *       아카이빙된 파일: _archive/
 *
 * 환경변수 패턴:
 *   {SERVICE_NAME}__{SECTION}__{FIELD}
 *   예: MODEL__VISION__YOLO_MODEL_PATH
 */

module.exports = {
  apps: [
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

    // Python model 서비스 (포트 8002) - AI 상품 판단
    {
      name: "model",
      cwd: "./services/model",
      script: "main.py",
      interpreter: "python",
      env: {
        PYTHONUNBUFFERED: "1",
        // API 설정
        MODEL__API__HOST: "0.0.0.0",
        MODEL__API__PORT: "8002",
        MODEL__API__LOG_LEVEL: "info",
        // Vision 설정
        // MODEL__VISION__YOLO_MODEL_PATH: "./models/siyeon_best.pt",
        // Node.js 연동 (다른 레포)
        MODEL__NODEJS_URL: "http://localhost:8888",
      },
      env_production: {
        PYTHONUNBUFFERED: "1",
        MODEL__API__HOST: "0.0.0.0",
        MODEL__API__PORT: "8002",
        MODEL__API__LOG_LEVEL: "info",
        MODEL__VISION__YOLO_MODEL_PATH: "/home/chai/Edge_Environment/models/siyeon_best.engine",
        MODEL__NODEJS_URL: "http://localhost:8888",
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
      script: "main.py",
      interpreter: "python",
      env: {
        PYTHONUNBUFFERED: "1",
        // API 설정
        CAMERA__API_HOST: "0.0.0.0",
        CAMERA__API_PORT: "8003",
        // 카메라 설정
        CAMERA__NVIDIA_MODE: "false",
        CAMERA__RESOLUTION_WIDTH: "640",
        CAMERA__RESOLUTION_HEIGHT: "480",
        CAMERA__FPS: "30",
        // 서비스 연동 (다른 레포)
        CAMERA__IO_BOARD_URL: "http://localhost:8000",
        CAMERA__NODEJS_CALLBACK_URL: "http://localhost:8888",
      },
      env_production: {
        PYTHONUNBUFFERED: "1",
        CAMERA__API_HOST: "0.0.0.0",
        CAMERA__API_PORT: "8003",
        CAMERA__NVIDIA_MODE: "true",
        CAMERA__RESOLUTION_WIDTH: "640",
        CAMERA__RESOLUTION_HEIGHT: "480",
        CAMERA__FPS: "30",
        CAMERA__IO_BOARD_URL: "http://localhost:8000",
        CAMERA__NODEJS_CALLBACK_URL: "http://localhost:8888",
      },
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
    },
  ],
};
