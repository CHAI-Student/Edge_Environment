# Edge Environment Lite

> **최종 업데이트**: 2026-01-30

Camera Driver + Model 서비스 (경량화 버전) - CHAI Smart Vending System

## 개요

이 레포는 AI 스마트 자판기 시스템의 **Camera Driver**와 **Model** 서비스만 관리합니다.

**다른 서비스 관리 위치:**
- Node.js, IO Board, MQTT → [Edge_Environment](../Edge_Environment)
- Payment → [CRK-PAYMENT](../CRK-PAYMENT)
- IO Board → [CRK-IO-BOARD](../CRK-IO-BOARD)

## 서비스 포트

| 서비스 | 포트 | 설명 | 관리 |
|--------|------|------|------|
| Model | 8002 | YOLO 추론 + 상품 판단 | 이 레포 |
| Camera Driver | 8003 | 카메라 스냅샷/녹화 | 이 레포 |
| React Client | 3000 | 웹 대시보드 | 이 레포 |
| Node.js | 8888 | 오케스트레이터 | 다른 레포 |
| IO Board | 8000 | 로드셀 + 데드볼트 | 다른 레포 |

## 빠른 시작

```bash
# 의존성 설치
pip install -e ".[ai,dev]"
npm install

# Camera Driver + Model 실행
npm run services

# React Client 실행 (다른 레포의 Node.js 8888과 연동)
npm run client

# 전체 실행
npm run all
```

## PM2 명령어

```bash
npm run services       # camera-driver + model
npm run client         # React client
npm run all            # 전체
npm run stop           # 중지
npm run logs           # 로그
npm run status         # 상태
```

## 프로젝트 구조

```
Edge_Environment/
├── services/
│   ├── camera_driver/     # 카메라 서비스 (8003)
│   └── model/             # AI 판단 서비스 (8002)
├── client/                # React 대시보드 (3000)
├── config/                # Zone/카메라 매핑
├── _archive/              # 아카이빙 (다른 레포로 이관)
└── ecosystem.config.js    # PM2 설정
```

## 테스트

```bash
# 헬스 체크
curl http://localhost:8002/api/health  # Model
curl http://localhost:8003/api/health  # Camera

# 상품 판단
curl -X POST http://localhost:8002/api/judge \
  -H "Content-Type: application/json" \
  -d '{"zone_id": 0, "delta_weight": -520}'

# 스냅샷
curl -X POST http://localhost:8003/api/zone/0/snapshot \
  -d '{"session_id": "test123"}'
```

## Commit Message Convention

| Type | Description |
|------|-------------|
| feat | 새로운 기능 |
| fix | 버그 수정 |
| add | 기존 기능 수정 |
| docs | 문서 수정 |
| refactor | 코드 리팩토링 |
| test | 테스트 코드 |

---

자세한 내용은 [CLAUDE.md](./CLAUDE.md) 참조
