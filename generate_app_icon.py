#!/usr/bin/env python3
"""
Generates an Apple Touch Icon for iPhone PWA Home Screen app using OpenCV.
"""

import os
import cv2
import numpy as np

# 180x180 canvas
img = np.full((180, 180, 3), (242, 247, 250), dtype=np.uint8)

# Warm accent box (#C4784A -> BGR: 74, 120, 196)
cv2.rectangle(img, (10, 10), (170, 170), (74, 120, 196), -1)

# Inner white icon shape
cv2.rectangle(img, (70, 40), (110, 120), (255, 255, 255), -1)
cv2.rectangle(img, (40, 110), (110, 140), (255, 255, 255), -1)

icon_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "apple-touch-icon.png"))
cv2.imwrite(icon_path, img)
print(f"[OK] Generated Apple Touch Icon -> {icon_path}")
