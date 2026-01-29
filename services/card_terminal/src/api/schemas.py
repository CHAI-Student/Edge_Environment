"""
Pydantic schemas for payment API request/response models.

This module defines all API request/response models with comprehensive validation,
pattern constraints, and examples following enterprise API design best practices.

All models include:
- Field-level validation (pattern, length, format)
- Example values for API documentation
- Clear descriptions for each field
- Type hints for IDE support
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from payment.const import CardInfoData


# ============================================================================
# RFC 7807 Problem Details Model
# ============================================================================


class ProblemDetail(BaseModel):
    """
    RFC 7807 Problem Details for HTTP APIs.

    Standard format for machine-readable error responses.
    See: https://tools.ietf.org/html/rfc7807

    Example:
        {
            "type": "urn:payment-gateway:error:validation",
            "title": "Validation Error",
            "status": 400,
            "detail": "Amount must be exactly 9 digits",
            "instance": "/api/v1/payment/token/approve"
        }
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "urn:payment-gateway:error:validation",
                "title": "Validation Error",
                "status": 400,
                "detail": "Amount must be exactly 9 digits",
                "instance": "/api/v1/payment/token/approve"
            }
        }
    )

    type: str = Field(
        ...,
        description="URN identifying the problem type",
        examples=["urn:payment-gateway:error:validation"],
    )
    title: str = Field(
        ...,
        description="Short, human-readable summary",
        examples=["Validation Error"],
    )
    status: int = Field(
        ...,
        description="HTTP status code",
        ge=100,
        le=599,
        examples=[400],
    )
    detail: str = Field(
        ...,
        description="Human-readable explanation specific to this occurrence",
        examples=["Amount must be exactly 9 digits"],
    )
    instance: Optional[str] = Field(
        None,
        description="URI reference identifying the specific occurrence",
        examples=["/api/v1/payment/token/approve"],
    )


# ============================================================================
# Token Payment Models
# ============================================================================


class PaymentTokenApproveRequest(BaseModel):
    """
    Token payment approval request.

    Initiates a token-based payment transaction with the CAT device.
    Amount must be a numeric string between 1 and 9 digits.

    Example:
        {
            "amount": "1000",
            "vankey_hash": "VANKEY1234567890HASH1234"
        }
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": "1000",
                "vankey_hash": "VANKEY1234567890HASH1234"
            }
        }
    )

    amount: str = Field(
        ...,
        description="Transaction amount as numeric string (1 to 9 digits, e.g., '1000' for ₩1,000)",
        pattern=r"^\d{1,9}$",
        min_length=1,
        max_length=9,
        examples=["1000", "10000", "100000"],
    )
    vankey_hash: str = Field(
        ...,
        description="VAN key hash (16 bytes) + token hash (8 bytes) = 24 ASCII characters",
        min_length=24,
        max_length=24,
        examples=["VANKEY1234567890HASH1234"],
    )

    @field_validator("amount")
    @classmethod
    def validate_amount_digits(cls, v: str) -> str:
        """Validate amount contains only digits."""
        if not v.isdigit():
            raise ValueError("Amount must contain only digits 0-9")
        return v


class PaymentTokenApproveResponse(BaseModel):
    """Token payment approval response.

    Fields:
        status: Transaction status ('Y' for success, 'N' for failure)
        authorization_number: Authorization number from device
        authorization_date: Authorization date in YYMMDD format
        card_info: Card information from device
        vankey: VAN key from device
        response_code: Device response code
        message: Human-readable message
    """
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "Y",
                    "authorization_number": "12345678",
                    "authorization_date": "260123",
                    "card_info": {
                        "SERIAL_NUMBER": "1234567890123456",
                        "ACQUIRER_ID": "001",
                        "ACQUIRER_NAME": "신한카드",
                        "ISSUER_ID": "002",
                        "ISSUER_NAME": "KB국민카드",
                        "MERCHANT_ID": "MERCHANT001"
                    },
                    "vankey": "VANKEY1234567890ABCDEFGH",
                    "response_code": 0,
                    "message": "Approved"
                },
                {
                    "status": "N",
                    "authorization_number": None,
                    "authorization_date": "260123",
                    "card_info": None,
                    "vankey": None,
                    "response_code": 201,
                    "message": "Declined - Insufficient funds"
                }
            ]
        }
    )

    status: str
    authorization_number: Optional[str]
    authorization_date: str
    card_info: Optional[CardInfoData]
    vankey: Optional[str]
    response_code: int
    message: str


class PaymentTokenCancelRequest(BaseModel):
    """
    Token payment cancellation request.

    Cancels a previously approved token payment transaction.
    Must match the original transaction details exactly.

    Example:
        {
            "amount": "1000",
            "original_authorization_number": "12345678",
            "original_authorization_date": "260123",
            "vankey_hash": "VANKEY1234567890HASH1234"
        }
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": "1000",
                "original_authorization_number": "12345678",
                "original_authorization_date": "260123",
                "vankey_hash": "VANKEY1234567890HASH1234"
            }
        }
    )

    amount: str = Field(
        ...,
        description="Transaction amount as numeric string (1 to 9 digits, must match original)",
        pattern=r"^\d{1,9}$",
        min_length=1,
        max_length=9,
        examples=["1000"],
    )
    original_authorization_number: str = Field(
        ...,
        description="Authorization number from original approval (8 characters)",
        min_length=8,
        max_length=8,
        examples=["12345678"],
    )
    original_authorization_date: str = Field(
        ...,
        description="Original authorization date in YYMMDD format (6 digits)",
        pattern=r"^\d{6}$",
        min_length=6,
        max_length=6,
        examples=["260123"],
    )
    vankey_hash: str = Field(
        ...,
        description="VAN key hash from original approval (24 characters)",
        min_length=24,
        max_length=24,
        examples=["VANKEY1234567890HASH1234"],
    )

    @field_validator("amount")
    @classmethod
    def validate_amount_digits(cls, v: str) -> str:
        """Validate amount contains only digits."""
        if not v.isdigit():
            raise ValueError("Amount must contain only digits 0-9")
        return v


class PaymentTokenCancelResponse(BaseModel):
    """Token payment cancellation response.

    Fields:
        status: Transaction status ('Y' for success, 'N' for failure)
        card_info: Card information from device
        vankey: VAN key from device
        response_code: Device response code
        message: Human-readable message
    """
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "Y",
                    "card_info": {
                        "SERIAL_NUMBER": "1234567890123456",
                        "ACQUIRER_ID": "001",
                        "ACQUIRER_NAME": "신한카드",
                        "ISSUER_ID": "002",
                        "ISSUER_NAME": "KB국민카드",
                        "MERCHANT_ID": "MERCHANT001"
                    },
                    "vankey": "VANKEY1234567890ABCDEFGH",
                    "response_code": 0,
                    "message": "Cancellation approved"
                },
                {
                    "status": "N",
                    "card_info": None,
                    "vankey": None,
                    "response_code": 301,
                    "message": "Original transaction not found"
                }
            ]
        }
    )

    status: str
    card_info: Optional[CardInfoData]
    vankey: Optional[str]
    response_code: int
    message: str


# ============================================================================
# Samsung Pay Models
# ============================================================================


class SamsungPayApproveRequest(BaseModel):
    """
    Samsung Pay approval request.

    Initiates a Samsung Pay transaction with the CAT device.
    Display message shown on the device screen.

    Example:
        {
            "amount": "000005000",
            "authorization_type": "PURCHASE",
            "display_message": "삼성페이 결제"
        }
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": "000005000",
                "authorization_type": "PURCHASE",
                "display_message": "삼성페이 결제"
            }
        }
    )

    amount: str = Field(
        ...,
        description="Transaction amount as numeric string (1 to 9 digits, e.g., '5000' for ₩5,000)",
        pattern=r"^\d{1,9}$",
        min_length=1,
        max_length=9,
        examples=["5000", "10000"],
    )
    authorization_type: str = Field(
        ...,
        description="Authorization type: 'PRE_AUTH' (0x00) or 'PURCHASE' (0x01)",
        pattern=r"^(PRE_AUTH|PURCHASE)$",
        examples=["PURCHASE", "PRE_AUTH"],
    )
    display_message: Optional[str] = Field(
        default="삼성페이 결제",
        description="Display message shown on device screen (EUC-KR encoding, max 20 bytes)",
        max_length=20,
        examples=["삼성페이 결제", "Samsung Pay"],
    )

    @field_validator("amount")
    @classmethod
    def validate_amount_digits(cls, v: str) -> str:
        """Validate amount contains only digits."""
        if not v.isdigit():
            raise ValueError("Amount must contain only digits 0-9")
        return v


class SamsungPayApproveResponse(BaseModel):
    """Samsung Pay approval response.

    Fields:
        status: Transaction status ('Y' for success, 'N' for failure)
        authorization_number: Authorization number from device
        authorization_date: Authorization date in YYMMDD format
        card_info: Card information from device
        vankey: VAN key from device
        response_code: Device response code
        message: Human-readable message
    """
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "Y",
                    "authorization_number": "87654321",
                    "authorization_date": "260123",
                    "card_info": {
                        "SERIAL_NUMBER": "9876543210987654",
                        "ACQUIRER_ID": "003",
                        "ACQUIRER_NAME": "우리카드",
                        "ISSUER_ID": "004",
                        "ISSUER_NAME": "하나카드",
                        "MERCHANT_ID": "MERCHANT002"
                    },
                    "vankey": "SPAYKEY98765ABCDEFGH1234",
                    "response_code": 0,
                    "message": "Approved"
                },
                {
                    "status": "N",
                    "authorization_number": None,
                    "authorization_date": "260123",
                    "card_info": None,
                    "vankey": None,
                    "response_code": 202,
                    "message": "Card declined - Contact issuer"
                }
            ]
        }
    )

    status: str
    authorization_number: Optional[str]
    authorization_date: str
    card_info: Optional[CardInfoData]
    vankey: Optional[str]
    response_code: int
    message: str


class SamsungPayCancelRequest(BaseModel):
    """
    Samsung Pay cancellation request.

    Cancels a previously approved Samsung Pay transaction.
    Must match the original transaction details exactly.

    Example:
        {
            "amount": "5000",
            "original_authorization_number": "87654321",
            "original_authorization_date": "260123",
            "vankey": "VANKEY1234567890ABCDEFGH"
        }
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": "5000",
                "original_authorization_number": "87654321",
                "original_authorization_date": "260123",
                "vankey": "VANKEY1234567890ABCDEFGH"
            }
        }
    )

    amount: str = Field(
        ...,
        description="Transaction amount as numeric string (1 to 9 digits, must match original)",
        pattern=r"^\d{1,9}$",
        min_length=1,
        max_length=9,
        examples=["5000"],
    )
    original_authorization_number: str = Field(
        ...,
        description="Authorization number from original approval (8 characters)",
        min_length=8,
        max_length=8,
        examples=["87654321"],
    )
    original_authorization_date: str = Field(
        ...,
        description="Original authorization date in YYMMDD format (6 digits)",
        pattern=r"^\d{6}$",
        min_length=6,
        max_length=6,
        examples=["260123"],
    )
    vankey: str = Field(
        ...,
        description="VAN key from original approval (24 characters)",
        min_length=24,
        max_length=24,
        examples=["VANKEY1234567890ABCDEFGH"],
    )

    @field_validator("amount")
    @classmethod
    def validate_amount_digits(cls, v: str) -> str:
        """Validate amount contains only digits."""
        if not v.isdigit():
            raise ValueError("Amount must contain only digits 0-9")
        return v


class SamsungPayCancelResponse(BaseModel):
    """Samsung Pay cancellation response.

    Fields:
        status: Transaction status ('Y' for success, 'N' for failure)
        card_info: Card information from device
        vankey: VAN key from device
        response_code: Device response code
        message: Human-readable message
    """
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "Y",
                    "card_info": {
                        "SERIAL_NUMBER": "9876543210987654",
                        "ACQUIRER_ID": "003",
                        "ACQUIRER_NAME": "우리카드",
                        "ISSUER_ID": "004",
                        "ISSUER_NAME": "하나카드",
                        "MERCHANT_ID": "MERCHANT002"
                    },
                    "vankey": "SPAYKEY98765ABCDEFGH1234",
                    "response_code": 0,
                    "message": "Cancellation approved"
                },
                {
                    "status": "N",
                    "card_info": None,
                    "vankey": None,
                    "response_code": 302,
                    "message": "Cancellation period expired"
                }
            ]
        }
    )

    status: str
    card_info: Optional[CardInfoData]
    vankey: Optional[str]
    response_code: int
    message: str


# ============================================================================
# SSE Stream Models
# ============================================================================


class TokenGeneratedStream(BaseModel):
    """Token generation event for SSE stream."""
    status: str
    vankey_hash: Optional[str]
    card_info: Optional[CardInfoData]
    response_code: int
    message: str


class RFIDStream(BaseModel):
    """RFID read event for SSE stream."""
    data: str
