"""
YOLO Wrapper for Product Detection.

실제 YOLO 출력 형식:
    det[0] xyxy=[258.72, 47.65, 315.12, 113.97] conf=0.788 cls=0 name=hand
    det[1] xyxy=[257.67, 75.54, 284.33, 110.22] conf=0.492 cls=109 name=BAG_DALGWANG_DONUT_CHOCO_45G

파싱하여 YOLODetection 객체 리스트로 변환.

사용 예시:
    wrapper = YOLOWrapper(model_path="best.pt")
    detections = wrapper.detect(image)
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional, Any
import logging

import numpy as np

from ..config import config

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
        self.is_tensorrt = self.model_path.endswith(".engine")

    def load(self) -> bool:
        """
        YOLO 모델 로드.

        .pt (PyTorch) 또는 .engine (TensorRT) 파일을 로드합니다.
        TensorRT 모델은 Jetson Orin Nano에서 최적화된 추론을 제공합니다.

        Returns:
            성공 여부
        """
        if self._loaded:
            return True

        try:
            from ultralytics import YOLO
            import torch

            # Device 자동 결정
            if self.device == "auto":
                if self.is_tensorrt:
                    self.device = "cuda"  # TensorRT는 항상 GPU
                elif torch.cuda.is_available():
                    self.device = "cuda"
                else:
                    self.device = "cpu"
                logger.info(f"Auto-selected device: {self.device}")

            # TensorRT 모델인 경우
            if self.is_tensorrt:
                self.device = "cuda"  # TensorRT는 항상 GPU
                logger.info(f"Loading TensorRT engine: {self.model_path}")

            self.model = YOLO(self.model_path)

            # TensorRT가 아닌 경우에만 device 이동
            # TensorRT 모델은 이미 GPU에 최적화되어 있음
            if not self.is_tensorrt:
                self.model.to(self.device)

            self.class_names = self.model.names
            self._loaded = True

            model_type = "TensorRT" if self.is_tensorrt else "PyTorch"
            logger.info(
                f"YOLO model loaded ({model_type}): {self.model_path}, "
                f"{len(self.class_names)} classes, device={self.device}"
            )
            return True
        except ImportError:
            logger.warning("ultralytics not installed. Use parse_results() for manual parsing.")
            return False
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            return False

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
