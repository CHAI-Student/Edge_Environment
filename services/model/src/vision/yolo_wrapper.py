"""
YOLO Wrapper for Product Detection.

실제 YOLO 출력 형식:
    det[0] xyxy=[258.72, 47.65, 315.12, 113.97] conf=0.788 cls=0 name=hand
    det[1] xyxy=[257.67, 75.54, 284.33, 110.22] conf=0.492 cls=109 name=BAG_DALGWANG_DONUT_CHOCO_45G

파싱하여 YOLODetection 객체 리스트로 변환.

CUDA/TensorRT 지원:
    - Windows (개발): .pt 모델 + CPU/CUDA
    - Jetson (배포): .engine 모델 + CUDA (TensorRT)
    - 자동 fallback: .engine 요청 시 CUDA 없으면 .pt로 전환

사용 예시:
    wrapper = YOLOWrapper(model_path="best.pt")
    detections = wrapper.detect(image)
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional, Any
import logging
import os

import numpy as np

from config import config

logger = logging.getLogger(__name__)


@dataclass
class YOLODetection:
    """
    YOLO 감지 결과.

    실제 YOLO 출력 형식과 1:1 매핑.

    Attributes:
        xyxy: Bounding box [x1, y1, x2, y2] (픽셀)
        conf: Confidence (0.0 ~ 1.0)
        cls: Class ID (0=hand, 1+=products)
        name: Class name (예: "hand", "chickenmayo_rice")
    """
    xyxy: Tuple[float, float, float, float]  # x1, y1, x2, y2
    conf: float
    cls: int
    name: str

    @property
    def x1(self) -> float:
        return self.xyxy[0]

    @property
    def y1(self) -> float:
        return self.xyxy[1]

    @property
    def x2(self) -> float:
        return self.xyxy[2]

    @property
    def y2(self) -> float:
        return self.xyxy[3]

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def center(self) -> Tuple[float, float]:
        """Bounding box 중심점."""
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2

    @property
    def area(self) -> float:
        """Bounding box 면적."""
        return self.width * self.height

    @property
    def is_hand(self) -> bool:
        """손인지 여부 (cls == 0)."""
        return self.cls == 0

    @property
    def is_product(self) -> bool:
        """상품인지 여부 (cls > 0)."""
        return self.cls > 0

    def distance_to(self, other: "YOLODetection") -> float:
        """다른 Detection과의 중심점 거리 (픽셀)."""
        cx1, cy1 = self.center
        cx2, cy2 = other.center
        return ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5

    def iou(self, other: "YOLODetection") -> float:
        """IoU (Intersection over Union) 계산."""
        xi1 = max(self.x1, other.x1)
        yi1 = max(self.y1, other.y1)
        xi2 = min(self.x2, other.x2)
        yi2 = min(self.y2, other.y2)

        if xi2 <= xi1 or yi2 <= yi1:
            return 0.0

        intersection = (xi2 - xi1) * (yi2 - yi1)
        union = self.area + other.area - intersection

        return intersection / union if union > 0 else 0.0

    def to_dict(self) -> dict:
        """딕셔너리 변환."""
        return {
            "xyxy": list(self.xyxy),
            "conf": round(self.conf, 4),
            "cls": self.cls,
            "name": self.name,
            "center": list(self.center),
            "area": round(self.area, 2),
            "is_hand": self.is_hand,
        }


class YOLOWrapper:
    """
    YOLO 모델 래퍼.

    YOLO 추론 결과를 YOLODetection 리스트로 변환.
    PyTorch (.pt) 및 TensorRT (.engine) 모델 모두 지원.

    Attributes:
        model: YOLO 모델 (ultralytics)
        conf_threshold: 최소 confidence (기본값 0.01, 매우 낮게)
        device: 추론 디바이스 ("cuda", "cpu")
        is_tensorrt: TensorRT 모델 여부
    """

    HAND_CLASS_ID = 0  # 손 클래스 ID

    def __init__(
        self,
        model_path: Optional[str] = None,
        conf_threshold: float = 0.01,
        device: str = "auto",  # auto: CUDA if available, else CPU
    ):
        """
        YOLO 래퍼 초기화.

        Args:
            model_path: YOLO 모델 경로 (.pt 또는 .engine 파일)
            conf_threshold: 최소 confidence (기본값 0.01)
            device: 추론 디바이스 (TensorRT는 항상 cuda)
        """
        self.model = None
        self.model_path = model_path or config.yolo_model_path
        self.conf_threshold = conf_threshold
        self.device = device
        self.class_names: dict = {}
        self._loaded = False
        self.is_tensorrt = False  # load() 시 결정됨
        self._cuda_available = False  # load() 시 결정됨

    def load(self) -> bool:
        """
        YOLO 모델 로드 (CUDA/TensorRT 자동 감지).

        .pt (PyTorch) 또는 .engine (TensorRT) 파일을 로드합니다.
        TensorRT 모델은 Jetson Orin Nano에서 최적화된 추론을 제공합니다.

        자동 fallback 지원:
            - .engine 요청 + CUDA 없음 → .pt로 자동 전환
            - .pt 요청 + CUDA 있고 .engine 존재 → .engine 사용

        Returns:
            성공 여부
        """
        if self._loaded:
            return True

        try:
            from ultralytics import YOLO
            import torch

            # 1. CUDA 환경 체크 및 초기화
            self._cuda_available = self._init_cuda()

            # 2. 모델 경로 해석 (fallback 처리)
            resolved_path = self._resolve_model_path(self._cuda_available)
            self.is_tensorrt = resolved_path.endswith(".engine")

            # 3. Device 결정
            if self.is_tensorrt:
                if not self._cuda_available:
                    logger.error("TensorRT requires CUDA but CUDA is not available")
                    return False
                self.device = "cuda"
            else:
                if self.device == "auto":
                    self.device = "cuda" if self._cuda_available else "cpu"
                logger.info(f"Auto-selected device: {self.device}")

            # 4. 모델 로드
            logger.info(f"Loading model: {resolved_path} (device={self.device})")
            self.model = YOLO(resolved_path)

            # TensorRT가 아닌 경우에만 device 이동
            # TensorRT 모델은 이미 GPU에 최적화되어 있음
            if not self.is_tensorrt:
                self.model.to(self.device)

            self.class_names = self.model.names
            self._loaded = True

            model_type = "TensorRT" if self.is_tensorrt else "PyTorch"
            logger.info(
                f"YOLO loaded ({model_type}): {len(self.class_names)} classes, device={self.device}"
            )
            return True
        except ImportError:
            logger.warning("ultralytics not installed. Use parse_results() for manual parsing.")
            return False
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}", exc_info=True)
            return False

    def _init_cuda(self) -> bool:
        """
        CUDA 환경 초기화 및 검증.

        Returns:
            CUDA 사용 가능 여부
        """
        try:
            import torch

            if not torch.cuda.is_available():
                logger.info("CUDA not available, using CPU")
                return False

            # CUDA 컨텍스트 초기화 (lazy init 강제)
            torch.cuda.init()
            device_name = torch.cuda.get_device_name(0)
            cuda_version = torch.version.cuda
            logger.info(f"CUDA initialized: {device_name} (CUDA {cuda_version})")
            return True
        except Exception as e:
            logger.warning(f"CUDA init failed: {e}")
            return False

    def _resolve_model_path(self, cuda_available: bool) -> str:
        """
        모델 경로 해석 및 fallback 처리.

        Args:
            cuda_available: CUDA 사용 가능 여부

        Returns:
            실제 사용할 모델 경로
        """
        original_path = self.model_path

        # 서비스 디렉토리 기준 (services/model/src/vision -> services/model)
        service_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        # 프로젝트 루트 (services/model -> Edge_Environment)
        project_root = os.path.dirname(os.path.dirname(service_dir))

        # 1. 절대 경로이고 파일이 존재하면 그대로 사용
        if os.path.isabs(original_path):
            if os.path.exists(original_path):
                logger.debug(f"Using absolute path: {original_path}")
                return original_path
            # 절대 경로지만 파일이 없으면 fallback 시도
            logger.warning(f"Absolute path not found: {original_path}")
        else:
            # 2. 상대 경로 해석 (프로젝트 루트 기준)
            full_path = os.path.join(project_root, original_path)
            if os.path.exists(full_path):
                logger.debug(f"Resolved relative path: {original_path} -> {full_path}")
                return full_path
            logger.warning(f"Relative path not found: {full_path}")

        # 3. Fallback: .engine -> .pt (CUDA 없을 경우)
        if original_path.endswith(".engine") and not cuda_available:
            pt_path = original_path.replace(".engine", ".pt")

            # 절대 경로 fallback
            if os.path.isabs(pt_path) and os.path.exists(pt_path):
                logger.warning(f"Falling back to .pt (no CUDA): {pt_path}")
                return pt_path

            # 상대 경로 fallback
            pt_full = os.path.join(project_root, pt_path)
            if os.path.exists(pt_full):
                logger.warning(f"Falling back to .pt (no CUDA): {pt_full}")
                return pt_full

        # 4. Fallback: .pt -> .engine (CUDA 있고 .engine 파일이 존재할 경우)
        if original_path.endswith(".pt") and cuda_available:
            engine_path = original_path.replace(".pt", ".engine")

            # 절대 경로 fallback
            if os.path.isabs(engine_path) and os.path.exists(engine_path):
                logger.info(f"Using TensorRT engine (auto-detected): {engine_path}")
                return engine_path

            # 상대 경로 fallback
            engine_full = os.path.join(project_root, engine_path)
            if os.path.exists(engine_full):
                logger.info(f"Using TensorRT engine (auto-detected): {engine_full}")
                return engine_full

        # 5. 원래 경로 반환 (에러는 YOLO 로드 시 발생)
        if os.path.isabs(original_path):
            return original_path
        return os.path.join(project_root, original_path)

    def detect(self, image: np.ndarray) -> List[YOLODetection]:
        """
        이미지에서 객체 감지.

        Args:
            image: numpy array (BGR) 또는 이미지 경로

        Returns:
            YOLODetection 리스트
        """
        if not self._loaded:
            if not self.load():
                return []

        if self.model is None:
            logger.error("YOLO model not loaded")
            return []

        try:
            results = self.model.predict(
                image,
                conf=self.conf_threshold,
                verbose=False,
            )
            return self.parse_results(results[0], self.class_names)
        except Exception as e:
            logger.error(f"YOLO detection failed: {e}")
            return []

    @staticmethod
    def parse_results(
        result: Any,
        class_names: Optional[dict] = None,
    ) -> List[YOLODetection]:
        """
        YOLO Results 객체 파싱.

        Args:
            result: YOLO Results 객체 (results[0])
            class_names: {cls_id: name} 매핑

        Returns:
            YOLODetection 리스트
        """
        detections = []

        if not hasattr(result, 'boxes') or result.boxes is None:
            return detections

        boxes = result.boxes
        names = class_names or getattr(result, 'names', {})

        for i in range(len(boxes)):
            xyxy = boxes.xyxy[i].tolist() if hasattr(boxes.xyxy[i], 'tolist') else list(boxes.xyxy[i])
            conf = float(boxes.conf[i])
            cls_id = int(boxes.cls[i])
            name = names.get(cls_id, f"class_{cls_id}")

            det = YOLODetection(
                xyxy=tuple(xyxy),
                conf=conf,
                cls=cls_id,
                name=name,
            )
            detections.append(det)

        return detections

    @staticmethod
    def parse_detection_list(
        detection_data: List[dict],
    ) -> List[YOLODetection]:
        """
        딕셔너리 리스트에서 YOLODetection 파싱.

        테스트용 또는 외부 API에서 받은 데이터 파싱.

        Args:
            detection_data: [{"xyxy": [...], "conf": ..., "cls": ..., "name": ...}, ...]

        Returns:
            YOLODetection 리스트
        """
        detections = []

        for d in detection_data:
            det = YOLODetection(
                xyxy=tuple(d["xyxy"]),
                conf=float(d["conf"]),
                cls=int(d["cls"]),
                name=str(d["name"]),
            )
            detections.append(det)

        return detections

    @property
    def is_loaded(self) -> bool:
        """모델 로드 상태."""
        return self._loaded
