# Edge Environment Lite - Model Service

> **최종 업데이트**: 2026-02-06 | **버전**: 5.4.0

AI 스마트 자판기 시스템의 **Model** 서비스 (Jetson Orin Nano 4GB TensorRT 전용)

## 개요

이 레포는 **Model** 서비스만 관리합니다.
**TensorRT 엔진(.engine)** 파일만 지원하며, **CUDA가 필수**입니다.

**최신 기능 (v5.3-5.4):**
- v5.4: 프로젝트 구조 마이그레이션 (`src/` -> `model_service/`)
- v5.4: Entry Point 변경 (`uv run model-service`)
- v5.3: Async Streaming Video Processing (처리 시간 20-30% 개선)

**다른 서비스 관리 위치:**
- Dashboard → `~\VOICE\2026\crk\dashboard`
- Node.js, Camera Driver → 다른 레포
- IO Board → CRK-IO-BOARD
- Payment → CRK-PAYMENT

## 서비스 포트

| 서비스 | 포트 | 관리 위치 |
|--------|------|-----------|
| Model | 8002 | **이 레포** |
| Dashboard | 3000 | dashboard/ 레포 |
| Node.js | 8888 | 다른 레포 |
| Camera Driver | 8003 | 다른 레포 |
| IO Board | 8000 | 다른 레포 |

## 빠른 시작 (Jetson Orin Nano)

```bash
# 1. uv 환경 설정 (시스템 패키지 사용 필수!)
uv venv --system-site-packages --python python3.10 .venv
source .venv/bin/activate

# 2. 의존성 설치
uv pip install -e ".[dev]"

# 3. TensorRT 엔진 준비 (.pt -> .engine 변환은 Jetson에서만 가능)
yolo export model=models/siyeon_best.pt format=engine device=0 half=True imgsz=480

# 4. Model 서비스 실행
uv run model-service
```

## 프로젝트 구조

```
Edge_Environment/
├── services/model/           # AI 판단 서비스 (8002)
│   ├── Dockerfile            # Model Service container
│   ├── model_service/        # 소스 코드 (v5.4)
│   │   ├── main.py           # Entry point
│   │   ├── api/routes/       # API 라우터
│   │   ├── service/          # 비즈니스 로직
│   │   ├── session/          # 세션 저장소
│   │   ├── video/            # 비디오 처리
│   │   ├── vision/           # YOLO 추론
│   │   └── core/             # 설정
│   └── tests/                # 테스트 코드 (19개 파일, 225+ 테스트)
├── docker/convert/           # TensorRT convert container
│   └── Dockerfile
├── data/sessions/            # Door Session YAML 영속화
├── logs/                     # 로그 (judgment, system, weight)
├── models/                   # TensorRT 엔진 파일
├── scripts/                  # convert_engine.sh 등
├── docs/                     # 상세 문서
├── docker-compose.yml        # 2-container orchestration
├── .env.docker               # Docker env var template
├── .dockerignore             # Docker build exclusions
└── pyproject.toml            # Python 프로젝트 설정
```

## Docker 실행

```bash
# Model Service 시작
docker compose up -d model

# 로그 확인
docker compose logs -f model

# TensorRT 엔진 변환 (일회성, .pt → .engine)
docker compose --profile convert run --rm convert
```

## API 테스트

```bash
# 헬스 체크
curl http://localhost:8002/api/health

# Trigger (Camera에서 호출)
curl -X POST http://localhost:8002/trigger \
  -H "Content-Type: application/json" \
  -d '{"zone": 1, "videos": {"top": "/path/top.avi", "side": "/path/side.avi"}, "loadcells": []}'

# 판단 결과 폴링 (Node.js에서 호출)
curl -X POST http://localhost:8002/api/judge/multi-zone \
  -H "Content-Type: application/json" \
  -d '{"zone": 1}'
```

## 요구사항

- **하드웨어**: Jetson Orin Nano Developer Kit (4GB)
- **OS**: JetPack 6.2 (Ubuntu 22.04)
- **Python**: 3.10.x, **NumPy**: < 2.0 (필수)
- **CUDA**: 12.x, **TensorRT**: 10.x (JetPack 포함)

## 테스트 실행

```bash
# 전체 테스트 실행
uv run pytest services/model/tests -v

# 특정 테스트 파일
uv run pytest services/model/tests/test_door_session_store.py -v
```

---

자세한 내용은 [CLAUDE.md](./CLAUDE.md) 및 [docs/](./docs/) 참조
