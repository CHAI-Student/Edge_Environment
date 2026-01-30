# Camera-Only Test Guide

> **최종 업데이트**: 2026-01-30

로드셀 없이 카메라만으로 상품 판단 시스템을 테스트하는 방법입니다.

## 필요 서비스

| 서비스 | 포트 | 필수 | 관리 레포 | 설명 |
|--------|------|------|-----------|------|
| Camera Driver | 8003 | O | **이 레포** | 카메라 스냅샷/녹화 |
| Model Service | 8002 | O | **이 레포** | AI 상품 판단 |
| Node.js Server | 8888 | 선택 | Edge_Environment | 오케스트레이터 |

> **참고**: Node.js 없이도 Model 서비스를 직접 호출하여 테스트할 수 있습니다.

## 빠른 시작

### 방법 1: PM2 통합 실행 (권장)

```bash
cd Edge_Environment

# Camera + Model 서비스 시작
npm run services

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
```

### 서비스 상태 확인

```bash
curl http://localhost:8003/api/health  # Camera
curl http://localhost:8002/api/health  # Model
```

## 테스트 실행

### Model 서비스 직접 호출 (Node.js 불필요)

```bash
# Vision-only 판단 (폴더 이미지 사용)
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 0,
    "vision_only": true,
    "media_paths": {
      "image_folder": "/data/snapshots/test_session"
    }
  }'
```

### Camera Driver + Model 연동

```bash
# 1. 스냅샷 캡처
curl -X POST http://localhost:8003/api/zone/0/snapshot \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test123", "include_top": true}'

# 2. 판단 요청
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 0,
    "vision_only": true,
    "media_paths": {
      "image_folder": "/data/snapshots/test123"
    }
  }'
```

### Node.js 경유 테스트 (다른 레포 실행 필요)

다른 레포(Edge_Environment)의 Node.js가 실행 중인 경우:

```bash
# Zone 0 카메라 테스트 (스냅샷)
curl -X POST http://localhost:8888/api/camera/test/snapshot-and-judge \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 0, "include_top": true}'

# 서비스 상태 확인
curl http://localhost:8888/api/camera/test/status
```

## API 엔드포인트

### Camera Driver (8003)

#### POST /api/zone/{id}/snapshot

**Request:**
```json
{
  "session_id": "260130153025",
  "include_top": true
}
```

**Response:**
```json
{
  "success": true,
  "zone_id": 0,
  "folder": "/data/snapshots/260130153025",
  "top_image": "cam_0/snapshot.jpg",
  "side_image": "cam_1/snapshot.jpg"
}
```

### Model Service (8002)

#### POST /api/judge (Vision-only)

**Request:**
```json
{
  "zone_id": 0,
  "vision_only": true,
  "media_paths": {
    "image_folder": "/data/snapshots/260130153025"
  }
}
```

**Response:**
```json
{
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
  "totalPrice": 1500
}
```

## 카메라 전용 모드 특징

| 항목 | 일반 모드 (로드셀+카메라) | 카메라 전용 모드 |
|------|-------------------------|-----------------|
| 개수 판단 | 무게 기반 정확 계산 | 1개 고정 |
| 신뢰도 | 높음 (0.6~0.95) | 낮음 (Vision × 0.7) |
| 판단 상태 | COMPLETE | PARTIAL |
| 무게 검증 | O | X |

## 주의사항

1. **개수 추정 불가**: 무게 데이터 없이는 개수를 1개로 고정
2. **신뢰도 감소**: Vision 신뢰도의 70%만 적용
3. **판단 상태**: 항상 `PARTIAL` (무게 미검증)

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

# PM2 로그 확인
pm2 logs model --lines 50
```

## Zone 매핑

| Zone | Side Camera | Top Camera |
|------|-------------|------------|
| 0 | cam_1 | cam_0 |
| 1 | cam_2 | cam_0 |
| 2 | cam_3 | cam_0 |
| 3 | cam_4 | cam_0 |
| 4 | cam_5 | cam_0 |

## PM2 명령어 요약

```bash
npm run services            # Camera + Model 시작
npm run services:stop       # 중지
pm2 logs                    # 로그 확인
pm2 status                  # 상태 확인
```
