# Jetson Orin Nano 4GB 설치 가이드

AI 스마트 자판기 Model 서비스 - Jetson Orin Nano 설치 및 실행 가이드

> **대상**: Jetson Orin Nano Developer Kit (4GB)
> **OS**: JetPack 6.2 (Ubuntu 22.04)
> **최종 업데이트**: 2026-02-06

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
cat /etc/nv_tegra_release
# 예상 출력: # R36 (release), REVISION: 2.0, ...

dpkg -l | grep -i l4t
```

### 2.2 CUDA 확인

```bash
nvcc --version
# 예상: Cuda compilation tools, release 12.x

ls /usr/local/cuda/
```

### 2.3 TensorRT 확인

```bash
dpkg -l | grep -i tensorrt
# 예상: libnvinfer10, libnvinfer-plugin10 등

python3 -c "import tensorrt; print(f'TensorRT: {tensorrt.__version__}')"
```

### 2.4 PyTorch 확인 (시스템 패키지)

```bash
python3 -c "import torch; print(f'PyTorch: {torch.__version__}')"
python3 -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
python3 -c "import torch; print(f'GPU: {torch.cuda.get_device_name(0)}')"
```

### 2.5 FFmpeg 설치

```bash
sudo apt update
sudo apt install -y ffmpeg
ffmpeg -version
ffmpeg -codecs | grep mjpeg
```

---

## 3. 프로젝트 설정

### 3.1 레포지토리 클론

```bash
cd ~
git clone <repository-url> Edge_Environment
cd Edge_Environment
```

### 3.2 uv 기반 환경 설정 (권장)

```bash
# uv 설치 (없으면)
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"

# 자동 설정 스크립트 실행
chmod +x scripts/setup_jetson.sh
./scripts/setup_jetson.sh

# 가상환경 활성화
source .venv/bin/activate
```

### 3.3 수동 설정

```bash
# 가상환경 생성 (시스템 패키지 포함 - 필수!)
uv venv --system-site-packages --python python3.10 .venv
source .venv/bin/activate

# 의존성 설치
uv pip install -e ".[dev]"

# NumPy 버전 확인 (반드시 1.x)
python -c "import numpy; print(numpy.__version__)"
# 2.x면 다운그레이드:
uv pip install "numpy>=1.24.0,<2.0.0"
```

### 3.4 환경변수 설정

```bash
cp .env.example .env
nano .env
```

**.env 파일 내용:**

```bash
MODEL__API__HOST=0.0.0.0
MODEL__API__PORT=8002
# 실제 엔진 파일명을 지정 (기본값: models/0204_siyeon.engine)
# siyeon_best.engine을 symlink로 사용하는 경우 아래 주석 해제
# MODEL__VISION__YOLO_MODEL_PATH=models/siyeon_best.engine
MODEL__VISION__YOLO_MODEL_PATH=models/0204_siyeon.engine
MODEL__BUFFER__TTL_SECONDS=300
MODEL__ASYNC_STREAMING__ENABLED=true
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
scp user@host:/path/to/siyeon_best.pt models/
```

### 4.3 TensorRT 엔진 변환

```bash
# .pt → .engine 변환 (Jetson에서만 가능!)
yolo export model=models/siyeon_best.pt \
    format=engine \
    device=0 \
    half=True \
    imgsz=480

ls -la models/siyeon_best.engine
# 예상 크기: 30-100MB
```

### 4.4 엔진 파일 이름 관리 (symlink)

코드 기본값은 `models/0204_siyeon.engine`입니다.
`siyeon_best.engine` 이름으로도 접근 가능하도록 symlink를 생성할 수 있습니다:

```bash
# 방법 1: 날짜 버전 파일을 기본 이름으로 symlink (권장)
cd models/
ln -sf 0204_siyeon.engine siyeon_best.engine
ls -la models/
# siyeon_best.engine -> 0204_siyeon.engine

# 방법 2: 환경변수로 실제 파일명 직접 지정
MODEL__VISION__YOLO_MODEL_PATH=models/0204_siyeon.engine
```

> **참고**: 새 엔진 파일로 교체할 때는 symlink만 업데이트하면 됩니다.
> `ln -sf 0301_siyeon.engine siyeon_best.engine`

### 4.5 변환 확인

```bash
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
source .venv/bin/activate
uv run model-service
```

### 5.2 헬스 체크

```bash
curl http://localhost:8002/api/health
# 예상: {"model": "HEALTHY", "status": "ok", "yolo_loaded": true, ...}

curl http://localhost:8002/api/health/detailed
```

### 5.3 Docker 실행 (v5.4+)

```bash
# Edge_Environment 루트에서 실행
docker compose up -d model
docker compose logs -f model

# TensorRT 엔진 변환 (일회성)
docker compose --profile convert run --rm convert
```

---

## 6. 성능 최적화

### 6.1 전원 모드 설정

```bash
# MAXN 모드 (최대 성능, 15W)
sudo nvpmodel -m 0
nvpmodel -q

# 클럭 최대화
sudo jetson_clocks
sudo jetson_clocks --show
```

### 6.2 GPU 모니터링

```bash
tegrastats
watch -n 1 tegrastats
```

### 6.3 스왑 메모리 증가

```bash
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

## 7. 트러블슈팅

### 7.1 CUDA를 찾을 수 없음

```bash
export PATH=/usr/local/cuda/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH

# 영구 적용
echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc
```

### 7.2 TensorRT 엔진 로드 실패

```bash
# "Incompatible engine version" → Jetson에서 재생성
rm models/siyeon_best.engine
yolo export model=models/siyeon_best.pt format=engine device=0 half=True imgsz=480
```

### 7.3 메모리 부족 (OOM)

```bash
free -h
tegrastats
# 배치 크기 확인 (batch_size=1 필수)
```

### 7.4 FFmpeg 오류

```bash
ffmpeg -codecs | grep mjpeg
sudo apt install --reinstall ffmpeg
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
WorkingDirectory=/home/jetson/Edge_Environment
Environment="PATH=/home/jetson/Edge_Environment/.venv/bin:/usr/local/cuda/bin:/usr/bin"
Environment="LD_LIBRARY_PATH=/usr/local/cuda/lib64"
ExecStart=/home/jetson/Edge_Environment/.venv/bin/python -m model_service.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 8.2 서비스 등록 및 시작

```bash
sudo systemctl daemon-reload
sudo systemctl enable ai-model
sudo systemctl start ai-model
sudo systemctl status ai-model
journalctl -u ai-model -f
```

---

## 부록: 성능 벤치마크

### 예상 성능 (Jetson Orin Nano 4GB)

| 항목 | 값 |
|------|------|
| YOLO 추론 | ~30-50ms/프레임 |
| 전체 비디오 (30fps x 10초) | ~10-15초 |
| Async Streaming (v5.3) | ~8-12초 |
| GPU 메모리 사용 | ~1.5-2GB |
| CPU 메모리 사용 | ~500MB |

---

## 체크리스트

설치 완료 후 확인:

- [ ] JetPack 6.2 설치 확인
- [ ] CUDA 12.x 동작 확인
- [ ] TensorRT 10.x 동작 확인
- [ ] Python 가상환경 생성 (`--system-site-packages`)
- [ ] NumPy < 2.0 확인
- [ ] 의존성 설치 완료
- [ ] TensorRT 엔진 생성 완료
- [ ] 서비스 시작 및 헬스체크 성공
- [ ] 성능 모드 설정 (MAXN + jetson_clocks)
- [ ] 스왑 메모리 설정
