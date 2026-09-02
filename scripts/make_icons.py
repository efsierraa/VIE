"""Genera los iconos PWA de VIE (192 y 512 px)."""
import os

from PIL import Image, ImageDraw, ImageFont

GREEN = (46, 125, 50)
HERE = os.path.join(os.path.dirname(__file__), "..", "app", "static", "icons")


def make(size: int):
    img = Image.new("RGB", (size, size), GREEN)
    draw = ImageDraw.Draw(img)
    font = None
    for candidate in ("arial.ttf", "segoeui.ttf", "DejaVuSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(candidate, int(size * 0.42))
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()
    text = "VIE"
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]), text, fill="white", font=font)
    os.makedirs(HERE, exist_ok=True)
    path = os.path.join(HERE, f"icon-{size}.png")
    img.save(path, format="PNG")
    print(f"OK {path}")


if __name__ == "__main__":
    make(192)
    make(512)
