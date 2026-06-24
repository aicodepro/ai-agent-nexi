import torch
import cv2

def main():
    # Load the YOLOv5m model (YOLOv5 Medium model for a balance between accuracy and speed)
    model = torch.hub.load('ultralytics/yolov5', 'yolov5m', pretrained=True)

    # Set the model parameters
    model.conf = 0.4  # Confidence threshold
    model.iou = 0.5   # IoU threshold for NMS
    model.imgsz = 416 # Reduced image size for faster inference

    # Set up the video capture (0 indicates the default webcam)
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame.")
            break

        # Perform object detection
        results = model(frame)

        # Filter results by confidence threshold
        filtered_results = results.pandas().xyxy[0]  # Get predictions as a pandas DataFrame
        filtered_results = filtered_results[filtered_results['confidence'] > model.conf]

        # Draw bounding boxes and labels on the frame
        for _, row in filtered_results.iterrows():
            xmin, ymin, xmax, ymax = int(row['xmin']), int(row['ymin']), int(row['xmax']), int(row['ymax'])
            label = f"{row['name']} {row['confidence']:.2f}"

            # Draw the bounding box
            cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), (255, 0, 0), 2)

            # Draw the label
            cv2.putText(frame, label, (xmin, ymin - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

        # Display the results
        cv2.imshow("YOLOv5m Object Detection", frame)

        # Exit with 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Release resources
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()

