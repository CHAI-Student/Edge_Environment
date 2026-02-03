# Edge Environment Lite - Model 서비스

AI 스마트 자판기 시스템의 Model 서비스 (v4.2 Service Layer + Docker)
**Jetson Orin Nano 4GB (JetPack 6.2) TensorRT 전용**

> **최종 업데이트**: 2026-02-02

## 개요

이 레포는 **Model** 서비스만 관리합니다.
**TensorRT 엔진(.engine)** 파일만 지원하며, **CUDA가 필수**입니다.
Node.js, IO Board, Payment, Camera Driver는 별도 레포에서 관리됩니다.

### v4.2 변경사항 (최신)

- **Service Layer 추가**: Controller-Service 패턴 적용
  - `src/service/trigger_service.py` - 트리거 비즈니스 로직
  - `src/service/judgment_service.py` - 판단 비즈니스 로직
  - `src/service/door_session_service.py` - DoorSession 관리
- **Config 통합**: `src/config.py` 제거, `core.config`로 일원화
- **Docker 지원**: Jetson Orin Nano 4GB 최적화 컨테이너
  - `Dockerfile` - 멀티스테이지 빌드
  - `docker-compose.yml` - 메모리 3G 제한
  - `.env.docker` - 환경변수 템플릿
- **TTL 자동 정리**: 백그라운드 태스크로 좀비 세션 정리
- **YAML Lock 분리**: Copy-on-write로 파일 I/O 중 블로킹 제거

### v4.1 변경사항

- **Door Session 추가**: 문 열림~닫힘 동안의 여러 trigger를 하나의 세션으로 통합 관리
- **ProductAggregator**: 다중 trigger 상품 합산, 반환(무게 증가) 시 차감 처리
- **YAML 영속화**: Door Session 데이터를 YAML 파일로 저장 (서비스 재시작 시 복구)
- **신규 API 엔드포인트**: Door Session 조회/통계/강제종료

### v4.0 변경사항

- **Frame Buffer 제거**: AVI Trigger 방식만 사용
- **API 단순화**: 2개 API로 통합
  - `POST /trigger` - Camera에서 호출, 즉시 YOLO 추론
  - `POST /api/judge/multi-zone` - Node.js 10초 폴링
- **SessionStore 추가**: 추론 결과 저장 (TTL 기반 자동 정리)
- **Jetson 4GB 최적화**: 480x480 입력, FP16, max_det=20

### Jetson Orin Nano 4GB 최적화

| 항목 | 설정 | 효과 |
|------|------|------|
| 입력 크기 | 480x480 (640x480에서 오른쪽 160px 크롭) | 메모리 44% 감소 |
| FP16 추론 | `half=True` | 메모리 50% 감소 |
| 최대 탐지 | `max_det=20` | 후처리 부하 감소 |
| FFmpeg 코덱 | `-c:v mjpeg` | AVI MJPEG 최적화 |
| 배치 크기 | 1 (고정) | 4GB 메모리 제약 |
| GPU 워밍업 | 서비스 시작 시 더미 추론 2회 | 첫 요청 지연 제거 |

## 아키텍처 (v4.2)

```
다른 레포                                 이 레포
┌─────────────────────────────┐          ┌─────────────────────────────┐
│ Node.js Orchestrator (8888) │          │ React Client (3000)         │
│   - 10초 간격 폴링          │          │   - setupProxy → 8888       │
├─────────────────────────────┤          ├─────────────────────────────┤
│ Camera Driver (8003)        │─────────►│ Model Service (8002)        │
│   - POST /trigger 호출      │          │   - SessionStore            │
│   - AVI 녹화 완료 시        │          │   - DoorSessionStore (v4.1) │
├─────────────────────────────┤          │   - YOLO 추론               │
│ IO Board (8000)             │          │   - 상품 판단               │
│ Payment (5000/5001)         │          └─────────────────────────────┘
│ MQTT Client (8006)          │
└─────────────────────────────┘
```

## 서비스 포트

| 서비스 | 포트 | 설명 | 관리 위치 |
|--------|------|------|-----------|
| Model | 8002 | YOLO 추론 + 상품 판단 | **이 레포** |
| React Client | 3000 | 웹 대시보드 UI | **이 레포** |
| Node.js | 8888 | 오케스트레이터 | 다른 레포 |
| Camera Driver | 8003 | 카메라 + AVI 녹화 | 다른 레포 |
| IO Board | 8000 | 로드셀 + 데드볼트 | 다른 레포 |
| Payment | 5000 | 결제 터미널 | 다른 레포 |

## Jetson Orin Nano 환경 설정

### 요구사항

| 항목 | 버전 | 비고 |
|------|------|------|
| 하드웨어 | Jetson Orin Nano Developer Kit | **4GB 모델** |
| OS | JetPack 6.2 (Ubuntu 22.04) | |
| Python | 3.10.x | JetPack 포함 |
| CUDA | 12.x | JetPack 포함 |
| cuDNN | 9.x | JetPack 포함 |
| TensorRT | 10.x | JetPack 포함 |
| FFmpeg | 4.x 이상 | `apt install ffmpeg` |
| NumPy | **1.x (< 2.0)** | 시스템 패키지 호환 필수 |

### uv 기반 환경 설정 (권장)

```bash
# 1. uv 설치 (없으면)
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"

# 2. 자동 설정 스크립트 실행
chmod +x scripts/setup_jetson.sh
./scripts/setup_jetson.sh

# 3. 가상환경 활성화
source .venv/bin/activate
```

### 수동 설정 (uv)

```bash
# 1. uv로 가상환경 생성 (시스템 패키지 상속 - CUDA/torch/tensorrt 필수!)
uv venv --system-site-packages --python python3.10 .venv
source .venv/bin/activate

# 2. 의존성 설치
uv pip install -e ".[dev]"

# 3. NumPy 버전 확인 (반드시 1.x)
python -c "import numpy; print(numpy.__version__)"
# 2.x면 다운그레이드:
uv pip install "numpy>=1.24.0,<2.0.0"
```

### TensorRT 엔진 변환

```bash
# .pt → .engine 변환 (Jetson에서만 가능, GPU 아키텍처 종속)
yolo export model=models/siyeon_best.pt format=engine device=0 half=True imgsz=480

# 결과 확인
ls -la models/siyeon_best.engine
```

### 환경 검증

```bash
# 1. CUDA 확인
python3 -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
# 기대: CUDA available: True

# 2. GPU 정보
python3 -c "import torch; print(torch.cuda.get_device_name(0))"
# 기대: Orin (또는 유사한 Jetson GPU 이름)

# 3. TensorRT 버전
python3 -c "import tensorrt; print(f'TensorRT: {tensorrt.__version__}')"

# 4. NumPy 버전 (반드시 1.x)
python3 -c "import numpy; print(f'NumPy: {numpy.__version__}')"
# 기대: 1.24.x 또는 1.26.x (NOT 2.x)

# 5. 서비스 시작 후 헬스 체크
curl http://localhost:8002/api/health
```

## 빠른 시작

### 1. 환경 설정
```bash
cp .env.example .env

# .env 주요 설정 (TensorRT 전용)
MODEL__VISION__YOLO_MODEL_PATH=models/siyeon_best.engine
MODEL__BUFFER__TTL_SECONDS=300
MODEL__BUFFER__MAX_SESSIONS=100
```

### 2. 의존성 설치 (uv)
```bash
# Jetson: uv + 시스템 패키지 상속
uv venv --system-site-packages --python python3.10 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### 3. 서비스 실행

```bash
# Model 서비스 직접 실행
cd services/model && python main.py
```

### 4. Docker 실행 (v4.2)

```bash
cd services/model

# 환경변수 설정
cp .env.docker .env

# Docker Compose로 실행 (Jetson GPU 사용)
docker-compose up -d

# 로그 확인
docker-compose logs -f model

# 헬스 체크
curl http://localhost:8002/api/health
```

## API 엔드포인트 (v4.2)

### 1. POST /trigger (Camera → Model)

Camera에서 녹화 완료 시 호출. 즉시 YOLO 추론 실행.

**Request:**
```json
{
  "zone": 1,
  "loadcells": [
    {
      "timestamp": "2026-02-01T14:30:25.123Z",
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

**Response:**
```json
{
  "success": true,
  "session_id": "zone_1_260201_143025",
  "door_session_id": "door_zone_1_260201_143000",
  "message": "추론 완료"
}
```

### 2. POST /api/judge/multi-zone (Node.js → Model)

데드볼트 문 열리면 10초 간격으로 폴링.

**Request:**
```json
{
  "session_id": "zone_1_260201_143025",
  "zone": 1,
  "products": [
    {"product_idx": "26", "product_name": "치킨마요", "sale_price": 3500, "product_weight": "365"}
  ]
}
```

**Response 1: Door Session 진행 중 (in_progress)**
```json
{
  "success": false,
  "status": "in_progress",
  "zone": 1,
  "door_session_id": "door_zone_1_260201_143000",
  "processing_stage": "door_session_active",
  "processing_stage_detail": "Door session 활성: 2개 trigger 수신",
  "interim_products": [
    {"productIdx": "26", "productId": 26, "name": "치킨마요", "count": 2, "price": 3500}
  ],
  "interimProductCount": 2,
  "interimTotalPrice": 7000,
  "doorSessionInfo": {
    "triggerCount": 2,
    "durationSeconds": 15.5,
    "createdAt": 1738476600.0,
    "lastTriggerAt": 1738476615.5
  }
}
```

**Response 2: Door Session 완료 (complete)**
```json
{
  "success": true,
  "status": "complete",
  "zone": 1,
  "door_session_id": "door_zone_1_260201_143000",
  "processing_stage": "complete",
  "processing_stage_detail": "Door session 완료: 3개 trigger 통합",
  "products": [
    {"productIdx": "26", "productId": 26, "name": "치킨마요", "count": 1, "price": 3500}
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
  }
}
```

### 3. GET /api/judge/session/{session_id} (세션 상태 조회)

**Response:**
```json
{
  "found": true,
  "session_id": "zone_1_260201_143025",
  "data": {
    "zone": 1,
    "status": "complete",
    "products": [...]
  }
}
```

### 4. GET /api/judge/sessions/stats (세션 통계)

**Response:**
```json
{
  "total_sessions": 10,
  "active_sessions": 3,
  "ttl_seconds": 300,
  "max_sessions": 100,
  "door_session_store": {
    "active_sessions": 1,
    "active_zones": [1]
  },
  "timestamp": 1738476700.0
}
```

### 5. GET /api/judge/door-sessions/stats (Door Session 통계)

**Response:**
```json
{
  "enabled": true,
  "active_sessions": 2,
  "active_zones": [1, 2],
  "session_timeout": 30.0,
  "weight_tolerance": 3.0,
  "max_duration": 600.0,
  "timestamp": 1738476700.0
}
```

### 6. GET /api/judge/door-session/{zone} (Door Session 조회)

**Response:**
```json
{
  "found": true,
  "zone": 1,
  "data": {
    "door_session_id": "door_zone_1_260201_143000",
    "status": "active",
    "triggers": [...],
    "aggregated_products": {...}
  }
}
```

### 7. POST /api/judge/door-session/{zone}/finalize (Door Session 강제 종료)

**Response:**
```json
{
  "success": true,
  "zone": 1,
  "door_session_id": "door_zone_1_260201_143000",
  "trigger_count": 3,
  "product_count": 2,
  "total_price": 7000,
  "message": "Door session finalized successfully"
}
```

### 헬스 체크

```bash
curl http://localhost:8002/api/health
# {"model": "HEALTHY", "status": "ok", "yolo_loaded": true, "session_store_ready": true}

curl http://localhost:8002/api/health/detailed
# 상세 정보 포함
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

| 변수 | 기본값 | 설명 |
|------|--------|------|
| MODEL__API__HOST | 0.0.0.0 | 서버 호스트 |
| MODEL__API__PORT | 8002 | 서버 포트 |
| MODEL__API__LOG_LEVEL | info | 로그 레벨 |
| MODEL__BUFFER__TTL_SECONDS | 300 | 세션 TTL (초) |
| MODEL__BUFFER__MAX_SESSIONS | 100 | 최대 세션 수 |
| MODEL__VISION__YOLO_MODEL_PATH | models/siyeon_best.engine | TensorRT 엔진 경로 |
| MODEL__VISION__TOP_WEIGHT | 0.5 | Top 카메라 가중치 |
| MODEL__VISION__SIDE_WEIGHT | 0.5 | Side 카메라 가중치 |
| MODEL__VISION__COMMON_CLASS_BONUS | 0.2 | 양쪽 감지 시 보너스 |
| MODEL__NODEJS_URL | http://localhost:8888 | Node.js URL |
| MODEL__DOOR_SESSION__TIMEOUT | 30.0 | Door Session 타임아웃 (초) |
| MODEL__DOOR_SESSION__WEIGHT_TOLERANCE | 3.0 | 반환 무게 매칭 허용 오차 (g) |
| MODEL__DOOR_SESSION__MAX_DURATION | 600.0 | Door Session 최대 지속 시간 (초) |

## 프로젝트 구조

```
Edge_Environment/
├── .env.example                  # 환경변수 예제
├── CLAUDE.md                     # 이 문서
├── README.md                     # 기본 README
├── pyproject.toml                # Python 프로젝트 설정
├── config/
│   └── yolo_product_mapping.json # YOLO 클래스-상품 매핑
├── models/
│   └── siyeon_best.engine        # TensorRT 엔진 (Jetson에서 생성)
├── client/                       # React Frontend (포트 3000)
└── services/
    └── model/                    # AI 상품 판단 (포트 8002)
        ├── main.py               # PM2 호환 진입점
        ├── Dockerfile            # Docker 빌드 (v4.2)
        ├── docker-compose.yml    # Docker Compose (v4.2)
        ├── .env.docker           # Docker 환경변수 템플릿 (v4.2)
        └── src/
            ├── api/
            │   ├── routes/       # 분리된 라우터
            │   │   ├── health.py     # GET /api/health
            │   │   ├── trigger.py    # POST /trigger
            │   │   ├── multi_zone.py # POST /api/judge/multi-zone
            │   │   └── products.py   # 상품 관리
            │   ├── deps.py       # 의존성 주입
            │   └── manager.py    # FastAPI 앱 팩토리 + TTL cleanup
            ├── service/          # 비즈니스 로직 레이어 (v4.2)
            │   ├── trigger_service.py      # 트리거 처리 서비스
            │   ├── judgment_service.py     # 판단 서비스
            │   └── door_session_service.py # DoorSession 서비스
            ├── session/          # 세션 저장소
            │   ├── session_store.py      # 기본 세션 저장소
            │   ├── door_session_store.py # Door Session 저장소 (v4.1)
            │   ├── door_session.py       # Door Session 데이터 모델
            │   ├── product_aggregator.py # 상품 통합/반환 처리
            │   └── yaml_persistence.py   # YAML 영속화
            ├── video/            # AVI 비디오 처리
            │   ├── video_processor.py
            │   ├── voting_ensemble.py
            │   └── frame_extractor.py
            ├── vision/           # YOLO 추론
            │   └── yolo_wrapper.py   # TensorRT 래퍼 (480x480, FP16)
            ├── weight/           # 무게 계산
            │   └── count_calculator.py
            ├── engine/           # 판단 엔진
            │   ├── decision_engine.py
            │   └── models.py
            ├── database/         # 상품 DB
            │   └── product_db.py
            └── core/             # 설정 (통합됨)
                ├── config.py     # 모든 설정 (유일한 config 파일)
                ├── exceptions.py
                └── logging_config.py
```

## 데이터 흐름 (v4.2)

```
┌─────────────────────────────────────────────────────────────┐
│                      데드볼트 문 열림                        │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
   [Camera]             [Node.js]              [IO Board]
   녹화 시작            폴링 시작              로드셀 모니터링
        │                  │                        │
        │                  │ POST /api/judge/multi-zone
        │                  │ (10초 간격)
        │                  ▼
        │            ┌─────────────────────────┐
        │            │ Model 서비스             │
        │            │ Door Session 없음        │
        │            │ → processing (waiting)   │
        │            └─────────────────────────┘
        │
        ▼ (녹화 완료 - 첫 번째)
   POST /trigger
   (zone=1, loadcells, videos)
        │
        ▼
┌────────────────────────────────────────────┐
│ Model 서비스 - 첫 번째 trigger             │
│                                            │
│ 1. VideoProcessor (AVI 처리)               │
│    - YOLO TensorRT 추론 → 치킨마요 2개     │
│                                            │
│ 2. delta_weight = -730g (제거)             │
│                                            │
│ 3. DoorSessionStore에 추가                 │
│    - 새 Door Session 생성                  │
│    - door_session_id 발급                  │
│    - ProductAggregator: 치킨마요 x2 합산   │
│                                            │
│ 4. SessionStore에도 저장 (하위 호환)       │
└────────────────────────────────────────────┘
        │
        ▼
   [Node.js 폴링]
   POST /api/judge/multi-zone (zone=1)
        │
        ▼
┌────────────────────────────────────────────┐
│ Model 서비스                                │
│ DoorSession 활성 → in_progress 응답        │
│ interim_products: 치킨마요 x2              │
└────────────────────────────────────────────┘
        │
        ▼
   [Camera 두 번째 trigger - 반환 감지]
   POST /trigger (delta=+365g)
        │
        ▼
┌────────────────────────────────────────────┐
│ Model 서비스 - 두 번째 trigger (반환)      │
│                                            │
│ 1. delta_weight = +365g (반환)             │
│    - is_return = true                      │
│                                            │
│ 2. DoorSessionStore에 추가                 │
│    - ProductAggregator: 무게 매칭          │
│    - 치킨마요(365g) 1개 차감               │
│    - 결과: 치킨마요 x1                     │
└────────────────────────────────────────────┘
        │
        ▼
   [30초 타임아웃 - 문 닫힘]
        │
        ▼
   [Node.js 폴링]
   POST /api/judge/multi-zone (zone=1)
        │
        ▼
┌────────────────────────────────────────────┐
│ Model 서비스                                │
│ DoorSession 타임아웃 → complete 응답       │
│ products: 치킨마요 x1                      │
│ totalPrice: 3500                           │
└────────────────────────────────────────────┘
```

### Door Session 개념 (v4.1)

```
┌─────────────────────────────────────────────────────────────────┐
│                      Door Session                                │
│  (문 열림 ~ 타임아웃까지의 모든 trigger 통합)                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  trigger_001 (제거)     trigger_002 (제거)    trigger_003 (반환) │
│  ├─ delta: -730g        ├─ delta: -250g       ├─ delta: +365g   │
│  ├─ 치킨마요 x2         ├─ 참치마요 x1        └─ (무게 매칭)    │
│  └─ is_return: false    └─ is_return: false       is_return: true│
│                                                                  │
│                    ▼ ProductAggregator ▼                        │
│                                                                  │
│  aggregated_products:                                            │
│  ├─ 치킨마요: 2 - 1 = 1개 (반환 1개 차감)                        │
│  └─ 참치마요: 1개                                                │
│                                                                  │
│  최종 결과: 치킨마요 3500원 + 참치마요 3000원 = 6500원           │
└─────────────────────────────────────────────────────────────────┘
```

## 가중치 계산 (v4.0)

```
상품 A: Top(0.8) + Side(0.7) 감지
  = 0.8 × 0.5 + 0.7 × 0.5 + 0.2 = 0.95

상품 B: Top(0.9) only
  = 0.9 × 0.5 = 0.45

상품 C: Side(0.85) only
  = 0.85 × 0.5 = 0.425
```

## 에러 처리

### HTTP 상태 코드

| 코드 | 상황 | 에러 코드 |
|------|------|-----------|
| 400 | 비디오 파일 없음 | `VIDEO_FILE_NOT_FOUND` |
| 400 | 잘못된 요청 | `VALIDATION_ERROR` |
| 500 | 비디오 손상 | `VIDEO_CORRUPTED` |
| 500 | FFmpeg 오류 | `FFMPEG_ERROR` |
| 500 | YOLO GPU 오류 | `YOLO_GPU_ERROR` |
| 503 | YOLO 모델 미로드 | `YOLO_MODEL_NOT_LOADED` |

### 에러 응답 형식

```json
{
  "detail": {
    "error_code": "VIDEO_FILE_NOT_FOUND",
    "message": "Video file not found: /path/to/video.avi",
    "video_path": "/path/to/video.avi"
  }
}
```

## 트러블슈팅

### CUDA 관련

```bash
# CUDA 사용 불가
# → JetPack 재설치 또는 CUDA 경로 확인
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH

# TensorRT 버전 불일치
# → Jetson에서 .engine 파일 재생성
yolo export model=models/siyeon_best.pt format=engine device=0 half=True imgsz=480
```

### 메모리 부족

```bash
# GPU 메모리 모니터링
tegrastats

# 성능 모드 설정 (MAXN)
sudo nvpmodel -m 0
sudo jetson_clocks
```

### FFmpeg 오류

```bash
# FFmpeg 설치 확인
ffmpeg -version

# MJPEG 코덱 지원 확인
ffmpeg -codecs | grep mjpeg
```

## 테스트 실행

```bash
# 전체 테스트 실행
cd Edge_Environment
pytest services/model/tests -v

# 특정 테스트 파일 실행
pytest services/model/tests/test_door_session_store.py -v
pytest services/model/tests/test_product_aggregator.py -v
pytest services/model/tests/test_voting_ensemble.py -v

# 테스트 커버리지 (pytest-cov 필요)
pytest services/model/tests --cov=services/model/src --cov-report=html
```

### 테스트 파일 구조

| 파일 | 테스트 대상 | 테스트 수 |
|------|------------|----------|
| `test_session_store.py` | SessionStore CRUD, TTL | 11 |
| `test_door_session_store.py` | DoorSessionStore, 타임아웃, 동시성 | 12 |
| `test_product_aggregator.py` | 상품 합산, 반환 처리 | 10 |
| `test_voting_ensemble.py` | 투표 앙상블, Top/Side 결합 | 14 |
| `test_trigger_helpers.py` | 무게 계산 헬퍼 | 15 |
| `test_api_routes.py` | API 엔드포인트 | 7 |
| `test_deps.py` | 의존성 주입 | 8 |
| `test_pipeline.py` | E2E 파이프라인 | 8 |
| `test_scenario.py` | 실제 시나리오 | 14 |
| `test_error_handling.py` | 예외 처리 | 14 |
| **총계** | | **116** |

## 삭제된 API (v3.0 → v4.0)

| API | 대체 방법 |
|-----|----------|
| POST /api/frame | 제거 (AVI Trigger만 사용) |
| POST /api/judge | POST /api/judge/multi-zone 사용 |
| GET /api/frame/stats | GET /trigger/stats 사용 |

## 기타 서비스 디렉토리 위치

'현위치': "~\VOICE\2026\crk\win_pc_test_sw2io_board\Edge_Environment"
'camera': "~\VOICE\2026\crk\CRK-CAMERA"
'io board': "~\VOICE\2026\crk\CRK-IO-BOARD"
'payment': "~\VOICE\2026\crk\CRK-PAYMENT"
'node': "~\VOICE\2026\crk\Edge_Environment"

## TODO (추후 구현)

### has_loadcell 필드 지원

**배경**: 자판기 하드웨어 모델에 따라 로드셀이 있는 모델과 없는 모델이 존재함.

**현재 상태**:
- Node.js가 `has_loadcell: "true"/"false"/"null"` 필드를 전송
- Model 서비스의 `ProductInfo`는 `loadcell` 필드명으로 정의되어 있어 무시됨
- 현재는 모든 상품에 대해 로드셀 기반 무게 검증을 수행

**구현 필요 사항**:
1. `ProductInfo.loadcell` → `has_loadcell`로 필드명 변경
2. `has_loadcell == "false"` 또는 `"null"`인 상품은 무게 검증 로직에서 제외
3. Vision-only 모드: 로드셀 없는 하드웨어에서는 YOLO 추론 결과만으로 상품 판단

**영향 범위**:
- `services/model/src/api/routes/multi_zone.py` - ProductInfo 모델
- `services/model/src/engine/decision_engine.py` - 무게 기반 개수 계산
- `services/model/src/session/product_aggregator.py` - 반환 처리 (무게 매칭)