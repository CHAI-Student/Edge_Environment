# Windows 테스트 환경 가이드

## 개요

이 문서는 Jetson Nano 배포 전 Windows 환경에서 테스트하는 방법을 설명합니다.

## 테스트 전략

### Docker vs 직접 실행

| 방식 | 장점 | 단점 | 권장 상황 |
|------|------|------|----------|
| **직접 실행** | 카메라 접근 용이, 디버깅 편리 | 환경 차이 | Windows 개발/테스트 |
| **Docker** | 환경 일관성 | USB 카메라 접근 어려움, ARM/x86 차이 | Jetson 배포 |

**권장**: Windows에서는 직접 실행 + 폴더 모드 사용

---

## 1. Windows 직접 실행 환경 구성

### 1.1 Python 환경 설정

```powershell
# Python 3.9+ 설치 확인
python --version

# 가상환경 생성
python -m venv venv
.\venv\Scripts\Activate.ps1

# 의존성 설치
pip install -r requirements.txt
```

### 1.2 필수 패키지

```txt
# requirements.txt
fastapi>=0.100.0
uvicorn>=0.22.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
opencv-python>=4.8.0
numpy>=1.24.0
httpx>=0.24.0
aiohttp>=3.8.0
pytest>=7.0.0
pytest-asyncio>=0.21.0
```

---

## 2. 테스트 모드 설명

### 2.1 API 모드 (카메라 연결 필요)

실제 USB 카메라가 연결된 상태에서 테스트:

```bash
# Camera Driver 시작 (포트 8003)
cd Edge_Environment/services/camera_driver
uvicorn main:app --host 0.0.0.0 --port 8003 --reload

# Model 서비스 시작 (포트 8002)
cd Edge_Environment/services/model
uvicorn main:app --host 0.0.0.0 --port 8002 --reload
```

### 2.2 폴더 모드 (카메라 없이 테스트)

미리 저장된 이미지로 테스트:

```python
# services/model/camera/camera_client.py
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

## 3. 녹화 테스트

### 3.1 녹화 API 사용

```bash
# 녹화 시작 (Zone 0, 영상 포함)
curl -X POST "http://localhost:8003/api/recording/start?zone_id=0&record_video=true"

# 응답 예시:
# {
#   "success": true,
#   "session_id": "20251106_141029",
#   "paths": {
#     "base_path": "./recordings/20251106_141029",
#     "images_path": "./recordings/20251106_141029/images",
#     "videos_path": "./recordings/20251106_141029/videos"
#   }
# }

# 스냅샷 캡처
curl -X POST "http://localhost:8003/api/recording/snapshot?zone_id=0"

# 녹화 중지
curl -X POST "http://localhost:8003/api/recording/stop"
```

### 3.2 저장 폴더 구조

```
recordings/
└── 20251106_141029/           # 세션 ID (타임스탬프)
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

### 3.3 카메라 번호 체계

| Camera ID | 역할 | 설명 |
|-----------|------|------|
| 0 | Top | 손 감지, 전체 Zone 커버 |
| 1 | Side Zone 0 | Zone 0 전용 |
| 2 | Side Zone 1 | Zone 1 전용 |
| 3 | Side Zone 2 | Zone 2 전용 |
| 4 | Side Zone 3 | Zone 3 전용 |
| 5 | Side Zone 4 | Zone 4 전용 |

---

## 4. 서비스별 테스트

### 4.1 IO Board 서비스 (포트 8001)

**하드웨어 없이 테스트:**

```bash
cd Edge_Environment/services/io_board
python -m main --test  # 테스트 모드 (시뮬레이션)
```

### 4.2 Model 서비스 (포트 8002)

```bash
cd Edge_Environment/services/model
uvicorn main:app --host 0.0.0.0 --port 8002

# 헬스 체크
curl http://localhost:8002/api/health

# 상품 목록 조회
curl http://localhost:8002/api/products
```

### 4.3 Camera Driver (포트 8003)

```bash
cd Edge_Environment/services/camera_driver
uvicorn main:app --host 0.0.0.0 --port 8003

# 상태 조회
curl http://localhost:8003/api/status

# 프레임 캡처 (카메라 연결 필요)
curl http://localhost:8003/api/frame/0 --output frame.jpg
```

---

## 5. 통합 테스트

### 5.1 전체 플로우 테스트

```bash
# 1. 서비스 시작 (각각 다른 터미널)
uvicorn main:app --port 8001  # io_board
uvicorn main:app --port 8002  # model
uvicorn main:app --port 8003  # camera_driver

# 2. 헬스 체크
curl http://localhost:8001/health
curl http://localhost:8002/api/health
curl http://localhost:8003/api/health
```

### 5.2 Pytest 실행

```bash
# 전체 테스트
cd Edge_Environment
pytest services/model/tests/ -v
pytest services/camera_driver/tests/ -v

# 특정 테스트
pytest services/model/tests/test_error_recovery.py -v

# 커버리지
pytest --cov=services --cov-report=html
```

---

## 6. Docker 배포 (Jetson용)

### 6.1 Dockerfile 예시

```dockerfile
# Jetson Nano용 (ARM64)
FROM nvcr.io/nvidia/l4t-pytorch:r32.7.1-pth1.10-py3

WORKDIR /app
COPY . .
RUN pip install -r requirements.txt

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
```

### 6.2 docker-compose.yml

```yaml
version: '3.8'
services:
  model:
    build: ./services/model
    ports:
      - "8002:8002"
    environment:
      - CAMERA_MODE=api
      - IO_BOARD_URL=http://io_board:8001
    depends_on:
      - io_board
      - camera_driver

  camera_driver:
    build: ./services/camera_driver
    ports:
      - "8003:8003"
    devices:
      - /dev/video0:/dev/video0  # Linux only
    privileged: true

  io_board:
    build: ./services/io_board
    ports:
      - "8001:8001"
    devices:
      - /dev/ttyUSB0:/dev/ttyUSB0
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

---

## 8. 테스트 체크리스트

- [ ] Python 환경 설정 완료
- [ ] 의존성 설치 완료
- [ ] IO Board 서비스 테스트 모드 실행
- [ ] Model 서비스 실행 및 헬스 체크
- [ ] Camera Driver 실행 (폴더 모드 또는 실제 카메라)
- [ ] 녹화 API 테스트
- [ ] Pytest 테스트 통과
- [ ] 통합 테스트 완료
