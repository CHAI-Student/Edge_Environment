/**
 * IOBoardSSESubscriber - IO Board SSE 스트림 구독자
 *
 * IO Board 서비스(8001)의 SSE 스트림을 구독하여
 * 로드셀 변화 이벤트를 감지하고 카메라 활성화 및 로그 저장을 수행합니다.
 *
 * 데이터 흐름:
 * IO Board SSE → IOBoardSSESubscriber → CameraDriverClient (활성화)
 *                                     → WeightEventLogger (로그 저장)
 *                                     → EventEmitter (내부 이벤트)
 */

const { EventSource } = require('eventsource');
const EventEmitter = require('events');
const config = require('../config/key');
const cameraClient = require('./CameraDriverClient');
const configManager = require('./ConfigManager');

class IOBoardSSESubscriber extends EventEmitter {
    constructor() {
        super();
        this.ioBoardUrl = config.ioBoardUrl || 'http://localhost:8001';
        this.eventSource = null;
        this.connected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 5000; // 5초

        // 로드셀 상태 추적
        this.lastLoadcellWeights = null;
        this.baselineWeights = null;
        this.lastUpdateTime = null;

        // 무게 변화 감지 설정
        this.weightChangeThreshold = 50; // 50g 이상 변화 감지
        this.debounceTime = 500; // 500ms 디바운스
        this.pendingChanges = new Map(); // zoneId -> {timeout, delta}

        // Zone별 카메라 활성화 상태
        this.activeZones = new Set();
        this.zoneDeactivateTimers = new Map(); // zoneId -> timerId

        // 카메라 비활성화 딜레이 (판단 완료 후)
        this.cameraDeactivateDelay = 5000; // 5초

        // 문/데드볼트 상태 추적
        this.doorState = null; // 'OPEN', 'CLOSED' or null
        this.deadboltState = null; // 'OPEN', 'CLOSED' or null
        this.lastDoorUpdateTime = null;
    }

    /**
     * SSE 스트림 구독 시작
     */
    start() {
        if (this.eventSource) {
            console.log('[IOBoardSSE] Already connected');
            return;
        }

        const sseUrl = `${this.ioBoardUrl}/sse?streams=loadcells,doors&loadcell_interval=0.5&door_interval=1.0`;
        console.log(`[IOBoardSSE] Connecting to ${sseUrl}`);

        this.eventSource = new EventSource(sseUrl);

        this.eventSource.onopen = () => {
            console.log('[IOBoardSSE] Connected');
            this.connected = true;
            this.reconnectAttempts = 0;
            this.emit('connected');
        };

        this.eventSource.onerror = (error) => {
            console.error('[IOBoardSSE] Connection error:', error.message || 'Unknown error');
            this.connected = false;
            this.emit('error', error);
            this._handleReconnect();
        };

        // loadcell.update 이벤트 처리 (IO Board sends with dot notation)
        this.eventSource.addEventListener('loadcell.update', (event) => {
            try {
                const data = JSON.parse(event.data);
                this._handleLoadcellUpdate(data);
            } catch (error) {
                console.error('[IOBoardSSE] Failed to parse loadcell.update:', error.message);
            }
        });

        // loadcell.change 이벤트 처리 (이벤트 기반)
        this.eventSource.addEventListener('loadcell.change', (event) => {
            try {
                const data = JSON.parse(event.data);
                this._handleLoadcellChange(data);
            } catch (error) {
                console.error('[IOBoardSSE] Failed to parse loadcell.change:', error.message);
            }
        });

        // door.update 이벤트 처리
        this.eventSource.addEventListener('door.update', (event) => {
            try {
                const data = JSON.parse(event.data);
                this._handleDoorUpdate(data);
            } catch (error) {
                console.error('[IOBoardSSE] Failed to parse door.update:', error.message);
            }
        });

        // 일반 message 이벤트 (fallback)
        this.eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'loadcell_update') {
                    this._handleLoadcellUpdate(data);
                } else if (data.type === 'loadcell_change') {
                    this._handleLoadcellChange(data);
                }
            } catch (error) {
                // JSON이 아닌 메시지는 무시
            }
        };
    }

    /**
     * SSE 스트림 구독 중지
     */
    stop() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
            this.connected = false;
            console.log('[IOBoardSSE] Disconnected');
            this.emit('disconnected');
        }

        // 타이머 정리
        for (const [zoneId, timer] of this.pendingChanges) {
            clearTimeout(timer.timeout);
        }
        this.pendingChanges.clear();

        for (const [zoneId, timerId] of this.zoneDeactivateTimers) {
            clearTimeout(timerId);
        }
        this.zoneDeactivateTimers.clear();
    }

    /**
     * 재연결 시도
     */
    _handleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('[IOBoardSSE] Max reconnect attempts reached');
            this.emit('max_reconnect_reached');
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1);

        console.log(`[IOBoardSSE] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

        setTimeout(() => {
            if (this.eventSource) {
                this.eventSource.close();
                this.eventSource = null;
            }
            this.start();
        }, delay);
    }

    /**
     * 로드셀 주기적 업데이트 처리
     * @param {Object} data - {raw_values: string[], filtered_values: string[], timestamp: string}
     */
    _handleLoadcellUpdate(data) {
        // IO Board SSE sends raw_values and filtered_values (as string arrays)
        // Support multiple formats for compatibility
        const rawValues = data.raw_values || data.weights || data.loadcells;
        const filteredValues = data.filtered_values || rawValues;
        const timestamp = data.timestamp || new Date().toISOString();

        // Convert string values to numbers
        const weights = (filteredValues || rawValues || []).map(v => parseFloat(v) || 0);

        if (!Array.isArray(weights) || weights.length === 0) {
            return;
        }

        // 첫 데이터는 베이스라인으로 설정
        if (!this.baselineWeights) {
            this.baselineWeights = [...weights];
            console.log('[IOBoardSSE] Baseline weights set:', this.baselineWeights);
        }

        // 직접 변화 감지 (IO Board가 change 이벤트를 보내지 않을 경우)
        if (this.lastLoadcellWeights) {
            const changes = this._detectWeightChanges(this.lastLoadcellWeights, weights);
            for (const change of changes) {
                this._processWeightChange(change, timestamp);
            }
        }

        this.lastLoadcellWeights = [...weights];
        this.lastUpdateTime = timestamp;

        // 이벤트 발생 - include all data for dashboard
        this.emit('loadcell_update', {
            weights,
            raw_values: rawValues,
            filtered_values: filteredValues,
            timestamp,
            baseline: this.baselineWeights
        });
    }

    /**
     * 로드셀 변화 이벤트 처리 (IO Board에서 직접 발생)
     * @param {Object} data - {zone_id, channel, delta, current, previous, timestamp}
     */
    _handleLoadcellChange(data) {
        console.log('[IOBoardSSE] Loadcell change event:', data);
        this._processWeightChange(data, data.timestamp || new Date().toISOString());
    }

    /**
     * 문/데드볼트 상태 업데이트 처리
     * @param {Object} data - {door: string, deadbolt: string, timestamp: string}
     */
    _handleDoorUpdate(data) {
        const timestamp = data.timestamp || new Date().toISOString();
        const prevDoorState = this.doorState;
        const prevDeadboltState = this.deadboltState;

        // 상태 업데이트
        this.doorState = data.door;
        this.deadboltState = data.deadbolt;
        this.lastDoorUpdateTime = timestamp;

        // 문 상태 이벤트 발생
        this.emit('door_update', {
            door: data.door,
            deadbolt: data.deadbolt,
            timestamp
        });

        // 문 열림/닫힘 상태 변화 감지
        if (prevDoorState && prevDoorState !== data.door) {
            if (data.door.toUpperCase().includes('OPEN')) {
                console.log('[IOBoardSSE] Door opened');
                this.emit('door_opened', { timestamp });
            } else if (data.door.toUpperCase().includes('CLOSED')) {
                console.log('[IOBoardSSE] Door closed');
                this.emit('door_closed', { timestamp });
            }
        }

        // 데드볼트 상태 변화 감지
        if (prevDeadboltState && prevDeadboltState !== data.deadbolt) {
            console.log(`[IOBoardSSE] Deadbolt state changed: ${prevDeadboltState} -> ${data.deadbolt}`);
            this.emit('deadbolt_changed', {
                previous: prevDeadboltState,
                current: data.deadbolt,
                timestamp
            });
        }
    }

    /**
     * 무게 변화 감지 (두 배열 비교)
     * @param {number[]} prev - 이전 무게 배열
     * @param {number[]} curr - 현재 무게 배열
     * @returns {Array<{zone_id, channel, delta, current, previous}>}
     */
    _detectWeightChanges(prev, curr) {
        const changes = [];
        const zoneMapping = configManager.getZoneMapping();

        for (let zoneId = 0; zoneId < 5; zoneId++) {
            const channels = zoneMapping.zones[zoneId]?.loadcell_channels || [zoneId * 2, zoneId * 2 + 1];
            let zoneDelta = 0;

            for (const ch of channels) {
                if (ch < prev.length && ch < curr.length) {
                    const prevWeight = parseFloat(prev[ch]) || 0;
                    const currWeight = parseFloat(curr[ch]) || 0;
                    zoneDelta += currWeight - prevWeight;
                }
            }

            if (Math.abs(zoneDelta) >= this.weightChangeThreshold) {
                changes.push({
                    zone_id: zoneId,
                    channels,
                    delta: zoneDelta,
                    current: channels.map(ch => curr[ch]),
                    previous: channels.map(ch => prev[ch])
                });
            }
        }

        return changes;
    }

    /**
     * 무게 변화 처리 (디바운스 적용)
     * @param {Object} change - 변화 정보
     * @param {string} timestamp - 타임스탬프
     */
    _processWeightChange(change, timestamp) {
        const zoneId = change.zone_id;

        // 기존 타이머 취소
        if (this.pendingChanges.has(zoneId)) {
            clearTimeout(this.pendingChanges.get(zoneId).timeout);
        }

        // 디바운스: 새 타이머 설정
        const timeout = setTimeout(() => {
            this._executeWeightChangeActions(zoneId, change, timestamp);
            this.pendingChanges.delete(zoneId);
        }, this.debounceTime);

        this.pendingChanges.set(zoneId, { timeout, change, timestamp });
    }

    /**
     * 무게 변화 시 실행할 액션들
     * @param {number} zoneId - Zone ID
     * @param {Object} change - 변화 정보
     * @param {string} timestamp - 타임스탬프
     */
    async _executeWeightChangeActions(zoneId, change, timestamp) {
        console.log(`[IOBoardSSE] Processing weight change - Zone ${zoneId}, Delta: ${change.delta}g`);

        // 1. 카메라 활성화
        try {
            if (!this.activeZones.has(zoneId)) {
                await cameraClient.activateZone(zoneId);
                this.activeZones.add(zoneId);
                console.log(`[IOBoardSSE] Camera activated for Zone ${zoneId}`);
            }

            // 기존 비활성화 타이머 취소
            if (this.zoneDeactivateTimers.has(zoneId)) {
                clearTimeout(this.zoneDeactivateTimers.get(zoneId));
            }

            // 새 비활성화 타이머 설정
            const deactivateTimer = setTimeout(async () => {
                try {
                    await cameraClient.deactivateZone(zoneId);
                    this.activeZones.delete(zoneId);
                    console.log(`[IOBoardSSE] Camera deactivated for Zone ${zoneId}`);
                } catch (error) {
                    console.error(`[IOBoardSSE] Failed to deactivate zone ${zoneId}:`, error.message);
                }
                this.zoneDeactivateTimers.delete(zoneId);
            }, this.cameraDeactivateDelay);

            this.zoneDeactivateTimers.set(zoneId, deactivateTimer);

        } catch (error) {
            console.error(`[IOBoardSSE] Failed to activate camera for zone ${zoneId}:`, error.message);
        }

        // 2. 이벤트 발생 (외부 리스너용)
        const eventData = {
            zone_id: zoneId,
            delta: change.delta,
            current: change.current,
            previous: change.previous,
            timestamp,
            cameras_activated: this.activeZones.has(zoneId)
        };

        this.emit('weight_change', eventData);

        // 3. 로그 저장은 WeightEventLogger에서 이벤트 구독으로 처리
    }

    /**
     * 베이스라인 무게 재설정
     */
    resetBaseline() {
        if (this.lastLoadcellWeights) {
            this.baselineWeights = [...this.lastLoadcellWeights];
            console.log('[IOBoardSSE] Baseline reset to:', this.baselineWeights);
        }
    }

    /**
     * 무게 변화 감지 임계값 설정
     * @param {number} threshold - 그램 단위
     */
    setWeightChangeThreshold(threshold) {
        this.weightChangeThreshold = threshold;
        console.log(`[IOBoardSSE] Weight change threshold set to ${threshold}g`);
    }

    /**
     * 카메라 비활성화 딜레이 설정
     * @param {number} delay - 밀리초
     */
    setCameraDeactivateDelay(delay) {
        this.cameraDeactivateDelay = delay;
        console.log(`[IOBoardSSE] Camera deactivate delay set to ${delay}ms`);
    }

    /**
     * 현재 상태 조회
     * @returns {Object}
     */
    getStatus() {
        return {
            connected: this.connected,
            reconnectAttempts: this.reconnectAttempts,
            lastUpdateTime: this.lastUpdateTime,
            baselineWeights: this.baselineWeights,
            lastWeights: this.lastLoadcellWeights,
            activeZones: Array.from(this.activeZones),
            pendingChanges: this.pendingChanges.size,
            doorState: this.doorState,
            deadboltState: this.deadboltState,
            lastDoorUpdateTime: this.lastDoorUpdateTime,
            settings: {
                weightChangeThreshold: this.weightChangeThreshold,
                debounceTime: this.debounceTime,
                cameraDeactivateDelay: this.cameraDeactivateDelay
            }
        };
    }
}

module.exports = new IOBoardSSESubscriber();
