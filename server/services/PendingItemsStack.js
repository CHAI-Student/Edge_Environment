/**
 * PendingItemsStack - YAML 기반 판단 결과 스택
 *
 * 문 열림부터 닫힘까지의 판단 결과를 YAML 파일로 관리합니다.
 * 문 닫힘 시 정산하여 순 변화(pickup - return)를 계산합니다.
 *
 * YAML 파일 구조:
 *     data/pending/{session_id}.yaml
 *     - session_id: "260126143025"
 *     - door_opened_at: 1737897025.123
 *     - items: [...]
 */

const fs = require('fs').promises;
const path = require('path');
const EventEmitter = require('events');

// js-yaml 동적 로드 (설치 필요 시 graceful 처리)
let yaml;
try {
    yaml = require('js-yaml');
} catch (e) {
    yaml = null;
    console.warn('[PendingItemsStack] js-yaml not installed, using JSON fallback');
}

class PendingItemsStack extends EventEmitter {
    constructor() {
        super();

        // 저장 경로
        this.pendingPath = process.env.PENDING_ITEMS_PATH ||
            path.join(__dirname, '..', '..', 'data', 'pending');

        // 현재 세션
        this.currentSession = null;
        this.items = [];
    }

    /**
     * 새 세션 시작 (문 열림 시)
     * @param {string} sessionId - 세션 ID (없으면 자동 생성)
     * @returns {string} 세션 ID
     */
    async startSession(sessionId = null) {
        if (!sessionId) {
            // 세션 ID 생성 (YYYYMMDD_HHMMSS 형식)
            const now = new Date();
            sessionId = now.toISOString()
                .replace(/[-:T.Z]/g, '')
                .slice(0, 14);
        }

        // 이전 세션이 있으면 저장
        if (this.currentSession) {
            await this._saveSession();
        }

        this.currentSession = {
            session_id: sessionId,
            door_opened_at: Date.now() / 1000,
            items: [],
        };
        this.items = this.currentSession.items;

        // 디렉토리 생성
        await fs.mkdir(this.pendingPath, { recursive: true });

        console.log(`[PendingItemsStack] Session started: ${sessionId}`);

        this.emit('session_started', { session_id: sessionId });

        return sessionId;
    }

    /**
     * 판단 결과 스택에 추가
     * @param {Object} item - 판단 결과 아이템
     */
    async pushItem(item) {
        if (!this.currentSession) {
            console.warn('[PendingItemsStack] No active session, starting new one');
            await this.startSession();
        }

        const itemWithDefaults = {
            timestamp: item.timestamp || Date.now() / 1000,
            zone_id: item.zone_id || 0,
            action: item.action || 'pickup',
            products: item.products || [],
            weight_delta: item.weight_delta || 0,
            media_paths: item.media_paths || null,
        };

        this.items.push(itemWithDefaults);

        console.log(
            `[PendingItemsStack] Item pushed: ${itemWithDefaults.action} at Zone ${itemWithDefaults.zone_id}, ` +
            `products=${itemWithDefaults.products.length}`
        );

        // 자동 저장
        await this._saveSession();

        this.emit('item_pushed', itemWithDefaults);
    }

    /**
     * 순 변화 계산 (pickup - return)
     * @returns {Object} 순 변화 결과
     */
    calculateNetChanges() {
        const netProducts = new Map(); // product_id -> { name, count, total_weight_delta }

        for (const item of this.items) {
            const multiplier = item.action === 'pickup' ? 1 : -1;

            for (const product of item.products || []) {
                const key = product.product_id;

                if (!netProducts.has(key)) {
                    netProducts.set(key, {
                        product_id: product.product_id,
                        name: product.name,
                        count: 0,
                        confidence_sum: 0,
                        confidence_count: 0,
                    });
                }

                const entry = netProducts.get(key);
                entry.count += (product.count || 1) * multiplier;
                entry.confidence_sum += product.confidence || 0;
                entry.confidence_count += 1;
            }
        }

        // 결과 정리 (count가 0인 항목은 제외, 음수는 반납 초과)
        const result = {
            pickups: [],
            returns: [],
            net_total_price: 0,
        };

        for (const [productId, entry] of netProducts) {
            if (entry.count === 0) continue;

            const avgConfidence = entry.confidence_count > 0
                ? entry.confidence_sum / entry.confidence_count
                : 0;

            const productInfo = {
                product_id: entry.product_id,
                name: entry.name,
                count: Math.abs(entry.count),
                confidence: avgConfidence,
            };

            if (entry.count > 0) {
                result.pickups.push(productInfo);
            } else {
                result.returns.push(productInfo);
            }
        }

        // 총 무게 변화
        result.total_weight_delta = this.items.reduce(
            (sum, item) => sum + (item.weight_delta || 0),
            0
        );

        result.event_count = this.items.length;
        result.pickup_events = this.items.filter(i => i.action === 'pickup').length;
        result.return_events = this.items.filter(i => i.action === 'return').length;

        return result;
    }

    /**
     * 세션 종료 (문 닫힘 시)
     * @returns {Object} 정산 결과
     */
    async closeSession() {
        if (!this.currentSession) {
            console.warn('[PendingItemsStack] No active session to close');
            return null;
        }

        // 순 변화 계산
        const netChanges = this.calculateNetChanges();

        // 세션 정보 추가
        const sessionResult = {
            session_id: this.currentSession.session_id,
            door_opened_at: this.currentSession.door_opened_at,
            door_closed_at: Date.now() / 1000,
            duration_seconds: Date.now() / 1000 - this.currentSession.door_opened_at,
            items: this.items,
            net_changes: netChanges,
        };

        // 최종 저장
        await this._saveSession(sessionResult);

        console.log(
            `[PendingItemsStack] Session closed: ${this.currentSession.session_id}, ` +
            `duration=${sessionResult.duration_seconds.toFixed(1)}s, ` +
            `pickups=${netChanges.pickup_events}, returns=${netChanges.return_events}`
        );

        // 세션 정리
        const closedSession = this.currentSession;
        this.currentSession = null;
        this.items = [];

        this.emit('session_closed', {
            session_id: closedSession.session_id,
            net_changes: netChanges,
            result: sessionResult,
        });

        return sessionResult;
    }

    /**
     * 세션 저장
     * @param {Object} data - 저장할 데이터 (없으면 현재 세션)
     */
    async _saveSession(data = null) {
        if (!this.currentSession && !data) return;

        const saveData = data || {
            session_id: this.currentSession.session_id,
            door_opened_at: this.currentSession.door_opened_at,
            items: this.items,
        };

        const filePath = path.join(
            this.pendingPath,
            `${saveData.session_id}.${yaml ? 'yaml' : 'json'}`
        );

        const maxRetries = 3;
        let lastError = null;

        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                let content;
                if (yaml) {
                    content = yaml.dump(saveData, {
                        indent: 2,
                        lineWidth: 120,
                        noRefs: true,
                    });
                } else {
                    content = JSON.stringify(saveData, null, 2);
                }

                await fs.writeFile(filePath, content, 'utf-8');
                return; // 성공

            } catch (error) {
                lastError = error;
                console.warn(`[PendingItemsStack] Save attempt ${attempt}/${maxRetries} failed:`, error.message);

                if (attempt < maxRetries) {
                    // 재시도 전 잠시 대기 (exponential backoff)
                    await new Promise(resolve => setTimeout(resolve, 100 * attempt));
                }
            }
        }

        // 모든 재시도 실패
        console.error(`[PendingItemsStack] Save failed after ${maxRetries} attempts:`, lastError?.message);
        // 중요 데이터 손실 방지를 위해 이벤트 발생
        this.emit('save_failed', { filePath, error: lastError?.message });
    }

    /**
     * 세션 로드
     * @param {string} sessionId - 세션 ID
     * @returns {Object|null} 세션 데이터
     */
    async loadSession(sessionId) {
        // yaml 또는 json 파일 시도
        const extensions = yaml ? ['yaml', 'json'] : ['json'];

        for (const ext of extensions) {
            const filePath = path.join(this.pendingPath, `${sessionId}.${ext}`);

            try {
                const content = await fs.readFile(filePath, 'utf-8');

                if (ext === 'yaml' && yaml) {
                    return yaml.load(content);
                } else {
                    return JSON.parse(content);
                }

            } catch (error) {
                if (error.code !== 'ENOENT') {
                    console.error(`[PendingItemsStack] Load failed:`, error.message);
                }
            }
        }

        return null;
    }

    /**
     * 세션 목록 조회
     * @returns {Promise<Array>} 세션 파일 목록
     */
    async listSessions() {
        try {
            const files = await fs.readdir(this.pendingPath);
            return files
                .filter(f => f.endsWith('.yaml') || f.endsWith('.json'))
                .map(f => f.replace(/\.(yaml|json)$/, ''))
                .sort()
                .reverse();  // 최신순
        } catch (error) {
            if (error.code === 'ENOENT') {
                return [];
            }
            // 디스크 읽기 오류 등 로깅 후 빈 배열 반환 (서비스 중단 방지)
            console.error(`[PendingItemsStack] listSessions error (code: ${error.code}):`, error.message);
            return [];
        }
    }

    /**
     * 상태 조회
     * @returns {Object} 현재 상태
     */
    getStatus() {
        return {
            has_active_session: this.currentSession !== null,
            session_id: this.currentSession?.session_id || null,
            item_count: this.items.length,
            door_opened_at: this.currentSession?.door_opened_at || null,
            pending_path: this.pendingPath,
        };
    }
}

module.exports = new PendingItemsStack();
