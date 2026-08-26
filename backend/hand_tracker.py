import cv2
import os
import urllib.request
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

class HandTracker:
    def __init__(self, max_hands=2, detection_con=0.7, track_con=0.5):
        self.max_hands = max_hands
        model_path = 'hand_landmarker.task'
        self.detector = None  # Khởi tạo là None
        
        # Tải mô hình nếu chưa có
        if not os.path.exists(model_path):
            url = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
            print(f"Đang tải mô hình từ {url}...")
            try:
                urllib.request.urlretrieve(url, model_path)
                print("Tải mô hình thành công.")
            except Exception as e:
                print(f"Lỗi khi tải mô hình: {e}")
                return  # Dừng khởi tạo nếu tải thất bại
        
        # Tạo options cho HandLandmarker
        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=max_hands,
            min_hand_detection_confidence=detection_con,
            min_hand_presence_confidence=track_con
        )
        
        # Tạo đối tượng HandLandmarker
        try:
            self.detector = vision.HandLandmarker.create_from_options(options)
            print("Khởi tạo HandLandmarker thành công.")
        except Exception as e:
            print(f"Lỗi khi tạo HandLandmarker: {e}")
            return

    def process_frame(self, frame):
        """Xử lý một frame và lưu kết quả vào self.detection_result"""
        if self.detector is None:
            return None
        
        # Chuyển đổi BGR (OpenCV) sang RGB (MediaPipe yêu cầu)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Tạo đối tượng MediaPipe Image
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        
        # Phát hiện hand landmarks
        self.detection_result = self.detector.detect(mp_image)
        return self.detection_result

    def get_landmarks(self, frame, draw=True):
        """TRẢ VỀ LIST CÁC BÀN TAY, MỖI BÀN TAY LÀ 1 LIST 21 ĐIỂM KÈM TỌA ĐỘ X, Y, Z"""
        all_hands = []
        
        if self.detection_result and self.detection_result.hand_landmarks:
            h, w, _ = frame.shape
            for hand_landmarks in self.detection_result.hand_landmarks:
                current_hand = []
                for id, lm in enumerate(hand_landmarks):
                    cx, cy = int(lm.x * w), int(lm.y * h)
                    cz = lm.z  # Lấy tọa độ chiều sâu z
                    current_hand.append([id, cx, cy, cz]) # Thêm cz vào mảng
                
                all_hands.append(current_hand) # Lưu bàn tay vào danh sách chung
                
                if draw:
                    self._draw_landmarks(frame, current_hand)
                        
        return all_hands # Trả về list các bàn tay (có thể là [] hoặc [hand1] hoặc [hand1, hand2])

    def _draw_landmarks(self, frame, current_hand):
        for id, cx, cy, cz in current_hand:  # Cập nhật unpacking 4 biến
            cv2.circle(frame, (cx, cy), 5, (0, 255, 0), -1)
        
        # Danh sách các đường kết nối giữa các landmark
        connections = [
            (0, 1), (1, 2), (2, 3), (3, 4), # Ngón cái
            (0, 5), (5, 6), (6, 7), (7, 8), # Ngón trỏ
            (5, 9), (9, 10), (10, 11), (11, 12), # Ngón giữa
            (9, 13), (13, 14), (14, 15), (15, 16), # Ngón áp út
            (13, 17), (17, 18), (18, 19), (19, 20), # Ngón út
            (0, 17) # Cổ tay
        ]
        
        # Vẽ các đường kết nối
        for start_idx, end_idx in connections:
            start_point = (current_hand[start_idx][1], current_hand[start_idx][2])
            end_point = (current_hand[end_idx][1], current_hand[end_idx][2])
            cv2.line(frame, start_point, end_point, (0, 255, 0), 2)

# ==========================================
# PHẦN CHẠY THỬ - CHỈ CHẠY KHI THỰC THI FILE NÀY
# ==========================================
if __name__ == "__main__":
    # Khởi tạo tracker
    print("Đang khởi tạo HandTracker...")
    tracker = HandTracker()
    
    if tracker.detector is None:
        print("Không thể khởi tạo HandTracker. Kiểm tra lỗi ở trên.")
        exit()
    
    # Mở webcam (0 là camera mặc định)
    cap = cv2.VideoCapture(0)
    
    # Kiểm tra mở camera thành công
    if not cap.isOpened():
        print("Không thể mở webcam. Kiểm tra xem camera có đang được sử dụng bởi ứng dụng khác không.")
        exit()
    
    print("Nhấn phím 'q' để thoát...")
    print("Đang chạy... Đưa tay vào trước camera để thấy landmarks.")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Không thể nhận frame từ webcam")
            break
        
        # Xử lý frame và lấy landmarks
        # QUAN TRỌNG: Luôn gọi process_frame trước khi get_landmarks
        tracker.process_frame(frame)
        hands = tracker.get_landmarks(frame, draw=True)
        
        # In số lượng tay phát hiện được (để debug)
        # Bạn có thể xóa dòng này trong thực tế
        if hands:
            print(f"Phát hiện {len(hands)} bàn tay")
        else:
            print("Không phát hiện bàn tay")
        
        # Hiển thị frame
        cv2.imshow('Hand Tracking', frame)
        
        # Thoát khi nhấn phím 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    # Giải phóng tài nguyên
    cap.release()
    cv2.destroyAllWindows()
    print("Đã thoát chương trình.")