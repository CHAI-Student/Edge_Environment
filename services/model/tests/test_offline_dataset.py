"""
오프라인 테스트: pt 파일 + 테스트 데이터셋 기반 Vision 파이프라인 테스트.

로드셀 값은 항상 정확하다고 가정하고, Vision 파이프라인만 테스트합니다.

사용법:
    # 기본 실행 (전체 세션 테스트)
    python -m tests.test_offline_dataset

    # 특정 세션만 테스트
    python -m tests.test_offline_dataset --session 20260116_180419

    # 특정 프레임만 테스트
    python -m tests.test_offline_dataset --session 20260116_180419 --frame 10

    # 결과 저장 (JSON)
    python -m tests.test_offline_dataset --output results.json

    # 상세 모드 (디텍션 시각화)
    python -m tests.test_offline_dataset --visualize --output-dir ./viz_results
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

import cv2
import numpy as np

# Windows 바로가기(.lnk) 해결을 위한 유틸리티
def resolve_shortcut(lnk_path: str) -> Optional[str]:
    """Windows 바로가기(.lnk) 파일의 실제 대상 경로 반환."""
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(lnk_path)
        target = shortcut.TargetPath
        if target and os.path.exists(target):
            return target
    except ImportError:
        # win32com이 없는 경우 무시
        pass
    except Exception:
        pass
    return None

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import config, ZONE_CAMERA_MAP, TOP_CAMERA_ID

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    """단일 Detection 결과."""
    class_id: int
    class_name: str
    confidence: float
    bbox: List[float]  # [x1, y1, x2, y2]
    is_hand: bool = False


@dataclass
class FrameTestResult:
    """프레임 테스트 결과."""
    session_id: str
    frame_number: int
    top_detections: List[DetectionResult]
    side_detections: List[DetectionResult]
    top_hands: int
    side_hands: int
    top_products: int
    side_products: int
    ensemble_candidates: List[Dict]
    final_product: Optional[str]
    final_confidence: float
    processing_time_ms: float


@dataclass
class SessionTestResult:
    """세션 전체 테스트 결과."""
    session_id: str
    total_frames: int
    processed_frames: int
    detection_rate: float
    avg_confidence: float
    avg_processing_time_ms: float
    frame_results: List[FrameTestResult]


class OfflineDatasetTester:
    """오프라인 데이터셋 테스터."""

    def __init__(
        self,
        model_path: str,
        test_dataset_path: str,
        confidence_threshold: float = 0.01,
        visualize: bool = False,
        output_dir: Optional[str] = None,
    ):
        self.model_path = Path(model_path)
        self.test_dataset_path = Path(test_dataset_path)
        self.confidence_threshold = confidence_threshold
        self.visualize = visualize
        self.output_dir = Path(output_dir) if output_dir else None

        self.model = None
        self.class_names = {}

        # 출력 디렉토리 생성
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Model path: {self.model_path}")
        logger.info(f"Test dataset: {self.test_dataset_path}")

    def load_model(self) -> bool:
        """YOLO 모델 로드."""
        try:
            from ultralytics import YOLO

            if not self.model_path.exists():
                logger.error(f"Model file not found: {self.model_path}")
                return False

            logger.info(f"Loading YOLO model: {self.model_path}")
            self.model = YOLO(str(self.model_path))

            # 클래스 이름 추출
            if hasattr(self.model, 'names'):
                self.class_names = self.model.names
                logger.info(f"Loaded {len(self.class_names)} classes")
                for idx, name in list(self.class_names.items())[:10]:
                    logger.info(f"  Class {idx}: {name}")
                if len(self.class_names) > 10:
                    logger.info(f"  ... and {len(self.class_names) - 10} more classes")

            return True
        except ImportError:
            logger.error("ultralytics not installed. Run: pip install ultralytics")
            return False
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False

    def get_sessions(self) -> List[str]:
        """테스트 데이터셋의 세션 목록 (바로가기 포함)."""
        sessions = []
        self._session_paths = {}  # 세션 ID -> 실제 경로 매핑

        if self.test_dataset_path.exists():
            for item in self.test_dataset_path.iterdir():
                if item.is_dir() and not item.name.startswith('.'):
                    # 일반 폴더
                    sessions.append(item.name)
                    self._session_paths[item.name] = item
                elif item.suffix == '.lnk':
                    # Windows 바로가기
                    target = resolve_shortcut(str(item))
                    if target:
                        session_name = item.stem  # .lnk 제외한 이름
                        sessions.append(session_name)
                        self._session_paths[session_name] = Path(target)
                        logger.debug(f"Resolved shortcut: {item.name} -> {target}")

        return sorted(sessions)

    def _get_session_path(self, session_id: str) -> Path:
        """세션 ID에 해당하는 실제 경로 반환."""
        if hasattr(self, '_session_paths') and session_id in self._session_paths:
            return self._session_paths[session_id]
        return self.test_dataset_path / session_id

    def get_frame_pairs(self, session_id: str) -> List[Tuple[int, str, str]]:
        """세션의 Top/Side 프레임 쌍 목록 반환.

        Returns:
            List of (frame_number, top_path, side_path)
        """
        base_path = self._get_session_path(session_id)
        session_path = base_path / "images"
        cam_0_path = session_path / "cam_0"
        cam_2_path = session_path / "cam_2"

        pairs = []

        if not cam_0_path.exists() or not cam_2_path.exists():
            logger.warning(f"Camera folders not found for session {session_id}")
            return pairs

        # Top 카메라 프레임 목록
        top_frames = {}
        for f in cam_0_path.glob("frame_*.jpg"):
            # frame_000001.jpg -> 1
            try:
                num = int(f.stem.split('_')[1])
                top_frames[num] = str(f)
            except (IndexError, ValueError):
                continue

        # Side 카메라 프레임 목록
        side_frames = {}
        for f in cam_2_path.glob("frame_*.jpg"):
            try:
                num = int(f.stem.split('_')[1])
                side_frames[num] = str(f)
            except (IndexError, ValueError):
                continue

        # 매칭된 쌍만 사용
        common_frames = sorted(set(top_frames.keys()) & set(side_frames.keys()))

        for num in common_frames:
            pairs.append((num, top_frames[num], side_frames[num]))

        return pairs

    def detect(self, image: np.ndarray) -> List[DetectionResult]:
        """이미지에서 객체 감지."""
        if self.model is None:
            return []

        results = self.model(image, conf=self.confidence_threshold, verbose=False)
        detections = []

        for r in results:
            if r.boxes is None:
                continue

            for i, box in enumerate(r.boxes):
                cls_id = int(box.cls[0].item())
                conf = float(box.conf[0].item())
                xyxy = box.xyxy[0].tolist()

                class_name = self.class_names.get(cls_id, f"class_{cls_id}")
                is_hand = class_name.lower() == "hand" or cls_id == config.hand_class_id

                detections.append(DetectionResult(
                    class_id=cls_id,
                    class_name=class_name,
                    confidence=conf,
                    bbox=xyxy,
                    is_hand=is_hand,
                ))

        return detections

    def filter_by_hand_proximity(
        self,
        detections: List[DetectionResult],
        max_distance: float = 150.0
    ) -> List[DetectionResult]:
        """손 근처의 상품만 필터링."""
        hands = [d for d in detections if d.is_hand]
        products = [d for d in detections if not d.is_hand]

        if not hands:
            # 손이 없으면 모든 상품 반환
            return products

        filtered = []
        for hand in hands:
            hand_center = (
                (hand.bbox[0] + hand.bbox[2]) / 2,
                (hand.bbox[1] + hand.bbox[3]) / 2
            )

            # 가장 가까운 상품 찾기
            min_dist = float('inf')
            nearest = None

            for prod in products:
                prod_center = (
                    (prod.bbox[0] + prod.bbox[2]) / 2,
                    (prod.bbox[1] + prod.bbox[3]) / 2
                )
                dist = ((hand_center[0] - prod_center[0]) ** 2 +
                       (hand_center[1] - prod_center[1]) ** 2) ** 0.5

                if dist < min_dist and dist <= max_distance:
                    min_dist = dist
                    nearest = prod

            if nearest and nearest not in filtered:
                filtered.append(nearest)

        return filtered

    def ensemble_results(
        self,
        top_products: List[DetectionResult],
        side_products: List[DetectionResult],
    ) -> List[Dict]:
        """Top + Side 카메라 결과 앙상블."""
        class_scores = {}

        # Top 카메라 결과 집계
        for prod in top_products:
            if prod.class_name not in class_scores:
                class_scores[prod.class_name] = {"top": 0.0, "side": 0.0, "class_id": prod.class_id}
            class_scores[prod.class_name]["top"] = max(
                class_scores[prod.class_name]["top"], prod.confidence
            )

        # Side 카메라 결과 집계
        for prod in side_products:
            if prod.class_name not in class_scores:
                class_scores[prod.class_name] = {"top": 0.0, "side": 0.0, "class_id": prod.class_id}
            class_scores[prod.class_name]["side"] = max(
                class_scores[prod.class_name]["side"], prod.confidence
            )

        # 앙상블 스코어 계산
        results = []
        for class_name, scores in class_scores.items():
            top_conf = scores["top"]
            side_conf = scores["side"]

            # 양쪽에서 감지되면 보너스
            if top_conf > 0 and side_conf > 0:
                combined = (
                    top_conf * config.top_weight +
                    side_conf * config.side_weight +
                    config.common_class_bonus
                )
                vote_count = 2
            elif top_conf > 0:
                combined = top_conf * config.top_weight
                vote_count = 1
            else:
                combined = side_conf * config.side_weight
                vote_count = 1

            combined = min(combined, 1.0)

            results.append({
                "class_id": scores["class_id"],
                "class_name": class_name,
                "top_confidence": top_conf,
                "side_confidence": side_conf,
                "combined_confidence": combined,
                "vote_count": vote_count,
                "is_consensus": vote_count == 2,
            })

        # combined_confidence 내림차순 정렬
        results.sort(key=lambda x: x["combined_confidence"], reverse=True)

        return results[:config.top_k]

    def visualize_detections(
        self,
        image: np.ndarray,
        detections: List[DetectionResult],
        title: str = ""
    ) -> np.ndarray:
        """감지 결과 시각화."""
        vis = image.copy()

        for det in detections:
            x1, y1, x2, y2 = [int(v) for v in det.bbox]

            # 손은 파란색, 상품은 초록색
            color = (255, 0, 0) if det.is_hand else (0, 255, 0)

            cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)

            label = f"{det.class_name}: {det.confidence:.2f}"
            cv2.putText(vis, label, (x1, y1 - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        if title:
            cv2.putText(vis, title, (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)

        return vis

    def test_frame(
        self,
        session_id: str,
        frame_number: int,
        top_path: str,
        side_path: str,
    ) -> Optional[FrameTestResult]:
        """단일 프레임 쌍 테스트."""
        start_time = time.time()

        # 이미지 로드
        top_img = cv2.imread(top_path)
        side_img = cv2.imread(side_path)

        if top_img is None or side_img is None:
            logger.warning(f"Failed to load images for frame {frame_number}")
            return None

        # 감지 수행
        top_detections = self.detect(top_img)
        side_detections = self.detect(side_img)

        # 손/상품 분리
        top_hands = [d for d in top_detections if d.is_hand]
        top_products_raw = [d for d in top_detections if not d.is_hand]
        side_hands = [d for d in side_detections if d.is_hand]
        side_products_raw = [d for d in side_detections if not d.is_hand]

        # 손 근접 필터링
        top_filtered = self.filter_by_hand_proximity(top_detections)
        side_filtered = self.filter_by_hand_proximity(side_detections)

        # 앙상블
        ensemble = self.ensemble_results(top_filtered, side_filtered)

        # 최종 결과
        final_product = ensemble[0]["class_name"] if ensemble else None
        final_confidence = ensemble[0]["combined_confidence"] if ensemble else 0.0

        processing_time = (time.time() - start_time) * 1000

        result = FrameTestResult(
            session_id=session_id,
            frame_number=frame_number,
            top_detections=[asdict(d) for d in top_detections],
            side_detections=[asdict(d) for d in side_detections],
            top_hands=len(top_hands),
            side_hands=len(side_hands),
            top_products=len(top_products_raw),
            side_products=len(side_products_raw),
            ensemble_candidates=ensemble,
            final_product=final_product,
            final_confidence=final_confidence,
            processing_time_ms=processing_time,
        )

        # 시각화
        if self.visualize and self.output_dir:
            top_vis = self.visualize_detections(
                top_img, top_detections, f"Top Cam - Frame {frame_number}"
            )
            side_vis = self.visualize_detections(
                side_img, side_detections, f"Side Cam - Frame {frame_number}"
            )

            # 결합 이미지
            combined = np.hstack([top_vis, side_vis])

            out_path = self.output_dir / session_id / f"frame_{frame_number:06d}_vis.jpg"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out_path), combined)

        return result

    def test_session(
        self,
        session_id: str,
        frame_numbers: Optional[List[int]] = None,
    ) -> SessionTestResult:
        """세션 전체 테스트."""
        frame_pairs = self.get_frame_pairs(session_id)

        if not frame_pairs:
            logger.warning(f"No frame pairs found for session {session_id}")
            return SessionTestResult(
                session_id=session_id,
                total_frames=0,
                processed_frames=0,
                detection_rate=0.0,
                avg_confidence=0.0,
                avg_processing_time_ms=0.0,
                frame_results=[],
            )

        # 특정 프레임만 테스트
        if frame_numbers:
            frame_pairs = [
                (num, top, side) for num, top, side in frame_pairs
                if num in frame_numbers
            ]

        results = []
        total_confidence = 0.0
        total_time = 0.0
        detection_count = 0

        logger.info(f"Testing session {session_id} with {len(frame_pairs)} frames")

        for num, top_path, side_path in frame_pairs:
            result = self.test_frame(session_id, num, top_path, side_path)

            if result:
                results.append(result)
                total_time += result.processing_time_ms

                if result.final_product:
                    detection_count += 1
                    total_confidence += result.final_confidence

                logger.info(
                    f"  Frame {num}: {result.final_product or 'No detection'} "
                    f"(conf={result.final_confidence:.3f}, time={result.processing_time_ms:.1f}ms)"
                )

        processed = len(results)
        detection_rate = detection_count / processed if processed > 0 else 0.0
        avg_confidence = total_confidence / detection_count if detection_count > 0 else 0.0
        avg_time = total_time / processed if processed > 0 else 0.0

        return SessionTestResult(
            session_id=session_id,
            total_frames=len(frame_pairs),
            processed_frames=processed,
            detection_rate=detection_rate,
            avg_confidence=avg_confidence,
            avg_processing_time_ms=avg_time,
            frame_results=results,
        )

    def run_all_tests(self) -> Dict:
        """전체 테스트 실행."""
        if not self.load_model():
            return {"error": "Failed to load model"}

        sessions = self.get_sessions()

        if not sessions:
            return {"error": "No sessions found in test dataset"}

        logger.info(f"Found {len(sessions)} sessions: {sessions}")

        all_results = {
            "model_path": str(self.model_path),
            "test_dataset": str(self.test_dataset_path),
            "num_classes": len(self.class_names),
            "class_names": self.class_names,
            "sessions": {},
            "summary": {
                "total_sessions": len(sessions),
                "total_frames": 0,
                "total_detections": 0,
                "overall_detection_rate": 0.0,
                "overall_avg_confidence": 0.0,
                "overall_avg_time_ms": 0.0,
            }
        }

        total_frames = 0
        total_detections = 0
        total_confidence = 0.0
        total_time = 0.0

        for session_id in sessions:
            result = self.test_session(session_id)
            all_results["sessions"][session_id] = {
                "total_frames": result.total_frames,
                "processed_frames": result.processed_frames,
                "detection_rate": result.detection_rate,
                "avg_confidence": result.avg_confidence,
                "avg_processing_time_ms": result.avg_processing_time_ms,
            }

            total_frames += result.processed_frames
            detection_count = int(result.detection_rate * result.processed_frames)
            total_detections += detection_count
            total_confidence += result.avg_confidence * detection_count
            total_time += result.avg_processing_time_ms * result.processed_frames

        # 전체 통계
        all_results["summary"]["total_frames"] = total_frames
        all_results["summary"]["total_detections"] = total_detections
        all_results["summary"]["overall_detection_rate"] = (
            total_detections / total_frames if total_frames > 0 else 0.0
        )
        all_results["summary"]["overall_avg_confidence"] = (
            total_confidence / total_detections if total_detections > 0 else 0.0
        )
        all_results["summary"]["overall_avg_time_ms"] = (
            total_time / total_frames if total_frames > 0 else 0.0
        )

        return all_results


def main():
    parser = argparse.ArgumentParser(
        description="오프라인 데이터셋 테스트 - Vision 파이프라인"
    )
    parser.add_argument(
        "--model",
        default=r"C:\Users\user\Desktop\VOICE\2026\crk\win_pc_test_sw2io_board\siyeon_best.pt",
        help="YOLO 모델 경로"
    )
    parser.add_argument(
        "--dataset",
        default=r"C:\Users\user\Desktop\VOICE\2026\crk\win_pc_test_sw2io_board\test_dataset",
        help="테스트 데이터셋 경로"
    )
    parser.add_argument(
        "--session",
        help="특정 세션 ID (지정하지 않으면 전체 세션 테스트)"
    )
    parser.add_argument(
        "--frame",
        type=int,
        help="특정 프레임 번호 (session과 함께 사용)"
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.01,
        help="감지 confidence 임계값 (기본: 0.01)"
    )
    parser.add_argument(
        "--output",
        help="결과 JSON 파일 경로"
    )
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="감지 결과 시각화"
    )
    parser.add_argument(
        "--output-dir",
        help="시각화 결과 저장 디렉토리"
    )

    args = parser.parse_args()

    tester = OfflineDatasetTester(
        model_path=args.model,
        test_dataset_path=args.dataset,
        confidence_threshold=args.confidence,
        visualize=args.visualize,
        output_dir=args.output_dir,
    )

    if args.session:
        # 특정 세션 테스트
        if not tester.load_model():
            sys.exit(1)

        frame_numbers = [args.frame] if args.frame else None
        result = tester.test_session(args.session, frame_numbers)

        print("\n" + "=" * 60)
        print(f"Session: {result.session_id}")
        print(f"Frames: {result.processed_frames}/{result.total_frames}")
        print(f"Detection Rate: {result.detection_rate:.1%}")
        print(f"Avg Confidence: {result.avg_confidence:.3f}")
        print(f"Avg Time: {result.avg_processing_time_ms:.1f}ms")
        print("=" * 60)

        # 세부 결과 출력
        for fr in result.frame_results:
            print(f"  Frame {fr.frame_number}: {fr.final_product or '-'} "
                  f"(conf={fr.final_confidence:.3f})")
    else:
        # 전체 테스트
        results = tester.run_all_tests()

        if "error" in results:
            logger.error(results["error"])
            sys.exit(1)

        # 요약 출력
        print("\n" + "=" * 60)
        print("OFFLINE DATASET TEST RESULTS")
        print("=" * 60)
        print(f"Model: {results['model_path']}")
        print(f"Classes: {results['num_classes']}")
        print("-" * 60)

        for session_id, session_result in results["sessions"].items():
            print(f"\n[{session_id}]")
            print(f"  Frames: {session_result['processed_frames']}/{session_result['total_frames']}")
            print(f"  Detection Rate: {session_result['detection_rate']:.1%}")
            print(f"  Avg Confidence: {session_result['avg_confidence']:.3f}")
            print(f"  Avg Time: {session_result['avg_processing_time_ms']:.1f}ms")

        print("\n" + "-" * 60)
        summary = results["summary"]
        print("SUMMARY:")
        print(f"  Total Sessions: {summary['total_sessions']}")
        print(f"  Total Frames: {summary['total_frames']}")
        print(f"  Total Detections: {summary['total_detections']}")
        print(f"  Overall Detection Rate: {summary['overall_detection_rate']:.1%}")
        print(f"  Overall Avg Confidence: {summary['overall_avg_confidence']:.3f}")
        print(f"  Overall Avg Time: {summary['overall_avg_time_ms']:.1f}ms")
        print("=" * 60)

        # 결과 저장
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
