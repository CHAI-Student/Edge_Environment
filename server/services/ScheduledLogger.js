/**
 * ScheduledLogger - 1분 주기 로깅 서비스
 *
 * 기능:
 * - 전체 카메라 스냅샷 저장
 * - 시스템 상태 로그 저장
 * - 무게 변화 로그 저장
 * - 판단 결과 로그 저장
 */

const fs = require('fs').promises;
const path = require('path');
const axios = require('axios');
const config = require('../config/key');

const CAMERA_URL = config.cameraDriverUrl || 'http://localhost:8003';
const IO_BOARD_URL = config.ioBoardUrl || 'http://localhost:8001';
const MODEL_URL = config.modelUrl || 'http://localhost:8002';

class ScheduledLogger {
    constructor() {
        this.logsDir = path.join(process.cwd(), 'logs');
        this.intervalId = null;
        this.logInterval = 60000; // 1분

        // 메모리 내 최근 로그 (빠른 조회용)
        this.recentWeightLogs = [];
        this.recentSystemLogs = [];
        this.recentJudgmentLogs = [];
        this.maxRecentLogs = 100;
    }

    /**
     * 로깅 시작
     */
    async start() {
        // 로그 디렉토리 생성
        await this._ensureDirectories();

        console.log('[ScheduledLogger] Starting 1-minute logging...');

        // 즉시 한 번 실행
        await this._runScheduledTasks();

        // 1분마다 실행
        this.intervalId = setInterval(async () => {
            await this._runScheduledTasks();
        }, this.logInterval);
    }

    /**
     * 로깅 중지
     */
    stop() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
            console.log('[ScheduledLogger] Stopped');
        }
    }

    /**
     * 로그 디렉토리 구조 생성
     */
    async _ensureDirectories() {
        const dirs = [
            this.logsDir,
            path.join(this.logsDir, 'weight'),
            path.join(this.logsDir, 'camera'),
            path.join(this.logsDir, 'system'),
            path.join(this.logsDir, 'judgment')
        ];

        for (const dir of dirs) {
            try {
                await fs.mkdir(dir, { recursive: true });
            } catch (error) {
                if (error.code !== 'EEXIST') {
                    console.error(`[ScheduledLogger] Failed to create directory ${dir}:`, error.message);
                }
            }
        }
    }

    /**
     * 스케줄된 작업 실행
     */
    async _runScheduledTasks() {
        const timestamp = new Date();
        const dateStr = this._formatDate(timestamp);
        const timeStr = this._formatTime(timestamp);

        console.log(`[ScheduledLogger] Running scheduled tasks at ${timestamp.toISOString()}`);

        // 병렬로 실행
        await Promise.all([
            this._captureAllCameras(dateStr, timeStr).catch(e =>
                console.error('[ScheduledLogger] Camera capture failed:', e.message)
            ),
            this._logSystemState(dateStr, timestamp).catch(e =>
                console.error('[ScheduledLogger] System log failed:', e.message)
            )
        ]);
    }

    /**
     * 전체 카메라 스냅샷 캡처
     */
    async _captureAllCameras(dateStr, timeStr) {
        try {
            // 카메라 상태 조회
            const statusResponse = await axios.get(`${CAMERA_URL}/api/status`, { timeout: 5000 });
            const cameras = statusResponse.data.cameras || {};

            // 스냅샷 저장 디렉토리
            const snapshotDir = path.join(this.logsDir, 'camera', dateStr, timeStr);
            await fs.mkdir(snapshotDir, { recursive: true });

            // 각 카메라별 캡처 (현재 활성화된 카메라만)
            const capturePromises = [];

            for (const [camId, camInfo] of Object.entries(cameras)) {
                capturePromises.push(
                    this._captureCamera(camId, snapshotDir)
                        .catch(e => console.warn(`[ScheduledLogger] Camera ${camId} capture failed:`, e.message))
                );
            }

            await Promise.all(capturePromises);
            console.log(`[ScheduledLogger] Camera snapshots saved to ${snapshotDir}`);

        } catch (error) {
            // 카메라 서비스 연결 실패는 경고만
            if (error.code === 'ECONNREFUSED') {
                console.warn('[ScheduledLogger] Camera service not available');
            } else {
                throw error;
            }
        }
    }

    /**
     * 개별 카메라 캡처
     */
    async _captureCamera(cameraId, outputDir) {
        try {
            // Try JSON endpoint first (returns base64)
            const response = await axios.get(
                `${CAMERA_URL}/api/camera/${cameraId}/frame`,
                { timeout: 10000 }
            );

            const filename = `cam_${cameraId}.jpg`;
            const filepath = path.join(outputDir, filename);

            if (response.data && response.data.frame) {
                // Base64 encoded image
                const imageBuffer = Buffer.from(response.data.frame, 'base64');
                await fs.writeFile(filepath, imageBuffer);
                return true;
            }

            return false;
        } catch (error) {
            // Fallback: try raw JPEG endpoint
            try {
                const response = await axios.get(
                    `${CAMERA_URL}/frame/${cameraId}`,
                    { timeout: 10000, responseType: 'arraybuffer' }
                );

                const filename = `cam_${cameraId}.jpg`;
                const filepath = path.join(outputDir, filename);
                await fs.writeFile(filepath, response.data);
                return true;
            } catch (e) {
                return false;
            }
        }
    }

    /**
     * 시스템 상태 로그
     */
    async _logSystemState(dateStr, timestamp) {
        const logFile = path.join(this.logsDir, 'system', `${dateStr}.jsonl`);

        // 각 서비스 상태 수집
        const [ioBoardHealth, cameraHealth, modelHealth] = await Promise.all([
            this._checkHealth(`${IO_BOARD_URL}/health`),
            this._checkHealth(`${CAMERA_URL}/api/health`),
            this._checkHealth(`${MODEL_URL}/api/health`)
        ]);

        // 로드셀 값 조회
        let loadcells = null;
        try {
            const response = await axios.get(`${IO_BOARD_URL}/loadcells`, { timeout: 5000 });
            loadcells = response.data.loadcells;
        } catch (error) {
            // 무시
        }

        // 문 상태 조회
        let doorStatus = null;
        try {
            const response = await axios.get(`${IO_BOARD_URL}/status`, { timeout: 5000 });
            doorStatus = {
                door: response.data.door,
                deadbolt: response.data.deadbolt
            };
        } catch (error) {
            // 무시
        }

        const logEntry = {
            timestamp: timestamp.toISOString(),
            services: {
                io_board: ioBoardHealth,
                camera: cameraHealth,
                model: modelHealth
            },
            loadcells,
            door: doorStatus,
            memory: process.memoryUsage(),
            uptime: process.uptime()
        };

        // 파일에 추가
        await fs.appendFile(logFile, JSON.stringify(logEntry) + '\n');

        // 메모리에 저장
        this.recentSystemLogs.unshift(logEntry);
        if (this.recentSystemLogs.length > this.maxRecentLogs) {
            this.recentSystemLogs.pop();
        }
    }

    /**
     * 헬스 체크
     */
    async _checkHealth(url) {
        try {
            const response = await axios.get(url, { timeout: 3000 });
            return {
                healthy: true,
                status: response.data.status || 'ok',
                timestamp: new Date().toISOString()
            };
        } catch (error) {
            return {
                healthy: false,
                error: error.message,
                timestamp: new Date().toISOString()
            };
        }
    }

    /**
     * 무게 이벤트 로그 저장
     */
    async logWeightEvent(event) {
        const timestamp = new Date();
        const dateStr = this._formatDate(timestamp);
        const logFile = path.join(this.logsDir, 'weight', `${dateStr}.jsonl`);

        const logEntry = {
            timestamp: timestamp.toISOString(),
            ...event
        };

        // 파일에 추가
        try {
            await fs.appendFile(logFile, JSON.stringify(logEntry) + '\n');
        } catch (error) {
            console.error('[ScheduledLogger] Failed to write weight log:', error.message);
        }

        // 메모리에 저장
        this.recentWeightLogs.unshift(logEntry);
        if (this.recentWeightLogs.length > this.maxRecentLogs) {
            this.recentWeightLogs.pop();
        }
    }

    /**
     * 판단 결과 로그 저장
     */
    async logJudgment(judgment) {
        const timestamp = new Date();
        const dateStr = this._formatDate(timestamp);
        const logFile = path.join(this.logsDir, 'judgment', `${dateStr}.jsonl`);

        const logEntry = {
            timestamp: timestamp.toISOString(),
            ...judgment
        };

        // 파일에 추가
        try {
            await fs.appendFile(logFile, JSON.stringify(logEntry) + '\n');
        } catch (error) {
            console.error('[ScheduledLogger] Failed to write judgment log:', error.message);
        }

        // 메모리에 저장
        this.recentJudgmentLogs.unshift(logEntry);
        if (this.recentJudgmentLogs.length > this.maxRecentLogs) {
            this.recentJudgmentLogs.pop();
        }
    }

    /**
     * 최근 무게 로그 조회
     */
    getRecentWeightLogs(limit = 50) {
        return this.recentWeightLogs.slice(0, limit);
    }

    /**
     * 최근 시스템 로그 조회
     */
    getRecentSystemLogs(limit = 50) {
        return this.recentSystemLogs.slice(0, limit);
    }

    /**
     * 최근 판단 로그 조회
     */
    getRecentJudgmentLogs(limit = 50) {
        return this.recentJudgmentLogs.slice(0, limit);
    }

    /**
     * 특정 날짜의 로그 파일 조회
     */
    async getLogFile(type, date) {
        const logFile = path.join(this.logsDir, type, `${date}.jsonl`);

        try {
            const content = await fs.readFile(logFile, 'utf-8');
            const lines = content.trim().split('\n').filter(line => line);
            return lines.map(line => JSON.parse(line));
        } catch (error) {
            if (error.code === 'ENOENT') {
                return [];
            }
            throw error;
        }
    }

    /**
     * 카메라 스냅샷 목록 조회
     */
    async getCameraSnapshots(date) {
        const dateDir = path.join(this.logsDir, 'camera', date);

        try {
            const times = await fs.readdir(dateDir);
            const snapshots = [];

            for (const time of times) {
                const timeDir = path.join(dateDir, time);
                const stat = await fs.stat(timeDir);

                if (stat.isDirectory()) {
                    const files = await fs.readdir(timeDir);
                    snapshots.push({
                        time,
                        files: files.filter(f => f.endsWith('.jpg')),
                        path: timeDir
                    });
                }
            }

            return snapshots.sort((a, b) => b.time.localeCompare(a.time));
        } catch (error) {
            if (error.code === 'ENOENT') {
                return [];
            }
            throw error;
        }
    }

    /**
     * 날짜 포맷 (YYYY-MM-DD)
     */
    _formatDate(date) {
        return date.toISOString().split('T')[0];
    }

    /**
     * 시간 포맷 (HH-MM-SS)
     */
    _formatTime(date) {
        return date.toISOString().split('T')[1].split('.')[0].replace(/:/g, '-');
    }
}

module.exports = new ScheduledLogger();
