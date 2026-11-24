"""Prepare images and fonts for the Abai presentation.

Usage: python3 prepare_assets.py <raw_web_dir> <user_images_dir> <ttf_dir> <out_root>
  raw_web_dir     : Wikimedia Commons downloads (standard-size thumbnails)
  user_images_dir : 1.jpg (carpet) and 2.jpg (portrait) supplied by the author
  ttf_dir         : Google Fonts TTF files (Cormorant Garamond, Montserrat)
  out_root        : abai-presentation/ folder
"""
import sys, os, subprocess
from PIL import Image, ImageFilter, ImageOps, ImageDraw, ImageChops, ImageEnhance

raw, user, ttf, out = sys.argv[1:5]
img_out = os.path.join(out, "images")
font_out = os.path.join(out, "src", "fonts")
os.makedirs(img_out, exist_ok=True); os.makedirs(font_out, exist_ok=True)

def save_jpg(im, name, q=84):
    p = os.path.join(img_out, name)
    im.convert("RGB").save(p, "JPEG", quality=q, optimize=True, progressive=True, subsampling=0 if q >= 88 else 2)
    print(f"{name:28s} {im.size[0]}x{im.size[1]}  {os.path.getsize(p)//1024} KB")

def fit_w(im, w):
    if im.width <= w: return im
    return im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)

def crop_ratio(im, r, cx=0.5, cy=0.5):
    """Crop to aspect ratio r=w/h around relative centre (cx, cy)."""
    w, h = im.size
    if w / h > r:
        nw = round(h * r); x = round((w - nw) * cx); return im.crop((x, 0, x + nw, h))
    nh = round(w / r); y = round((h - nh) * cy); return im.crop((0, y, w, y + nh))

# ---------- the author's own images ----------
portrait = Image.open(os.path.join(user, "2.jpg")).convert("RGB")
portrait = portrait.resize((portrait.width * 2, portrait.height * 2), Image.LANCZOS)
portrait = portrait.crop((8, 8, portrait.width - 8, portrait.height - 8))  # drop the thin scan border
portrait = portrait.filter(ImageFilter.UnsharpMask(radius=1.6, percent=55, threshold=2))
save_jpg(portrait, "portrait.jpg", 92)

carpet = Image.open(os.path.join(user, "1.jpg")).convert("RGB")
carpet2 = carpet.resize((carpet.width * 2, carpet.height * 2), Image.LANCZOS)
carpet2 = carpet2.filter(ImageFilter.UnsharpMask(radius=1.4, percent=45, threshold=2))
save_jpg(carpet2, "carpet.jpg", 86)

# central medallion of the carpet, cut into a soft-edged circle
cx, cy, r = 373 * 2, 540 * 2, 188 * 2
med = carpet2.crop((cx - r, cy - r, cx + r, cy + r))
med = ImageEnhance.Contrast(med).enhance(1.08)
S = 4  # supersampled mask for a smooth edge
mask = Image.new("L", (2 * r * S, 2 * r * S), 0)
ImageDraw.Draw(mask).ellipse((0, 0, 2 * r * S - 1, 2 * r * S - 1), fill=255)
mask = mask.resize((2 * r, 2 * r), Image.LANCZOS).filter(ImageFilter.GaussianBlur(1.2))
med.putalpha(mask)
p = os.path.join(img_out, "medallion.png"); med.save(p, optimize=True)
print(f"{'medallion.png':28s} {med.size}  {os.path.getsize(p)//1024} KB")

# ---------- Wikimedia Commons images ----------
def W(name): return Image.open(os.path.join(raw, name + ".jpg")).convert("RGB")

save_jpg(crop_ratio(W("zhidebay_dusk"), 16 / 9, cy=0.55), "zhidebay_dusk.jpg", 82)
save_jpg(W("manuscript"), "manuscript.jpg", 80)
ph = W("abai_photo"); ph = ImageOps.autocontrast(ph.convert("L"), cutoff=0.5).convert("RGB")
save_jpg(ph, "abai_photo.jpg", 86)
save_jpg(fit_w(W("ornate_book"), 1100), "ornate_book.jpg", 82)
save_jpg(fit_w(W("stamp_1965"), 900), "stamp_1965.jpg", 86)
save_jpg(fit_w(W("first_collection"), 1280), "first_collection.jpg", 82)
save_jpg(W("opera"), "opera.jpg", 82)
save_jpg(fit_w(W("moscow_monument"), 900), "moscow_monument.jpg", 82)
save_jpg(fit_w(W("almaty_monument_h"), 1280), "almaty_monument.jpg", 82)
save_jpg(fit_w(W("zhidebay_road"), 1600), "zhidebay_road.jpg", 82)
save_jpg(W("paris_bust"), "paris_bust.jpg", 86)
save_jpg(fit_w(W("abai_joly"), 800), "abai_joly.jpg", 82)
save_jpg(W("tenge_1993"), "tenge_1993.jpg", 90)

# dombra: keep the front view (left instrument) and turn the white studio background transparent
d = W("dombra")
d = d.crop((0, 0, int(d.width * 0.5), d.height))
g = d.convert("L")
# alpha: pixels close to white become transparent, with a soft ramp
alpha = g.point(lambda v: 0 if v >= 246 else (255 if v <= 226 else int((246 - v) * 255 / 20)))
# remove isolated speckles and grow the solid core a touch so thin strings survive
alpha = alpha.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
bbox = alpha.getbbox()
d.putalpha(alpha)
d = d.crop(bbox)
d = d.resize((round(d.width * 1500 / d.height), 1500), Image.LANCZOS)
p = os.path.join(img_out, "dombra.png"); d.save(p, optimize=True)
print(f"{'dombra.png':28s} {d.size}  {os.path.getsize(p)//1024} KB")

# ---------- fonts: subset to Latin + Cyrillic (incl. Kazakh letters) as WOFF2 ----------
unicodes = ",".join([
    "U+0020-007E", "U+00A0-00FF", "U+0400-04FF", "U+2010-2027", "U+2030-203A",
    "U+2116", "U+2190-2193", "U+2212", "U+25C6", "U+2726",
])
fonts = {
    "CormorantGaramond-600.ttf": "cormorant-600.woff2",
    "CormorantGaramond-700.ttf": "cormorant-700.woff2",
    "CormorantGaramond-500i.ttf": "cormorant-500i.woff2",
    "CormorantGaramond-600i.ttf": "cormorant-600i.woff2",
    "Montserrat-300.ttf": "montserrat-300.woff2",
    "Montserrat-400.ttf": "montserrat-400.woff2",
    "Montserrat-500.ttf": "montserrat-500.woff2",
    "Montserrat-600.ttf": "montserrat-600.woff2",
}
for src, dst in fonts.items():
    subprocess.run([sys.executable, "-m", "fontTools.subset", os.path.join(ttf, src),
                    f"--unicodes={unicodes}", "--flavor=woff2", "--layout-features=*",
                    f"--output-file={os.path.join(font_out, dst)}"], check=True)
    print(f"{dst:28s} {os.path.getsize(os.path.join(font_out, dst))//1024} KB")
