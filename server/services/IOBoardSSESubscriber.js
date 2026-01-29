/**
 * IOBoardSSESubscriber - IO Board SSE 스트림 구독자
 *
 * IO Board 서비스(8000)의 SSE 스트림을 구독하여
 * 로드셀 변화 이벤트를 감지합니다.
 *
 * [Event-Driven Architecture 변경]
 * - Camera Driver가 자체적으로 SSE를 구독하고 이미지/영상을 저장
 * - Node.js는 media-ready 콜백을 받아 WeightChangeAccumulator로 처리
 * - 카메라 활성화/비활성화 직접 호출 제거
 *
 * 데이터 흐름:
 * IO Board SSE → IOBoardSSESubscriber → 문 열림/닫힘 처리 (PendingItemsStack)
 *                                     → loadcell.update → Dashboard SSE 전달
 *
 * Camera Driver SSE → EventRecordingManager → Node.js callback → WeightChangeAccumulator
 */

const { EventSource } = require('eventsource');
const EventEmitter = require('events');
const config = require('../config/key');
const configManager = require('./ConfigManager');
const cameraClient = require('./CameraDriverClient');

// Lazy-loaded modules (avoid circular dependencies)
let pendingItemsStack = null;
let weightAccumulator = null;

class IOBoardSSESubscriber extends EventEmitter {
    constructor() {
        super();
        this.ioBoardUrl = config.ioBoardUrl || 'http://localhost:8000';
        this.eventSource = null;
        this.connected = false;
        this.reconnecting = false; // 재연결 중 플래그 (race condition 방지)
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

        // 카메라 비활성화 딜레이 (마지막 무게 변화로부터 10초)
        this.cameraDeactivateDelay = 10000; // 10초

        // Zone별 녹화 세션 관리
        this.zoneRecordingSessions = new Map(); // zoneId -> {sessionId, startTime}
        this.zoneRecordingStopTimers = new Map(); // zoneId -> timerId

        // Top 카메라 (cam0) 상태
        this.topCameraActive = false;
        this.topCameraRecordingSession = null;
        this.topCameraDeactivateTimer = null;

        // 문/데드볼트 상태 추적
        this.doorState = null; // 'OPEN', 'CLOSED' or null
        this.deadboltState = null; // 'OPEN', 'CLOSED' or null
        this.lastDoorUpdateTime = null;

        // 정산 타이머
        this.settlementTimer = null;
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
    async stop() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
            this.connected = false;
            console.log('[IOBoardSSE] Disconnected');
            this.emit('disconnected');
        }

        // 타이머 정리 (안전하게 존재 확인 후 정리)
        for (const [zoneId, timer] of this.pendingChanges) {
            if (timer && timer.timeout) {
                clearTimeout(timer.timeout);
            }
        }
        this.pendingChanges.clear();

        for (const [zoneId, timerId] of this.zoneDeactivateTimers) {
            clearTimeout(timerId);
        }
        this.zoneDeactivateTimers.clear();

        // 정산 타이머 정리
        if (this.settlementTimer) {
            clearTimeout(this.settlementTimer);
            this.settlementTimer = null;
        }

        // 녹화 세션 정리 (레거시 - Camera Driver가 자체 관리)
        for (const [zoneId, session] of this.zoneRecordingSessions) {
            console.log(`[IOBoardSSE] Cleaning up zone ${zoneId} recording session`);
        }
        this.zoneRecordingSessions.clear();

        // Top 카메라 정리 (레거시 - Camera Driver가 자체 관리)
        if (this.topCameraDeactivateTimer) {
            clearTimeout(this.topCameraDeactivateTimer);
            this.topCameraDeactivateTimer = null;
        }

        this.topCameraActive = false;
        this.topCameraRecordingSession = null;
    }

    /**
     * 재연결 시도
     */
    _handleReconnect() {
        // 이미 재연결 중이면 무시 (race condition 방지)
        if (this.reconnecting) {
            console.log('[IOBoardSSE] Already reconnecting, skipping');
            return;
        }

        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('[IOBoardSSE] Max reconnect attempts reached');
            this.emit('max_reconnect_reached');
            return;
        }

        this.reconnecting = true;
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1);

        console.log(`[IOBoardSSE] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

        setTimeout(() => {
            try {
                if (this.eventSource) {
                    this.eventSource.close();
                    this.eventSource = null;
                }
                this.start();
            } finally {
                this.reconnecting = false;
            }
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
     * @param {Object} data - {changed_indices, old_values, new_values, deltas, timestamp, ...}
     */
    _handleLoadcellChange(data) {
        console.log('[IOBoardSSE] Loadcell change event:', data);

        // IO Board의 실제 이벤트 형식 처리
        // {changed_indices: [0], old_values: [12], new_values: [-12], deltas: [24], ...}
        const changedIndices = data.changed_indices || [];
        const oldValues = data.old_values || [];
        const newValues = data.new_values || [];
        const deltas = data.deltas || [];
        const timestamp = data.timestamp || new Date().toISOString();

        if (changedIndices.length === 0) {
            return;
        }

        // changed_indices에서 zone_id 계산
        const zoneId = configManager.getZoneFromChannels(changedIndices);

        if (zoneId === null || zoneId === undefined) {
            console.log(`[IOBoardSSE] Could not determine zone from channels: ${changedIndices}`);
            return;
        }

        // 총 delta 계산
        const totalDelta = deltas.reduce((sum, d) => sum + d, 0);

        // 변화 정보 구성
        const change = {
            zone_id: zoneId,
            channels: changedIndices,
            delta: totalDelta,
            current: newValues,
            previous: oldValues
        };

        this._processWeightChange(change, timestamp);
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

            const isOpening = data.deadbolt.toUpperCase().includes('OPEN');
            const isClosing = data.deadbolt.toUpperCase().includes('CLOSE') ||
                              data.deadbolt.toUpperCase().includes('LOCK');

            if (isOpening) {
                // 데드볼트 열림 → PendingItemsStack 세션 시작
                this._onDeadboltOpened(timestamp);
            } else if (isClosing) {
                // 데드볼트 닫힘 → 정산 처리 스케줄링
                this._scheduleSettlement(timestamp);
            }

            this.emit('deadbolt_changed', {
                previous: prevDeadboltState,
                current: data.deadbolt,
                timestamp
            });
        }
    }

    /**
     * 데드볼트 열림 시 처리
     * @param {string} timestamp - 타임스탬프
     */
    async _onDeadboltOpened(timestamp) {
        try {
            // PendingItemsStack 세션 시작
            const stack = this._getPendingItemsStack();
            const sessionId = await stack.startSession();

            console.log(`[IOBoardSSE] Deadbolt opened: session started (${sessionId})`);

            this.emit('session_started', {
                session_id: sessionId,
                timestamp
            });

        } catch (error) {
            console.error('[IOBoardSSE] Failed to start session:', error.message);
        }
    }

    /**
     * 정산 처리 스케줄링 (데드볼트 닫힘)
     * @param {string} timestamp - 타임스탬프
     */
    _scheduleSettlement(timestamp) {
        // 기존 타이머 취소
        if (this.settlementTimer) {
            clearTimeout(this.settlementTimer);
        }

        // 대기 시간 (WeightAccumulator 타이머 완료 대기)
        const settlementDelay = 15000;  // 15초 (10초 + 여유 5초)

        this.settlementTimer = setTimeout(async () => {
            await this._processDoorClose(timestamp);
            this.settlementTimer = null;
        }, settlementDelay);

        console.log(`[IOBoardSSE] Settlement scheduled in ${settlementDelay}ms`);
    }

    /**
     * 문 닫힘 정산 처리
     * @param {string} timestamp - 타임스탬프
     */
    async _processDoorClose(timestamp) {
        try {
            // 1. WeightAccumulator 강제 처리 (대기 중인 이벤트 처리)
            const accumulator = this._getWeightAccumulator();
            const accumulatorResult = await accumulator.forceProcess();

            // 2. PendingItemsStack 세션 종료 및 정산
            const stack = this._getPendingItemsStack();
            const sessionResult = await stack.closeSession();

            if (sessionResult) {
                console.log(
                    `[IOBoardSSE] Settlement complete: ` +
                    `pickups=${sessionResult.net_changes.pickup_events}, ` +
                    `returns=${sessionResult.net_changes.return_events}`
                );

                this.emit('door_settlement', {
                    session_id: sessionResult.session_id,
                    net_changes: sessionResult.net_changes,
                    duration_seconds: sessionResult.duration_seconds,
                    timestamp
                });
            }

        } catch (error) {
            console.error('[IOBoardSSE] Settlement failed:', error.message);
        }
    }

    /**
     * PendingItemsStack 가져오기 (lazy load)
     */
    _getPendingItemsStack() {
        if (!pendingItemsStack) {
            pendingItemsStack = require('./PendingItemsStack');
        }
        return pendingItemsStack;
    }

    /**
     * WeightChangeAccumulator 가져오기 (lazy load)
     */
    _getWeightAccumulator() {
        if (!weightAccumulator) {
            weightAccumulator = require('./WeightChangeAccumulator');
        }
        return weightAccumulator;
    }

    /**
     * Top 카메라 활성화 및 녹화 시작 (Deadbolt 열릴 때)
     * @param {string} timestamp - 타임스탬프
     */
    async _activateTopCameraWithRecording(timestamp) {
        try {
            // 기존 비활성화 타이머 취소
            if (this.topCameraDeactivateTimer) {
                clearTimeout(this.topCameraDeactivateTimer);
                this.topCameraDeactivateTimer = null;
            }

            // 이미 활성화 상태면 스킵
            if (this.topCameraActive) {
                console.log('[IOBoardSSE] Top camera already active');
                return;
            }

            // Top 카메라 활성화
            await cameraClient.activateTopCamera();
            this.topCameraActive = true;

            // 녹화 시작
            const sessionId = new Date().toISOString()
                .replace(/[-:T.Z]/g, '')
                .slice(2, 14);

            const recordingResult = await cameraClient.startTopCameraRecording(sessionId);
            this.topCameraRecordingSession = recordingResult.session_id || sessionId;

            console.log(`[IOBoardSSE] Top camera activated and recording started: session=${this.topCameraRecordingSession}`);

            this.emit('top_camera_activated', {
                session_id: this.topCameraRecordingSession,
                timestamp
            });

        } catch (error) {
            console.error('[IOBoardSSE] Failed to activate top camera:', error.message);
        }
    }

    /**
     * Top 카메라 비활성화 스케줄링 (Deadbolt 닫힐 때)
     */
    _scheduleTopCameraDeactivation() {
        // 기존 타이머 취소
        if (this.topCameraDeactivateTimer) {
            clearTimeout(this.topCameraDeactivateTimer);
        }

        // 10초 후 비활성화
        this.topCameraDeactivateTimer = setTimeout(async () => {
            try {
                if (this.topCameraActive) {
                    // 녹화 중지
                    await cameraClient.stopRecording();

                    // Top 카메라 비활성화
                    await cameraClient.deactivateTopCamera();

                    console.log(`[IOBoardSSE] Top camera deactivated and recording stopped: session=${this.topCameraRecordingSession}`);

                    this.emit('top_camera_deactivated', {
                        session_id: this.topCameraRecordingSession
                    });

                    this.topCameraActive = false;
                    this.topCameraRecordingSession = null;
                }
            } catch (error) {
                console.error('[IOBoardSSE] Failed to deactivate top camera:', error.message);
            }
            this.topCameraDeactivateTimer = null;
        }, this.cameraDeactivateDelay);

        console.log(`[IOBoardSSE] Top camera deactivation scheduled in ${this.cameraDeactivateDelay}ms`);
    }

    /**
     * 무게 변화 감지 (두 배열 비교)
     * @param {number[]} prev - 이전 무게 배열
     * @param {number[]} curr - 현재 무게 배열
     * @returns {Array<{zone_id, channel, delta, current, previous}>}
     */
    _detectWeightChanges(prev, curr) {
        const changes = [];
        const enabledZones = configManager.getEnabledZones();

        for (const zoneId of enabledZones) {
            const channels = configManager.getLoadcellChannelsForZone(zoneId);
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

        // 이벤트 데이터 구성 (새로운 형식)
        const eventData = {
            zone_id: zoneId,
            timestamp: Date.now() / 1000,
            weight_data: {
                before_weights: this.lastLoadcellWeights || [],
                after_weights: change.current || [],
                delta_weight: change.delta,
                channels: change.channels || [zoneId * 2, zoneId * 2 + 1]
            },
            media_paths: null,
            judgment_result: null
        };

        try {
            // 1. 카메라 활성화 및 녹화 시작 (아직 활성화되지 않은 경우)
            const isNewActivation = !this.activeZones.has(zoneId);
            if (isNewActivation) {
                await cameraClient.activateZone(zoneId);
                this.activeZones.add(zoneId);
                console.log(`[IOBoardSSE] Camera activated for Zone ${zoneId}`);

                // 녹화 시작
                await this._startZoneRecording(zoneId, timestamp);
            } else {
                // 이미 활성화된 상태에서 추가 무게 변화 → 타이머 리셋
                console.log(`[IOBoardSSE] Zone ${zoneId} already active, extending recording timer`);
            }

            // 2. 스냅샷 캡처 및 저장
            const snapshotResult = await this._captureAndSaveSnapshot(zoneId, timestamp);
            if (snapshotResult) {
                eventData.media_paths = {
                    image_folder: snapshotResult.session_path,
                    top_image: snapshotResult.top_image,
                    side_image: snapshotResult.side_image,
                    video_path: this.zoneRecordingSessions.get(zoneId)?.videoPath || null
                };
            }

            // 3. Model 서비스에 판단 요청
            const judgeResult = await this._requestJudgment(eventData);
            eventData.judgment_result = judgeResult;

            // 4. 이벤트 발생 (외부 리스너용)
            eventData.delta = change.delta;
            eventData.current = change.current;
            eventData.previous = change.previous;
            eventData.cameras_activated = this.activeZones.has(zoneId);
            eventData.recording_session = this.zoneRecordingSessions.get(zoneId)?.sessionId || null;
            this.emit('weight_change', eventData);

            // 5. 카메라 비활성화 + 녹화 중지 타이머 설정/리셋 (마지막 변화로부터 10초)
            this._scheduleZoneDeactivation(zoneId);

        } catch (error) {
            console.error(`[IOBoardSSE] Error processing weight change:`, error.message);
            this.emit('weight_change_error', { zoneId, error: error.message });
        }
    }

    /**
     * Zone 녹화 시작
     * @param {number} zoneId - Zone ID
     * @param {string} timestamp - 타임스탬프
     */
    async _startZoneRecording(zoneId, timestamp) {
        try {
            // 세션 ID 생성
            const sessionId = new Date().toISOString()
                .replace(/[-:T.Z]/g, '')
                .slice(2, 14) + `_zone${zoneId}`;

            // 녹화 시작 (Zone 카메라 + Top 카메라)
            const result = await cameraClient.startRecording(zoneId, true, sessionId);

            // 세션 정보 저장
            this.zoneRecordingSessions.set(zoneId, {
                sessionId: result.session_id || sessionId,
                startTime: Date.now(),
                videoPath: result.paths?.video || null
            });

            console.log(`[IOBoardSSE] Zone ${zoneId} recording started: session=${result.session_id || sessionId}`);

            this.emit('zone_recording_started', {
                zone_id: zoneId,
                session_id: result.session_id || sessionId,
                timestamp
            });

        } catch (error) {
            console.error(`[IOBoardSSE] Failed to start zone ${zoneId} recording:`, error.message);
        }
    }

    /**
     * Zone 녹화 중지
     * @param {number} zoneId - Zone ID
     */
    async _stopZoneRecording(zoneId) {
        try {
            const session = this.zoneRecordingSessions.get(zoneId);
            if (!session) {
                return;
            }

            // 녹화 중지
            const result = await cameraClient.stopRecording();

            console.log(`[IOBoardSSE] Zone ${zoneId} recording stopped: session=${session.sessionId}`);

            this.emit('zone_recording_stopped', {
                zone_id: zoneId,
                session_id: session.sessionId,
                duration_ms: Date.now() - session.startTime,
                paths: result.session_info?.paths || null
            });

            // 세션 정보 삭제
            this.zoneRecordingSessions.delete(zoneId);

        } catch (error) {
            console.error(`[IOBoardSSE] Failed to stop zone ${zoneId} recording:`, error.message);
        }
    }

    /**
     * Zone 카메라 비활성화 스케줄링 (녹화 중지 포함)
     * 마지막 무게 변화로부터 10초 후 녹화 중지 및 카메라 비활성화
     * @param {number} zoneId - Zone ID
     */
    _scheduleZoneDeactivation(zoneId) {
        // 기존 비활성화 타이머 취소
        if (this.zoneDeactivateTimers.has(zoneId)) {
            clearTimeout(this.zoneDeactivateTimers.get(zoneId));
            console.log(`[IOBoardSSE] Zone ${zoneId} deactivation timer reset (new weight change detected)`);
        }

        // 새 비활성화 타이머 설정 (마지막 무게 변화로부터 10초 후)
        const deactivateTimer = setTimeout(async () => {
            try {
                // 1. 녹화 먼저 중지
                await this._stopZoneRecording(zoneId);

                // 2. 카메라 비활성화
                await cameraClient.deactivateZone(zoneId);
                this.activeZones.delete(zoneId);

                console.log(`[IOBoardSSE] Zone ${zoneId} recording stopped and camera deactivated`);

                this.emit('zone_deactivated', {
                    zone_id: zoneId,
                    reason: 'timeout',
                    delay_ms: this.cameraDeactivateDelay
                });

            } catch (error) {
                console.error(`[IOBoardSSE] Failed to deactivate zone ${zoneId}:`, error.message);
            }
            this.zoneDeactivateTimers.delete(zoneId);
        }, this.cameraDeactivateDelay);

        this.zoneDeactivateTimers.set(zoneId, deactivateTimer);
        console.log(`[IOBoardSSE] Zone ${zoneId} scheduled for deactivation in ${this.cameraDeactivateDelay}ms`);
    }

    /**
     * 스냅샷 캡처 및 저장
     * @param {number} zoneId - Zone ID
     * @param {string} timestamp - 타임스탬프
     * @returns {Promise<{session_path: string, top_image: string|null, side_image: string|null}|null>}
     */
    async _captureAndSaveSnapshot(zoneId, timestamp) {
        try {
            // 세션 ID 생성 (YYMMDD_HHMMSS 형식)
            const now = new Date();
            const sessionId = now.toISOString()
                .replace(/[-:T.Z]/g, '')
                .slice(2, 14); // "260126143025" 형식

            // Camera Driver에 스냅샷 요청
            const result = await cameraClient.captureSnapshot(zoneId, sessionId);

            return {
                session_path: result.session_path || null,
                top_image: result.images?.cam0 || null,
                side_image: result.images?.[`cam${zoneId + 1}`] || null
            };
        } catch (error) {
            console.error(`[IOBoardSSE] Snapshot capture failed:`, error.message);
            return null;
        }
    }

    /**
     * Model 서비스에 판단 요청
     * @param {Object} eventData - 이벤트 데이터
     * @returns {Promise<Object>}
     */
    async _requestJudgment(eventData) {
        try {
            const productJudgeClient = require('./ProductJudgeClient');
            if (!productJudgeClient || !productJudgeClient.judgeWithWeightData) {
                throw new Error('ProductJudgeClient not properly loaded');
            }
            return await productJudgeClient.judgeWithWeightData(eventData);
        } catch (error) {
            console.error(`[IOBoardSSE] Judgment request failed:`, error.message);
            return { success: false, error: error.message };
        }
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
        // Zone 녹화 세션 정보 수집
        const zoneRecordingSessions = {};
        for (const [zoneId, session] of this.zoneRecordingSessions) {
            zoneRecordingSessions[zoneId] = {
                sessionId: session.sessionId,
                startTime: session.startTime,
                duration_ms: Date.now() - session.startTime
            };
        }

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
            // 녹화 상태
            recording: {
                topCamera: {
                    active: this.topCameraActive,
                    sessionId: this.topCameraRecordingSession,
                    deactivationScheduled: this.topCameraDeactivateTimer !== null
                },
                zones: zoneRecordingSessions
            },
            settings: {
                weightChangeThreshold: this.weightChangeThreshold,
                debounceTime: this.debounceTime,
                cameraDeactivateDelay: this.cameraDeactivateDelay
            }
        };
    }
}

module.exports = new IOBoardSSESubscriber();
