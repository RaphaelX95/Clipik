"""עיצוב ורינדור של דפי מוצר.

אותו HTML משמש גם לדף שנשמר ב-/p/<slug> וגם לתצוגה המקדימה בבונידו,
כך שמה שרואים בבונידו הוא בדיוק מה שהלקוח רואה.
"""
import html
import re

_IMAGE_RE = re.compile(r"data:image/(?:jpeg|png|webp);base64,[A-Za-z0-9+/=]{1,1500000}")
MAX_IMAGES = 10


def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


def clean_images(images) -> list:
    if not isinstance(images, list):
        return []
    return [img for img in images if isinstance(img, str) and _IMAGE_RE.fullmatch(img)][:MAX_IMAGES]


CSS = """
:root{--ink:#1b1530;--plum:#241b45;--paper:#f4efe6;--accent:#e8542b;--mint:#dff2ea;--muted:#6b6880;--line:#e6dfd2}
*{box-sizing:border-box}
html,body{margin:0;background:var(--paper);color:var(--ink);font-family:Heebo,Arial,sans-serif;-webkit-font-smoothing:antialiased}
.band{background:var(--plum);color:#f7f1e6;padding:56px 20px 130px;position:relative;overflow:hidden}
.band::after{content:"";position:absolute;left:-120px;bottom:-160px;width:360px;height:360px;border-radius:50%;background:radial-gradient(circle,rgba(232,84,43,.75),rgba(232,84,43,0) 70%)}
.wrap{max-width:760px;margin:0 auto;position:relative;z-index:1}
.kicker{display:inline-block;font-size:13px;background:rgba(255,255,255,.12);padding:6px 12px;border-radius:999px;margin-bottom:16px}
h1{font-size:clamp(30px,6vw,46px);line-height:1.12;margin:0 0 14px;font-weight:900}
.price{display:inline-block;font-size:20px;font-weight:700;background:var(--accent);color:#fff;padding:8px 16px;border-radius:12px;margin:4px 0 16px}
.lead{font-size:18px;line-height:1.75;margin:0;opacity:.92;max-width:620px;white-space:pre-line}
.gallery{position:relative;max-width:760px;margin:-86px auto 0;padding:14px;background:#fff;border-radius:28px;box-shadow:0 30px 60px -30px rgba(27,21,48,.45);z-index:2}
.stage{position:relative;aspect-ratio:4/5;border-radius:20px;overflow:hidden;background:var(--mint)}
.slide{display:none;width:100%;height:100%;object-fit:cover}
.slide.on{display:block}
.arrow{position:absolute;top:50%;transform:translateY(-50%);width:44px;height:44px;border-radius:50%;border:0;background:rgba(255,255,255,.92);font-size:22px;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.15)}
.arrow.prev{right:12px}
.arrow.next{left:12px}
.thumbs{display:flex;gap:8px;overflow-x:auto;margin-top:10px;padding:2px}
.thumbs button{flex:0 0 64px;height:64px;padding:0;border-radius:12px;border:2px solid transparent;overflow:hidden;background:none;cursor:pointer}
.thumbs button.on{border-color:var(--accent)}
.thumbs img{width:100%;height:100%;object-fit:cover;display:block}
.sec{max-width:760px;margin:48px auto 0;padding:0 20px}
.sec h2{font-size:24px;font-weight:900;margin:0 0 16px}
.bens{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px}
.ben{background:var(--mint);border-radius:22px;padding:22px 20px}
.ben .n{font-size:14px;font-weight:700;color:var(--accent);letter-spacing:.06em}
.ben p{margin:10px 0 0;font-size:18px;font-weight:700;line-height:1.5}
.revs{display:grid;gap:14px}
.rev{background:#fff;border:1px solid var(--line);border-radius:22px;padding:14px 22px 20px;position:relative}
.rev::before{content:"\\201D";position:absolute;top:2px;left:18px;font-size:64px;line-height:1;color:var(--accent);font-weight:900}
.rev p{margin:0 0 10px;padding-top:22px;font-size:17px;line-height:1.7}
.rev b{font-size:14px;color:var(--muted);font-weight:500}
.faq details{background:#fff;border:1px solid var(--line);border-radius:18px;margin-bottom:10px;padding:0 20px}
.faq summary{list-style:none;cursor:pointer;font-weight:700;font-size:17px;padding:18px 0;display:flex;justify-content:space-between;gap:12px;align-items:center}
.faq summary::-webkit-details-marker{display:none}
.faq summary::after{content:"+";font-size:26px;color:var(--accent);line-height:1}
.faq details[open] summary::after{content:"\\2212"}
.faq details p{margin:0 0 18px;font-size:16px;line-height:1.7;color:#3b3754}
.foot{text-align:center;color:var(--muted);font-size:13px;padding:56px 20px 40px}
@media (max-width:600px){.gallery{margin-top:-70px}.arrow{width:38px;height:38px}}
"""

_GALLERY_JS = """
(function(){
  var slides=document.querySelectorAll('.slide'), thumbs=document.querySelectorAll('.thumbs button'), i=0;
  if(!slides.length) return;
  function show(n){
    i=(n+slides.length)%slides.length;
    slides.forEach(function(s,k){s.classList.toggle('on',k===i)});
    thumbs.forEach(function(t,k){t.classList.toggle('on',k===i)});
  }
  var p=document.querySelector('.prev'), x=document.querySelector('.next');
  if(p) p.addEventListener('click',function(){show(i-1)});
  if(x) x.addEventListener('click',function(){show(i+1)});
  thumbs.forEach(function(t,k){t.addEventListener('click',function(){show(k)})});
})();
"""


def render_product_page(page: dict) -> str:
    product = str(page.get("product") or "").strip()
    headline = str(page.get("headline") or "").strip() or product or "שם המוצר"
    price = str(page.get("price") or "").strip()
    description = str(page.get("description") or "").strip()
    images = clean_images(page.get("images"))
    benefits = [b for b in (page.get("benefits") or []) if isinstance(b, str) and b.strip()]
    reviews = [r for r in (page.get("reviews") or []) if isinstance(r, dict) and str(r.get("text", "")).strip()]
    faq = [f for f in (page.get("faq") or []) if isinstance(f, dict) and str(f.get("q", "")).strip() and str(f.get("a", "")).strip()]

    gallery = ""
    if images:
        slides = "".join(
            f'<img class="slide{" on" if k == 0 else ""}" src="{img}" alt="{esc(headline)} - תמונה {k + 1}">'
            for k, img in enumerate(images)
        )
        controls = ""
        thumbs = ""
        if len(images) > 1:
            controls = '<button class="arrow prev" type="button" aria-label="התמונה הקודמת">›</button><button class="arrow next" type="button" aria-label="התמונה הבאה">‹</button>'
            thumbs = '<div class="thumbs">' + "".join(
                f'<button type="button" class="{"on" if k == 0 else ""}" aria-label="תמונה {k + 1}"><img src="{img}" alt=""></button>'
                for k, img in enumerate(images)
            ) + "</div>"
        gallery = f'<div class="gallery"><div class="stage">{slides}{controls}</div>{thumbs}</div>'

    price_html = f'<div class="price">{esc(price)}</div>' if price else ""
    desc_html = f'<p class="lead">{esc(description)}</p>' if description else ""

    bens_html = ""
    if benefits:
        items = "".join(
            f'<div class="ben"><div class="n">{k + 1:02d}</div><p>{esc(b)}</p></div>' for k, b in enumerate(benefits)
        )
        bens_html = f'<section class="sec"><h2>היתרונות</h2><div class="bens">{items}</div></section>'

    revs_html = ""
    if reviews:
        items = "".join(
            f'<div class="rev"><p>{esc(r.get("text", "")).strip()}</p>'
            + (f'<b>{esc(r.get("name", ""))}</b>' if str(r.get("name", "")).strip() else "")
            + "</div>"
            for r in reviews
        )
        revs_html = f'<section class="sec"><h2>ביקורות לקוחות</h2><div class="revs">{items}</div></section>'

    faq_html = ""
    if faq:
        items = "".join(
            f'<details><summary>{esc(f["q"])}</summary><p>{esc(f["a"])}</p></details>' for f in faq
        )
        faq_html = f'<section class="sec faq"><h2>שאלות נפוצות</h2>{items}</section>'

    return f"""<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>{esc(headline)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>{CSS}</style></head>
<body>
<header class="band"><div class="wrap">
  <span class="kicker">{esc(product) if product else "מוצר חדש"}</span>
  <h1>{esc(headline)}</h1>
  {price_html}
  {desc_html}
</div></header>
{gallery}
{bens_html}
{revs_html}
{faq_html}
<footer class="foot">נוצר באמצעות קליפיק</footer>
<script>{_GALLERY_JS}</script>
</body></html>"""
