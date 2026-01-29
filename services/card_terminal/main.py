"""PM2 호환 진입점 - Card Terminal Service."""
import os
import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    # src 디렉토리를 작업 디렉토리와 import 경로로 설정
    src_dir = Path(__file__).parent / "src"
    os.chdir(src_dir)
    sys.path.insert(0, str(src_dir))

    # src/main.py를 __main__으로 실행
    runpy.run_path("main.py", run_name="__main__")
