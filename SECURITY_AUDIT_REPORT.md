# Edge Environment 보안 및 코드 품질 감사 보고서

> **감사일**: 2026-01-22
> **대상**: Edge_Environment 전체 코드베이스
> **브랜치**: minkyu

---

## 목차
1. [요약](#1-요약)
2. [보안 취약점](#2-보안-취약점)
3. [코드 품질 이슈](#3-코드-품질-이슈)
4. [권장 조치사항](#4-권장-조치사항)

---

## 1. 요약

### 발견된 이슈 통계

| 카테고리 | Critical | High | Medium | Low |
|----------|----------|------|--------|-----|
| 보안 취약점 | 6 | 3 | 5 | 1 |
| 코드 품질 | 1 | 2 | 6 | 4 |

### 즉시 조치 필요 항목
1. 모든 API 엔드포인트 인증 부재
2. HTTP 평문 통신 (HTTPS 미사용)
3. Path Traversal 취약점
4. 0.0.0.0 바인딩 (모든 인터페이스 공개)
5. card_terminal 모듈 import 오류

---

## 2. 보안 취약점

### 2.1 CRITICAL: 인증 메커니즘 부재

**영향 범위**: 모든 FastAPI 서비스

| 서비스 | 포트 | 영향받는 엔드포인트 |
|--------|------|-------------------|
| model | 8002 | /api/judge, /api/products, /api/stats |
| io_board | 8001 | /sse, /loadcells, /deadbolt |
| camera_driver | 8003 | /frame/*, /stream/* |
| mqtt_client | 8006 | /health |
| card_terminal | 5000 | 결제 API |

**문제**:
- JWT, API Key, Bearer Token 검증 없음
- 누구나 상품 판단, 카메라 접근, 데드볼트 제어 가능

**권장 조치**:
```python
# FastAPI Depends() 기반 인증 추가
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key

@router.get("/api/judge")
async def judge(api_key: str = Depends(verify_api_key)):
    ...
```

---

### 2.2 CRITICAL: HTTPS 미사용

**영향 범위**: 모든 서비스 간 통신

**문제**:
- 모든 HTTP 통신이 평문(plaintext)
- 중간자 공격(MITM) 취약
- 로드셀 데이터, 카메라 이미지, 결제 정보 암호화 없음

**권장 조치**:
```python
# uvicorn SSL 설정
uvicorn.run(
    app,
    host="0.0.0.0",
    port=8002,
    ssl_keyfile="./key.pem",
    ssl_certfile="./cert.pem"
)
```

---

### 2.3 CRITICAL: Path Traversal 취약점

**위치**: `services/model/config.py` (L150, L163-166)

**취약 코드**:
```python
def get_snapshot_folder(session_id: str) -> str:
    return os.path.join(config.snapshot_base_path, session_id)
```

**공격 시나리오**:
```
GET /api/judge?session_id=../../etc/passwd
→ 임의 파일 시스템 접근 가능
```

**권장 조치**:
```python
import re

def validate_session_id(session_id: str) -> bool:
    # 숫자와 언더스코어만 허용
    return bool(re.match(r'^[0-9_]+$', session_id))

def get_snapshot_folder(session_id: str) -> str:
    if not validate_session_id(session_id):
        raise ValueError(f"Invalid session_id: {session_id}")
    return os.path.join(config.snapshot_base_path, session_id)
```

---

### 2.4 CRITICAL: 0.0.0.0 바인딩

**위치**: 모든 서비스 `config.py`

**문제**:
- 기본 호스트가 `0.0.0.0` (모든 네트워크 인터페이스)
- 외부 네트워크에서 직접 접근 가능

**권장 조치**:
```python
# 개발 환경: localhost만
host = os.getenv("API_HOST", "127.0.0.1")

# 프로덕션: 방화벽 + 리버스 프록시 뒤에서만 0.0.0.0
```

---

### 2.5 CRITICAL: MQTT 인증 미흡

**위치**: `services/mqtt_client/config.py` (L15-16)

**문제**:
```python
mqtt_client_username: str | None = None
mqtt_client_password: str | None = None
```
- 선택적 인증 (None 허용)
- 재고 및 판매 데이터 보호 안 됨

---

### 2.6 HIGH: SSE 스트림 무인증

**위치**: `services/io_board/api.py`

**문제**:
- `/sse` 엔드포인트 보호 없음
- 실시간 로드셀 데이터 공개 스트림

---

### 2.7 HIGH: 결제 데이터 보안

**위치**: `services/card_terminal/`

**문제**:
- PCI DSS 준수 여부 불명
- 평문 통신
- VAN key 처리 방식 불명확

---

### 2.8 HIGH: 예외 정보 노출

**위치**: `services/model/api/routes.py` (L278-280)

**취약 코드**:
```python
except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
```

**문제**: 내부 경로, 스택 트레이스 노출

**권장 조치**:
```python
except Exception as e:
    logger.error(f"Judge failed: {e}", exc_info=True)
    raise HTTPException(
        status_code=500,
        detail="Internal server error. Please contact support."
    )
```

---

### 2.9 MEDIUM: 의존성 버전 미고정

**문제**: 상한선 없는 버전 지정
```
fastapi>=0.100.0      # 상한선 없음
uvicorn>=0.23.0       # 상한선 없음
```

**권장**:
```
fastapi>=0.100.0,<0.115.0
uvicorn>=0.23.0,<0.30.0
```

---

## 3. 코드 품질 이슈

### 3.1 CRITICAL: card_terminal import 오류

**위치**: `services/card_terminal/main.py` (L7)

**오류 코드**:
```python
from payment import CommunicationManager  # 잘못됨
```

**수정**:
```python
from .payment import CommunicationManager  # 상대 import
```

---

### 3.2 HIGH: 미사용 Import

| 파일 | Import | 상태 |
|------|--------|------|
| camera_client.py | `import asyncio` | 미사용 |
| camera_client.py | `import io` | 미사용 |

---

### 3.3 HIGH: TODO/FIXME (미완성 구현)

| 파일 | 라인 | 내용 |
|------|------|------|
| IF02.py | 41 | `# TODO: check actual status` - 헬스체크 미구현 |
| IF03.py | 57 | `# TODO: Implement door control logic` - 도어 제어 stub |
| IF04.py | 60 | `# TODO: Implement collect door logic` - 미완성 |

---

### 3.4 MEDIUM: 하드코딩된 값

| 서비스 | 파일 | 하드코딩 값 |
|--------|------|-----------|
| io_board | config.py | `"COM3"` (시리얼 포트) |
| card_terminal | main.py | `"127.0.0.1:30000"` (API 서버) |
| card_terminal | main.py | `"0.0.0.0:5000"` (CAT 서버) |

---

### 3.5 MEDIUM: 전역 변수 타입 힌트

**위치**: `services/model/main.py` (L46-51)

**현재**:
```python
product_db: ProductDatabase = None
decision_engine: ProductDecisionEngine = None
```

**권장**:
```python
from typing import Optional
product_db: Optional[ProductDatabase] = None
decision_engine: Optional[ProductDecisionEngine] = None
```

---

### 3.6 MEDIUM: Requirements 불일치

| 서비스 | 문제 |
|--------|------|
| model | `aiohttp>=3.8.0` 미사용 |
| card_terminal | FastAPI/uvicorn 누락 |

---

### 3.7 LOW: Deprecated 엔드포인트 잔존

**위치**: `services/io_board/api.py` (L403)
- `deprecated=True` 엔드포인트 여전히 활성

---

### 3.8 LOW: .env.example 파일 부재

필요한 환경 변수 문서화 없음:
- `IO_BOARD_URL`
- `CAMERA_DRIVER_URL`
- `NODEJS_URL`
- `MQTT_BROKER_HOST`
- `API_KEY`

---

## 4. 권장 조치사항

### 즉시 조치 (CRITICAL)

| 우선순위 | 항목 | 담당 |
|----------|------|------|
| 1 | API 인증 추가 (JWT/API Key) | Backend |
| 2 | HTTPS/TLS 적용 | DevOps |
| 3 | Path Traversal 방지 | Backend |
| 4 | 바인드 주소 제한 (127.0.0.1) | DevOps |
| 5 | card_terminal import 수정 | Backend |
| 6 | MQTT TLS + 인증 설정 | DevOps |

### 1주 내 조치 (HIGH)

| 항목 | 담당 |
|------|------|
| 예외 메시지 정보 숨김 | Backend |
| 미사용 import 제거 | Backend |
| TODO 항목 구현 | Backend |
| 의존성 버전 고정 | DevOps |

### 월간 조치 (MEDIUM/LOW)

| 항목 | 담당 |
|------|------|
| .env.example 작성 | Backend |
| 타입 힌트 개선 | Backend |
| Requirements 정리 | Backend |
| 보안 헤더 추가 | Backend |
| 감사 로깅 추가 | Backend |

---

## 부록: 환경 변수 예시 (.env.example)

```bash
# =============================================================================
# API Configuration
# =============================================================================
API_HOST=127.0.0.1
API_KEY=your-secure-api-key-here

# =============================================================================
# Service URLs
# =============================================================================
IO_BOARD_URL=http://localhost:8001
CAMERA_DRIVER_URL=http://localhost:8003
NODEJS_URL=http://localhost:8888

# =============================================================================
# MQTT Configuration
# =============================================================================
MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=

# =============================================================================
# Serial Port (IO Board)
# =============================================================================
SERIAL_PORT=COM3
SERIAL_BAUDRATE=38400

# =============================================================================
# YOLO Model
# =============================================================================
YOLO_MODEL_PATH=../../../siyeon_best.pt
```

---

> **다음 감사 예정**: PR 머지 전 재검사
> **문의**: minkyu 브랜치 담당자
