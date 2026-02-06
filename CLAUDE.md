# Edge Environment Lite - Model 서비스

AI 스마트 자판기 시스템의 Model 서비스 (v5.4)
**Jetson Orin Nano 4GB (JetPack 6.2) TensorRT 전용**

> **최종 업데이트**: 2026-02-06 | **버전**: 5.4.0

## 개요

이 레포는 **Model** 서비스만 관리합니다.
**TensorRT 엔진(.engine)** 전용, **CUDA 필수**.
Node.js, IO Board, Payment, Camera Driver, Dashboard는 별도 레포에서 관리됩니다.

## 최신 변경사항

### v5.4 (최신)
- 프로젝트 구조 마이그레이션: `src/` -> `model_service/`
- Entry Point 변경: `uv run model-service`

### v5.3
- Async Streaming Video Processing: Top/Side I/O 병렬화
- Feature Flag: `MODEL__ASYNC_STREAMING__ENABLED`
- 처리 시간 20-30% 개선 (12-20초 -> 8-14초/트리거)

### v5.0-5.2
- StrictWeightMatcher: 무게 우선 엄격 매칭
- Cross-zone return logic 개선
- Deduplication 캐시 크기 제한

> 전체 변경 이력: [CHANGELOG_v4.8.md](./CHANGELOG_v4.8.md)

## 아키텍처

```
다른 레포                              이 레포
┌─────────────────────────┐          ┌─────────────────────────┐
│ Node.js (8888) - 폴링   │          │ Model Service (8002)    │
├─────────────────────────┤          │ - SessionStore          │
│ Camera (8003)           │────────► │ - DoorSessionStore      │
│ - POST /trigger         │          │ - YOLO TensorRT 추론    │
├─────────────────────────┤          └─────────────────────────┘
│ IO Board (8000)         │
│ Dashboard (3000)        │  ← dashboard/ 레포
└─────────────────────────┘
```

## 서비스 포트

| 서비스 | 포트 | 관리 위치 |
|--------|------|-----------|
| Model | 8002 | **이 레포** |
| Dashboard | 3000 | dashboard/ 레포 |
| Node.js | 8888 | 다른 레포 |
| Camera | 8003 | 다른 레포 |
| IO Board | 8000 | CRK-IO-BOARD |
| Payment | 5000 | CRK-PAYMENT |

## 빠른 시작

```bash
cd Edge_Environment

# 1. 환경 설정 (최초 1회)
./scripts/setup_jetson.sh

# 2. 가상환경 활성화
source .venv/bin/activate

# 3. Model 서비스 시작
uv run model-service
```

## 프로젝트 구조

```
Edge_Environment/
├── services/model/           # AI 판단 서비스 (8002)
│   ├── model_service/        # 소스 코드 (v5.4)
│   │   ├── main.py           # Entry point
│   │   ├── api/routes/       # API 라우터
│   │   ├── service/          # 비즈니스 로직
│   │   ├── session/          # 세션 저장소
│   │   ├── video/            # 비디오 처리, Async Streaming (v5.3)
│   │   ├── vision/           # YOLO TensorRT 추론
│   │   ├── weight/           # 무게 계산
│   │   ├── engine/           # 판단 엔진
│   │   └── core/             # 설정 (config.py)
│   └── tests/                # 테스트 (130+)
├── data/sessions/            # Door Session YAML 영속화
├── logs/                     # 로그
├── models/                   # TensorRT 엔진 (.engine)
├── scripts/                  # 설정 스크립트
├── docs/                     # 상세 문서
│   ├── JETSON_SETUP.md       # Jetson 설치 가이드
│   └── REFERENCE.md          # API 상세 스펙
└── pyproject.toml
```

## API 요약

### 핵심 API

| API | 설명 |
|-----|------|
| `GET /api/health` | 헬스 체크 |
| `POST /trigger` | Camera에서 호출, YOLO 추론 실행 |
| `POST /api/judge/multi-zone` | Node.js 10초 폴링, 판단 결과 |
| `GET /api/judge/door-sessions/stats` | Door Session 통계 |
| `POST /api/judge/door-session/{zone}/finalize` | 강제 종료 |

### 빠른 테스트

```bash
# 헬스 체크
curl http://localhost:8002/api/health

# Trigger
curl -X POST http://localhost:8002/trigger \
  -H "Content-Type: application/json" \
  -d '{"zone": 1, "videos": {"top": "/path/top.avi", "side": "/path/side.avi"}, "loadcells": []}'

# 판단 결과 폴링
curl -X POST http://localhost:8002/api/judge/multi-zone \
  -H "Content-Type: application/json" \
  -d '{"zone": 1}'
```

> API 상세: [docs/REFERENCE.md](./docs/REFERENCE.md)

## 환경 변수

### 필수 설정

| 변수 | 기본값 | 설명 |
|------|--------|------|
| MODEL__API__PORT | 8002 | 서버 포트 |
| MODEL__VISION__YOLO_MODEL_PATH | models/siyeon_best.engine | TensorRT 엔진 |
| MODEL__BUFFER__TTL_SECONDS | 300 | 세션 TTL (초) |

### Async Streaming (v5.3)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| MODEL__ASYNC_STREAMING__ENABLED | true | Async 모드 활성화 |
| MODEL__ASYNC_STREAMING__FRAME_QUEUE_SIZE | 10 | 프레임 큐 크기 |

### Weight (v5.1)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| MODEL__WEIGHT__TOLERANCE_GRAMS | 3.0 | 무게 허용 오차 (g) |
| MODEL__WEIGHT__STRICT_MODE | true | 엄격 무게 검증 |

> 전체 환경변수: `.env.example` 참조

## 요구사항

| 항목 | 버전 |
|------|------|
| 하드웨어 | Jetson Orin Nano 4GB |
| OS | JetPack 6.2 (Ubuntu 22.04) |
| Python | 3.10.x |
| CUDA | 12.x (JetPack 포함) |
| TensorRT | 10.x (JetPack 포함) |
| NumPy | **< 2.0** (필수) |

> 상세 설치 가이드: [docs/JETSON_SETUP.md](./docs/JETSON_SETUP.md)

## Jetson 4GB 최적화

| 항목 | 설정 | 효과 |
|------|------|------|
| 입력 크기 | 480x480 | 메모리 44% 감소 |
| FP16 추론 | half=True | 메모리 50% 감소 |
| 최대 탐지 | max_det=20 | 후처리 부하 감소 |
| Async Streaming | Top/Side I/O 병렬화 | 처리 시간 30% 감소 |

## 테스트 실행

```bash
# 전체 테스트 (130+)
uv run pytest services/model/tests -v

# 특정 테스트
uv run pytest services/model/tests/test_async_streaming.py -v
uv run pytest services/model/tests/test_door_session_store.py -v
```

## 데이터 흐름

```
1. Camera Driver → AVI 녹화 완료
2. Camera → Model (POST /trigger + videos + loadcells)
3. Model: YOLO TensorRT 추론 → VotingEnsemble → DoorSessionStore
4. (반복) 추가 trigger → 같은 Door Session에 통합
5. Node.js → Model (POST /api/judge/multi-zone) 10초 간격 폴링
6. Model: DoorSession 타임아웃 → 완료 시 결과 응답
```

## 관련 레포 위치

| 레포 | 경로 |
|------|------|
| 현위치 | `~\VOICE\2026\crk\win_pc_test_sw2io_board\Edge_Environment` |
| Dashboard | `~\VOICE\2026\crk\dashboard` |
| Camera | `~\VOICE\2026\crk\CRK-CAMERA` |
| IO Board | `~\VOICE\2026\crk\CRK-IO-BOARD` |
| Payment | `~\VOICE\2026\crk\CRK-PAYMENT` |
| Node.js | `~\VOICE\2026\crk\Edge_Environment` |

## 문서 참조

- [README.md](./README.md) - 빠른 시작 가이드
- [docs/JETSON_SETUP.md](./docs/JETSON_SETUP.md) - Jetson 상세 설치 가이드
- [docs/REFERENCE.md](./docs/REFERENCE.md) - API 상세 스펙
- [CHANGELOG_v4.8.md](./CHANGELOG_v4.8.md) - 전체 변경 이력
