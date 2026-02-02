# Model Service Dockerfile for Jetson Orin Nano 4GB
#
# Jetson Orin Nano (JetPack 6.2) TensorRT 전용
# 멀티스테이지 빌드로 이미지 크기 최소화
#
# Build:
#   docker build -t model-service:latest .
#
# Run:
#   docker run --runtime nvidia -p 8002:8002 model-service:latest

# ==============================================================================
# Stage 1: Base image with CUDA and TensorRT
# ==============================================================================
FROM nvcr.io/nvidia/l4t-pytorch:r36.2.0-pth2.1-py3 AS base

# Jetson 환경 변수
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul

# 시스템 패키지 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# Python 패키지 디렉토리
WORKDIR /app

# ==============================================================================
# Stage 2: Dependencies
# ==============================================================================
FROM base AS deps

# pip 업그레이드
RUN pip3 install --no-cache-dir --upgrade pip

# pyproject.toml 복사 (캐시 활용)
COPY pyproject.toml ./

# 의존성 설치 (--system-site-packages 필요 - CUDA/TensorRT 상속)
# uv 대신 pip 사용 (Docker 환경에서 더 안정적)
RUN pip3 install --no-cache-dir \
    fastapi>=0.109.0 \
    uvicorn>=0.25.0 \
    pydantic>=2.5.0 \
    pydantic-settings>=2.1.0 \
    pyyaml>=6.0 \
    python-multipart>=0.0.6 \
    httpx>=0.25.0 \
    numpy>=1.24.0,\<2.0.0 \
    opencv-python-headless>=4.8.0 \
    ultralytics>=8.1.0

# ==============================================================================
# Stage 3: Application
# ==============================================================================
FROM deps AS app

# 소스 코드 복사
COPY main.py ./
COPY src/ ./src/

# 설정 파일 복사
COPY ../../config/ /app/config/

# 비root 사용자 생성 (보안)
RUN useradd -m -u 1000 modeluser
USER modeluser

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8002/api/health || exit 1

# 포트 노출
EXPOSE 8002

# 환경 변수 (런타임 설정 가능)
ENV MODEL__API__HOST=0.0.0.0
ENV MODEL__API__PORT=8002
ENV MODEL__API__LOG_LEVEL=info
ENV MODEL__VISION__YOLO_MODEL_PATH=/data/models/siyeon_best.engine
ENV MODEL__BUFFER__TTL_SECONDS=300
ENV MODEL__BUFFER__MAX_SESSIONS=100
ENV MODEL__DOOR_SESSION__ENABLED=true
ENV MODEL__DOOR_SESSION__TIMEOUT=30.0

# 볼륨 마운트 포인트
VOLUME ["/data/models", "/data/sessions"]

# 실행
CMD ["python3", "main.py"]
