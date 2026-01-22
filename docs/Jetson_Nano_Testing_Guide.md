# Jetson Orin Nano 테스트 가이드

AI Smart Vending Machine 시스템을 Jetson Orin Nano에서 Docker로 테스트하는 방법을 설명합니다.

> **대상 환경**: Jetson Orin Nano, JetPack 6.2, Ubuntu 22.04
> **작업 방식**: Jetson 장치에서 직접 실행 (SSH 원격 접속 아님)

---

## 목차

1. [사전 준비](#1-사전-준비)
2. [프로젝트 클론 및 설정](#2-프로젝트-클론-및-설정)
3. [Docker 배포 테스트](#3-docker-배포-테스트)
4. [터미널 개별 서비스 테스트](#4-터미널-개별-서비스-테스트)
5. [전체 시스템 통합 테스트](#5-전체-시스템-통합-테스트)
6. [트러블슈팅](#6-트러블슈팅)

---

## 1. 사전 준비

### 1.1 JetPack 6.2 환경 확인

Jetson Orin Nano의 터미널을 열고 다음 명령어를 실행합니다.

```bash
# JetPack 버전 확인
cat /etc/nv_tegra_release
# 예상 출력: # R36 (release), REVISION: 2.0, ...

# Ubuntu 버전 확인
lsb_release -a
# 예상 출력: Ubuntu 22.04.x LTS

# Docker 설치 확인
docker --version
# 예상 출력: Docker version 24.x.x

docker compose version
# 예상 출력: Docker Compose version v2.x.x

# NVIDIA Container Toolkit 확인
nvidia-smi
# GPU 정보가 표시되어야 함

# Docker에서 GPU 테스트
docker run --rm --runtime=nvidia --gpus all nvcr.io/nvidia/l4t-base:r36.2.0 nvidia-smi
```

### 1.2 Docker 및 NVIDIA Container Toolkit 설치 (미설치 시)

```bash
# Docker 설치
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin

# NVIDIA Container Toolkit (JetPack 6.2에 기본 포함)
sudo apt-get install -y nvidia-container-toolkit

# Docker 데몬 재시작
sudo systemctl restart docker
```

### 1.3 사용자 권한 설정

```bash
# Docker 그룹 추가
sudo usermod -aG docker $USER

# 시리얼 포트 접근 권한 (dialout 그룹)
sudo usermod -aG dialout $USER

# 비디오 장치 접근 권한 (video 그룹)
sudo usermod -aG video $USER

# 변경 적용 (로그아웃 후 재로그인)
# GUI: 로그아웃 → 로그인
# 터미널: 새 터미널 열기

# 권한 확인
groups
# 출력에 docker, dialout, video가 포함되어야 함
```

### 1.4 하드웨어 연결 확인

```bash
# 시리얼 포트 확인 (IO Board)
# JetPack 6.2에서는 주로 /dev/ttyTHS0 또는 /dev/ttyUSB0
ls -la /dev/ttyTHS* /dev/ttyUSB* 2>/dev/null

# USB 카메라 확인
ls -la /dev/video*
v4l2-ctl --list-devices

# 개별 카메라 정보 확인
v4l2-ctl -d /dev/video0 --all
```

---

## 2. 프로젝트 클론 및 설정

### 2.1 GitHub에서 프로젝트 클론

```bash
# 작업 디렉토리 생성
mkdir -p ~/ai-vending
cd ~/ai-vending

# Git 설치 확인
git --version

# 프로젝트 클론
git clone https://github.com/CHAI-Student/Edge_Environment.git
cd Edge_Environment

# 브랜치 확인 및 전환 (필요시)
git branch -a
git checkout main  # 또는 원하는 브랜치
```

### 2.2 환경 변수 설정

```bash
# .env 파일 생성 (예제 파일 복사)
cp .env.example .env

# .env 파일 편집
nano .env
```

**.env 파일 내용 예시:**

```env
# IO Board
IO_BOARD_PORT=/dev/ttyTHS0
IO_BOARD_BAUDRATE=38400

# Camera
CAMERA_MODE=hardware

# Model
YOLO_MODEL_PATH=/app/models/siyeon_best.pt

# MQTT
MQTT_BROKER_HOST=192.168.1.10
MQTT_BROKER_PORT=1883

# MongoDB (선택)
MONGO_URI=mongodb://localhost:27017/chai

# MinIO (선택)
MINIO_ENDPOINT=localhost
MINIO_PORT=9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# Log Level
LOG_LEVEL=INFO
```

### 2.3 모델 파일 준비

```bash
# 모델 디렉토리 생성
mkdir -p models

# YOLO 모델 파일 복사 (USB 또는 네트워크에서)
# 예: USB 드라이브에서 복사
cp /media/$USER/USB_DRIVE/siyeon_best.pt models/

# 모델 파일 확인
ls -la models/
```

---

## 3. Docker 배포 테스트

### 3.1 이미지 빌드

```bash
cd ~/ai-vending/Edge_Environment

# 전체 빌드 (Jetson GPU 설정 포함)
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml build

# 빌드 진행 상황 확인 (시간이 걸림)
# model 서비스는 GPU 이미지 기반이라 오래 걸릴 수 있음

# 개별 서비스 빌드 (필요시)
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml build io_board
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml build model
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml build camera_driver
```

### 3.2 서비스 시작

```bash
# 전체 서비스 시작 (백그라운드)
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml up -d

# 시작 로그 확인
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml logs

# 실시간 로그 모니터링
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml logs -f

# 특정 서비스 로그만 확인
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml logs -f model
```

### 3.3 상태 확인

```bash
# 컨테이너 상태 확인
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml ps

# 헬스 체크 (각 서비스)
curl http://localhost:8001/health      # io_board
curl http://localhost:8002/api/health  # model
curl http://localhost:8003/api/health  # camera_driver
curl http://localhost:8004/status      # card_terminal
curl http://localhost:8006/health      # mqtt_client
curl http://localhost:8888/health      # node_server

# 전체 헬스 체크 스크립트
for port in 8001 8002 8003 8004 8006 8888; do
  echo -n "Port $port: "
  curl -s http://localhost:$port/health 2>/dev/null || curl -s http://localhost:$port/api/health 2>/dev/null || echo "FAILED"
done

# GPU 사용량 모니터링
nvidia-smi
watch -n 1 nvidia-smi  # 1초마다 갱신
```

### 3.4 서비스 제어

```bash
# 전체 재시작
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml restart

# 특정 서비스만 재시작
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml restart model

# 전체 중지
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml down

# 중지 + 볼륨 삭제
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml down -v

# 이미지까지 삭제 (재빌드 필요)
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml down --rmi all
```

---

## 4. 터미널 개별 서비스 테스트

Docker 없이 직접 서비스를 실행하여 디버깅합니다.

### 4.1 Python 환경 설정

```bash
cd ~/ai-vending/Edge_Environment

# Python 버전 확인 (3.10 이상 필요)
python3 --version

# 가상환경 생성
python3 -m venv .venv
source .venv/bin/activate

# pip 업그레이드
pip install --upgrade pip

# 의존성 설치
pip install -e ".[ai,mqtt]"

# PyTorch/CUDA 확인 (JetPack 6.2용)
python3 -c "import torch; print(f'PyTorch: {torch.__version__}, CUDA: {torch.cuda.is_available()}')"
```

### 4.2 IO Board 서비스 테스트

**터미널 1:**
```bash
source .venv/bin/activate
cd ~/ai-vending/Edge_Environment
IO_BOARD_PORT=/dev/ttyTHS0 uvicorn services.io_board.main:app --host 0.0.0.0 --port 8001
```

**터미널 2 (새 터미널 열기):**
```bash
# 헬스 체크
curl http://localhost:8001/health

# 로드셀 무게 조회
curl http://localhost:8001/api/loadcell/weights

# 도어 상태 조회
curl http://localhost:8001/api/door/status

# SSE 스트림 테스트
curl -N http://localhost:8001/sse
```

### 4.3 Camera Driver 서비스 테스트

**터미널 1:**
```bash
source .venv/bin/activate
cd ~/ai-vending/Edge_Environment
CAMERA_MODE=hardware uvicorn services.camera_driver.main:app --host 0.0.0.0 --port 8003
```

**터미널 2:**
```bash
# 헬스 체크
curl http://localhost:8003/api/health

# 카메라 목록
curl http://localhost:8003/api/cameras

# 프레임 캡처 테스트
curl http://localhost:8003/api/cameras/0/capture --output test_cam0.jpg
ls -la test_cam0.jpg

# 이미지 확인 (GUI 환경)
eog test_cam0.jpg
```

### 4.4 Model 서비스 테스트

**터미널 1:**
```bash
source .venv/bin/activate
cd ~/ai-vending/Edge_Environment
YOLO_MODEL_PATH=~/ai-vending/Edge_Environment/models/siyeon_best.pt \
IO_BOARD_URL=http://localhost:8001 \
CAMERA_DRIVER_URL=http://localhost:8003 \
uvicorn services.model.main:app --host 0.0.0.0 --port 8002
```

**터미널 2:**
```bash
# 헬스 체크
curl http://localhost:8002/api/health

# 상품 목록 조회
curl http://localhost:8002/api/products

# 상품 판단 테스트
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 0}'

# 무게 변화 포함 판단
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 0, "weight_delta": -350}'
```

### 4.5 Node.js 서버 테스트

```bash
cd ~/ai-vending/Edge_Environment

# Node.js 설치 확인
node --version  # v18 이상 권장

# 의존성 설치
npm install

# 서버 실행
NODE_ENV=production node server/index.js
```

**다른 터미널에서:**
```bash
curl http://localhost:8888/health
```

---

## 5. 전체 시스템 통합 테스트

### 5.1 서비스 연동 테스트

```bash
# 모든 서비스 상태 확인
echo "=== Service Health Check ==="
curl -s http://localhost:8001/health && echo " - io_board OK"
curl -s http://localhost:8002/api/health && echo " - model OK"
curl -s http://localhost:8003/api/health && echo " - camera_driver OK"
curl -s http://localhost:8006/health && echo " - mqtt_client OK"
curl -s http://localhost:8888/health && echo " - node_server OK"

# 초기 무게 확인
echo "=== Initial Weights ==="
curl -s http://localhost:8001/api/loadcell/weights | python3 -m json.tool

# 카메라 상태 확인
echo "=== Camera Status ==="
curl -s http://localhost:8003/api/cameras | python3 -m json.tool
```

### 5.2 상품 픽업 시나리오 테스트

```bash
# Zone 0에서 상품 판단
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 0,
    "weight_delta": -365
  }' | python3 -m json.tool
```

### 5.3 SSE 이벤트 모니터링

**터미널 1 (이벤트 모니터링):**
```bash
# loadcell.change 이벤트 실시간 수신
curl -N http://localhost:8001/sse
```

**터미널 2 (이벤트 트리거):**
```bash
# 로드셀에서 물건을 집으면 터미널 1에 이벤트 표시됨
```

### 5.4 pytest 통합 테스트

```bash
cd ~/ai-vending/Edge_Environment
source .venv/bin/activate

# pytest 설치 확인
pip install pytest pytest-asyncio pytest-cov

# 전체 테스트
pytest services/model/tests/ -v

# 특정 테스트만 실행
pytest services/model/tests/test_api.py -v

# 커버리지 포함
pytest services/model/tests/ -v --cov=services/model --cov-report=html

# HTML 리포트 확인
xdg-open htmlcov/index.html
```

---

## 6. 트러블슈팅

### 6.1 시리얼 포트 접근 오류

```bash
# 오류: Permission denied: '/dev/ttyTHS0'

# 해결 1: dialout 그룹 확인
groups
# dialout이 없으면:
sudo usermod -aG dialout $USER
# 로그아웃 후 재로그인

# 해결 2: 수동 권한 부여
sudo chmod 666 /dev/ttyTHS0

# 해결 3: udev 규칙 추가 (영구적)
echo 'KERNEL=="ttyTHS*", MODE="0666"' | sudo tee /etc/udev/rules.d/99-serial.rules
sudo udevadm control --reload-rules
```

### 6.2 카메라 인식 실패

```bash
# 문제: /dev/video* 장치가 없음

# USB 카메라 연결 확인
lsusb

# 카메라 장치 목록
v4l2-ctl --list-devices

# 권한 문제 해결
sudo chmod 666 /dev/video*

# udev 규칙 (영구적)
echo 'KERNEL=="video*", MODE="0666"' | sudo tee /etc/udev/rules.d/99-camera.rules
sudo udevadm control --reload-rules
```

### 6.3 GPU 메모리 부족

```bash
# GPU 상태 확인
nvidia-smi

# GPU 사용 프로세스 확인
sudo fuser -v /dev/nvidia*

# 다른 프로세스 종료
sudo kill -9 <PID>

# Docker 컨테이너 리소스 확인
docker stats

# 메모리 정리
docker system prune -f
```

### 6.4 Docker 빌드 오류

```bash
# 오류: failed to solve: failed to compute cache key

# 해결: Docker 캐시 정리
docker builder prune -f
docker system prune -f

# 재빌드
docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml build --no-cache
```

### 6.5 컨테이너 디버깅

```bash
# 컨테이너 내부 접속
docker exec -it edge_environment-model-1 /bin/bash

# 컨테이너 로그 확인
docker logs edge_environment-model-1 --tail=100

# 컨테이너 간 네트워크 테스트
docker exec edge_environment-model-1 curl http://io_board:8001/health
```

### 6.6 네트워크 문제

```bash
# Docker 네트워크 확인
docker network ls
docker network inspect edge_environment_default

# 포트 사용 확인
sudo netstat -tlnp | grep -E "8001|8002|8003"

# 방화벽 확인 (UFW)
sudo ufw status
```

---

## 빠른 참조 명령어

| 작업 | 명령어 |
|------|--------|
| 전체 빌드 | `docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml build` |
| 전체 시작 | `docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml up -d` |
| 전체 중지 | `docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml down` |
| 상태 확인 | `docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml ps` |
| 로그 확인 | `docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml logs -f` |
| 특정 서비스 재시작 | `docker compose -f docker-compose.yaml -f docker-compose.jetson.yaml restart <service>` |
| GPU 확인 | `nvidia-smi` |
| 시리얼 포트 | `ls -la /dev/ttyTHS* /dev/ttyUSB*` |
| 카메라 확인 | `v4l2-ctl --list-devices` |

---

## 환경 변수 참조

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `IO_BOARD_PORT` | `/dev/ttyTHS0` | 시리얼 포트 경로 |
| `IO_BOARD_BAUDRATE` | `38400` | 시리얼 통신 속도 |
| `YOLO_MODEL_PATH` | `/app/models/siyeon_best.pt` | YOLO 모델 파일 경로 |
| `CAMERA_MODE` | `hardware` | `hardware` 또는 `folder` |
| `MQTT_BROKER_HOST` | `192.168.1.10` | MQTT 브로커 IP |
| `MQTT_BROKER_PORT` | `1883` | MQTT 브로커 포트 |
| `MONGO_URI` | - | MongoDB 연결 URI |
| `LOG_LEVEL` | `INFO` | 로그 레벨 (DEBUG/INFO/WARNING/ERROR) |

---

## JetPack 6.2 특이사항

1. **L4T 버전**: R36.2.0 (CUDA 12.2, cuDNN 8.9)
2. **기본 Python**: Python 3.10
3. **Docker Runtime**: `nvidia-container-toolkit` 사용 (`--runtime=nvidia` 또는 `--gpus all`)
4. **시리얼 포트**: 기본 UART는 `/dev/ttyTHS0`
5. **Power Mode**: `sudo nvpmodel -q` 로 확인, `sudo nvpmodel -m 0` 으로 최대 성능 모드

```bash
# JetPack 6.2 최대 성능 모드 설정
sudo nvpmodel -m 0
sudo jetson_clocks
```
