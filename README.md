# Edge Environment Lite - Model Service

> **최종 업데이트**: 2026-02-02 | **버전**: 4.2.0

AI 스마트 자판기 시스템의 **Model** 서비스 (Jetson Orin Nano 4GB TensorRT 전용)

## 개요

이 레포는 **Model** 서비스만 관리합니다.
**TensorRT 엔진(.engine)** 파일만 지원하며, **CUDA가 필수**입니다.

**v4.2 신규 기능:**
- Service Layer: Controller-Service 패턴으로 비즈니스 로직 분리
- Docker 지원: Jetson Orin Nano 4GB 최적화 컨테이너 (메모리 3G 제한)
- Config 통합: 설정 파일 일원화 (`core.config`)
- TTL 자동 정리: 백그라운드 태스크로 좀비 세션 정리

**v4.1 기능:**
- Door Session: 문 열림~닫힘 동안 여러 trigger 통합 관리
- 반환 처리: 무게 증가 시 해당 상품 차감
- YAML 영속화: 서비스 재시작 시 세션 복구

**다른 서비스 관리 위치:**
- Node.js, Camera Driver, IO Board, MQTT → 다른 레포
- Payment → CRK-PAYMENT
- IO Board → CRK-IO-BOARD

## 서비스 포트

| 서비스 | 포트 | 설명 | 관리 |
|--------|------|------|------|
| Model | 8002 | YOLO 추론 + 상품 판단 | **이 레포** |
| React Client | 3000 | 웹 대시보드 | **이 레포** |
| Node.js | 8888 | 오케스트레이터 | 다른 레포 |
| Camera Driver | 8003 | 카메라 | 다른 레포 |
| IO Board | 8000 | 로드셀 + 데드볼트 | 다른 레포 |

## 빠른 시작 (Jetson Orin Nano)

```bash
# 1. Python 환경 설정 (시스템 패키지 사용 필수!)
python3 -m venv --system-site-packages .venv
source .venv/bin/activate

# 2. 의존성 설치
pip install -e ".[ai]"

# 3. TensorRT 엔진 준비 (.pt → .engine 변환은 Jetson에서만 가능)
yolo export model=models/siyeon_best.pt format=engine device=0 half=True imgsz=480

# 4. Model 서비스 실행
cd services/model && python main.py
```

## 프로젝트 구조

```
Edge_Environment/
├── services/
│   └── model/             # AI 판단 서비스 (8002)
│       ├── main.py        # PM2 호환 진입점
│       ├── Dockerfile     # Docker 빌드 (v4.2)
│       ├── docker-compose.yml  # Docker Compose
│       └── src/
│           ├── api/       # API 라우터
│           ├── service/   # 비즈니스 로직 (v4.2)
│           ├── session/   # 세션 저장소
│           ├── vision/    # YOLO 추론
│           └── core/      # 설정 (통합됨)
├── models/                # TensorRT 엔진 파일
├── config/                # YOLO 클래스 매핑
├── client/                # React 대시보드 (3000)
└── pyproject.toml         # Python 프로젝트 설정
```

## Docker 실행 (v4.2)

```bash
cd services/model

# 환경변수 설정
cp .env.docker .env

# Docker Compose로 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f model

# 중지
docker-compose down
```

## API 테스트

```bash
# 헬스 체크
curl http://localhost:8002/api/health

# AVI 기반 트리거 (Camera에서 호출)
curl -X POST http://localhost:8002/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "zone": 1,
    "videos": {"top": "/data/videos/top.avi", "side": "/data/videos/side.avi"},
    "loadcells": []
  }'

# 판단 결과 폴링 (Node.js에서 호출)
curl -X POST http://localhost:8002/api/judge/multi-zone \
  -H "Content-Type: application/json" \
  -d '{"session_id": "zone_1_260201_143025"}'
```

## Jetson Orin Nano 4GB 최적화

| 항목 | 설정 | 효과 |
|------|------|------|
| 입력 크기 | 480x480 | 메모리 44% 감소 |
| FP16 추론 | `half=True` | 메모리 50% 감소 |
| 최대 탐지 | 20개 | 후처리 부하 감소 |
| 배치 크기 | 1 (고정) | 메모리 제약 |

## 요구사항

- **하드웨어**: Jetson Orin Nano Developer Kit (4GB)
- **OS**: JetPack 6.2 (Ubuntu 22.04)
- **Python**: 3.10.x
- **CUDA**: 12.x (JetPack 포함)
- **TensorRT**: 10.x (JetPack 포함)

## 테스트 실행

```bash
# 전체 테스트 실행 (116 테스트)
pytest services/model/tests -v

# 특정 모듈 테스트
pytest services/model/tests/test_door_session_store.py -v
pytest services/model/tests/test_product_aggregator.py -v
```

---

자세한 내용은 [CLAUDE.md](./CLAUDE.md) 및 [설치 가이드](./docs/JETSON_SETUP.md) 참조
