#!/usr/bin/env python3
"""
서비스 정합성 검증 스크립트.

각 Python 서비스의 import가 정상적으로 작동하는지 확인합니다.

실행 방법:
    python verify_services.py
"""

import os
import sys
from pathlib import Path

# Edge_Environment 루트 디렉토리
ROOT_DIR = Path(__file__).parent


def clear_service_modules():
    """서비스 관련 모듈 캐시를 정리합니다."""
    modules_to_remove = []
    for mod_name in sys.modules:
        # core, config, exceptions 등 서비스 모듈 정리
        if any(
            mod_name.startswith(prefix)
            for prefix in ["core", "config", "exceptions", "api", "services"]
        ):
            modules_to_remove.append(mod_name)

    for mod_name in modules_to_remove:
        del sys.modules[mod_name]


def test_service(service_name: str, test_imports: list) -> bool:
    """
    서비스 import 테스트.

    Args:
        service_name: 서비스 이름 (io_board, card_terminal, model, camera_driver, mqtt_client)
        test_imports: 테스트할 import 문 리스트

    Returns:
        성공 여부
    """
    src_dir = ROOT_DIR / "services" / service_name / "src"

    if not src_dir.exists():
        print(f"  [SKIP] src/ 디렉토리 없음: {src_dir}")
        return True

    # 이전 서비스의 모듈 캐시 정리
    clear_service_modules()

    # sys.path에 src 디렉토리 추가
    old_path = sys.path.copy()
    old_cwd = os.getcwd()

    try:
        os.chdir(src_dir)
        # 기존 경로를 유지하면서 src 디렉토리를 맨 앞에 추가
        sys.path = [str(src_dir)] + [p for p in old_path if p != str(src_dir)]

        for import_stmt in test_imports:
            try:
                exec(import_stmt, {})  # 격리된 네임스페이스에서 실행
                print(f"  [OK] {import_stmt}")
            except Exception as e:
                print(f"  [FAIL] {import_stmt}")
                print(f"         Error: {e}")
                return False

        return True

    finally:
        sys.path = old_path
        os.chdir(old_cwd)
        # 테스트 후에도 모듈 캐시 정리
        clear_service_modules()


def main():
    print("=" * 60)
    print("서비스 정합성 검증")
    print("=" * 60)

    results = {}

    # io_board
    print("\n[io_board]")
    results["io_board"] = test_service("io_board", [
        "from core.config import Settings",
        "from core.logging_config import setup_logging, get_logger",
    ])

    # card_terminal
    print("\n[card_terminal]")
    results["card_terminal"] = test_service("card_terminal", [
        "from core.config import Settings",
        "from core.logging_config import setup_logging, get_logger",
        "from exceptions import PaymentGatewayError",
    ])

    # model
    print("\n[model]")
    results["model"] = test_service("model", [
        "from core.config import Settings, config",
        "from core.logging_config import setup_logging, get_logger",
        "from config import ZONE_CHANNEL_MAP, ZONE_CAMERA_MAP",
    ])

    # camera_driver
    print("\n[camera_driver]")
    results["camera_driver"] = test_service("camera_driver", [
        "from core.config import Settings, settings",
        "from core.logging_config import setup_logging, get_logger",
        "from config import ZONE_CAMERA_MAP, ALL_CAMERA_IDS",
    ])

    # mqtt_client
    print("\n[mqtt_client]")
    results["mqtt_client"] = test_service("mqtt_client", [
        "from core.config import Settings, settings",
        "from core.logging_config import setup_logging, get_logger",
        "from config import settings as config_settings",
    ])

    # 결과 요약
    print("\n" + "=" * 60)
    print("검증 결과 요약")
    print("=" * 60)

    all_pass = True
    for service, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {service}: {status}")
        if not passed:
            all_pass = False

    print()
    if all_pass:
        print("모든 서비스 검증 통과!")
        return 0
    else:
        print("일부 서비스 검증 실패. 위의 에러를 확인하세요.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
