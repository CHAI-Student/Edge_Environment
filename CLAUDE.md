# Edge Environment - CHAI Smart Vending System

Jetson Orin Nano 기반 AI 스마트 자판기 엣지 시스템

## 아키텍처

Node.js 중심의 마이크로서비스 아키텍처. **Model 서비스는 stateless 판단 전용**.

```
┌─────────────────────────────────────────────────────────────┐
│                 Node.js Orchestrator (8889)                  │
│   - IO Board SSE 구독 (loadcell.change)                      │
│   - Camera Driver 스냅샷 저장 요청                           │
│   - Model 서비스에 판단 요청 (weight_data + media_paths)     │
└────┬──────────────┬──────────────┬──────────────┬───────────┘
     │              │              │              │
     ▼              ▼              ▼              ▼
┌─────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐
│IO Board │  │  Camera   │  │   Model   │  │   MQTT    │
│ (8001)  │  │  (8003)   │  │  (8002)   │  │  (8006)   │
│  SSE →  │  │← snapshot │  │← 판단만   │  │           │
└─────────┘  └───────────┘  └───────────┘  └───────────┘
```

### 데이터 흐름

```
1. IO Board SSE → Node.js (loadcell.change 이벤트)
2. Node.js → Camera Driver (POST /api/zone/{id}/snapshot)
3. Node.js → Model (POST /api/judge with weight_data + media_paths)
4. Model → 파일 시스템 (이미지 로드, Vision 추론)
5. Model → Node.js (판단 결과 반환)
```

## 서비스 포트

| 서비스 | 포트 | 설명 |
|--------|------|------|
| IO Board | 8001 | 로드셀(10ch) + 데드볼트 SSE |
| Model | 8002 | YOLO 추론 + 상품 판단 (stateless) |
| Camera Driver | 8003 | 6대 카메라 스냅샷 (Nvidia 지원) |
| MQTT Client | 8006 | CHAI IF01-04 프로토콜 |
| Node.js | 8889 | 오케스트레이터 + 대시보드 |
| Card Terminal | 8004 | 결제 터미널 (미구현) |

## 빠른 시작

### 1. 환경 설정
```bash
cp .env.example .env

# Jetson Orin Nano 설정
IO_BOARD_PORT=/dev/ttyUSB0
CAMERA_MODE=api
NVIDIA_MODE=true
YOLO_MODEL_PATH=./models/siyeon_best.engine
```

### 2. 의존성 설치
```bash
pip install -e ".[ai,mqtt,dev]"
npm install
```

### 3. 서비스 실행 (Jetson)
```bash
# IO Board
IO_BOARD_PORT=/dev/ttyUSB0 uvicorn services.io_board.main:app --host 0.0.0.0 --port 8001

# Camera Driver
CAMERA_MODE=api NVIDIA_MODE=true uvicorn services.camera_driver.main:app --host 0.0.0.0 --port 8003

# MQTT Client
uvicorn services.mqtt_client.main:app --host 0.0.0.0 --port 8006

# Model (TensorRT)
YOLO_MODEL_PATH=./models/siyeon_best.engine uvicorn services.model.main:app --host 0.0.0.0 --port 8002

# Node.js
npm run start
```

### 4. 대시보드
```
http://localhost:8889/dashboard.html
```

## 테스트 명령어

### 헬스 체크
```bash
curl http://localhost:8001/health    # IO Board
curl http://localhost:8002/api/health # Model
curl http://localhost:8003/api/health # Camera
curl http://localhost:8006/health    # MQTT
curl http://localhost:8889/health    # Node.js
```

### SSE 스트림
```bash
# IO Board SSE
curl -N "http://localhost:8001/sse?streams=loadcells,doors&loadcell_interval=0.5"

# Node.js 통합 SSE
curl -N http://localhost:8889/sse/events
```

### 상품 판단 테스트
```bash
# 권장 형식: weight_data + media_paths (image_folder만 지정)
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 0,
    "weight_data": {
      "before_weights": [1000, 1005, 0, 0, 0, 0, 0, 0, 0, 0],
      "after_weights": [480, 505, 0, 0, 0, 0, 0, 0, 0, 0],
      "delta_weight": -520,
      "channels": [0, 1]
    },
    "media_paths": {
      "image_folder": "data/20260128_115230/images",
      "active_zones": [0, 1]
    }
  }'

# 레거시 형식 (하위 호환)
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 0, "delta_weight": -520}'
```

### 카메라 제어
```bash
# Zone 활성화/비활성화
curl -X POST http://localhost:8889/api/camera/zone/0/activate
curl -X POST http://localhost:8889/api/camera/zone/0/deactivate

# 스냅샷 (Camera Driver 직접)
curl -X POST http://localhost:8003/api/zone/0/snapshot \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test123", "include_top": true}'
```

### 로드셀/데드볼트
```bash
curl http://localhost:8001/loadcells
curl http://localhost:8001/status
curl -X POST http://localhost:8001/deadbolt -d '{"action": "OPEN"}'
```

### 카메라 전용 테스트 (로드셀 없이)

로드셀 연결 없이 카메라만으로 테스트할 때 사용합니다.
자세한 내용: [docs/CAMERA_ONLY_TEST.md](docs/CAMERA_ONLY_TEST.md)

```bash
# 서비스 상태 확인
curl http://localhost:8889/api/camera/test/status

# Zone 0 카메라 테스트 (스냅샷 + 판단)
curl -X POST http://localhost:8889/api/camera/test/snapshot-and-judge \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 0, "include_top": true}'

# 기존 이미지로 판단
curl -X POST http://localhost:8889/api/camera/test/judge-from-folder \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 0, "image_folder": "/data/snapshots/260126143025"}'

# Python 스크립트
python scripts/test_camera_only.py --zone 0
```

**주의**: 카메라 전용 모드는 개수=1 고정, 신뢰도 70%로 감소, 상태=PARTIAL

## 환경 변수

### IO Board
| 변수 | 기본값 | 설명 |
|------|--------|------|
| IO_BOARD_PORT | /dev/ttyUSB0 | 시리얼 포트 |
| IO_BOARD_BAUDRATE | 38400 | 통신 속도 |

### Camera Driver
| 변수 | 기본값 | 설명 |
|------|--------|------|
| CAMERA_MODE | api | api (실제) / folder (테스트) |
| NVIDIA_MODE | true | Jetson 짝수 인덱싱 |
| CAMERA_RESOLUTION | 640x480 | 해상도 |

### Model (stateless)
| 변수 | 기본값 | 설명 |
|------|--------|------|
| YOLO_MODEL_PATH | ./models/siyeon_best.pt | 모델 경로 (.pt 또는 .engine) |
| YOLO_CONFIDENCE_THRESHOLD | 0.3 | 추론 임계값 |
| SNAPSHOT_BASE_PATH | /data/snapshots | 스냅샷 경로 |

### Node.js
| 변수 | 기본값 | 설명 |
|------|--------|------|
| PORT | 8889 | 서버 포트 |
| IO_BOARD_URL | http://localhost:8001 | IO Board URL |
| CAMERA_DRIVER_URL | http://localhost:8003 | Camera URL |
| PRODUCT_JUDGE_URL | http://localhost:8002 | Model URL |

### MQTT
| 변수 | 기본값 | 설명 |
|------|--------|------|
| MQTT_BROKER_HOST | localhost | 브로커 호스트 |
| MQTT_BROKER_PORT | 1883 | 브로커 포트 |

## 설정 파일

### Zone 매핑 (`config/zone_mapping.json`)
```json
{
  "zones": {
    "0": {"loadcell_channels": [0, 1], "side_camera_id": 1},
    "1": {"loadcell_channels": [2, 3], "side_camera_id": 2},
    "2": {"loadcell_channels": [4, 5], "side_camera_id": 3},
    "3": {"loadcell_channels": [6, 7], "side_camera_id": 4},
    "4": {"loadcell_channels": [8, 9], "side_camera_id": 5}
  },
  "top_camera_id": 0
}
```

### 카메라 디바이스 (`config/camera_device_map.json`)
```json
{
  "nvidia_mode": true,
  "device_map": {
    "0": {"name": "Top Camera", "physical_index": 0},
    "1": {"name": "Zone 0", "physical_index": 2},
    "2": {"name": "Zone 1", "physical_index": 4},
    "3": {"name": "Zone 2", "physical_index": 6},
    "4": {"name": "Zone 3", "physical_index": 8},
    "5": {"name": "Zone 4", "physical_index": 10}
  }
}
```

## 프로젝트 구조

```
Edge_Environment/
├── config/
│   ├── zone_mapping.json
│   └── camera_device_map.json
├── services/
│   ├── io_board/
│   │   ├── protocol.py          # STX/ETX/LRC 프로토콜
│   │   ├── serial_io.py         # 비동기 시리얼
│   │   ├── api.py               # FastAPI + SSE
│   │   ├── commands.py          # MC-DC, RQ-IW 등
│   │   └── filters.py           # 칼만/지수평활
│   ├── model/
│   │   ├── api/routes.py        # POST /api/judge
│   │   ├── vision/
│   │   │   ├── yolo_wrapper.py
│   │   │   ├── hand_filter.py
│   │   │   └── multi_view_ensemble.py
│   │   ├── weight/
│   │   │   └── count_calculator.py
│   │   ├── engine/
│   │   │   ├── decision_engine.py
│   │   │   └── advanced/        # baseline, return, cross-zone
│   │   └── database/product_db.py
│   ├── camera_driver/
│   │   ├── core/camera_manager.py
│   │   └── api/routes.py
│   └── mqtt_client/
│       └── protocol/            # IF01-IF04
├── server/
│   ├── services/
│   │   ├── IOBoardSSESubscriber.js  # SSE 구독 + 판단 흐름
│   │   ├── CameraDriverClient.js    # 스냅샷 요청
│   │   └── ProductJudgeClient.js    # Model 호출
│   └── routes/
└── client/public/dashboard.html
```

## 주요 API

### Model Service (8002)
```
GET  /api/health                 # 헬스 체크
GET  /api/products               # 상품 목록
POST /api/judge                  # 상품 판단 (메인)
POST /api/judge/multi-zone       # 다중 Zone 판단
```

### IO Board Service (8001)
```
GET  /health                     # 헬스 체크
GET  /loadcells                  # 10채널 무게
GET  /status                     # 도어/데드볼트 상태
POST /deadbolt                   # 데드볼트 제어
GET  /sse                        # SSE 스트림
```

### Camera Driver (8003)
```
GET  /api/health                 # 헬스 체크
GET  /api/status                 # 카메라 상태
POST /api/zone/{id}/activate     # Zone 활성화
POST /api/zone/{id}/deactivate   # Zone 비활성화
POST /api/zone/{id}/snapshot     # 스냅샷 캡처
GET  /api/devices/scan           # 디바이스 스캔
```

### Node.js (8889)
```
GET  /health                     # 헬스 체크
GET  /api/dashboard/status       # 통합 상태
GET  /sse/events                 # 실시간 SSE
POST /api/camera/zone/{id}/activate
POST /api/camera/zone/{id}/deactivate
GET  /api/weight/events          # 무게 이벤트
```

## 개발 가이드

### 코드 스타일
```bash
ruff check .
ruff format .
mypy services/
```

### 테스트
```bash
pytest services/model/tests/ -v
pytest services/camera_driver/tests/ -v
```

### 디버깅
```bash
# 상세 로그
uvicorn services.io_board.main:app --port 8001 --log-level debug

# SSE 모니터링
curl -N "http://localhost:8001/sse?streams=loadcells"
```
