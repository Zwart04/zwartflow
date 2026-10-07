from PIL import Image, ImageDraw


def rounded(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def make(size: int) -> Image.Image:
    s = 8 / size
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # background rounded square
    rounded(d, (0, 0, size - 1, size - 1), int(size * 0.22), (14, 16, 20, 255))
    # accent dot nodes
    c = size // 2
    r = int(size * 0.30)
    col = (76, 141, 255, 255)
    # router "Z" arrow: three nodes connected
    pts = [
        (int(c - r * 0.9), int(c - r * 0.9)),
        (int(c + r * 0.9), int(c - r * 0.9)),
        (int(c + r * 0.9), int(c + r * 0.9)),
    ]
    for i in range(len(pts) - 1):
        d.line([pts[i], pts[i + 1]], fill=(231, 234, 240, 255), width=max(2, int(s * 9)))
    node_r = max(2, int(s * 11))
    for i, p in enumerate(pts):
        color = col if i == 1 else (62, 207, 142, 255)
        draw_node(d, p, node_r, color)
    return img


def draw_node(d, p, r, color):
    d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=color)


if __name__ == "__main__":
    from pathlib import Path
    here = Path(__file__).parent
    ico_path = here / "assets" / "icon.ico"
    png_path = here / "assets" / "icon.png"
    ico_path.parent.mkdir(exist_ok=True)
    imgs = [make(x) for x in (256, 128, 64, 48, 32, 16)]
    imgs[0].save(ico_path, format="ICO", sizes=[(s, s) for s in (256, 128, 64, 48, 32, 16)])
    imgs[0].save(png_path, format="PNG")
    print("written", ico_path, png_path)
