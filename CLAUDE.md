# Edge Environment Lite - Model 서비스

AI 스마트 자판기 시스템의 Model 서비스 (v4.0 AVI Trigger API)
**Jetson Orin Nano 4GB (JetPack 6.2) TensorRT 전용**

> **최종 업데이트**: 2026-02-01

## 개요

이 레포는 **Model** 서비스만 관리합니다.
**TensorRT 엔진(.engine)** 파일만 지원하며, **CUDA가 필수**입니다.
Node.js, IO Board, Payment, Camera Driver는 별도 레포에서 관리됩니다.

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

## 아키텍처 (v4.0)

```
다른 레포                                 이 레포
┌─────────────────────────────┐          ┌─────────────────────────────┐
│ Node.js Orchestrator (8888) │          │ React Client (3000)         │
│   - 10초 간격 폴링          │          │   - setupProxy → 8888       │
├─────────────────────────────┤          ├─────────────────────────────┤
│ Camera Driver (8003)        │─────────►│ Model Service (8002)        │
│   - POST /trigger 호출      │          │   - SessionStore            │
│   - AVI 녹화 완료 시        │          │   - YOLO 추론               │
├─────────────────────────────┤          │   - 상품 판단               │
│ IO Board (8000)             │          └─────────────────────────────┘
│ Payment (5000/5001)         │
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

## API 엔드포인트 (v4.0)

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
  "message": "추론 완료"
}
```

### 2. POST /api/judge/multi-zone (Node.js → Model)

데드볼트 문 열리면 10초 간격으로 폴링.

**Request:**
```json
{
  "session_id": "zone_1_260201_143025",
  "products": [
    {"product_idx": "26", "product_name": "치킨마요", "sale_price": 3500, "product_weight": "365"}
  ]
}
```

**Response 1: 판단 안됨**
```json
{
  "status": "processing",
  "message": "YOLO 추론 대기 중"
}
```

**Response 2: 판단 완료**
```json
{
  "status": "complete",
  "products": [
    {"productId": 26, "name": "치킨마요", "count": 1, "price": 3500}
  ],
  "totalPrice": 3500
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
        └── src/
            ├── api/
            │   ├── routes/       # 분리된 라우터
            │   │   ├── health.py     # GET /api/health
            │   │   ├── trigger.py    # POST /trigger
            │   │   ├── multi_zone.py # POST /api/judge/multi-zone
            │   │   └── products.py   # 상품 관리
            │   ├── deps.py       # 의존성 주입
            │   └── manager.py    # FastAPI 앱 팩토리
            ├── session/          # 세션 저장소
            │   └── session_store.py
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
            └── core/             # 설정
                ├── config.py
                ├── exceptions.py
                └── logging_config.py
```

## 데이터 흐름 (v4.0)

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
        │            ┌─────────────┐
        │            │ Model 서비스 │
        │            │ 세션 없음    │
        │            │ → processing │
        │            └─────────────┘
        │
        ▼ (녹화 완료)
   POST /trigger
   (zone, loadcells, videos)
        │
        ▼
┌───────────────────────────────────────┐
│ Model 서비스                           │
│                                       │
│ 1. VideoProcessor (AVI 처리)          │
│    - FFmpeg -c:v mjpeg 프레임 추출    │
│    - 480x480 크롭 (오른쪽 160px 제거) │
│    - YOLO TensorRT 추론 (FP16)        │
│    - VotingEnsemble                   │
│                                       │
│ 2. 로드셀 → delta_weight 계산         │
│                                       │
│ 3. Top-5 후보군 추출                  │
│                                       │
│ 4. 무게 기반 개수 계산                │
│                                       │
│ 5. SessionStore에 결과 저장           │
└───────────────────────────────────────┘
        │
        ▼
   [Node.js 다음 폴링]
   POST /api/judge/multi-zone
        │
        ▼
┌───────────────────────────────────────┐
│ Model 서비스                           │
│ SessionStore에서 결과 조회            │
│ → {"status": "complete", ...}         │
└───────────────────────────────────────┘
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

## 삭제된 API (v3.0 → v4.0)

| API | 대체 방법 |
|-----|----------|
| POST /api/frame | 제거 (AVI Trigger만 사용) |
| POST /api/judge | POST /api/judge/multi-zone 사용 |
| GET /api/frame/stats | GET /trigger/stats 사용 |
