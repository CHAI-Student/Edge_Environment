# Jetson Orin Nano 테스트 가이드

> **최종 업데이트**: 2026-01-29

AI Smart Vending Machine 시스템을 Jetson Orin Nano에서 테스트하는 방법을 설명합니다.

> **대상 환경**: Jetson Orin Nano, JetPack 6.2, Ubuntu 22.04
> **작업 방식**: Jetson 장치에서 직접 실행 (PM2 기반)

---

## 목차

1. [사전 준비](#1-사전-준비)
2. [프로젝트 클론 및 설정](#2-프로젝트-클론-및-설정)
3. [PM2 통합 실행 (권장)](#3-pm2-통합-실행-권장)
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

# NVIDIA GPU 확인
nvidia-smi
# GPU 정보가 표시되어야 함
```

### 1.2 Node.js 설치

```bash
# NodeSource에서 Node.js 20.x LTS 설치
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# 버전 확인
node --version   # v20.x.x
npm --version    # 10.x.x

# PM2 전역 설치
sudo npm install -g pm2
pm2 --version
```

### 1.3 Python 환경 설정

```bash
# Python 버전 확인 (3.10 이상 필요)
python3 --version

# pip 업그레이드
pip3 install --upgrade pip

# uv 설치 (권장 - 빠른 패키지 관리자)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv --version
```

### 1.4 사용자 권한 설정

```bash
# 시리얼 포트 접근 권한 (dialout 그룹)
sudo usermod -aG dialout $USER

# 비디오 장치 접근 권한 (video 그룹)
sudo usermod -aG video $USER

# 변경 적용 (로그아웃 후 재로그인)
# GUI: 로그아웃 → 로그인
# 터미널: 새 터미널 열기

# 권한 확인
groups
# 출력에 dialout, video가 포함되어야 함
```

### 1.5 하드웨어 연결 확인

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

**.env 파일 내용 예시 (Jetson):**

```env
# IO Board (Jetson: /dev/ttyTHS0, USB: /dev/ttyUSB0)
IO_BOARD__SERIAL__PORT=/dev/ttyTHS0
IO_BOARD__SERIAL__BAUDRATE=38400

# Camera
CAMERA__NVIDIA_MODE=true
CAMERA__RESOLUTION_WIDTH=640
CAMERA__RESOLUTION_HEIGHT=480
CAMERA__FPS=30

# Model
MODEL__VISION__YOLO_MODEL_PATH=../../../siyeon_best.pt

# MQTT (필요시)
MQTT__MQTT_BROKER_HOST=192.168.1.10
MQTT__MQTT_BROKER_PORT=1883

# Log Level
LOG_LEVEL=INFO
```

### 2.3 의존성 설치

```bash
cd ~/ai-vending/Edge_Environment

# Python 의존성 (uv 권장)
uv sync --extra ai --extra mqtt

# 또는 pip
pip install -e ".[ai,mqtt]"

# Node.js 의존성
npm install
```

### 2.4 모델 파일 준비

```bash
# 모델 디렉토리 생성
mkdir -p models

# YOLO 모델 파일 복사 (USB 또는 네트워크에서)
# 예: USB 드라이브에서 복사
cp /media/$USER/USB_DRIVE/siyeon_best.pt ./

# 모델 파일 확인
ls -la siyeon_best.pt
```

---

## 3. PM2 통합 실행 (권장)

### 3.1 전체 서비스 시작

```bash
cd ~/ai-vending/Edge_Environment

# 전체 서비스 시작 (7개 서비스)
npm start

# 또는 직접 PM2 사용
pm2 start ecosystem.config.js
```

**실행되는 서비스:**
| 서비스 | 포트 | 설명 |
|--------|------|------|
| orchestrator | 8889 | Node.js 오케스트레이터 |
| client | 3000 | React 대시보드 |
| io-board | 8001 | 로드셀 + 데드볼트 |
| model | 8002 | AI 상품 판단 |
| camera-driver | 8003 | 카메라 관리 |
| mqtt-client | 8006 | MQTT IF01-04 |
| card-terminal | 5000 | 결제 터미널 |

### 3.2 서비스 상태 확인

```bash
# PM2 서비스 목록
pm2 list
pm2 status

# 전체 로그 확인
pm2 logs

# 특정 서비스 로그
pm2 logs model --lines 100
pm2 logs io-board --lines 50

# 실시간 로그 모니터링
pm2 logs --follow
```

### 3.3 헬스 체크

```bash
# 각 서비스 헬스 체크
curl http://localhost:8001/health         # IO Board
curl http://localhost:8002/api/health     # Model
curl http://localhost:8003/api/health     # Camera Driver
curl http://localhost:8006/health         # MQTT
curl http://localhost:8889/health         # Node.js
curl http://localhost:5000/status         # Card Terminal

# 전체 헬스 체크 스크립트
echo "=== Service Health Check ===" && \
curl -s http://localhost:8001/health && echo " - io-board" && \
curl -s http://localhost:8002/api/health && echo " - model" && \
curl -s http://localhost:8003/api/health && echo " - camera-driver" && \
curl -s http://localhost:8889/health && echo " - orchestrator"

# GPU 사용량 모니터링
nvidia-smi
watch -n 1 nvidia-smi  # 1초마다 갱신
```

### 3.4 개별 서비스 제어

```bash
# 특정 서비스만 시작
pm2 start ecosystem.config.js --only model
pm2 start ecosystem.config.js --only "io-board,camera-driver"

# 서비스 재시작
pm2 restart model
pm2 restart io-board

# 서비스 중지
pm2 stop model
pm2 stop all

# 서비스 삭제
pm2 delete model
pm2 delete all
```

### 3.5 PM2 자동 시작 설정

```bash
# 현재 PM2 프로세스 목록 저장
pm2 save

# 시스템 부팅 시 자동 시작 설정
pm2 startup
# 출력되는 sudo 명령어 실행

# 자동 시작 해제
pm2 unstartup
```

---

## 4. 터미널 개별 서비스 테스트

PM2 없이 직접 서비스를 실행하여 디버깅합니다.

### 4.1 IO Board 서비스 테스트 (포트 8001)

**터미널 1:**
```bash
cd ~/ai-vending/Edge_Environment/services/io_board
IO_BOARD__SERIAL__PORT=/dev/ttyTHS0 python main.py
```

**터미널 2:**
```bash
# 헬스 체크
curl http://localhost:8001/health

# 로드셀 무게 조회
curl http://localhost:8001/loadcells

# 도어/데드볼트 상태 조회
curl http://localhost:8001/status

# 데드볼트 열기
curl -X POST http://localhost:8001/deadbolt \
  -H "Content-Type: application/json" \
  -d '{"action": "OPEN"}'

# 데드볼트 닫기
curl -X POST http://localhost:8001/deadbolt \
  -H "Content-Type: application/json" \
  -d '{"action": "CLOSE"}'

# SSE 스트림 테스트
curl -N "http://localhost:8001/sse?streams=loadcells,doors"
```

### 4.2 Camera Driver 서비스 테스트 (포트 8003)

**터미널 1:**
```bash
cd ~/ai-vending/Edge_Environment/services/camera_driver
CAMERA__NVIDIA_MODE=true python main.py
```

**터미널 2:**
```bash
# 헬스 체크
curl http://localhost:8003/api/health

# 카메라 상태
curl http://localhost:8003/api/status

# 디바이스 스캔
curl http://localhost:8003/api/devices/scan

# Zone 0 활성화
curl -X POST http://localhost:8003/api/zone/0/activate

# Zone 0 스냅샷
curl -X POST http://localhost:8003/api/zone/0/snapshot \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test123", "include_top": true}'

# 프레임 캡처 테스트 (이미지 저장)
curl http://localhost:8003/api/cameras/0/capture --output test_cam0.jpg
ls -la test_cam0.jpg
```

### 4.3 Model 서비스 테스트 (포트 8002)

**터미널 1:**
```bash
cd ~/ai-vending/Edge_Environment/services/model
MODEL__VISION__YOLO_MODEL_PATH=../../../siyeon_best.pt python main.py
```

**터미널 2:**
```bash
# 헬스 체크
curl http://localhost:8002/api/health

# 상품 목록 조회
curl http://localhost:8002/api/products

# Zone 설정 조회
curl http://localhost:8002/api/zones/config

# 상품 판단 테스트 (Vision-only)
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 0, "vision_only": true}'

# 무게 변화 포함 판단
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
      "image_folder": "data/test_images"
    }
  }'
```

### 4.4 Card Terminal 서비스 테스트 (포트 5000/5001)

**터미널 1:**
```bash
cd ~/ai-vending/Edge_Environment/services/card_terminal
python main.py
```

**터미널 2:**
```bash
# 헬스 체크
curl http://localhost:5000/status

# SSE 이벤트 스트림 연결
curl -N http://localhost:5000/sse

# 토큰 결제 승인 테스트
curl -X POST http://localhost:5000/payment/token/approve \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "000001000",
    "vankey_hash": "VANKEY1234567890HASH1234"
  }'

# 삼성페이 승인 테스트
curl -X POST http://localhost:5000/payment/samsung-pay/approve \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "000005000",
    "authorization_type": "PURCHASE",
    "display_message": "삼성페이 결제"
  }'
```

### 4.5 Node.js 서버 테스트 (포트 8889)

```bash
cd ~/ai-vending/Edge_Environment

# 서버만 실행
npm run start:server

# 또는 서버 + React 동시 실행 (개발용)
npm run dev
```

**다른 터미널에서:**
```bash
# 헬스 체크
curl http://localhost:8889/health

# 통합 상태 조회
curl http://localhost:8889/api/dashboard/status

# SSE 이벤트 스트림
curl -N http://localhost:8889/sse/events
```

### 4.6 React 클라이언트 테스트 (포트 3000)

```bash
cd ~/ai-vending/Edge_Environment/client

# 개발 서버 실행
npm start

# 빌드 (프로덕션용)
npm run build
```

브라우저에서 `http://localhost:3000` 접속하여 대시보드 확인.

---

## 5. 전체 시스템 통합 테스트

### 5.1 서비스 연동 테스트

```bash
# PM2로 전체 서비스 시작
cd ~/ai-vending/Edge_Environment
npm start

# 30초 대기 후 상태 확인
sleep 30
pm2 status

# 전체 헬스 체크
echo "=== Service Health Check ==="
curl -s http://localhost:8001/health && echo " - io-board OK"
curl -s http://localhost:8002/api/health && echo " - model OK"
curl -s http://localhost:8003/api/health && echo " - camera-driver OK"
curl -s http://localhost:8006/health && echo " - mqtt-client OK"
curl -s http://localhost:8889/health && echo " - orchestrator OK"
curl -s http://localhost:5000/status && echo " - card-terminal OK"
```

### 5.2 상품 픽업 시나리오 테스트

```bash
# Zone 0에서 상품 판단 (Node.js 경유)
curl -X POST http://localhost:8889/api/model/judge \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 0,
    "weight_data": {
      "before_weights": [1000, 1005, 0, 0, 0, 0, 0, 0, 0, 0],
      "after_weights": [480, 505, 0, 0, 0, 0, 0, 0, 0, 0],
      "delta_weight": -520,
      "channels": [0, 1]
    }
  }' | python3 -m json.tool
```

### 5.3 카메라 전용 테스트 (로드셀 없이)

```bash
# 서비스 상태 확인
curl http://localhost:8889/api/camera/test/status

# Zone 0 스냅샷 + 판단
curl -X POST http://localhost:8889/api/camera/test/snapshot-and-judge \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 0, "include_top": true}'

# 녹화 + 판단 (3초)
curl -X POST http://localhost:8889/api/camera/test/record-and-judge \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 0, "include_top": true, "duration_ms": 3000}'
```

### 5.4 SSE 이벤트 모니터링

**터미널 1 (이벤트 모니터링):**
```bash
# IO Board SSE (loadcell.change, door.update)
curl -N "http://localhost:8001/sse?streams=loadcells,doors"

# 또는 Node.js 통합 SSE
curl -N http://localhost:8889/sse/events
```

**터미널 2 (이벤트 트리거):**
```bash
# 데드볼트 열기 → 터미널 1에 door.update 이벤트 표시
curl -X POST http://localhost:8001/deadbolt \
  -H "Content-Type: application/json" \
  -d '{"action": "OPEN"}'
```

### 5.5 pytest 통합 테스트

```bash
cd ~/ai-vending/Edge_Environment

# pytest 설치 확인
pip install pytest pytest-asyncio pytest-cov

# 전체 테스트
pytest services/model/src/tests/ -v

# 특정 테스트만 실행
pytest services/model/src/tests/test_api.py -v

# 커버리지 포함
pytest services/model/src/tests/ -v --cov=services/model/src --cov-report=html

# HTML 리포트 확인 (GUI 환경)
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

# PM2 서비스 메모리 확인
pm2 monit

# 메모리 정리 (PM2 재시작)
pm2 restart all
```

### 6.4 PM2 서비스 오류

```bash
# 로그 확인
pm2 logs model --lines 200

# 서비스 상세 정보
pm2 show model

# 서비스 재시작 (오류 후)
pm2 restart model

# 전체 삭제 후 재시작
pm2 delete all
npm start
```

### 6.5 포트 충돌

```bash
# 사용 중인 포트 확인
sudo netstat -tlnp | grep -E "8001|8002|8003|8006|8889|5000|3000"

# 특정 포트 프로세스 확인
sudo lsof -i :8002

# 프로세스 종료
sudo kill -9 <PID>
```

### 6.6 Python 모듈 오류

```bash
# 오류: ModuleNotFoundError

# 가상환경 확인
which python3

# uv 사용 시 재설치
uv sync --extra ai --extra mqtt

# pip 사용 시 재설치
pip install -e ".[ai,mqtt]"
```

### 6.7 Node.js 오류

```bash
# 오류: Cannot find module

# node_modules 삭제 후 재설치
rm -rf node_modules
npm install

# PM2 캐시 정리
pm2 kill
npm start
```

---

## 빠른 참조 명령어

| 작업 | 명령어 |
|------|--------|
| 전체 시작 | `npm start` |
| 전체 중지 | `npm run stop` |
| 전체 재시작 | `npm run restart` |
| 상태 확인 | `pm2 status` |
| 로그 확인 | `pm2 logs` |
| 특정 서비스 시작 | `pm2 start ecosystem.config.js --only <service>` |
| 특정 서비스 재시작 | `pm2 restart <service>` |
| GPU 확인 | `nvidia-smi` |
| 시리얼 포트 | `ls -la /dev/ttyTHS* /dev/ttyUSB*` |
| 카메라 확인 | `v4l2-ctl --list-devices` |

---

## 환경 변수 참조

### Python 서비스 (env_prefix 패턴)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `IO_BOARD__SERIAL__PORT` | `/dev/ttyUSB0` | 시리얼 포트 경로 |
| `IO_BOARD__SERIAL__BAUDRATE` | `38400` | 시리얼 통신 속도 |
| `IO_BOARD__API__PORT` | `8001` | IO Board API 포트 |
| `MODEL__VISION__YOLO_MODEL_PATH` | `siyeon_best.pt` | YOLO 모델 파일 경로 |
| `MODEL__API__PORT` | `8002` | Model API 포트 |
| `CAMERA__NVIDIA_MODE` | `true` | Jetson 짝수 인덱싱 |
| `CAMERA__API_PORT` | `8003` | Camera API 포트 |
| `MQTT__MQTT_BROKER_HOST` | `localhost` | MQTT 브로커 IP |
| `MQTT__MQTT_BROKER_PORT` | `1883` | MQTT 브로커 포트 |
| `MQTT__API_PORT` | `8006` | MQTT API 포트 |
| `CARD_TERMINAL__API__PORT` | `5000` | Card Terminal API 포트 |
| `CARD_TERMINAL__CAT__PORT` | `5001` | CAT 디바이스 TCP 포트 |

### 서비스 포트

| 서비스 | 포트 | 설명 |
|--------|------|------|
| io-board | 8001 | 로드셀 + 데드볼트 SSE |
| model | 8002 | AI 상품 판단 |
| camera-driver | 8003 | 카메라 관리 |
| card-terminal | 5000/5001 | 결제 터미널 API/CAT |
| mqtt-client | 8006 | MQTT IF01-04 |
| orchestrator | 8889 | Node.js 오케스트레이터 |
| client | 3000 | React 대시보드 |

---

## JetPack 6.2 특이사항

1. **L4T 버전**: R36.2.0 (CUDA 12.2, cuDNN 8.9)
2. **기본 Python**: Python 3.10
3. **시리얼 포트**: 기본 UART는 `/dev/ttyTHS0`
4. **Power Mode**: `sudo nvpmodel -q` 로 확인

```bash
# JetPack 6.2 최대 성능 모드 설정
sudo nvpmodel -m 0
sudo jetson_clocks
```

---

## API 엔드포인트 요약

### IO Board (8001)
```
GET  /health                  # 헬스 체크
GET  /loadcells               # 로드셀 무게 (10ch)
GET  /status                  # door + deadbolt 상태
GET  /deadbolt                # 데드볼트 상태
POST /deadbolt                # 데드볼트 제어 {"action": "OPEN"/"CLOSE"}
POST /init                    # 초기화
POST /calibrate               # 센서 보정
GET  /sse                     # SSE 스트림
```

### Model (8002)
```
GET  /api/health              # 헬스 체크
GET  /api/products            # 상품 목록
GET  /api/zones/config        # Zone 설정
POST /api/judge               # 상품 판단
POST /api/judge/cancel        # 추론 취소
```

### Camera Driver (8003)
```
GET  /api/health              # 헬스 체크
GET  /api/status              # 카메라 상태
GET  /api/devices/scan        # 디바이스 스캔
POST /api/zone/{id}/activate  # Zone 활성화
POST /api/zone/{id}/snapshot  # 스냅샷 캡처
```

### Card Terminal (5000)
```
GET  /status                  # 헬스 체크
GET  /sse                     # SSE 이벤트 스트림
POST /payment/token/approve   # 토큰 결제 승인
POST /payment/token/cancel    # 토큰 결제 취소
POST /payment/samsung-pay/approve  # 삼성페이 승인
POST /payment/samsung-pay/cancel   # 삼성페이 취소
```

### Node.js Orchestrator (8889)
```
GET  /health                  # 헬스 체크
GET  /api/dashboard/status    # 통합 상태
GET  /sse/events              # 통합 SSE 스트림
POST /api/model/judge         # 판단 프록시
POST /api/camera/test/snapshot-and-judge  # 카메라 테스트
```
