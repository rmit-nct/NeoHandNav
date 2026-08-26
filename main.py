import cv2
import time
from backend.hand_tracker import HandTracker

def main():
    # Khởi tạo camera với DirectShow để tránh treo trên Windows
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    
    if not cap.isOpened():
        print("Lỗi: Không thể truy cập vào camera. Hãy đảm bảo không có ứng dụng nào khác đang chiếm dụng camera.")
        return

    # Khởi tạo HandTracker (hỗ trợ tối đa 2 bàn tay)
    tracker = HandTracker(max_hands=2)
    
    # Biến điều tiết thời gian in (in mỗi 0.5 giây để không trôi terminal)
    last_print_time = 0
    print_interval = 0.5 

    print("Đang khởi động camera... Nhấn phím 'q' trên cửa sổ camera để thoát.")

    while True:
        success, frame = cap.read()
        if not success: 
            print("Không thể nhận dữ liệu từ camera.")
            break
            
        # Lật khung hình như soi gương
        frame = cv2.flip(frame, 1)

        # Xử lý khung hình và trích xuất tọa độ
        tracker.process_frame(frame)
        all_hands = tracker.get_landmarks(frame, draw=True)
        
        # In dữ liệu 5 ngón tay khi có bàn tay xuất hiện và đủ thời gian điều tiết
        if all_hands and (time.time() - last_print_time > print_interval):
            # Xóa màn hình terminal (tùy chọn, giúp hiển thị gọn gàng trên PowerShell)
            print("\033c", end="") 
            
            # ID và tên các đầu ngón tay trong chuẩn MediaPipe
            finger_ids = [4, 8, 12, 16, 20]
            finger_names = ["Cái", "Trỏ", "Giữa", "Áp út", "Út"]
            
            for i, hand in enumerate(all_hands):
                print(f"=== Bàn tay {i+1} ===")
                # Kiểm tra an toàn: Đảm bảo bàn tay có đủ 21 điểm mốc
                if len(hand) >= 21:
                    for j, finger_id in enumerate(finger_ids):
                        # Lấy thêm biến z ở vị trí index 3
                        x, y, z = hand[finger_id][1], hand[finger_id][2], hand[finger_id][3]
                        # In thêm tọa độ z
                        print(f"Ngón {finger_names[j]}: x={x}, y={y}, z={z:.4f}")
                else:
                    print("Đang nhận diện bàn tay...")
            
            last_print_time = time.time()

        # Hiển thị cửa sổ camera
        cv2.imshow("HandNav - Multi-Hand Test", frame)
        
        # Thoát bằng phím 'q' hoặc đóng cửa sổ
        key = cv2.waitKey(10) & 0xFF
        if key == ord('q'):
            print("\nĐang thoát chương trình...")
            break
            
        if cv2.getWindowProperty("HandNav - Multi-Hand Test", cv2.WND_PROP_VISIBLE) < 1:
            break
            
    # Giải phóng tài nguyên
    cap.release()
    cv2.destroyAllWindows()
    print("Đã đóng camera thành công.")
if __name__ == "__main__":
    main()
