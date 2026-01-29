# Camera-Only Test Guide

> **최종 업데이트**: 2026-01-29

로드셀 없이 카메라만으로 상품 판단 시스템을 테스트하는 방법입니다.

## 필요 서비스

카메라 전용 테스트를 위해 다음 서비스가 실행 중이어야 합니다:

| 서비스 | 포트 | 필수 | 설명 |
|--------|------|------|------|
| Camera Driver | 8003 | O | 카메라 스냅샷/녹화 |
| Model Service | 8002 | O | AI 상품 판단 |
| Node.js Server | 8888 | O | 오케스트레이터 |
| IO Board | 8000 | X | 불필요 (카메라 전용 모드) |

## 빠른 시작

### 방법 1: PM2 통합 실행 (권장)

```bash
cd Edge_Environment

# 전체 서비스 시작 (IO Board 포함)
npm start

# 또는 필요한 서비스만 시작
pm2 start ecosystem.config.js --only "orchestrator,model,camera-driver"

# 상태 확인
pm2 status
```

### 방법 2: 개별 터미널 실행

```bash
# 터미널 1: Camera Driver
cd Edge_Environment/services/camera_driver
python main.py

# 터미널 2: Model Service
cd Edge_Environment/services/model
python main.py

# 터미널 3: Node.js Server
cd Edge_Environment
npm run start:server
```

### 서비스 상태 확인

```bash
curl http://localhost:8888/api/camera/test/status
```

응답 예시:
```json
{
  "success": true,
  "mode": "camera_only_test",
  "services": {
    "camera_driver": { "healthy": true },
    "model_service": { "healthy": true }
  },
  "note": "Camera-only mode: loadcell not required"
}
```

### 테스트 실행

```bash
# Zone 0 카메라 테스트 (스냅샷)
curl -X POST http://localhost:8888/api/camera/test/snapshot-and-judge \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 0, "include_top": true}'

# Zone 0 카메라 테스트 (녹화 3초)
curl -X POST http://localhost:8888/api/camera/test/record-and-judge \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 0, "include_top": true, "duration_ms": 3000, "fps": 30, "top_k": 5}'
```

## API 엔드포인트

### POST /api/camera/test/snapshot-and-judge

카메라 스냅샷 촬영 후 Vision 전용 판단을 수행합니다.

**Request:**
```json
{
  "zone_id": 0,
  "include_top": true
}
```

**Response:**
```json
{
  "success": true,
  "mode": "camera_only",
  "zone_id": 0,
  "session_id": "260129153025",
  "snapshot": {
    "session_path": "/data/snapshots/260129153025",
    "images": {
      "cam_0": "/data/snapshots/260129153025/cam_0/snapshot.jpg",
      "cam_1": "/data/snapshots/260129153025/cam_1/snapshot.jpg"
    }
  },
  "judgment": {
    "success": true,
    "status": "partial",
    "confidence": 0.56,
    "products": [
      {
        "productId": 5,
        "name": "코카콜라 350ml",
        "count": 1,
        "unitPrice": 1500,
        "totalPrice": 1500,
        "confidence": 0.56
      }
    ],
    "totalPrice": 1500,
    "productCount": 1
  }
}
```

### POST /api/camera/test/record-and-judge

지정 시간 동안 연속 스냅샷 촬영 후 Vision 판단을 수행합니다. 로드셀 정합성 비교 전 후보군 도출에 사용합니다.

**Request:**
```json
{
  "zone_id": 0,
  "include_top": true,
  "duration_ms": 3000,
  "snapshot_interval_ms": 500
}
```

**Response:**
```json
{
  "success": true,
  "mode": "camera_only_recording",
  "zone_id": 0,
  "session_id": "20260129_214859",
  "recording": {
    "duration_ms": 3000,
    "snapshot_count": 6,
    "session_path": "/data/snapshots/20260129_214859"
  },
  "snapshots": [
    {
      "index": 0,
      "timestamp": 1769431740131,
      "images": {
        "cam_0": "/data/snapshots/.../cam_0/snapshot_000.jpg",
        "cam_1": "/data/snapshots/.../cam_1/snapshot_000.jpg"
      }
    }
  ],
  "judgment": {
    "success": true,
    "status": "partial",
    "products": [...]
  }
}
```

### POST /api/camera/test/judge-from-folder

이미 저장된 이미지로 판단을 테스트합니다.

**Request (폴더 경로):**
```json
{
  "zone_id": 0,
  "image_folder": "/data/snapshots/260129153025"
}
```

**Request (개별 이미지 경로):**
```json
{
  "zone_id": 0,
  "top_image": "/path/to/top.jpg",
  "side_image": "/path/to/side.jpg"
}
```

### GET /api/camera/test/status

카메라 테스트 모드 상태를 확인합니다.

## Python 스크립트

### 설치

```bash
pip install requests
```

### 사용법

```bash
# 기본 테스트 (Zone 0)
python scripts/test_camera_only.py

# Zone 지정
python scripts/test_camera_only.py --zone 1

# 서비스 상태만 확인
python scripts/test_camera_only.py --mode check

# 기존 이미지로 테스트
python scripts/test_camera_only.py --mode folder --folder /data/snapshots/260129153025

# Model 서비스 직접 테스트
python scripts/test_camera_only.py --mode direct --zone 0
```

### 전체 옵션

```
--mode      테스트 모드: nodejs (기본), direct, folder, check
--zone      Zone ID (0-4, 기본: 0)
--folder    이미지 폴더 경로 (folder 모드)
--top-image Top 카메라 이미지 경로
--side-image Side 카메라 이미지 경로
--no-top    Top 카메라 제외
```

## Windows 배치 파일

```cmd
# Zone 0 테스트
scripts\test_camera_only.bat 0

# Zone 1 테스트
scripts\test_camera_only.bat 1
```

## Model Service 직접 호출

Node.js 없이 Model 서비스를 직접 호출할 수도 있습니다.

```bash
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 0,
    "vision_only": true,
    "media_paths": {
      "image_folder": "/data/snapshots/260129153025"
    }
  }'
```

## 카메라 전용 모드 특징

| 항목 | 일반 모드 (로드셀+카메라) | 카메라 전용 모드 |
|------|-------------------------|-----------------|
| 개수 판단 | 무게 기반 정확 계산 | 1개 고정 |
| 신뢰도 | 높음 (0.6~0.95) | 낮음 (Vision × 0.7) |
| 판단 상태 | COMPLETE | PARTIAL |
| 무게 검증 | O | X |
| 다중 상품 | 지원 | 제한적 |

## 주의사항

1. **개수 추정 불가**: 무게 데이터 없이는 개수를 정확히 알 수 없어 1개로 고정됩니다.

2. **신뢰도 감소**: Vision 신뢰도의 70%만 적용됩니다.

3. **판단 상태**: 항상 `PARTIAL` (무게 미검증)로 반환됩니다.

4. **테스트 용도**: 프로덕션 환경에서는 로드셀과 함께 사용하는 것을 권장합니다.

## 트러블슈팅

### 카메라 연결 실패

```bash
# 카메라 상태 확인
curl http://localhost:8003/api/status

# 디바이스 스캔
curl http://localhost:8003/api/devices/scan

# PM2 로그 확인
pm2 logs camera-driver --lines 50
```

### Model 서비스 오류

```bash
# 헬스 체크
curl http://localhost:8002/api/health

# 상품 목록 확인 (모델 로드 확인)
curl http://localhost:8002/api/products

# PM2 로그 확인
pm2 logs model --lines 50
```

### 이미지 경로 오류

- 이미지 경로는 절대 경로 사용 권장
- Windows에서는 백슬래시(`\`) 대신 슬래시(`/`) 사용
- 경로에 한글이 포함된 경우 인코딩 문제 확인

### Node.js 서버 오류

```bash
# 헬스 체크
curl http://localhost:8888/health

# PM2 로그 확인
pm2 logs orchestrator --lines 50
```

## Zone 매핑

| Zone | Side Camera | Top Camera | 로드셀 채널 |
|------|-------------|------------|-------------|
| 0 | cam_1 | cam_0 | [0, 1] |
| 1 | cam_2 | cam_0 | [2, 3] |
| 2 | cam_3 | cam_0 | [4, 5] |
| 3 | cam_4 | cam_0 | [6, 7] |
| 4 | cam_5 | cam_0 | [8, 9] |

## PM2 명령어 요약

```bash
# 서비스 시작
npm start                                    # 전체
pm2 start ecosystem.config.js --only model   # 개별

# 상태 확인
pm2 status
pm2 logs

# 서비스 제어
pm2 restart model
pm2 stop camera-driver
pm2 delete all
```
