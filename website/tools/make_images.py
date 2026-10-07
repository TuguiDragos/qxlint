"""Makes every picture qxlint's website shows from the one icon the repository keeps for it, into website/static.
Run it again only when the icon changes: uv run --with pillow python website/tools/make_images.py"""
from pathlib import Path
from PIL import Image

repo = Path(__file__).resolve().parents[2]
site = repo / "website/static"
images = site / "images"
images.mkdir(parents=True, exist_ok=True)
icon = Image.open(repo / "readme-assets/png/qxlint-icon-256.png").convert("RGBA")
resized = lambda size: icon.resize((size, size), Image.LANCZOS)

for size in (84, 168, 256):
    resized(size).save(images / f"qxlint-icon-{size}.webp", "WEBP", quality=92, method=6)
icon.save(images / "qxlint-icon-256.png", optimize=True)
icon.save(site / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
resized(96).save(site / "favicon-96x96.png", optimize=True)

# Home screen icons are square: iOS and Android draw their own rounded corners. The 256 icon is the largest there is,
# so nothing is made bigger than it.
edge = (12, 16, 22, 255)
for size, name in [(180, "apple-touch-icon.png"), (192, "icon-192.png"), (256, "icon-256.png")]:
    square = Image.new("RGBA", (size, size), edge)
    square.alpha_composite(resized(size))
    square.convert("RGB").save(site / name, optimize=True)
print("done")
