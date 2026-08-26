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
        
        if not os.path.exists(model_path):
            url = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
            urllib.request.urlretrieve(url, model_path)

        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=max_hands,
            min_hand_detection_confidence=detection_con,
            min_hand_presence_confidence=track_con
        )
        self.detector = vision.HandLandmarker.create_from_options(options)
        self.detection_result = None

    def process_frame(self, frame):
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
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
        
        connections = [
            (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
            (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16),
            (13, 17), (17, 18), (18, 19), (19, 20), (0, 17)
        ]
        for start, end in connections:
            cv2.line(frame, (current_hand[start][1], current_hand[start][2]), 
                            (current_hand[end][1], current_hand[end][2]), (0, 255, 0), 2)