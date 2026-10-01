"""Render source-frame contact sheet and measured method comparison charts."""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path('instance/group_batch')
items = json.loads((ROOT / 'inventory.json').read_text())
width, height, header, columns = 480, 270, 38, 3
rows = (len(items) + columns - 1) // columns
canvas = np.full((rows * (height + header), columns * width, 3), 242, dtype=np.uint8)
for index, item in enumerate(items):
    image = cv2.imread(item['screenshot'])
    if image is None:
        continue
    scale = min(width/image.shape[1], height/image.shape[0])
    resized = cv2.resize(image, (round(image.shape[1]*scale), round(image.shape[0]*scale)))
    x, y = (index % columns)*width, (index // columns)*(height+header)
    canvas[y:y+height, x:x+width] = (20, 20, 20)
    ox, oy = (width-resized.shape[1])//2, (height-resized.shape[0])//2
    canvas[y+oy:y+oy+resized.shape[0], x+ox:x+ox+resized.shape[1]] = resized
    label = f"{item['file'][:43]}  |  {item['detected_faces']} faces"
    cv2.putText(canvas, label, (x+8, y+height+25), cv2.FONT_HERSHEY_SIMPLEX,
                .48, (20, 20, 20), 1, cv2.LINE_AA)
cv2.imwrite(str(ROOT / 'marked-contact-sheet.jpg'), canvas,
            [int(cv2.IMWRITE_JPEG_QUALITY), 88])

try:
    import matplotlib.pyplot as plt
except ImportError:
    raise SystemExit(0)

names = []
ready = {method: [] for method in ('existing', 'nvidia', 'psycon')}
unknown = {method: [] for method in ready}
for item in items:
    names.append(item['file'].replace('WhatsApp Video 2026-09-27 at ', 'WA '))
    stem = Path(item['file']).stem
    for method in ready:
        path = ROOT / stem / f'{method}-summary.json'
        saved = json.loads(path.read_text()) if path.exists() else {}
        ready[method].append(saved.get('ready_profiles') if saved.get('status') == 'complete' else np.nan)
        unknown[method].append(saved.get('unknown_s') if saved.get('status') == 'complete' else np.nan)

figure, axes = plt.subplots(2, 1, figsize=(15, 9), layout='constrained')
x = np.arange(len(names))
for offset, method in enumerate(ready):
    axes[0].bar(x + (offset-1)*.25, ready[method], .23, label=method.upper())
    axes[1].bar(x + (offset-1)*.25, unknown[method], .23, label=method.upper())
axes[0].set_ylabel('Ready profiles')
axes[1].set_ylabel('Unknown clean speech (seconds)')
for axis in axes:
    axis.set_xticks(x, names, rotation=35, ha='right')
    axis.grid(axis='y', alpha=.25)
    axis.legend(ncols=3)
figure.savefig(ROOT / 'method-comparison.png', dpi=160)
plt.close(figure)
