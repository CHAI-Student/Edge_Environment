# Edge Environment Services - minkyu 브랜치

## 브랜치 정보
- **브랜치명**: minkyu
- **목적**: Model 서비스 개발 및 테스트
- **최종 업데이트**: 2026-01-29
- **Pull Request 시 제외 예정**: 이 README 파일, INTEGRATION_GUIDE.md

> **아키텍처 (2026-01-29)**:
> - Model 서비스: **Stateless** (판단 전용)
> - Node.js: Event-Driven Architecture (SSE 구독 + 세션 관리)
> - Vision: Motion Tracking + Multi-View Ensemble 지원

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
│   ├── model/             # AI 상품 판단 서비스 (포트 8002)
│   ├── camera_driver/     # 6대 카메라 관리 (포트 8003)
│   ├── mqtt_client/       # MQTT CHAI IF01-04 (포트 8006)
│   └── card_terminal/     # 결제 터미널 (포트 5000)
├── server/                # Node.js 오케스트레이터 (포트 8889)
│   ├── services/          # 핵심 서비스 모듈
│   └── routes/            # API 라우트
├── client/                # React 대시보드 (포트 3000)
└── README_MINKYU.md       # 이 파일 (브랜치 전용)
```

> **PM2 통합**: `npm start`로 모든 서비스 동시 실행

---

## Model 서비스 상세 (Stateless 아키텍처)

> **삭제된 폴더/파일**:
> - `src/sse_client/` (SSE 구독 → Node.js로 이전)
> - `src/api/node_client.py` (결과 푸시 → 동기 응답으로 변경)

### 디렉토리 구조
```
services/model/
├── main.py                      # FastAPI 진입점 (Stateless)
└── src/                         # ★ 소스 코드 폴더
    ├── config.py                # Zone-Channel-Camera 매핑 + Vision 설정
    │
    ├── api/                     # REST API
    │   ├── routes.py            # /api/judge, /api/products, /api/door/*
    │   └── models.py            # Pydantic 스키마 (WeightData, MediaPaths)
    │
    ├── camera/                  # 이미지 로드 (Node.js가 전달한 경로에서)
    │   ├── camera_client.py     # camera_driver HTTP 클라이언트 (폴백용)
    │   └── frame_capturer.py    # FolderFrameLoader
    │
    ├── vision/                  # YOLO 추론 파이프라인
    │   ├── yolo_wrapper.py      # .pt 또는 .engine 지원
    │   ├── hand_filter.py       # 손 근접 필터
    │   ├── top5_extractor.py    # Top-K 추출
    │   ├── multi_view_ensemble.py   # Top+Side 앙상블
    │   ├── multi_hand_detector.py   # 다중 손 감지
    │   └── motion_correlation_filter.py  # ★ Motion Tracking
    │
    ├── weight/                  # 무게 기반 개수 계산
    │   ├── count_calculator.py
    │   └── multi_zone_monitor.py
    │
    ├── engine/                  # 판단 엔진
    │   ├── models.py
    │   ├── decision_engine.py
    │   ├── event_tracker.py
    │   └── advanced/            # 고급 시나리오
    │       ├── baseline_manager.py  # 베이스라인 드리프트 보정
    │       ├── return_detector.py   # 반환 감지
    │       ├── cross_zone_detector.py  # Zone 간 이동
    │       └── rapid_pickup_handler.py # 연속 픽업
    │
    ├── database/                # 상품 DB
    │   └── product_db.py        # IF11 형식 지원
    │
    ├── door_payment/            # 도어 결제 모듈
    │   ├── __init__.py          # DoorPaymentController export
    │   ├── controller.py
    │   └── payment_client.py
    │
    ├── monitor/                 # --test 모드 대시보드
    │   ├── console_dashboard.py
    │   └── test_mode.py
    │
    ├── error_recovery/          # 에러 복구 모듈
    │
    └── tests/                   # 단위 테스트
        ├── conftest.py
        └── test_*.py
```

### 주요 설정 (src/config.py)
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
# src/engine/decision_engine.py
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

### PM2 통합 실행 (권장)
```bash
cd Edge_Environment
npm start                                    # 전체 서비스 시작
pm2 start ecosystem.config.js --only model   # Model 서비스만 시작
```

### 개별 서비스 실행 (개발용)
```bash
cd Edge_Environment/services/model
python main.py                               # FastAPI 서버 시작 (포트 8002)

# 환경 변수 지정
LOG_LEVEL=DEBUG python main.py              # 디버그 모드
```

### 단위 테스트
```bash
cd Edge_Environment/services/model
python -m pytest src/tests/ -v
```

---

## API 엔드포인트

### 핵심 API
| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | /api/health | 헬스 체크 |
| GET | /api/zones/config | Zone 설정 조회 |
| POST | /api/judge | 상품 판단 요청 (메인) |
| POST | /api/judge/cancel | 추론 취소 |
| GET | /api/judge/active | 활성 추론 목록 |
| POST | /api/judge/multi-zone | 다중 Zone 판단 |
| POST | /api/judge/with-history | 히스토리 기반 판단 |

### 상품 관리 API
| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | /api/products | 상품 목록 |
| GET | /api/products/{id} | 상품 상세 |
| POST | /api/products/register | 상품 등록 |
| PUT | /api/products/{id} | 상품 수정 |
| DELETE | /api/products/{id} | 상품 삭제 |
| POST | /api/products/sync | IF11 형식 동기화 |
| GET | /api/products/export | 전체 내보내기 |
| GET | /api/products/search | 이름 검색 |
| GET | /api/products/barcode/{bc} | 바코드 조회 |
| POST | /api/products/{id}/images | 이미지 업로드 |

### 통계 API
| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | /api/stats/recognition-rate | 인식률 통계 |
| POST | /api/stats/reset | 통계 초기화 |

### Door Payment API
| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | /api/door/transaction | 도어 결제 시작 |
| GET | /api/door/status | 도어 상태 |
| POST | /api/door/cancel | 거래 취소 |
| POST | /api/door/emergency-lock | 비상 잠금 |

### /api/judge 요청 예시 (권장 형식)
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
        "image_folder": "/data/snapshots/260126143025",
        "top_image": "/data/snapshots/260126143025/cam_0/snapshot.jpg",
        "side_image": "/data/snapshots/260126143025/cam_1/snapshot.jpg"
    }
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

### 2026-01-29 ★ 최신
- **Motion Tracking 추가**: `src/vision/motion_correlation_filter.py`
  - 연속 프레임 분석으로 손 움직임 추적
  - motion_bonus_map으로 신뢰도 보정
- **Event-Driven Architecture**: Node.js 세션 관리 강화
  - `WeightChangeAccumulator`: 무게 변화 누적 처리
  - `PendingItemsStack`: 세션별 픽업/반환 관리
- **추론 취소 기능**: `/api/judge/cancel`, `/api/judge/active`
- **카메라별 결과 반환**: `camera_results` 필드 추가

### 2026-01-28
- **통합 npm 실행**: `npm start`로 React 클라이언트 포함 전체 서비스 실행
- **PM2 ecosystem 업데이트**: React client (port 3000) 추가

### 2026-01-26 ★ 아키텍처 변경
- **Model 서비스 Stateless 전환**
  - `src/sse_client/` 폴더 삭제 (SSE 구독 → Node.js로 이전)
  - `src/api/node_client.py` 삭제 (결과 푸시 → 동기 응답)
- **새로운 API 형식**: `weight_data` + `media_paths`
- **Node.js 포트 변경**: 8888 → 8889
- **Door Payment 모듈 추가**: `src/door_payment/`
- **Advanced 엔진 모듈 추가**: `src/engine/advanced/`
  - `baseline_manager.py` - 베이스라인 드리프트 보정
  - `return_detector.py` - 반환 감지
  - `cross_zone_detector.py` - Zone 간 이동
  - `rapid_pickup_handler.py` - 연속 픽업

### 2026-01-22 (2차)
- **IF11 상품 리스트 지원**: Node.js → Model 상품 동기화 (`/api/products/sync`)
- **에러 코드 체계**: E2xxx (IO Board), E3xxx (Camera), E4xxx (Vision), E5xxx (Network), E6xxx (Payment)
- **카메라 디바이스 스캐너**: `src/core/device_scanner.py` (고유 ID 기반 재매핑)

### 2026-01-22 (1차)
- **모델 교체**: `1224_v8n_img480_best_aug_segment.pt` → `siyeon_best.pt`
- **클래스 확장**: 131개 → 133개 (hand + 132개 상품)
- **테스트 데이터셋 확장**: 2개 → 13개 세션 (Google Drive 연동)
- **평균 Confidence 26% 향상**: 0.357 → 0.450

### 2026-01-21
- **src/config.py**: top_k=5 → top_k=1 (최고 confidence만 추출)
- **src/config.py**: 앙상블 가중치 4:6 → 5:5 (동일 가중치)
- **src/engine/decision_engine.py**: `judge_by_weight_only()` 폴백 메서드 추가

### 이전 커밋
- Model 서비스 기본 구조 생성
- io_board, camera_driver, mqtt_client 서비스 구현
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
| orchestrator | **8889** | Node.js 오케스트레이터 (SSE 구독 + 스냅샷 요청) ★ |
| io-board | 8001 | IO Board SSE 스트림 (로드셀+데드볼트) |
| model | 8002 | AI 상품 판단 (Stateless) |
| camera-driver | 8003 | 6대 카메라 관리 + 스냅샷 저장 |
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
| **오프라인 테스트** | pt 파일 + 데이터셋 (로드셀 정확 가정) | `src/tests/test_offline_dataset.py` |
| **하드웨어 테스트** | 실제 IO Board + 카메라 연동 | `src/tests/test_hardware_integration.py` |

### 1. 오프라인 테스트 (Vision 파이프라인)

```bash
cd Edge_Environment/services/model

# 전체 데이터셋 테스트
python -m src.tests.test_offline_dataset

# 특정 세션만
python -m src.tests.test_offline_dataset --session 20260116_180419

# 특정 프레임만
python -m src.tests.test_offline_dataset --session 20260116_180419 --frame 10

# 시각화 결과 저장
python -m src.tests.test_offline_dataset --visualize --output-dir ./viz_results

# JSON 결과 저장
python -m src.tests.test_offline_dataset --output results.json

# 커스텀 모델/데이터셋
python -m src.tests.test_offline_dataset \
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
python -m src.tests.test_hardware_integration --check-connection

# SSE 이벤트 모니터링 (10초)
python -m src.tests.test_hardware_integration --monitor-sse --duration 10

# Zone 캡처 테스트
python -m src.tests.test_hardware_integration --capture-zone 1

# 전체 Zone 스캔
python -m src.tests.test_hardware_integration --scan-all-zones

# 수동 판단 테스트
python -m src.tests.test_hardware_integration --manual-judge --zone 1 --delta -365

# 실시간 모니터링 + 자동 판단 (60초)
python -m src.tests.test_hardware_integration --realtime-monitor --duration 60

# 정확도 테스트 (10회 반복)
python -m src.tests.test_hardware_integration --accuracy-test --zone 1 --repeat 10

# 특정 상품 정확도 테스트
python -m src.tests.test_hardware_integration \
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
curl http://localhost:8002/api/health    # Model
curl http://localhost:8001/health        # IO Board
curl http://localhost:8003/api/health    # Camera Driver
curl http://localhost:8889/health        # Node.js Orchestrator
curl http://localhost:8006/health        # MQTT Client
```

### 상품 판단 (POST /api/judge) - 권장 형식
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
      "image_folder": "/data/snapshots/test",
      "top_image": "/data/snapshots/test/cam_0/snapshot.jpg",
      "side_image": "/data/snapshots/test/cam_1/snapshot.jpg"
    }
  }'
```

### 상품 판단 (레거시 형식 - 하위 호환)
```bash
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 1, "delta_weight": -365.0}'
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
