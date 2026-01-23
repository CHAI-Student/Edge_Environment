import cv2
import os
import numpy as np
import threading
import time
from datetime import datetime

# --- 설정값 ---
CAMERA_INDICES = [0] 
IS_CSI_CAMERA = False 

CAPTURE_WIDTH = 480
CAPTURE_HEIGHT = 480

MAIN_OUTPUT_DIR = "image_recordings"
SAVE_FPS = 10 
# --- ---

def gstreamer_pipeline(sensor_id, capture_width, capture_height, framerate=30):
    """
    Jetson Nano의 CSI 카메라를 위한 GStreamer 파이프라인
    * 중요 수정: appsink에 drop=true, max-buffers=1을 추가하여 버퍼 적체를 방지합니다.
    """
    return (
        f"nvarguscamerasrc sensor-id={sensor_id} ! "
        f"video/x-raw(memory:NVMM), width=(int){capture_width}, height=(int){capture_height}, framerate=(fraction){framerate}/1 ! "
        "nvvidconv flip-method=0 ! "
        "video/x-raw, format=(string)BGRx ! "
        "videoconvert ! "
        "video/x-raw, format=(string)BGR ! "
        "appsink drop=true max-buffers=1"
    )

class CameraThread:
    """
    카메라 영상을 별도의 스레드에서 읽어오는 클래스입니다.
    Always keeps the latest frame only. (항상 최신 프레임만 유지)
    """
    def __init__(self, src=0, width=480, height=480, is_csi=False):
        self.src = src
        self.width = width
        self.height = height
        self.is_csi = is_csi
        self.stopped = False
        self.grabbed = False
        self.frame = None
        self.actual_res = (0, 0)
        self.crop_coords = (0, 0)

        # 카메라 초기화
        if self.is_csi:
            pipeline = gstreamer_pipeline(self.src, self.width, self.height)
            self.cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        else:
            self.cap = cv2.VideoCapture(self.src, cv2.CAP_V4L2)
            # USB 카메라 버퍼 사이즈를 1로 강제 설정 (백엔드에 따라 작동 안 할 수도 있음)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        if not self.cap.isOpened():
            print(f"[Error] Camera #{self.src} failed to open.")
            return

        # 실제 해상도 확인 및 Crop 좌표 계산
        w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.actual_res = (w, h)
        
        crop_x = (w - self.width) // 2
        crop_y = (h - self.height) // 2
        self.crop_coords = (crop_x, crop_y)

        # 초기 프레임 한 번 읽기
        self.grabbed, self.frame = self.cap.read()

    def start(self):
        """스레드 시작"""
        t = threading.Thread(target=self.update, args=())
        t.daemon = True # 메인 프로그램 종료 시 스레드도 강제 종료
        t.start()
        return self

    def update(self):
        """
        카메라에서 지속적으로 프레임을 읽어오는 루프 (별도 스레드에서 실행)
        메인 루프의 속도와 관계없이 카메라는 최대 속도로 버퍼를 비웁니다.
        """
        while True:
            if self.stopped:
                return
            
            ret, frame = self.cap.read()
            if ret:
                self.grabbed = True
                self.frame = frame
            else:
                self.grabbed = False

    def read(self):
        """메인 스레드에서 최신 프레임을 가져갈 때 호출"""
        if not self.grabbed or self.frame is None:
            return None
        
        # Crop 수행
        cx, cy = self.crop_coords
        cropped_frame = self.frame[cy : cy + self.height, cx : cx + self.width]
        return cropped_frame

    def stop(self):
        """카메라 및 스레드 자원 해제"""
        self.stopped = True
        time.sleep(0.1) # 스레드 종료 대기
        self.cap.release()

def main():
    if len(CAMERA_INDICES) < 1:
        print("오류: 카메라를 2대 이상 지정해주세요.")
        return

    # 1. 카메라 스레드 객체 생성 및 시작
    cam_threads = []
    print(f"카메라 {len(CAMERA_INDICES)}대 연결 및 스레드 시작 중...")

    for idx in CAMERA_INDICES:
        cam = CameraThread(src=idx, width=CAPTURE_WIDTH, height=CAPTURE_HEIGHT, is_csi=IS_CSI_CAMERA)
        if cam.cap.isOpened():
            cam.start()
            cam_threads.append(cam)
            print(f" -> Camera #{idx} Thread Started. ({cam.actual_res[0]}x{cam.actual_res[1]})")
        else:
            print(f" -> Camera #{idx} Initialization Failed.")
            # 실패 시 기존 카메라들 정리
            for c in cam_threads: c.stop()
            return

    print("\n[시스템 준비 완료] 엔터를 누르면 이미지 저장이 시작됩니다.")
    print("'q'를 누르면 종료됩니다.")

    is_saving = False
    session_dirs = []
    saved_image_counts = [0] * len(cam_threads)
    
    # FPS 제어를 위한 시간 관리
    prev_time = 0
    save_interval = 1.0 / SAVE_FPS if SAVE_FPS > 0 else 0

    try:
        while True:
            current_time = time.time()
            frames_for_display = []
            clean_frames_current = []

            # 2. 각 카메라 스레드에서 최신 프레임 가져오기 (Non-blocking)
            all_frames_valid = True
            for i, cam in enumerate(cam_threads):
                frame = cam.read()
                
                if frame is None:
                    # 프레임이 준비 안 됐거나 끊김 -> 검은 화면 대체
                    frame = np.zeros((CAPTURE_HEIGHT, CAPTURE_WIDTH, 3), dtype=np.uint8)
                    cv2.putText(frame, "No Signal", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    all_frames_valid = False
                
                clean_frames_current.append(frame)

                # 디스플레이용 복사
                disp_frame = frame.copy()
                label = f"CAM {CAMERA_INDICES[i]}"
                cv2.putText(disp_frame, label, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)
                
                status_msg = "REC" if is_saving else "Standby"
                color = (0, 0, 255) if is_saving else (0, 255, 0)
                cv2.putText(disp_frame, status_msg, (10, CAPTURE_HEIGHT - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                
                frames_for_display.append(disp_frame)

            # 3. 화면 병합 및 출력
            if frames_for_display:
                combined_frame = cv2.hconcat(frames_for_display)
                cv2.imshow('Multi-Camera Threaded', combined_frame)

            # 4. 저장 로직 (Non-blocking에 가깝게 동작)
            # 시간차를 계산하여 정확한 FPS로 저장 시도
            if is_saving and all_frames_valid:
                if (current_time - prev_time) >= save_interval:
                    prev_time = current_time
                    for i, frame in enumerate(clean_frames_current):
                        saved_image_counts[i] += 1
                        filename = os.path.join(session_dirs[i], f"frame_{saved_image_counts[i]:06d}.jpg")
                        # cv2.imwrite는 블로킹 함수이지만, 
                        # 카메라 읽기가 별도 스레드라 버퍼 오버플로우는 발생하지 않음.
                        # 만약 imwrite가 너무 느리면 디스플레이 FPS만 떨어짐.
                        cv2.imwrite(filename, frame)

            # 5. 키 입력 처리
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == 13: # Enter Key
                if not is_saving:
                    is_saving = True
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    base_path = os.path.join(MAIN_OUTPUT_DIR, timestamp)
                    session_dirs = []
                    for idx in CAMERA_INDICES:
                        d = os.path.join(base_path, f"cam_{idx}")
                        os.makedirs(d, exist_ok=True)
                        session_dirs.append(d)
                    saved_image_counts = [0] * len(cam_threads)
                    print(f"\n>>> 녹화 시작: {base_path}")
                else:
                    print("\n>>> 녹화 종료 및 프로그램 종료.")
                    break

    finally:
        # 정리 작업
        print("리소스 해제 중...")
        for cam in cam_threads:
            cam.stop()
        cv2.destroyAllWindows()
        print("종료되었습니다.")

if __name__ == '__main__':
    main()