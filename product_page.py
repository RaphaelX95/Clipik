"""עיצוב ורינדור של דפי מוצר.

כל תבנית (layout) בונה את הדף במבנה אחר: תמונה למעלה, תמונה במרכז, תמונה בצד,
קולאז', תמונה מלאה או מגזין. אותו רינדור משמש לדף שנשמר, לתצוגה המקדימה בבונידו
ולדפי הדוגמה, כך שמה שרואים בבונידו הוא מה שהלקוח יקבל.
"""
import html
import json
import re

MAX_IMAGES = 10
# SVG מותר רק כי התמונות ממקור הדוגמאות בלבד. העלאות של משתמשים עוברות המרה ל-JPEG בדפדפן.
_IMAGE_RE = re.compile(r"data:image/(?:jpeg|png|webp|svg\+xml);base64,[A-Za-z0-9+/=]{1,1500000}")

LAYOUTS = {
    "top": "עליונה",
    "center": "במרכז",
    "side": "צד לצד",
    "collage": "קולאז'",
    "overlay": "תמונה מלאה",
    "editorial": "מגזין",
    "stack": "ערימה",
    "frame": "מסגרת",
    "giant": "ענקית",
    "minimal": "מינימלי",
}
# תבניות ישנות שנשמרו לפני שהתבניות הוחלפו
_LEGACY_LAYOUTS = {"modern": "top", "bold": "overlay"}

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
.buy{max-width:820px;margin:48px auto 0;padding:0 20px;text-align:center}
.buy-details{text-align:right;background:#fff;border:1px solid var(--line);border-radius:20px;padding:26px 24px;margin-bottom:28px}
.buy-details h2{font-size:24px;line-height:1.3;margin:0 0 12px}
.buy-details .buy-txt{font-size:17px;line-height:1.8;color:#3b3754;white-space:pre-line;margin:0}
.cta-btn{display:inline-block;max-width:100%;box-sizing:border-box;background:var(--accent);color:#fff;font-weight:800;font-size:19px;line-height:1.2;padding:18px 44px;border-radius:999px;text-decoration:none;box-shadow:0 12px 26px -12px var(--accent)}
.cta-btn:hover{filter:brightness(1.06)}
@media (max-width:600px){.buy{padding:0 16px}.buy-details{padding:22px 18px}.cta-btn{display:block;width:100%;padding:18px 20px;font-size:18px}}
.thumbs{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.thumbs img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:16px}
"""

LAYOUT_CSS = {
    # תמונה גדולה מתחת לכותרת, תמונות נוספות למטה
    # כותרת בראש, תמונה רחבה, ויתרונות בשני טורים
    "stack": """
.stack-head{background:var(--paper);padding:44px 20px 0;text-align:center}
.stack-head .price{margin-inline:auto}
.stack-head .kicker{background:var(--mint)}
.stack-main{max-width:820px;margin:26px auto 0;padding:0 20px}
.stack-main img{width:100%;aspect-ratio:16/10;object-fit:cover;border-radius:24px}
.l-stack .bens{grid-template-columns:1fr 1fr;gap:12px}
.l-stack .ben{background:#fff;border-top:4px solid var(--accent);border-radius:16px;padding:18px}
@media (max-width:600px){.l-stack .bens{grid-template-columns:1fr}}
""",
    # תמונה בתוך מסגרת עם צל מוזז, ויתרונות כרשימת סימון
    "frame": """
.frame-wrap{max-width:900px;margin:32px auto 0;padding:0 20px}
.frame-row{display:grid;grid-template-columns:1fr 1fr;gap:30px;align-items:center;border:2px solid var(--accent);border-radius:32px;padding:28px}
.frame-media img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:20px;box-shadow:12px 12px 0 var(--accent)}
.frame-text .bens{grid-template-columns:1fr;gap:10px}
.l-frame .ben{background:none;border-radius:0;padding:0;display:flex;gap:10px;align-items:flex-start}
.l-frame .ben .n{font-size:0}
.l-frame .ben .n::after{content:"✓";font-size:18px;color:var(--accent);font-weight:900}
.l-frame .ben p{margin:0;font-size:17px}
@media (max-width:700px){.frame-row{grid-template-columns:1fr;padding:20px}}
""",
    # כותרת גדולה מאוד, תמונה עגולה, ויתרונות עם מספרים גדולים
    "giant": """
.giant-head{max-width:900px;margin:0 auto;padding:48px 20px 0}
.l-giant h1{font-size:clamp(40px,9vw,68px);line-height:1.05;letter-spacing:-.01em}
.giant-circle{max-width:420px;margin:36px auto 0;padding:0 20px}
.giant-circle img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:50%;border:10px solid #fff;box-shadow:0 30px 60px -30px rgba(0,0,0,.35)}
.l-giant .bens{grid-template-columns:1fr;gap:26px}
.l-giant .ben{background:none;border-radius:0;padding:0}
.l-giant .ben .n{font-size:48px;font-weight:900;color:var(--accent);line-height:1}
.l-giant .ben p{font-size:22px;margin-top:4px}
""",
    # עמוד שקט: עמודה צרה, הרבה רווח, ויתרונות ברשימה דקה
    "minimal": """
.min-head{max-width:560px;margin:0 auto;padding:68px 20px 0;text-align:center}
.min-head h1{font-size:36px;font-weight:600;letter-spacing:-.01em}
.min-head .price{background:none;color:var(--ink);border:1px solid var(--line)}
.min-head .kicker{background:none;color:#6b6880;padding:0}
.min-img{max-width:420px;margin:40px auto 0;padding:0 20px}
.min-img img{width:100%;aspect-ratio:4/5;object-fit:cover;border-radius:4px}
.l-minimal .sec{max-width:560px}
.l-minimal .bens{grid-template-columns:1fr;gap:0}
.l-minimal .ben{background:none;border-radius:0;padding:16px 0;border-bottom:1px solid var(--line);display:flex;gap:14px;align-items:baseline}
.l-minimal .ben .n{font-size:12px;color:#6b6880;min-width:24px}
.l-minimal .ben p{margin:0;font-size:17px;font-weight:500}
""",
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


DEFAULT_CTA = "להזמנה עכשיו"


def _text_block(product, headline, price, description, cls=""):
    kicker = f'<span class="kicker" data-f="product">{esc(product)}</span>' if product else ""
    price_html = f'<div class="price" data-f="price">{esc(price)}</div>' if price else ""
    desc_html = f'<p class="lead" data-f="description">{esc(description)}</p>' if description else ""
    return f'<div class="{cls}">{kicker}<h1 data-f="headline">{esc(headline)}</h1>{price_html}{desc_html}</div>'


def _benefits(benefits, cls="bens"):
    if not benefits:
        return ""
    items = "".join(f'<div class="ben"><div class="n">{k + 1:02d}</div><p data-ben="{k}">{esc(b)}</p></div>' for k, b in enumerate(benefits))
    return f'<div class="{cls}">{items}</div>'


def _faq(faq):
    if not faq:
        return ""
    items = "".join(f'<details><summary data-faq="{k}">{esc(f["q"])}</summary><p data-faqa="{k}">{esc(f["a"])}</p></details>' for k, f in enumerate(faq))
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
        items = "".join(f'<div class="item"><span>{k + 1:02d}</span><span data-ben="{k}">{esc(b)}</span></div>' for k, b in enumerate(benefits))
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
            chips = '<div class="sec"><div class="chips">' + "".join(f'<span data-ben="{k}">{esc(b)}</span>' for k, b in enumerate(benefits)) + "</div></div>"
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
            text = f'<div><div class="ed-num">{k + 1:02d}</div><p data-ben="{k}">{esc(b)}</p></div>'
            if k < len(pool):
                src = pool[k]
                flip = " flip" if k % 2 else ""
                rows.append(f'<div class="ed-row{flip}"><div class="ed-img">{_img(src, alt)}</div>{text}</div>')
            else:
                rows.append(f'<div class="ed-row noimg">{text}</div>')
        return head + "".join(rows) + _faq(faq)

    if layout == "stack":
        head = f'<header class="stack-head">{_text_block(product, headline, price, description)}</header>'
        media = f'<figure class="stack-main">{_img(main, alt)}</figure>' if main else ""
        more = f'<div class="sec-more"><div class="thumbs">{"".join(_img(i, alt) for i in rest)}</div></div>' if rest else ""
        return head + media + more + f'<section class="sec">{_benefits(benefits)}</section>' + _faq(faq)

    if layout == "frame":
        media = f'<div class="frame-media">{_img(main, alt)}</div>' if main else ""
        text = f'<div class="frame-text">{_text_block(product, headline, price, description)}{_benefits(benefits)}</div>'
        more = f'<div class="sec-more"><div class="thumbs">{"".join(_img(i, alt) for i in rest)}</div></div>' if rest else ""
        return f'<div class="frame-wrap"><div class="frame-row">{media}{text}</div>{more}</div>' + _faq(faq)

    if layout == "giant":
        head = f'<header class="giant-head">{_text_block(product, headline, price, description)}</header>'
        media = f'<div class="giant-circle">{_img(main, alt)}</div>' if main else ""
        more = f'<div class="sec-more"><div class="thumbs">{"".join(_img(i, alt) for i in rest)}</div></div>' if rest else ""
        return head + media + f'<section class="sec">{_benefits(benefits)}</section>' + more + _faq(faq)

    if layout == "minimal":
        head = f'<header class="min-head">{_text_block(product, headline, price, description)}</header>'
        media = f'<figure class="min-img">{_img(main, alt)}</figure>' if main else ""
        more = f'<div class="sec-more"><div class="thumbs">{"".join(_img(i, alt) for i in rest)}</div></div>' if rest else ""
        return head + media + f'<section class="sec">{_benefits(benefits)}</section>' + more + _faq(faq)

    return _text_block(product, headline, price, description)


def _details(details_title, details):
    """הסבר חופשי על המוצר. מופיע מעל השאלות הנפוצות."""
    if not (details_title or details):
        return ""
    title = f'<h2 data-f="details_title">{esc(details_title)}</h2>' if details_title else ""
    text = f'<p class="buy-txt" data-f="details">{esc(details)}</p>' if details else ""
    return f'<section class="buy"><div class="buy-details">{title}{text}</div></section>'


def _cta(cta_text, cta_url):
    """כפתור קריאה לפעולה, בסוף הדף."""
    href = esc(cta_url) if cta_url else "#"
    target = ' target="_blank" rel="noopener"' if cta_url else ""
    return f'<section class="buy"><div class="buy-cta"><a class="cta-btn" href="{href}"{target} data-f="cta_text">{esc(cta_text)}</a></div></section>'


# חלקים שאפשר להסיר מהדף. התוכן נשמר, והסימון קובע רק מה מופיע.
HIDEABLE = ("description", "benefits", "reviews", "faq", "specs", "shipping", "details", "cta")


def _stars(n) -> str:
    n = max(0, min(5, int(round(n))))
    return "★" * n + "☆" * (5 - n)


def _clean_reviews(raw) -> list:
    out = []
    for r in raw or []:
        if not isinstance(r, dict):
            continue
        text = str(r.get("text", "")).strip()
        if not text:
            continue
        try:
            rating = max(1, min(5, int(r.get("rating", 5))))
        except (TypeError, ValueError):
            rating = 5
        out.append({"name": str(r.get("name", "")).strip(), "text": text, "rating": rating})
    return out


def _clean_specs(text) -> list:
    rows = []
    for line in str(text or "").splitlines():
        key, _, value = line.strip().partition(":")
        if key.strip():
            rows.append((key.strip(), value.strip()))
    return rows[:12]


def _rate_line(reviews) -> str:
    if not reviews:
        return ""
    avg = sum(r["rating"] for r in reviews) / len(reviews)
    word = "ביקורת" if len(reviews) == 1 else "ביקורות"
    return f'<div class="rate"><span class="stars">{_stars(avg)}</span><span>{avg:.1f} · {len(reviews)} {word}</span></div>'


def _extra(reviews, specs, shipping) -> str:
    """משלוח, מפרט וביקורות. מופיעים אחרי ההסבר ולפני השאלות, בכל התבניות."""
    parts = []
    if shipping:
        parts.append(f'<div class="sec"><div class="shipinfo">{esc(shipping)}</div></div>')
    if specs:
        rows = "".join(f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in specs)
        parts.append(f'<section class="sec specs"><h2>מפרט</h2><table>{rows}</table></section>')
    if reviews:
        items = "".join(
            f'<div class="rev"><div class="rev-top"><b>{esc(r["name"]) or "לקוח"}</b>'
            f'<span class="stars">{_stars(r["rating"])}</span></div><p>{esc(r["text"])}</p></div>'
            for r in reviews)
        parts.append(f'<section class="sec reviews"><h2>ביקורות לקוחות</h2>{items}</section>')
    return "".join(parts)


FEATURE_CSS = """
.rate{display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:15px;margin:6px 0 4px}
.stars{color:#d9a13b;letter-spacing:2px;font-size:16px}
.shipinfo{background:#fff;border:1px solid var(--line);border-radius:16px;padding:14px 18px;font-size:15px;text-align:center;font-weight:600}
.specs table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:18px;overflow:hidden;font-size:15px}
.specs td{padding:12px 18px;border-bottom:1px solid var(--line);vertical-align:top}
.specs tr:last-child td{border-bottom:0}
.specs td:first-child{width:38%;color:#6b6880;font-weight:600}
.reviews .rev{background:#fff;border:1px solid var(--line);border-radius:18px;padding:16px 18px;margin-bottom:10px}
.reviews .rev-top{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:6px}
.reviews .rev p{margin:0;font-size:16px;line-height:1.7;color:#3b3754}
"""


def _place_buy(body, details_html, cta_html):
    """הסבר מעל השאלות הנפוצות, וכפתור בסוף הדף (אחרי השאלות)."""
    marker = '<section class="sec faq">'
    idx = body.find(marker)
    if idx >= 0:
        body = body[:idx] + details_html + body[idx:]
    else:
        body += details_html
    return body + cta_html


def _faq_sec(faq):
    return _faq(faq) if faq else ""


def _render(page: dict, images: list, edit: bool = False) -> str:
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
    cta_text = str(page.get("cta_text") or "").strip() or DEFAULT_CTA
    cta_url = str(page.get("cta_url") or "").strip()
    if not cta_url.lower().startswith(("http://", "https://")):
        cta_url = ""
    details_title = str(page.get("details_title") or "").strip()
    details = str(page.get("details") or "").strip()
    reviews = _clean_reviews(page.get("reviews"))
    specs = _clean_specs(page.get("specs"))
    shipping = str(page.get("shipping") or "").strip()[:200]
    hidden = {k for k in (page.get("hidden") or []) if k in HIDEABLE}
    # מה שמוסתר לא מופיע בדף, אבל התוכן נשאר שמור ואפשר להחזיר אותו בבונה
    v_description = "" if "description" in hidden else description
    v_benefits = [] if "benefits" in hidden else benefits
    v_faq = [] if "faq" in hidden else faq
    v_reviews = [] if "reviews" in hidden else reviews
    v_specs = [] if "specs" in hidden else specs
    v_shipping = "" if "shipping" in hidden else shipping
    v_details_title = "" if "details" in hidden else details_title
    v_details = "" if "details" in hidden else details
    v_cta = "" if "cta" in hidden else _cta(cta_text, cta_url)
    body = _body(theme["template"], product, headline, price, v_description, images, v_benefits, v_faq)
    body = body.replace("</h1>", "</h1>" + _rate_line(v_reviews), 1)
    body = _place_buy(body, _details(v_details_title, v_details) + _extra(v_reviews, v_specs, v_shipping), v_cta)
    doc = f"""<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>{esc(headline)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family={font_query}:wght@{font_weights}&display=swap" rel="stylesheet">
<style>{root_css}{BASE_CSS}{FEATURE_CSS}{LAYOUT_CSS[theme["template"]]}</style></head>
<body class="l-{theme["template"]}">
{body}
<footer class="foot">נוצר באמצעות קליפיק</footer>
</body></html>"""
    if edit:
        doc = _with_editor(doc, {"product": product, "headline": headline, "price": price,
                                 "description": description, "benefits": benefits, "faq": faq,
                                 "cta_text": cta_text, "cta_url": cta_url,
                                 "details_title": details_title, "details": details,
                                 "reviews": reviews, "specs_text": str(page.get("specs") or ""),
                                 "shipping": shipping, "hidden": sorted(hidden), "theme": theme}, images)
    return doc


def render_product_page(page: dict, edit: bool = False) -> str:
    return _render(page, clean_images(page.get("images")), edit=edit)


# ---- דפי דוגמה ----
# צילומי המוצרים הם תמונות שנוצרו ב-AI, ונמצאים ב-example_images.py.
from example_images import IMAGES as _PHOTOS


_COPY = {
    "ex-1": ("להזמנת הסוקולנט", "על הצמח ועל העציץ",
             "הסוקולנט מגיע בעציץ טרקוטה טבעי, שמכניס מעט חום לכל חלל.\nהעציץ עשוי חרס, ולכן נותן לאדמה להתייבש בין ההשקיות ומונע שורשים רטובים."),
    "ex-2": ("להזמנת הבקבוק", "למה הבקבוק הזה שווה את זה",
             "שתי דפנות נירוסטה עם בידוד ואקום שומרות על הנוזל בטמפרטורה שלו לאורך היום.\nפקק הברגה אטום שלא נפתח בתיק, והבקבוק מתאים גם לתה קר, למים עם קרח ולמשקאות חמים."),
    "ex-3": ("להזמנת המנורה", "שלוש רמות אור, מגע אחד",
             "המנורה מכוונת את עוצמת האור בלחיצה ארוכה על המתג. בלילה אפשר לקרוא בלי להפריע לשינה.\nהבסיס יציב, הכבל ארוך מספיק, והטעינה נעשית דרך USB."),
    "ex-4": ("להזמנת הכרית", "שינה שמתאימה לצורת הראש",
             "הכרית מזיכרון צורה נשענת על הצוואר ומחזירה את עצמה לצורה אחרי כל קימה.\nהכיסוי מתפרק ונשטף במכונה, והמילוי נשאר במקומו גם אחרי תקופה ארוכה של שימוש."),
    "ex-5": ("להזמנת הסט", "שני סכינים, שתי משימות",
             "סכין השף לחיתוך ירקות וחלבונים, וסכין הקילוף לעבודה עדינה על פירות וירקות קטנים.\nהלהבים עשויים נירוסטה ונשמרים חדים בעזרת השחזה קלה. הסט מגיע על בלוק עץ שמשאיר את הסכינים מסודרים על השיש."),
    "ex-6": ("להזמנת התיק", "מחשב נייד, ספר ובקבוק, הכול נכנס",
             "תא מרופד למחשב נייד עד 15.6 אינץ' שומר עליו מפני תנועה ושריטות.\nרצועות גב רכות, רוכסנים חזקים ומעבר לכבל טעינה, כך שאפשר לחבר את הטלפון בלי לפתוח את התיק."),
    "ex-7": ("להזמנת הספל", "עבודת יד בכל ספל",
             "כל ספל נוצר בעבודת יד, ולכן לכל אחד יש שונות קטנה בצורה ובגוון הזיגוג. זה חלק מהיופי שלו.\nמתאים לקפה ולתה. מומלץ לשטוף ביד כדי לשמור על הזיגוג לאורך זמן."),
    "ex-8": ("להזמנת המחצלת", "אחיזה טובה גם בזיעה",
             "משטח הפקק נותן אחיזה טובה לידיים וכפות הרגליים, גם באימון חם. הפקק טבעי, נעים למגע ומרגיש חם יותר מגומי.\nמשקל קל, רצועת נשיאה מצורפת, ומחצלת שנפרשת בקלות על כל משטח."),
    "ex-9": ("להזמנת השעון", "מסך עגול ומעקב יומיומי",
             "מסך עגול מציג את השעה, הצעדים, הדופק והתראות מהטלפון.\nעמיד למים לשחייה קלה ולהזעה, ומודד שינה שעוזר להבין את קצב היום. הטעינה מגנטית ונעשית בקלות."),
    "ex-10": ("להזמנת הסרום", "טפטפת אחת, מינון מדויק",
              "הטפטפת נותנת מינון מדויק, כך שמספיק כמה טיפות לפנים ולצוואר בבוקר ובערב.\nהנוסחה קלה ולא שומנית, מתאימה לעור רגיל ורגיש, ונספגת מהר לפני איפור. מומלץ להמשיך עם קרם לחות."),
}


_SPECS = {
    "ex-1": 'גובה: כ-7 ס״מ\nקוטר עציץ: 8 ס״מ\nחומר: חרס טרקוטה\nניקוז: יש חור ניקוז בתחתית',
    "ex-2": 'נפח: כ-500 מ״ל\nחומר: נירוסטה 304\nשמירת חום: עד 12 שעות\nשמירת קור: עד 24 שעות',
    "ex-3": 'עוצמה: 3 רמות אור\nחיבור: USB\nאורך כבל: 1.5 מטר\nחומר: אלומיניום',
    "ex-4": 'חומר: זיכרון צורה\nמידה: 50 × 70 ס״מ\nכיסוי: נשטף במכונה\nגובה: 12 ס״מ',
    "ex-5": 'מספר להבים: 2\nחומר להב: נירוסטה\nבסיס: בלוק עץ\nשחזור: ביד',
    "ex-6": 'נפח: 25 ליטר\nתא מחשב: עד 15.6 אינץ׳\nחומר: ניילון עמיד\nמשקל: 0.8 ק״ג',
    "ex-7": 'נפח: 350 מ״ל\nחומר: קרמיקה\nזיגוג: בעבודת יד\nשטיפה: ביד',
    "ex-8": 'עובי: 6 מ״מ\nמידות: 183 × 61 ס״מ\nחומר: גומי טבעי ופקק\nמשקל: 1.2 ק״ג',
    "ex-9": 'מסך: AMOLED עגול\nעמידות: 5 ATM\nסוללה: עד 7 ימים\nחיבור: Bluetooth',
    "ex-10": 'נפח: 30 מ״ל\nסוג עור: רגיל ורגיש\nטפטפת: מינון מדויק\nתוקף: 12 חודשים',
}
SHIPPING_DEFAULT = "משלוח עד 3 ימי עסקים · החזרה עד 14 יום"


def _example(slug, name, layout, color, font, product, headline, price, description, benefits, faq, photo):
    cta, details_title, details = _COPY[slug]
    page = {
        "product": product, "headline": headline, "price": price, "description": description,
        "benefits": benefits, "faq": [{"q": q, "a": a} for q, a in faq],
        "cta_text": cta, "cta_url": "", "details_title": details_title, "details": details,
        "specs": _SPECS[slug], "shipping": SHIPPING_DEFAULT,
        "theme": {"template": layout, "font": font, "color": color},
    }
    return {"slug": slug, "name": name, "look": f"{LAYOUTS[layout]} · {font} · {color}", "page": page, "images": [_PHOTOS[photo]]}


EXAMPLES = [
    _example("ex-1", "עציץ טרקוטה עם סוקולנט", "top", "ocean", "heebo", "עציץ טרקוטה עם סוקולנט", "ירוק שלא דורש הרבה", "₪39",
             "סוקולנט קטן בעציץ טרקוטה, מוכן לשולחן העבודה או לחלון. מתאים למי שרוצה צמח שמחזיק מעמד גם כשמשכחים להשקות.",
             ["מתאים לחדר עם אור בהיר", "משקים פעם בשבוע עד שבועיים", "עציץ טרקוטה שנותן לשורשים לנשום"],
             [("כמה פעמים צריך להשקות?", "פעם בשבוע עד שבועיים, כשהאדמה יבשה למגע."),
              ("האם הוא צריך שמש ישירה?", "אור בהיר מספיק. שמש ישירה בשעות החמות עלולה לשרוף את העלים."),
              ("איזה גודל העציץ?", "קוטר של כ-8 ס\"מ וגובה של כ-7 ס\"מ."),
              ("יש ניקוז בתחתית?", "כן, יש חור ניקוז. מומלץ להניח צלחת מתחת."),
              ("מה כלול בהזמנה?", "הסוקולנט בעציץ והוראות טיפול קצרות.")],
             "plant"),
    _example("ex-2", "בקבוק תרמי נירוסטה", "center", "forest", "assistant", "בקבוק תרמי נירוסטה", "הקפה נשאר חם עד הצהריים", "₪79",
             "בקבוק מנירוסטה בעל דופן כפולה, שמשמר חום וקור לאורך היום.",
             ["שומר חום עד 12 שעות", "בלי ריח ובלי טעם מתכת", "נכנס לכל תיק וכל מחזיק כוסות"],
             [("כמה זמן שומר על החום?", "עד 12 שעות לחום ועד 24 שעות לקור, תלוי בטמפרטורה ההתחלתית."),
              ("אפשר לשטוף במדיח?", "מומלץ לשטוף ביד במים חמימים וסבון עדין."),
              ("מאיזה חומר הוא עשוי?", "נירוסטה 304 ללא BPA."),
              ("מה נפח הבקבוק?", "כ-500 מ\"ל."),
              ("יש אחריות?", "שנה אחריות על פגמי ייצור.")],
             "thermos"),
    _example("ex-3", "מנורת שולחן LED", "overlay", "mono", "rubik", "מנורת שולחן LED", "אור נעים לכל שעות היום", "₪129",
             "מנורה עם שלוש רמות אור וטמפרטורת צבע שמתאימה לעבודה, לקריאה ולערב.",
             ["שלוש רמות בהירות", "טמפרטורת צבע מתכווננת", "בסיס יציב שלא מחליק"],
             [("איך מפעילים את המנורה?", "לחיצה קצרה על הכפתור מדליקה, ולחיצה ארוכה משנה את הבהירות."),
              ("יש זיכרון לרמת האור?", "כן, המנורה זוכרת את ההגדרה האחרונה."),
              ("אפשר לחבר ל-USB?", "כן, כבל טעינה מסופק באריזה."),
              ("כמה חשמל היא צורכת?", "פחות מ-8 וואט ברמה הגבוהה ביותר."),
              ("יש אחריות?", "שנה אחריות על פגמי ייצור.")],
             "lamp"),
    _example("ex-4", "כרית שינה מזיכרון", "side", "rose", "frank", "כרית שינה מזיכרון", "לילה שקט מתחיל בכרית נכונה", "₪149",
             "כרית מקצף זיכרון שמתאימה את עצמה לצורת הראש והצוואר, ותומכת בשינה רגועה.",
             ["תמיכה לצוואר ולכתפיים", "חזרה לצורה תוך שניות", "ציפית רכה שנשטפת במכונה"],
             [("איזה גובה כרית מתאים?", "הכרית בגובה בינוני, מתאימה לרוב סוגי השינה."),
              ("אפשר לשטוף את הציפית?", "כן, במכונה במחזור עדין עד 30 מעלות."),
              ("כמה זמן לוקח לכרית להתאפס?", "הכרית חוזרת לצורתה תוך כמה שניות אחרי השימוש."),
              ("יש ריח בהתחלה?", "לעיתים יש ריח קל של חדש, שנעלם תוך יום או יומיים באוויר."),
              ("יש אחריות?", "שנה אחריות על פגמי ייצור.")],
             "pillow"),
    _example("ex-5", "סט סכיני מטבח", "editorial", "plum", "heebo", "סט סכיני מטבח", "חותכים בקלות, בלי להתאמץ", "₪219",
             "סט של שני סכינים, סכין שף וסכין קילוף, על בלוק עץ שמחזיק אותם במקום אחד.",
             ["להב חד שנשאר חד זמן רב", "ידית נוחה שלא מחליקה", "בלוק עץ שמחזיק את שני הסכינים"],
             [("אפשר לשטוף במדיח?", "לא מומלץ. שטיפה ביד ומייבשים מיד מאריכות את חיי הלהב."),
              ("איך שומרים על החדות?", "מומלץ לחדד אחת לכמה חודשים באבן חידוד."),
              ("אילו סכינים כלולים?", "סכין שף וסכין קילוף, יחד עם בלוק העץ."),
              ("מאיזה חומר הלהב?", "פלדה מוקשחת שמתאימה לשימוש יומיומי."),
              ("יש אחריות?", "שנה אחריות על פגמי ייצור.")],
             "knives"),
    _example("ex-6", "תיק גב למחשב נייד", "collage", "ocean", "frank", "תיק גב למחשב נייד", "הכול במקום, והמחשב מוגן", "₪169",
             "תיק גב עם תא מרופד למחשב עד 16 אינץ', כיסים מסודרים ורצועות נוחות לכל היום.",
             ["תא מרופד למחשב עד 16 אינץ'", "כיסים לטלפון, לכבלים ולבקבוק", "רצועות רכות שנשארות נוחות"],
             [("אילו מחשבים נכנסים לתא?", "מחשבים עד 16 אינץ' כולל."),
              ("יש יציאת USB לטעינה?", "כן, בצד התיק יש יציאה לחיבור סוללה חיצונית."),
              ("מאיזה חומר התיק?", "בד עמיד למים עם ציפוי פנימי."),
              ("מה הנפח שלו?", "כ-25 ליטר."),
              ("יש אחריות?", "שנה אחריות על התפרים והרוכסנים.")],
             "backpack"),
    _example("ex-7", "ספל קרמיקה בעבודת יד", "stack", "rose", "rubik", "ספל קרמיקה בעבודת יד", "הבוקר מתחיל בספל שאוהבים", "₪59",
             "ספל קרמיקה עם גימור חול מט, שמחזיק את החום ומתאים לקפה, לתה ולשוקו.",
             ["גימור מט שנעים ביד", "מתאים למיקרוגל ולמדיח כלים", "נפח של כ-350 מ\"ל"],
             [("אפשר לשים במיקרוגל?", "כן. מומלץ להימנע משינויים פתאומיים בטמפרטורה."),
              ("אפשר לשים במדיח כלים?", "כן, במחזור עדין."),
              ("האם כל ספל זהה?", "כל ספל עשוי ביד, ולכן יש הבדלים קטנים בגימור. זה חלק מהאופי שלו."),
              ("מה נפח הספל?", "כ-350 מ\"ל."),
              ("מה קורה אם הספל נשבר בהובלה?", "שולחים החלפה.")],
             "mug"),
    _example("ex-8", "מחצלת יוגה עם רצועת פקק", "frame", "mono", "heebo", "מחצלת יוגה עם רצועת פקק", "תנועה נעימה על מחצלת יציבה", "₪99",
             "מחצלת עבה ונוחה עם משטח שלא מחליק, ורצועת פקק שנושאת אותה בקלות.",
             ["עובי נדיב שנעים לברכיים", "משטח שלא מחליק גם בזיעה", "רצועת פקק לנשיאה קלה"],
             [("מה עובי המחצלת?", "כ-6 מ\"מ."),
              ("מה גודל המחצלת?", "כ-183 על 61 ס\"מ."),
              ("איך מנקים אותה?", "מנגבים במטלית לחה ומייבשים באוויר."),
              ("מאיזה חומר היא עשויה?", "חומר ללא PVC."),
              ("יש אחריות?", "שנה אחריות על פגמי ייצור.")],
             "yoga"),
    _example("ex-9", "שעון חכם עם מסך עגול", "giant", "ocean", "assistant", "שעון חכם עם מסך עגול", "צעדים, דופק ושינה במקום אחד", "₪349",
             "שעון חכם עם מסך עגול, מעקב פעילות, דופק ושינה, ורצועה נוחה ליום שלם.",
             ["מעקב צעדים, דופק ושינה", "סוללה לכמה ימים", "עמיד למים לרחצה רגילה"],
             [("כמה זמן נמשכת הסוללה?", "בשימוש רגיל עד כמה ימים, תלוי בשימוש במסך ובהתראות."),
              ("האם הוא עמיד למים?", "עמיד לרחצה ולגשם. לא מומלץ לשחייה עמוקה."),
              ("עם אילו טלפונים הוא עובד?", "מתחבר לאנדרואיד ולאייפון דרך אפליקציה."),
              ("מה כלול באריזה?", "השעון, כבל טעינה ומדריך קצר."),
              ("יש אחריות?", "שנה אחריות מהיצרן.")],
             "watch"),
    _example("ex-10", "סרום לעור עם טפטפת", "minimal", "plum", "frank", "סרום לעור עם טפטפת", "עור רענן בכמה טיפות", "₪89",
             "סרום מרוכז בבקבוק זכוכית כהה עם טפטפת, לשימוש יומיומי בבוקר או בערב.",
             ["מרקם קל שנספג מהר", "בקבוק זכוכית כהה שמגן על הרכיבים", "מתאים לשימוש יומיומי"],
             [("כמה טיפות להשתמש?", "שתיים עד שלוש טיפות, על פנים נקיות ויבשות."),
              ("מתאים לעור רגיש?", "מומלץ לבדוק על אזור קטן לפני השימוש הראשון."),
              ("מתי משתמשים בו?", "בבוקר או בערב, לפני הקרם."),
              ("מה תוקף המוצר?", "כשנתיים מיום הייצור, ועד כמה חודשים אחרי הפתיחה."),
              ("יש אחריות?", "שנה אחריות על פגמי ייצור.")],
             "serum"),
]

# ---- עריכה ישירה: אותו דף מוצר, עם טקסטים שאפשר ללחוץ ולשנות ----
SECTION_LABELS = (
    ("description", "תיאור קצר"),
    ("benefits", "יתרונות"),
    ("shipping", "משלוח והחזרות"),
    ("specs", "מפרט"),
    ("details", "הסבר מלא"),
    ("reviews", "ביקורות"),
    ("faq", "שאלות נפוצות"),
    ("cta", "כפתור קנייה"),
)


def _section_checks(hidden) -> str:
    """תיבות סימון להצגה או הסתרה של כל חלק בדף. סומן = מוצג."""
    out = []
    for key, label in SECTION_LABELS:
        checked = "" if key in hidden else " checked"
        out.append(f'<label><input type="checkbox" data-hide-key="{key}"{checked}> {label}</label>')
    return "".join(out)


EDITOR_CSS = """
body.pe-on{padding-bottom:210px}
body.pe-on.pe-min{padding-bottom:48px}
[contenteditable]{outline:1px dashed rgba(0,0,0,.3);outline-offset:4px;border-radius:4px;cursor:text}
[contenteditable]:hover{background:rgba(255,236,140,.3)}
[contenteditable]:focus{outline:2px solid #6c5ce7;background:rgba(255,236,140,.22)}
#pe-bar{position:fixed;left:0;right:0;bottom:0;z-index:9999;max-height:30vh;overflow:auto;background:#fff;color:#1d1d1f;border-top:1px solid #ddd;box-shadow:0 -6px 24px rgba(0,0,0,.14);padding:8px 14px;font:13px/1.45 system-ui,sans-serif;text-align:right}
#pe-bar.pe-collapsed{max-height:none;padding-top:6px;padding-bottom:6px}
#pe-bar.pe-collapsed #pe-body{display:none}
#pe-bar .pe-hint{color:#555}
#pe-bar .pe-count{color:#555;font-size:12px}
#pe-bar #pe-back{color:#6c5ce7;font-size:13px;text-decoration:none;font-weight:600}
#pe-bar .pe-row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:6px}
#pe-bar button{font:inherit;padding:6px 14px;border-radius:8px;border:1px solid #6c5ce7;background:#6c5ce7;color:#fff;cursor:pointer}
#pe-bar button:disabled{opacity:.6;cursor:default}
#pe-bar .pe-thumb{display:flex;flex-direction:column;gap:4px;align-items:center}
#pe-bar .pe-thumb img{width:52px!important;height:52px!important;object-fit:cover;border-radius:8px;display:block}
#pe-bar .pe-thumb button{padding:2px 8px;font-size:12px;background:#fff;color:#6c5ce7}
#pe-bar .pe-thumb .pe-del{color:#b42318;border-color:#b42318}
#pe-bar #pe-toggle{padding:3px 10px;font-size:12px;background:#fff;color:#6c5ce7}
#pe-bar #pe-status{color:#555}
#pe-sections label{display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border:1px solid #ddd;border-radius:8px;cursor:pointer;font-size:12px}
#pe-sections input{margin:0;accent-color:#6c5ce7}
"""

EDITOR_BAR = """<div id="pe-bar" dir="rtl" role="region" aria-label="עריכת הדף">
  <div class="pe-row"><a id="pe-back" href="/product-examples.html">→ חזרה לתבניות</a><strong>עריכה ישירה בדף</strong><button id="pe-toggle" type="button" aria-expanded="true">הסתרת העריכה</button></div>
  <div id="pe-body">
    <div class="pe-row"><span class="pe-hint">לחצו על טקסט כדי לשנות אותו. הסגנון, הצבעים והפונט נשארים כמו בתבנית.</span></div>
    <div class="pe-row" id="pe-sections"><span class="pe-hint">מה מוצג בדף:</span>__SECTIONS__</div>
    <div class="pe-row" id="pe-imgs"></div>
    <div class="pe-row"><button id="pe-save" type="button">שמירה ויצירת קישור לדף</button><span id="pe-status" role="status"></span></div>
    <div class="pe-row" id="pe-result" hidden></div>
  </div>
</div>"""

EDITOR_JS = r"""
(function () {
  var data = JSON.parse(document.getElementById('pe-data').textContent);
  var page = data.page;
  var images = data.images.slice();
  var imgBox = document.getElementById('pe-imgs');
  var statusEl = document.getElementById('pe-status');
  var result = document.getElementById('pe-result');
  var saveBtn = document.getElementById('pe-save');

  var LIMIT = 3;
  // חזרה: אם יש היסטוריה בדפדפן חוזרים אליה, אחרת (למשל פתיחה מקישור חיצוני) לעמוד התבניות
  document.getElementById('pe-back').addEventListener('click', function (e) {
    if (window.history.length > 1) { e.preventDefault(); window.history.back(); }
  });
  var toggleBtn = document.getElementById('pe-toggle');
  var bar = document.getElementById('pe-bar');
  document.body.classList.add('pe-on');
  toggleBtn.addEventListener('click', function () {
    var hidden = bar.classList.toggle('pe-collapsed');
    document.body.classList.toggle('pe-min', hidden);
    toggleBtn.textContent = hidden ? 'הצגת העריכה' : 'הסתרת העריכה';
    toggleBtn.setAttribute('aria-expanded', hidden ? 'false' : 'true');
  });
  document.querySelectorAll('details').forEach(function (d) { d.open = true; });
  document.querySelectorAll('a.cta-btn').forEach(function (a) {
    a.addEventListener('click', function (e) { e.preventDefault(); });
  });
  document.querySelectorAll('summary').forEach(function (s) {
    s.addEventListener('click', function (e) { e.preventDefault(); });
  });
  document.querySelectorAll('[data-f],[data-ben],[data-faq],[data-faqa]').forEach(function (el) {
    el.setAttribute('contenteditable', 'true');
    el.setAttribute('spellcheck', 'false');
    el.addEventListener('keydown', function (e) {
      // ההסבר החופשי הוא רב-שורות, אז שם Enter מותר. בשאר השדות הוא נחסם
      if (e.key === 'Enter') { if (el.getAttribute('data-f') !== 'details') e.preventDefault(); return; }
      // רווח בתוך שאלה (summary) היה פותח ומסגיר את התשובה, אז מוסיפים אותו ידנית
      if (e.key === ' ' && el.tagName === 'SUMMARY') { e.preventDefault(); document.execCommand('insertText', false, ' '); }
    });
    el.addEventListener('paste', function (e) {
      e.preventDefault();
      var t = (e.clipboardData || window.clipboardData).getData('text') || '';
      if (el.getAttribute('data-f') !== 'details') t = t.replace(/\s+/g, ' ');
      else t = t.replace(/\r/g, '');
      document.execCommand('insertText', false, t);
    });
  });

  function has(sel) { return !!document.querySelector(sel); }

  function text(sel) {
    var el = document.querySelector(sel);
    return el ? el.textContent.replace(/\s+/g, ' ').trim() : '';
  }

  // טקסט רב-שורות: innerText שומר על שורות חדשות
  function multi(sel) {
    var el = document.querySelector(sel);
    return el ? el.innerText.replace(/\n{3,}/g, '\n\n').trim() : '';
  }

  function collect() {
    var benefits = [];
    (page.benefits || []).forEach(function (orig, k) {
      var sel = '[data-ben="' + k + '"]';
      var v = document.querySelector(sel) ? text(sel) : orig;
      if (v) benefits.push(v);
    });
    var faq = [];
    (page.faq || []).forEach(function (orig, k) {
      // שאלה שמוסתרת לא נמצאת בדף, ולכן שומרים את הערך המקורי שלה
      var qEl = document.querySelector('[data-faq="' + k + '"]');
      var aEl = document.querySelector('[data-faqa="' + k + '"]');
      var q = qEl ? text('[data-faq="' + k + '"]') : orig.q;
      var a = aEl ? text('[data-faqa="' + k + '"]') : orig.a;
      if (q && a) faq.push({ q: q, a: a });
    });
    return {
      product: text('[data-f="product"]') || page.product,
      headline: text('[data-f="headline"]') || page.headline,
      price: text('[data-f="price"]'),
      description: has('[data-f="description"]') ? text('[data-f="description"]') : (page.description || ''),
      cta_text: (has('[data-f="cta_text"]') ? text('[data-f="cta_text"]') : '') || page.cta_text || 'להזמנה עכשיו',
      cta_url: page.cta_url || '',
      details_title: has('[data-f="details_title"]') ? text('[data-f="details_title"]') : (page.details_title || ''),
      details: has('[data-f="details"]') ? multi('[data-f="details"]') : (page.details || ''),
      hidden: page.hidden || [],
      benefits: benefits,
      faq: faq,
      images: images.slice(0, LIMIT),
      theme: page.theme,
      reviews: page.reviews || [],
      specs: page.specs || '',
      shipping: page.shipping || '',
    };
  }

  function shrink(file) {
    return new Promise(function (resolve, reject) {
      var r = new FileReader();
      r.onload = function () {
        var img = new Image();
        img.onload = function () {
          var s = Math.min(1, 1000 / Math.max(img.width, img.height));
          var c = document.createElement('canvas');
          c.width = Math.round(img.width * s);
          c.height = Math.round(img.height * s);
          var x = c.getContext('2d');
          x.fillStyle = '#fff';
          x.fillRect(0, 0, c.width, c.height);
          x.drawImage(img, 0, 0, c.width, c.height);
          resolve(c.toDataURL('image/jpeg', 0.82));
        };
        img.onerror = function () { reject(new Error('bad image')); };
        img.src = r.result;
      };
      r.onerror = function () { reject(r.error); };
      r.readAsDataURL(file);
    });
  }

  // אחרי כל שינוי בתמונות נטען מחדש הדף עם העריכה, כך שהתמונות מוצגות במקום שלהן
  function refreshPage() {
    statusEl.textContent = 'מעדכן את הדף...';
    fetch('/api/product-page/preview?edit=1', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(collect())
    }).then(function (r) {
      return r.json().catch(function () { return {}; });
    }).then(function (d) {
      if (!d.html) throw new Error('no html');
      document.open();
      document.write(d.html);
      document.close();
    }).catch(function () {
      statusEl.textContent = 'לא הצלחנו לעדכן את התצוגה';
    });
  }

  // הצגה או הסתרה של חלק בדף. לפני הרינדור שומרים את מה שנערך עד עכשיו
  document.querySelectorAll('#pe-sections input').forEach(function (cb) {
    cb.addEventListener('change', function () {
      var key = cb.getAttribute('data-hide-key');
      var c = collect();
      var h = (c.hidden || []).filter(function (k) { return k !== key; });
      if (!cb.checked) h.push(key);
      c.hidden = h;
      page = c;
      refreshPage();
    });
  });

  var fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = 'image/png,image/jpeg,image/webp';
  fileInput.hidden = true;
  document.body.appendChild(fileInput);
  var pending = -1;

  // i = מספר התמונה להחלפה, או אורך הרשימה להוספה
  function pickFile(i) { pending = i; fileInput.value = ''; fileInput.click(); }

  fileInput.addEventListener('change', function () {
    var f = fileInput.files[0];
    var i = pending;
    pending = -1;
    if (!f || i < 0) return;
    if (f.size > 10 * 1024 * 1024) { statusEl.textContent = 'תמונה גדולה מדי (מקס 10MB)'; return; }
    statusEl.textContent = 'מעבד את התמונה...';
    shrink(f).then(function (next) {
      if (i >= images.length) { if (images.length < LIMIT) images.push(next); }
      else images[i] = next;
      refreshPage();
    }).catch(function () { statusEl.textContent = 'לא הצלחנו לקרוא את התמונה'; });
  });

  function renderThumbs() {
    imgBox.innerHTML = '';
    var count = document.createElement('span');
    count.className = 'pe-count';
    count.textContent = 'תמונות: ' + images.length + ' מתוך ' + LIMIT;
    imgBox.appendChild(count);
    images.forEach(function (src, i) {
      var box = document.createElement('div');
      box.className = 'pe-thumb';
      var im = document.createElement('img');
      im.src = src;
      im.alt = 'תמונה ' + (i + 1);
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = 'החלפה';
      b.addEventListener('click', function () { pickFile(i); });
      var del = document.createElement('button');
      del.type = 'button';
      del.className = 'pe-del';
      del.textContent = 'הסרה';
      del.addEventListener('click', function () {
        if (images.length <= 1) { statusEl.textContent = 'צריך להשאיר לפחות תמונה אחת'; return; }
        images.splice(i, 1);
        refreshPage();
      });
      box.appendChild(im);
      box.appendChild(b);
      box.appendChild(del);
      imgBox.appendChild(box);
    });
    if (images.length < LIMIT) {
      var add = document.createElement('button');
      add.type = 'button';
      add.textContent = '+ הוספת תמונה';
      add.addEventListener('click', function () { pickFile(images.length); });
      imgBox.appendChild(add);
    }
  }
  renderThumbs();

  function showResult(url) {
    result.hidden = false;
    result.innerHTML = '';
    var a = document.createElement('a');
    a.href = url; a.target = '_blank'; a.rel = 'noopener'; a.textContent = url;
    var copy = document.createElement('button');
    copy.type = 'button'; copy.textContent = 'העתקת הקישור';
    copy.addEventListener('click', function () {
      if (!navigator.clipboard) { statusEl.textContent = 'לא הצלחנו להעתיק'; return; }
      navigator.clipboard.writeText(url).then(
        function () { statusEl.textContent = 'הקישור הועתק'; },
        function () { statusEl.textContent = 'לא הצלחנו להעתיק'; });
    });
    result.appendChild(a);
    result.appendChild(copy);
  }

  saveBtn.addEventListener('click', function () {
    var body = collect();
    if (!body.product) { statusEl.textContent = 'כדי לשמור צריך שם מוצר'; return; }
    saveBtn.disabled = true;
    statusEl.textContent = 'שומר...';
    fetch('/api/product-page', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) { return { ok: r.ok, d: d }; });
    }).then(function (res) {
      if (!res.ok || !res.d.page_url) throw new Error(res.d.error || 'השמירה לא הצליחה, נסו שוב');
      statusEl.textContent = 'הדף נשמר';
      showResult(res.d.page_url);
    }).catch(function (err) {
      statusEl.textContent = err.message;
    }).then(function () {
      saveBtn.disabled = false;
    });
  });
})();
"""


def _with_editor(doc: str, fields: dict, images: list) -> str:
    """מוסיף לדף השמור את סרגל העריכה והסקריפט. הדף עצמו נשאר זהה לתצוגה האמיתית."""
    data = {
        "page": {
            "product": fields["product"],
            "headline": fields["headline"],
            "price": fields["price"],
            "description": fields["description"],
            "cta_text": fields["cta_text"],
            "cta_url": fields["cta_url"],
            "details_title": fields["details_title"],
            "details": fields["details"],
            "reviews": fields["reviews"],
            "hidden": fields["hidden"],
            "specs": fields["specs_text"],
            "shipping": fields["shipping"],
            "benefits": list(fields["benefits"]),
            "faq": [{"q": f["q"], "a": f["a"]} for f in fields["faq"]],
            "theme": fields["theme"],
        },
        "images": list(images),
    }
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\/")
    bar = EDITOR_BAR.replace("__SECTIONS__", _section_checks(fields["hidden"]))
    tail = (
        f"<style>{EDITOR_CSS}</style>{bar}"
        f'<script id="pe-data" type="application/json">{payload}</script>'
        f"<script>{EDITOR_JS}</script>"
    )
    return doc.replace("</body>", tail + "</body>")


def template_data(slug: str):
    """נתוני תבנית לעריכה: התוכן, התמונות והעיצוב של הדוגמה."""
    for ex in EXAMPLES:
        if ex["slug"] == slug:
            return {
                "slug": slug,
                "name": ex["name"],
                "layout": ex["page"]["theme"]["template"],
                "page": ex["page"],
                "images": ex["images"],
            }
    return None


def example_page_html(slug: str):
    for ex in EXAMPLES:
        if ex["slug"] == slug:
            return _render(ex["page"], ex["images"])
    return None


def example_edit_html(slug: str):
    """דף הדוגמה בדיוק כמו בתצוגה האמיתית, עם אפשרות לערוך אותו ישירות."""
    for ex in EXAMPLES:
        if ex["slug"] == slug:
            return _render(ex["page"], ex["images"], edit=True)
    return None
