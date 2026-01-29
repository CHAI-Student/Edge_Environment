"""
Payment command layer for CAT device communication.

This module provides high-level functions for sending payment commands
to the CAT device and processing responses. All commands include:
- Input validation
- Configurable timeout
- Protocol validation
- Structured error handling
- Request/response logging

Timeout behavior:
- Uses COMM_TIMEOUT from config (default 30 seconds)
- Raises TimeoutError if device doesn't respond in time
- Can be overridden per-command if needed
"""

import asyncio
import logging

from construct import ConstructError

from config import settings
from exceptions import ProtocolError, TimeoutError, ValidationError

from .payment_types import (
    DeviceCheckData,
    TxSPayApprovalData,
    TxSPayCancelData,
    TxTokenApprovalData,
    TxTokenCancelData,
    TxTokenData,
)

from .const import (
    AuthorizationType,
    MessageType,
    ServiceCode,
    build_card_info_data,
)
from .manager import Communication
from .payload import (
    DeviceCheckRequest,
    DeviceCheckResponse,
    ErrorPayload,
    TransactionSPayApproveRequest,
    TransactionSPayApproveResponse,
    TransactionSPayCancelRequest,
    TransactionSPayCancelResponse,
    TransactionSPayInitilizeRequest,
    TransactionTokenApproveRequest,
    TransactionTokenApproveResponse,
    TransactionTokenCancelRequest,
    TransactionTokenCancelResponse,
    TransactionTokenGenerateRequest,
    TransactionTokenGenerateResponse,
    TransactionTokenInitilizeRequest,
    TransactionRFIDInitilizeRequest,
)
from .structure import Protocol

logger = logging.getLogger(__name__)


def _validate_amount(amount: str, field_name: str = "amount") -> None:
    """
    Validate amount field format.

    Args:
        amount: Amount string to validate
        field_name: Name of field for error message

    Raises:
        ValidationError: If amount is invalid format
    """
    if not amount:
        raise ValidationError(
            f"{field_name} is required",
            field=field_name,
        )

    if len(amount) != 9:
        raise ValidationError(
            f"{field_name} must be exactly 9 digits, got {len(amount)}",
            field=field_name,
            value=amount,
        )

    if not amount.isdigit():
        raise ValidationError(
            f"{field_name} must contain only digits 0-9",
            field=field_name,
            value=amount,
        )


def _validate_authorization_number(auth_number: str, field_name: str = "authorization_number") -> None:
    """
    Validate authorization number format.

    Args:
        auth_number: Authorization number to validate
        field_name: Name of field for error message

    Raises:
        ValidationError: If authorization number is invalid
    """
    if not auth_number:
        raise ValidationError(
            f"{field_name} is required",
            field=field_name,
        )

    if len(auth_number) != 8:
        raise ValidationError(
            f"{field_name} must be exactly 8 characters, got {len(auth_number)}",
            field=field_name,
            value=auth_number,
        )


def _validate_authorization_date(auth_date: str, field_name: str = "authorization_date") -> None:
    """
    Validate authorization date format (YYMMDD).

    Args:
        auth_date: Authorization date to validate
        field_name: Name of field for error message

    Raises:
        ValidationError: If date is invalid format
    """
    if not auth_date:
        raise ValidationError(
            f"{field_name} is required",
            field=field_name,
        )

    if len(auth_date) != 6:
        raise ValidationError(
            f"{field_name} must be YYMMDD format (6 digits), got {len(auth_date)}",
            field=field_name,
            value=auth_date,
        )

    if not auth_date.isdigit():
        raise ValidationError(
            f"{field_name} must contain only digits",
            field=field_name,
            value=auth_date,
        )


def _validate_response(
    response,
    expected_service_code: ServiceCode,
    expected_message_type: MessageType = MessageType.RESPONSE,
) -> None:
    """
    Validate protocol response matches expected values.

    Args:
        response: Protocol response object
        expected_service_code: Expected service code
        expected_message_type: Expected message type

    Raises:
        ProtocolError: If response doesn't match expected values
    """
    if response.service_code != expected_service_code.value:
        raise ProtocolError(
            f"Service code mismatch: expected {expected_service_code.value}, got {response.service_code}",
            expected=expected_service_code.value,
            received=response.service_code,
        )

    if response.message_type != expected_message_type:
        raise ProtocolError(
            f"Message type mismatch: expected {expected_message_type}, got {response.message_type}",
            expected=expected_message_type,
            received=response.message_type,
        )


async def retrieve_request(comm: Communication):
    while True:
        message = await comm.read_request()

        if not message.service_code in ServiceCode:
            logger.error("Unknown service code: %s", message.service_code)
            continue

        service_code = ServiceCode(message.service_code)

        if service_code == ServiceCode.TX_TOKEN_INIT:
            payload_struct = TransactionTokenInitilizeRequest
        elif service_code == ServiceCode.TX_SPAY_INIT:
            payload_struct = TransactionSPayInitilizeRequest
        elif service_code == ServiceCode.TX_RFID_INIT:
            payload_struct = TransactionRFIDInitilizeRequest
        else:
            logger.error("Service code %s not implemented yet", service_code)
            continue

        break

    payload = payload_struct.parse(message.payload)

    return message, payload


async def send_tx_token_generate(
    comm: Communication,
    timeout: float | None = None,
) -> TxTokenData:
    """
    Request token generation from CAT device.

    Args:
        comm: Communication instance
        timeout: Response timeout in seconds (uses config default if None)

    Returns:
        Token generation data with vankey_hash and card info

    Raises:
        TimeoutError: If device doesn't respond in time
        ProtocolError: If response is invalid
        CommunicationError: If communication fails
    """
    logger.debug("Sending TX_TOKEN_GENERATE request")

    request_payload = TransactionTokenGenerateRequest.build(
        {
            "message": "",
        }
    )
    request = Protocol.build(
        {
            "service_code": ServiceCode.TX_TOKEN_GENERATE.value,
            "message_type": MessageType.REQUEST,
            "payload": request_payload,
        }
    )

    response = await comm.fetch(request, timeout=timeout)
    _validate_response(response, ServiceCode.TX_TOKEN_GENERATE)

    try:
        response_payload = TransactionTokenGenerateResponse.parse(response.payload)
    except ConstructError as e:
        raise ProtocolError(
            response.payload.decode('euc-kr', errors='ignore')
        ) from e

    logger.info(
        "Token generated",
        extra={
            "status": response_payload.status,
            "response_code": response_payload.response_code.name,
        },
    )

    return TxTokenData(
        status=response_payload.status,
        vankey_hash=response_payload.vankey_hash,
        card_info=build_card_info_data(response_payload.card_info),
        response_code=response_payload.response_code,
        message=response_payload.message,
    )


async def send_tx_token_approve(
    comm: Communication,
    amount: str,
    vankey_hash: str,
    timeout: float | None = None,
) -> TxTokenApprovalData:
    """
    Approve token payment transaction.

    Args:
        comm: Communication instance
        amount: Transaction amount (9-digit numeric string)
        vankey_hash: VAN key hash (24 characters)
        timeout: Response timeout in seconds (uses config default if None)

    Returns:
        Token approval data with authorization number and card info

    Raises:
        ValidationError: If input parameters are invalid
        TimeoutError: If device doesn't respond in time
        ProtocolError: If response is invalid
        CommunicationError: If communication fails
    """
    _validate_amount(amount)

    logger.debug(
        "Sending TX_TOKEN_APPROVE request",
        extra={"amount": amount, "vankey_hash_len": len(vankey_hash)},
    )

    request_payload = TransactionTokenApproveRequest.build(
        {
            "amount": amount,
            "vankey_hash": vankey_hash,
            "message": "",
        }
    )
    request = Protocol.build(
        {
            "service_code": ServiceCode.TX_TOKEN_APPROVE.value,
            "message_type": MessageType.REQUEST,
            "payload": request_payload,
        }
    )

    response = await comm.fetch(request, timeout=timeout)
    _validate_response(response, ServiceCode.TX_TOKEN_APPROVE)

    try:
        response_payload = TransactionTokenApproveResponse.parse(response.payload)
    except ConstructError as e:
        raise ProtocolError(
            response.payload.decode('euc-kr', errors='ignore')
        ) from e

    logger.info(
        "Token payment approved",
        extra={
            "status": response_payload.status,
            "auth_number": response_payload.authorization_number,
            "response_code": response_payload.response_code.name,
        },
    )

    return TxTokenApprovalData(
        status=response_payload.status,
        authorization_number=response_payload.authorization_number,
        card_info=build_card_info_data(response_payload.card_info),
        vankey=response_payload.vankey,
        response_code=response_payload.response_code,
        message=response_payload.message,
    )


async def send_tx_token_cancel(
    comm: Communication,
    amount: str,
    original_authorization_number: str,
    original_authorization_date: str,
    vankey_hash: str,
    timeout: float | None = None,
) -> TxTokenCancelData:
    """
    Cancel token payment transaction.

    Args:
        comm: Communication instance
        amount: Transaction amount (9-digit numeric string, must match original)
        original_authorization_number: Authorization number from approval (8 characters)
        original_authorization_date: Authorization date in YYMMDD format (6 digits)
        vankey_hash: VAN key hash from original approval (24 characters)
        timeout: Response timeout in seconds (uses config default if None)

    Returns:
        Token cancellation data with card info

    Raises:
        ValidationError: If input parameters are invalid
        TimeoutError: If device doesn't respond in time
        ProtocolError: If response is invalid
        CommunicationError: If communication fails
    """
    _validate_amount(amount)
    _validate_authorization_number(original_authorization_number, "original_authorization_number")
    _validate_authorization_date(original_authorization_date, "original_authorization_date")

    logger.debug(
        "Sending TX_TOKEN_CANCEL request",
        extra={
            "amount": amount,
            "auth_number": original_authorization_number,
            "auth_date": original_authorization_date,
        },
    )

    request_payload = TransactionTokenCancelRequest.build(
        {
            "amount": amount,
            "original_authorization_number": original_authorization_number,
            "original_authorization_date": original_authorization_date,
            "vankey_hash": vankey_hash,
        }
    )
    request = Protocol.build(
        {
            "service_code": ServiceCode.TX_TOKEN_CANCEL.value,
            "message_type": MessageType.REQUEST,
            "payload": request_payload,
        }
    )

    response = await comm.fetch(request, timeout=timeout)
    _validate_response(response, ServiceCode.TX_TOKEN_CANCEL)

    try:
        response_payload = TransactionTokenCancelResponse.parse(response.payload)
    except ConstructError as e:
        raise ProtocolError(
            response.payload.decode('euc-kr', errors='ignore')
        ) from e

    logger.info(
        "Token payment cancelled",
        extra={
            "status": response_payload.status,
            "response_code": response_payload.response_code.name,
        },
    )

    return TxTokenCancelData(
        status=response_payload.status,
        card_info=build_card_info_data(response_payload.card_info),
        vankey=response_payload.vankey,
        response_code=response_payload.response_code,
        message=response_payload.message,
    )


async def send_tx_spay_approve(
    comm: Communication,
    amount: str,
    authorization_type: AuthorizationType,
    display_message: str = "",
    timeout: float | None = None,
) -> TxSPayApprovalData:
    """
    Approve Samsung Pay transaction.

    Args:
        comm: Communication instance
        amount: Transaction amount (9-digit numeric string)
        authorization_type: Authorization type (PRE_AUTH or PURCHASE)
        display_message: Message to display on device screen
        timeout: Response timeout in seconds (uses config default if None)

    Returns:
        Samsung Pay approval data with authorization number and card info

    Raises:
        ValidationError: If input parameters are invalid
        TimeoutError: If device doesn't respond in time
        ProtocolError: If response is invalid
        CommunicationError: If communication fails
    """
    _validate_amount(amount)

    logger.debug(
        "Sending TX_SPAY_APPROVE request",
        extra={
            "amount": amount,
            "auth_type": authorization_type.value,
            "display_msg": display_message,
        },
    )

    request_payload = TransactionSPayApproveRequest.build(
        {
            "amount": amount,
            "authorization_type": authorization_type,
            "message": display_message,
        }
    )
    request = Protocol.build(
        {
            "service_code": ServiceCode.TX_SPAY_APPROVE.value,
            "message_type": MessageType.REQUEST,
            "payload": request_payload,
        }
    )

    response = await comm.fetch(request, timeout=timeout)
    _validate_response(response, ServiceCode.TX_SPAY_APPROVE)

    try:
        response_payload = TransactionSPayApproveResponse.parse(response.payload)
    except ConstructError as e:
        raise ProtocolError(
            response.payload.decode('euc-kr', errors='ignore')
        ) from e

    logger.info(
        "Samsung Pay approved",
        extra={
            "status": response_payload.status,
            "auth_number": response_payload.authorization_number,
            "vankey_len": len(response_payload.vankey) if response_payload.vankey else 0,
            "response_code": response_payload.response_code.name,
        },
    )

    return TxSPayApprovalData(
        status=response_payload.status,
        authorization_number=response_payload.authorization_number,
        card_info=build_card_info_data(response_payload.card_info),
        vankey=response_payload.vankey,
        response_code=response_payload.response_code,
        message=response_payload.message,
    )


async def send_tx_spay_cancel(
    comm: Communication,
    amount: str,
    original_authorization_number: str,
    original_authorization_date: str,
    vankey: str,
    timeout: float | None = None,
) -> TxSPayCancelData:
    """
    Cancel Samsung Pay transaction.

    Args:
        comm: Communication instance
        amount: Transaction amount (9-digit numeric string, must match original)
        original_authorization_number: Authorization number from approval (8 characters)
        original_authorization_date: Authorization date in YYMMDD format (6 digits)
        vankey: VAN key from original approval (24 characters)
        timeout: Response timeout in seconds (uses config default if None)

    Returns:
        Samsung Pay cancellation data with card info

    Raises:
        ValidationError: If input parameters are invalid
        TimeoutError: If device doesn't respond in time
        ProtocolError: If response is invalid
        CommunicationError: If communication fails
    """
    _validate_amount(amount)
    _validate_authorization_number(original_authorization_number, "original_authorization_number")
    _validate_authorization_date(original_authorization_date, "original_authorization_date")

    logger.debug(
        "Sending TX_SPAY_CANCEL request",
        extra={
            "amount": amount,
            "auth_number": original_authorization_number,
            "auth_date": original_authorization_date,
        },
    )

    request_payload = TransactionSPayCancelRequest.build(
        {
            "amount": amount,
            "original_authorization_number": original_authorization_number,
            "original_authorization_date": original_authorization_date,
            "vankey": vankey,
        }
    )
    request = Protocol.build(
        {
            "service_code": ServiceCode.TX_SPAY_CANCEL.value,
            "message_type": MessageType.REQUEST,
            "payload": request_payload,
        }
    )

    response = await comm.fetch(request, timeout=timeout)
    _validate_response(response, ServiceCode.TX_SPAY_CANCEL)

    try:
        response_payload = TransactionSPayCancelResponse.parse(response.payload)
    except ConstructError as e:
        raise ProtocolError(
            response.payload.decode('euc-kr', errors='ignore')
        ) from e


    logger.info(
        "Samsung Pay cancelled",
        extra={
            "status": response_payload.status,
            "response_code": response_payload.response_code.name,
        },
    )

    return TxSPayCancelData(
        status=response_payload.status,
        card_info=build_card_info_data(response_payload.card_info),
        vankey=response_payload.vankey,
        response_code=response_payload.response_code,
        message=response_payload.message,
    )


async def send_device_check(
    comm: Communication,
    timeout: float | None = None,
) -> DeviceCheckData:
    """
    Perform device health check.

    Args:
        comm: Communication instance
        timeout: Response timeout in seconds (uses config default if None)

    Returns:
        Device check data with response code

    Raises:
        TimeoutError: If device doesn't respond in time
        ProtocolError: If response is invalid
        CommunicationError: If communication fails
    """
    logger.debug("Sending DEVICE_CHECK request")

    request_payload = DeviceCheckRequest.build(
        {
            "message": "",
        }
    )
    request = Protocol.build(
        {
            "service_code": ServiceCode.DEVICE_CHECK.value,
            "message_type": MessageType.REQUEST,
            "payload": request_payload,
        }
    )

    response = await comm.fetch(request, timeout=timeout)


    try:
        response_payload = DeviceCheckResponse.parse(response.payload)
    except ConstructError as e:
        raise ProtocolError(
            response.payload.decode('euc-kr', errors='ignore')
        ) from e


    logger.info(
        "Device check complete",
        extra={"response_code": response_payload.response_code.name},
    )

    return DeviceCheckData(
        response_code=response_payload.response_code,
    )
