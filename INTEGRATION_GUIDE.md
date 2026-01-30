# Camera & Model 서비스 통합 가이드

> **작성일**: 2026-01-30 (최종 업데이트)
> **대상**: Camera Driver + Model 서비스 개발자

---

## 목차

1. [시스템 개요](#1-시스템-개요)
2. [서비스 구조](#2-서비스-구조)
3. [다른 레포와 연동](#3-다른-레포와-연동)
4. [테스트 방법](#4-테스트-방법)
5. [API 레퍼런스](#5-api-레퍼런스)
6. [트러블슈팅](#6-트러블슈팅)

---

## 1. 시스템 개요

### 1.1 아키텍처

이 레포는 **Camera Driver**와 **Model** 서비스만 관리합니다.
Node.js, IO Board, Payment는 별도 레포에서 관리됩니다.

```
다른 레포들                              이 레포 (경량화 버전)
┌─────────────────────────────┐          ┌─────────────────────────────┐
│ Edge_Environment            │          │                             │
│ ├── Node.js (8888) ★        │◄────────►│ React Client (3000)         │
│ ├── server/                 │          │   - setupProxy → 8888       │
│ └── services/mqtt_client/   │          │                             │
├─────────────────────────────┤          ├─────────────────────────────┤
│ CRK-IO-BOARD               │          │ Camera Driver (8003)        │
│ └── io_board (8000)         │◄────────►│   - 스냅샷/녹화 제공        │
├─────────────────────────────┤          │   - SSE 이벤트 구독         │
│ CRK-PAYMENT                 │          ├─────────────────────────────┤
│ └── card_terminal (5000)    │          │ Model Service (8002)        │
└─────────────────────────────┘          │   - YOLO 추론               │
                                         │   - 상품 판단               │
                                         └─────────────────────────────┘
```

### 1.2 서비스 포트

| 서비스 | 포트 | 관리 레포 | 역할 |
|--------|------|-----------|------|
| **Model** | 8002 | 이 레포 | AI 상품 판단 (YOLO + Weight) |
| **Camera Driver** | 8003 | 이 레포 | 6대 카메라 관리 |
| **React Client** | 3000 | 이 레포 | 웹 대시보드 |
| Node.js | 8888 | Edge_Environment | 오케스트레이터 |
| IO Board | 8000 | CRK-IO-BOARD | 로드셀 + 데드볼트 |
| Payment | 5000 | CRK-PAYMENT | 결제 터미널 |

---

## 2. 서비스 구조

### 2.1 디렉토리 구조

```
Edge_Environment/
├── services/
│   ├── camera_driver/             # 카메라 서비스 (8003)
│   │   ├── main.py                # FastAPI 진입점
│   │   └── src/
│   │       ├── core/
│   │       │   ├── camera.py      # 카메라 추상화
│   │       │   ├── manager.py     # 카메라 관리자
│   │       │   └── event_recording_manager.py  # 이벤트 녹화
│   │       ├── api/
│   │       │   ├── routes.py      # REST API
│   │       │   └── manager.py     # API 관리자
│   │       └── models.py          # Pydantic 스키마
│   │
│   └── model/                     # AI 판단 서비스 (8002)
│       ├── main.py                # FastAPI 진입점
│       └── src/
│           ├── api/               # REST API
│           │   ├── routes.py
│           │   └── models.py
│           ├── vision/            # YOLO 추론
│           │   ├── yolo_wrapper.py
│           │   ├── hand_filter.py
│           │   └── multi_view_ensemble.py
│           ├── weight/            # 무게 계산
│           │   └── count_calculator.py
│           ├── engine/            # 판단 엔진
│           │   └── decision_engine.py
│           └── database/          # 상품 DB
│               └── product_db.py
│
├── client/                        # React Frontend (3000)
│   ├── src/
│   │   └── setupProxy.js          # API 프록시 → 8888
│   └── public/
│
├── config/
│   ├── zone_mapping.json          # Zone-Channel-Camera 매핑
│   └── camera_device_map.json     # 카메라 디바이스 매핑
│
├── _archive/                      # 아카이빙 (다른 레포로 이관)
│   ├── io_board/
│   ├── card_terminal/
│   ├── mqtt_client/
│   └── server/
│
├── ecosystem.config.js            # PM2 설정
└── package.json
```

### 2.2 Model 서비스 상세 (Stateless)

Model 서비스는 **Stateless** 방식으로 동작합니다.
- SSE 구독 없음
- 요청-응답 방식만 지원
- Node.js가 모든 흐름 제어

```
services/model/src/
├── api/
│   ├── routes.py          # /api/judge, /api/products
│   └── models.py          # WeightData, MediaPaths
├── vision/
│   ├── yolo_wrapper.py    # YOLO 모델 래퍼
│   ├── hand_filter.py     # 손 근접 필터
│   └── multi_view_ensemble.py  # Top+Side 앙상블
├── weight/
│   └── count_calculator.py     # 개수 계산
├── engine/
│   └── decision_engine.py      # 판단 로직
└── database/
    └── product_db.py           # IF11 상품 DB
```

---

## 3. 다른 레포와 연동

### 3.1 데이터 흐름

```
1. IO Board SSE → Node.js (loadcell.change 이벤트)
2. Node.js → Camera Driver (스냅샷 요청)
3. Node.js → Model (weight_data + media_paths 전달)
4. Model → Node.js (판단 결과 반환)
```

### 3.2 Node.js가 호출하는 API

#### Camera Driver (8003)

```javascript
// 스냅샷 요청
POST http://localhost:8003/api/zone/0/snapshot
{
    "session_id": "260130143025",
    "include_top": true
}

// 응답
{
    "success": true,
    "folder": "/data/snapshots/260130143025",
    "top_image": "cam_0/snapshot.jpg",
    "side_image": "cam_1/snapshot.jpg"
}
```

#### Model (8002)

```javascript
// 상품 판단 요청
POST http://localhost:8002/api/judge
{
    "zone_id": 0,
    "weight_data": {
        "before_weights": [1000, 1005, 0, 0, 0, 0, 0, 0, 0, 0],
        "after_weights": [480, 505, 0, 0, 0, 0, 0, 0, 0, 0],
        "delta_weight": -520,
        "channels": [0, 1]
    },
    "media_paths": {
        "image_folder": "/data/snapshots/260130143025"
    }
}

// 응답
{
    "success": true,
    "products": [{
        "productId": 26,
        "name": "chickenmayo_rice",
        "count": 1,
        "unitPrice": 3500,
        "totalPrice": 3500,
        "confidence": 0.91
    }],
    "status": "complete",
    "confidence": 0.91
}
```

### 3.3 React Client 프록시 설정

`client/src/setupProxy.js`가 API 요청을 Node.js(8888)로 프록시합니다:

```javascript
// /api/* → http://localhost:8888
// /sse/* → http://localhost:8888
// /health → http://localhost:8888
```

따라서 다른 레포의 Node.js가 8888에서 실행되어야 Client가 정상 동작합니다.

---

## 4. 테스트 방법

### 4.1 헬스 체크

```bash
# 이 레포 서비스
curl http://localhost:8002/api/health  # Model
curl http://localhost:8003/api/health  # Camera

# 다른 레포 서비스 (선택)
curl http://localhost:8888/health      # Node.js
curl http://localhost:8000/health      # IO Board
```

### 4.2 Model 단독 테스트

```bash
# 상품 판단 (레거시 형식)
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 0, "delta_weight": -520}'

# 상품 판단 (권장 형식)
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 0,
    "weight_data": {
      "delta_weight": -520,
      "channels": [0, 1]
    },
    "media_paths": {
      "image_folder": "data/test_images"
    }
  }'
```

### 4.3 Camera Driver 테스트

```bash
# 카메라 상태
curl http://localhost:8003/api/status

# 스냅샷 캡처
curl -X POST http://localhost:8003/api/zone/0/snapshot \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test123", "include_top": true}'

# 디바이스 스캔
curl http://localhost:8003/api/devices/scan
```

### 4.4 오프라인 테스트 (Vision 파이프라인)

```bash
cd services/model

# 데이터셋 테스트
python -m src.tests.test_offline_dataset

# 특정 세션만
python -m src.tests.test_offline_dataset --session 20260116_180419

# 시각화 저장
python -m src.tests.test_offline_dataset --visualize --output-dir ./viz_results
```

---

## 5. API 레퍼런스

### 5.1 Model Service (8002)

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | /api/health | 헬스 체크 |
| POST | /api/judge | 상품 판단 |
| POST | /api/judge/cancel | 추론 취소 |
| GET | /api/products | 상품 목록 |
| POST | /api/products/register | 상품 등록 |
| POST | /api/products/sync | IF11 동기화 |

#### POST /api/judge

**요청 (권장 형식):**
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
        "image_folder": "/data/snapshots/session123"
    }
}
```

**응답:**
```json
{
    "success": true,
    "products": [{
        "productId": 26,
        "name": "chickenmayo_rice",
        "count": 1,
        "unitPrice": 3500,
        "totalPrice": 3500,
        "confidence": 0.91
    }],
    "totalPrice": 3500,
    "status": "complete",
    "confidence": 0.91,
    "isRemoval": true,
    "zoneId": 0
}
```

### 5.2 Camera Driver (8003)

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | /api/health | 헬스 체크 |
| GET | /api/status | 카메라 상태 |
| GET | /api/cameras | 카메라 목록 |
| POST | /api/zone/{id}/activate | Zone 활성화 |
| POST | /api/zone/{id}/deactivate | Zone 비활성화 |
| POST | /api/zone/{id}/snapshot | 스냅샷 캡처 |
| GET | /api/devices/scan | 디바이스 스캔 |
| POST | /api/recording/start | 녹화 시작 |
| POST | /api/recording/stop | 녹화 중지 |

#### POST /api/zone/{id}/snapshot

**요청:**
```json
{
    "session_id": "260130143025",
    "include_top": true
}
```

**응답:**
```json
{
    "success": true,
    "zone_id": 0,
    "folder": "/data/snapshots/260130143025",
    "top_image": "cam_0/snapshot.jpg",
    "side_image": "cam_1/snapshot.jpg",
    "timestamp": "2026-01-30T14:30:25.123Z"
}
```

---

## 6. 트러블슈팅

### 6.1 자주 발생하는 문제

#### Model 서비스 시작 실패

```
Error: Model file not found
```

**해결:**
```bash
# YOLO 모델 경로 확인
ls ./models/siyeon_best.pt

# 환경변수 설정
export MODEL__VISION__YOLO_MODEL_PATH=./models/siyeon_best.pt
```

#### 카메라 연결 실패

```
Error: Camera 0 not available
```

**해결:**
```bash
# Windows: 장치 관리자에서 카메라 확인
# Jetson: NVIDIA_MODE=true 설정

# 디바이스 스캔
curl http://localhost:8003/api/devices/scan
```

#### Node.js 연결 실패

```
Error: Connection refused to localhost:8888
```

**해결:** 다른 레포(Edge_Environment)에서 Node.js 서비스 실행 필요

### 6.2 로그 확인

```bash
# PM2 로그
pm2 logs model
pm2 logs camera-driver

# 실시간 로그
pm2 logs --follow
```

### 6.3 서비스 재시작

```bash
# 개별 재시작
pm2 restart model
pm2 restart camera-driver

# 전체 재시작
pm2 restart all

# 완전 초기화
pm2 delete all
npm run services
```

---

## 부록: Zone-채널-카메라 매핑

```
Zone 0 ─ LoadCell [0,1] ─ Side Camera 1 ─ Top Camera 0
Zone 1 ─ LoadCell [2,3] ─ Side Camera 2 ─ Top Camera 0
Zone 2 ─ LoadCell [4,5] ─ Side Camera 3 ─ Top Camera 0
Zone 3 ─ LoadCell [6,7] ─ Side Camera 4 ─ Top Camera 0
Zone 4 ─ LoadCell [8,9] ─ Side Camera 5 ─ Top Camera 0
```

---

> **문의**: minkyu 브랜치 담당자
> **최종 업데이트**: 2026-01-30
