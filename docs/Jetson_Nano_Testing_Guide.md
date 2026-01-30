# Jetson Orin Nano 테스트 가이드

> **최종 업데이트**: 2026-01-30

Camera Driver + Model 서비스를 Jetson Orin Nano에서 테스트하는 방법을 설명합니다.

> **대상 환경**: Jetson Orin Nano, JetPack 6.2, Ubuntu 22.04
> **관리 서비스**: Camera Driver (8003), Model (8002), React Client (3000)

---

## 서비스 구성

이 레포에서 관리하는 서비스:

| 서비스 | 포트 | 설명 |
|--------|------|------|
| camera-driver | 8003 | 카메라 관리 |
| model | 8002 | AI 상품 판단 |
| client | 3000 | React 대시보드 |

다른 레포에서 관리하는 서비스:

| 서비스 | 포트 | 레포 |
|--------|------|------|
| orchestrator | 8888 | Edge_Environment |
| io-board | 8000 | CRK-IO-BOARD |
| card-terminal | 5000 | CRK-PAYMENT |
| mqtt-client | 8006 | Edge_Environment |

---

## 1. 사전 준비

### 1.1 JetPack 환경 확인

```bash
# JetPack 버전 확인
cat /etc/nv_tegra_release

# NVIDIA GPU 확인
nvidia-smi
```

### 1.2 Node.js 설치

```bash
# Node.js 20.x LTS 설치
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# PM2 전역 설치
sudo npm install -g pm2
```

### 1.3 Python 환경 설정

```bash
# uv 설치 (권장)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

# 프로젝트 폴더로 이동
cd ~/Edge_Environment

# 의존성 설치
uv sync --extra ai
```

### 1.4 사용자 권한 설정

```bash
# 비디오 장치 접근 권한
sudo usermod -aG video $USER

# 로그아웃 후 재로그인
```

### 1.5 카메라 확인

```bash
# USB 카메라 확인
v4l2-ctl --list-devices

# 개별 카메라 정보
v4l2-ctl -d /dev/video0 --all
```

---

## 2. 프로젝트 설정

### 2.1 환경 변수

```bash
# .env 파일 생성
cp .env.example .env
nano .env
```

**.env 파일 (Jetson):**

```env
# Camera
CAMERA__NVIDIA_MODE=true
CAMERA__RESOLUTION_WIDTH=640
CAMERA__RESOLUTION_HEIGHT=480
CAMERA__FPS=30

# Model
MODEL__VISION__YOLO_MODEL_PATH=./models/siyeon_best.engine

# 연동 URL (다른 레포)
CAMERA__IO_BOARD_URL=http://localhost:8000
CAMERA__NODEJS_CALLBACK_URL=http://localhost:8888
MODEL__NODEJS_URL=http://localhost:8888

# Log Level
LOG_LEVEL=INFO
```

### 2.2 모델 파일 준비

```bash
mkdir -p models
# TensorRT 엔진 파일 또는 PyTorch 모델 복사
cp /path/to/siyeon_best.engine ./models/
```

---

## 3. 서비스 실행

### 3.1 PM2 통합 실행

```bash
# Camera + Model 서비스 시작
npm run services

# Client도 함께 시작
npm run all

# 상태 확인
pm2 status
pm2 logs
```

### 3.2 개별 실행 (디버깅용)

```bash
# 터미널 1: Camera Driver
cd services/camera_driver
CAMERA__NVIDIA_MODE=true python main.py

# 터미널 2: Model
cd services/model
python main.py
```

### 3.3 헬스 체크

```bash
curl http://localhost:8003/api/health  # Camera
curl http://localhost:8002/api/health  # Model
```

---

## 4. 테스트

### 4.1 Camera Driver 테스트

```bash
# 카메라 상태
curl http://localhost:8003/api/status

# 디바이스 스캔
curl http://localhost:8003/api/devices/scan

# Zone 0 스냅샷
curl -X POST http://localhost:8003/api/zone/0/snapshot \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test123", "include_top": true}'
```

### 4.2 Model 테스트

```bash
# 상품 목록
curl http://localhost:8002/api/products

# Vision-only 판단
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 0,
    "vision_only": true,
    "media_paths": {"image_folder": "data/test_images"}
  }'

# 무게 포함 판단
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 0,
    "weight_data": {"delta_weight": -520, "channels": [0, 1]},
    "media_paths": {"image_folder": "data/test_images"}
  }'
```

### 4.3 Pytest 실행

```bash
pytest services/model/tests/ -v
pytest services/camera_driver/tests/ -v
```

---

## 5. 다른 레포 연동

다른 레포의 서비스와 함께 테스트:

```bash
# 다른 레포 서비스 확인
curl http://localhost:8888/health  # Node.js
curl http://localhost:8000/health  # IO Board

# Node.js 경유 판단
curl -X POST http://localhost:8888/api/model/judge \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 0, "delta_weight": -520}'
```

---

## 6. 트러블슈팅

### 카메라 인식 실패

```bash
# 카메라 장치 목록
v4l2-ctl --list-devices

# 권한 문제 해결
sudo chmod 666 /dev/video*
```

### GPU 메모리 부족

```bash
# GPU 상태 확인
nvidia-smi

# PM2 서비스 재시작
pm2 restart all
```

### PM2 서비스 오류

```bash
pm2 logs model --lines 200
pm2 restart model
```

---

## 빠른 참조

| 작업 | 명령어 |
|------|--------|
| 서비스 시작 | `npm run services` |
| 전체 시작 | `npm run all` |
| 중지 | `npm run services:stop` |
| 상태 확인 | `pm2 status` |
| 로그 확인 | `pm2 logs` |
| GPU 확인 | `nvidia-smi` |
| 카메라 확인 | `v4l2-ctl --list-devices` |

---

## JetPack 6.2 특이사항

1. **L4T 버전**: R36.2.0 (CUDA 12.2)
2. **기본 Python**: Python 3.10
3. **TensorRT**: FP16/INT8 엔진 지원

```bash
# 최대 성능 모드 설정
sudo nvpmodel -m 0
sudo jetson_clocks
```

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
GET  /api/health              # 헬스 체크
GET  /api/products            # 상품 목록
POST /api/judge               # 상품 판단
POST /api/judge/cancel        # 추론 취소
```
