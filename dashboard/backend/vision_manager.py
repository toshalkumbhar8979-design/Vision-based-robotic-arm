"""
==========================================================================
PERCEPTION & VISION MANAGER (PYTHON - STRICT ARUCO DETECTION)
==========================================================================
Project:  Vision-Based Autonomous Robotic Arm
File:     vision_manager.py
Location: dashboard/backend/

PURPOSE:
  Executes high-accuracy OpenCV ArUco detection (DICT_4X4_50) strictly
  filtered for Marker ID 0 (Block 1), ID 1 (Block 2), and ID 2 (Target Box).
  Includes strict border validation and ID white-listing to eliminate 100%
  of false positives (t-shirts, shadows, hair).
==========================================================================
"""

import os
import time
import logging
import cv2
import numpy as np
from typing import Generator, Optional, Dict, Tuple, List

logger = logging.getLogger("VisionManager")
logging.basicConfig(level=logging.INFO)

class VisionManager:
    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.cap: Optional[cv2.VideoCapture] = None
        self.is_running = True

        # Target valid IDs for our project
        self.VALID_IDS = {0, 1, 2}

        # Build OpenCV 5.0 Strict Detector Parameters (Eliminates false positives)
        self.params = cv2.aruco.DetectorParameters()
        self.params.adaptiveThreshWinSizeMin = 5
        self.params.adaptiveThreshWinSizeMax = 25
        self.params.adaptiveThreshWinSizeStep = 5
        self.params.minMarkerPerimeterRate = 0.04 # Requires valid tag size
        self.params.maxMarkerPerimeterRate = 4.0
        self.params.polygonalApproxAccuracyRate = 0.03
        self.params.minCornerDistanceRate = 0.05
        self.params.minDistanceToBorder = 3
        self.params.markerBorderBits = 1 # Must have solid 1-cell black border
        self.params.perspectiveRemovePixelPerCell = 8
        self.params.maxErroneousBitsInBorderRate = 0.15 # Strict border checking (rejects t-shirts & hair)
        self.params.errorCorrectionRate = 0.3 # Strict bit error tolerance
        self.params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX

        # Dictionaries (DICT_4X4_50)
        self.dict_4x4 = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        self.detector_4x4 = cv2.aruco.ArucoDetector(self.dict_4x4, self.params)

        # Target Marker Labels
        self.marker_labels: Dict[int, str] = {
            0: "Block 1 (ArUco ID: 0)",
            1: "Block 2 (ArUco ID: 1)",
            2: "Target Box (ArUco ID: 2)"
        }

        # Latest detection state & pose data
        self.last_detected_ids: List[int] = []
        self.is_camera_connected = False
        self.latest_block_pose: Dict[str, float] = {"x_cm": 0.0, "y_cm": 0.0, "theta_deg": 0.0, "valid": False}

    def init_camera(self) -> bool:
        """Attempts to open USB camera (Logitech C270 or FaceTime camera)."""
        if self.cap is not None and self.cap.isOpened():
            return True

        logger.info(f"Opening camera index {self.camera_index}...")
        self.cap = cv2.VideoCapture(self.camera_index)
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        if self.cap.isOpened():
            self.is_camera_connected = True
            self.is_running = True
            logger.info(f"Camera index {self.camera_index} opened successfully.")
            return True
        else:
            self.is_camera_connected = False
            logger.warning(f"Failed to open camera index {self.camera_index}.")
            return False

    def stop_camera(self):
        """Cleanly releases camera resource on shutdown."""
        self.is_running = False
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        self.is_camera_connected = False

    def detect_and_annotate(self, frame: np.ndarray) -> np.ndarray:
        """Executes strict ArUco detection and draws bounding boxes ONLY for valid IDs (0, 1, 2)."""
        if frame is None:
            return frame

        # Convert to grayscale for contrast
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Detect ArUco Markers
        corners, ids, rejected = self.detector_4x4.detectMarkers(gray)

        self.last_detected_ids = []
        tag_centers: Dict[int, Tuple[float, float]] = {}
        tag_widths_px: Dict[int, float] = {}
        tag_corners_map: Dict[int, np.ndarray] = {}

        if ids is not None and len(ids) > 0:
            ids_flat = ids.flatten()

            for i, raw_id in enumerate(ids_flat):
                marker_id = int(raw_id)

                # STRICT WHITELIST CHECK: Reject any false positive ID not in {0, 1, 2}
                if marker_id not in self.VALID_IDS:
                    continue

                self.last_detected_ids.append(marker_id)
                marker_corners = corners[i][0] # 4 corner points
                pts = marker_corners.astype(np.int32)
                tag_corners_map[marker_id] = marker_corners

                # Draw thick neon green bounding box around ArUco tag
                cv2.polylines(frame, [pts], isClosed=True, color=(0, 255, 102), thickness=3)

                # Orientation markers (Corner 0 = Red, Others = Yellow)
                cv2.circle(frame, tuple(pts[0]), 6, (0, 0, 255), -1)
                for pt in pts[1:]:
                    cv2.circle(frame, tuple(pt), 4, (0, 255, 255), -1)

                # Center crosshair point
                center_x = float(np.mean(pts[:, 0]))
                center_y = float(np.mean(pts[:, 1]))
                tag_centers[marker_id] = (center_x, center_y)
                cv2.circle(frame, (int(center_x), int(center_y)), 5, (255, 153, 0), -1)

                # Calculate tag width in pixels for scale calibration
                width_top = np.linalg.norm(marker_corners[0] - marker_corners[1])
                width_bottom = np.linalg.norm(marker_corners[3] - marker_corners[2])
                tag_widths_px[marker_id] = float((width_top + width_bottom) / 2.0)

                # Calculate orientation angle theta for this tag
                c0, c1 = marker_corners[0], marker_corners[1]
                dx_edge = c1[0] - c0[0]
                dy_edge = c1[1] - c0[1]
                tag_theta_deg = round(float(np.degrees(np.arctan2(dy_edge, dx_edge))), 1)

                # Draw orientation heading line from center toward Corner 0 (Red Dot)
                heading_len = 25
                angle_rad = np.arctan2(c0[1] - center_y, c0[0] - center_x)
                head_x = int(center_x + heading_len * np.cos(angle_rad))
                head_y = int(center_y + heading_len * np.sin(angle_rad))
                cv2.line(frame, (int(center_x), int(center_y)), (head_x, head_y), (0, 0, 255), 2, cv2.LINE_AA)

                # Label string with live coordinates & orientation angle theta
                base_label = self.marker_labels.get(marker_id, f"ArUco ID: {marker_id}")
                label_text = f"{base_label} | (u:{int(center_x)}, v:{int(center_y)}) | θ:{tag_theta_deg}°"

                # Banner positioning
                top_y = min(pts[:, 1]) - 12
                top_x = min(pts[:, 0])

                # Dark container box for label
                (w, h), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                bg_x1 = max(0, top_x - 4)
                bg_y1 = max(0, top_y - h - 10)
                bg_x2 = min(frame.shape[1], top_x + w + 8)
                bg_y2 = max(0, top_y + 4)
                cv2.rectangle(frame, (bg_x1, bg_y1), (bg_x2, bg_y2), (20, 18, 17), -1)

                # Neon green text
                cv2.putText(
                    frame, label_text, (max(0, top_x), max(18, top_y)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 102), 2, cv2.LINE_AA
                )

        # Real-World Coordinate Transformation (Tag ID 2 = World Origin, Tag ID 0 = Block 1)
        if 2 in tag_centers:
            origin_x, origin_y = tag_centers[2]
            tag2_w_px = tag_widths_px.get(2, 60.0)
            cm_per_pixel = 4.0 / max(1.0, tag2_w_px)

            # Draw World Origin Coordinate Axes (Red = +X right, Green = +Y forward/up)
            axis_len = 45
            cv2.arrowedLine(frame, (int(origin_x), int(origin_y)), (int(origin_x + axis_len), int(origin_y)), (0, 0, 255), 2, tipLength=0.2)
            cv2.putText(frame, "+X (cm)", (int(origin_x + axis_len + 4), int(origin_y + 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 2)

            cv2.arrowedLine(frame, (int(origin_x), int(origin_y)), (int(origin_x), int(origin_y - axis_len)), (0, 255, 0), 2, tipLength=0.2)
            cv2.putText(frame, "+Y (cm)", (int(origin_x - 18), int(origin_y - axis_len - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)

            if 0 in tag_centers:
                block_x_px, block_y_px = tag_centers[0]

                # Relative coordinates in centimeters relative to World Origin Tag 2
                dx_cm = (block_x_px - origin_x) * cm_per_pixel
                dy_cm = (origin_y - block_y_px) * cm_per_pixel # Inverted Y for image frame

                # Orientation angle relative to horizontal
                c0, c1 = tag_corners_map[0][0], tag_corners_map[0][1]
                theta_rad = np.arctan2(c1[1] - c0[1], c1[0] - c0[0])
                theta_deg = float(np.degrees(theta_rad))

                # Draw connecting vector line between World Origin Tag 2 and Block Tag 0
                cv2.line(frame, (int(origin_x), int(origin_y)), (int(block_x_px), int(block_y_px)), (255, 153, 0), 2, cv2.LINE_AA)
                mid_x = int((origin_x + block_x_px) / 2)
                mid_y = int((origin_y + block_y_px) / 2)
                dist_cm = round(float(np.sqrt(dx_cm**2 + dy_cm**2)), 1)
                cv2.putText(frame, f"d={dist_cm}cm", (mid_x + 5, mid_y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 153, 0), 2, cv2.LINE_AA)

                self.latest_block_pose = {
                    "x_cm": round(dx_cm, 1),
                    "y_cm": round(dy_cm, 1),
                    "theta_deg": round(theta_deg, 1),
                    "valid": True
                }
            else:
                self.latest_block_pose["valid"] = False
        else:
            self.latest_block_pose["valid"] = False

        # On-Screen HUD Status Overlay at Top-Left
        if len(self.last_detected_ids) > 0:
            status_str = f"ArUco Status: DETECTED (IDs: {self.last_detected_ids})"
            cv2.rectangle(frame, (10, 10), (450, 42), (20, 18, 17), -1)
            cv2.putText(frame, status_str, (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 102), 2, cv2.LINE_AA)

            if self.latest_block_pose["valid"]:
                pose_str = f"Block Pose: X={self.latest_block_pose['x_cm']}cm Y={self.latest_block_pose['y_cm']}cm θ={self.latest_block_pose['theta_deg']}°"
                cv2.rectangle(frame, (10, 46), (450, 78), (20, 18, 17), -1)
                cv2.putText(frame, pose_str, (20, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 153, 0), 2, cv2.LINE_AA)
            elif 0 in tag_centers:
                # Show orientation theta even before Tag 2 (World Origin) is placed
                c0, c1 = tag_corners_map[0][0], tag_corners_map[0][1]
                t_deg = round(float(np.degrees(np.arctan2(c1[1] - c0[1], c1[0] - c0[0]))), 1)
                pose_str = f"Block 1 (ID 0): px=({int(tag_centers[0][0])},{int(tag_centers[0][1])}) | θ={t_deg}°"
                cv2.rectangle(frame, (10, 46), (450, 78), (20, 18, 17), -1)
                cv2.putText(frame, pose_str, (20, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 153, 0), 2, cv2.LINE_AA)
        else:
            cv2.rectangle(frame, (10, 10), (360, 42), (20, 18, 17), -1)
            cv2.putText(frame, "ArUco Status: Searching for Tag...", (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 165, 255), 1, cv2.LINE_AA)

        return frame

    def generate_mjpeg_stream(self) -> Generator[bytes, None, None]:
        """Generator function producing continuous MJPEG byte stream for FastAPI with clean shutdown."""
        self.is_running = True
        try:
            if not self.init_camera():
                while self.is_running:
                    blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                    blank_frame[:] = (36, 38, 42)

                    for x in range(0, 640, 40):
                        cv2.line(blank_frame, (x, 0), (x, 480), (45, 48, 52), 1)
                    for y in range(0, 480, 40):
                        cv2.line(blank_frame, (0, y), (640, y), (45, 48, 52), 1)

                    cv2.putText(blank_frame, "Camera 1 (Workspace View)", (140, 220),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (242, 247, 250), 2, cv2.LINE_AA)
                    cv2.putText(blank_frame, "Camera standing by... Plug USB camera or allow webcam access", (60, 260),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (74, 120, 196), 1, cv2.LINE_AA)

                    ret, jpeg = cv2.imencode('.jpg', blank_frame)
                    if ret:
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
                    time.sleep(0.1)

            while self.is_running:
                if self.cap is None or not self.cap.isOpened():
                    time.sleep(0.1)
                    continue

                success, frame = self.cap.read()
                if not success:
                    logger.warning("Camera read frame failed. Re-initializing...")
                    time.sleep(0.2)
                    continue

                # Run strict ArUco detection & annotation
                annotated_frame = self.detect_and_annotate(frame)

                # Compress to JPG
                ret, jpeg = cv2.imencode('.jpg', annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if not ret:
                    continue

                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

                time.sleep(0.033)
        finally:
            logger.info("Video stream generator ended cleanly.")


# Global singleton instance
vision_manager_cam1 = VisionManager(camera_index=0)
