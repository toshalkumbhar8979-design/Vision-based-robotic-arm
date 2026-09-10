#!/usr/bin/env python3
"""
ArUco Marker Sheet Generator (Stage 1 Perception)
Project: Vision-Based Autonomous Pick-and-Place Robotic Arm
Dictionary: DICT_4X4_50

Generates PNG images and a printable HTML sheet with exact 4cm x 4cm physical dimensions
for Marker ID 0 (Block 1), Marker ID 1 (Block 2), and Marker ID 2 (Target Box).
"""

import os
import cv2
import numpy as np

OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "aruco_markers"))
os.makedirs(OUTPUT_DIR, exist_ok=True)

# OpenCV ArUco Dictionary 4x4_50
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

# Generate Marker 0, 1, 2
markers_info = [
    (0, "Block_1_Marker_0.png", "Block 1 (Sponge Cube 1) - ArUco ID 0"),
    (1, "Block_2_Marker_1.png", "Block 2 (Sponge Cube 2) - ArUco ID 1"),
    (2, "Target_Box_Marker_2.png", "Target Box Destination - ArUco ID 2"),
]

generated_files = []

for marker_id, filename, label in markers_info:
    # 400x400 px high-res image
    img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, 400)
    
    # Add a clean 40px white margin/border around the marker
    img_with_border = cv2.copyMakeBorder(
        img, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255
    )
    
    filepath = os.path.join(OUTPUT_DIR, filename)
    cv2.imwrite(filepath, img_with_border)
    generated_files.append((marker_id, filename, label, filepath))
    print(f"[OK] Generated ArUco Marker ID {marker_id} -> {filepath}")

# Create a printable HTML sheet with exact 4cm x 4cm CSS dimensions
html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Printable ArUco Markers (Stage 1 - DICT_4X4_50)</title>
  <style>
    body {{
      font-family: Arial, sans-serif;
      margin: 20px;
      background: #faf7f2;
      color: #2a2624;
    }}
    h2 {{
      color: #c4784a;
    }}
    .instructions {{
      background: #fff;
      border: 1px solid #e0d6c8;
      padding: 16px;
      border-radius: 8px;
      margin-bottom: 24px;
      max-width: 800px;
    }}
    .marker-grid {{
      display: flex;
      gap: 30px;
      flex-wrap: wrap;
    }}
    .marker-card {{
      background: #fff;
      border: 2px dashed #c4784a;
      padding: 20px;
      border-radius: 12px;
      text-align: center;
      width: 200px;
    }}
    .marker-img {{
      width: 4cm;
      height: 4cm;
      object-fit: contain;
      border: 1px solid #ccc;
    }}
    .marker-title {{
      font-weight: bold;
      font-size: 0.9rem;
      margin-top: 10px;
    }}
    .marker-dim {{
      font-size: 0.8rem;
      color: #666;
      margin-top: 4px;
    }}
    @media print {{
      body {{ background: #fff; }}
      .instructions {{ border: none; }}
      .marker-card {{ border: 1px solid #000; page-break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <h2>Stage 1 ArUco Marker Print Sheet (DICT_4X4_50)</h2>
  
  <div class="instructions">
    <strong>Printing & Mounting Instructions:</strong>
    <ol>
      <li>Print this page on a standard printer (Select <strong>Scale: 100% / Actual Size</strong> in print dialog).</li>
      <li>Cut out each marker along the dashed border line.</li>
      <li><strong>Crucial Step:</strong> Glue each cutout onto a stiff piece of <strong>thin cardboard</strong> first before sticking to sponge cubes. Cardboard guarantees the marker stays 100% flat!</li>
      <li>Stick <strong>Marker 0</strong> on Block 1, <strong>Marker 1</strong> on Block 2, and <strong>Marker 2</strong> on the Target Destination Box.</li>
    </ol>
  </div>

  <div class="marker-grid">
    <div class="marker-card">
      <img src="Block_1_Marker_0.png" class="marker-img" alt="ArUco ID 0">
      <div class="marker-title">Block 1 (Sponge Cube 1)</div>
      <div class="marker-dim">ArUco ID: 0 (Size: 4cm × 4cm)</div>
    </div>

    <div class="marker-card">
      <img src="Block_2_Marker_1.png" class="marker-img" alt="ArUco ID 1">
      <div class="marker-title">Block 2 (Sponge Cube 2)</div>
      <div class="marker-dim">ArUco ID: 1 (Size: 4cm × 4cm)</div>
    </div>

    <div class="marker-card">
      <img src="Target_Box_Marker_2.png" class="marker-img" alt="ArUco ID 2">
      <div class="marker-title">Target Destination Box</div>
      <div class="marker-dim">ArUco ID: 2 (Size: 4cm × 4cm)</div>
    </div>
  </div>
</body>
</html>
"""

html_filepath = os.path.join(OUTPUT_DIR, "print_aruco_sheet.html")
with open(html_filepath, "w") as f:
    f.write(html_content)

print(f"[SUCCESS] Created printable ArUco sheet -> {html_filepath}")
