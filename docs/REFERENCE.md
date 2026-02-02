# API Reference (v4.1)

Model Service API 상세 스펙

> **최종 업데이트**: 2026-02-02

---

## 1. Health Check

### GET /api/health

서비스 상태 확인.

**Response:**
```json
{
  "model": "HEALTHY",
  "status": "ok",
  "yolo_loaded": true,
  "session_store_ready": true,
  "door_session_store_ready": true
}
```

### GET /api/health/detailed

상세 서비스 상태 확인.

**Response:**
```json
{
  "model": "HEALTHY",
  "status": "ok",
  "yolo_loaded": true,
  "yolo_model_path": "models/siyeon_best.engine",
  "session_store_ready": true,
  "door_session_store_ready": true,
  "uptime_seconds": 3600.5,
  "memory_usage_mb": 512.3
}
```

---

## 2. Trigger API

### POST /trigger

Camera에서 AVI 녹화 완료 시 호출.

**Request:**
```json
{
  "zone": 1,
  "loadcells": [
    {
      "timestamp": "2026-02-02T14:30:25.123Z",
      "raw_value": ["+12345", "+12345"],
      "filtered_value": ["+12344", "+12346"],
      "filter_method": "none"
    }
  ],
  "videos": {
    "top": "/data/videos/top.avi",
    "side": "/data/videos/side.avi"
  }
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| zone | int | O | Zone 번호 |
| loadcells | array | O | 로드셀 데이터 배열 |
| videos | object | O | 비디오 파일 경로 (top/side) |

**Response (성공):**
```json
{
  "success": true,
  "session_id": "zone_1_260202_143025",
  "door_session_id": "door_zone_1_260202_143000",
  "message": "추론 완료",
  "processing_time_ms": 1500.5
}
```

**Response (에러):**
```json
{
  "detail": {
    "error_code": "VIDEO_FILE_NOT_FOUND",
    "message": "Video file not found: /path/to/video.avi",
    "video_path": "/path/to/video.avi"
  }
}
```

| 에러 코드 | HTTP | 설명 |
|----------|------|------|
| VIDEO_FILE_NOT_FOUND | 400 | 비디오 파일 없음 |
| VALIDATION_ERROR | 400 | 요청 검증 실패 |
| VIDEO_CORRUPTED | 500 | 비디오 손상 |
| FFMPEG_ERROR | 500 | FFmpeg 오류 |
| YOLO_GPU_ERROR | 500 | YOLO GPU 오류 |
| YOLO_MODEL_NOT_LOADED | 503 | YOLO 모델 미로드 |

---

## 3. Multi-Zone Judge API

### POST /api/judge/multi-zone

Node.js에서 10초 간격 폴링.

**Request:**
```json
{
  "session_id": "zone_1_260202_143025",
  "zone": 1,
  "products": [
    {
      "product_idx": "26",
      "product_name": "치킨마요",
      "sale_price": 3500,
      "product_weight": "365"
    }
  ]
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| session_id | string | X | 세션 ID (없으면 최근 세션 자동 선택) |
| zone | int | X | Zone 번호 (Door Session 조회용) |
| products | array | X | 상품 목록 (무게 보정용) |

**Response 1: 대기 중 (processing)**
```json
{
  "success": false,
  "status": "processing",
  "message": "YOLO 추론 대기 중",
  "reason": "not_found",
  "device_id": null,
  "processing_stage": "waiting",
  "processing_stage_detail": "세션 생성 대기 중"
}
```

**Response 2: Door Session 진행 중 (in_progress)**
```json
{
  "success": false,
  "status": "in_progress",
  "device_id": null,
  "zone": 1,
  "door_session_id": "door_zone_1_260202_143000",
  "session_id": "zone_1_260202_143025",
  "processing_stage": "door_session_active",
  "processing_stage_detail": "Door session 활성: 2개 trigger 수신",
  "interim_products": [
    {
      "productIdx": "26",
      "productId": 26,
      "name": "치킨마요",
      "count": 2,
      "price": 3500,
      "confidence": 0.92
    }
  ],
  "interimProductCount": 2,
  "interimTotalPrice": 7000,
  "doorSessionInfo": {
    "triggerCount": 2,
    "durationSeconds": 15.5,
    "createdAt": 1738476600.0,
    "lastTriggerAt": 1738476615.5
  },
  "stats": {
    "topFrames": 0,
    "sideFrames": 0,
    "processingTimeMs": 3000.5
  }
}
```

**Response 3: Door Session 완료 (complete)**
```json
{
  "success": true,
  "status": "complete",
  "device_id": null,
  "zone": 1,
  "door_session_id": "door_zone_1_260202_143000",
  "session_id": "zone_1_260202_143025",
  "processing_stage": "complete",
  "processing_stage_detail": "Door session 완료: 3개 trigger 통합",
  "products": [
    {
      "productIdx": "26",
      "productId": 26,
      "name": "치킨마요",
      "count": 1,
      "price": 3500,
      "confidence": 0.92
    }
  ],
  "productCount": 1,
  "totalPrice": 3500,
  "confidence": 0.92,
  "weightInfo": {
    "delta": -365.0,
    "isRemoval": true
  },
  "doorSessionInfo": {
    "triggerCount": 3,
    "durationSeconds": 45.2,
    "createdAt": 1738476600.0,
    "finalizedAt": 1738476645.2
  },
  "stats": {
    "topFrames": 150,
    "sideFrames": 150,
    "processingTimeMs": 4500.5
  }
}
```

---

## 4. Session Status API

### GET /api/judge/session/{session_id}

세션 상태 조회.

**Response (찾음):**
```json
{
  "found": true,
  "session_id": "zone_1_260202_143025",
  "data": {
    "zone": 1,
    "status": "complete",
    "products": [...],
    "total_price": 3500,
    "delta_weight": -365.0,
    "confidence": 0.92
  }
}
```

**Response (못찾음):**
```json
{
  "found": false,
  "session_id": "zone_1_260202_143025",
  "message": "Session not found or expired"
}
```

---

## 5. Session Stats API

### GET /api/judge/sessions/stats

세션 저장소 통계.

**Response:**
```json
{
  "total_sessions": 10,
  "active_sessions": 3,
  "ttl_seconds": 300,
  "max_sessions": 100,
  "door_session_store": {
    "active_sessions": 1,
    "active_zones": [1],
    "session_timeout": 30.0,
    "weight_tolerance": 3.0
  },
  "timestamp": 1738476700.0
}
```

---

## 6. Door Session API (v4.1)

### GET /api/judge/door-sessions/stats

Door Session 저장소 통계.

**Response:**
```json
{
  "enabled": true,
  "active_sessions": 2,
  "active_zones": [1, 2],
  "session_timeout": 30.0,
  "weight_tolerance": 3.0,
  "max_duration": 600.0,
  "yaml_dir": "data/sessions",
  "timestamp": 1738476700.0
}
```

### GET /api/judge/door-session/{zone}

특정 Zone의 Door Session 조회.

**Response (찾음):**
```json
{
  "found": true,
  "zone": 1,
  "data": {
    "door_session_id": "door_zone_1_260202_143000",
    "zone": 1,
    "status": "active",
    "triggers": [
      {
        "trigger_id": "trigger_001",
        "session_id": "zone_1_260202_143025",
        "timestamp": 1738476600.0,
        "products": [...],
        "delta_weight": -365.0,
        "is_return": false
      }
    ],
    "aggregated_products": {
      "26": {
        "product_id": 26,
        "product_idx": "26",
        "name": "치킨마요",
        "count": 1,
        "unit_price": 3500,
        "weight": 365.0
      }
    },
    "created_at": 1738476600.0,
    "last_trigger_at": 1738476615.5
  }
}
```

### POST /api/judge/door-session/{zone}/finalize

Door Session 강제 종료.

**Response:**
```json
{
  "success": true,
  "zone": 1,
  "door_session_id": "door_zone_1_260202_143000",
  "trigger_count": 3,
  "product_count": 2,
  "total_price": 6500,
  "message": "Door session finalized successfully"
}
```

---

## 7. Products API

### GET /api/products

상품 목록 조회.

**Response:**
```json
{
  "products": [
    {
      "product_id": 26,
      "product_idx": "26",
      "name": "치킨마요",
      "price": 3500,
      "weight": 365.0,
      "yolo_class_id": 26
    }
  ],
  "total_count": 30
}
```

### POST /api/products/sync

IF11 상품 동기화.

**Request:**
```json
{
  "products": [
    {
      "saleItemIdx": 26,
      "itemName": "치킨마요주먹밥",
      "salePrice": 3500,
      "weight": 365
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "synced_count": 1,
  "message": "Products synced successfully"
}
```

---

## 응답 스키마 참조

### ProductResponse

| 필드 | 타입 | 설명 |
|------|------|------|
| productIdx | string | IF11 product_idx |
| productId | int | YOLO class_id |
| name | string | 상품명 |
| count | int | 수량 |
| price | int | 단가 |
| confidence | float | 신뢰도 (0.0~1.0) |

### WeightInfo

| 필드 | 타입 | 설명 |
|------|------|------|
| delta | float | 무게 변화량 (g) |
| isRemoval | bool | 제거 여부 (음수면 true) |

### DoorSessionInfo

| 필드 | 타입 | 설명 |
|------|------|------|
| triggerCount | int | Trigger 수 |
| durationSeconds | float | 세션 지속 시간 (초) |
| createdAt | float | 생성 시각 (epoch) |
| lastTriggerAt | float | 마지막 trigger 시각 |
| finalizedAt | float | 종료 시각 (complete일 때) |

### ProcessingStats

| 필드 | 타입 | 설명 |
|------|------|------|
| topFrames | int | Top 카메라 프레임 수 |
| sideFrames | int | Side 카메라 프레임 수 |
| processingTimeMs | float | 처리 시간 (ms) |
