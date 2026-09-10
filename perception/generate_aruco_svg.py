#!/usr/bin/env python3
"""
Official OpenCV ArUco Marker Generator (DICT_4X4_50)
Generates 100% mathematically exact SVG & PNG vector markers using OpenCV's official dictionary.
"""

import os
import cv2
import numpy as np

OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "aruco_markers"))
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load OpenCV official DICT_4X4_50 dictionary
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

def extract_official_bits(marker_id: int):
    """Extracts exact 4x4 binary matrix (0=black, 1=white) directly from OpenCV dictionary."""
    img_6x6 = cv2.aruco.generateImageMarker(aruco_dict, marker_id, 6, borderBits=1)
    inner_4x4 = (img_6x6[1:5, 1:5] // 255).tolist()
    return inner_4x4

def generate_svg(marker_id: int):
    """Generates crisp 4cm x 4cm SVG vector marker matching OpenCV DICT_4X4_50."""
    bits = extract_official_bits(marker_id)
    grid_size = 6 # 1 border + 4 data + 1 border
    cell_size = 50 # SVG internal units
    total_dim = grid_size * cell_size # 300x300 px
    
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="4cm" height="4cm" viewBox="0 0 {total_dim} {total_dim}">',
        f'  <!-- Background / White Margin -->',
        f'  <rect width="{total_dim}" height="{total_dim}" fill="white" />',
        f'  <!-- Outer Black Border -->',
        f'  <rect x="0" y="0" width="{total_dim}" height="{total_dim}" fill="black" />',
        f'  <!-- White Inner Padding Box -->',
        f'  <rect x="{cell_size}" y="{cell_size}" width="{4*cell_size}" height="{4*cell_size}" fill="white" />'
    ]
    
    # Draw data cells (0 = black, 1 = white)
    for r in range(4):
        for c in range(4):
            if bits[r][c] == 0: # Black bit
                x = (c + 1) * cell_size
                y = (r + 1) * cell_size
                svg.append(f'  <rect x="{x}" y="{y}" width="{cell_size}" height="{cell_size}" fill="black" />')
                
    svg.append('</svg>')
    return '\n'.join(svg)

# Generate official SVGs & PNGs for IDs 0, 1, 2
markers_info = [
    (0, "Block_1_Marker_0.png", "aruco_id_0.svg", "Block 1 (Sponge Cube 1) - ArUco ID 0"),
    (1, "Block_2_Marker_1.png", "aruco_id_1.svg", "Block 2 (Sponge Cube 2) - ArUco ID 1"),
    (2, "Target_Box_Marker_2.png", "aruco_id_2.svg", "Target Box Destination - ArUco ID 2"),
]

for mid, png_name, svg_name, label in markers_info:
    # 1. Write SVG
    svg_path = os.path.join(OUTPUT_DIR, svg_name)
    with open(svg_path, "w") as f:
        f.write(generate_svg(mid))

    # 2. Write PNG with OpenCV
    img_400 = cv2.aruco.generateImageMarker(aruco_dict, mid, 400, borderBits=1)
    img_padded = cv2.copyMakeBorder(img_400, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
    png_path = os.path.join(OUTPUT_DIR, png_name)
    cv2.imwrite(png_path, img_padded)

    print(f"[OK] Generated Official OpenCV ArUco ID {mid} -> {svg_name} & {png_name}")

# Generate Printable HTML Sheet
html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Official Printable ArUco Markers (DICT_4X4_50)</title>
  <style>
    body {{
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      margin: 24px;
      background: #faf7f2;
      color: #2a2624;
    }}
    h2 {{
      color: #c4784a;
      margin-bottom: 6px;
    }}
    .instructions {{
      background: #fff;
      border: 1px solid #e0d6c8;
      padding: 18px 24px;
      border-radius: 10px;
      margin-bottom: 28px;
      max-width: 850px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }}
    .instructions ol {{
      margin: 10px 0 0 20px;
      padding: 0;
      line-height: 1.6;
    }}
    .marker-grid {{
      display: flex;
      gap: 32px;
      flex-wrap: wrap;
    }}
    .marker-card {{
      background: #fff;
      border: 2px dashed #c4784a;
      padding: 24px;
      border-radius: 12px;
      text-align: center;
      width: 220px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }}
    .marker-img {{
      width: 4cm;
      height: 4cm;
      border: 1px solid #ddd;
    }}
    .marker-title {{
      font-weight: 700;
      font-size: 0.95rem;
      margin-top: 14px;
      color: #2a2624;
    }}
    .marker-dim {{
      font-family: monospace;
      font-size: 0.8rem;
      color: #666;
      margin-top: 6px;
    }}
    @media print {{
      body {{ background: #fff; margin: 0; padding: 10px; }}
      .instructions {{ border: 1px solid #ccc; box-shadow: none; }}
      .marker-card {{ border: 1px dashed #000; box-shadow: none; page-break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <h2>Stage 1 Official ArUco Marker Print Sheet (DICT_4X4_50)</h2>
  <div style="font-size: 0.9rem; color: #666; margin-bottom: 20px;">Mathematically Exact OpenCV Dictionary • Pre-scaled to 4cm × 4cm</div>
  
  <div class="instructions">
    <strong style="color: #c4784a; font-size: 1rem;">Printing & Mounting Guide:</strong>
    <ol>
      <li>Click <strong>File &rarr; Print</strong> (or press <code>Cmd+P</code> / <code>Ctrl+P</code>).</li>
      <li>In the Print Dialog, set <strong>Scale: 100% / Actual Size</strong> (do NOT fit to page).</li>
      <li>Cut out each marker along the dashed outer border line.</li>
      <li><strong style="color: #b02a2a;">CRITICAL STEP:</strong> Glue each cutout onto a flat piece of <strong>thin cardboard</strong> before sticking to the sponge cubes. Cardboard guarantees the marker stays 100% flat so vision detection works in variable lighting.</li>
      <li>Attach <strong>Marker 0</strong> to Block 1, <strong>Marker 1</strong> to Block 2, and <strong>Marker 2</strong> to Target Box.</li>
    </ol>
  </div>

  <div class="marker-grid">
    <div class="marker-card">
      <iframe src="aruco_id_0.svg" style="width: 4cm; height: 4cm; border: none; overflow: hidden;" scrolling="no"></iframe>
      <div class="marker-title">Block 1 (Sponge Cube 1)</div>
      <div class="marker-dim">ArUco ID: 0 (4cm × 4cm)</div>
    </div>

    <div class="marker-card">
      <iframe src="aruco_id_1.svg" style="width: 4cm; height: 4cm; border: none; overflow: hidden;" scrolling="no"></iframe>
      <div class="marker-title">Block 2 (Sponge Cube 2)</div>
      <div class="marker-dim">ArUco ID: 1 (4cm × 4cm)</div>
    </div>

    <div class="marker-card">
      <iframe src="aruco_id_2.svg" style="width: 4cm; height: 4cm; border: none; overflow: hidden;" scrolling="no"></iframe>
      <div class="marker-title">Target Destination Box</div>
      <div class="marker-dim">ArUco ID: 2 (4cm × 4cm)</div>
    </div>
  </div>
</body>
</html>
"""

html_filepath = os.path.join(OUTPUT_DIR, "print_aruco_sheet.html")
with open(html_filepath, "w") as f:
    f.write(html_content)

print(f"[SUCCESS] Regenerated 100% official OpenCV ArUco files in -> {OUTPUT_DIR}")
