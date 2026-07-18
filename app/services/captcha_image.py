"""
服务端图验生成 - P0-1

用 PIL (Pillow) 生成 4 位字母数字图(去 I/L/0/1 防混淆):
  - 随机字符
  - 干扰线
  - 噪点
  - 字符轻微旋转
  - 浅色背景

返回: PNG bytes, code_value
"""
from __future__ import annotations

import io
import os
import random
import string

from PIL import Image, ImageDraw, ImageFont

# 字符集(去 I L 0 1)
CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

# 颜色 (RGB)
BG_COLOR = (255, 251, 245)  # #fffbf5
CHAR_COLORS = [
    (37, 99, 235),    # blue
    (249, 115, 22),   # orange
    (16, 185, 129),   # green
    (239, 68, 68),    # red
    (124, 58, 237),   # purple
]

# 字体路径(Win 默认有)
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
_FONT_PATH = None
for _p in _FONT_CANDIDATES:
    if os.path.exists(_p):
        _FONT_PATH = _p
        break


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    if _FONT_PATH:
        try:
            return ImageFont.truetype(_FONT_PATH, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def generate_captcha_png(width: int = 120, height: int = 48, length: int = 4) -> tuple[bytes, str]:
    """
    生成图验 PNG
      返回: (png_bytes, code_value)
    """
    # 生成 code
    code = "".join(random.choices(CHARS, k=length))

    # 创建图片
    img = Image.new("RGB", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # 干扰线
    for _ in range(4):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        line_color = (random.randint(100, 200), random.randint(100, 200), random.randint(100, 200), 100)
        draw.line([(x1, y1), (x2, y2)], fill=line_color, width=1)

    # 噪点
    for _ in range(30):
        x = random.randint(0, width)
        y = random.randint(0, height)
        c = (random.randint(0, 150), random.randint(0, 150), random.randint(0, 150))
        draw.point((x, y), fill=c)

    # 字符(每个单独画, 旋转)
    font_size = 28
    font = _get_font(font_size)
    for i, ch in enumerate(code):
        ch_font = _get_font(font_size + random.randint(-2, 4))
        color = random.choice(CHAR_COLORS)
        # bbox 测宽
        bbox = draw.textbbox((0, 0), ch, font=ch_font)
        ch_w = bbox[2] - bbox[0]
        ch_h = bbox[3] - bbox[1]
        x = 10 + i * 26 + random.randint(0, 4)
        y = (height - ch_h) // 2 + random.randint(-2, 2)

        # 创建单字符透明图层旋转后贴回
        ch_img = Image.new("RGBA", (ch_w + 6, ch_h + 6), (0, 0, 0, 0))
        ch_draw = ImageDraw.Draw(ch_img)
        ch_draw.text((3, 3), ch, fill=color, font=ch_font)
        # 旋转
        angle = random.uniform(-25, 25)
        ch_img = ch_img.rotate(angle, expand=True, resample=Image.BICUBIC)
        img.paste(ch_img, (x, y), ch_img)

    # 输出 PNG
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), code
