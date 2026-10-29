"""עיצוב ורינדור של דפי מוצר.

כל תבנית (layout) בונה את הדף במבנה אחר: תמונה למעלה, תמונה במרכז, תמונה בצד,
קולאז', תמונה מלאה או מגזין. אותו רינדור משמש לדף שנשמר, לתצוגה המקדימה בבונידו
ולדפי הדוגמה, כך שמה שרואים בבונידו הוא מה שהלקוח יקבל.
"""
import base64
import html
import re

MAX_IMAGES = 10
_IMAGE_RE = re.compile(r"data:image/(?:jpeg|png|webp);base64,[A-Za-z0-9+/=]{1,1500000}")

LAYOUTS = {
    "top": "עליונה",
    "center": "במרכז",
    "side": "צד לצד",
    "collage": "קולאז'",
    "overlay": "תמונה מלאה",
    "editorial": "מגזין",
}
# תבניות ישנות שנשמרו לפני שהתבניות הוחלפו
_LEGACY_LAYOUTS = {"modern": "top", "minimal": "center", "bold": "overlay"}

FONTS = {
    "heebo": ("Heebo", "400;700;900"),
    "rubik": ("Rubik", "400;700;900"),
    "frank": ("Frank Ruhl Libre", "400;700;900"),
    "assistant": ("Assistant", "400;700"),
}
COLORS = {
    "plum": {"band": "#241b45", "accent": "#e8542b", "paper": "#f4efe6", "mint": "#dff2ea", "ink": "#1b1530"},
    "forest": {"band": "#1f3d2f", "accent": "#c8a24a", "paper": "#f3f1ea", "mint": "#e3eee6", "ink": "#16241c"},
    "ocean": {"band": "#0d3b5c", "accent": "#17a6a3", "paper": "#eef5f8", "mint": "#dcedf3", "ink": "#0b2233"},
    "rose": {"band": "#4a1d2e", "accent": "#e0557a", "paper": "#faf1f3", "mint": "#f6dfe6", "ink": "#2a1420"},
    "mono": {"band": "#111111", "accent": "#f5c518", "paper": "#f5f5f2", "mint": "#e8e8e4", "ink": "#111111"},
}
DEFAULT_THEME = {"template": "top", "font": "heebo", "color": "plum"}


def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


def clean_images(images) -> list:
    if not isinstance(images, list):
        return []
    return [img for img in images if isinstance(img, str) and _IMAGE_RE.fullmatch(img)][:MAX_IMAGES]


def clean_theme(value) -> dict:
    value = value if isinstance(value, dict) else {}
    template = value.get("template")
    template = _LEGACY_LAYOUTS.get(template, template)
    return {
        "template": template if template in LAYOUTS else DEFAULT_THEME["template"],
        "font": value.get("font") if value.get("font") in FONTS else DEFAULT_THEME["font"],
        "color": value.get("color") if value.get("color") in COLORS else DEFAULT_THEME["color"],
    }


BASE_CSS = """
*{box-sizing:border-box}
html,body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--font),Arial,sans-serif;-webkit-font-smoothing:antialiased}
img{display:block;max-width:100%}
.wrap{max-width:820px;margin:0 auto;padding:0 20px}
.kicker{display:inline-block;font-size:13px;padding:6px 12px;border-radius:999px;margin-bottom:14px;background:var(--mint);color:var(--ink)}
h1{font-size:clamp(30px,6vw,50px);line-height:1.12;margin:0 0 14px;font-weight:900}
h2{font-size:24px;font-weight:900;margin:0 0 16px}
.price{display:inline-block;font-size:20px;font-weight:700;background:var(--accent);color:#fff;padding:8px 16px;border-radius:12px;margin:4px 0 14px}
.lead{font-size:18px;line-height:1.75;margin:0;max-width:620px;white-space:pre-line}
.sec{max-width:820px;margin:48px auto 0;padding:0 20px}
.bens{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}
.ben{background:var(--mint);border-radius:22px;padding:22px 20px}
.ben .n{font-size:14px;font-weight:700;color:var(--accent);letter-spacing:.06em}
.ben p{margin:10px 0 0;font-size:18px;font-weight:700;line-height:1.5}
.faq details{background:#fff;border:1px solid #e6dfd2;border-radius:18px;margin-bottom:10px;padding:0 20px}
.faq summary{list-style:none;cursor:pointer;font-weight:700;font-size:17px;padding:18px 0;display:flex;justify-content:space-between;gap:12px;align-items:center}
.faq summary::-webkit-details-marker{display:none}
.faq summary::after{content:"+";font-size:26px;color:var(--accent);line-height:1}
.faq details[open] summary::after{content:"\\2212"}
.faq details p{margin:0 0 18px;font-size:16px;line-height:1.7;color:#3b3754}
.foot{text-align:center;color:#6b6880;font-size:13px;padding:56px 20px 40px}
.thumbs{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.thumbs img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:16px}
"""

LAYOUT_CSS = {
    # תמונה גדולה מתחת לכותרת, תמונות נוספות למטה
    "top": """
.band{background:var(--band);color:#f7f1e6;padding:56px 20px 130px;position:relative;overflow:hidden}
.band .wrap{position:relative;z-index:1}
.band .kicker{background:rgba(255,255,255,.12);color:#f7f1e6}
.hero-img{max-width:820px;margin:-86px auto 0;position:relative;z-index:2;padding:0 20px}
.hero-img img{width:100%;aspect-ratio:4/3;object-fit:cover;border-radius:28px;box-shadow:0 30px 60px -30px rgba(0,0,0,.45)}
.sec-more{max-width:820px;margin:36px auto 0;padding:0 20px}
""",
    # כותרת במרכז, תמונה גדולה באמצע, יתרונות מתחת
    "center": """
.center-head{text-align:center;padding:56px 20px 8px}
.center-head .lead{margin:0 auto}
.center-head .kicker{background:var(--accent);color:#fff}
.center-main{max-width:560px;margin:28px auto 0;padding:0 20px}
.center-main img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:999px 999px 28px 28px;border:10px solid #fff;box-shadow:0 20px 50px -25px rgba(0,0,0,.35)}
.center-list{max-width:560px;margin:36px auto 0;padding:0 20px;text-align:center}
.center-list .item{padding:18px 0;border-bottom:1px solid #e6dfd2;font-size:19px;font-weight:700}
.center-list .item span{color:var(--accent);margin-left:10px;font-size:14px}
.center-list .item:first-child{border-top:1px solid #e6dfd2}
""",
    # טקסט מצד אחד, תמונה מהצד השני
    "side": """
.split{max-width:960px;margin:0 auto;padding:40px 20px 0;display:grid;grid-template-columns:1fr 1fr;gap:32px;align-items:center}
.split-media img.big{width:100%;aspect-ratio:4/5;object-fit:cover;border-radius:24px}
.split-media .small{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}
.split-media .small img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:14px}
.split-text .bens{grid-template-columns:1fr;gap:10px}
.split-text .ben{background:transparent;border-right:4px solid var(--accent);border-radius:0;padding:10px 16px}
@media (max-width:760px){.split{grid-template-columns:1fr}}
""",
    # קולאז' של תמונות: תמונה ראשית גדולה וכמה קטנות סביבה
    "collage": """
.collage-head{padding:52px 20px 20px}
.mosaic{max-width:820px;margin:0 auto;padding:0 20px;display:grid;grid-template-columns:repeat(4,1fr);grid-auto-rows:150px;gap:10px}
.mosaic img{width:100%;height:100%;object-fit:cover;border-radius:16px}
.mosaic img.wide{grid-column:span 2;grid-row:span 2}
.chips{display:flex;flex-wrap:wrap;gap:10px;margin-top:26px}
.chips span{background:var(--mint);padding:10px 16px;border-radius:999px;font-weight:700;font-size:15px}
@media (max-width:600px){.mosaic{grid-template-columns:repeat(2,1fr);grid-auto-rows:130px}}
""",
    # תמונה ראשית ברקע מלא, כותרת מעליה, יתרונות בשורה
    "overlay": """
.full{position:relative;min-height:78vh;display:flex;align-items:flex-end;color:#fff;background:var(--band) center/cover no-repeat}
.full .scrim{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.05) 0%,rgba(0,0,0,.35) 45%,rgba(0,0,0,.9) 100%)}
.full .wrap{position:relative;padding-bottom:56px;padding-top:120px}
.full .kicker{background:var(--accent);color:#fff}
.full h1{font-size:clamp(40px,8vw,68px);font-weight:900}
.full .lead{opacity:.92}
.strip{max-width:820px;margin:-30px auto 0;padding:0 20px;position:relative;z-index:2}
.strip .bens{grid-template-columns:repeat(3,1fr)}
.strip .ben{background:#fff;box-shadow:0 18px 40px -22px rgba(0,0,0,.35)}
.film{display:flex;gap:10px;overflow-x:auto;max-width:820px;margin:28px auto 0;padding:0 20px 4px}
.film img{width:200px;height:200px;object-fit:cover;border-radius:18px;flex:0 0 auto}
@media (max-width:600px){.strip .bens{grid-template-columns:1fr}}
""",
    # מגזין: כל יתרון בשורה נפרדת עם תמונה, לסירוגין
    "editorial": """
.ed-head{padding:56px 20px 10px;max-width:820px;margin:0 auto;border-bottom:3px solid var(--ink)}
.ed-head h1{font-size:clamp(36px,7vw,60px);letter-spacing:-.01em}
.ed-row{max-width:820px;margin:36px auto 0;padding:0 20px;display:grid;grid-template-columns:1fr 1fr;gap:26px;align-items:center}
.ed-row.flip .ed-img{order:2}
.ed-row img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:20px}
.ed-num{font-size:64px;font-weight:900;color:var(--accent);line-height:1}
.ed-row p{font-size:21px;font-weight:700;line-height:1.5;margin:8px 0 0}
.ed-row.noimg{grid-template-columns:1fr}
@media (max-width:600px){.ed-row{grid-template-columns:1fr}.ed-row.flip .ed-img{order:0}}
""",
}


def _text_block(product, headline, price, description, cls=""):
    kicker = f'<span class="kicker">{esc(product)}</span>' if product else ""
    price_html = f'<div class="price">{esc(price)}</div>' if price else ""
    desc_html = f'<p class="lead">{esc(description)}</p>' if description else ""
    return f'<div class="{cls}">{kicker}<h1>{esc(headline)}</h1>{price_html}{desc_html}</div>'


def _benefits(benefits, cls="bens"):
    if not benefits:
        return ""
    items = "".join(f'<div class="ben"><div class="n">{k + 1:02d}</div><p>{esc(b)}</p></div>' for k, b in enumerate(benefits))
    return f'<div class="{cls}">{items}</div>'


def _faq(faq):
    if not faq:
        return ""
    items = "".join(f'<details><summary>{esc(f["q"])}</summary><p>{esc(f["a"])}</p></details>' for f in faq)
    return f'<section class="sec faq"><h2>שאלות נפוצות</h2>{items}</section>'


def _img(src, alt, cls=""):
    return f'<img class="{cls}" src="{src}" alt="{esc(alt)}">'


def _body(layout, product, headline, price, description, images, benefits, faq):
    alt = headline or product or "תמונת המוצר"
    main = images[0] if images else ""
    rest = images[1:]

    if layout == "top":
        hero = (f'<header class="band"><div class="wrap">{_text_block(product, headline, price, description)}</div></header>'
                + (f'<div class="hero-img">{_img(main, alt)}</div>' if main else ""))
        more = f'<div class="sec-more"><div class="thumbs">{"".join(_img(i, alt) for i in rest)}</div></div>' if rest else ""
        return hero + more + f'<section class="sec">{_benefits(benefits)}</section>' + _faq(faq)

    if layout == "center":
        head = f'<header class="center-head">{_text_block(product, headline, price, description)}</header>'
        media = f'<figure class="center-main">{_img(main, alt)}</figure>' if main else ""
        items = "".join(f'<div class="item"><span>{k + 1:02d}</span>{esc(b)}</div>' for k, b in enumerate(benefits))
        lst = f'<div class="center-list">{items}</div>' if items else ""
        more = f'<div class="sec-more"><div class="thumbs">{"".join(_img(i, alt) for i in rest)}</div></div>' if rest else ""
        return head + media + lst + more + _faq(faq)

    if layout == "side":
        if main:
            small = "".join(_img(i, alt, "") for i in rest[:4])
            media = (f'<div class="split-media">{_img(main, alt, "big")}'
                     + (f'<div class="small">{small}</div>' if small else "") + "</div>")
            text = f'<div class="split-text">{_text_block(product, headline, price, description)}{_benefits(benefits, "bens")}</div>'
            return f'<div class="split">{media}{text}</div>' + _faq_sec(faq)
        text = f'<div class="sec">{_text_block(product, headline, price, description)}{_benefits(benefits)}</div>'
        return text + _faq(faq)

    if layout == "collage":
        head = f'<header class="collage-head"><div class="wrap">{_text_block(product, headline, price, description)}</div></header>'
        cells = []
        for k, src in enumerate(images[:7]):
            cells.append(_img(src, alt, "wide" if k == 0 else ""))
        mosaic = f'<div class="mosaic">{"".join(cells)}</div>' if cells else ""
        chips = ""
        if benefits:
            chips = '<div class="sec"><div class="chips">' + "".join(f"<span>{esc(b)}</span>" for b in benefits) + "</div></div>"
        return head + mosaic + chips + _faq(faq)

    if layout == "overlay":
        bg = f' style="background-image:url({main})"' if main else ""
        head = (f'<header class="full"{bg}><div class="scrim"></div>'
                f'<div class="wrap">{_text_block(product, headline, price, description)}</div></header>')
        strip = f'<div class="strip">{_benefits(benefits)}</div>' if benefits else ""
        film = ""
        if rest:
            film = '<div class="film">' + "".join(_img(i, alt) for i in rest) + "</div>"
        return head + strip + film + _faq_sec(faq)

    if layout == "editorial":
        head = f'<header class="ed-head">{_text_block(product, headline, price, description)}</header>'
        rows = []
        pool = images
        for k, b in enumerate(benefits):
            text = f'<div><div class="ed-num">{k + 1:02d}</div><p>{esc(b)}</p></div>'
            if pool:
                src = pool[k % len(pool)]
                flip = " flip" if k % 2 else ""
                rows.append(f'<div class="ed-row{flip}"><div class="ed-img">{_img(src, alt)}</div>{text}</div>')
            else:
                rows.append(f'<div class="ed-row noimg">{text}</div>')
        return head + "".join(rows) + _faq(faq)

    return _text_block(product, headline, price, description)


def _faq_sec(faq):
    return _faq(faq) if faq else ""


def _render(page: dict, images: list) -> str:
    theme = clean_theme(page.get("theme"))
    colors = COLORS[theme["color"]]
    font_name, font_weights = FONTS[theme["font"]]
    font_query = font_name.replace(" ", "+")
    product = str(page.get("product") or "").strip()
    headline = str(page.get("headline") or "").strip() or product or "שם המוצר"
    price = str(page.get("price") or "").strip()
    description = str(page.get("description") or "").strip()
    benefits = [b for b in (page.get("benefits") or []) if isinstance(b, str) and b.strip()]
    faq = [f for f in (page.get("faq") or []) if isinstance(f, dict) and str(f.get("q", "")).strip() and str(f.get("a", "")).strip()]

    root_css = (
        f":root{{--ink:{colors['ink']};--band:{colors['band']};--paper:{colors['paper']};"
        f"--accent:{colors['accent']};--mint:{colors['mint']};--line:#e6dfd2;--font:'{font_name}'}}"
    )
    body = _body(theme["template"], product, headline, price, description, images, benefits, faq)
    return f"""<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>{esc(headline)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family={font_query}:wght@{font_weights}&display=swap" rel="stylesheet">
<style>{root_css}{BASE_CSS}{LAYOUT_CSS[theme["template"]]}</style></head>
<body class="l-{theme["template"]}">
{body}
<footer class="foot">נוצר באמצעות קליפיק</footer>
</body></html>"""


def render_product_page(page: dict) -> str:
    return _render(page, clean_images(page.get("images")))


# ---- דפי דוגמה ----
# תמונות הדוגמה הן איורים פשוטים (SVG) שנוצרים כאן. הן לא מגיעות מהמשתמשים.
_SHAPES = {
    "headphones": '<path d="M120 230 V190 a80 80 0 0 1 160 0 V230" fill="none" stroke="#fff" stroke-width="22" stroke-linecap="round"/>'
                  '<rect x="92" y="212" width="56" height="96" rx="24" fill="#fff"/><rect x="252" y="212" width="56" height="96" rx="24" fill="#fff"/>',
    "bottle": '<rect x="170" y="98" width="60" height="26" rx="8" fill="#fff"/><rect x="180" y="120" width="40" height="30" fill="#fff"/>'
              '<rect x="158" y="146" width="84" height="210" rx="34" fill="#fff"/><rect x="158" y="196" width="84" height="12" fill="rgba(0,0,0,.12)"/>',
    "lamp": '<circle cx="200" cy="190" r="120" fill="rgba(255,255,255,.14)"/>'
            '<path d="M148 150 L252 150 L280 220 L120 220 Z" fill="#fff"/><rect x="193" y="218" width="14" height="108" fill="#fff"/>'
            '<ellipse cx="200" cy="332" rx="70" ry="14" fill="#fff"/>',
    "pillow": '<rect x="86" y="146" width="228" height="136" rx="54" fill="#fff"/>'
              '<path d="M92 214 q108 -44 216 0" fill="none" stroke="rgba(0,0,0,.14)" stroke-width="5"/>',
    "knives": '<rect x="150" y="96" width="16" height="140" rx="7" fill="#fff"/><rect x="192" y="80" width="16" height="156" rx="7" fill="#fff"/>'
              '<rect x="234" y="104" width="16" height="132" rx="7" fill="#fff"/>'
              '<rect x="118" y="232" width="164" height="110" rx="16" fill="#fff"/>'
              '<rect x="146" y="236" width="12" height="60" rx="5" fill="rgba(0,0,0,.2)"/><rect x="194" y="236" width="12" height="60" rx="5" fill="rgba(0,0,0,.2)"/>',
    "backpack": '<path d="M170 128 v-22 a30 30 0 0 1 60 0 v22" fill="none" stroke="#fff" stroke-width="12"/>'
                '<rect x="128" y="120" width="144" height="210" rx="46" fill="#fff"/>'
                '<rect x="165" y="236" width="70" height="60" rx="14" fill="rgba(0,0,0,.14)"/>',
}


def _svg_image(shape: str, c_from: str, c_to: str, zoom: float = 1.0, dx: float = 0, dy: float = 0) -> str:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{c_from}"/>'
        f'<stop offset="1" stop-color="{c_to}"/></linearGradient></defs>'
        '<rect width="400" height="400" fill="url(#g)"/>'
        f'<g transform="translate({200 + dx} {200 + dy}) scale({zoom}) translate(-200 -200)">{_SHAPES[shape]}</g></svg>'
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def _example(slug, name, layout, color, font, product, headline, price, description, benefits, faq, shape, zoom_shots):
    c = COLORS[color]
    shots = [_svg_image(shape, c["accent"], c["band"], zoom=z, dx=dx, dy=dy) for z, dx, dy in zoom_shots]
    page = {
        "product": product, "headline": headline, "price": price, "description": description,
        "benefits": benefits, "faq": [{"q": q, "a": a} for q, a in faq],
        "theme": {"template": layout, "font": font, "color": color},
    }
    return {"slug": slug, "name": name, "look": f"{LAYOUTS[layout]} · {font} · {color}", "page": page, "images": shots}


EXAMPLES = [
    _example("ex-1", "אוזניות אלחוטיות", "top", "ocean", "heebo", "אוזניות אלחוטיות", "שמעו כל רגע בלי חוטים", "₪189",
             "אוזניות קלות עם סוללה שמחזיקה יום שלם, וחיבור מהיר לכל מכשיר.",
             ["סוללה ליום שלם", "חיבור מיידי לכל מכשיר", "קלות שאפשר לשכוח שהן על הראש"],
             [("כמה זמן נמשכת הסוללה?", "עד 10 שעות האזנה רצופה, והטעינה המלאה לוקחת כשעה."),
              ("האם הן עמידות למים?", "כן, הן עמידות לזיעה ולגשם קל, אבל לא לשחייה."),
              ("איך מחברים אותן לטלפון?", "מפעילים את המצב לחיבור ובוחרים אותן ברשימת ה-Bluetooth."),
              ("מה כלול באריזה?", "האוזניות, כבל טעינה, ונרתיק נשיאה."),
              ("יש אחריות?", "שנה אחריות על התקלות של היצרן.")],
             "headphones", [(1, 0, 0), (1.9, 0, 40), (1, 0, 0)]),
    _example("ex-2", "בקבוק תרמי נירוסטה", "center", "forest", "assistant", "בקבוק תרמי נירוסטה", "הקפה נשאר חם עד הצהריים", "₪79",
             "בקבוק מנירוסטה בעל דופן כפולה, שמשמר חום וקור לאורך היום.",
             ["שומר חום עד 12 שעות", "בלי ריח ובלי טעם מתכת", "נכנס לכל תיק וכל מחזיק כוסות"],
             [("כמה זמן שומר על החום?", "עד 12 שעות לחום ועד 24 שעות לקור, תלוי בטמפרטורה ההתחלתית."),
              ("אפשר לשטוף במדיח?", "מומלץ לשטוף ביד במים חמימים וסבון עדין."),
              ("מאיזה חומר הוא עשוי?", "נירוסטה 304 ללא BPA."),
              ("מה נפח הבקבוק?", "כ-500 מ\"ל."),
              ("יש אחריות?", "שנה אחריות על פגמי ייצור.")],
             "bottle", [(1, 0, 0), (1.8, 0, 60), (1, 0, 0)]),
    _example("ex-3", "מנורת שולחן LED", "overlay", "mono", "rubik", "מנורת שולחן LED", "אור נעים לכל שעות היום", "₪129",
             "מנורה עם שלוש רמות אור וטמפרטורת צבע שמתאימה לעבודה, לקריאה ולערב.",
             ["שלוש רמות בהירות", "טמפרטורת צבע מתכווננת", "בסיס יציב שלא מחליק"],
             [("איך מפעילים את המנורה?", "לחיצה קצרה על הכפתור מדליקה, ולחיצה ארוכה משנה את הבהירות."),
              ("יש זיכרון לרמת האור?", "כן, המנורה זוכרת את ההגדרה האחרונה."),
              ("אפשר לחבר ל-USB?", "כן, כבל טעינה מסופק באריזה."),
              ("כמה חשמל היא צורכת?", "פחות מ-8 וואט ברמה הגבוהה ביותר."),
              ("יש אחריות?", "שנה אחריות על פגמי ייצור.")],
             "lamp", [(1, 0, 0), (1.7, 0, -50), (1.3, 40, 0)]),
    _example("ex-4", "כרית שינה מזיכרון", "side", "rose", "frank", "כרית שינה מזיכרון", "לילה שקט מתחיל בכרית נכונה", "₪149",
             "כרית מקצף זיכרון שמתאימה את עצמה לצורת הראש והצוואר, ותומכת בשינה רגועה.",
             ["תמיכה לצוואר ולכתפיים", "חזרה לצורה תוך שניות", "ציפית רכה שנשטפת במכונה"],
             [("איזה גובה כרית מתאים?", "הכרית בגובה בינוני, מתאימה לרוב סוגי השינה."),
              ("אפשר לשטוף את הציפית?", "כן, במכונה במחזור עדין עד 30 מעלות."),
              ("כמה זמן לוקח לכרית להתאפס?", "הכרית חוזרת לצורתה תוך כמה שניות אחרי השימוש."),
              ("יש ריח בהתחלה?", "לעיתים יש ריח קל של חדש, שנעלם תוך יום או יומיים באוויר."),
              ("יש אחריות?", "שנה אחריות על פגמי ייצור.")],
             "pillow", [(1, 0, 0), (1.6, -40, 0), (1.3, 40, 30)]),
    _example("ex-5", "סט סכיני מטבח", "editorial", "plum", "heebo", "סט סכיני מטבח", "חותכים בקלות, בלי להתאמץ", "₪219",
             "סט של ארבעה סכינים מפלדה מוקשחת, עם בלוק עץ שמחזיק את כולם במקום אחד.",
             ["להב חד שנשאר חד זמן רב", "ידית נוחה שלא מחליקה", "בלוק עץ שמחזיק את כל הסכינים"],
             [("אפשר לשטוף במדיח?", "לא מומלץ. שטיפה ביד ומייבשים מיד מאריכות את חיי הלהב."),
              ("איך שומרים על החדות?", "מומלץ לחדד אחת לכמה חודשים באבן חידוד."),
              ("אילו סכינים כלולים?", "סכין שף, סכין ירקות, סכין לחם וסכין קילוף."),
              ("מאיזה חומר הלהב?", "פלדה מוקשחת שמתאימה לשימוש יומיומי."),
              ("יש אחריות?", "שנה אחריות על פגמי ייצור.")],
             "knives", [(1, 0, 0), (1.5, 0, -30), (1.2, -30, 20)]),
    _example("ex-6", "תיק גב למחשב נייד", "collage", "ocean", "frank", "תיק גב למחשב נייד", "הכול במקום, והמחשב מוגן", "₪169",
             "תיק גב עם תא מרופד למחשב עד 16 אינץ', כיסים מסודרים ורצועות נוחות לכל היום.",
             ["תא מרופד למחשב עד 16 אינץ'", "כיסים לטלפון, לכבלים ולבקבוק", "רצועות רכות שנשארות נוחות"],
             [("אילו מחשבים נכנסים לתא?", "מחשבים עד 16 אינץ' כולל."),
              ("יש יציאת USB לטעינה?", "כן, בצד התיק יש יציאה לחיבור סוללה חיצונית."),
              ("מאיזה חומר התיק?", "בד עמיד למים עם ציפוי פנימי."),
              ("מה הנפח שלו?", "כ-25 ליטר."),
              ("יש אחריות?", "שנה אחריות על התפרים והרוכסנים.")],
             "backpack", [(1, 0, 0), (1.8, 0, 30), (1.4, -50, -40), (1.1, 60, 0), (2.0, 0, -60)]),
]


def example_page_html(slug: str):
    for ex in EXAMPLES:
        if ex["slug"] == slug:
            return _render(ex["page"], ex["images"])
    return None
