# Edge Environment Lite - Model 서비스

AI 스마트 자판기 시스템의 Model 서비스 (v3.0 Frame Buffer API)

> **최종 업데이트**: 2026-01-30

## 개요

이 레포는 **Model** 서비스만 관리합니다.
Node.js, IO Board, Payment, Camera Driver는 별도 레포에서 관리됩니다.

## 아키텍처 (v3.0)

```
다른 레포                                 이 레포
┌─────────────────────────────┐          ┌─────────────────────────────┐
│ Node.js Orchestrator (8888) │          │ React Client (3000)         │
│ Camera Driver (8003)        │─────────►│   - setupProxy → 8888       │
│   - POST /api/frame 전송    │          ├─────────────────────────────┤
│ IO Board (8000)             │          │ Model Service (8002)        │
│ Payment (5000/5001)         │          │   - FrameBuffer             │
│ MQTT Client (8006)          │          │   - YOLO 추론               │
└─────────────────────────────┘          │   - 상품 판단               │
                                         └─────────────────────────────┘
```

## 서비스 포트

| 서비스 | 포트 | 설명 | 관리 위치 |
|--------|------|------|-----------|
| Model | 8002 | YOLO 추론 + 상품 판단 | **이 레포** |
| React Client | 3000 | 웹 대시보드 UI | **이 레포** |
| Node.js | 8888 | 오케스트레이터 | 다른 레포 |
| Camera Driver | 8003 | 카메라 + Frame 전송 | 다른 레포 |
| IO Board | 8000 | 로드셀 + 데드볼트 | 다른 레포 |
| Payment | 5000 | 결제 터미널 | 다른 레포 |

## 빠른 시작

### 1. 환경 설정
```bash
cp .env.example .env

# .env 주요 설정
MODEL__VISION__YOLO_MODEL_PATH=./models/siyeon_best.pt
MODEL__BUFFER__TTL_SECONDS=30
MODEL__BUFFER__MAX_SESSIONS=100
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
# Model 서비스 (PM2)
npm run services

# React Client만 실행
npm run client

# 전체 실행 (client + model)
npm run all

# 개별 실행 (개발용)
cd services/model && python main.py
```

### 4. 서비스 중지
```bash
npm run services:stop
# 또는
pm2 stop all
```

## API 엔드포인트 (v3.0)

### Frame 수신 (신규)

```bash
# 프레임 전송 (Camera Driver에서 호출)
curl -X POST http://localhost:8002/api/frame \
  -F "zone_id=0" \
  -F "camera_id=0" \
  -F "image=@snapshot.jpg" \
  -F "format=bgr" \
  -F "width=640" \
  -F "height=480" \
  -F "session_id=sess_123"

# 버퍼 상태 조회
curl http://localhost:8002/api/frame/stats
```

### 상품 판단

```bash
# 헬스 체크
curl http://localhost:8002/api/health

# 상품 판단 (Node.js에서 호출)
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 0,
    "session_id": "sess_123",
    "weight_data": {
      "delta_weight": -520.0,
      "channels": [0, 1]
    }
  }'
```

### 상품 관리

```bash
# 상품 목록
curl http://localhost:8002/api/products

# IF11 상품 동기화
curl -X POST http://localhost:8002/api/products/sync \
  -H "Content-Type: application/json" \
  -d '{
    "products": [
      {"saleItemIdx": 26, "itemName": "치킨마요주먹밥", "salePrice": 3500, "weight": 520}
    ]
  }'
```

## 환경 변수

### Model
| 변수 | 기본값 | 설명 |
|------|--------|------|
| MODEL__API__HOST | 0.0.0.0 | 서버 호스트 |
| MODEL__API__PORT | 8002 | 서버 포트 |
| MODEL__API__LOG_LEVEL | info | 로그 레벨 |
| MODEL__BUFFER__TTL_SECONDS | 30 | 세션 TTL (초) |
| MODEL__BUFFER__MAX_SESSIONS | 100 | 최대 세션 수 |
| MODEL__VISION__YOLO_MODEL_PATH | - | 모델 경로 |
| MODEL__NODEJS_URL | http://localhost:8888 | Node.js URL |

## 프로젝트 구조

```
Edge_Environment/
├── services/
│   └── model/                     # AI 상품 판단 (포트 8002)
│       ├── main.py                # FastAPI 진입점
│       └── src/
│           ├── api/
│           │   ├── routes/        # 분리된 라우터
│           │   │   ├── health.py  # GET /api/health
│           │   │   ├── frame.py   # POST /api/frame (신규)
│           │   │   ├── judge.py   # POST /api/judge
│           │   │   └── products.py
│           │   ├── deps.py        # 의존성 주입
│           │   └── manager.py     # FastAPI 앱 팩토리
│           ├── buffer/            # 프레임 버퍼 (신규)
│           │   └── frame_buffer.py
│           ├── vision/            # YOLO 추론
│           │   ├── yolo_wrapper.py
│           │   ├── hand_filter.py
│           │   └── multi_view_ensemble.py
│           ├── weight/            # 무게 계산
│           │   └── count_calculator.py
│           ├── engine/            # 판단 엔진
│           │   ├── decision_engine.py
│           │   └── models.py
│           └── database/          # 상품 DB
│               └── product_db.py
├── client/                        # React Frontend (포트 3000)
├── config/
│   ├── zone_mapping.json          # Zone-Channel-Camera 매핑
│   └── camera_device_map.json     # 카메라 디바이스 매핑
├── _archive/                      # 아카이빙
│   └── camera_driver/             # (이동됨)
├── ecosystem.config.js            # PM2 설정
├── package.json
└── pyproject.toml
```

## 데이터 흐름

```
[Camera Driver]
    │
    ▼
POST /api/frame (여러 번 - top, side)
    │
    ▼
[FrameBuffer] <── 메모리에 저장 (session_id 기준)
    │
    │──── [Node.js] POST /api/judge (session_id + weight_data)
    │
    ▼
[버퍼에서 이미지 조회] → [YOLO 추론] → [Ensemble] → [무게 검증] → 결과
    │
    ▼
[세션 정리] + 응답 반환
```

## PM2 명령어

```bash
npm run start          # 전체 서비스 시작
npm run services       # model만 시작
npm run client         # React client만 시작
npm run all            # 전체 (client + services)
npm run stop           # 전체 중지
npm run logs           # 로그 확인
npm run status         # 상태 확인
```

## 아카이빙된 서비스

다음 서비스들은 `_archive/` 폴더로 이동되었으며, 다른 레포에서 관리됩니다:
- `camera_driver/` → 다른 레포로 이관 (POST /api/frame 방식으로 연동)
- `io_board/` → CRK-IO-BOARD 레포
- `card_terminal/` → CRK-PAYMENT 레포
- `mqtt_client/` → Edge_Environment 레포
- `server/` → Edge_Environment 레포
