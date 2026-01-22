"""
YOLO Wrapper for Product Detection.

실제 YOLO 출력 형식:
    det[0] xyxy=[258.72, 47.65, 315.12, 113.97] conf=0.788 cls=0 name=hand
    det[1] xyxy=[257.67, 75.54, 284.33, 110.22] conf=0.492 cls=109 name=BAG_DALGWANG_DONUT_CHOCO_45G

파싱하여 YOLODetection 객체 리스트로 변환.

사용 예시:
    wrapper = YOLOWrapper(model_path="best.pt")
    detections = wrapper.detect(image)

    # 또는 이미 추론된 결과 파싱
    detections = YOLOWrapper.parse_results(yolo_results)
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional, Any
import logging

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
        name: Class name (예: "hand", "BAG_DALGWANG_DONUT_CHOCO_45G")
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
        # 교집합 영역
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

    @classmethod
    def from_yolo_box(cls, box: Any) -> "YOLODetection":
        """
        YOLO box 객체에서 YOLODetection 생성.

        Args:
            box: YOLO Results의 boxes 요소
                 - box.xyxy: tensor [[x1, y1, x2, y2]]
                 - box.conf: tensor [conf]
                 - box.cls: tensor [cls]

        Returns:
            YOLODetection 인스턴스
        """
        # tensor to python
        xyxy = box.xyxy[0].tolist() if hasattr(box.xyxy[0], 'tolist') else list(box.xyxy[0])
        conf = float(box.conf[0]) if hasattr(box.conf, '__getitem__') else float(box.conf)
        cls_id = int(box.cls[0]) if hasattr(box.cls, '__getitem__') else int(box.cls)

        # name은 model.names에서 가져와야 함 (외부에서 주입)
        name = getattr(box, 'name', f"class_{cls_id}")

        return cls(
            xyxy=tuple(xyxy),
            conf=conf,
            cls=cls_id,
            name=name,
        )


class YOLOWrapper:
    """
    YOLO 모델 래퍼.

    YOLO 추론 결과를 YOLODetection 리스트로 변환.

    Attributes:
        model: YOLO 모델 (ultralytics)
        conf_threshold: 최소 confidence (기본값 0.01, 매우 낮게)
        device: 추론 디바이스 ("cuda", "cpu")
    """

    HAND_CLASS_ID = 0  # 손 클래스 ID

    def __init__(
        self,
        model_path: Optional[str] = None,
        conf_threshold: float = 0.01,
        device: str = "cuda",
    ):
        """
        YOLO 래퍼 초기화.

        Args:
            model_path: YOLO 모델 경로 (.pt 파일)
            conf_threshold: 최소 confidence (기본값 0.01)
            device: 추론 디바이스
        """
        self.model = None
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        self.device = device
        self.class_names: dict = {}

        if model_path:
            self._load_model(model_path)

    def _load_model(self, model_path: str) -> None:
        """YOLO 모델 로드."""
        try:
            from ultralytics import YOLO
            self.model = YOLO(model_path)
            self.model.to(self.device)
            self.class_names = self.model.names
            logger.info(f"YOLO model loaded: {model_path}, {len(self.class_names)} classes")
        except ImportError:
            logger.warning("ultralytics not installed. Use parse_results() for manual parsing.")
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")

    def detect(self, image) -> List[YOLODetection]:
        """
        이미지에서 객체 감지.

        Args:
            image: numpy array (BGR) 또는 이미지 경로

        Returns:
            YOLODetection 리스트
        """
        if self.model is None:
            raise RuntimeError("YOLO model not loaded. Call _load_model() first.")

        results = self.model.predict(
            image,
            conf=self.conf_threshold,
            verbose=False,
        )

        return self.parse_results(results[0], self.class_names)

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

    @staticmethod
    def from_raw_output(raw_text: str) -> List[YOLODetection]:
        """
        YOLO 로그 출력 텍스트에서 파싱.

        형식:
            det[0] xyxy=[258.72, 47.65, ...] conf=0.788 cls=0 name=hand

        Args:
            raw_text: YOLO 출력 텍스트

        Returns:
            YOLODetection 리스트
        """
        import re

        detections = []
        pattern = r'xyxy=\[([\d.,\s]+)\]\s+conf=([\d.]+)\s+cls=(\d+)\s+name=(\S+)'

        for match in re.finditer(pattern, raw_text):
            xyxy_str, conf_str, cls_str, name = match.groups()
            xyxy = tuple(float(x.strip()) for x in xyxy_str.split(','))

            det = YOLODetection(
                xyxy=xyxy,
                conf=float(conf_str),
                cls=int(cls_str),
                name=name,
            )
            detections.append(det)

        return detections
