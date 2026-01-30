# Edge Environment Lite - Camera & Model 서비스

AI 스마트 자판기 시스템의 Camera Driver + Model 서비스 (경량화 버전)

> **최종 업데이트**: 2026-01-30

## 개요

이 레포는 **Camera Driver**와 **Model** 서비스만 관리합니다.
Node.js, IO Board, Payment 등은 별도 레포([Edge_Environment](../Edge_Environment))에서 관리됩니다.

## 아키텍처

```
다른 레포 (Edge_Environment)              이 레포 (경량화 버전)
┌─────────────────────────────┐          ┌─────────────────────────────┐
│ Node.js Orchestrator (8888) │◄────────►│ React Client (3000)         │
│ IO Board (8000)             │          │   - setupProxy → 8888       │
│ Payment (5000/5001)         │          ├─────────────────────────────┤
│ MQTT Client (8006)          │          │ Camera Driver (8003)        │
└─────────────────────────────┘          │ Model Service (8002)        │
              ▲                          └─────────────────────────────┘
              │                                      │
              └──────────────────────────────────────┘
                        HTTP 통신
```

## 서비스 포트

| 서비스 | 포트 | 설명 | 관리 위치 |
|--------|------|------|-----------|
| Model | 8002 | YOLO 추론 + 상품 판단 | **이 레포** |
| Camera Driver | 8003 | 카메라 스냅샷/녹화 | **이 레포** |
| React Client | 3000 | 웹 대시보드 UI | **이 레포** |
| Node.js | 8888 | 오케스트레이터 | 다른 레포 |
| IO Board | 8000 | 로드셀 + 데드볼트 | 다른 레포 |
| Payment | 5000 | 결제 터미널 | 다른 레포 |

## 빠른 시작

### 1. 환경 설정
```bash
cp .env.example .env

# .env 주요 설정
CAMERA__NVIDIA_MODE=false           # Windows: false, Jetson: true
MODEL__VISION__YOLO_MODEL_PATH=./models/siyeon_best.pt
```

### 2. 의존성 설치
```bash
# Python (uv 권장)
uv sync --extra ai

# 또는 pip
pip install -e ".[ai,dev]"

# Node.js (PM2용)
npm install
```

### 3. 서비스 실행

```bash
# Camera Driver + Model (PM2)
npm run services

# React Client만 실행
npm run client

# 전체 실행 (client + camera + model)
npm run all

# 개별 실행 (개발용)
cd services/camera_driver && python main.py
cd services/model && python main.py
```

### 4. 서비스 중지
```bash
npm run services:stop
# 또는
pm2 stop all
```

## 테스트 명령어

### 헬스 체크
```bash
curl http://localhost:8002/api/health  # Model
curl http://localhost:8003/api/health  # Camera
```

### 상품 판단 테스트
```bash
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
      "image_folder": "data/20260128_115230/images"
    }
  }'
```

### 카메라 스냅샷
```bash
curl -X POST http://localhost:8003/api/zone/0/snapshot \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test123", "include_top": true}'
```

## 환경 변수

### Camera Driver
| 변수 | 기본값 | 설명 |
|------|--------|------|
| CAMERA__API_HOST | 0.0.0.0 | 서버 호스트 |
| CAMERA__API_PORT | 8003 | 서버 포트 |
| CAMERA__NVIDIA_MODE | false | Jetson 짝수 인덱싱 (true=Jetson) |
| CAMERA__RESOLUTION_WIDTH | 640 | 가로 해상도 |
| CAMERA__RESOLUTION_HEIGHT | 480 | 세로 해상도 |
| CAMERA__FPS | 30 | 프레임률 |
| CAMERA__IO_BOARD_URL | http://localhost:8000 | IO Board URL (다른 레포) |
| CAMERA__NODEJS_CALLBACK_URL | http://localhost:8888 | Node.js URL (다른 레포) |

### Model
| 변수 | 기본값 | 설명 |
|------|--------|------|
| MODEL__API__HOST | 0.0.0.0 | 서버 호스트 |
| MODEL__API__PORT | 8002 | 서버 포트 |
| MODEL__API__LOG_LEVEL | info | 로그 레벨 |
| MODEL__VISION__YOLO_MODEL_PATH | - | 모델 경로 (.pt 또는 .engine) |
| MODEL__NODEJS_URL | http://localhost:8888 | Node.js URL (다른 레포) |

## 프로젝트 구조

```
Edge_Environment/
├── services/
│   ├── camera_driver/             # 카메라 관리 (포트 8003)
│   │   ├── main.py                # FastAPI 진입점
│   │   └── src/
│   │       ├── core/              # 카메라 코어
│   │       │   ├── camera.py
│   │       │   ├── manager.py
│   │       │   └── event_recording_manager.py
│   │       ├── api/               # REST API
│   │       │   ├── routes.py
│   │       │   └── manager.py
│   │       └── models.py          # Pydantic 스키마
│   └── model/                     # AI 상품 판단 (포트 8002)
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
│           ├── engine/            # 판단 엔진
│           └── database/          # 상품 DB
├── client/                        # React Frontend (포트 3000)
│   ├── src/
│   │   └── setupProxy.js          # API 프록시 → localhost:8888
│   └── public/
├── config/
│   ├── zone_mapping.json          # Zone-Channel-Camera 매핑
│   └── camera_device_map.json     # 카메라 디바이스 매핑
├── _archive/                      # 아카이빙 (다른 레포로 이관)
│   ├── io_board/
│   ├── card_terminal/
│   ├── mqtt_client/
│   └── server/
├── ecosystem.config.js            # PM2 설정 (경량화)
├── package.json
└── pyproject.toml
```

## 주요 API

### Model Service (8002)
```
GET  /api/health                 # 헬스 체크
POST /api/judge                  # 상품 판단 (메인)
POST /api/judge/cancel           # 추론 취소
GET  /api/products               # 상품 목록
POST /api/products/register      # 상품 등록
POST /api/products/sync          # IF11 상품 동기화
```

### Camera Driver (8003)
```
GET  /api/health                 # 헬스 체크
GET  /api/status                 # 카메라 상태
GET  /api/cameras                # 카메라 목록
POST /api/zone/{id}/activate     # Zone 활성화
POST /api/zone/{id}/deactivate   # Zone 비활성화
POST /api/zone/{id}/snapshot     # 스냅샷 캡처
GET  /api/devices/scan           # 디바이스 스캔
POST /api/recording/start        # 녹화 시작
POST /api/recording/stop         # 녹화 중지
```

## PM2 명령어

```bash
npm run start          # 전체 서비스 시작
npm run services       # camera-driver + model만 시작
npm run client         # React client만 시작
npm run all            # 전체 (client + services)
npm run stop           # 전체 중지
npm run logs           # 로그 확인
npm run status         # 상태 확인
```

## 개발 가이드

### 테스트
```bash
pytest services/model/tests/ -v
pytest services/camera_driver/tests/ -v
```

### 코드 스타일
```bash
ruff check services/
ruff format services/
```

### 디버깅
```bash
# 상세 로그
LOG_LEVEL=DEBUG python services/camera_driver/main.py
LOG_LEVEL=DEBUG python services/model/main.py
```

## 다른 레포와 연동

이 레포의 서비스들은 다른 레포의 Node.js 오케스트레이터와 통신합니다:

1. **Client (3000)**: `setupProxy.js`가 API 요청을 `localhost:8888`로 프록시
2. **Camera Driver (8003)**: Node.js가 스냅샷/녹화 요청
3. **Model (8002)**: Node.js가 상품 판단 요청

```bash
# 다른 레포 서비스 실행 확인
curl http://localhost:8888/health  # Node.js
curl http://localhost:8000/health  # IO Board
```

## 아카이빙된 서비스

다음 서비스들은 `_archive/` 폴더로 이동되었으며, 다른 레포에서 관리됩니다:
- `io_board/` → CRK-IO-BOARD 레포
- `card_terminal/` → CRK-PAYMENT 레포
- `mqtt_client/` → Edge_Environment 레포
- `server/` → Edge_Environment 레포
