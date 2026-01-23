# Edge Environment Services - minkyu 브랜치

## 브랜치 정보
- **브랜치명**: minkyu
- **목적**: Model 서비스 개발 및 테스트
- **Pull Request 시 제외 예정**: 이 README 파일, INTEGRATION_GUIDE.md

---

## 빠른 시작

### Node.js 총괄 담당자용
**[INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md)** 를 참조하세요.

포함 내용:
- Node.js → Model 서비스 연동 방법
- API 사용 예시 (ProductJudgeClient, IOBoardClient)
- 테스트 방법 (오프라인/하드웨어/전체 시스템)
- 데이터 흐름 및 아키텍처 설명

### 필수 파일 (별도 제공)
| 파일 | 위치 | 설명 |
|------|------|------|
| `siyeon_best.pt` | 프로젝트 루트 | YOLO 모델 (133개 클래스, 6.63MB) |
| `test_dataset/` | 프로젝트 루트 | 테스트 이미지 데이터셋 (13개 세션) |

---

## 서비스 구조

```
Edge_Environment/
├── services/
│   ├── io_board/          # IO Board 통합 (포트 8001)
│   ├── model/             # AI 상품 판단 서비스 (포트 8002) ★ 신규
│   ├── camera_driver/     # 6대 카메라 관리 (포트 8003)
│   ├── mqtt_client/       # MQTT CHAI IF01-04 (포트 8006)
│   └── card_terminal/     # 결제 터미널 (포트 5000)
└── README_MINKYU.md       # 이 파일 (브랜치 전용)
```

> **삭제됨**: deadbolt_driver (8004), loadcell_driver (8005) → io_board에 통합

---

## Model 서비스 상세

### 디렉토리 구조
```
services/model/
├── main.py                      # FastAPI 진입점 + --test 모드
├── config.py                    # Zone-Channel-Camera 매핑
├── requirements.txt
│
├── sse_client/                  # io_board SSE 구독
│   ├── io_board_subscriber.py
│   ├── event_parser.py
│   └── zone_detector.py
│
├── camera/                      # 이미지 캡처
│   ├── camera_client.py         # camera_driver HTTP 클라이언트
│   └── frame_capturer.py        # FrameCapturer + FolderFrameLoader
│
├── vision/                      # YOLO 추론 파이프라인
│   ├── yolo_wrapper.py
│   ├── hand_filter.py
│   ├── top5_extractor.py
│   └── multi_view_ensemble.py
│
├── weight/                      # 무게 기반 개수 계산
│   └── count_calculator.py
│
├── engine/                      # 판단 엔진
│   ├── models.py
│   ├── decision_engine.py
│   └── event_tracker.py
│
├── database/                    # 상품 DB (50개 기본 상품)
│   └── product_db.py
│
├── api/                         # REST API
│   ├── routes.py                # /api/judge, /api/health
│   └── node_client.py           # Node.js 결과 전송
│
├── monitor/                     # --test 모드 대시보드
│   ├── console_dashboard.py
│   └── test_mode.py
│
└── tests/                       # 단위 테스트 (6개 파일)
    ├── conftest.py
    ├── test_config.py
    ├── test_count_calculator.py
    ├── test_decision_engine.py
    ├── test_product_db.py
    └── test_top5_extractor.py
```

### 주요 설정 (config.py)
```python
# 변경된 파라미터 (2026-01-21)
top_k: int = 1              # Top-1만 추출 (최고 confidence 클래스)
top_weight: float = 0.5     # Top 카메라 가중치 (5:5 동일)
side_weight: float = 0.5    # Side 카메라 가중치 (5:5 동일)
tolerance_percent: float = 0.10  # 허용 오차 10%
```

### Loadcell-only 폴백 메커니즘
Vision 판단 실패(NO_DETECTION, UNCERTAIN) 시 무게만으로 가장 가까운 상품을 추정합니다.

```python
# decision_engine.py
def judge_by_weight_only(delta_weight: float) -> JudgmentResult:
    """
    무게만으로 가장 가까운 상품 추정 (Vision 실패 시 폴백).

    - 모든 상품 중 무게 차이가 가장 작은 상품 찾기
    - tolerance_percent 범위 내: status=PARTIAL, confidence 최대 70%
    - tolerance_percent 범위 외: status=UNCERTAIN, confidence 최대 50%
    """
```

---

## 실행 방법

### 일반 모드 (FastAPI 서버)
```bash
cd Edge_Environment/services/model
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8002 --reload
```

### 테스트 모드 (콘솔 대시보드)
```bash
cd Edge_Environment/services/model
python -m main --test
```

### 단위 테스트
```bash
cd Edge_Environment/services/model
python -m pytest tests/ -v
```

---

## API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | /api/judge | 상품 판단 요청 |
| GET | /api/health | 헬스 체크 |
| GET | /api/products | 상품 목록 |

### /api/judge 요청 예시
```json
{
    "zone_id": 0,
    "loadcell_weights": ["+00432", "+00433", ...],
    "baseline_weights": ["+00800", "+00800", ...],
    "snapshot_folder": "/data/260121_1200/",
    "products": [
        {"id": 26, "name": "chickenmayo_rice", "weight": 365, "price": 3500}
    ]
}
```

### /api/judge 응답 예시
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
    "timestamp": 1737046800.123
}
```

---

## 변경 이력

### 2026-01-22 (2차)
- **IF11 상품 리스트 지원**: Node.js → Model 상품 동기화 (`/api/products/sync`)
- **에러 복구 모듈**: `error_recovery/` (RecoveryManager, ErrorCode, ServiceError)
- **카메라 디바이스 스캐너**: `device_scanner.py` (고유 ID 기반 재매핑)
- **테스트 추가**: `test_error_recovery.py`, `test_product_registration.py` (36+ 테스트)

### 2026-01-22 (1차)
- **모델 교체**: `1224_v8n_img480_best_aug_segment.pt` → `siyeon_best.pt`
- **클래스 확장**: 131개 → 133개 (hand + 132개 상품)
- **ecosystem.config.js**: YOLO_MODEL_PATH 업데이트
- **test_offline_dataset.py**: Windows 바로가기(.lnk) 파일 지원 추가
- **테스트 데이터셋 확장**: 2개 → 13개 세션 (Google Drive 연동)
- **평균 Confidence 26% 향상**: 0.357 → 0.450

### 2026-01-21
- **config.py**: top_k=5 → top_k=1 (최고 confidence만 추출)
- **config.py**: 앙상블 가중치 4:6 → 5:5 (동일 가중치)
- **decision_engine.py**: `judge_by_weight_only()` 폴백 메서드 추가
- **decision_engine.py**: Vision 실패 시 자동 폴백 호출

### 이전 커밋
- Model 서비스 기본 구조 생성 (30개 파일)
- 단위 테스트 작성 (6개 파일, 1,072줄)
- io_board 서비스 커밋
- camera_driver, card_terminal, mqtt_client 커밋
- .gitignore 업데이트

---

## Zone 매핑 정보

### Zone-Channel-Camera 매핑
| Zone | LoadCell Channels | Side Camera | Top Camera |
|------|-------------------|-------------|------------|
| Zone 0 | 0, 1 | CAM 1 | CAM 0 (공유) |
| Zone 1 | 2, 3 | CAM 2 | CAM 0 (공유) |
| Zone 2 | 4, 5 | CAM 3 | CAM 0 (공유) |
| Zone 3 | 6, 7 | CAM 4 | CAM 0 (공유) |
| Zone 4 | 8, 9 | CAM 5 | CAM 0 (공유) |

---

---

## PM2로 전체 서비스 실행

### PM2 설치 (최초 1회)
```bash
npm install -g pm2
```

### 전체 서비스 시작
```bash
cd Edge_Environment
pm2 start ecosystem.config.js
```

### 서비스 목록 (ecosystem.config.js)

| 서비스명 | 포트 | 설명 |
|---------|------|------|
| orchestrator | 8888 | Node.js 메인 서버 |
| io-board | 8001 | IO Board 제어 (로드셀+데드볼트) |
| model | 8002 | AI 상품 판단 |
| camera-driver | 8003 | 6대 카메라 관리 |
| card-terminal | 5000 | 결제 터미널 |

### PM2 명령어
```bash
# 상태 확인
pm2 list

# 로그 확인
pm2 logs
pm2 logs model

# 개별 서비스 실행
pm2 start ecosystem.config.js --only model
pm2 start ecosystem.config.js --only "io-board,model,camera-driver"

# 재시작/중지
pm2 restart model
pm2 stop all
pm2 delete all
```

---

## Model 서비스 테스트

### 테스트 종류

| 테스트 | 설명 | 파일 |
|--------|------|------|
| **오프라인 테스트** | pt 파일 + 데이터셋 (로드셀 정확 가정) | `tests/test_offline_dataset.py` |
| **하드웨어 테스트** | 실제 IO Board + 카메라 연동 | `tests/test_hardware_integration.py` |

### 1. 오프라인 테스트 (Vision 파이프라인)

```bash
cd Edge_Environment/services/model

# 전체 데이터셋 테스트
python -m tests.test_offline_dataset

# 특정 세션만
python -m tests.test_offline_dataset --session 20260116_180419

# 특정 프레임만
python -m tests.test_offline_dataset --session 20260116_180419 --frame 10

# 시각화 결과 저장
python -m tests.test_offline_dataset --visualize --output-dir ./viz_results

# JSON 결과 저장
python -m tests.test_offline_dataset --output results.json

# 커스텀 모델/데이터셋
python -m tests.test_offline_dataset \
  --model "C:\path\to\model.pt" \
  --dataset "C:\path\to\test_dataset"
```

**테스트 데이터셋 구조:**
```
test_dataset/
├── 20260116_180419/              # 로컬 폴더
│   ├── cam_0.mp4                 # Top 카메라
│   ├── cam_2.mp4                 # Side 카메라 (Zone 1)
│   └── images/
│       ├── cam_0/frame_*.jpg     # Top 프레임들
│       └── cam_2/frame_*.jpg     # Side 프레임들
├── 20260116_175306.lnk           # Google Drive 바로가기 (자동 해석)
├── 20260116_175426.lnk
└── ...
```

> **참고**: Windows 바로가기(.lnk) 파일은 자동으로 Google Drive 경로로 해석됩니다.

### 2. 하드웨어 연동 테스트

**필수 조건**: io_board(8001), camera_driver(8003), model(8002) 실행 중

```bash
cd Edge_Environment/services/model

# 서비스 연결 확인
python -m tests.test_hardware_integration --check-connection

# SSE 이벤트 모니터링 (10초)
python -m tests.test_hardware_integration --monitor-sse --duration 10

# Zone 캡처 테스트
python -m tests.test_hardware_integration --capture-zone 1

# 전체 Zone 스캔
python -m tests.test_hardware_integration --scan-all-zones

# 수동 판단 테스트
python -m tests.test_hardware_integration --manual-judge --zone 1 --delta -365

# 실시간 모니터링 + 자동 판단 (60초)
python -m tests.test_hardware_integration --realtime-monitor --duration 60

# 정확도 테스트 (10회 반복)
python -m tests.test_hardware_integration --accuracy-test --zone 1 --repeat 10

# 특정 상품 정확도 테스트
python -m tests.test_hardware_integration \
  --accuracy-test \
  --zone 1 \
  --repeat 10 \
  --delta -365 \
  --expected-product "chickenmayo_rice"
```

---

## HTTP API 테스트 (curl)

### 헬스 체크
```bash
curl http://localhost:8002/api/health
curl http://localhost:8001/health
curl http://localhost:8003/health
```

### 상품 판단 (POST /api/judge)
```bash
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 1,
    "delta_weight": -365.0,
    "loadcell_weights": ["+00000", "+00000", "-00180", "-00185", "+00000", "+00000", "+00000", "+00000", "+00000", "+00000"],
    "baseline_weights": ["+00000", "+00000", "+00000", "+00000", "+00000", "+00000", "+00000", "+00000", "+00000", "+00000"]
  }'
```

### 다중 Zone 판단 (Cross-Zone 감지)
```bash
curl -X POST http://localhost:8002/api/judge/multi-zone \
  -H "Content-Type: application/json" \
  -d '{
    "zone_deltas": [
      {"zone_id": 0, "delta": -365.0},
      {"zone_id": 1, "delta": 365.0}
    ],
    "check_cross_zone": true
  }'
```

### 히스토리 기반 판단 (반환 감지)
```bash
curl -X POST http://localhost:8002/api/judge/with-history \
  -H "Content-Type: application/json" \
  -d '{
    "current_request": {"zone_id": 0, "delta_weight": 365.0},
    "recent_events": [
      {"timestamp": 1737450000.0, "zone_id": 0, "delta_weight": -365.0, "direction": "pickup", "product_name": "chickenmayo_rice"}
    ],
    "check_return": true
  }'
```

### 인식률 통계
```bash
curl http://localhost:8002/api/stats/recognition-rate
```

### SSE 스트림 구독 (io_board)
```bash
curl -N "http://localhost:8001/sse?streams=loadcells&filter_method=exponential&filter_alpha=0.2&threshold=5.0"
```

### 카메라 프레임 캡처
```bash
curl http://localhost:8003/frame/0 --output top_cam.jpg    # Top
curl http://localhost:8003/frame/2 --output side_cam.jpg   # Zone 1
curl -X POST http://localhost:8003/zone/1/activate          # Zone 활성화
```

---

## YOLO 모델 정보

- **파일**: `siyeon_best.pt` (프로젝트 루트)
- **클래스 수**: 133개 (hand + 132개 상품)
- **입력 해상도**: 480px
- **모델 크기**: 6.63 MB

### 최신 테스트 결과 (2026-01-22)

| 항목 | 값 |
|------|-----|
| 테스트 세션 | 13개 |
| 총 프레임 | 408개 |
| 감지율 | 100% |
| 평균 Confidence | 0.450 |
| 평균 처리 시간 | 112ms/frame |

**이전 모델 대비 개선:**
- 클래스 수: 131 → 133 (+2)
- 평균 Confidence: 0.357 → 0.450 (+26%)

---

## 참고 사항

- 이 README는 minkyu 브랜치 전용입니다.
- Pull Request 시 이 파일은 제외됩니다.
- 메인 문서는 루트의 `CLAUDE.md` 파일을 참조하세요.
