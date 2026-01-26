#!/usr/bin/env python3
"""
Camera-Only Testing Script

로드셀 없이 카메라만으로 상품 판단 시스템을 테스트합니다.

사용법:
    # Node.js 서버를 통한 테스트 (권장)
    python test_camera_only.py --mode nodejs --zone 0

    # Model 서비스 직접 테스트
    python test_camera_only.py --mode direct --zone 0

    # 기존 이미지 폴더로 테스트
    python test_camera_only.py --mode folder --folder /path/to/images --zone 0

필요 서비스:
    - Camera Driver (8003)
    - Model Service (8002)
    - Node.js Server (8889) - nodejs 모드 사용 시
"""

import argparse
import requests
import json
import sys
from datetime import datetime


def test_via_nodejs(zone_id: int, include_top: bool = True):
    """Node.js 서버를 통한 카메라 전용 테스트"""
    print(f"\n[Camera-Only Test via Node.js]")
    print(f"Zone: {zone_id}, Include Top: {include_top}")
    print("-" * 50)

    url = "http://localhost:8889/api/camera/test/snapshot-and-judge"
    payload = {
        "zone_id": zone_id,
        "include_top": include_top
    }

    try:
        print("Sending request...")
        response = requests.post(url, json=payload, timeout=30)
        result = response.json()

        if result.get("success"):
            print(f"\n[SUCCESS]")
            print(f"Mode: {result.get('mode')}")
            print(f"Session ID: {result.get('session_id')}")

            snapshot = result.get('snapshot', {})
            print(f"\nSnapshot:")
            print(f"  Path: {snapshot.get('session_path')}")
            if snapshot.get('images'):
                for cam, path in snapshot['images'].items():
                    print(f"  {cam}: {path}")

            judgment = result.get('judgment', {})
            print(f"\nJudgment:")
            print(f"  Status: {judgment.get('status')}")
            print(f"  Confidence: {judgment.get('confidence', 0):.2%}")
            print(f"  Product Count: {judgment.get('productCount', 0)}")

            if judgment.get('products'):
                print(f"\n  Products Detected:")
                for p in judgment['products']:
                    print(f"    - {p.get('name')} x{p.get('count')} "
                          f"(confidence: {p.get('confidence', 0):.2%}, "
                          f"price: {p.get('totalPrice')})")
            else:
                print(f"\n  No products detected")

            weight_info = judgment.get('weightInfo', {})
            print(f"\nWeight Info (not used in camera-only mode):")
            print(f"  Delta: {weight_info.get('delta', 0):.1f}g")
        else:
            print(f"\n[FAILED]")
            print(f"Error: {result.get('error')}")

        return result

    except requests.exceptions.ConnectionError:
        print(f"\n[ERROR] Cannot connect to Node.js server at localhost:8889")
        print("Make sure the Node.js server is running: npm run start")
        return None
    except Exception as e:
        print(f"\n[ERROR] {e}")
        return None


def test_direct_model(zone_id: int, image_folder: str = None,
                      top_image: str = None, side_image: str = None):
    """Model 서비스 직접 테스트"""
    print(f"\n[Camera-Only Test - Direct Model]")
    print(f"Zone: {zone_id}")
    print("-" * 50)

    url = "http://localhost:8002/api/judge"
    payload = {
        "zone_id": zone_id,
        "vision_only": True,
        "weight_data": None,
        "media_paths": {
            "image_folder": image_folder,
            "top_image": top_image,
            "side_image": side_image
        }
    }

    try:
        print(f"Media paths: {json.dumps(payload['media_paths'], indent=2)}")
        print("Sending request...")

        response = requests.post(url, json=payload, timeout=30)
        result = response.json()

        print(f"\n[Result]")
        print(f"Status: {result.get('status')}")
        print(f"Confidence: {result.get('confidence', 0):.2%}")
        print(f"Success: {result.get('success')}")

        if result.get('products'):
            print(f"\nProducts Detected:")
            for p in result['products']:
                print(f"  - {p.get('name')} x{p.get('count')} "
                      f"(confidence: {p.get('confidence', 0):.2%})")
        else:
            print(f"\nNo products detected")

        return result

    except requests.exceptions.ConnectionError:
        print(f"\n[ERROR] Cannot connect to Model service at localhost:8002")
        print("Make sure the Model service is running")
        return None
    except Exception as e:
        print(f"\n[ERROR] {e}")
        return None


def check_services():
    """서비스 상태 확인"""
    print("\n[Service Health Check]")
    print("-" * 50)

    services = {
        "Camera Driver": "http://localhost:8003/api/health",
        "Model Service": "http://localhost:8002/api/health",
        "Node.js Server": "http://localhost:8889/health"
    }

    all_healthy = True
    for name, url in services.items():
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                print(f"  {name}: OK")
            else:
                print(f"  {name}: UNHEALTHY (status {response.status_code})")
                all_healthy = False
        except requests.exceptions.ConnectionError:
            print(f"  {name}: NOT RUNNING")
            all_healthy = False
        except Exception as e:
            print(f"  {name}: ERROR ({e})")
            all_healthy = False

    return all_healthy


def main():
    parser = argparse.ArgumentParser(
        description="Camera-Only Testing for Smart Vending Machine"
    )
    parser.add_argument(
        "--mode", choices=["nodejs", "direct", "folder", "check"],
        default="nodejs",
        help="Test mode: nodejs (via Node.js), direct (Model API), folder (from saved images), check (health check)"
    )
    parser.add_argument(
        "--zone", type=int, default=0,
        help="Zone ID (0-4)"
    )
    parser.add_argument(
        "--folder", type=str,
        help="Image folder path (for folder mode)"
    )
    parser.add_argument(
        "--top-image", type=str,
        help="Top camera image path"
    )
    parser.add_argument(
        "--side-image", type=str,
        help="Side camera image path"
    )
    parser.add_argument(
        "--no-top", action="store_true",
        help="Exclude top camera"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  CHAI Smart Vending - Camera-Only Test")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if args.mode == "check":
        check_services()
        return

    # 서비스 상태 확인
    if not check_services():
        print("\n[WARNING] Some services are not running!")
        if args.mode == "nodejs":
            print("Node.js mode requires all services to be running.")
            return

    if args.mode == "nodejs":
        test_via_nodejs(args.zone, not args.no_top)
    elif args.mode == "direct":
        test_direct_model(
            args.zone,
            args.folder,
            args.top_image,
            args.side_image
        )
    elif args.mode == "folder":
        if not args.folder and not args.top_image and not args.side_image:
            print("[ERROR] folder mode requires --folder or image paths")
            return
        test_direct_model(
            args.zone,
            args.folder,
            args.top_image,
            args.side_image
        )


if __name__ == "__main__":
    main()
