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

    // Python io_board 서비스 (포트 8001)
    {
      name: "io-board",
      cwd: "./services/io_board",
      script: "python",
      args: "main.py",
      interpreter: "none",
      env: {
        PYTHONUNBUFFERED: "1",
      },
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
    },

    // Python card_terminal 서비스 (포트 5000)
    {
      name: "card-terminal",
      cwd: "./services/card_terminal",
      script: "python",
      args: "main.py",
      interpreter: "none",
      env: {
        PYTHONUNBUFFERED: "1",
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
      args: "-m uvicorn main:app --host 0.0.0.0 --port 8002",
      interpreter: "none",
      env: {
        PYTHONUNBUFFERED: "1",
        YOLO_MODEL_PATH: "../../../siyeon_best.pt",
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
      args: "-m uvicorn main:app --host 0.0.0.0 --port 8003",
      interpreter: "none",
      env: {
        PYTHONUNBUFFERED: "1",
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
      args: "-m uvicorn main:app --host 0.0.0.0 --port 8006",
      interpreter: "none",
      env: {
        PYTHONUNBUFFERED: "1",
      },
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 2000,
    },
  ],
};
