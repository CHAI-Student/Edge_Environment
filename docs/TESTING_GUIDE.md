# Windows 테스트 환경 가이드

> **최종 업데이트**: 2026-01-29

## 개요

이 문서는 Jetson Orin Nano 배포 전 Windows 환경에서 테스트하는 방법을 설명합니다.

## 테스트 전략

### 직접 실행 vs PM2

| 방식 | 장점 | 단점 | 권장 상황 |
|------|------|------|----------|
| **PM2 통합** | 서비스 관리 편리, 자동 재시작 | PM2 설치 필요 | Windows/Jetson 모두 |
| **직접 실행** | 디버깅 편리, 환경 변수 유연 | 터미널 여러 개 필요 | 개발/디버깅 |

**권장**: PM2 통합 실행 + 필요 시 개별 서비스 디버깅

### PM2 통합 실행 (권장)

```bash
# 전체 서비스 시작
npm start

# 또는 개별 실행
pm2 start ecosystem.config.js --only model
pm2 start ecosystem.config.js --only "io-board,camera-driver"

# 상태 확인
pm2 status
pm2 logs
```

---

## 1. uv를 사용한 환경 구성 (권장)

### 1.1 uv 설치

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 또는 pip로 설치
pip install uv

# 설치 확인
uv --version
```

### 1.2 Python + 가상환경 한번에 설정

```powershell
# Edge_Environment 폴더로 이동
cd C:\Users\user\Desktop\VOICE\2026\crk\win_pc_test_sw2io_board\Edge_Environment

# Python 3.11 + 가상환경 생성 + 의존성 설치 (한번에!)
uv sync

# 가상환경 활성화
.venv\Scripts\Activate.ps1
```

### 1.3 선택적 의존성 설치

```powershell
# 테스트 도구 포함
uv sync --extra test

# AI/Vision 포함 (GPU 사용 시)
uv sync --extra ai

# MQTT 포함
uv sync --extra mqtt

# 전체 개발 환경
uv sync --extra ai --extra mqtt --extra dev
```

### 1.4 uv 주요 명령어

```powershell
# 패키지 추가
uv add <package>

# 패키지 제거
uv remove <package>

# 의존성 업데이트
uv lock --upgrade

# 특정 Python 버전으로 실행
uv run --python 3.11 python script.py
```

---

## 2. 기존 pip 방식 (대안)

### 2.1 Python 환경 설정

```powershell
# Python 3.10+ 설치 확인
python --version

# 가상환경 생성
python -m venv venv
.\venv\Scripts\Activate.ps1

# pyproject.toml 기반 설치
pip install -e ".[ai,mqtt,dev]"
```

---

## 3. 테스트 모드 설명

### 3.1 API 모드 (카메라 연결 필요)

실제 USB 카메라가 연결된 상태에서 테스트:

```bash
# Camera Driver 시작 (포트 8003)
cd Edge_Environment/services/camera_driver
python main.py

# Model 서비스 시작 (포트 8002)
cd Edge_Environment/services/model
python main.py
```

### 3.2 폴더 모드 (카메라 없이 테스트)

미리 저장된 이미지로 테스트:

```python
# services/model/src/camera/camera_client.py
from .frame_capturer import FolderFrameLoader

# 폴더 구조
# test_images/
# ├── cam_0/  (Top camera)
# ├── cam_1/  (Zone 0)
# └── ...

loader = FolderFrameLoader(base_path="./test_images")
frame = loader.get_frame(camera_id=0)
```

---

## 4. 녹화 테스트

### 4.1 녹화 API 사용

```bash
# 녹화 시작 (Zone 0, 영상 포함)
curl -X POST "http://localhost:8003/api/recording/start?zone_id=0&record_video=true"

# 응답 예시:
# {
#   "success": true,
#   "session_id": "20260129_141029",
#   "paths": {
#     "base_path": "./recordings/20260129_141029",
#     "images_path": "./recordings/20260129_141029/images",
#     "videos_path": "./recordings/20260129_141029/videos"
#   }
# }

# 스냅샷 캡처
curl -X POST "http://localhost:8003/api/recording/snapshot?zone_id=0"

# 녹화 중지
curl -X POST "http://localhost:8003/api/recording/stop"
```

### 4.2 저장 폴더 구조

```
recordings/
└── 20260129_141029/           # 세션 ID (타임스탬프)
    ├── images/
    │   ├── cam_0/             # Top camera
    │   │   ├── frame_0001.jpg
    │   │   ├── frame_0002.jpg
    │   │   └── ...
    │   ├── cam_1/             # Side Zone 0
    │   └── cam_5/             # Side Zone 4
    └── videos/
        ├── cam_0.mp4          # Top camera 영상
        ├── cam_1.mp4
        └── cam_5.mp4
```

### 4.3 카메라 번호 체계

| Camera ID | 역할 | 설명 |
|-----------|------|------|
| 0 | Top | 손 감지, 전체 Zone 커버 |
| 1 | Side Zone 0 | Zone 0 전용 |
| 2 | Side Zone 1 | Zone 1 전용 |
| 3 | Side Zone 2 | Zone 2 전용 |
| 4 | Side Zone 3 | Zone 3 전용 |
| 5 | Side Zone 4 | Zone 4 전용 |

---

## 5. 서비스별 테스트

### 5.1 IO Board 서비스 (포트 8000)

**하드웨어 없이 테스트 불가** - 시리얼 연결 필요

```bash
# Windows에서 COM 포트로 실행
cd Edge_Environment/services/io_board
set IO_BOARD__SERIAL__PORT=COM3
python main.py

# 헬스 체크
curl http://localhost:8000/health

# 로드셀 무게 조회
curl http://localhost:8000/loadcells

# 도어/데드볼트 상태
curl http://localhost:8000/status
```

### 5.2 Model 서비스 (포트 8002)

```bash
cd Edge_Environment/services/model
python main.py

# 헬스 체크
curl http://localhost:8002/api/health

# Zone 설정 조회
curl http://localhost:8002/api/zones/config

# 상품 목록 조회
curl http://localhost:8002/api/products

# 상품 판단 테스트 (Vision-only)
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 0, "vision_only": true, "media_paths": {"image_folder": "./test_images"}}'
```

### 5.3 Camera Driver (포트 8003)

```bash
cd Edge_Environment/services/camera_driver
python main.py

# 상태 조회
curl http://localhost:8003/api/status

# 디바이스 스캔
curl http://localhost:8003/api/devices/scan

# Zone 활성화
curl -X POST http://localhost:8003/api/zone/0/activate

# 스냅샷 (카메라 연결 필요)
curl -X POST http://localhost:8003/api/zone/0/snapshot \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test123", "include_top": true}'
```

### 5.4 Card Terminal (포트 5000)

```bash
cd Edge_Environment/services/card_terminal
python main.py

# 헬스 체크
curl http://localhost:5000/status

# SSE 이벤트 스트림
curl -N http://localhost:5000/sse
```

### 5.5 Node.js 서버 (포트 8889)

```bash
cd Edge_Environment
npm run start:server   # 서버만 실행
npm run dev            # 서버 + React 동시 실행

# 헬스 체크
curl http://localhost:8889/health

# 통합 상태 조회
curl http://localhost:8889/api/dashboard/status
```

---

## 6. 통합 테스트

### 6.1 전체 플로우 테스트

```bash
# PM2로 전체 서비스 시작
npm start

# 또는 각각 다른 터미널에서 개별 실행
# 터미널 1: python services/io_board/main.py
# 터미널 2: python services/model/main.py
# 터미널 3: python services/camera_driver/main.py
# 터미널 4: node server/index.js

# 헬스 체크
curl http://localhost:8000/health      # io_board
curl http://localhost:8002/api/health  # model
curl http://localhost:8003/api/health  # camera_driver
curl http://localhost:8889/health      # node.js
```

### 6.2 Pytest 실행

```powershell
cd C:\Users\user\Desktop\VOICE\2026\crk\win_pc_test_sw2io_board\Edge_Environment

# uv 사용 (권장) - 가상환경 자동 감지
uv run pytest services/model/src/tests/ -v
uv run pytest services/camera_driver/src/tests/ -v

# 또는 가상환경 활성화 후 직접 실행
.venv\Scripts\Activate.ps1
pytest services/model/src/tests/ -v
pytest services/camera_driver/src/tests/ -v

# 특정 테스트
uv run pytest services/model/src/tests/test_error_recovery.py -v

# 커버리지
uv run pytest --cov=services --cov-report=html
```

---

## 7. 문제 해결

### 7.1 카메라 연결 안됨

```bash
# Windows: 디바이스 관리자에서 카메라 확인
# 또는 Python으로 확인
python -c "import cv2; print([cv2.VideoCapture(i).isOpened() for i in range(6)])"
```

### 7.2 OpenCV 설치 문제

```bash
# GPU 버전 대신 CPU 버전 사용
pip uninstall opencv-python opencv-python-headless
pip install opencv-python-headless
```

### 7.3 포트 충돌

```powershell
# 사용 중인 포트 확인
netstat -ano | findstr :8002

# 프로세스 종료
taskkill /PID <PID> /F
```

### 7.4 PM2 설치

```bash
# Node.js 설치 후
npm install -g pm2

# Windows에서 PM2 자동 시작 (관리자 권한)
npm install -g pm2-windows-startup
pm2-startup install
pm2 save
```

---

## 8. 테스트 체크리스트

- [ ] Python 환경 설정 완료 (uv sync 또는 pip install)
- [ ] Node.js 및 PM2 설치 완료
- [ ] 의존성 설치 완료
- [ ] IO Board 서비스 테스트 (시리얼 연결 시)
- [ ] Model 서비스 실행 및 헬스 체크
- [ ] Camera Driver 실행 (폴더 모드 또는 실제 카메라)
- [ ] Card Terminal 헬스 체크
- [ ] Node.js 서버 헬스 체크
- [ ] Pytest 테스트 통과
- [ ] 통합 테스트 완료

---

## API 엔드포인트 요약

### IO Board (8000)
```
GET  /health      # 헬스 체크
GET  /loadcells   # 로드셀 무게
GET  /status      # door + deadbolt 상태
POST /deadbolt    # 데드볼트 제어
POST /init        # 초기화
POST /calibrate   # 센서 보정
GET  /sse         # SSE 스트림
```

### Model (8002)
```
GET  /api/health         # 헬스 체크
GET  /api/products       # 상품 목록
GET  /api/zones/config   # Zone 설정
POST /api/judge          # 상품 판단
```

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

### Card Terminal (5000)
```
GET  /status                       # 헬스 체크
GET  /sse                          # SSE 이벤트 스트림
POST /payment/token/approve        # 토큰 결제 승인
POST /payment/samsung-pay/approve  # 삼성페이 승인
```

### Node.js (8889)
```
GET  /health                  # 헬스 체크
GET  /api/dashboard/status    # 통합 상태
GET  /sse/events              # 통합 SSE 스트림
POST /api/model/judge         # 판단 프록시
```
