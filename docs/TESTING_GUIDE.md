# Windows 테스트 환경 가이드

> **최종 업데이트**: 2026-01-30

## 개요

이 레포의 **Camera Driver**와 **Model** 서비스를 Windows에서 테스트하는 방법입니다.

> **참고**: Node.js, IO Board, Payment 서비스는 다른 레포에서 관리됩니다.

## 서비스 구성

| 서비스 | 포트 | 관리 레포 |
|--------|------|-----------|
| Camera Driver | 8003 | **이 레포** |
| Model | 8002 | **이 레포** |
| React Client | 3000 | **이 레포** |
| Node.js | 8888 | Edge_Environment |
| IO Board | 8000 | CRK-IO-BOARD |
| Payment | 5000 | CRK-PAYMENT |

---

## 1. 환경 구성

### 1.1 uv 사용 (권장)

```powershell
# uv 설치
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 프로젝트 폴더로 이동
cd Edge_Environment

# Python + 의존성 설치
uv sync --extra ai

# 가상환경 활성화
.venv\Scripts\Activate.ps1
```

### 1.2 pip 사용 (대안)

```powershell
# 가상환경 생성
python -m venv venv
.\venv\Scripts\Activate.ps1

# 의존성 설치
pip install -e ".[ai,dev]"
```

### 1.3 Node.js (PM2용)

```bash
npm install
npm install -g pm2
```

---

## 2. 서비스 실행

### 2.1 PM2 통합 실행 (권장)

```bash
# Camera + Model 서비스 시작
npm run services

# Client도 함께 시작
npm run all

# 상태 확인
pm2 status
pm2 logs
```

### 2.2 개별 실행 (디버깅용)

```bash
# Camera Driver
cd services/camera_driver
python main.py

# Model Service
cd services/model
python main.py
```

---

## 3. 테스트

### 3.1 헬스 체크

```bash
curl http://localhost:8003/api/health  # Camera
curl http://localhost:8002/api/health  # Model
```

### 3.2 Camera Driver 테스트

```bash
# 카메라 상태
curl http://localhost:8003/api/status

# 디바이스 스캔
curl http://localhost:8003/api/devices/scan

# Zone 활성화
curl -X POST http://localhost:8003/api/zone/0/activate

# 스냅샷
curl -X POST http://localhost:8003/api/zone/0/snapshot \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test123", "include_top": true}'
```

### 3.3 Model 테스트

```bash
# 상품 목록
curl http://localhost:8002/api/products

# Vision-only 판단
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 0,
    "vision_only": true,
    "media_paths": {"image_folder": "./test_images"}
  }'

# 무게 포함 판단
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 0,
    "weight_data": {"delta_weight": -520, "channels": [0, 1]},
    "media_paths": {"image_folder": "./test_images"}
  }'
```

### 3.4 Pytest 실행

```bash
# Model 테스트
pytest services/model/tests/ -v

# Camera Driver 테스트
pytest services/camera_driver/tests/ -v

# 커버리지
pytest --cov=services --cov-report=html
```

---

## 4. 녹화 테스트

```bash
# 녹화 시작
curl -X POST "http://localhost:8003/api/recording/start?zone_id=0"

# 스냅샷 캡처
curl -X POST "http://localhost:8003/api/recording/snapshot?zone_id=0"

# 녹화 중지
curl -X POST "http://localhost:8003/api/recording/stop"
```

### 저장 구조

```
recordings/
└── 20260130_141029/
    ├── images/
    │   ├── cam_0/frame_*.jpg
    │   └── cam_1/frame_*.jpg
    └── videos/
        ├── cam_0.mp4
        └── cam_1.mp4
```

---

## 5. 다른 레포 연동 테스트

다른 레포의 서비스와 함께 테스트할 때:

```bash
# 다른 레포 서비스 확인
curl http://localhost:8888/health  # Node.js (Edge_Environment)
curl http://localhost:8000/health  # IO Board (CRK-IO-BOARD)

# Node.js 경유 판단 요청
curl -X POST http://localhost:8888/api/model/judge \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 0, "delta_weight": -520}'
```

---

## 6. 문제 해결

### 카메라 연결 안됨

```bash
# 카메라 디바이스 확인
python -c "import cv2; print([cv2.VideoCapture(i).isOpened() for i in range(6)])"

# 디바이스 스캔
curl http://localhost:8003/api/devices/scan
```

### 포트 충돌

```powershell
# 포트 확인
netstat -ano | findstr :8002

# 프로세스 종료
taskkill /PID <PID> /F
```

### PM2 로그 확인

```bash
pm2 logs model --lines 50
pm2 logs camera-driver --lines 50
```

---

## 7. 테스트 체크리스트

- [ ] Python 환경 설정 완료
- [ ] Node.js + PM2 설치 완료
- [ ] Camera Driver 헬스 체크 통과
- [ ] Model 서비스 헬스 체크 통과
- [ ] 스냅샷 캡처 테스트 완료
- [ ] 상품 판단 테스트 완료
- [ ] Pytest 테스트 통과

---

## API 요약

### Camera Driver (8003)

```
GET  /api/health              # 헬스 체크
GET  /api/status              # 카메라 상태
GET  /api/devices/scan        # 디바이스 스캔
POST /api/zone/{id}/activate  # Zone 활성화
POST /api/zone/{id}/snapshot  # 스냅샷 캡처
POST /api/recording/start     # 녹화 시작
POST /api/recording/stop      # 녹화 중지
```

### Model (8002)

```
GET  /api/health         # 헬스 체크
GET  /api/products       # 상품 목록
POST /api/judge          # 상품 판단
POST /api/judge/cancel   # 추론 취소
```
