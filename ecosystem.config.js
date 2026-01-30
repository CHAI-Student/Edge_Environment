/**
 * PM2 Ecosystem Configuration
 *
 * Model 서비스 전용 (v3.0 - Frame Buffer API)
 *
 * 사용법:
 *   npm run services              # model 실행
 *   npm run client                # React 클라이언트 실행
 *   npm run all                   # 전체 실행
 *   pm2 logs
 *   pm2 stop all
 *
 * 참고:
 *   - camera_driver가 _archive로 이동됨
 *   - Model이 /api/frame으로 직접 이미지를 수신
 *   - io_board, card_terminal, mqtt_client, server는 다른 레포에서 관리
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

    // Python model 서비스 (포트 8002) - AI 상품 판단 (v3.0 Frame Buffer API)
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
        // Buffer 설정
        MODEL__BUFFER__TTL_SECONDS: "30",
        MODEL__BUFFER__MAX_SESSIONS: "100",
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
        MODEL__BUFFER__TTL_SECONDS: "30",
        MODEL__BUFFER__MAX_SESSIONS: "100",
        MODEL__VISION__YOLO_MODEL_PATH: "/home/chai/Edge_Environment/models/siyeon_best.engine",
        MODEL__NODEJS_URL: "http://localhost:8888",
      },
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
    },
  ],
};
