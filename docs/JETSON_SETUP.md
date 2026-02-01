# Jetson Orin Nano 4GB 설치 가이드

AI 스마트 자판기 Model 서비스 - Jetson Orin Nano 설치 및 실행 가이드

> **대상**: Jetson Orin Nano Developer Kit (4GB)
> **OS**: JetPack 6.2 (Ubuntu 22.04)
> **최종 업데이트**: 2026-02-01

## 목차

1. [사전 요구사항](#1-사전-요구사항)
2. [JetPack 설치 확인](#2-jetpack-설치-확인)
3. [프로젝트 설정](#3-프로젝트-설정)
4. [TensorRT 엔진 생성](#4-tensorrt-엔진-생성)
5. [서비스 실행](#5-서비스-실행)
6. [성능 최적화](#6-성능-최적화)
7. [트러블슈팅](#7-트러블슈팅)
8. [시스템 서비스 등록](#8-시스템-서비스-등록)

---

## 1. 사전 요구사항

### 하드웨어

- Jetson Orin Nano Developer Kit (**4GB 모델**)
- microSD 카드 64GB 이상 (UHS-I 이상 권장)
- 전원 어댑터 (DC 5V/4A 또는 USB-C PD)
- 네트워크 연결 (이더넷 또는 WiFi)

### 소프트웨어

- JetPack 6.2 (Ubuntu 22.04 기반)
- NVIDIA L4T (Linux for Tegra)

---

## 2. JetPack 설치 확인

### 2.1 JetPack 버전 확인

```bash
# JetPack 버전 확인
cat /etc/nv_tegra_release
# 예상 출력: # R36 (release), REVISION: 2.0, ...

# L4T 버전 확인
dpkg -l | grep -i l4t
```

### 2.2 CUDA 확인

```bash
# CUDA 버전 확인
nvcc --version
# 예상: Cuda compilation tools, release 12.x

# CUDA 경로 확인
ls /usr/local/cuda/
```

### 2.3 TensorRT 확인

```bash
# TensorRT 버전 확인
dpkg -l | grep -i tensorrt
# 예상: libnvinfer10, libnvinfer-plugin10 등

# Python에서 확인
python3 -c "import tensorrt; print(f'TensorRT: {tensorrt.__version__}')"
```

### 2.4 PyTorch 확인 (시스템 패키지)

```bash
# PyTorch 확인 (JetPack 포함)
python3 -c "import torch; print(f'PyTorch: {torch.__version__}')"
python3 -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
python3 -c "import torch; print(f'GPU: {torch.cuda.get_device_name(0)}')"
```

### 2.5 FFmpeg 설치

```bash
# FFmpeg 설치 (MJPEG 디코딩용)
sudo apt update
sudo apt install -y ffmpeg

# 설치 확인
ffmpeg -version
ffmpeg -codecs | grep mjpeg
```

---

## 3. 프로젝트 설정

### 3.1 레포지토리 클론

```bash
# 홈 디렉토리로 이동
cd ~

# 레포지토리 클론
git clone <repository-url> Edge_Environment
cd Edge_Environment
```

### 3.2 Python 가상환경 생성

**중요**: `--system-site-packages` 옵션 필수! (PyTorch, NumPy 등 시스템 패키지 사용)

```bash
# 가상환경 생성 (시스템 패키지 포함)
python3 -m venv --system-site-packages .venv

# 가상환경 활성화
source .venv/bin/activate

# pip 업그레이드
pip install --upgrade pip
```

### 3.3 의존성 설치

```bash
# AI 의존성 설치
pip install -e ".[ai]"

# 설치 확인
pip list | grep ultralytics
```

### 3.4 환경변수 설정

```bash
# .env 파일 생성
cp .env.example .env

# 편집
nano .env
```

**.env 파일 내용:**

```bash
# Model Service 설정
MODEL__API__HOST=0.0.0.0
MODEL__API__PORT=8002
MODEL__API__LOG_LEVEL=info

# TensorRT 엔진 경로
MODEL__VISION__YOLO_MODEL_PATH=models/siyeon_best.engine

# 세션 설정
MODEL__BUFFER__TTL_SECONDS=300
MODEL__BUFFER__MAX_SESSIONS=100

# 카메라 가중치
MODEL__VISION__TOP_WEIGHT=0.5
MODEL__VISION__SIDE_WEIGHT=0.5
MODEL__VISION__COMMON_CLASS_BONUS=0.2
```

---

## 4. TensorRT 엔진 생성

### 4.1 모델 디렉토리 생성

```bash
mkdir -p models
```

### 4.2 PyTorch 모델 복사

```bash
# scp 또는 USB로 .pt 파일 복사
# 예: scp user@host:/path/to/siyeon_best.pt models/
```

### 4.3 TensorRT 엔진 변환

```bash
# .pt → .engine 변환 (Jetson에서만 가능!)
# 480x480 입력 크기, FP16 최적화
yolo export model=models/siyeon_best.pt \
    format=engine \
    device=0 \
    half=True \
    imgsz=480

# 변환 결과 확인
ls -la models/siyeon_best.engine
# 예상 크기: 30-100MB (모델에 따라 다름)
```

### 4.4 변환 확인

```bash
# Python에서 엔진 로드 테스트
python3 -c "
from ultralytics import YOLO
model = YOLO('models/siyeon_best.engine')
print(f'Model loaded: {model.names}')
print(f'Class count: {len(model.names)}')
"
```

---

## 5. 서비스 실행

### 5.1 직접 실행 (개발/테스트)

```bash
# 가상환경 활성화
source .venv/bin/activate

# Model 서비스 실행
cd services/model
python main.py
```

### 5.2 헬스 체크

```bash
# 다른 터미널에서
curl http://localhost:8002/api/health
# 예상 응답: {"model": "HEALTHY", "status": "ok", "yolo_loaded": true, ...}

# 상세 헬스 체크
curl http://localhost:8002/api/health/detailed
```

### 5.3 추론 테스트

```bash
# 테스트 비디오가 있는 경우
curl -X POST http://localhost:8002/trigger \
    -H "Content-Type: application/json" \
    -d '{
        "zone": 0,
        "videos": {"top": "/path/to/test_top.avi", "side": "/path/to/test_side.avi"},
        "loadcells": []
    }'
```

---

## 6. 성능 최적화

### 6.1 전원 모드 설정

```bash
# MAXN 모드 (최대 성능, 15W)
sudo nvpmodel -m 0

# 현재 모드 확인
nvpmodel -q

# 클럭 최대화
sudo jetson_clocks

# 상태 확인
sudo jetson_clocks --show
```

### 6.2 GPU 모니터링

```bash
# 실시간 모니터링
tegrastats

# 지속적 모니터링 (1초 간격)
watch -n 1 tegrastats
```

### 6.3 메모리 관리

```bash
# 스왑 메모리 증가 (4GB RAM 보완)
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 영구 적용
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 6.4 부팅 시 클럭 최대화

```bash
# 서비스 파일 생성
sudo nano /etc/systemd/system/jetson-clocks.service
```

**jetson-clocks.service:**

```ini
[Unit]
Description=Maximize Jetson Clocks
After=nvpmodel.service

[Service]
Type=oneshot
ExecStart=/usr/bin/jetson_clocks
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

```bash
# 서비스 활성화
sudo systemctl enable jetson-clocks
sudo systemctl start jetson-clocks
```

---

## 7. 트러블슈팅

### 7.1 CUDA를 찾을 수 없음

```bash
# 환경변수 설정
export PATH=/usr/local/cuda/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH

# 영구 적용
echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc
```

### 7.2 TensorRT 엔진 로드 실패

```bash
# "Incompatible engine version" 오류
# → Jetson에서 .engine 파일 재생성 필요
rm models/siyeon_best.engine
yolo export model=models/siyeon_best.pt format=engine device=0 half=True imgsz=480
```

### 7.3 메모리 부족 (OOM)

```bash
# 1. 스왑 확인
free -h

# 2. 다른 프로세스 확인
htop

# 3. GPU 메모리 확인
tegrastats

# 4. 배치 크기 확인 (코드에서 batch_size=1 확인)
```

### 7.4 FFmpeg 오류

```bash
# MJPEG 코덱 확인
ffmpeg -codecs | grep mjpeg

# 재설치
sudo apt install --reinstall ffmpeg
```

### 7.5 서비스 시작 느림 (첫 요청 지연)

```bash
# GPU 워밍업이 정상적으로 실행되는지 확인
# 로그에서 "GPU warmup complete" 메시지 확인
```

---

## 8. 시스템 서비스 등록

### 8.1 systemd 서비스 파일 생성

```bash
sudo nano /etc/systemd/system/ai-model.service
```

**ai-model.service:**

```ini
[Unit]
Description=AI Smart Vending Model Service
After=network.target

[Service]
Type=simple
User=jetson
WorkingDirectory=/home/jetson/Edge_Environment/services/model
Environment="PATH=/home/jetson/Edge_Environment/.venv/bin:/usr/local/cuda/bin:/usr/bin"
Environment="LD_LIBRARY_PATH=/usr/local/cuda/lib64"
ExecStart=/home/jetson/Edge_Environment/.venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 8.2 서비스 등록 및 시작

```bash
# 서비스 등록
sudo systemctl daemon-reload
sudo systemctl enable ai-model

# 서비스 시작
sudo systemctl start ai-model

# 상태 확인
sudo systemctl status ai-model

# 로그 확인
journalctl -u ai-model -f
```

### 8.3 서비스 관리

```bash
# 시작
sudo systemctl start ai-model

# 중지
sudo systemctl stop ai-model

# 재시작
sudo systemctl restart ai-model

# 상태
sudo systemctl status ai-model

# 로그 (실시간)
journalctl -u ai-model -f

# 로그 (최근 100줄)
journalctl -u ai-model -n 100
```

---

## 부록: 성능 벤치마크

### 예상 성능 (Jetson Orin Nano 4GB)

| 항목 | 값 |
|------|------|
| YOLO 추론 | ~30-50ms/프레임 |
| 전체 비디오 (30fps × 10초) | ~10-15초 |
| GPU 메모리 사용 | ~1.5-2GB |
| CPU 메모리 사용 | ~500MB |

### 성능 모니터링

```bash
# CPU/GPU/메모리 종합 모니터링
tegrastats

# 출력 예시:
# RAM 2048/3964MB (lfb 0x0) SWAP 1234/8192MB CPU [25%,20%,30%,25%] GPU 95%

# 열 관리 확인
cat /sys/devices/virtual/thermal/thermal_zone*/temp
```

---

## 체크리스트

설치 완료 후 확인:

- [ ] JetPack 6.2 설치 확인
- [ ] CUDA 12.x 동작 확인
- [ ] TensorRT 10.x 동작 확인
- [ ] Python 가상환경 생성 (`--system-site-packages`)
- [ ] 의존성 설치 완료
- [ ] TensorRT 엔진 생성 완료
- [ ] 서비스 시작 및 헬스체크 성공
- [ ] 성능 모드 설정 (MAXN + jetson_clocks)
- [ ] 스왑 메모리 설정
- [ ] systemd 서비스 등록 (선택)

---

문의사항이나 문제가 있으면 이슈를 등록해주세요.
