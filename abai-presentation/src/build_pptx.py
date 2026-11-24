"""Assemble the PowerPoint file from the layers rendered by export_layers.js.

Usage: python3 build_pptx.py <layers_dir> <out.pptx>

Each slide gets: a hidden title (for navigation and screen readers), the background picture,
one picture (or group) per element, speaker notes, a slide transition (Morph / Curtains / Fade)
and an auto-playing animation timeline that mirrors the HTML show.
"""
import io, json, os, sys, hashlib
from PIL import Image
from lxml import etree
from pptx import Presentation
from pptx.util import Emu, Pt

LAYERS, OUT = sys.argv[1], sys.argv[2]
PX = 6350  # EMU per CSS pixel on a 1920x1080 stage (12192000 / 1920)
SCALE = 2  # layers were rendered at 2x

NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
NS_P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
NS_P15 = "http://schemas.microsoft.com/office/powerpoint/2012/main"
NS_P159 = "http://schemas.microsoft.com/office/powerpoint/2015/09/main"

manifest = json.load(open(os.path.join(LAYERS, "manifest.json"), encoding="utf-8"))
cache_dir = os.path.join(LAYERS, "_opt")
os.makedirs(cache_dir, exist_ok=True)


# ---------------------------------------------------------------- images
def prepare(part):
    """Trim transparent margins, cap the resolution, return (path, x, y, w, h) in CSS px."""
    src = os.path.join(LAYERS, part["file"])
    box = dict(part["box"])
    key = hashlib.sha1((part["file"] + json.dumps(box)).encode()).hexdigest()[:12]
    im = Image.open(src)
    is_png = part["file"].endswith(".png")
    if is_png and part.get("trim"):
        bbox = im.getchannel("A").getbbox()
        if bbox:
            im = im.crop(bbox)
            box = {"x": box["x"] + bbox[0] / SCALE, "y": box["y"] + bbox[1] / SCALE,
                   "w": (bbox[2] - bbox[0]) / SCALE, "h": (bbox[3] - bbox[1]) / SCALE}
    if part.get("shared") and "medallion" in part["file"]:
        cap = 1100
    elif box["w"] >= 1900 or part.get("photo"):
        cap = 1920
    else:
        cap = 1700
    if max(im.size) > cap:
        r = cap / max(im.size)
        im = im.resize((round(im.width * r), round(im.height * r)), Image.LANCZOS)
    if part.get("shared"):
        out = os.path.join(cache_dir, part["file"])  # identical bytes on every slide -> stored once
        if not os.path.exists(out):
            im.save(out, optimize=True)
    elif is_png:
        out = os.path.join(cache_dir, key + ".png")
        im.save(out, optimize=True)
    else:
        out = os.path.join(cache_dir, key + ".jpg")
        im.convert("RGB").save(out, quality=86, optimize=True, progressive=False)
    return out, box


def bg_image(name):
    out = os.path.join(cache_dir, name)
    if not os.path.exists(out):
        im = Image.open(os.path.join(LAYERS, name)).convert("RGB").resize((2880, 1620), Image.LANCZOS)
        im.save(out, quality=88, optimize=True, subsampling=0)
    return out


# ---------------------------------------------------------------- transitions
def alt_content(requires, choice, fallback='<p:transition spd="slow"><p:fade/></p:transition>'):
    return (f'<mc:AlternateContent xmlns:mc="{NS_MC}" xmlns:p="{NS_P}">'
            f'<mc:Choice xmlns:p14="{NS_P14}" xmlns:p15="{NS_P15}" xmlns:p159="{NS_P159}" Requires="{requires}">{choice}</mc:Choice>'
            f'<mc:Fallback>{fallback}</mc:Fallback></mc:AlternateContent>')

TRANSITIONS = {
    "fade": f'<p:transition xmlns:p="{NS_P}" spd="slow"><p:fade/></p:transition>',
    "morph": alt_content("p159", '<p:transition spd="slow" p14:dur="1700"><p159:morph option="byObject"/></p:transition>'),
    "curtains": alt_content("p15", '<p:transition spd="slow" p14:dur="2750"><p15:prstTrans prst="curtains"/></p:transition>'),
}


# ---------------------------------------------------------------- animations
class Ids:
    def __init__(self, start):
        self.n = start
    def __call__(self):
        self.n += 1
        return self.n

def tgt(spid):
    return f'<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl>'

def set_visible(ids, spid):
    return (f'<p:set><p:cBhvr><p:cTn id="{ids()}" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
            f'{tgt(spid)}<p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr>'
            f'<p:to><p:strVal val="visible"/></p:to></p:set>')

def anim_effect(ids, spid, dur, flt):
    return (f'<p:animEffect transition="in" filter="{flt}"><p:cBhvr><p:cTn id="{ids()}" dur="{dur}"/>{tgt(spid)}</p:cBhvr></p:animEffect>')

def anim_prop(ids, spid, dur, attr, v0, v1):
    return (f'<p:anim calcmode="lin" valueType="num"><p:cBhvr additive="base"><p:cTn id="{ids()}" dur="{dur}" decel="100000" fill="hold"/>'
            f'{tgt(spid)}<p:attrNameLst><p:attrName>{attr}</p:attrName></p:attrNameLst></p:cBhvr><p:tavLst>'
            f'<p:tav tm="0"><p:val><p:strVal val="{v0}"/></p:val></p:tav>'
            f'<p:tav tm="100000"><p:val><p:strVal val="{v1}"/></p:val></p:tav></p:tavLst></p:anim>')

# HTML animation name -> (presetID, presetSubtype, builder)
def ent_fade(ids, s, d):  return set_visible(ids, s) + anim_effect(ids, s, d, "fade")
def ent_float(dy):
    def f(ids, s, d):
        return (set_visible(ids, s) + anim_effect(ids, s, d, "fade") + anim_prop(ids, s, d, "ppt_x", "#ppt_x", "#ppt_x")
                + anim_prop(ids, s, d, "ppt_y", f"#ppt_y+{dy}", "#ppt_y"))
    return f
def ent_slide(dx):
    def f(ids, s, d):
        return (set_visible(ids, s) + anim_effect(ids, s, d, "fade") + anim_prop(ids, s, d, "ppt_x", f"#ppt_x{dx}", "#ppt_x")
                + anim_prop(ids, s, d, "ppt_y", "#ppt_y", "#ppt_y"))
    return f
def ent_zoom(k):
    def f(ids, s, d):
        return (set_visible(ids, s) + anim_prop(ids, s, d, "ppt_w", f"#ppt_w*{k}", "#ppt_w")
                + anim_prop(ids, s, d, "ppt_h", f"#ppt_h*{k}", "#ppt_h") + anim_effect(ids, s, d, "fade"))
    return f
def ent_wipe(flt):
    def f(ids, s, d): return set_visible(ids, s) + anim_effect(ids, s, d, flt)
    return f

ENTRANCE = {
    "fade":    (10, 0, ent_fade),
    "up":      (42, 0, ent_float("0.045")),
    "rise":    (42, 0, ent_float("0.08")),
    "left":    (42, 0, ent_slide("-0.045")),
    "right":   (42, 0, ent_slide("+0.045")),
    "zoom":    (53, 16, ent_zoom("0.8")),
    "zoomout": (53, 16, ent_zoom("1.15")),
    "wipe":    (22, 8, ent_wipe("wipe(left)")),
    "wipe-up": (22, 4, ent_wipe("wipe(down)")),
}

def effect_par(ids, spid, preset, cls, sub, delay, grp, body_fn, repeat=""):
    cid = ids()
    rep = f' repeatCount="{repeat}"' if repeat else ""
    body = body_fn()
    return (f'<p:par><p:cTn id="{cid}" presetID="{preset}" presetClass="{cls}" presetSubtype="{sub}"{rep} fill="hold" grpId="{grp}" nodeType="withEffect">'
            f'<p:stCondLst><p:cond delay="{delay}"/></p:stCondLst><p:childTnLst>{body}</p:childTnLst></p:cTn></p:par>')

def timing_xml(items):
    """items: list of dicts with spid, anim, t (s), du (s), loop."""
    ids = Ids(4)
    pars = []
    grp_of = {}
    for it in sorted(items, key=lambda x: (x["t"] if x["anim"] else -1)):
        s = it["spid"]
        if it["anim"]:
            preset, sub, fn = ENTRANCE[it["anim"]]
            dur = int(min(max(it["du"], .5), 2.0) * 1000)
            g = grp_of[s] = grp_of.get(s, -1) + 1
            pars.append(effect_par(ids, s, preset, "entr", sub, int(it["t"] * 1000), g, lambda fn=fn, s=s, dur=dur: fn(ids, s, dur)))
        if it["loop"] == "spin":
            g = grp_of[s] = grp_of.get(s, -1) + 1
            pars.append(effect_par(ids, s, 8, "emph", 0, 0, g,
                lambda s=s: f'<p:animRot by="21600000"><p:cBhvr><p:cTn id="{ids()}" dur="90000" fill="hold"/>{tgt(s)}'
                            f'<p:attrNameLst><p:attrName>r</p:attrName></p:attrNameLst></p:cBhvr></p:animRot>', repeat="indefinite"))
        elif it["loop"] == "kb":
            g = grp_of[s] = grp_of.get(s, -1) + 1
            pars.append(effect_par(ids, s, 6, "emph", 0, 0, g,
                lambda s=s: f'<p:animScale><p:cBhvr><p:cTn id="{ids()}" dur="20000" decel="60000" fill="hold"/>{tgt(s)}</p:cBhvr>'
                            f'<p:by x="110000" y="110000"/></p:animScale>'))
    if not pars:
        return None
    return (f'<p:timing xmlns:p="{NS_P}"><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>'
            f'<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>'
            f'<p:par><p:cTn id="3" fill="hold"><p:stCondLst><p:cond delay="indefinite"/><p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond></p:stCondLst><p:childTnLst>'
            f'<p:par><p:cTn id="4" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>{"".join(pars)}</p:childTnLst></p:cTn></p:par>'
            f'</p:childTnLst></p:cTn></p:par>'
            f'</p:childTnLst></p:cTn>'
            f'<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>'
            f'<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst>'
            f'</p:seq></p:childTnLst></p:cTn></p:par></p:tnLst></p:timing>')


# ---------------------------------------------------------------- build
prs = Presentation()
prs.slide_width, prs.slide_height = Emu(1920 * PX), Emu(1080 * PX)
layout = prs.slide_layouts[5]  # "Title Only"
cp = prs.core_properties
cp.title, cp.subject, cp.language = "Абай Құнанбайұлы", "Ақын, ойшыл, ағартушы, сазгер", "kk-KZ"
cp.author = cp.last_modified_by = ""

def emu(v):
    return Emu(int(round(v * PX)))

prev_names = set()
for si, sd in enumerate(manifest):
    slide = prs.slides.add_slide(layout)
    # hidden title: kept for the slide list, navigation and screen readers, covered by the background
    title = slide.shapes.title
    title.left, title.top, title.width, title.height = emu(140), emu(120), emu(1200), emu(110)
    title.text = sd["title"]
    for p in title.text_frame.paragraphs:
        for r in p.runs:
            r.font.size = Pt(28)
            r.font.name = "Arial"
    bg = slide.shapes.add_picture(bg_image(sd["bg"]), 0, 0, prs.slide_width, prs.slide_height)
    bg.name = "Фон"
    bg._element.nvPicPr.cNvPr.set("descr", "")

    names_here = set()
    items = []
    for el in sd["els"]:
        parts = [prepare(p) for p in el["parts"]]
        if len(parts) == 1:
            path, b = parts[0]
            shp = slide.shapes.add_picture(path, emu(b["x"]), emu(b["y"]), emu(b["w"]), emu(b["h"]))
            cnv = shp._element.nvPicPr.cNvPr
        else:
            shp = slide.shapes.add_group_shape()
            for (path, b), part_name in zip(parts, ["Фотосурет", "Жиектеме"]):
                inner = shp.shapes.add_picture(path, emu(b["x"]), emu(b["y"]), emu(b["w"]), emu(b["h"]))
                inner.name = part_name
                inner._element.nvPicPr.cNvPr.set("descr", "")
            cnv = shp._element.nvGrpSpPr.cNvPr
        label = (el["alt"] or "Безендіру")
        shp.name = el["name"] or (label if len(label) <= 40 else label[:39] + "…")
        cnv.set("descr", el["alt"] or "")
        anim = el["anim"]
        # a Morph-linked object that was already on the previous slide glides into place instead of re-entering
        if el["name"] and el["name"] in prev_names:
            anim = None
        if el["name"]:
            names_here.add(el["name"])
        if anim or el["loop"]:
            items.append({"spid": shp.shape_id, "anim": anim, "t": el["t"], "du": el["du"], "loop": el["loop"]})
    prev_names = names_here

    slide.notes_slide.notes_text_frame.text = sd["notes"]

    sld = slide._element
    clr = sld.find(f"{{{NS_P}}}clrMapOvr")
    tr = etree.fromstring(TRANSITIONS[sd["tr"]])
    clr.addnext(tr)
    tx = timing_xml(items)
    if tx:
        tr.addnext(etree.fromstring(tx))

prs.save(OUT)
print(f"saved {OUT}  {os.path.getsize(OUT) / 1e6:.1f} MB, {len(prs.slides)} slides")
