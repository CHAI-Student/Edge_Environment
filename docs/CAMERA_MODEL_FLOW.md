# Camera → Model 데이터 흐름 가이드

> **최종 업데이트**: 2026-01-30

카메라에서 모델이 결과를 내는 구조를 설명합니다. 다른 개발자가 카메라 로직을 구현할 때 참고하세요.

---

## 1. 전체 타임라인

```
[무게 변화 이벤트 발생] → [3초간 촬영] → [Model 판단 요청]
        ↑                    ↑                    ↑
   IO Board SSE         Camera Driver          Model Service
   (다른 레포)           (이 레포, 8003)        (이 레포, 8002)
```

---

## 2. Camera Driver - 3초 촬영 로직

### 설정 값 (event_recording_manager.py)

```python
_timed_capture_duration = 3.0  # 3초
_timed_capture_interval = 0.1  # 0.1초 간격 (10fps, 약 30장)
```

### 촬영 흐름

1. `on_weight_change()` 이벤트 수신 시 `_timed_capture()` 시작
2. 3초 동안 0.1초 간격으로 Top + Side 카메라 프레임 캡처
3. 이미지 저장: `frame_0001.jpg`, `frame_0002.jpg`, ... (약 30장)
4. Side 카메라 영상도 동시 녹화 (mp4)
5. 완료 후 Model 서비스에 판단 요청

### 코드 위치

- `services/camera_driver/src/core/event_recording_manager.py`
- `_timed_capture()` 메서드 (line 348~)

---

## 3. 저장 구조 (중요)

```
Edge_Environment/
└── {YYYYMMDD_HHMMSS}/         # 세션 폴더 (예: 20260130_141029)
    ├── images/
    │   ├── cam_0/             # Top 카메라 (cam0)
    │   │   ├── frame_0001.jpg
    │   │   ├── frame_0002.jpg
    │   │   └── ...            # 약 30장
    │   └── cam_1/             # Side 카메라 (Zone 0 = cam1)
    │       ├── frame_0001.jpg
    │       ├── frame_0002.jpg
    │       └── ...
    └── videos/
        └── cam_1/recording.mp4  # Side 영상
```

### 카메라 매핑

| Zone | Top Camera | Side Camera | LoadCell Channels |
|------|------------|-------------|-------------------|
| 0 | cam_0 | cam_1 | [0, 1] |
| 1 | cam_0 | cam_2 | [2, 3] |
| 2 | cam_0 | cam_3 | [4, 5] |
| 3 | cam_0 | cam_4 | [6, 7] |
| 4 | cam_0 | cam_5 | [8, 9] |

---

## 4. Model 서비스 입력 형식

### POST /api/judge 요청

```json
{
  "zone_id": 0,
  "weight_data": {
    "before_weights": [1000, 1005, 0, 0, 0, 0, 0, 0, 0, 0],
    "after_weights": [480, 505, 0, 0, 0, 0, 0, 0, 0, 0],
    "delta_weight": -520,
    "channels": [0, 1]
  },
  "media_paths": {
    "image_folder": "/path/to/20260130_141029/images"
  },
  "timestamp": 1737897025.123
}
```

### 필드 설명

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| zone_id | int | O | Zone ID (0-4) |
| weight_data | object | △ | 무게 데이터 (vision_only=false일 때 필요) |
| weight_data.before_weights | float[] | O | 변화 전 10채널 무게 (g) |
| weight_data.after_weights | float[] | O | 변화 후 10채널 무게 (g) |
| weight_data.delta_weight | float | O | Zone별 총 무게 변화량 (g) |
| weight_data.channels | int[] | O | 변화 감지된 채널 인덱스 |
| media_paths | object | O | 이미지 경로 |
| media_paths.image_folder | string | O | 이미지 폴더 경로 |
| timestamp | float | △ | 이벤트 타임스탬프 |
| vision_only | bool | △ | Vision 전용 모드 (기본값: false) |

---

## 5. Model이 이미지를 찾는 방식

Model 서비스는 `image_folder`에서 자동으로 이미지를 탐색합니다.

### 탐색 로직 (routes.py:686-714)

```python
# 모든 카메라 폴더 탐색 (cam0 ~ cam5)
for cam_id in range(6):
    # 폴더 이름 형식 지원: cam0 또는 cam_0
    cam_names = [f"cam{cam_id}", f"cam_{cam_id}"]

    # 연속 프레임 탐색 (Motion Tracking용)
    frame_files = sorted([
        f for f in os.listdir(cam_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    ])

    # 또는 단일 스냅샷 탐색
    # snapshot.jpg, frame.jpg, capture.jpg
```

### 지원하는 파일 형식

1. **연속 프레임** (권장, Motion Tracking 지원)
   - `frame_0001.jpg`, `frame_0002.jpg`, ...
   - 파일명이 정렬 가능해야 함

2. **단일 스냅샷**
   - `snapshot.jpg`
   - `frame.jpg`
   - `capture.jpg`

---

## 6. Motion Tracking (연속 프레임 처리)

연속 프레임이 있으면 Model은 자동으로 Motion Tracking을 수행합니다.

### 동작 방식

1. 모든 프레임을 순차 처리
2. 프레임 간 객체 위치 변화 추적
3. 손 근접 영역에서 움직임 있는 객체에 보너스 부여
4. 최종 신뢰도 향상

### 설정 값 (config.py)

```python
use_motion_tracking = True
max_motion_bonus = 0.15      # 최대 보너스
min_motion_correlation = 0.3  # 최소 상관도
motion_lookback_frames = 5    # 히스토리 프레임 수
```

---

## 7. Vision Only 모드 (카메라만 사용)

`weight_data` 없이 `media_paths`만 전달하면 자동으로 Vision Only 모드가 됩니다.

### 요청 예시

```json
{
  "zone_id": 0,
  "vision_only": true,
  "media_paths": {
    "image_folder": "/path/to/images"
  }
}
```

### 주의사항

| 항목 | 일반 모드 | Vision Only 모드 |
|------|----------|-----------------|
| 개수 판단 | 무게 기반 정확 계산 | **1개 고정** |
| 신뢰도 | 높음 (0.6~0.95) | **낮음 (Vision × 0.7)** |
| 판단 상태 | COMPLETE | **PARTIAL** |
| 무게 검증 | O | X |

---

## 8. 카메라 개발자 체크리스트

### 필수 구현 사항

- [ ] **폴더 구조 준수**
  - `{session_id}/images/cam_{N}/` 형식
  - cam_0 = Top 카메라
  - cam_1~5 = Side 카메라 (Zone 0~4)

- [ ] **파일명 규칙**
  - 연속 프레임: `frame_NNNN.jpg` (4자리 숫자, 정렬 가능)
  - 단일 스냅샷: `snapshot.jpg`

- [ ] **촬영 설정**
  - 3초 동안 0.1초 간격 (약 30장)
  - JPEG 품질 90 (`cv2.IMWRITE_JPEG_QUALITY, 90`)

- [ ] **Model 호출 시점**
  - 3초 촬영 완료 후 `POST /api/judge` 호출
  - `image_folder` 경로에 `/images` 디렉토리까지 포함

### 테스트 방법

```bash
# 1. Camera Driver 시작
cd services/camera_driver && python main.py

# 2. Model 서비스 시작
cd services/model && python main.py

# 3. 판단 테스트
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{
    "zone_id": 0,
    "vision_only": true,
    "media_paths": {
      "image_folder": "./test_images"
    }
  }'
```

---

## 9. API 응답 형식

### 성공 응답

```json
{
  "success": true,
  "status": "complete",
  "confidence": 0.85,
  "products": [
    {
      "productId": 5,
      "name": "코카콜라 350ml",
      "count": 1,
      "unitPrice": 1500,
      "totalPrice": 1500,
      "confidence": 0.85
    }
  ],
  "totalPrice": 1500,
  "productCount": 1,
  "isRemoval": true,
  "weightInfo": {
    "delta": -520.0,
    "explained": -520.0,
    "residual": 0.0
  },
  "timestamp": 1737897025.123,
  "inference_id": "inf_1737897025123_abc12345"
}
```

### 상태 코드

| status | 설명 |
|--------|------|
| complete | 완전한 판단 (무게+비전 일치) |
| partial | 부분 판단 (무게 미검증) |
| uncertain | 불확실 (신뢰도 낮음) |
| no_detection | 감지 실패 |
| cancelled | 추론 취소됨 |

---

## 10. 트러블슈팅

### 이미지를 찾을 수 없음

```
WARNING: No valid images found in media_paths
```

**원인:** `image_folder` 경로가 잘못되었거나 파일명 형식이 맞지 않음

**해결:**
1. 폴더 경로 확인 (`/images` 포함 여부)
2. 카메라 폴더명 확인 (`cam_0` 또는 `cam0`)
3. 파일명 형식 확인 (`frame_NNNN.jpg`)

### Motion Tracking이 동작하지 않음

**원인:** 연속 프레임이 1장뿐임

**해결:** 최소 2장 이상의 연속 프레임 저장

### 신뢰도가 너무 낮음

**원인:** 손이 상품을 가리고 있음

**해결:** 손이 빠진 후 프레임 캡처 (3초 버퍼의 목적)

---

## 관련 문서

- [CAMERA_ONLY_TEST.md](CAMERA_ONLY_TEST.md) - 카메라 전용 테스트
- [TESTING_GUIDE.md](TESTING_GUIDE.md) - Windows 테스트 가이드
- [Jetson_Nano_Testing_Guide.md](Jetson_Nano_Testing_Guide.md) - Jetson 테스트 가이드
