"""
하드웨어 연동 테스트: 실제 IO Board + 6대 카메라 + Model 서비스 통합 테스트.

이 테스트는 실제 자판기 환경에서 모델의 성능과 로직을 테스트합니다.

필수 조건:
    - io_board 서비스 실행 중 (포트 8000)
    - camera_driver 서비스 실행 중 (포트 8003)
    - model 서비스 실행 중 (포트 8002)

사용법:
    # 연결 상태 확인
    python -m tests.test_hardware_integration --check-connection

    # SSE 이벤트 모니터링 (10초간)
    python -m tests.test_hardware_integration --monitor-sse --duration 10

    # 특정 Zone 캡처 테스트 (Zone 1)
    python -m tests.test_hardware_integration --capture-zone 1

    # 전체 Zone 스캔
    python -m tests.test_hardware_integration --scan-all-zones

    # 수동 판단 테스트 (무게 변화 시뮬레이션)
    python -m tests.test_hardware_integration --manual-judge --zone 1 --delta -365

    # 실시간 모니터링 + 자동 판단
    python -m tests.test_hardware_integration --realtime-monitor

    # 특정 상품 인식 정확도 테스트 (10회 반복)
    python -m tests.test_hardware_integration --accuracy-test --zone 1 --repeat 10
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import logging

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import config, ZONE_CAMERA_MAP, ZONE_CHANNEL_MAP, TOP_CAMERA_ID

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ServiceStatus:
    """서비스 상태."""
    name: str
    url: str
    is_healthy: bool
    response_time_ms: float
    details: Optional[Dict] = None
    error: Optional[str] = None


@dataclass
class CaptureResult:
    """캡처 결과."""
    zone_id: int
    top_camera_ok: bool
    side_camera_ok: bool
    top_frame_size: Optional[tuple] = None
    side_frame_size: Optional[tuple] = None
    capture_time_ms: float = 0.0


@dataclass
class JudgmentTestResult:
    """판단 테스트 결과."""
    zone_id: int
    delta_weight: float
    products: List[Dict]
    total_price: int
    status: str
    confidence: float
    processing_time_ms: float
    success: bool
    error: Optional[str] = None


class HardwareIntegrationTester:
    """하드웨어 연동 테스터."""

    def __init__(
        self,
        io_board_url: str = "http://localhost:8000",
        camera_driver_url: str = "http://localhost:8003",
        model_url: str = "http://localhost:8002",
        timeout: float = 10.0,
    ):
        self.io_board_url = io_board_url
        self.camera_driver_url = camera_driver_url
        self.model_url = model_url
        self.timeout = timeout

    async def check_service(self, name: str, base_url: str) -> ServiceStatus:
        """서비스 상태 확인."""
        start_time = time.time()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # /health 또는 루트 엔드포인트 시도
                for endpoint in ["/api/health", "/health", "/"]:
                    try:
                        response = await client.get(f"{base_url}{endpoint}")
                        if response.status_code == 200:
                            elapsed = (time.time() - start_time) * 1000
                            return ServiceStatus(
                                name=name,
                                url=base_url,
                                is_healthy=True,
                                response_time_ms=elapsed,
                                details=response.json() if response.headers.get("content-type", "").startswith("application/json") else None,
                            )
                    except Exception:
                        continue

                # 모든 엔드포인트 실패
                elapsed = (time.time() - start_time) * 1000
                return ServiceStatus(
                    name=name,
                    url=base_url,
                    is_healthy=False,
                    response_time_ms=elapsed,
                    error="No health endpoint responded",
                )

        except httpx.TimeoutException:
            return ServiceStatus(
                name=name,
                url=base_url,
                is_healthy=False,
                response_time_ms=self.timeout * 1000,
                error="Connection timeout",
            )
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            return ServiceStatus(
                name=name,
                url=base_url,
                is_healthy=False,
                response_time_ms=elapsed,
                error=str(e),
            )

    async def check_all_connections(self) -> Dict[str, ServiceStatus]:
        """모든 서비스 연결 확인."""
        services = [
            ("io_board", self.io_board_url),
            ("camera_driver", self.camera_driver_url),
            ("model", self.model_url),
        ]

        results = {}
        for name, url in services:
            status = await self.check_service(name, url)
            results[name] = status

            status_str = "OK" if status.is_healthy else "FAIL"
            logger.info(
                f"  [{status_str}] {name} ({url}) - {status.response_time_ms:.1f}ms"
                + (f" - {status.error}" if status.error else "")
            )

        return results

    async def monitor_sse(self, duration: float = 10.0) -> List[Dict]:
        """SSE 이벤트 모니터링."""
        events = []
        sse_url = f"{self.io_board_url}/sse?streams=loadcells,doors"

        logger.info(f"Monitoring SSE events for {duration}s: {sse_url}")

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", sse_url) as response:
                    start_time = time.time()

                    async for line in response.aiter_lines():
                        if time.time() - start_time > duration:
                            break

                        line = line.strip()
                        if not line:
                            continue

                        if line.startswith("event:"):
                            event_type = line[6:].strip()
                        elif line.startswith("data:"):
                            try:
                                data = json.loads(line[5:].strip())
                                event = {
                                    "type": event_type if 'event_type' in dir() else "unknown",
                                    "data": data,
                                    "timestamp": time.time(),
                                }
                                events.append(event)

                                # 변화 이벤트 출력
                                if "changed_indices" in data:
                                    logger.info(
                                        f"  [CHANGE] indices={data.get('changed_indices')}, "
                                        f"deltas={data.get('deltas')}"
                                    )
                                elif "raw_values" in data:
                                    # Update 이벤트는 요약만
                                    pass
                            except json.JSONDecodeError:
                                pass

        except Exception as e:
            logger.error(f"SSE monitoring error: {e}")

        logger.info(f"Captured {len(events)} events")
        return events

    async def capture_zone(self, zone_id: int) -> CaptureResult:
        """특정 Zone 카메라 캡처."""
        start_time = time.time()

        top_ok = False
        side_ok = False
        top_size = None
        side_size = None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Top 카메라 (항상 0)
                try:
                    response = await client.get(
                        f"{self.camera_driver_url}/frame/{TOP_CAMERA_ID}",
                        headers={"Accept": "image/jpeg"},
                    )
                    if response.status_code == 200:
                        top_ok = True
                        # 이미지 크기 추출 시도
                        try:
                            import cv2
                            import numpy as np
                            img = cv2.imdecode(
                                np.frombuffer(response.content, np.uint8),
                                cv2.IMREAD_COLOR
                            )
                            if img is not None:
                                top_size = (img.shape[1], img.shape[0])
                        except ImportError:
                            pass
                except Exception as e:
                    logger.error(f"Top camera capture failed: {e}")

                # Side 카메라
                side_cam_id = ZONE_CAMERA_MAP.get(zone_id, zone_id + 1)
                try:
                    response = await client.get(
                        f"{self.camera_driver_url}/frame/{side_cam_id}",
                        headers={"Accept": "image/jpeg"},
                    )
                    if response.status_code == 200:
                        side_ok = True
                        try:
                            import cv2
                            import numpy as np
                            img = cv2.imdecode(
                                np.frombuffer(response.content, np.uint8),
                                cv2.IMREAD_COLOR
                            )
                            if img is not None:
                                side_size = (img.shape[1], img.shape[0])
                        except ImportError:
                            pass
                except Exception as e:
                    logger.error(f"Side camera (Zone {zone_id}) capture failed: {e}")

        except Exception as e:
            logger.error(f"Capture error: {e}")

        elapsed = (time.time() - start_time) * 1000

        return CaptureResult(
            zone_id=zone_id,
            top_camera_ok=top_ok,
            side_camera_ok=side_ok,
            top_frame_size=top_size,
            side_frame_size=side_size,
            capture_time_ms=elapsed,
        )

    async def scan_all_zones(self) -> List[CaptureResult]:
        """모든 Zone 스캔."""
        results = []

        for zone_id in range(5):
            result = await self.capture_zone(zone_id)
            results.append(result)

            top_status = "OK" if result.top_camera_ok else "FAIL"
            side_status = "OK" if result.side_camera_ok else "FAIL"

            logger.info(
                f"  Zone {zone_id}: Top={top_status} {result.top_frame_size or ''}, "
                f"Side={side_status} {result.side_frame_size or ''}, "
                f"Time={result.capture_time_ms:.1f}ms"
            )

        return results

    async def manual_judge(
        self,
        zone_id: int,
        delta_weight: float,
        loadcell_weights: Optional[List[str]] = None,
        baseline_weights: Optional[List[str]] = None,
    ) -> JudgmentTestResult:
        """수동 판단 테스트."""
        start_time = time.time()

        # 기본 로드셀 값 (delta_weight 반영)
        if loadcell_weights is None:
            loadcell_weights = ["+00000"] * 10
            # Zone의 채널에 변화량 적용
            channels = ZONE_CHANNEL_MAP.get(zone_id, [0, 1])
            for ch in channels:
                # 현재 값 = baseline + delta/2 (각 채널에 분배)
                val = int(delta_weight / len(channels))
                loadcell_weights[ch] = f"+{abs(val):05d}" if val >= 0 else f"-{abs(val):05d}"

        if baseline_weights is None:
            baseline_weights = ["+00000"] * 10

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.model_url}/api/judge",
                    json={
                        "zone_id": zone_id,
                        "delta_weight": delta_weight,
                        "loadcell_weights": loadcell_weights,
                        "baseline_weights": baseline_weights,
                    },
                )

                elapsed = (time.time() - start_time) * 1000

                if response.status_code == 200:
                    data = response.json()
                    return JudgmentTestResult(
                        zone_id=zone_id,
                        delta_weight=delta_weight,
                        products=data.get("products", []),
                        total_price=data.get("totalPrice", 0),
                        status=data.get("status", "unknown"),
                        confidence=data.get("confidence", 0.0),
                        processing_time_ms=elapsed,
                        success=data.get("success", False),
                    )
                else:
                    return JudgmentTestResult(
                        zone_id=zone_id,
                        delta_weight=delta_weight,
                        products=[],
                        total_price=0,
                        status="error",
                        confidence=0.0,
                        processing_time_ms=elapsed,
                        success=False,
                        error=f"HTTP {response.status_code}: {response.text}",
                    )

        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            return JudgmentTestResult(
                zone_id=zone_id,
                delta_weight=delta_weight,
                products=[],
                total_price=0,
                status="error",
                confidence=0.0,
                processing_time_ms=elapsed,
                success=False,
                error=str(e),
            )

    async def realtime_monitor(self, duration: float = 60.0):
        """실시간 모니터링 + 자동 판단."""
        sse_url = f"{self.io_board_url}/sse?streams=loadcells"

        logger.info(f"Starting realtime monitor for {duration}s...")
        logger.info("Waiting for weight changes (threshold: 5g)...")

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", sse_url) as response:
                    start_time = time.time()
                    event_type = None

                    async for line in response.aiter_lines():
                        if time.time() - start_time > duration:
                            break

                        line = line.strip()
                        if not line:
                            continue

                        if line.startswith("event:"):
                            event_type = line[6:].strip()
                        elif line.startswith("data:") and event_type == "loadcell.change":
                            try:
                                data = json.loads(line[5:].strip())
                                changed_indices = data.get("changed_indices", [])
                                deltas = data.get("deltas", [])

                                # Zone 감지
                                for idx in changed_indices:
                                    zone_id = idx // 2  # 채널 0,1 → Zone 0, 채널 2,3 → Zone 1, ...

                                    if zone_id >= 5:
                                        continue

                                    # 해당 Zone의 총 delta 계산
                                    zone_channels = ZONE_CHANNEL_MAP.get(zone_id, [])
                                    total_delta = sum(
                                        deltas[i] for i in zone_channels
                                        if i < len(deltas)
                                    )

                                    if abs(total_delta) < 5:  # 임계값 미만
                                        continue

                                    logger.info(f"\n{'='*50}")
                                    logger.info(f"WEIGHT CHANGE DETECTED!")
                                    logger.info(f"  Zone: {zone_id}")
                                    logger.info(f"  Delta: {total_delta:.1f}g")
                                    logger.info(f"  Direction: {'PICKUP' if total_delta < 0 else 'RETURN'}")

                                    # 자동 판단 요청
                                    result = await self.manual_judge(zone_id, total_delta)

                                    logger.info(f"\n  JUDGMENT RESULT:")
                                    logger.info(f"    Status: {result.status}")
                                    logger.info(f"    Confidence: {result.confidence:.3f}")
                                    if result.products:
                                        for prod in result.products:
                                            logger.info(
                                                f"    Product: {prod.get('name', 'unknown')} x {prod.get('count', 0)} "
                                                f"= {prod.get('totalPrice', 0):,}won"
                                            )
                                    else:
                                        logger.info(f"    No products detected")
                                    logger.info(f"    Processing: {result.processing_time_ms:.1f}ms")
                                    logger.info(f"{'='*50}\n")

                                    break  # 한 Zone만 처리

                            except json.JSONDecodeError:
                                pass

        except Exception as e:
            logger.error(f"Realtime monitor error: {e}")

    async def accuracy_test(
        self,
        zone_id: int,
        repeat: int = 10,
        expected_product: Optional[str] = None,
        delta_weight: float = -365.0,
    ) -> Dict:
        """정확도 테스트."""
        logger.info(f"Running accuracy test: Zone {zone_id}, {repeat} iterations")

        results = []
        success_count = 0
        correct_count = 0

        for i in range(repeat):
            logger.info(f"\n  Iteration {i+1}/{repeat}")

            result = await self.manual_judge(zone_id, delta_weight)
            results.append(asdict(result))

            if result.success:
                success_count += 1

                if expected_product and result.products:
                    detected = result.products[0].get("name", "")
                    if detected == expected_product:
                        correct_count += 1
                        logger.info(f"    [CORRECT] {detected}")
                    else:
                        logger.info(f"    [WRONG] Expected: {expected_product}, Got: {detected}")
                else:
                    logger.info(f"    [OK] {result.products}")
            else:
                logger.info(f"    [FAIL] {result.error or result.status}")

            # 잠시 대기
            await asyncio.sleep(0.5)

        success_rate = success_count / repeat if repeat > 0 else 0
        accuracy = correct_count / repeat if repeat > 0 and expected_product else None

        summary = {
            "zone_id": zone_id,
            "iterations": repeat,
            "success_count": success_count,
            "success_rate": success_rate,
            "correct_count": correct_count if expected_product else None,
            "accuracy": accuracy,
            "delta_weight": delta_weight,
            "expected_product": expected_product,
            "results": results,
        }

        logger.info(f"\n  SUMMARY:")
        logger.info(f"    Success Rate: {success_rate:.1%} ({success_count}/{repeat})")
        if accuracy is not None:
            logger.info(f"    Accuracy: {accuracy:.1%} ({correct_count}/{repeat})")

        return summary


async def main():
    parser = argparse.ArgumentParser(
        description="하드웨어 연동 테스트 - IO Board + Camera + Model"
    )
    parser.add_argument(
        "--io-board-url",
        default="http://localhost:8000",
        help="io_board 서비스 URL"
    )
    parser.add_argument(
        "--camera-url",
        default="http://localhost:8003",
        help="camera_driver 서비스 URL"
    )
    parser.add_argument(
        "--model-url",
        default="http://localhost:8002",
        help="model 서비스 URL"
    )
    parser.add_argument(
        "--check-connection",
        action="store_true",
        help="서비스 연결 상태 확인"
    )
    parser.add_argument(
        "--monitor-sse",
        action="store_true",
        help="SSE 이벤트 모니터링"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="모니터링 시간 (초)"
    )
    parser.add_argument(
        "--capture-zone",
        type=int,
        help="특정 Zone 캡처 테스트 (0-4)"
    )
    parser.add_argument(
        "--scan-all-zones",
        action="store_true",
        help="모든 Zone 스캔"
    )
    parser.add_argument(
        "--manual-judge",
        action="store_true",
        help="수동 판단 테스트"
    )
    parser.add_argument(
        "--zone",
        type=int,
        default=1,
        help="테스트 Zone ID"
    )
    parser.add_argument(
        "--delta",
        type=float,
        default=-365.0,
        help="무게 변화량 (음수: 픽업, 양수: 반환)"
    )
    parser.add_argument(
        "--realtime-monitor",
        action="store_true",
        help="실시간 모니터링 + 자동 판단"
    )
    parser.add_argument(
        "--accuracy-test",
        action="store_true",
        help="정확도 테스트"
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=10,
        help="반복 횟수 (accuracy-test용)"
    )
    parser.add_argument(
        "--expected-product",
        help="예상 상품명 (accuracy-test용)"
    )
    parser.add_argument(
        "--output",
        help="결과 저장 파일 (JSON)"
    )

    args = parser.parse_args()

    tester = HardwareIntegrationTester(
        io_board_url=args.io_board_url,
        camera_driver_url=args.camera_url,
        model_url=args.model_url,
    )

    result = None

    if args.check_connection:
        print("\n" + "=" * 60)
        print("SERVICE CONNECTION CHECK")
        print("=" * 60)
        statuses = await tester.check_all_connections()

        all_ok = all(s.is_healthy for s in statuses.values())
        print("\n" + "-" * 60)
        print(f"Overall: {'ALL OK' if all_ok else 'SOME SERVICES UNAVAILABLE'}")
        print("=" * 60)

        result = {name: asdict(s) for name, s in statuses.items()}

    elif args.monitor_sse:
        print("\n" + "=" * 60)
        print(f"SSE EVENT MONITORING ({args.duration}s)")
        print("=" * 60)
        events = await tester.monitor_sse(args.duration)

        print(f"\nCaptured {len(events)} events")
        result = {"events": events}

    elif args.capture_zone is not None:
        print("\n" + "=" * 60)
        print(f"ZONE {args.capture_zone} CAPTURE TEST")
        print("=" * 60)
        capture_result = await tester.capture_zone(args.capture_zone)

        print(f"\n  Top Camera: {'OK' if capture_result.top_camera_ok else 'FAIL'}")
        if capture_result.top_frame_size:
            print(f"    Size: {capture_result.top_frame_size}")
        print(f"  Side Camera: {'OK' if capture_result.side_camera_ok else 'FAIL'}")
        if capture_result.side_frame_size:
            print(f"    Size: {capture_result.side_frame_size}")
        print(f"  Capture Time: {capture_result.capture_time_ms:.1f}ms")
        print("=" * 60)

        result = asdict(capture_result)

    elif args.scan_all_zones:
        print("\n" + "=" * 60)
        print("ALL ZONES SCAN")
        print("=" * 60)
        scan_results = await tester.scan_all_zones()

        ok_count = sum(1 for r in scan_results if r.top_camera_ok and r.side_camera_ok)
        print("\n" + "-" * 60)
        print(f"Zones OK: {ok_count}/5")
        print("=" * 60)

        result = [asdict(r) for r in scan_results]

    elif args.manual_judge:
        print("\n" + "=" * 60)
        print(f"MANUAL JUDGMENT TEST - Zone {args.zone}, Delta={args.delta}g")
        print("=" * 60)
        judge_result = await tester.manual_judge(args.zone, args.delta)

        print(f"\n  Status: {judge_result.status}")
        print(f"  Success: {judge_result.success}")
        print(f"  Confidence: {judge_result.confidence:.3f}")
        print(f"  Products: {judge_result.products}")
        print(f"  Total Price: {judge_result.total_price:,}won")
        print(f"  Processing: {judge_result.processing_time_ms:.1f}ms")
        if judge_result.error:
            print(f"  Error: {judge_result.error}")
        print("=" * 60)

        result = asdict(judge_result)

    elif args.realtime_monitor:
        print("\n" + "=" * 60)
        print(f"REALTIME MONITORING ({args.duration}s)")
        print("=" * 60)
        await tester.realtime_monitor(args.duration)

    elif args.accuracy_test:
        print("\n" + "=" * 60)
        print(f"ACCURACY TEST - Zone {args.zone}")
        print("=" * 60)
        result = await tester.accuracy_test(
            zone_id=args.zone,
            repeat=args.repeat,
            expected_product=args.expected_product,
            delta_weight=args.delta,
        )

    else:
        # 기본: 연결 확인
        print("\n" + "=" * 60)
        print("HARDWARE INTEGRATION TESTER")
        print("=" * 60)
        print("\nUsage examples:")
        print("  --check-connection     Check all services")
        print("  --monitor-sse          Monitor SSE events")
        print("  --capture-zone 1       Capture Zone 1")
        print("  --scan-all-zones       Scan all 5 zones")
        print("  --manual-judge         Test judgment manually")
        print("  --realtime-monitor     Monitor + auto judge")
        print("  --accuracy-test        Test recognition accuracy")
        print("\nRun with --help for all options")
        print("=" * 60)

    # 결과 저장
    if args.output and result:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
