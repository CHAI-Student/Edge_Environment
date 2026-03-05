#!/bin/bash
# TensorRT Engine 변환 스크립트
#
# .pt → .engine (TensorRT FP16) 변환
# Jetson Orin Nano에서 실행 (GPU 필수)
#
# 환경변수:
#   PT_FILE  - 변환할 .pt 파일명 (기본: siyeon_best.pt)
#   IMGSZ    - 입력 이미지 크기 (기본: 480)

set -e

PT_FILE="${PT_FILE:-siyeon_best.pt}"
IMGSZ="${IMGSZ:-480}"
INPUT_PATH="/models/${PT_FILE}"

echo "=========================================="
echo " TensorRT Engine 변환"
echo "=========================================="
echo " PT 파일:   ${INPUT_PATH}"
echo " 이미지 크기: ${IMGSZ}x${IMGSZ}"
echo " FP16:      enabled"
echo "=========================================="

# 1. 파일 존재 확인
if [ ! -f "${INPUT_PATH}" ]; then
    echo "ERROR: ${INPUT_PATH} 파일을 찾을 수 없습니다."
    echo "models/ 디렉토리에 .pt 파일이 있는지 확인하세요."
    ls -la /models/ 2>/dev/null || echo "  /models/ 디렉토리가 비어있거나 마운트되지 않았습니다."
    exit 1
fi

echo ""
echo "입력 파일 크기: $(du -h "${INPUT_PATH}" | cut -f1)"
echo ""

# 2. YOLO export (TensorRT FP16)
echo "변환 시작..."
yolo export model="${INPUT_PATH}" format=engine half=True imgsz="${IMGSZ}" device=0

# 3. 결과 확인
ENGINE_FILE="${INPUT_PATH%.pt}.engine"

if [ -f "${ENGINE_FILE}" ]; then
    echo ""
    echo "=========================================="
    echo " 변환 완료!"
    echo "=========================================="
    echo " 출력 파일: ${ENGINE_FILE}"
    echo " 파일 크기: $(du -h "${ENGINE_FILE}" | cut -f1)"
    echo "=========================================="
else
    echo "ERROR: .engine 파일이 생성되지 않았습니다."
    echo "예상 경로: ${ENGINE_FILE}"
    ls -la /models/ 2>/dev/null
    exit 1
fi
