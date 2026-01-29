# Edge Environment - CHAI Smart Vending System

Jetson Orin Nano 기반 AI 스마트 자판기 엣지 시스템

> **최종 업데이트**: 2026-01-29

## 아키텍처

Node.js 중심의 마이크로서비스 아키텍처. **Event-Driven Architecture** 적용.

```
┌─────────────────────────────────────────────────────────────────────┐
│                  Node.js Orchestrator (8889)                         │
│   - IO Board SSE 구독 (loadcell.change, door.update)                 │
│   - Camera Driver 스냅샷/녹화 요청                                   │
│   - Model 서비스에 판단 요청 (weight_data + media_paths)             │
│   - PendingItemsStack: 세션별 픽업/반환 관리                         │
│   - WeightChangeAccumulator: 무게 변화 누적 처리                     │
│   - MongoDB/MinIO 연동                                               │
└────┬──────────────┬──────────────┬──────────────┬───────────────────┘
     │              │              │              │
     ▼              ▼              ▼              ▼
┌─────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐
│IO Board │  │  Camera   │  │   Model   │  │   MQTT    │  │  React    │
│ (8000)  │  │  (8003)   │  │  (8002)   │  │  (8006)   │  │  (3000)   │
│  SSE →  │  │← snapshot │  │← 판단만   │  │ IF01-04   │  │ Dashboard │
└─────────┘  └───────────┘  └───────────┘  └───────────┘  └───────────┘
```

### 데이터 흐름

```
1. IO Board SSE → Node.js (loadcell.change, door.update 이벤트)
2. 데드볼트 열림 → PendingItemsStack 세션 시작
3. Node.js → Camera Driver (POST /api/zone/{id}/snapshot)
4. Node.js → Model (POST /api/judge with weight_data + media_paths)
5. Model → Vision 추론 (Motion Tracking + Multi-View Ensemble)
6. Model → Node.js (판단 결과 반환)
7. 데드볼트 닫힘 → 정산 처리 (Settlement)
```

## 서비스 포트

| 서비스 | 포트 | 설명 |
|--------|------|------|
| IO Board | 8000 | 로드셀(10ch) + 데드볼트 SSE |
| Card Terminal API | 8001 | 결제 터미널 REST API |
| Model | 8002 | YOLO 추론 + 상품 판단 (stateless) |
| Camera Driver | 8003 | 6대 카메라 스냅샷/녹화 (Nvidia 지원) |
| MQTT Client | 8006 | CHAI IF01-04 프로토콜 |
| Node.js | 8889 | 오케스트레이터 + API |
| React Client | 3000 | 웹 대시보드 UI |
| Card Terminal CAT | 5001 | CAT 디바이스 TCP 서버 |

## 빠른 시작

### 1. 환경 설정
```bash
cp .env.example .env

# .env 수정 (주요 설정)
IO_BOARD_PORT=/dev/ttyUSB0          # Jetson: /dev/ttyTHS0
CAMERA_MODE=api
NVIDIA_MODE=true
YOLO_MODEL_PATH=../../../siyeon_best.pt
MONGO_URI=mongodb://localhost:27017/chai
```

### 2. 의존성 설치
```bash
# Python (uv 권장)
uv sync --extra ai --extra mqtt

# 또는 pip
pip install -e ".[ai,mqtt,dev]"

# Node.js
npm install

# PM2 전역 설치
npm install -g pm2
```

### 3. 서비스 실행 (PM2 통합)
```bash
# 전체 서비스 시작 (권장)
npm start
# 또는
pm2 start ecosystem.config.js

# 서비스 목록:
# - orchestrator (Node.js :8889)
# - client (React :3000)
# - io-board (:8001)
# - model (:8002)
# - camera-driver (:8003)
# - mqtt-client (:8006)
# - card-terminal (:5000)
```

### 4. 개별 서비스 실행 (개발용)
```bash
# IO Board (python main.py 패턴)
cd services/io_board && python main.py

# Camera Driver
cd services/camera_driver && python main.py

# Model
cd services/model && python main.py

# MQTT Client
cd services/mqtt_client && python main.py

# Card Terminal
cd services/card_terminal && python main.py

# Node.js + React (동시 실행)
npm run dev
```

> **참고**: 각 서비스의 `main.py`는 PM2 래퍼로, 내부적으로 `src/main.py`를 실행합니다.
> 환경변수는 `.env` 파일 또는 `ecosystem.config.js`에서 설정합니다.

### 5. 대시보드
```
http://localhost:3000        # React 개발 서버
http://localhost:8889        # Node.js 정적 파일 서빙 (production)
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

### 공통
| 변수 | 기본값 | 설명 |
|------|--------|------|
| NODE_ENV | development | 환경 (production/development) |
| LOG_LEVEL | INFO | 로그 레벨 (DEBUG/INFO/WARNING/ERROR) |

### IO Board
| 변수 | 기본값 | 설명 |
|------|--------|------|
| IO_BOARD_PORT | /dev/ttyUSB0 | 시리얼 포트 (Jetson: /dev/ttyTHS0) |
| IO_BOARD_BAUDRATE | 38400 | 통신 속도 |

### Camera Driver
| 변수 | 기본값 | 설명 |
|------|--------|------|
| CAMERA_MODE | api | api (실제) / folder (테스트) |
| NVIDIA_MODE | true | Jetson 짝수 인덱싱 |
| CAMERA_RESOLUTION_WIDTH | 640 | 가로 해상도 |
| CAMERA_RESOLUTION_HEIGHT | 480 | 세로 해상도 |
| CAMERA_FPS | 30 | 프레임률 |
| CAMERA_JPEG_QUALITY | 80 | JPEG 압축 품질 |

### Model (stateless)
| 변수 | 기본값 | 설명 |
|------|--------|------|
| YOLO_MODEL_PATH | ../../../siyeon_best.pt | 모델 경로 (.pt 또는 .engine) |
| YOLO_CONFIDENCE_THRESHOLD | 0.3 | 추론 임계값 |
| YOLO_TOP_K | 1 | Top-K 추출 개수 |

### Node.js
| 변수 | 기본값 | 설명 |
|------|--------|------|
| PORT | 8889 | 서버 포트 |
| IO_BOARD_URL | http://localhost:8001 | IO Board URL |
| CAMERA_DRIVER_URL | http://localhost:8003 | Camera URL |
| PRODUCT_JUDGE_URL | http://localhost:8002 | Model URL |
| NODEJS_URL | http://localhost:8889 | 자체 URL |

### MQTT
| 변수 | 기본값 | 설명 |
|------|--------|------|
| MQTT_BROKER_HOST | localhost | 브로커 호스트 |
| MQTT_BROKER_PORT | 1883 | 브로커 포트 |
| MQTT_URL | mqtt://localhost:1883 | Node.js용 MQTT URL |
| DIVISION_IDX | DIV001 | 디바이스 식별자 |
| DEVICE_IDX | DEV001 | 디바이스 ID |

### MongoDB / MinIO
| 변수 | 기본값 | 설명 |
|------|--------|------|
| MONGO_URI | mongodb://localhost:27017/chai | MongoDB 연결 |
| MINIO_ENDPOINT | localhost | MinIO 엔드포인트 |
| MINIO_PORT | 9000 | MinIO 포트 |
| MINIO_ACCESS_KEY | minioadmin | MinIO 액세스 키 |
| MINIO_SECRET_KEY | minioadmin | MinIO 시크릿 키 |
| MINIO_BUCKET | chaiimage | MinIO 버킷 |

### Card Terminal
| 변수 | 기본값 | 설명 |
|------|--------|------|
| CARD_API_HOST | 0.0.0.0 | REST API 서버 호스트 |
| CARD_API_PORT | 5000 | REST API 서버 포트 |
| CAT_HOST | 0.0.0.0 | CAT 디바이스 TCP 서버 호스트 |
| CAT_PORT | 5001 | CAT 디바이스 TCP 서버 포트 |
| COMM_TIMEOUT | 30 | 통신 타임아웃 (초) |
| SHUTDOWN_TIMEOUT | 10 | Graceful shutdown 타임아웃 (초) |

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
│   ├── zone_mapping.json          # Zone-Channel-Camera 매핑
│   └── camera_device_map.json     # 카메라 디바이스 매핑
├── services/
│   ├── io_board/                  # 로드셀 + 데드볼트 (포트 8001)
│   │   ├── main.py                # FastAPI 진입점
│   │   └── src/                   # ★ 소스 코드 폴더
│   │       ├── protocol.py        # STX/ETX/LRC 프로토콜
│   │       ├── serial_io.py       # 비동기 시리얼
│   │       ├── commands.py        # MC-DC, RQ-IW 등
│   │       ├── filters.py         # 칼만/지수평활
│   │       ├── config.py          # 설정
│   │       ├── machine/           # 상태 머신 (sse.py, recording.py)
│   │       ├── events/            # 이벤트 처리
│   │       └── recording/         # 녹화 관리
│   ├── model/                     # AI 상품 판단 (포트 8002)
│   │   ├── main.py                # FastAPI 진입점
│   │   └── src/                   # ★ 소스 코드 폴더
│   │       ├── config.py          # Zone/Vision 설정
│   │       ├── api/               # REST API
│   │       │   ├── routes.py      # 엔드포인트
│   │       │   └── models.py      # Pydantic 스키마
│   │       ├── vision/            # YOLO 추론
│   │       │   ├── yolo_wrapper.py
│   │       │   ├── hand_filter.py
│   │       │   ├── multi_view_ensemble.py
│   │       │   └── motion_correlation_filter.py
│   │       ├── weight/            # 무게 계산
│   │       │   └── count_calculator.py
│   │       ├── engine/            # 판단 엔진
│   │       │   ├── decision_engine.py
│   │       │   └── advanced/      # baseline, return, cross-zone
│   │       ├── database/          # 상품 DB
│   │       │   └── product_db.py
│   │       ├── camera/            # 이미지 로드
│   │       ├── door_payment/      # 도어 결제 모듈
│   │       ├── error_recovery/    # 에러 복구
│   │       └── tests/             # 테스트 코드
│   ├── camera_driver/             # 카메라 관리 (포트 8003)
│   │   ├── main.py                # FastAPI 진입점
│   │   └── src/                   # ★ 소스 코드 폴더
│   │       ├── config.py          # 설정
│   │       ├── core/              # 카메라 코어
│   │       │   ├── camera.py
│   │       │   ├── manager.py
│   │       │   └── device_scanner.py
│   │       ├── api/               # REST API
│   │       │   ├── routes.py
│   │       │   └── streaming.py
│   │       └── models/            # 스키마
│   ├── mqtt_client/               # MQTT IF01-04 (포트 8006)
│   │   ├── main.py                # 진입점
│   │   └── src/                   # ★ 소스 코드 폴더
│   │       ├── config.py
│   │       ├── core/              # MQTT 코어
│   │       │   ├── core.py
│   │       │   └── router.py
│   │       ├── protocol/          # IF01-IF04
│   │       │   ├── IF01.py
│   │       │   ├── IF02.py
│   │       │   ├── IF03.py
│   │       │   └── IF04.py
│   │       └── util/              # 유틸리티
│   └── card_terminal/             # 결제 터미널 (포트 5000)
│       ├── main.py                # 진입점 (TCP + REST)
│       └── src/                   # ★ 소스 코드 폴더
│           ├── config.py          # 환경 변수 설정
│           ├── exceptions.py      # RFC 7807 에러 처리
│           ├── action/            # SSE 이벤트 처리
│           │   └── manager.py
│           ├── api/               # REST API
│           │   ├── manager.py     # FastAPI + Graceful Server
│           │   └── schemas.py     # Pydantic 스키마
│           └── payment/           # 결제 프로토콜
│               ├── command.py
│               ├── const.py
│               ├── manager.py
│               ├── payload.py
│               ├── structure.py
│               └── payment_types.py
├── server/
│   ├── index.js                   # Express 진입점
│   ├── config/
│   │   ├── key.js                 # 환경 설정 라우터
│   │   ├── dev.js                 # 개발 환경
│   │   └── prod.js                # 프로덕션 환경
│   ├── services/
│   │   ├── IOBoardSSESubscriber.js    # SSE 구독 + 이벤트 처리
│   │   ├── CameraDriverClient.js      # 스냅샷/녹화 요청
│   │   ├── ProductJudgeClient.js      # Model 판단 요청
│   │   ├── ConfigManager.js           # Zone 설정 관리
│   │   ├── WeightChangeAccumulator.js # 무게 변화 누적
│   │   ├── PendingItemsStack.js       # 세션별 픽업/반환 관리
│   │   └── ScheduledLogger.js         # 스케줄 로깅
│   ├── routes/
│   │   ├── camera.js              # /api/camera
│   │   ├── cameraCallback.js      # Event-Driven 콜백
│   │   ├── door.js                # /api/door
│   │   ├── model.js               # /api/model
│   │   ├── events.js              # /sse, /api/weight
│   │   ├── logs.js                # /api/logs
│   │   ├── mqtt.js                # MQTT 라우트
│   │   ├── auth.js                # JWT 인증
│   │   ├── Mqtt/                  # MQTT 모듈
│   │   ├── RestAPI/               # REST API 모듈
│   │   └── AIServer/              # AI 서버 연동
│   └── model/                     # DB 모델
├── client/                        # React Frontend
│   ├── src/
│   └── public/
├── ecosystem.config.js            # PM2 설정
├── package.json
├── pyproject.toml                 # Python 의존성 (uv)
└── .env.example                   # 환경 변수 예시
```

## 주요 API

### Model Service (8002)
```
GET  /api/health                 # 헬스 체크
GET  /api/zones/config           # Zone 설정 조회
GET  /api/products               # 상품 목록
GET  /api/products/{id}          # 상품 상세
GET  /api/products/export        # 전체 상품 내보내기
GET  /api/products/search?query= # 상품 검색
GET  /api/products/barcode/{bc}  # 바코드 조회
POST /api/products/register      # 상품 등록
POST /api/products/sync          # IF11 상품 동기화
PUT  /api/products/{id}          # 상품 수정
DELETE /api/products/{id}        # 상품 삭제
POST /api/judge                  # 상품 판단 (메인)
POST /api/judge/cancel           # 추론 취소
GET  /api/judge/active           # 활성 추론 목록
POST /api/judge/multi-zone       # 다중 Zone 판단
POST /api/judge/with-history     # 히스토리 기반 판단 (반환 감지)
GET  /api/stats/recognition-rate # 인식률 통계
POST /api/stats/reset            # 통계 초기화
POST /api/door/transaction       # 도어 결제 시작
GET  /api/door/status            # 도어 상태
POST /api/door/cancel            # 거래 취소
POST /api/door/emergency-lock    # 비상 잠금
```

### IO Board Service (8001)
```
GET  /health                     # 헬스 체크
GET  /loadcells                  # 10채널 무게
GET  /status                     # 도어/데드볼트 상태
POST /deadbolt                   # 데드볼트 제어 (OPEN/CLOSE)
POST /calibrate                  # 로드셀 영점 보정
POST /init                       # 시스템 초기화
GET  /sse                        # SSE 스트림
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
POST /api/recording/snapshot     # 녹화 중 스냅샷
```

### Node.js (8889)
```
GET  /health                     # 헬스 체크
GET  /api/dashboard/status       # 통합 상태 (모든 서비스)

# Camera
POST /api/camera/zone/{id}/activate
POST /api/camera/zone/{id}/deactivate
GET  /api/camera/test/status     # 테스트 모드 상태
POST /api/camera/test/snapshot-and-judge  # 스냅샷 + 판단
POST /api/camera/test/record-and-judge    # 녹화 + 판단
POST /api/camera/test/judge-from-folder   # 기존 이미지 판단

# Door
POST /api/door/deadbolt          # 데드볼트 제어 프록시

# Model
POST /api/model/judge            # 판단 프록시
GET  /api/model/products         # 상품 목록 프록시

# Events (SSE)
GET  /sse/events                 # 실시간 이벤트 SSE
GET  /api/weight/events          # 무게 이벤트

# Logs
GET  /api/logs                   # 로그 조회
POST /api/logs                   # 로그 기록
```

### Card Terminal (API: 5000 / CAT TCP: 5001)
```
# Status
GET  /status                      # 디바이스 헬스 체크

# SSE Events
GET  /sse                         # SSE 이벤트 스트림
                                  # - tx_token_generate: 토큰 생성
                                  # - samsung_pay_init: 삼성페이 초기화
                                  # - rfid_init: RFID 카드 감지

# Token Payment
POST /payment/token/approve       # 토큰 결제 승인
POST /payment/token/cancel        # 토큰 결제 취소

# Samsung Pay
POST /payment/samsung-pay/approve # 삼성페이 승인
POST /payment/samsung-pay/cancel  # 삼성페이 취소
```

## PM2 명령어

```bash
# 서비스 관리
pm2 start ecosystem.config.js     # 전체 시작
pm2 stop all                      # 전체 중지
pm2 restart all                   # 전체 재시작
pm2 delete all                    # 전체 삭제

# 개별 서비스
pm2 start ecosystem.config.js --only model
pm2 restart io-board
pm2 logs model --lines 100

# 상태 확인
pm2 list                          # 서비스 목록
pm2 status                        # 상태 확인
pm2 logs                          # 전체 로그
```

## Event-Driven Architecture

### 데드볼트 이벤트 흐름
```
1. 데드볼트 OPEN → PendingItemsStack.startSession()
2. 무게 변화 감지 → WeightChangeAccumulator에 누적
3. 카메라 활성화/스냅샷/녹화 자동 시작
4. Model 판단 요청 → 결과를 세션에 기록
5. 데드볼트 CLOSE → 정산 처리 (15초 대기 후)
6. PendingItemsStack.closeSession() → 픽업/반환 정산
```

### Motion Tracking (Vision)
```
1. 연속 프레임 입력 (frame_0001.jpg, frame_0002.jpg, ...)
2. MotionCorrelationFilter: 프레임간 객체 추적
3. 손 근접 영역에서 움직임 있는 객체 보너스
4. MultiViewEnsemble: Top + Side 카메라 결합
5. motion_bonus_map을 통해 최종 신뢰도 증가
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
# Python 테스트
pytest services/model/tests/ -v
pytest services/camera_driver/tests/ -v

# uv 사용 시
uv run pytest services/model/tests/ -v --cov=services/model
```

### 디버깅
```bash
# Python 서비스 상세 로그 (LOG_LEVEL 환경변수 사용)
LOG_LEVEL=DEBUG python services/io_board/main.py

# 또는 .env 파일에서 설정
# LOG_LEVEL=DEBUG

# SSE 모니터링
curl -N "http://localhost:8001/sse?streams=loadcells,doors"

# Node.js 디버그 모드
LOG_LEVEL=debug node server/index.js
```

## 헬스 체크

```bash
# 전체 서비스 헬스 체크
curl http://localhost:8001/health      # IO Board
curl http://localhost:8002/api/health  # Model
curl http://localhost:8003/api/health  # Camera
curl http://localhost:8006/health      # MQTT
curl http://localhost:8889/health      # Node.js
curl http://localhost:5000/status      # Card Terminal

# 통합 상태 (Node.js)
curl http://localhost:8889/api/dashboard/status
```

## Card Terminal 테스트

```bash
# 헬스 체크
curl http://localhost:5000/status

# SSE 이벤트 스트림 연결
curl -N http://localhost:5000/sse

# 토큰 결제 승인 (amount: 9자리, vankey_hash: 24자리)
curl -X POST http://localhost:5000/payment/token/approve \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "000001000",
    "vankey_hash": "VANKEY1234567890HASH1234"
  }'

# 토큰 결제 취소
curl -X POST http://localhost:5000/payment/token/cancel \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "000001000",
    "original_authorization_number": "12345678",
    "original_authorization_date": "260129",
    "vankey_hash": "VANKEY1234567890HASH1234"
  }'

# 삼성페이 승인
curl -X POST http://localhost:5000/payment/samsung-pay/approve \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "000005000",
    "authorization_type": "PURCHASE",
    "display_message": "삼성페이 결제"
  }'
```
