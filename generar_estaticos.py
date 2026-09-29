"""Genera imágenes locales y descarga Bootstrap 5 para uso estático."""

from io import BytesIO
from pathlib import Path
from urllib.request import urlopen

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent
IMG = BASE / "static" / "img"
CSS = BASE / "static" / "css"
JS = BASE / "static" / "js"
IMG.mkdir(parents=True, exist_ok=True)


def fuente(tamano: int):
    for ruta in (
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if Path(ruta).exists():
            return ImageFont.truetype(ruta, tamano)
    return ImageFont.load_default()


def degradado(ancho, alto, c1, c2):
    img = Image.new("RGB", (ancho, alto), c1)
    draw = ImageDraw.Draw(img)
    for y in range(alto):
        t = y / max(alto - 1, 1)
        color = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
        draw.line((0, y, ancho, y), fill=color)
    return img, draw


def guardar_faro():
    img, draw = degradado(1200, 800, (8, 42, 74), (212, 164, 72))
    draw.ellipse((820, 70, 980, 230), fill=(255, 236, 170))
    draw.polygon([(180, 760), (1020, 760), (900, 560), (280, 560)], fill=(14, 92, 118))
    draw.rectangle((560, 220, 640, 560), fill=(245, 242, 232))
    draw.polygon([(500, 220), (700, 220), (600, 120)], fill=(180, 40, 48))
    draw.rectangle((585, 140, 615, 200), fill=(250, 220, 90))
    draw.text((60, 40), "La Serena", font=fuente(48), fill=(255, 255, 255))
    draw.text((60, 100), "Faro Monumental", font=fuente(28), fill=(243, 215, 130))
    img.save(IMG / "faro_la_serena.png")


def guardar_edificio():
    img, draw = degradado(1200, 800, (230, 220, 200), (90, 130, 150))
    draw.rectangle((220, 260, 980, 720), fill=(236, 228, 210))
    draw.rectangle((200, 230, 1000, 270), fill=(180, 40, 48))
    for x in range(280, 940, 90):
        for y in range(320, 640, 90):
            draw.rectangle((x, y, x + 50, y + 60), fill=(120, 170, 196))
    draw.rectangle((560, 520, 680, 720), fill=(72, 48, 32))
    draw.text((40, 40), "Edificio Consistorial", font=fuente(40), fill=(11, 58, 91))
    img.save(IMG / "edificio_municipal.png")


def guardar_atencion():
    img, draw = degradado(1200, 800, (11, 58, 91), (232, 244, 250))
    draw.rounded_rectangle((140, 220, 1060, 680), radius=28, fill=(255, 255, 255))
    draw.rectangle((140, 220, 1060, 320), fill=(201, 162, 39))
    draw.text((180, 245), "Mesa de atencion ciudadana", font=fuente(36), fill=(28, 20, 3))
    draw.rectangle((200, 380, 520, 620), fill=(11, 58, 91))
    draw.rectangle((560, 380, 1000, 460), fill=(236, 242, 247))
    draw.rectangle((560, 490, 1000, 570), fill=(236, 242, 247))
    img.save(IMG / "atencion_ciudadana.png")


def guardar_escudo():
    img = Image.new("RGB", (256, 256), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse((18, 18, 238, 238), fill=(11, 58, 91), outline=(201, 162, 39), width=10)
    draw.polygon([(128, 48), (188, 170), (68, 170)], fill=(201, 162, 39))
    draw.text((78, 186), "LS", font=fuente(42), fill=(255, 255, 255))
    img.save(IMG / "escudo_la_serena.png")


def descargar(url: str, destino: Path):
    with urlopen(url, timeout=60) as resp:
        destino.write_bytes(resp.read())


def main():
    guardar_faro()
    guardar_edificio()
    guardar_atencion()
    guardar_escudo()
    descargar(
        "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css",
        CSS / "bootstrap.min.css",
    )
    descargar(
        "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js",
        JS / "bootstrap.bundle.min.js",
    )
    print("Recursos estáticos generados.")


if __name__ == "__main__":
    main()
