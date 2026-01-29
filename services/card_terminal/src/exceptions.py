"""
Payment Gateway Exception Hierarchy with RFC 7807 Problem Details support.

This module defines custom exceptions that follow RFC 7807 (Problem Details for HTTP APIs)
to provide standardized error responses across the payment gateway application.

All exceptions include:
- type: URN identifying the problem type (urn:payment-gateway:error:*)
- title: A short, human-readable summary
- status: HTTP status code
- detail: A human-readable explanation specific to this occurrence
- instance: URI reference identifying the specific occurrence
"""

from typing import Any, Dict, Optional


class PaymentGatewayError(Exception):
    """
    Base exception for all payment gateway errors.

    Follows RFC 7807 Problem Details specification for standardized error responses.
    All subclasses should define type_urn, title, and status attributes.
    """

    type_urn: str = "urn:payment-gateway:error:generic"
    title: str = "Payment Gateway Error"
    status: int = 500

    def __init__(
        self,
        detail: str,
        instance: Optional[str] = None,
        **kwargs: Any
    ):
        """
        Initialize payment gateway error.

        Args:
            detail: Human-readable explanation specific to this error occurrence
            instance: URI reference identifying the specific occurrence (e.g., request ID)
            **kwargs: Additional context fields to include in the problem details
        """
        super().__init__(detail)
        self.detail = detail
        self.instance = instance
        self.extra = kwargs

    def to_problem_detail(self) -> Dict[str, Any]:
        """
        Convert exception to RFC 7807 Problem Detail dictionary.

        Returns:
            Dictionary with type, title, status, detail, instance, and any extra fields
        """
        problem = {
            "type": self.type_urn,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
        }

        if self.instance:
            problem["instance"] = self.instance

        # Add any extra context fields
        problem.update(self.extra)

        return problem

    def __str__(self) -> str:
        """Return detail message for logging."""
        return f"{self.title}: {self.detail}"


class ValidationError(PaymentGatewayError):
    """
    Input validation error (invalid format, missing fields, constraint violations).

    Examples:
        - Amount not 9 digits
        - VAN key hash not 24 characters
        - Invalid date format
        - Missing required field
    """

    type_urn = "urn:payment-gateway:error:validation"
    title = "Validation Error"
    status = 400


class CommunicationError(PaymentGatewayError):
    """
    Communication error with the CAT device.

    Examples:
        - TCP connection failed
        - Connection timeout
        - Network error
        - Device not responding
    """

    type_urn = "urn:payment-gateway:error:communication"
    title = "Communication Error"
    status = 503


class ProtocolError(PaymentGatewayError):
    """
    Protocol violation or unexpected response from CAT device.

    Examples:
        - Invalid message structure
        - Wrong service code in response
        - Checksum mismatch
        - Unexpected message type
    """

    type_urn = "urn:payment-gateway:error:protocol"
    title = "Protocol Error"
    status = 502


class TimeoutError(PaymentGatewayError):
    """
    Operation timeout error.

    Examples:
        - Device response timeout
        - Transaction timeout
        - Queue timeout
    """

    type_urn = "urn:payment-gateway:error:timeout"
    title = "Timeout Error"
    status = 504


class DeviceError(PaymentGatewayError):
    """
    CAT device returned an error status.

    Examples:
        - Transaction declined
        - Card read error
        - Device malfunction
    """

    type_urn = "urn:payment-gateway:error:device"
    title = "Device Error"
    status = 422

    def __init__(
        self,
        detail: str,
        response_code: Optional[str] = None,
        instance: Optional[str] = None,
        **kwargs: Any
    ):
        """
        Initialize device error with optional response code.

        Args:
            detail: Human-readable error explanation
            response_code: Device response code (e.g., "N" for declined)
            instance: Request identifier
            **kwargs: Additional context
        """
        super().__init__(detail, instance, **kwargs)
        if response_code:
            self.extra["response_code"] = response_code


class ConfigurationError(PaymentGatewayError):
    """
    Configuration or initialization error.

    Examples:
        - Invalid environment variable
        - Missing required configuration
        - Invalid configuration value
    """

    type_urn = "urn:payment-gateway:error:configuration"
    title = "Configuration Error"
    status = 500
