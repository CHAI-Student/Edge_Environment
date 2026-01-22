# Edge Environment 통합 가이드

> **작성일**: 2026-01-22
> **작성자**: minkyu 브랜치
> **대상**: Node.js 총괄 담당자 및 개발팀

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

### 1.1 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    AI Smart Vending Machine System                       │
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
│   └──────┬──────┘     └──────┬──────┘     └──────┬──────┘               │
│          │                   │                   │                       │
│          │   SSE (실시간)     │   HTTP            │                       │
│          ▼                   ▼                   │                       │
│   ┌─────────────────────────────────┐           │                       │
│   │         model :8002             │           │                       │
│   │   (AI 상품 판단 + 센서 퓨전)      │           │                       │
│   │                                 │           │                       │
│   │   Vision + Weight → 상품 결정    │           │                       │
│   └──────────────┬──────────────────┘           │                       │
│                  │                              │                       │
│                  │   HTTP POST (판단 결과)       │                       │
│                  ▼                              ▼                       │
│   ┌─────────────────────────────────────────────────────────┐           │
│   │              Node.js Orchestrator :8888                  │           │
│   │                                                          │           │
│   │   - 전체 흐름 제어                                        │           │
│   │   - MQTT 브로커 연동 (CHAI IF01-07)                       │           │
│   │   - 결제 처리                                             │           │
│   │   - Frontend 통신                                        │           │
│   └──────────────────────────────────────────────────────────┘           │
│                  │                                                       │
│                  ▼                                                       │
│   ┌─────────────────────────────────────────────────────────┐           │
│   │              mqtt_client :8006                           │           │
│   │              (MQTT CHAI IF01-04)                         │           │
│   └─────────────────────────────────────────────────────────┘           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 서비스 포트 구성

| 서비스 | 포트 | 언어 | 역할 |
|--------|------|------|------|
| **orchestrator** | 8888 | Node.js | 전체 흐름 제어, MQTT, Frontend API |
| **io_board** | 8001 | Python | 로드셀 10채널 + 데드볼트 제어 |
| **model** | 8002 | Python | AI 상품 판단 (Vision + Weight 퓨전) |
| **camera_driver** | 8003 | Python | 6대 카메라 관리 |
| **card_terminal** | 5000 | Python | 결제 터미널 |
| **mqtt_client** | 8006 | Python | MQTT 브로커 연동 |

---

## 2. 서비스 구조

### 2.1 디렉토리 구조

```
Edge_Environment/
├── server/                         # Node.js Orchestrator
│   ├── index.js                    # Express 진입점 (포트 8888)
│   ├── config/
│   │   ├── key.js                  # 환경 설정 라우터
│   │   ├── dev.js                  # 개발 환경 (MQTT, API 등)
│   │   └── prod.js                 # 프로덕션 환경
│   ├── routes/
│   │   ├── auth.js                 # JWT 인증
│   │   ├── mqtt.js                 # MQTT 라우팅
│   │   └── RestAPI/                # REST API 모듈
│   └── services/
│       ├── IOBoardClient.js        # io_board HTTP 클라이언트
│       └── ProductJudgeClient.js   # model 서비스 HTTP 클라이언트
│
├── services/                       # Python 마이크로서비스
│   ├── io_board/                   # 로드셀 + 데드볼트 (8001)
│   ├── model/                      # AI 상품 판단 (8002) ★
│   ├── camera_driver/              # 카메라 관리 (8003)
│   ├── mqtt_client/                # MQTT 클라이언트 (8006)
│   └── card_terminal/              # 결제 터미널 (5000)
│
├── client/                         # React Frontend
├── ecosystem.config.js             # PM2 설정
├── package.json                    # Node.js 의존성
└── .env                            # 환경 변수
```

### 2.2 Model 서비스 상세 구조

```
services/model/
├── main.py                         # FastAPI 진입점
├── config.py                       # 설정 (Zone 매핑, 파라미터)
├── requirements.txt                # Python 의존성
│
├── api/                            # REST API
│   ├── routes.py                   # 엔드포인트 정의
│   ├── models.py                   # Pydantic 스키마
│   └── node_client.py              # Node.js 결과 전송
│
├── sse_client/                     # io_board 실시간 구독
│   ├── io_board_subscriber.py      # SSE 스트림 리스너
│   ├── event_parser.py             # 이벤트 파싱
│   └── zone_detector.py            # 채널 → Zone 매핑
│
├── camera/                         # 이미지 캡처
│   ├── camera_client.py            # camera_driver API
│   └── frame_capturer.py           # 프레임 로더
│
├── vision/                         # YOLO 추론
│   ├── yolo_wrapper.py             # YOLO 모델 래퍼
│   ├── hand_filter.py              # 손 근접 필터
│   ├── top5_extractor.py           # Top-K 추출
│   └── multi_view_ensemble.py      # Top+Side 앙상블
│
├── weight/                         # 무게 계산
│   ├── count_calculator.py         # 개수 계산
│   └── multi_zone_monitor.py       # 다중 Zone 모니터링
│
├── engine/                         # 판단 엔진
│   ├── decision_engine.py          # 핵심 판단 로직
│   ├── event_tracker.py            # 이벤트 추적
│   └── advanced/                   # 고급 시나리오
│       ├── return_detector.py      # 반환 감지
│       ├── cross_zone_detector.py  # Zone 간 이동
│       └── rapid_pickup_handler.py # 연속 픽업
│
├── database/                       # 상품 DB
│   └── product_db.py
│
├── monitor/                        # 테스트 대시보드
│   ├── console_dashboard.py
│   └── test_mode.py
│
└── tests/                          # 테스트
    ├── test_offline_dataset.py     # 오프라인 테스트
    └── test_hardware_integration.py # 하드웨어 테스트
```

---

## 3. Node.js 연동 가이드

### 3.1 Model 서비스 연동 방법

Node.js Orchestrator는 두 가지 방식으로 Model 서비스와 통신합니다:

#### 방식 1: Model → Node.js (실시간 이벤트 기반)

```
io_board (SSE) → model (판단) → Node.js (결과 수신)
```

Model 서비스가 io_board의 SSE 스트림을 구독하고, 무게 변화 감지 시 자동으로 상품 판단 후 Node.js에 결과를 전송합니다.

**Node.js에서 수신해야 할 엔드포인트:**
```javascript
// server/routes/sensor.js (예시)
app.post('/api/sensor/judgment', (req, res) => {
    const result = req.body;
    /*
    result 구조:
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
        "status": "complete",    // "complete" | "partial" | "uncertain"
        "confidence": 0.91,
        "weightInfo": {
            "delta": -365.0,
            "explained": 365.0,
            "residual": 0.0
        },
        "isRemoval": true,       // true=픽업, false=반환
        "zoneId": 0,
        "timestamp": 1737450000.123
    }
    */

    // 결과 처리 로직
    if (result.status === 'complete') {
        // 확실한 판단 - 바로 결제 진행
        processPayment(result.products);
    } else if (result.status === 'partial') {
        // 부분 판단 - 사용자 확인 필요
        requestUserConfirmation(result);
    } else {
        // 불확실 - 재시도 또는 수동 처리
        handleUncertainJudgment(result);
    }

    res.json({ received: true });
});
```

#### 방식 2: Node.js → Model (직접 요청)

Node.js에서 특정 시점에 직접 상품 판단을 요청할 수 있습니다.

**ProductJudgeClient 사용 (services/ProductJudgeClient.js):**
```javascript
const axios = require('axios');

class ProductJudgeClient {
    constructor(baseUrl = 'http://localhost:8002') {
        this.baseUrl = baseUrl;
    }

    // 단일 Zone 상품 판단
    async judge(zoneId, deltaWeight, options = {}) {
        const response = await axios.post(`${this.baseUrl}/api/judge`, {
            zone_id: zoneId,
            delta_weight: deltaWeight,
            ...options
        });
        return response.data;
    }

    // 다중 Zone 동시 판단 (Cross-Zone 감지)
    async judgeMultiZone(zoneDeltas, checkCrossZone = true) {
        const response = await axios.post(`${this.baseUrl}/api/judge/multi-zone`, {
            zone_deltas: zoneDeltas,
            check_cross_zone: checkCrossZone
        });
        return response.data;
    }

    // 히스토리 기반 판단 (반환 감지)
    async judgeWithHistory(currentRequest, recentEvents, options = {}) {
        const response = await axios.post(`${this.baseUrl}/api/judge/with-history`, {
            current_request: currentRequest,
            recent_events: recentEvents,
            check_return: options.checkReturn || true,
            check_rapid_pickup: options.checkRapidPickup || false
        });
        return response.data;
    }

    // 헬스 체크
    async health() {
        const response = await axios.get(`${this.baseUrl}/api/health`);
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

**사용 예시:**
```javascript
const ProductJudgeClient = require('./services/ProductJudgeClient');
const judgeClient = new ProductJudgeClient('http://localhost:8002');

// 단일 Zone 판단
router.post('/judge', async (req, res) => {
    try {
        const result = await judgeClient.judge(
            req.body.zoneId,     // Zone 0-4
            req.body.deltaWeight // 무게 변화량 (음수=픽업, 양수=반환)
        );
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
python -m tests.test_offline_dataset

# 3. 특정 세션만 테스트
python -m tests.test_offline_dataset --session 20260116_180419

# 4. 특정 프레임만 테스트
python -m tests.test_offline_dataset --session 20260116_180419 --frame 10

# 5. 시각화 결과 저장
python -m tests.test_offline_dataset --visualize --output-dir ./viz_results

# 6. JSON 결과 저장
python -m tests.test_offline_dataset --output results.json

# 7. 커스텀 모델/데이터셋 경로
python -m tests.test_offline_dataset \
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
python -m tests.test_hardware_integration --check-connection

# 2. SSE 이벤트 모니터링 (로드셀 변화 감지 확인)
python -m tests.test_hardware_integration --monitor-sse --duration 10

# 3. Zone별 카메라 캡처 테스트
python -m tests.test_hardware_integration --capture-zone 1

# 4. 전체 Zone 스캔
python -m tests.test_hardware_integration --scan-all-zones

# 5. 수동 판단 테스트 (특정 무게 변화 시뮬레이션)
python -m tests.test_hardware_integration --manual-judge --zone 1 --delta -365

# 6. 실시간 모니터링 + 자동 판단
python -m tests.test_hardware_integration --realtime-monitor --duration 60

# 7. 정확도 테스트 (반복 측정)
python -m tests.test_hardware_integration --accuracy-test --zone 1 --repeat 10

# 8. 특정 상품 정확도 테스트
python -m tests.test_hardware_integration \
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
python main.py
# 또는
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

#### model 서비스
```bash
cd Edge_Environment/services/model
uvicorn main:app --host 0.0.0.0 --port 8002 --reload
```

#### camera_driver 서비스
```bash
cd Edge_Environment/services/camera_driver
uvicorn main:app --host 0.0.0.0 --port 8003 --reload
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

#### 상품 판단 (기본)
```http
POST /api/judge
Content-Type: application/json

{
    "zone_id": 0,
    "delta_weight": -365.0,
    "loadcell_weights": ["+00267", "+00268", "+00000", ...],
    "baseline_weights": ["+00432", "+00433", "+00000", ...]
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

### 7.1 실시간 상품 판단 흐름

```
┌──────────────────────────────────────────────────────────────────────┐
│                    REAL-TIME PRODUCT JUDGMENT FLOW                    │
└──────────────────────────────────────────────────────────────────────┘

[1] 손님이 상품을 집음
        │
        ▼
[2] 로드셀 무게 변화 감지 (io_board)
    - 10채널 중 특정 채널에서 변화 감지
    - threshold (5g) 초과 시 이벤트 발생
        │
        │ SSE: loadcell.change
        │ {changed_indices: [0,1], deltas: [-180,-185]}
        ▼
[3] Zone 감지 (model - zone_detector)
    - 채널 [0,1] → Zone 0
    - 채널 [2,3] → Zone 1
    - ...
        │
        ▼
[4] 카메라 프레임 캡처 (camera_driver)
    - Top 카메라 (CAM 0) - 전체 뷰
    - Side 카메라 (Zone별) - 상세 뷰
        │
        ▼
[5] Vision 파이프라인 (model - vision/)
    ┌─────────────────────────────────────────────┐
    │  5.1 YOLO 추론                               │
    │      - 손(hand) 감지                         │
    │      - 상품(products) 감지                   │
    │                                             │
    │  5.2 Hand Filter (ROI)                      │
    │      - 손과 가장 가까운 상품 필터링            │
    │                                             │
    │  5.3 Top-K 추출                             │
    │      - 최고 confidence 상품 1개 추출         │
    │      (config: top_k=1)                      │
    │                                             │
    │  5.4 Multi-View Ensemble                    │
    │      - Top + Side 카메라 결과 결합           │
    │      - 가중치: 5:5 (동일)                    │
    │      - 양쪽에서 감지된 클래스 우선            │
    └─────────────────────────────────────────────┘
        │
        │ Vision 후보: [chickenmayo_rice: 0.90]
        ▼
[6] Weight Validation (model - weight/)
    ┌─────────────────────────────────────────────┐
    │  Vision 후보 × 무게 변화량 매칭               │
    │                                             │
    │  - delta_weight = -365g (로드셀에서)         │
    │  - candidate: chickenmayo_rice (365g)       │
    │  - count = 365 / 365 = 1개                  │
    │  - error = |365 - 365| / 365 = 0%           │
    │  - tolerance (10%) 이내 → ✓ VALIDATED       │
    └─────────────────────────────────────────────┘
        │
        ▼
[7] 최종 판단 결정 (model - decision_engine)
    - status: "complete" (confidence > 0.7)
    - products: [{chickenmayo_rice, count: 1, price: 3500}]
        │
        │ HTTP POST /api/sensor/judgment
        ▼
[8] Node.js Orchestrator 수신
    - 결제 처리 진행
    - Frontend 알림
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
    { name: "model", cwd: "./services/model",
      args: "-m uvicorn main:app --host 0.0.0.0 --port 8002",
      env: { YOLO_MODEL_PATH: "../../../siyeon_best.pt" }, ... },
    { name: "camera-driver", cwd: "./services/camera_driver", ... },
    { name: "card-terminal", cwd: "./services/card_terminal", ... },
  ]
};
```

### services/model/config.py
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
> **최종 업데이트**: 2026-01-22
