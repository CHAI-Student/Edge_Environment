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

    // Python product_judge 서비스 (포트 8002)
    {
      name: "product-judge",
      cwd: "./services/product_judge",
      script: "python",
      args: "-m uvicorn product_judge.main:app --host 0.0.0.0 --port 8002",
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
