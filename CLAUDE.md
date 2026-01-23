# Edge Environment - CHAI Smart Vending System

AI 기반 스마트 자판기 엣지 시스템입니다. 무게 센서와 카메라를 활용하여 상품을 자동으로 인식하고 판단합니다.

## 아키텍처

마이크로서비스 기반 아키텍처로 구성되어 있습니다:

```
┌─────────────────────────────────────────────────────────────┐
│                    Web Dashboard (8889)                      │
│                    (모니터링/제어 UI)                         │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                Node.js Orchestrator (8889)                   │
│     (SSE 구독 + 카메라 제어 + 무게 이벤트 로깅)              │
└────┬──────────────┬──────────────┬──────────────┬───────────┘
     │              │              │              │
     ▼              ▼              ▼              ▼
┌─────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐
│IO Board │  │  Camera   │  │   Model   │  │   MQTT    │
│ (8001)  │  │  (8003)   │  │  (8002)   │  │  (8006)   │
│  SSE →  │  │← activate │  │← 판단요청 │  │           │
└─────────┘  └───────────┘  └───────────┘  └───────────┘
```

**데이터 흐름:**
```
로드셀 변화 → IO Board SSE → Node.js → 카메라 활성화 + 로그 저장
                                    ↓
                              Model 서비스에 판단 요청
```

## 서비스 포트 매핑

| 서비스 | 포트 | 설명 |
|--------|------|------|
| IO Board | 8001 | 로드셀/도어 제어 (Mock 모드 지원) |
| Model | 8002 | YOLO 추론 + 상품 판단 |
| Camera Driver | 8003 | 카메라 프레임 캡처 (Nvidia 지원) |
| Card Terminal | 5000 | 결제 터미널 (미구현) |
| MQTT Client | 8006 | MQTT 브로커 연동 |
| Node.js | 8889 | 메인 오케스트레이터 + 웹 대시보드 |

## 빠른 시작

### 1. 환경 설정
```bash
# .env 파일 생성
cp .env.example .env

# 주요 설정값 수정
# IO_BOARD_MOCK_MODE=true  # 하드웨어 없이 테스트
# CAMERA_MODE=folder       # 폴더 이미지 사용
# MQTT_BROKER_HOST=localhost
```

### 2. 의존성 설치
```bash
# Python 의존성
pip install -e ".[ai,mqtt,dev]"

# Node.js 의존성
npm install
cd client && npm install && cd ..
```

### 3. 서비스 실행

#### 개별 서비스 실행 (개발 모드)
```bash
# 터미널 1: IO Board (Mock 모드)
IO_BOARD_MOCK_MODE=true uvicorn services.io_board.main:app --host 0.0.0.0 --port 8001

# 터미널 2: Camera Driver
CAMERA_MODE=folder uvicorn services.camera_driver.main:app --host 0.0.0.0 --port 8003

# 터미널 3: MQTT Client
MQTT_BROKER_HOST=localhost uvicorn services.mqtt_client.main:app --host 0.0.0.0 --port 8006

# 터미널 4: Model (IO Board, Camera 실행 후)
IO_BOARD_URL=http://localhost:8001 \
CAMERA_DRIVER_URL=http://localhost:8003 \
NODEJS_URL=http://localhost:8889 \
YOLO_MODEL_PATH=./siyeon_best.pt \
uvicorn services.model.main:app --host 0.0.0.0 --port 8002

# 터미널 5: Node.js Orchestrator
npm run start
```

### 4. 대시보드 접속
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

### 로드셀 데이터 조회
```bash
curl http://localhost:8001/loadcells
```

### 카메라 제어 (Node.js를 통해)
```bash
# Zone 카메라 활성화
curl -X POST http://localhost:8889/api/camera/zone/0/activate

# Zone 카메라 비활성화
curl -X POST http://localhost:8889/api/camera/zone/0/deactivate

# 카메라 상태 조회
curl http://localhost:8889/api/camera/status
```

### 무게 이벤트 조회
```bash
# 최근 이벤트 조회
curl http://localhost:8889/api/weight/events

# Zone별 통계
curl http://localhost:8889/api/weight/stats/0

# 베이스라인 리셋
curl -X POST http://localhost:8889/api/weight/baseline/reset
```

### 상품 판단 테스트
```bash
# 520g 상품 픽업 테스트
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 0, "delta_weight": -520}'
```

### SSE 스트림 테스트
```bash
# IO Board SSE 스트림
curl -N http://localhost:8001/sse?streams=loadcells&loadcell_interval=0.5

# Node.js SSE 스트림 (통합)
curl -N http://localhost:8889/sse/events
```

### MQTT 테스트
```bash
# 구독
mosquitto_sub -h localhost -t "chai/#" -v

# 발행
mosquitto_pub -h localhost -t "chai/test" -m "hello"
```

## 설정 파일

### Zone 매핑 설정
`config/zone_mapping.json` - Zone-로드셀-카메라 매핑
```json
{
  "zones": {
    "0": { "loadcell_channels": [0, 1], "side_camera_id": 1 },
    "1": { "loadcell_channels": [2, 3], "side_camera_id": 2 },
    ...
  }
}
```

### 카메라 디바이스 매핑
`config/camera_device_map.json` - Nvidia 장치 매핑
```json
{
  "nvidia_mode": true,
  "device_map": {
    "0": { "physical_index": 0 },
    "1": { "physical_index": 2 },
    ...
  }
}
```

Nvidia Jetson에서는 카메라가 짝수 인덱스(0, 2, 4, 6, 8, 10)로 할당됩니다.

## Docker 배포

### 빌드
```bash
docker compose -f docker-compose.yaml build --parallel
```

### 개발 모드 실행
```bash
docker compose -f docker-compose.yaml -f docker-compose.dev.yaml up -d
```

### 상태 확인
```bash
docker compose ps
docker compose logs -f
```

### 종료
```bash
docker compose down
```

## 환경 변수

### 공통
| 변수 | 기본값 | 설명 |
|------|--------|------|
| NODE_ENV | development | 실행 환경 |
| LOG_LEVEL | INFO | 로깅 레벨 |

### IO Board
| 변수 | 기본값 | 설명 |
|------|--------|------|
| IO_BOARD_MOCK_MODE | false | Mock 모드 활성화 |
| IO_BOARD_PORT | COM3 | 시리얼 포트 |
| IO_BOARD_BAUDRATE | 38400 | 통신 속도 |

### Camera
| 변수 | 기본값 | 설명 |
|------|--------|------|
| CAMERA_MODE | folder | api/folder |
| NVIDIA_MODE | false | Nvidia 장치 인덱싱 |

### MQTT
| 변수 | 기본값 | 설명 |
|------|--------|------|
| MQTT_BROKER_HOST | localhost | 브로커 호스트 |
| MQTT_BROKER_PORT | 1883 | 브로커 포트 |
| DEVICE_IDX | DEV001 | 디바이스 ID |

### Model
| 변수 | 기본값 | 설명 |
|------|--------|------|
| YOLO_MODEL_PATH | ./siyeon_best.pt | YOLO 모델 경로 |
| IO_BOARD_URL | http://localhost:8001 | IO Board URL |
| CAMERA_DRIVER_URL | http://localhost:8003 | Camera URL |
| NODEJS_URL | http://localhost:8889 | Node.js URL |

### Node.js
| 변수 | 기본값 | 설명 |
|------|--------|------|
| PORT | 8889 | 서버 포트 |
| MONGO_URI | mongodb://localhost:27017/chai | MongoDB URI |
| MINIO_ENDPOINT | localhost | MinIO 엔드포인트 |

## 프로젝트 구조

```
Edge_Environment/
├── config/                   # 설정 파일 (Zone/카메라 매핑)
│   ├── zone_mapping.json
│   └── camera_device_map.json
├── services/
│   ├── io_board/             # 로드셀/도어 제어 서비스
│   ├── model/                # AI 상품 판단 서비스
│   ├── camera_driver/        # 카메라 드라이버
│   ├── mqtt_client/          # MQTT 클라이언트
│   └── card_terminal/        # 결제 터미널 (미완성)
├── server/                   # Node.js 오케스트레이터
│   ├── services/             # 서비스 클라이언트
│   │   ├── CameraDriverClient.js
│   │   ├── IOBoardSSESubscriber.js
│   │   ├── WeightEventLogger.js
│   │   └── ConfigManager.js
│   └── routes/               # API 라우트
│       ├── camera.js
│       └── events.js
├── client/                   # React 프론트엔드
│   └── public/
│       └── dashboard.html    # 대시보드 UI
├── docker-compose.yaml       # Docker 구성
├── pyproject.toml            # Python 패키지 설정
└── package.json              # Node.js 패키지 설정
```

## 주요 API

### Node.js Service (8889)
- `GET /health` - 헬스 체크
- `GET /api/dashboard/status` - 대시보드용 통합 상태
- `GET /sse/events` - 실시간 이벤트 SSE 스트림

#### 카메라 제어
- `POST /api/camera/zone/:zoneId/activate` - Zone 카메라 활성화
- `POST /api/camera/zone/:zoneId/deactivate` - Zone 카메라 비활성화
- `GET /api/camera/status` - 카메라 상태 조회

#### 무게 이벤트
- `GET /api/weight/events` - 최근 무게 이벤트 조회
- `GET /api/weight/stats/:zoneId` - Zone별 통계
- `POST /api/weight/baseline/reset` - 베이스라인 리셋

#### 설정
- `GET /api/config` - 모든 설정 조회
- `PUT /api/config/zone-mapping` - Zone 매핑 업데이트
- `PUT /api/config/camera-device-map` - 카메라 디바이스 매핑 업데이트

### Model Service (8002)
- `GET /api/health` - 헬스 체크
- `GET /api/products` - 등록된 상품 목록
- `POST /api/judge` - 상품 판단
- `POST /api/judge/multi-zone` - 다중 Zone 판단
- `POST /api/judge/with-history` - 히스토리 기반 판단

### IO Board Service (8001)
- `GET /health` - 헬스 체크
- `GET /loadcells` - 로드셀 값 조회
- `GET /status` - 도어/데드볼트 상태
- `POST /deadbolt` - 데드볼트 제어
- `GET /sse` - SSE 스트림 (loadcells, doors)

### Camera Driver (8003)
- `GET /api/health` - 헬스 체크
- `POST /api/init` - 카메라 초기화
- `GET /api/status` - 카메라 상태
- `POST /api/zone/:zoneId/activate` - Zone 카메라 활성화
- `POST /api/zone/:zoneId/deactivate` - Zone 카메라 비활성화
- `GET /api/devices/scan` - 디바이스 스캔

## 개발 가이드

### Python 코드 스타일
```bash
ruff check .
ruff format .
mypy services/
```

### 테스트 실행
```bash
pytest services/model/tests/
```

## 디버깅

### 서비스 상태 확인
```bash
# 모든 서비스 헬스 체크
curl http://localhost:8889/api/dashboard/status | jq
```

### 로그 확인
```bash
# Node.js 로그 (터미널에서 직접 확인)
npm run start

# Python 서비스 로그
uvicorn services.io_board.main:app --port 8001 --log-level debug
```

### SSE 연결 테스트
```bash
# IO Board SSE 구독
curl -N http://localhost:8001/sse?streams=loadcells

# Node.js 통합 SSE 구독
curl -N http://localhost:8889/sse/events
```
