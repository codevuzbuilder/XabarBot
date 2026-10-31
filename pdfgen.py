"""pdfgen.py — shaxsiy chat tarixini PDF qiladi (reportlab). Kirill/lotin uchun DejaVuSans shrifti ishlatiladi."""
import io, os, time
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

KIND = {"photo": "rasm", "video": "video", "voice": "ovozli xabar", "video_note": "video xabar", "document": "fayl",
        "audio": "audio", "animation": "GIF", "sticker": "stiker"}
FONTS = [
    ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    ("/Library/Fonts/Arial Unicode.ttf", None),
]
_F = None


def _fonts():
    """(oddiy, qalin, unicode_bormi)"""
    global _F
    if _F: return _F
    for reg, bold in FONTS:
        if os.path.exists(reg):
            try:
                pdfmetrics.registerFont(TTFont("HF", reg))
                pdfmetrics.registerFont(TTFont("HFB", bold if bold and os.path.exists(bold) else reg))
                _F = ("HF", "HFB", True)
                return _F
            except Exception:
                continue
    _F = ("Helvetica", "Helvetica-Bold", False)
    return _F


def _clean(t, uni):
    t = str(t or "")
    if not uni:                                   # shriftsiz holat: faqat lotin-1
        for a in "ʻʼ’‘`": t = t.replace(a, "'")
        t = t.encode("latin-1", "replace").decode("latin-1")
    t = "".join(ch for ch in t if (ch in "\n\t" or ord(ch) >= 32) and ord(ch) <= 0xFFFF and ch not in "\u200d\ufe0f")
    return escape(t).replace("\n", "<br/>")


def build(title, rows):
    """rows: msgs jadvali qatorlari (ts, who, out, kind, text, deleted, old). PDF baytlarini qaytaradi."""
    f, fb, uni = _fonts()
    base = ParagraphStyle("m", fontName=f, fontSize=9.5, leading=13, spaceAfter=3)
    head = ParagraphStyle("h", fontName=fb, fontSize=15, leading=19, spaceAfter=4)
    sub = ParagraphStyle("s", fontName=f, fontSize=9, leading=12, textColor=colors.grey, spaceAfter=8)
    day = ParagraphStyle("d", fontName=fb, fontSize=9, leading=12, textColor=colors.grey, alignment=1, spaceBefore=8, spaceAfter=5)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm,
                            bottomMargin=16 * mm, title="Chat tarixi", author="Bot")

    def footer(c, d):
        c.setFont(f, 8)
        c.setFillColor(colors.grey)
        c.drawCentredString(A4[0] / 2, 8 * mm, str(d.page))

    story = [Paragraph(_clean("Chat tarixi: " + str(title), uni), head)]
    if rows:
        a, z = time.strftime("%d.%m.%Y", time.localtime(rows[0]["ts"])), time.strftime("%d.%m.%Y", time.localtime(rows[-1]["ts"]))
        story.append(Paragraph(f"{len(rows)} ta xabar · {a} — {z}", sub))
    last = ""
    for r in rows:
        d = time.strftime("%d.%m.%Y", time.localtime(r["ts"]))
        if d != last:
            story.append(Paragraph(d, day))
            last = d
        out = bool(r["out"])
        who = "Siz" if out else (r["who"] or title)
        body = _clean(r["text"], uni)
        if r["kind"]:
            tag = f"[{KIND.get(r['kind'], r['kind'])}]"
            body = tag + (" " + body if body else "")
        flags = ""
        if r["old"]: flags += f' <font color="#e67e22">[tahrirlangan; eski: {_clean(r["old"], uni)}]</font>'
        if r["deleted"]: flags += ' <font color="#c0392b">[o\'chirilgan]</font>'
        hm = time.strftime("%H:%M", time.localtime(r["ts"]))
        col = "#1a5fb4" if out else "#222222"
        try:
            story.append(Paragraph(f'<font color="#888888">{hm}</font> <font name="{fb}" color="{col}">{_clean(who, uni)}:</font> {body}{flags}', base))
        except Exception:
            story.append(Paragraph(f"{hm} {_clean(who, uni)}: [xabarni ko'rsatib bo'lmadi]", base))
    if not rows: story.append(Spacer(1, 10))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
