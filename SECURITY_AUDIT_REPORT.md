# Edge Environment 보안 및 코드 품질 감사 보고서

> **감사일**: 2026-01-26 (2차 감사)
> **대상**: Edge_Environment 전체 코드베이스
> **브랜치**: minkyu
> **상태**: 🔴 프로덕션 배포 불가

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
| 보안 취약점 | **8** | 6 | 5 | 5 |
| 코드 품질 | 1 | 2 | 6 | 4 |

### 🔴 즉시 조치 필요 항목 (배포 차단)
1. **하드코딩된 자격증명** - MongoDB, MinIO, MQTT, 사용자 비밀번호 노출
2. **무제한 CORS 설정** - `app.use(cors())` 무옵션
3. **모든 API 엔드포인트 인증 부재**
4. **Path Traversal 취약점** - logs.js, camera routes
5. **민감 데이터 로깅** - JWT 토큰 콘솔 출력
6. **HTTP 평문 통신** - HTTPS 미설정
7. **Helmet 미사용** - import만 하고 미적용
8. **파일 업로드 검증 미흡**

---

## 2. 보안 취약점

### 2.0 🔴 CRITICAL: 하드코딩된 자격증명 (신규 발견)

**위치**: `server/config/dev.js` (Lines 3-21)

**노출된 자격증명:**
```javascript
module.exports = {
    mongoURI: 'mongodb://admin:%40crkchai2025@139.150.81.182:27017/CHAI?authSource=admin',
    minioAccessKey: 'admin',
    minioSecretKey: 'CrkMinio2026',
    mqttURL: 'mqtt://chaidev.atcrk.co.kr:1883',
    mqttID: 'pnt',
    mqttPW: 'chai',
    userId: 'chai',
    userPassword: 'carrier041!',
    // ...
};
```

**노출된 정보:**
- MongoDB 접속 URL + 사용자/비밀번호
- MinIO 액세스 키/시크릿
- MQTT 브로커 자격증명
- 사용자 계정 비밀번호
- 서버 IP 주소 (139.150.81.182, 139.150.8.82)

**영향**: 공격자가 데이터베이스, 파일 저장소, MQTT 브로커, 외부 API에 무단 접근 가능

**권장 조치**:
```bash
# .env 파일 사용 (절대 Git 커밋하지 않음)
MONGO_URI=mongodb://...
MINIO_ACCESS_KEY=...
MINIO_SECRET_KEY=...
```

---

### 2.0.1 🔴 CRITICAL: 무제한 CORS 설정 (신규 발견)

**위치**: `server/index.js` (Line 64)

**취약 코드:**
```javascript
app.use(cors())  // 옵션 없음 - 모든 origin 허용!
```

**문제:**
- 모든 도메인에서 API 접근 허용
- CSRF 공격 가능
- 악성 웹사이트에서 사용자 데이터 탈취 가능

**권장 조치:**
```javascript
app.use(cors({
    origin: ['http://localhost:8889', 'https://your-production-domain.com'],
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'DELETE'],
    allowedHeaders: ['Content-Type', 'Authorization', 'X-API-Key']
}));
```

---

### 2.0.2 🔴 CRITICAL: Helmet 미사용 (신규 발견)

**위치**: `server/index.js`

**문제:**
```javascript
const helmet = require('helmet');  // Import만 하고
// app.use(helmet()) 호출 없음!   // 사용하지 않음
```

**누락된 보안 헤더:**
- X-Content-Type-Options
- X-Frame-Options (클릭재킹 방지)
- X-XSS-Protection
- Strict-Transport-Security (HSTS)
- Content-Security-Policy

**권장 조치:**
```javascript
app.use(helmet());
```

---

### 2.0.3 🔴 CRITICAL: 민감 데이터 로깅 (신규 발견)

**위치**: `server/config/key.js` (Line 44), `server/routes/auth.js`

**취약 코드:**
```javascript
// key.js
console.log('jwtToken', process.env.JWT_TOKEN);  // JWT 토큰 로깅!

// auth.js - devAutoLogin()
const token = r.data.accessToken;
process.env.JWT_TOKEN = cachedToken;
console.log('jwtToken', process.env.JWT_TOKEN);  // 다시 로깅!
```

**문제:**
- JWT 토큰이 콘솔/로그 파일에 출력
- 로그 수집 시스템에 토큰 노출
- 세션 하이재킹 위험

**권장 조치:**
```javascript
// 민감 데이터 로깅 금지
if (process.env.NODE_ENV !== 'production') {
    console.log('Token generated (redacted)');
}
```

---

### 2.1 CRITICAL: 인증 메커니즘 부재

**영향 범위**: 모든 FastAPI 서비스 + Node.js

| 서비스 | 포트 | 영향받는 엔드포인트 |
|--------|------|-------------------|
| Node.js | 8889 | /api/door/deadbolt/unlock, /api/door/deadbolt/lock |
| Node.js | 8889 | /api/camera/zone/*/activate |
| Node.js | 8889 | /api/model/test |
| model | 8002 | /api/judge, /api/products, /api/stats |
| io_board | 8001 | /sse, /loadcells, /deadbolt |
| camera_driver | 8003 | /frame/*, /api/zone/*/snapshot |
| mqtt_client | 8006 | /health |
| card_terminal | 5000 | 결제 API |

**문제**:
- JWT, API Key, Bearer Token 검증 없음
- 누구나 상품 판단, 카메라 접근, 데드볼트 제어 가능
- **물리적 보안 위협**: 인증 없이 도어 잠금 해제 가능

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

### 2.3 CRITICAL: Path Traversal 취약점 (다중 위치)

#### 2.3.1 Node.js logs.js

**위치**: `server/routes/logs.js` (Lines 158-188)

**취약 코드**:
```javascript
router.get('/camera/:date/:time/:filename', async (req, res) => {
    const { date, time, filename } = req.params;

    // 불충분한 검증 - '..' 문자열만 확인
    if (filename.includes('..') || time.includes('..')) {
        return res.status(400).json({ error: 'Invalid path' });
    }

    const filepath = path.join(process.cwd(), 'logs', 'camera', date, time, filename);
    res.sendFile(filepath);  // 취약!
});
```

**공격 시나리오**:
```
# Windows 경로 우회
GET /api/logs/camera/2026-01-26/..%5c..%5c..%5c/etc/passwd

# URL 인코딩 우회
GET /api/logs/camera/2026-01-26/%2e%2e/%2e%2e/sensitive.txt
```

#### 2.3.2 Camera Driver snapshot

**위치**: `services/camera_driver/api/routes.py` (Lines 313-363)

**취약 코드**:
```python
@router.post("/zone/{zone_id}/snapshot")
async def capture_zone_snapshot(zone_id: int, request: ZoneSnapshotRequest):
    # session_id가 사용자 입력에서 직접 사용됨
    session_path = str(project_root / request.session_id / "images")  # 취약!
```

#### 2.3.3 Model service media_paths

**위치**: `services/model/api/routes.py` (Lines 379-437)

**취약 코드**:
```python
if media_paths.top_image and os.path.exists(media_paths.top_image):
    image_paths.append(("top", media_paths.top_image))  # 경로 검증 없음!
```

**권장 조치**:
```python
import re
import os

def validate_path(user_path: str, allowed_base: str) -> str:
    """경로 검증 및 정규화"""
    # 1. 절대 경로로 변환
    abs_path = os.path.abspath(user_path)
    abs_base = os.path.abspath(allowed_base)

    # 2. 허용된 디렉토리 내인지 확인
    if not abs_path.startswith(abs_base):
        raise ValueError(f"Path traversal detected: {user_path}")

    # 3. 파일 존재 확인
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"File not found: {user_path}")

    return abs_path

def validate_session_id(session_id: str) -> bool:
    """세션 ID는 숫자와 언더스코어만 허용"""
    return bool(re.match(r'^[0-9_]+$', session_id))
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

### 2.6 HIGH: 파일 업로드 검증 미흡 (신규 발견)

**위치**: `services/model/api/routes.py` (Lines 622-711)

**취약 코드:**
```python
@router.post("/products/{product_id}/images")
async def upload_product_images(
    product_id: int,
    camera_id: int = Form(..., ge=0, le=5),
    images: List[UploadFile] = File(...),
):
    for image in images:
        # 확장자만 검사 - Magic byte 검사 없음!
        if not image.filename.lower().endswith((".jpg", ".jpeg", ".png")):
            continue

        # 파일 크기 제한 없음!
        content = await image.read()
        with open(filepath, "wb") as f:
            f.write(content)
```

**문제:**
- 파일 확장자만 검사 (악성 파일 업로드 가능)
- Magic byte (파일 시그니처) 검증 없음
- 파일 크기 제한 없음 (DoS 공격 가능)
- 안티바이러스 스캔 없음

**권장 조치:**
```python
import magic  # python-magic 패키지

ALLOWED_MIME_TYPES = {'image/jpeg', 'image/png'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

async def validate_image(file: UploadFile) -> bytes:
    content = await file.read()

    # 1. 크기 검사
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large")

    # 2. Magic byte 검사
    mime = magic.from_buffer(content, mime=True)
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(415, f"Invalid file type: {mime}")

    return content
```

---

### 2.7 HIGH: SSE 스트림 무인증

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

### 2.9 MEDIUM: Rate Limiting 부재 (신규 발견)

**영향 범위**: 모든 API 엔드포인트

**문제:**
- 요청 속도 제한 없음
- 브루트포스 공격 가능
- DoS 공격 취약

**영향받는 엔드포인트:**
- `/api/door/deadbolt/unlock` - 도어 제어 무한 요청 가능
- `/api/judge` - AI 추론 리소스 고갈 가능
- `/api/products/images` - 파일 업로드 플러딩

**권장 조치 (Node.js):**
```javascript
const rateLimit = require('express-rate-limit');

// 전역 제한
app.use(rateLimit({
    windowMs: 15 * 60 * 1000,  // 15분
    max: 100,                   // 100 요청
    message: 'Too many requests'
}));

// 도어 제어 강화 제한
const doorLimiter = rateLimit({
    windowMs: 60 * 1000,  // 1분
    max: 5,                // 5회
    message: 'Door control rate limit exceeded'
});
app.use('/api/door', doorLimiter);
```

**권장 조치 (FastAPI):**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/judge")
@limiter.limit("10/minute")
async def judge(request: Request):
    ...
```

---

### 2.10 MEDIUM: 의존성 버전 미고정

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

### 보안 취약점 요약 테이블

| ID | 심각도 | 취약점 | 위치 | 신규 |
|----|--------|--------|------|------|
| 2.0 | 🔴 CRITICAL | 하드코딩된 자격증명 | server/config/dev.js | ✓ |
| 2.0.1 | 🔴 CRITICAL | 무제한 CORS | server/index.js | ✓ |
| 2.0.2 | 🔴 CRITICAL | Helmet 미사용 | server/index.js | ✓ |
| 2.0.3 | 🔴 CRITICAL | 민감 데이터 로깅 | server/config/key.js, auth.js | ✓ |
| 2.1 | 🔴 CRITICAL | 인증 메커니즘 부재 | 모든 서비스 | |
| 2.2 | 🔴 CRITICAL | HTTPS 미사용 | 모든 서비스 | |
| 2.3 | 🔴 CRITICAL | Path Traversal | logs.js, routes.py | ✓ 확장 |
| 2.4 | 🔴 CRITICAL | 0.0.0.0 바인딩 | 모든 config.py | |
| 2.5 | 🔴 CRITICAL | MQTT 인증 미흡 | mqtt_client/config.py | |
| 2.6 | 🟠 HIGH | 파일 업로드 검증 미흡 | model/api/routes.py | ✓ |
| 2.7 | 🟠 HIGH | SSE 스트림 무인증 | io_board/api.py | |
| 2.8 | 🟠 HIGH | 예외 정보 노출 | model/api/routes.py | |
| 2.9 | 🟡 MEDIUM | Rate Limiting 부재 | 모든 엔드포인트 | ✓ |
| 2.10 | 🟡 MEDIUM | 의존성 버전 미고정 | requirements.txt | |

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

### 🔴 배포 차단 - 즉시 조치 (CRITICAL)

> **경고**: 아래 항목이 해결되기 전까지 프로덕션 배포 금지

| 우선순위 | 항목 | 담당 | 예상 시간 |
|----------|------|------|----------|
| **1** | 하드코딩된 자격증명 제거 (dev.js) | Backend | 1h |
| **2** | CORS 화이트리스트 설정 | Backend | 30m |
| **3** | Helmet 미들웨어 활성화 | Backend | 10m |
| **4** | 민감 데이터 로깅 제거 | Backend | 30m |
| **5** | API 인증 추가 (JWT/API Key) | Backend | 4h |
| **6** | Path Traversal 방지 (logs.js, routes.py) | Backend | 2h |
| **7** | HTTPS/TLS 적용 | DevOps | 2h |
| **8** | 바인드 주소 제한 (127.0.0.1) | DevOps | 30m |

**dev.js 자격증명 제거 예시:**
```javascript
// 수정 전 (취약)
mongoURI: 'mongodb://admin:password@139.150.81.182:27017/CHAI'

// 수정 후 (안전)
mongoURI: process.env.MONGO_URI || 'mongodb://localhost:27017/CHAI'
```

**CORS 설정 예시:**
```javascript
// 수정 전 (취약)
app.use(cors())

// 수정 후 (안전)
app.use(cors({
    origin: process.env.ALLOWED_ORIGINS?.split(',') || ['http://localhost:8889'],
    credentials: true
}));
```

**Helmet 활성화:**
```javascript
const helmet = require('helmet');
app.use(helmet());  // 이 줄 추가!
```

### 1주 내 조치 (HIGH)

| 항목 | 담당 | 설명 |
|------|------|------|
| 파일 업로드 검증 강화 | Backend | Magic byte 검사, 크기 제한 |
| 입력 값 검증 (zone_id, delta_weight) | Backend | 범위 검사 추가 |
| 예외 메시지 정보 숨김 | Backend | 스택 트레이스 노출 방지 |
| Rate Limiting 추가 | Backend | express-rate-limit 적용 |
| MQTT TLS + 인증 설정 | DevOps | 브로커 보안 강화 |

### 월간 조치 (MEDIUM/LOW)

| 항목 | 담당 | 설명 |
|------|------|------|
| CSRF 토큰 적용 | Backend | csurf 미들웨어 |
| 보안 감사 로깅 | Backend | 인증 실패, 도어 제어 이벤트 |
| 의존성 버전 고정 | DevOps | 정확한 버전 지정 |
| SameSite 쿠키 플래그 | Backend | CSRF 추가 방어 |
| .env.example 작성 | Backend | 환경 변수 문서화 |

---

## 부록: 환경 변수 예시 (.env.example)

```bash
# =============================================================================
# 🔐 SECURITY - 절대 Git에 커밋하지 마세요!
# =============================================================================
# 강력한 API 키 생성: openssl rand -hex 32
API_KEY=your-secure-api-key-here-minimum-32-characters
JWT_SECRET=your-jwt-secret-here-minimum-32-characters

# =============================================================================
# 🌐 CORS Configuration
# =============================================================================
ALLOWED_ORIGINS=http://localhost:8889,https://your-production-domain.com

# =============================================================================
# 📦 Database (프로덕션 환경)
# =============================================================================
MONGO_URI=mongodb://localhost:27017/CHAI
# 주의: 절대로 비밀번호를 코드에 하드코딩하지 마세요!

# =============================================================================
# 🗄️ MinIO (파일 저장소)
# =============================================================================
MINIO_ENDPOINT=localhost
MINIO_PORT=9000
MINIO_ACCESS_KEY=
MINIO_SECRET_KEY=
MINIO_BUCKET=chai-images

# =============================================================================
# 📡 MQTT Configuration
# =============================================================================
MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=
# TLS 사용 시
# MQTT_TLS=true
# MQTT_CA_CERT=/path/to/ca.crt

# =============================================================================
# 🔌 Service URLs
# =============================================================================
IO_BOARD_URL=http://localhost:8001
CAMERA_DRIVER_URL=http://localhost:8003
PRODUCT_JUDGE_URL=http://localhost:8002
NODEJS_URL=http://localhost:8889

# =============================================================================
# ⚙️ API Configuration
# =============================================================================
# 개발: 127.0.0.1 (로컬만)
# 프로덕션: 0.0.0.0 (리버스 프록시 뒤에서만)
API_HOST=127.0.0.1
NODE_ENV=development

# =============================================================================
# 🔧 Serial Port (IO Board)
# =============================================================================
SERIAL_PORT=COM3
SERIAL_BAUDRATE=38400

# =============================================================================
# 🤖 YOLO Model
# =============================================================================
YOLO_MODEL_PATH=../../../siyeon_best.pt
YOLO_CONFIDENCE_THRESHOLD=0.3

# =============================================================================
# 📷 Camera Configuration
# =============================================================================
CAMERA_MODE=api
NVIDIA_MODE=true
CAMERA_RESOLUTION_WIDTH=640
CAMERA_RESOLUTION_HEIGHT=480
SNAPSHOT_BASE_PATH=/data/snapshots
```

---

## 부록: 보안 체크리스트

배포 전 확인 사항:

- [ ] dev.js에 하드코딩된 자격증명 제거
- [ ] .env 파일 생성 및 Git에서 제외 (.gitignore)
- [ ] CORS 화이트리스트 설정
- [ ] Helmet 미들웨어 활성화
- [ ] JWT 토큰 로깅 제거
- [ ] HTTPS 인증서 설정
- [ ] API 인증 미들웨어 추가
- [ ] Path Traversal 검증 추가
- [ ] Rate Limiting 설정
- [ ] 보안 감사 로깅 활성화

---

> **감사 이력**:
> - 2026-01-22: 1차 감사 (15개 이슈)
> - 2026-01-26: 2차 감사 (24개 이슈, 8개 Critical 신규 발견)
>
> **다음 감사 예정**: PR 머지 전 재검사
> **문의**: minkyu 브랜치 담당자
