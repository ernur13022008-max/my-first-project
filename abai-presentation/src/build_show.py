"""Build the self-contained HTML show from src/deck.html.

Inlines fonts (WOFF2) and images (WebP in the HTML) as data URIs, fills in the credits, and writes:
  ../Abai_Qunanbaiuly_show.html   - standalone file that works offline in any modern browser
  <out_dir>/artifact.html          - the same page without <html>/<head>/<body>, for publishing as an Artifact
Usage: python3 build_show.py [out_dir]
"""
import base64, html, io, json, os, re, sys
from PIL import Image, features

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "build")
os.makedirs(OUT_DIR, exist_ok=True)
WEBP = features.check("webp")


def b64(data: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


_cache = {}
def image_uri(name: str) -> str:
    if name in _cache:
        return _cache[name]
    path = os.path.join(ROOT, "images", name)
    if WEBP:
        im = Image.open(path)
        buf = io.BytesIO()
        if im.mode in ("RGBA", "LA", "P"):
            im.convert("RGBA").save(buf, "WEBP", quality=86, method=6)
        else:
            im.convert("RGB").save(buf, "WEBP", quality=80, method=6)
        uri = b64(buf.getvalue(), "image/webp")
    else:
        mime = "image/png" if name.endswith(".png") else "image/jpeg"
        uri = b64(open(path, "rb").read(), mime)
    _cache[name] = uri
    return uri


FONTS = [
    ("Cormorant Garamond", 600, "normal", "cormorant-600.woff2"),
    ("Cormorant Garamond", 700, "normal", "cormorant-700.woff2"),
    ("Cormorant Garamond", 500, "italic", "cormorant-500i.woff2"),
    ("Cormorant Garamond", 600, "italic", "cormorant-600i.woff2"),
    ("Montserrat", 300, "normal", "montserrat-300.woff2"),
    ("Montserrat", 400, "normal", "montserrat-400.woff2"),
    ("Montserrat", 500, "normal", "montserrat-500.woff2"),
    ("Montserrat", 600, "normal", "montserrat-600.woff2"),
]
font_css = "\n".join(
    f'@font-face {{ font-family: "{fam}"; font-weight: {w}; font-style: {st}; font-display: block; '
    f'src: url({b64(open(os.path.join(HERE, "fonts", f), "rb").read(), "font/woff2")}) format("woff2"); }}'
    for fam, w, st, f in FONTS
)

credits = json.load(open(os.path.join(HERE, "credits.json"), encoding="utf-8"))
def lic_html(c):
    if c["license_url"]:
        return f'<a href="{html.escape(c["license_url"])}" target="_blank" rel="noopener">{html.escape(c["license"])}</a>'
    return html.escape(c["license"])
credits_html = "".join(
    f'<li>{html.escape(c["desc"])} — {html.escape(c["author"])}, {lic_html(c)}, '
    f'<a href="{html.escape(c["source"])}" target="_blank" rel="noopener">Wikimedia Commons</a></li>'
    for c in credits
)
credits_text = "Суреттердің дереккөздері (Wikimedia Commons; кесілген, өлшемі өзгертілген):\n" + "\n".join(
    f'{i}. {c["desc"]} — {c["author"]}, {c["license"]}' + (f' ({c["license_url"]})' if c["license_url"] else "") + f'. {c["source"]}'
    for i, c in enumerate(credits, 1)
) + "\nКілем мен Абай портреті — презентация авторының суреттері. Қаріптер: Cormorant Garamond, Montserrat (SIL OFL)."

src = open(os.path.join(HERE, "deck.html"), encoding="utf-8").read()
src = src.replace("{{FONTS}}", font_css)
src = src.replace("{{CREDITS_HTML}}", credits_html)
src = src.replace("{{CREDITS_TEXT}}", html.escape(credits_text, quote=False))
src = re.sub(r"\{\{IMG:([^}]+)\}\}", lambda m: image_uri(m.group(1)), src)
assert "{{" not in src, "unfilled placeholder"

standalone = os.path.join(ROOT, "Abai_Qunanbaiuly_show.html")
open(standalone, "w", encoding="utf-8").write(src)

head = src.split("<!--ARTIFACT-HEAD-START-->", 1)[1].split("<!--ARTIFACT-HEAD-END-->", 1)[0]
body = src.split("<!--ARTIFACT-BODY-START-->", 1)[1]
body = body.replace("<!--ARTIFACT-BODY-END-->", "").replace("</body>", "").replace("</html>", "")
open(os.path.join(OUT_DIR, "artifact.html"), "w", encoding="utf-8").write(head.strip() + "\n" + body.strip() + "\n")
open(os.path.join(OUT_DIR, "credits.txt"), "w", encoding="utf-8").write(credits_text)

print(f"webp={WEBP}  standalone={os.path.getsize(standalone)/1e6:.2f} MB  artifact={os.path.getsize(os.path.join(OUT_DIR, 'artifact.html'))/1e6:.2f} MB")
