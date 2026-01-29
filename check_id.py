from ultralytics import YOLO
model = YOLO(r"C:\Users\user\Desktop\VOICE\2026\crk\win_pc_test_sw2io_board\Edge_Environment\models\siyeon_best.pt")
for idx, name in sorted(model.names.items()):     
    print(f"{idx}: {name}")