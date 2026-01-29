"""
Error Codes for AI Smart Vending Machine.

에러 코드 정의 및 분류.

코드 체계:
- E1xxx: 시스템 에러
- E2xxx: IO Board 에러
- E3xxx: 카메라 에러
- E4xxx: Vision 에러
- E5xxx: 네트워크 에러
- E6xxx: 결제 에러
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional
import time


class ErrorCode(str, Enum):
    """에러 코드."""

    # 시스템 에러 (E1xxx)
    E1001 = "E1001"  # 서비스 초기화 실패
    E1002 = "E1002"  # 설정 로드 실패
    E1003 = "E1003"  # 메모리 부족
    E1004 = "E1004"  # 디스크 공간 부족

    # IO Board 에러 (E2xxx)
    E2001 = "E2001"  # 시리얼 포트 없음
    E2002 = "E2002"  # 시리얼 포트 접근 거부
    E2003 = "E2003"  # 통신 오류
    E2004 = "E2004"  # 체크섬 오류
    E2005 = "E2005"  # 타임아웃
    E2006 = "E2006"  # 로드셀 이상값
    E2007 = "E2007"  # 데드볼트 제어 실패

    # 카메라 에러 (E3xxx)
    E3001 = "E3001"  # 카메라 연결 실패
    E3002 = "E3002"  # 프레임 캡처 실패
    E3003 = "E3003"  # 타임아웃
    E3004 = "E3004"  # 이미지 디코드 실패
    E3005 = "E3005"  # 서비스 불가
    E3006 = "E3006"  # 카메라 매핑 실패

    # Vision 에러 (E4xxx)
    E4001 = "E4001"  # 모델 로드 실패
    E4002 = "E4002"  # 추론 실패
    E4003 = "E4003"  # 손 감지 실패
    E4004 = "E4004"  # 상품 감지 실패
    E4005 = "E4005"  # 앙상블 실패

    # 네트워크 에러 (E5xxx)
    E5001 = "E5001"  # SSE 연결 실패
    E5002 = "E5002"  # HTTP 요청 실패
    E5003 = "E5003"  # Node.js 연결 실패
    E5004 = "E5004"  # MQTT 연결 실패
    E5005 = "E5005"  # 타임아웃

    # 결제 에러 (E6xxx)
    E6001 = "E6001"  # 카드 터미널 연결 실패
    E6002 = "E6002"  # 결제 승인 실패
    E6003 = "E6003"  # 결제 취소 실패
    E6004 = "E6004"  # 네트워크 오류


# 에러 코드별 복구 가능 여부
ERROR_RECOVERABLE = {
    # IO Board - 대부분 자동 복구 가능
    ErrorCode.E2001: False,  # 시리얼 포트 없음 - 수동 연결 필요
    ErrorCode.E2002: False,  # 접근 거부 - 권한 설정 필요
    ErrorCode.E2003: True,   # 통신 오류 - 재시도
    ErrorCode.E2004: True,   # 체크섬 오류 - 재시도
    ErrorCode.E2005: True,   # 타임아웃 - 재시도
    ErrorCode.E2006: True,   # 로드셀 이상값 - 재보정
    ErrorCode.E2007: True,   # 데드볼트 제어 - 재시도

    # 카메라 - 대부분 자동 복구 가능
    ErrorCode.E3001: True,   # 연결 실패 - 재연결
    ErrorCode.E3002: True,   # 프레임 캡처 - 재시도
    ErrorCode.E3003: True,   # 타임아웃 - 재시도
    ErrorCode.E3004: True,   # 디코드 실패 - 재시도
    ErrorCode.E3005: True,   # 서비스 불가 - 대기 후 재시도
    ErrorCode.E3006: True,   # 매핑 실패 - 재스캔

    # Vision - 대부분 자동 복구 가능
    ErrorCode.E4001: False,  # 모델 로드 - 수동 확인 필요
    ErrorCode.E4002: True,   # 추론 실패 - 재시도
    ErrorCode.E4003: True,   # 손 감지 - 프레임 재캡처
    ErrorCode.E4004: True,   # 상품 감지 - 프레임 재캡처
    ErrorCode.E4005: True,   # 앙상블 실패 - 재처리

    # 네트워크 - 자동 복구
    ErrorCode.E5001: True,   # SSE - 재연결
    ErrorCode.E5002: True,   # HTTP - 재시도
    ErrorCode.E5003: True,   # Node.js - 재연결
    ErrorCode.E5004: True,   # MQTT - 재연결
    ErrorCode.E5005: True,   # 타임아웃 - 재시도

    # 결제 - 주의 필요
    ErrorCode.E6001: True,   # 터미널 연결 - 재연결
    ErrorCode.E6002: False,  # 승인 실패 - 수동 확인
    ErrorCode.E6003: False,  # 취소 실패 - 수동 확인
    ErrorCode.E6004: True,   # 네트워크 - 재시도
}


# 에러 메시지
ERROR_MESSAGES = {
    ErrorCode.E2001: "시리얼 포트를 찾을 수 없습니다",
    ErrorCode.E2002: "시리얼 포트 접근이 거부되었습니다",
    ErrorCode.E2003: "IO Board 통신 오류",
    ErrorCode.E2004: "체크섬 검증 실패",
    ErrorCode.E2005: "IO Board 응답 타임아웃",
    ErrorCode.E2006: "로드셀 이상값 감지",
    ErrorCode.E2007: "데드볼트 제어 실패",

    ErrorCode.E3001: "카메라 연결 실패",
    ErrorCode.E3002: "프레임 캡처 실패",
    ErrorCode.E3003: "카메라 응답 타임아웃",
    ErrorCode.E3004: "이미지 디코드 실패",
    ErrorCode.E3005: "카메라 서비스 불가",
    ErrorCode.E3006: "카메라 매핑 실패",

    ErrorCode.E4001: "AI 모델 로드 실패",
    ErrorCode.E4002: "추론 실패",
    ErrorCode.E4003: "손 감지 실패",
    ErrorCode.E4004: "상품 감지 실패",
    ErrorCode.E4005: "앙상블 처리 실패",

    ErrorCode.E5001: "SSE 연결 실패",
    ErrorCode.E5002: "HTTP 요청 실패",
    ErrorCode.E5003: "Node.js 서버 연결 실패",
    ErrorCode.E5004: "MQTT 브로커 연결 실패",
    ErrorCode.E5005: "네트워크 타임아웃",

    ErrorCode.E6001: "카드 터미널 연결 실패",
    ErrorCode.E6002: "결제 승인 실패",
    ErrorCode.E6003: "결제 취소 실패",
    ErrorCode.E6004: "결제 네트워크 오류",
}


@dataclass
class ServiceError:
    """서비스 에러 정보."""

    code: ErrorCode
    message: str
    service: str
    timestamp: float
    recoverable: bool
    details: Optional[dict] = None
    recovery_attempted: bool = False
    recovery_success: bool = False

    @classmethod
    def create(
        cls,
        code: ErrorCode,
        service: str,
        details: Optional[dict] = None,
        message: Optional[str] = None,
    ) -> "ServiceError":
        """
        에러 생성.

        Args:
            code: 에러 코드
            service: 서비스 이름
            details: 추가 정보
            message: 커스텀 메시지

        Returns:
            ServiceError 인스턴스
        """
        return cls(
            code=code,
            message=message or ERROR_MESSAGES.get(code, "Unknown error"),
            service=service,
            timestamp=time.time(),
            recoverable=ERROR_RECOVERABLE.get(code, False),
            details=details,
        )

    def to_dict(self) -> dict:
        """딕셔너리 변환."""
        return {
            "code": self.code.value,
            "message": self.message,
            "service": self.service,
            "timestamp": self.timestamp,
            "recoverable": self.recoverable,
            "details": self.details,
            "recovery_attempted": self.recovery_attempted,
            "recovery_success": self.recovery_success,
        }
