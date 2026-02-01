#!/bin/bash
# =============================================================================
# Jetson Orin Nano 환경 설정 스크립트 (uv 사용)
# =============================================================================
#
# 요구 환경:
#   - Jetson Orin Nano Developer Kit
#   - JetPack 6.2 (Ubuntu 22.04)
#   - CUDA, cuDNN, TensorRT (JetPack에 포함)
#
# 사용법:
#   chmod +x scripts/setup_jetson.sh
#   ./scripts/setup_jetson.sh
#
# =============================================================================

set -e  # 에러 발생 시 중단

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE} Jetson Orin Nano 환경 설정 (uv)${NC}"
echo -e "${BLUE}=======================================${NC}"

# -----------------------------------------------------------------------------
# 1. 시스템 환경 확인
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}[1/6] 시스템 환경 확인...${NC}"

# Jetson 확인
if [ ! -f /etc/nv_tegra_release ]; then
    echo -e "${RED}Error: Jetson 환경이 아닙니다.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Jetson 환경 확인됨${NC}"

# Python 버전 확인
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1-2)
if [[ "$PYTHON_VERSION" != "3.10" && "$PYTHON_VERSION" != "3.11" ]]; then
    echo -e "${RED}Error: Python 3.10 또는 3.11 필요 (현재: $PYTHON_VERSION)${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python $PYTHON_VERSION${NC}"

# CUDA 확인
if ! command -v nvcc &> /dev/null; then
    echo -e "${YELLOW}Warning: nvcc not found in PATH${NC}"
else
    CUDA_VERSION=$(nvcc --version | grep "release" | awk '{print $5}' | cut -d',' -f1)
    echo -e "${GREEN}✓ CUDA $CUDA_VERSION${NC}"
fi

# PyTorch CUDA 확인
TORCH_CUDA=$(python3 -c "import torch; print(torch.cuda.is_available())" 2>/dev/null || echo "false")
if [ "$TORCH_CUDA" = "True" ]; then
    TORCH_VERSION=$(python3 -c "import torch; print(torch.__version__)")
    echo -e "${GREEN}✓ PyTorch $TORCH_VERSION (CUDA 사용 가능)${NC}"
else
    echo -e "${RED}Error: PyTorch CUDA 지원 안됨${NC}"
    echo -e "${YELLOW}JetPack에서 제공하는 PyTorch를 설치하세요:${NC}"
    echo -e "  sudo apt-get install python3-torch"
    exit 1
fi

# TensorRT 확인
TRT_VERSION=$(python3 -c "import tensorrt; print(tensorrt.__version__)" 2>/dev/null || echo "not found")
if [ "$TRT_VERSION" = "not found" ]; then
    echo -e "${YELLOW}Warning: TensorRT not found (engine 파일 로드 불가)${NC}"
else
    echo -e "${GREEN}✓ TensorRT $TRT_VERSION${NC}"
fi

# -----------------------------------------------------------------------------
# 2. uv 설치
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}[2/6] uv 설치 확인...${NC}"

if ! command -v uv &> /dev/null; then
    echo "uv 설치 중..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # PATH 추가
    export PATH="$HOME/.cargo/bin:$PATH"

    # bashrc에 추가 (없으면)
    if ! grep -q 'cargo/bin' ~/.bashrc; then
        echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
    fi

    echo -e "${GREEN}✓ uv 설치 완료${NC}"
else
    UV_VERSION=$(uv --version)
    echo -e "${GREEN}✓ uv 이미 설치됨 ($UV_VERSION)${NC}"
fi

# -----------------------------------------------------------------------------
# 3. 가상환경 생성 (시스템 패키지 상속)
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}[3/6] 가상환경 생성...${NC}"

# 프로젝트 루트로 이동
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "프로젝트 경로: $PROJECT_ROOT"

# 기존 venv 삭제 (있으면)
if [ -d ".venv" ]; then
    echo "기존 .venv 삭제 중..."
    rm -rf .venv
fi

# uv로 가상환경 생성 (시스템 패키지 상속 - CUDA/torch/tensorrt 사용)
echo "가상환경 생성 중 (--system-site-packages)..."
uv venv --system-site-packages --python python3.10 .venv

echo -e "${GREEN}✓ 가상환경 생성 완료${NC}"

# -----------------------------------------------------------------------------
# 4. 의존성 설치
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}[4/6] 의존성 설치...${NC}"

# 가상환경 활성화
source .venv/bin/activate

# uv로 의존성 설치
echo "패키지 설치 중..."
uv pip install -e ".[dev]"

# NumPy 버전 확인 (반드시 1.x)
NUMPY_VERSION=$(python3 -c "import numpy; print(numpy.__version__)")
if [[ "$NUMPY_VERSION" == 2.* ]]; then
    echo -e "${YELLOW}NumPy 2.x 감지됨. 1.x로 다운그레이드...${NC}"
    uv pip install "numpy>=1.24.0,<2.0.0"
    NUMPY_VERSION=$(python3 -c "import numpy; print(numpy.__version__)")
fi
echo -e "${GREEN}✓ NumPy $NUMPY_VERSION${NC}"

echo -e "${GREEN}✓ 의존성 설치 완료${NC}"

# -----------------------------------------------------------------------------
# 5. TensorRT 엔진 확인
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}[5/6] TensorRT 엔진 확인...${NC}"

ENGINE_PATH="$PROJECT_ROOT/models/siyeon_best.engine"
PT_PATH="$PROJECT_ROOT/models/siyeon_best.pt"

if [ -f "$ENGINE_PATH" ]; then
    echo -e "${GREEN}✓ TensorRT 엔진 존재: $ENGINE_PATH${NC}"
elif [ -f "$PT_PATH" ]; then
    echo -e "${YELLOW}⚠ .pt 파일 존재, .engine 변환 필요:${NC}"
    echo -e "  yolo export model=$PT_PATH format=engine device=0 half=True"
else
    echo -e "${YELLOW}⚠ 모델 파일 없음. 나중에 추가하세요:${NC}"
    echo -e "  models/siyeon_best.engine"
fi

# -----------------------------------------------------------------------------
# 6. 환경 검증
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}[6/6] 환경 검증...${NC}"

python3 << 'EOF'
import sys

print("=" * 50)
print("환경 검증 결과")
print("=" * 50)

# Python
print(f"Python: {sys.version}")

# NumPy
try:
    import numpy as np
    print(f"NumPy: {np.__version__}", end="")
    if np.__version__.startswith("1."):
        print(" ✓")
    else:
        print(" ⚠ (1.x 권장)")
except ImportError:
    print("NumPy: NOT FOUND ✗")

# PyTorch + CUDA
try:
    import torch
    cuda_status = "✓ CUDA" if torch.cuda.is_available() else "✗ CPU only"
    print(f"PyTorch: {torch.__version__} ({cuda_status})")
    if torch.cuda.is_available():
        print(f"  GPU: {torch.cuda.get_device_name(0)}")
except ImportError:
    print("PyTorch: NOT FOUND ✗")

# TensorRT
try:
    import tensorrt as trt
    print(f"TensorRT: {trt.__version__} ✓")
except ImportError:
    print("TensorRT: NOT FOUND ⚠")

# OpenCV
try:
    import cv2
    print(f"OpenCV: {cv2.__version__} ✓")
except ImportError:
    print("OpenCV: NOT FOUND ⚠")

# FastAPI
try:
    import fastapi
    print(f"FastAPI: {fastapi.__version__} ✓")
except ImportError:
    print("FastAPI: NOT FOUND ✗")

# Ultralytics
try:
    import ultralytics
    print(f"Ultralytics: {ultralytics.__version__} ✓")
except ImportError:
    print("Ultralytics: NOT FOUND ✗")

print("=" * 50)
EOF

echo ""
echo -e "${GREEN}=======================================${NC}"
echo -e "${GREEN} 설정 완료!${NC}"
echo -e "${GREEN}=======================================${NC}"
echo ""
echo -e "가상환경 활성화:"
echo -e "  ${BLUE}source .venv/bin/activate${NC}"
echo ""
echo -e "서비스 시작:"
echo -e "  ${BLUE}cd services/model && python main.py${NC}"
echo ""
echo -e "헬스 체크:"
echo -e "  ${BLUE}curl http://localhost:8002/api/health${NC}"
echo ""
