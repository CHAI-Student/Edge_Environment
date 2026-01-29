# Edge Environment 통합 가이드

> **작성일**: 2026-01-29 (최종 업데이트)
> **작성자**: minkyu 브랜치
> **대상**: Node.js 총괄 담당자 및 개발팀
> **아키텍처**: Event-Driven + Model Stateless

---

## 목차

1. [시스템 개요](#1-시스템-개요)
2. [서비스 구조](#2-서비스-구조)
3. [Node.js 연동 가이드](#3-nodejs-연동-가이드)
4. [테스트 방법](#4-테스트-방법)
5. [실행 방법](#5-실행-방법)
6. [API 레퍼런스](#6-api-레퍼런스)
7. [데이터 흐름](#7-데이터-흐름)
8. [트러블슈팅](#8-트러블슈팅)

---

## 1. 시스템 개요

### 1.1 전체 아키텍처 (2026-01-29 업데이트)

> **핵심 변경**:
> - Model 서비스: **Stateless** (판단 전용, SSE 구독 없음)
> - Node.js: **Event-Driven Architecture** (세션 관리 + 무게 누적)
> - Vision: **Motion Tracking** + **Multi-View Ensemble**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    AI Smart Vending Machine System                       │
│                    (Event-Driven Architecture)                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐               │
│   │  IO Board   │     │  6 Cameras  │     │ Card Reader │               │
│   │ (LoadCell   │     │ (Top 1 +    │     │ (Payment)   │               │
│   │  +Deadbolt) │     │  Zone 5)    │     │             │               │
│   └──────┬──────┘     └──────┬──────┘     └──────┬──────┘               │
│          │                   │                   │                       │
│          ▼                   ▼                   ▼                       │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐               │
│   │  io_board   │     │camera_driver│     │card_terminal│               │
│   │   :8001     │     │   :8003     │     │   :5000     │               │
│   │   (SSE)     │     │(Snapshot/Rec)│    │  (Payment)  │               │
│   └──────┬──────┘     └──────┬──────┘     └──────┬──────┘               │
│          │                   │                   │                       │
│   ┌──────┴───────────────────┴───────────────────┴──────────────────┐   │
│   │              Node.js Orchestrator :8889 ★                        │   │
│   │                                                                  │   │
│   │   ┌─────────────────────────────────────────────────────────┐   │   │
│   │   │ IOBoardSSESubscriber                                     │   │   │
│   │   │   - loadcell.change / door.update 이벤트 수신            │   │   │
│   │   │   - 데드볼트 열림/닫힘 감지 → 세션 관리                   │   │   │
│   │   └─────────────────────────────────────────────────────────┘   │   │
│   │   ┌─────────────────┐   ┌─────────────────┐                     │   │
│   │   │WeightChange     │   │PendingItemsStack│                     │   │
│   │   │Accumulator      │ ↔ │ (세션별 관리)   │                     │   │
│   │   └─────────────────┘   └─────────────────┘                     │   │
│   │                                                                  │   │
│   └────────────────────────┬────────────────────────────────────────┘   │
│                            │                                             │
│                            │ POST /api/judge                             │
│                            │ {weight_data, media_paths}                  │
│                            ▼                                             │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │              model :8002 (STATELESS)                             │   │
│   │                                                                  │   │
│   │   - Vision: YOLO + Motion Tracking + Multi-View Ensemble        │   │
│   │   - Weight: 무게 검증 + 개수 계산                               │   │
│   │   - 판단 결과 반환 (camera_results 포함)                        │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐               │
│   │ mqtt_client │     │   MongoDB   │     │    MinIO    │               │
│   │   :8006     │     │  (logs/db)  │     │  (images)   │               │
│   └─────────────┘     └─────────────┘     └─────────────┘               │
│                                                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │              React Client :3000 (Dashboard)                      │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 서비스 포트 구성

| 서비스 | 포트 | 언어 | 역할 |
|--------|------|------|------|
| **orchestrator** | 8889 | Node.js | SSE 구독 + 세션 관리 + 판단 흐름 제어 ★ |
| **client** | 3000 | React | 웹 대시보드 UI |
| **io_board** | 8001 | Python | 로드셀 10채널 + 데드볼트 SSE 스트림 |
| **model** | 8002 | Python | AI 상품 판단 (Stateless, Vision + Weight) |
| **camera_driver** | 8003 | Python | 6대 카메라 관리 + 스냅샷/녹화 |
| **card_terminal** | 5000 | Python | 결제 터미널 |
| **mqtt_client** | 8006 | Python | MQTT 브로커 연동 (IF01-04) |

---

## 2. 서비스 구조

### 2.1 디렉토리 구조

```
Edge_Environment/
├── server/                         # Node.js Orchestrator
│   ├── index.js                    # Express 진입점 (포트 8889)
│   ├── config/
│   │   ├── key.js                  # 환경 설정 라우터
│   │   ├── dev.js                  # 개발 환경
│   │   └── prod.js                 # 프로덕션 환경
│   ├── routes/
│   │   ├── auth.js                 # JWT 인증
│   │   ├── mqtt.js                 # MQTT 라우팅
│   │   ├── camera.js               # 카메라 제어 라우트
│   │   ├── cameraCallback.js       # Event-Driven 콜백
│   │   ├── door.js                 # 도어 제어 라우트
│   │   ├── model.js                # Model 프록시 라우트
│   │   ├── events.js               # SSE 이벤트 라우트
│   │   ├── logs.js                 # 로그 라우트
│   │   ├── Mqtt/                   # MQTT 모듈
│   │   ├── RestAPI/                # REST API 모듈
│   │   └── AIServer/               # AI 서버 모듈
│   ├── services/
│   │   ├── IOBoardSSESubscriber.js # SSE 구독 + 세션 관리 ★
│   │   ├── IOBoardClient.js        # io_board HTTP 클라이언트
│   │   ├── CameraDriverClient.js   # camera_driver HTTP 클라이언트
│   │   ├── ProductJudgeClient.js   # model 서비스 HTTP 클라이언트
│   │   ├── ConfigManager.js        # Zone 설정 관리
│   │   ├── WeightChangeAccumulator.js  # 무게 변화 누적 ★
│   │   ├── PendingItemsStack.js    # 세션별 픽업/반환 관리 ★
│   │   └── ScheduledLogger.js      # 스케줄 로깅
│   └── model/                      # DB 모델
│
├── services/                       # Python 마이크로서비스
│   ├── io_board/                   # 로드셀 + 데드볼트 (8001)
│   ├── model/                      # AI 상품 판단 (8002)
│   ├── camera_driver/              # 카메라 관리 (8003)
│   ├── mqtt_client/                # MQTT 클라이언트 (8006)
│   └── card_terminal/              # 결제 터미널 (5000)
│
├── client/                         # React Frontend (포트 3000)
│   ├── src/
│   └── public/
│
├── ecosystem.config.js             # PM2 설정
├── package.json                    # Node.js 의존성
├── pyproject.toml                  # Python 의존성 (uv)
└── .env                            # 환경 변수
```

### 2.2 Model 서비스 상세 구조 (Stateless 아키텍처)

> **핵심 특징**:
> - Stateless: SSE 구독 없음, 요청-응답 방식만 지원
> - Motion Tracking: 연속 프레임 분석으로 손 움직임 추적
> - 추론 취소: `/api/judge/cancel` 엔드포인트로 진행 중인 추론 취소 가능

```
services/model/
├── main.py                         # FastAPI 진입점 (Stateless)
└── src/                            # ★ 소스 코드 폴더
    ├── config.py                   # 설정 (Zone 매핑, Vision 파라미터)
    │
    ├── api/                        # REST API
    │   ├── routes.py               # 엔드포인트 (/api/judge, /api/products, /api/door)
    │   └── models.py               # Pydantic 스키마 (WeightData, MediaPaths)
    │
    ├── camera/                     # 이미지 로드
    │   ├── camera_client.py        # camera_driver API (폴백용)
    │   └── frame_capturer.py       # 파일 시스템에서 프레임 로드
    │
    ├── vision/                     # YOLO 추론
    │   ├── yolo_wrapper.py         # YOLO 모델 래퍼 (.pt 또는 .engine)
    │   ├── hand_filter.py          # 손 근접 필터
    │   ├── top5_extractor.py       # Top-K 추출
    │   ├── multi_view_ensemble.py  # Top+Side 앙상블
    │   ├── multi_hand_detector.py  # 다중 손 감지
    │   └── motion_correlation_filter.py # ★ Motion Tracking (연속 프레임)
    │
    ├── weight/                     # 무게 계산
    │   ├── count_calculator.py     # 개수 계산
    │   └── multi_zone_monitor.py   # 다중 Zone 모니터링
    │
    ├── engine/                     # 판단 엔진
    │   ├── models.py               # 데이터 모델
    │   ├── decision_engine.py      # 핵심 판단 로직
    │   ├── event_tracker.py        # 이벤트 추적
    │   └── advanced/               # 고급 시나리오
    │       ├── baseline_manager.py # 베이스라인 드리프트 보정
    │       ├── return_detector.py  # 반환 감지
    │       ├── cross_zone_detector.py  # Zone 간 이동
    │       └── rapid_pickup_handler.py # 연속 픽업
    │
    ├── database/                   # 상품 DB
    │   └── product_db.py           # IF11 형식 지원
    │
    ├── door_payment/               # 도어 결제 모듈
    │   ├── __init__.py             # DoorPaymentController export
    │   ├── controller.py           # 거래 상태 관리
    │   └── payment_client.py       # 결제 단말 통신
    │
    ├── error_recovery/             # 에러 복구 모듈
    │
    ├── monitor/                    # 테스트 대시보드
    │   ├── console_dashboard.py
    │   └── test_mode.py
    │
    └── tests/                      # 테스트
        ├── test_offline_dataset.py # 오프라인 테스트
        ├── test_hardware_integration.py # 하드웨어 테스트
        └── conftest.py             # 테스트 설정
```

---

## 3. Node.js 연동 가이드

### 3.1 새로운 아키텍처: Node.js 중심 오케스트레이션

> **중요**: 2026-01-26 업데이트로 Model 서비스가 **stateless**로 변경되었습니다.
> Node.js가 모든 흐름을 제어합니다.

```
┌─────────────────────────────────────────────────────────────────┐
│                    새로운 데이터 흐름                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. IO Board SSE → Node.js (loadcell.change 이벤트)             │
│  2. Node.js → Camera Driver (스냅샷 저장 요청)                   │
│  3. Node.js → Model (weight_data + media_paths 전달)            │
│  4. Model → Node.js (판단 결과 반환)                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Node.js 핵심 서비스 파일

| 파일 | 역할 |
|------|------|
| `server/services/IOBoardSSESubscriber.js` | IO Board SSE 구독 + 무게 변화 감지 |
| `server/services/CameraDriverClient.js` | 카메라 스냅샷 요청 |
| `server/services/ProductJudgeClient.js` | Model 서비스 판단 요청 |

#### IOBoardSSESubscriber.js 사용 예시

```javascript
// server/services/IOBoardSSESubscriber.js
const EventSource = require('eventsource');

class IOBoardSSESubscriber {
    constructor(ioboardUrl = 'http://localhost:8001') {
        this.url = ioboardUrl;
        this.eventSource = null;
        this.debounceTimeout = null;
        this.debounceMs = 500;  // 500ms 디바운스
        this.weightThreshold = 50;  // 50g 이상 변화 시 감지
    }

    connect() {
        const sseUrl = `${this.url}/sse?streams=loadcells,doors&loadcell_interval=0.5`;
        this.eventSource = new EventSource(sseUrl);

        this.eventSource.addEventListener('loadcell.change', (event) => {
            const data = JSON.parse(event.data);
            // data: { zone_id, delta_weight, channels, before_weights, after_weights }
            this.handleWeightChange(data);
        });

        this.eventSource.addEventListener('door.update', (event) => {
            const data = JSON.parse(event.data);
            // data: { door: "OPEN"|"CLOSED", deadbolt: "LOCKED"|"UNLOCKED" }
            this.handleDoorUpdate(data);
        });
    }

    async handleWeightChange(data) {
        // 디바운스: 연속 이벤트 무시
        if (this.debounceTimeout) {
            clearTimeout(this.debounceTimeout);
        }

        this.debounceTimeout = setTimeout(async () => {
            if (Math.abs(data.delta_weight) < this.weightThreshold) return;

            // 1. 카메라 스냅샷 요청
            const sessionId = Date.now().toString();
            const snapshotResult = await this.cameraClient.captureSnapshot(
                data.zone_id,
                sessionId
            );

            // 2. Model 서비스에 판단 요청
            const judgment = await this.productJudge.judge({
                zone_id: data.zone_id,
                weight_data: {
                    before_weights: data.before_weights,
                    after_weights: data.after_weights,
                    delta_weight: data.delta_weight,
                    channels: data.channels
                },
                media_paths: {
                    image_folder: snapshotResult.folder,
                    top_image: snapshotResult.top_image,
                    side_image: snapshotResult.side_image
                }
            });

            // 3. 결과 처리
            this.emit('judgment', judgment);
        }, this.debounceMs);
    }
}
```

### 3.2 Model 서비스 연동 (Stateless)

Model 서비스는 이제 **요청-응답 방식**으로만 동작합니다. SSE 구독이나 카메라 호출을 하지 않습니다.

**ProductJudgeClient 사용 (server/services/ProductJudgeClient.js):**

> **권장 형식**: `weight_data` + `media_paths` (레거시 `delta_weight`도 지원)

```javascript
const axios = require('axios');

class ProductJudgeClient {
    constructor(baseUrl = 'http://localhost:8002') {
        this.baseUrl = baseUrl;
        this.timeout = 10000; // 10초 타임아웃
    }

    // ★ 권장: weight_data + media_paths 형식
    async judge(request) {
        const response = await axios.post(`${this.baseUrl}/api/judge`, {
            zone_id: request.zone_id,
            weight_data: request.weight_data,      // 무게 정보
            media_paths: request.media_paths       // 이미지 경로
        }, { timeout: this.timeout });
        return response.data;
    }

    // 레거시 형식 (하위 호환)
    async judgeLegacy(zoneId, deltaWeight) {
        const response = await axios.post(`${this.baseUrl}/api/judge`, {
            zone_id: zoneId,
            delta_weight: deltaWeight
        }, { timeout: this.timeout });
        return response.data;
    }

    // 다중 Zone 동시 판단 (Cross-Zone 감지)
    async judgeMultiZone(zoneDeltas, checkCrossZone = true) {
        const response = await axios.post(`${this.baseUrl}/api/judge/multi-zone`, {
            zone_deltas: zoneDeltas,
            check_cross_zone: checkCrossZone
        }, { timeout: this.timeout });
        return response.data;
    }

    // 히스토리 기반 판단 (반환 감지)
    async judgeWithHistory(currentRequest, recentEvents, options = {}) {
        const response = await axios.post(`${this.baseUrl}/api/judge/with-history`, {
            current_request: currentRequest,
            recent_events: recentEvents,
            check_return: options.checkReturn ?? true,
            check_rapid_pickup: options.checkRapidPickup ?? false
        }, { timeout: this.timeout });
        return response.data;
    }

    // 헬스 체크
    async health() {
        const response = await axios.get(`${this.baseUrl}/api/health`, { timeout: 5000 });
        return response.data;
    }

    // 인식률 통계
    async getStats() {
        const response = await axios.get(`${this.baseUrl}/api/stats/recognition-rate`);
        return response.data;
    }
}

module.exports = ProductJudgeClient;
```

**사용 예시 (권장 형식):**
```javascript
const ProductJudgeClient = require('./services/ProductJudgeClient');
const judgeClient = new ProductJudgeClient('http://localhost:8002');

// ★ 권장: weight_data + media_paths 형식
router.post('/judge', async (req, res) => {
    try {
        const result = await judgeClient.judge({
            zone_id: req.body.zoneId,
            weight_data: {
                before_weights: req.body.beforeWeights,  // 10채널 배열
                after_weights: req.body.afterWeights,    // 10채널 배열
                delta_weight: req.body.deltaWeight,      // 총 변화량
                channels: req.body.channels              // 변화 채널 [0,1]
            },
            media_paths: {
                image_folder: req.body.imageFolder,      // 스냅샷 폴더
                top_image: req.body.topImage,            // Top 카메라 경로
                side_image: req.body.sideImage           // Side 카메라 경로
            }
        });
        res.json(result);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// 다중 Zone 판단 (여러 Zone 동시 변화 시)
router.post('/judge-multi', async (req, res) => {
    try {
        const result = await judgeClient.judgeMultiZone([
            { zone_id: 0, delta: -365.0 },  // Zone 0 픽업
            { zone_id: 1, delta: +365.0 }   // Zone 1 반환 (이동)
        ], true);  // Cross-Zone 체크 활성화
        res.json(result);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});
```

### 3.2 IO Board 연동 방법

**IOBoardClient 사용 (services/IOBoardClient.js):**
```javascript
const axios = require('axios');

class IOBoardClient {
    constructor(baseUrl = 'http://localhost:8001') {
        this.baseUrl = baseUrl;
    }

    // 데드볼트 제어
    async setDeadbolt(action) {
        // action: "OPEN" | "CLOSE"
        const response = await axios.post(`${this.baseUrl}/deadbolt`, {
            action: action
        });
        return response.data;
    }

    // 로드셀 값 조회
    async getLoadcells() {
        const response = await axios.get(`${this.baseUrl}/loadcells`);
        return response.data;
        /*
        반환 형식:
        {
            "raw": ["+00432", "+00433", "+00260", ...],  // 10채널
            "filtered": [430.5, 431.2, 259.8, ...],
            "timestamp": "2026-01-22T14:30:45.123Z"
        }
        */
    }

    // 도어/데드볼트 상태 조회
    async getStatus() {
        const response = await axios.get(`${this.baseUrl}/status`);
        return response.data;
        /*
        반환 형식:
        {
            "door": "CLOSED",      // "OPEN" | "CLOSED"
            "deadbolt": "LOCKED",  // "LOCKED" | "UNLOCKED"
            "timestamp": "..."
        }
        */
    }

    // 로드셀 영점 보정
    async calibrate() {
        const response = await axios.post(`${this.baseUrl}/calibrate`);
        return response.data;
    }

    // 시스템 초기화
    async init() {
        const response = await axios.post(`${this.baseUrl}/init`);
        return response.data;
    }
}

module.exports = IOBoardClient;
```

### 3.3 카메라 연동 방법

```javascript
const axios = require('axios');

class CameraDriverClient {
    constructor(baseUrl = 'http://localhost:8003') {
        this.baseUrl = baseUrl;
    }

    // 단일 카메라 프레임 캡처
    async getFrame(cameraId) {
        const response = await axios.get(
            `${this.baseUrl}/frame/${cameraId}`,
            { responseType: 'arraybuffer' }
        );
        return response.data;  // JPEG 바이너리
    }

    // Zone별 프레임 (Top + Side)
    async getZoneFrames(zoneId) {
        const response = await axios.get(`${this.baseUrl}/zone/${zoneId}/frames`);
        return response.data;
        /*
        {
            "top_frame": "base64...",
            "side_frame": "base64...",
            "zone_id": 0
        }
        */
    }

    // 카메라 상태 조회
    async getStatus() {
        const response = await axios.get(`${this.baseUrl}/status`);
        return response.data;
    }
}
```

### 3.4 상품 판단 결과 상태값

| 상태 | 의미 | 처리 방법 |
|------|------|----------|
| `complete` | 확실한 판단 (confidence > 0.7) | 바로 결제 진행 |
| `partial` | 부분 판단 (0.5 < confidence < 0.7) | 사용자 확인 요청 |
| `uncertain` | 불확실 (confidence < 0.5) | 재시도 또는 수동 처리 |
| `no_detection` | Vision 감지 실패 | Loadcell-only 폴백 결과 |

---

## 4. 테스트 방법

### 4.1 필수 파일 (별도 제공)

다음 파일들은 별도로 제공됩니다:

| 파일 | 위치 | 설명 |
|------|------|------|
| `siyeon_best.pt` | 프로젝트 루트 | YOLO 모델 (133개 클래스) |
| `test_dataset/` | 프로젝트 루트 | 테스트 이미지 데이터셋 |

**설치 위치:**
```
win_pc_test_sw2io_board/
├── siyeon_best.pt              ← YOLO 모델 파일
├── test_dataset/               ← 테스트 데이터셋 폴더
│   ├── 20260116_180419/
│   │   └── images/
│   │       ├── cam_0/frame_*.jpg
│   │       └── cam_2/frame_*.jpg
│   └── ...
└── Edge_Environment/
```

### 4.2 테스트 모드 1: 오프라인 테스트 (Vision 파이프라인)

**목적**: 실제 하드웨어 없이 YOLO 모델과 Vision 파이프라인만 테스트

**사전 조건**:
- `siyeon_best.pt` 파일 존재
- `test_dataset/` 폴더 존재

**실행 방법:**
```bash
cd Edge_Environment/services/model

# 1. Python 환경 설정
python -m venv venv
.\venv\Scripts\Activate.ps1   # Windows
pip install -r requirements.txt

# 2. 전체 데이터셋 테스트
python -m src.tests.test_offline_dataset

# 3. 특정 세션만 테스트
python -m src.tests.test_offline_dataset --session 20260116_180419

# 4. 특정 프레임만 테스트
python -m src.tests.test_offline_dataset --session 20260116_180419 --frame 10

# 5. 시각화 결과 저장
python -m src.tests.test_offline_dataset --visualize --output-dir ./viz_results

# 6. JSON 결과 저장
python -m src.tests.test_offline_dataset --output results.json

# 7. 커스텀 모델/데이터셋 경로
python -m src.tests.test_offline_dataset \
  --model "C:\path\to\custom_model.pt" \
  --dataset "C:\path\to\custom_dataset"
```

**출력 예시:**
```
============================================================
              OFFLINE VISION PIPELINE TEST
============================================================

Model: siyeon_best.pt (133 classes)
Dataset: C:\...\test_dataset

[Session 1/13] 20260116_175306
  Processing 35 frames...
  ✓ Detection Rate: 100% (35/35)
  ✓ Avg Confidence: 0.462
  ✓ Avg Time: 108ms/frame

[Session 2/13] 20260116_175426
  ...

============================================================
                      SUMMARY
============================================================
Total Sessions: 13
Total Frames: 408
Overall Detection Rate: 100%
Overall Avg Confidence: 0.450
Overall Avg Time: 112ms/frame
============================================================
```

### 4.3 테스트 모드 2: 하드웨어 연동 테스트

**목적**: 실제 IO Board + 카메라와 연동하여 전체 파이프라인 테스트

**사전 조건**:
- io_board 서비스 실행 중 (포트 8001)
- camera_driver 서비스 실행 중 (포트 8003)
- model 서비스 실행 중 (포트 8002)
- 실제 하드웨어 연결됨

**실행 방법:**
```bash
cd Edge_Environment/services/model

# 1. 서비스 연결 확인
python -m src.tests.test_hardware_integration --check-connection

# 2. SSE 이벤트 모니터링 (로드셀 변화 감지 확인)
python -m src.tests.test_hardware_integration --monitor-sse --duration 10

# 3. Zone별 카메라 캡처 테스트
python -m src.tests.test_hardware_integration --capture-zone 1

# 4. 전체 Zone 스캔
python -m src.tests.test_hardware_integration --scan-all-zones

# 5. 수동 판단 테스트 (특정 무게 변화 시뮬레이션)
python -m src.tests.test_hardware_integration --manual-judge --zone 1 --delta -365

# 6. 실시간 모니터링 + 자동 판단
python -m src.tests.test_hardware_integration --realtime-monitor --duration 60

# 7. 정확도 테스트 (반복 측정)
python -m src.tests.test_hardware_integration --accuracy-test --zone 1 --repeat 10

# 8. 특정 상품 정확도 테스트
python -m src.tests.test_hardware_integration \
  --accuracy-test \
  --zone 1 \
  --repeat 10 \
  --delta -365 \
  --expected-product "chickenmayo_rice"
```

### 4.4 테스트 모드 3: 전체 시스템 통합 테스트 (PM2)

**목적**: 모든 서비스 (Node.js + Python 5개)를 동시에 실행하여 전체 시스템 테스트

**사전 조건**:
- PM2 설치됨 (`npm install -g pm2`)
- 모든 서비스 의존성 설치됨
- `siyeon_best.pt` 파일 존재

#### Step 1: 의존성 설치

```bash
# Node.js 의존성
cd Edge_Environment
npm install

# Python 서비스별 의존성
cd services/io_board && pip install -r requirements.txt
cd ../model && pip install -r requirements.txt
cd ../camera_driver && pip install -r requirements.txt
cd ../mqtt_client && pip install -r requirements.txt
cd ../card_terminal && pip install -r requirements.txt
```

#### Step 2: PM2로 전체 서비스 시작

```bash
cd Edge_Environment

# 전체 서비스 시작
pm2 start ecosystem.config.js

# 상태 확인
pm2 list

# 로그 확인 (전체)
pm2 logs

# 특정 서비스 로그
pm2 logs model
pm2 logs io-board
```

#### Step 3: 개별 서비스 실행 (디버깅용)

```bash
# 특정 서비스만 실행
pm2 start ecosystem.config.js --only model
pm2 start ecosystem.config.js --only "io-board,model,camera-driver"
```

#### Step 4: 서비스 제어

```bash
# 재시작
pm2 restart model
pm2 restart all

# 중지
pm2 stop model
pm2 stop all

# 삭제 (프로세스 제거)
pm2 delete all
```

#### Step 5: 헬스 체크 (curl)

```bash
# 각 서비스 헬스 체크
curl http://localhost:8002/api/health    # model
curl http://localhost:8001/health        # io_board
curl http://localhost:8003/health        # camera_driver
curl http://localhost:8006/health        # mqtt_client
curl http://localhost:8888/api/health    # Node.js (있다면)
```

### 4.5 테스트 모드 4: Model 서비스 단독 테스트 모드

**목적**: Model 서비스의 콘솔 대시보드로 실시간 상태 확인

```bash
cd Edge_Environment/services/model

# 테스트 모드 실행 (콘솔 대시보드)
python -m main --test

# 또는 커스텀 URL로
python -m main --test \
  --io-board-url http://localhost:8001 \
  --camera-url http://localhost:8003
```

**대시보드 출력 예시:**
```
+=========================================================================+
|                    MODEL SERVICE - TEST MODE                             |
|                    Time: 2026-01-22 14:30:45                            |
+-------------------------------------------------------------------------+
|                                                                          |
|  [LoadCell Weights]                                                      |
|  Zone 0: 865g (Ch0: 432g, Ch1: 433g) - STABLE                           |
|  Zone 1: 520g (Ch2: 260g, Ch3: 260g) - STABLE                           |
|  Zone 2:   0g (Ch4:   0g, Ch5:   0g) - STABLE                           |
|                                                                          |
|  [Recent Event] Zone 0 | Delta: -365g | Time: 14:30:42                  |
|                                                                          |
|  [Vision - Top Camera]                                                   |
|    1. chickenmayo_rice  conf=0.788                                      |
|                                                                          |
|  [Final Judgment]                                                        |
|    Product: chickenmayo_rice                                            |
|    Count: 1 | Price: 3,500won | Status: COMPLETE                        |
|                                                                          |
+=========================================================================+
```

---

## 5. 실행 방법

### 5.1 개발 환경 빠른 시작

```bash
# 1. 프로젝트 이동
cd win_pc_test_sw2io_board/Edge_Environment

# 2. Node.js 의존성 설치
npm install

# 3. PM2 전역 설치 (최초 1회)
npm install -g pm2

# 4. 전체 서비스 시작
pm2 start ecosystem.config.js

# 5. 상태 확인
pm2 list
pm2 logs
```

### 5.2 서비스별 개별 실행

#### Node.js Orchestrator
```bash
cd Edge_Environment
node server/index.js
# 또는
npm start
```

#### io_board 서비스
```bash
cd Edge_Environment/services/io_board
python main.py                      # 포트 8001
```

#### model 서비스
```bash
cd Edge_Environment/services/model
python main.py                      # 포트 8002
```

#### camera_driver 서비스
```bash
cd Edge_Environment/services/camera_driver
python main.py                      # 포트 8003
```

#### mqtt_client 서비스
```bash
cd Edge_Environment/services/mqtt_client
python main.py
```

#### card_terminal 서비스
```bash
cd Edge_Environment/services/card_terminal
python main.py
```

### 5.3 서비스 시작 순서 (권장)

하드웨어 의존성으로 인해 다음 순서로 시작을 권장합니다:

```
1. io_board (8001)      - 하드웨어 초기화
2. camera_driver (8003) - 카메라 초기화
3. model (8002)         - Vision + io_board SSE 구독
4. mqtt_client (8006)   - MQTT 브로커 연결
5. card_terminal (5000) - 결제 터미널
6. orchestrator (8888)  - 전체 조율
```

---

## 6. API 레퍼런스

### 6.1 Model 서비스 API

#### 헬스 체크
```http
GET /api/health
```
```json
{
    "status": "healthy",
    "model_loaded": true,
    "model_classes": 133,
    "io_board_connected": true,
    "camera_connected": true
}
```

#### 상품 판단 (권장 형식 - weight_data + media_paths)
```http
POST /api/judge
Content-Type: application/json

{
    "zone_id": 0,
    "weight_data": {
        "before_weights": [1000, 1005, 0, 0, 0, 0, 0, 0, 0, 0],
        "after_weights": [480, 505, 0, 0, 0, 0, 0, 0, 0, 0],
        "delta_weight": -520,
        "channels": [0, 1]
    },
    "media_paths": {
        "image_folder": "/data/snapshots/260126143025",
        "top_image": "/data/snapshots/260126143025/cam_0/snapshot.jpg",
        "side_image": "/data/snapshots/260126143025/cam_1/snapshot.jpg"
    }
}
```

#### 상품 판단 (레거시 형식 - 하위 호환)
```http
POST /api/judge
Content-Type: application/json

{
    "zone_id": 0,
    "delta_weight": -365.0
}
```
```json
{
    "success": true,
    "products": [
        {
            "productId": 26,
            "name": "chickenmayo_rice",
            "count": 1,
            "unitPrice": 3500,
            "totalPrice": 3500,
            "confidence": 0.91
        }
    ],
    "totalPrice": 3500,
    "status": "complete",
    "confidence": 0.91,
    "weightInfo": {
        "delta": -365.0,
        "explained": 365.0,
        "residual": 0.0
    },
    "isRemoval": true,
    "zoneId": 0,
    "timestamp": 1737450000.123
}
```

#### 다중 Zone 판단
```http
POST /api/judge/multi-zone
Content-Type: application/json

{
    "zone_deltas": [
        {"zone_id": 0, "delta": -365.0},
        {"zone_id": 1, "delta": +365.0}
    ],
    "check_cross_zone": true
}
```

#### 히스토리 기반 판단 (반환 감지)
```http
POST /api/judge/with-history
Content-Type: application/json

{
    "current_request": {
        "zone_id": 0,
        "delta_weight": 365.0
    },
    "recent_events": [
        {
            "timestamp": 1737450000.0,
            "zone_id": 0,
            "delta_weight": -365.0,
            "direction": "pickup",
            "product_name": "chickenmayo_rice"
        }
    ],
    "check_return": true
}
```

#### 인식률 통계
```http
GET /api/stats/recognition-rate
```
```json
{
    "total_judgments": 150,
    "complete_count": 120,
    "partial_count": 25,
    "uncertain_count": 5,
    "complete_rate": 0.80,
    "avg_confidence": 0.78
}
```

#### IF11 상품 리스트 동기화 (Node.js → Model)
```http
POST /api/products/sync
Content-Type: application/json

{
    "product_list": [
        {
            "product_idx": "P17355176364813008",
            "product_name": "페리에 330ml",
            "sale_price": 1985,
            "stock_qty": 12,
            "product_weight": "550"
        },
        {
            "product_idx": "P17355176391055026",
            "product_name": "하겐다즈 그린티&아몬드 80ml",
            "sale_price": 4300,
            "stock_qty": 10,
            "product_weight": "77"
        }
    ]
}
```
```json
{
    "success": true,
    "loaded_count": 2,
    "total_products": 52,
    "message": "Successfully synced 2 products from IF11 format",
    "timestamp": 1737450000.123
}
```

> **참고**: README.md Step 5.1 "상품 정보(상품명, 무게, 재고) + 스냅샷 경로 (node → model)" 연동용

### 6.2 IO Board 서비스 API

#### 로드셀 값 조회
```http
GET /loadcells
```
```json
{
    "raw": ["+00432", "+00433", "+00260", "+00261", "+00000", "+00000", "+00000", "+00000", "+00000", "+00000"],
    "filtered": [430.5, 431.2, 259.8, 260.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    "timestamp": "2026-01-22T14:30:45.123Z"
}
```

#### 데드볼트 제어
```http
POST /deadbolt
Content-Type: application/json

{
    "action": "OPEN"
}
```

#### 도어/데드볼트 상태
```http
GET /status
```
```json
{
    "door": "CLOSED",
    "deadbolt": "LOCKED",
    "timestamp": "2026-01-22T14:30:45.123Z"
}
```

#### SSE 스트림 구독
```http
GET /sse?streams=loadcells&filter_method=exponential&filter_alpha=0.2&threshold=5.0
```

### 6.3 Camera Driver 서비스 API

#### 프레임 캡처
```http
GET /frame/0     # Top 카메라
GET /frame/1     # Zone 0 Side 카메라
GET /frame/2     # Zone 1 Side 카메라
...
```

#### Zone별 프레임
```http
GET /zone/0/frames
```

#### 카메라 상태
```http
GET /status
```

---

## 7. 데이터 흐름

### 7.1 실시간 상품 판단 흐름 (Node.js 중심)

> **업데이트**: Node.js가 SSE 구독 및 카메라 제어를 담당합니다.

```
┌──────────────────────────────────────────────────────────────────────┐
│                    REAL-TIME PRODUCT JUDGMENT FLOW                    │
│                    (Node.js 오케스트레이션)                           │
└──────────────────────────────────────────────────────────────────────┘

[1] 손님이 상품을 집음
        │
        ▼
[2] 로드셀 무게 변화 감지 (io_board :8001)
    - 10채널 중 특정 채널에서 변화 감지
    - threshold (5g) 초과 시 이벤트 발생
        │
        │ SSE: loadcell.change
        │ {zone_id: 0, delta_weight: -365, channels: [0,1],
        │  before_weights: [...], after_weights: [...]}
        ▼
[3] ★ Node.js SSE 수신 (IOBoardSSESubscriber.js)
    - 무게 변화 감지 (threshold: 50g)
    - 디바운스 처리 (500ms)
    - Zone ID 확인
        │
        ▼
[4] ★ Node.js → Camera Driver 스냅샷 요청
    - POST /api/zone/{zone_id}/snapshot
    - session_id 생성 (타임스탬프)
    - include_top: true (Top 카메라 포함)
        │
        │ 스냅샷 저장 경로: /data/snapshots/{session_id}/
        ▼
[5] ★ Node.js → Model 서비스 판단 요청
    - POST /api/judge
    - weight_data: {before_weights, after_weights, delta_weight, channels}
    - media_paths: {image_folder, top_image, side_image}
        │
        ▼
[6] Model 서비스 Vision 파이프라인 (Stateless)
    ┌─────────────────────────────────────────────┐
    │  6.1 이미지 로드 (media_paths에서)           │
    │      - Top 카메라 이미지                     │
    │      - Side 카메라 이미지                    │
    │                                             │
    │  6.2 YOLO 추론                               │
    │      - 손(hand) 감지                         │
    │      - 상품(products) 감지                   │
    │                                             │
    │  6.3 Hand Filter (ROI)                      │
    │      - 손과 가장 가까운 상품 필터링            │
    │                                             │
    │  6.4 Top-K 추출 + Multi-View Ensemble       │
    │      - 최고 confidence 상품 1개 추출         │
    │      - Top + Side 카메라 결과 결합 (5:5)     │
    └─────────────────────────────────────────────┘
        │
        │ Vision 후보: [chickenmayo_rice: 0.90]
        ▼
[7] Model 서비스 Weight Validation
    ┌─────────────────────────────────────────────┐
    │  Vision 후보 × 무게 변화량 매칭               │
    │                                             │
    │  - delta_weight = -365g (weight_data에서)   │
    │  - candidate: chickenmayo_rice (365g)       │
    │  - count = 365 / 365 = 1개                  │
    │  - tolerance (10%) 이내 → ✓ VALIDATED       │
    └─────────────────────────────────────────────┘
        │
        ▼
[8] Model 서비스 → Node.js 결과 반환
    - HTTP Response (동기)
    - status: "complete" (confidence > 0.7)
    - products: [{chickenmayo_rice, count: 1, price: 3500}]
        │
        ▼
[9] Node.js 결과 처리
    - 결제 처리 진행
    - Frontend SSE 알림
    - MQTT 재고 업데이트 (IF04)
```

### 7.2 Zone-채널-카메라 매핑

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ZONE - CHANNEL - CAMERA MAPPING                   │
└─────────────────────────────────────────────────────────────────────┘

Zone 0 (1단)
├── LoadCell: Channel 0, 1
├── Side Camera: CAM 1
└── Top Camera: CAM 0 (공유)

Zone 1 (2단)
├── LoadCell: Channel 2, 3
├── Side Camera: CAM 2
└── Top Camera: CAM 0 (공유)

Zone 2 (3단)
├── LoadCell: Channel 4, 5
├── Side Camera: CAM 3
└── Top Camera: CAM 0 (공유)

Zone 3 (4단)
├── LoadCell: Channel 6, 7
├── Side Camera: CAM 4
└── Top Camera: CAM 0 (공유)

Zone 4 (5단)
├── LoadCell: Channel 8, 9
├── Side Camera: CAM 5
└── Top Camera: CAM 0 (공유)

┌──────────────────────────────────────────────────────────────────┐
│                                                                   │
│   ┌─────┐  Top Camera (CAM 0) - 전체 상단 뷰                      │
│   │     │                                                         │
│   │  0  │  ← 모든 Zone 공유                                       │
│   │     │                                                         │
│   └─────┘                                                         │
│                                                                   │
│   ┌─────┬─────┬─────┬─────┬─────┐  Side Cameras                  │
│   │  1  │  2  │  3  │  4  │  5  │                                │
│   │Zone0│Zone1│Zone2│Zone3│Zone4│                                │
│   └─────┴─────┴─────┴─────┴─────┘                                │
│                                                                   │
│   ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐  │
│   │ LC0 │ LC1 │ LC2 │ LC3 │ LC4 │ LC5 │ LC6 │ LC7 │ LC8 │ LC9 │  │
│   └──┬──┴──┬──┴──┬──┴──┬──┴──┬──┴──┬──┴──┬──┴──┬──┴──┬──┴──┬──┘  │
│      └──┬──┘     └──┬──┘     └──┬──┘     └──┬──┘     └──┬──┘      │
│       Zone0      Zone1      Zone2      Zone3      Zone4          │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 8. 트러블슈팅

### 8.1 자주 발생하는 문제

#### YOLO 모델 로드 실패
```
Error: Model file not found
```
**해결**: `siyeon_best.pt` 파일이 프로젝트 루트에 있는지 확인
```bash
# ecosystem.config.js의 YOLO_MODEL_PATH 확인
YOLO_MODEL_PATH: "../../../siyeon_best.pt"
```

#### io_board 연결 실패
```
Error: Connection refused to localhost:8001
```
**해결**: io_board 서비스가 먼저 실행되어야 함
```bash
pm2 start ecosystem.config.js --only io-board
pm2 logs io-board
```

#### 카메라 연결 실패
```
Error: Camera 0 not available
```
**해결**: USB 카메라 연결 확인, 권한 확인
```bash
# Windows: 장치 관리자에서 카메라 확인
# Linux: /dev/video* 권한 확인
```

#### SSE 연결 끊김
```
Warning: SSE connection lost, reconnecting...
```
**해결**: io_board 서비스 상태 확인, 네트워크 확인

### 8.2 로그 확인 방법

```bash
# PM2 로그 (전체)
pm2 logs

# 특정 서비스 로그
pm2 logs model --lines 100

# 실시간 로그 팔로우
pm2 logs model --follow

# 에러 로그만
pm2 logs model --err
```

### 8.3 서비스 재시작

```bash
# 단일 서비스 재시작
pm2 restart model

# 전체 재시작
pm2 restart all

# 완전 초기화 후 재시작
pm2 delete all
pm2 start ecosystem.config.js
```

---

## 부록: 설정 파일 요약

### ecosystem.config.js
```javascript
module.exports = {
  apps: [
    { name: "orchestrator", script: "./server/index.js", ... },
    { name: "io-board", cwd: "./services/io_board", script: "python", args: "main.py", ... },
    { name: "model", cwd: "./services/model", script: "python", args: "main.py",
      env: { YOLO_MODEL_PATH: "../../../siyeon_best.pt" }, ... },
    { name: "camera-driver", cwd: "./services/camera_driver", script: "python", args: "main.py", ... },
    { name: "card-terminal", cwd: "./services/card_terminal", script: "python", args: "main.py", ... },
  ]
};
```

### services/model/src/config.py
```python
ZONE_CHANNEL_MAP = {0: [0,1], 1: [2,3], 2: [4,5], 3: [6,7], 4: [8,9]}
ZONE_CAMERA_MAP = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5}
TOP_CAMERA_ID = 0

top_k = 1                 # Top-1만 추출
top_weight = 0.5          # Top 카메라 가중치
side_weight = 0.5         # Side 카메라 가중치
tolerance_percent = 0.10  # 허용 오차 10%
```

---

> **문의**: minkyu 브랜치 담당자
> **최종 업데이트**: 2026-01-26

---

## 9. 최신 업데이트

### 9.1 Event-Driven Architecture (2026-01-29) ★ 최신

**Node.js 세션 관리 강화:**
- `WeightChangeAccumulator`: 무게 변화 이벤트 누적 처리
- `PendingItemsStack`: 데드볼트 열림/닫힘 기반 세션 관리
- 정산 처리: 데드볼트 닫힘 후 15초 대기 → 픽업/반환 정산

**Motion Tracking:**
- `src/vision/motion_correlation_filter.py` 추가
- 연속 프레임 분석으로 손 움직임 추적
- `motion_bonus_map`으로 신뢰도 보정

**추론 취소 기능:**
- `POST /api/judge/cancel`: 진행 중인 추론 취소
- `GET /api/judge/active`: 활성 추론 목록 조회
- 새로운 무게 이벤트 발생 시 기존 추론 취소 가능

**카메라별 결과 반환:**
```json
{
  "camera_results": {
    "cam0": {"detected": true, "confidence": 0.85, "candidates": [...]},
    "cam1": {"detected": true, "confidence": 0.78, "candidates": [...]}
  }
}
```

### 9.2 통합 실행 (2026-01-28)

**PM2로 전체 서비스 실행:**
```bash
npm start   # pm2 start ecosystem.config.js
```

**서비스 목록 (ecosystem.config.js):**
| 서비스 | 포트 | 설명 |
|--------|------|------|
| orchestrator | 8889 | Node.js 오케스트레이터 |
| client | 3000 | React 대시보드 |
| io-board | 8001 | 로드셀 + 데드볼트 |
| model | 8002 | AI 상품 판단 |
| camera-driver | 8003 | 카메라 관리 |
| mqtt-client | 8006 | MQTT IF01-04 |
| card-terminal | 5000 | 결제 터미널 |

### 9.3 아키텍처 변경 (2026-01-26)

**Model 서비스 Stateless 전환:**
- `src/sse_client/` 폴더 삭제 (io_board SSE 구독 제거)
- `src/api/node_client.py` 삭제 (결과 푸시 → 동기 응답으로 변경)
- Node.js가 모든 흐름 제어 담당

**새로운 API 요청 형식:**
```json
{
  "zone_id": 0,
  "weight_data": {
    "before_weights": [1000, 1005, 0, 0, 0, 0, 0, 0, 0, 0],
    "after_weights": [480, 505, 0, 0, 0, 0, 0, 0, 0, 0],
    "delta_weight": -520,
    "channels": [0, 1]
  },
  "media_paths": {
    "image_folder": "/data/snapshots/260126143025",
    "top_image": "...",
    "side_image": "..."
  }
}
```

### 9.4 Node.js 서비스 파일

| 파일 | 역할 |
|------|------|
| `IOBoardSSESubscriber.js` | SSE 구독 + 세션 관리 + 무게 감지 |
| `CameraDriverClient.js` | 스냅샷/녹화 요청 |
| `ProductJudgeClient.js` | Model 판단 요청 |
| `ConfigManager.js` | Zone 설정 관리 |
| `WeightChangeAccumulator.js` | 무게 변화 누적 ★ |
| `PendingItemsStack.js` | 세션별 픽업/반환 관리 ★ |
| `ScheduledLogger.js` | 스케줄 로깅 |

### 9.5 에러 코드 체계

| 범위 | 서비스 | 예시 |
|------|--------|------|
| E2xxx | io_board | E2001(포트 없음), E2005(타임아웃) |
| E3xxx | camera | E3001(연결 실패), E3006(매핑 실패) |
| E4xxx | vision | E4001(모델 로드 실패), E4002(추론 실패) |
| E5xxx | network | E5001(SSE 실패), E5003(Node.js 실패) |
| E6xxx | payment | E6001(단말기 연결 실패), E6004(네트워크) |

### 9.6 Door Payment 모듈

Model 서비스에 도어 결제 모듈이 추가되었습니다.

**API 엔드포인트:**
```
POST /api/door/transaction      # 결제 시작
GET  /api/door/status           # 도어 상태
POST /api/door/cancel           # 거래 취소
POST /api/door/emergency-lock   # 비상 잠금
```

---

> **문의**: minkyu 브랜치 담당자
> **최종 업데이트**: 2026-01-29
