#!/usr/bin/env python3
"""
테스트 파일 import 검증 스크립트.

실행:
    python verify_imports.py
"""

import sys
import os
import ast
import traceback

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def check_syntax(filepath: str) -> bool:
    """Python 파일의 구문 검사."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        ast.parse(source)
        return True
    except SyntaxError as e:
        print(f"  [SYNTAX ERROR] {filepath}: {e}")
        return False


def check_imports(filepath: str) -> bool:
    """Import 문 검증 (실제 import 시도)."""
    # Temporarily change directory to allow relative imports
    original_dir = os.getcwd()
    file_dir = os.path.dirname(os.path.abspath(filepath))

    try:
        os.chdir(file_dir)

        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()

        tree = ast.parse(source)

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(('import', alias.name))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                for alias in node.names:
                    imports.append(('from', module, alias.name))

        print(f"  Found {len(imports)} imports")
        return True

    except Exception as e:
        print(f"  [IMPORT ERROR] {filepath}: {e}")
        return False
    finally:
        os.chdir(original_dir)


def verify_module_exists(module_path: str) -> bool:
    """모듈 파일 존재 확인."""
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # Convert module path to file path
    parts = module_path.split('.')
    possible_paths = [
        os.path.join(base_dir, *parts) + '.py',
        os.path.join(base_dir, *parts, '__init__.py'),
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return True
    return False


def main():
    """검증 메인 함수."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    tests_dir = os.path.join(base_dir, 'tests')

    print("=" * 60)
    print("Model Service - Test Import Verification")
    print("=" * 60)

    # 1. Check required modules exist
    print("\n[1] Checking required modules...")
    required_modules = [
        'vision.multi_hand_detector',
        'vision.yolo_wrapper',
        'vision.hand_filter',
        'vision.top5_extractor',
        'vision.multi_view_ensemble',
        'engine.event_tracker',
        'engine.advanced',
        'engine.decision_engine',
        'engine.models',
        'weight.count_calculator',
        'weight.multi_zone_monitor',
        'database.product_db',
        'sse_client.event_parser',
        'sse_client.zone_detector',
        'camera.frame_capturer',
        'config',
    ]

    missing = []
    for module in required_modules:
        exists = verify_module_exists(module)
        status = "OK" if exists else "MISSING"
        print(f"  {module}: {status}")
        if not exists:
            missing.append(module)

    if missing:
        print(f"\n  MISSING MODULES: {missing}")

    # 2. Check test file syntax
    print("\n[2] Checking test file syntax...")
    test_files = [
        'test_advanced_scenarios.py',
        'test_decision_engine.py',
        'test_vision.py',
        'test_camera.py',
        'test_sse_client.py',
        'conftest.py',
    ]

    syntax_ok = True
    for test_file in test_files:
        filepath = os.path.join(tests_dir, test_file)
        if os.path.exists(filepath):
            result = check_syntax(filepath)
            status = "OK" if result else "ERROR"
            print(f"  {test_file}: {status}")
            if not result:
                syntax_ok = False
        else:
            print(f"  {test_file}: NOT FOUND")
            syntax_ok = False

    # 3. Try importing test modules
    print("\n[3] Attempting test module imports...")

    try:
        # Add tests directory to path
        sys.path.insert(0, tests_dir)

        # Import conftest first (fixtures)
        import conftest
        print("  conftest: OK")

        # Import vision modules
        from vision.multi_hand_detector import MultiHandDetector, HandCluster
        print("  vision.multi_hand_detector: OK")

        from vision.yolo_wrapper import YOLODetection
        print("  vision.yolo_wrapper: OK")

        # Import engine modules
        from engine.event_tracker import EventTracker, EventDirection
        print("  engine.event_tracker: OK")

        from engine.advanced import (
            ReturnDetector,
            CrossZoneDetector,
            BaselineManager,
            RapidPickupHandler,
        )
        print("  engine.advanced: OK")

        # Import weight modules
        from weight import MultiZoneWeightMonitor
        print("  weight.MultiZoneWeightMonitor: OK")

    except ImportError as e:
        print(f"  IMPORT FAILED: {e}")
        traceback.print_exc()
    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("Verification Complete")
    print("=" * 60)


if __name__ == '__main__':
    main()
