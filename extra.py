"""extra.py — 🎨 dizayn, ✏️ tugma nomi, 💎 premium emoji, 📢 majburiy kanallar, ⚡ avto-to'lov va 💳 Click ulash, 🕘 tarix (PDF)."""
import re, time
from core import *
from pay import *
import pdfgen

PER = 8                                                  # dizayn panelida bir sahifadagi tugmalar soni
NEXT = {"primary": "success", "success": "danger", "danger": "primary"}     # ko'k → yashil → qizil → ko'k
SNAME = {"primary": "🔵 ko'k", "success": "🟢 yashil", "danger": "🔴 qizil"}
MODES = {"c": "🎨 DIZAYN\nTugma ustiga bosing: ko'k → yashil → qizil → ko'k",
         "e": "✏️ TAHRIRLASH\nNomini o'zgartirmoqchi bo'lgan tugmani bosing",
         "m": "💎 PREMIUM EMOJI\nTugmani bosing, so'ng premium emoji yuboring"}


def keys_of(s, grp):
    return [k for k in ROUTES if ((k in ADMIN_KEYS) == (grp == "a")) and (s.main or k not in MAIN_ONLY)]


def panel(s, mode, grp, page):
    allk = list(ROUTES)
    ks = keys_of(s, grp)
    pages = max(1, (len(ks) + PER - 1) // PER)
    page = max(0, min(page, pages - 1))
    rows, line = [], []
    for k in ks[page * PER:(page + 1) * PER]:
        b = btn(k)
        b["callback_data"] = f"b|{mode}|{allk.index(k)}|{grp}|{page}"
        line.append(b)
        if len(line) == 2: rows.append(line); line = []
    if line: rows.append(line)
    nav = []
    if page > 0: nav.append(ib("⬅️", "primary", cb=f"p|{mode}|{grp}|{page - 1}"))
    nav.append(ib(f"{page + 1}/{pages}", "primary", cb="noop"))
    if page < pages - 1: nav.append(ib("➡️", "primary", cb=f"p|{mode}|{grp}|{page + 1}"))
    rows.append(nav)
    other = "a" if grp == "u" else "u"
    rows.append([ib("⚙️ Admin tugmalari" if other == "a" else "👤 Foydalanuvchi tugmalari", "success", cb=f"p|{mode}|{other}|0")])
    return MODES[mode], ik(rows)


def _edit_markup(s, c, mk):
    s.call("editMessageReplyMarkup", chat_id=c["message"]["chat"]["id"], message_id=c["message"]["message_id"], reply_markup=mk)


def f_design(s, uid):
    t, mk = panel(s, "c", "u", 0); s.send(uid, t, inl=mk)


def f_edit(s, uid):
    t, mk = panel(s, "e", "u", 0); s.send(uid, t, inl=mk)


def f_emoji(s, uid):
    t, mk = panel(s, "m", "u", 0); s.send(uid, t, inl=mk)


def f_design_reset(s, uid):
    reset_design()
    s.send(uid, "♻️ Dizayn asl holatiga qaytarildi (ranglar, nomlar, emojilar).", main_rows(uid))


def menu_keys(s, uid):
    return [(b if isinstance(b, str) else b[0]) for r in main_rows(uid) for b in r]


def f_emoji_bulk(s, uid):
    ks = menu_keys(s, uid)
    STATE[uid] = ("emoji_bulk",)
    lst = "\n".join(f"{i + 1}. {esc(k)}" for i, k in enumerate(ks))
    s.send(uid, "💎 <b>Ommaviy premium emoji</b>\nBitta xabarda premium emojilarni shu tartibda yuboring "
                f"(har bir tugmaga bittadan, ortiqchasi tashlab yuboriladi):\n\n{lst}", [[("🏠 Menyu", "")]])


@cbq("noop")
def cb_noop(s, uid, c, a): return None


@cbq("p")
def cb_page(s, uid, c, a):
    if not is_admin(uid): return None
    mode, grp, page = a[0], a[1], int(a[2])
    _edit_markup(s, c, panel(s, mode, grp, page)[1])


@cbq("b")
def cb_btn(s, uid, c, a):
    if not is_admin(uid): return None
    mode, i, grp, page = a[0], int(a[1]), a[2], int(a[3])
    ks = list(ROUTES)
    if i >= len(ks): return None
    k = ks[i]
    if mode == "c":
        new = NEXT[cur_style(k)]
        bset(k, style=new)
        _edit_markup(s, c, panel(s, mode, grp, page)[1])
        return f"{shown(k)}: {SNAME[new]}"
    if mode == "e":
        STATE[uid] = ("btnedit", i)
        s.send(uid, f"✏️ <b>{esc(shown(k))}</b> tugmasi uchun yangi nomni kiriting.\n"
                    f"(Asl nomiga qaytarish: <code>-</code>)", [[("🏠 Menyu", "")]])
    else:
        STATE[uid] = ("emoji", i)
        s.send(uid, f"💎 <b>{esc(shown(k))}</b> tugmasi uchun <b>premium emoji</b> yuboring.\n"
                    f"(O'chirish: <code>0</code>)", [[("🏠 Menyu", "")]])
    return None


@state("btnedit")
def st_btnedit(s, uid, st, m):
    if not is_admin(uid): return s.menu(uid)
    k = list(ROUTES)[st[1]]
    new = (m.get("text") or "").strip()
    if not new: return s.send(uid, "❌ Matn yuboring.")
    if new == "-": bset(k, label=None)
    else:
        if len(new) > 40: return s.send(uid, "❌ Juda uzun (40 belgigacha).")
        if label_conflict(k, new): return s.send(uid, "❌ Bunday nomli tugma allaqachon bor. Boshqa nom yuboring.")
        bset(k, label=new)
    STATE.pop(uid, None)
    s.send(uid, f"✅ <b>{esc(k)}</b> → <b>{esc(shown(k))}</b>", main_rows(uid))


def emoji_ids(m):
    return [e["custom_emoji_id"] for e in (m.get("entities") or []) if e.get("type") == "custom_emoji"]


@state("emoji")
def st_emoji(s, uid, st, m):
    if not is_admin(uid): return s.menu(uid)
    k = list(ROUTES)[st[1]]
    ids = emoji_ids(m)
    if (m.get("text") or "").strip() == "0": bset(k, emoji=None); done = "o'chirildi"
    elif ids: bset(k, emoji=ids[0]); done = "o'rnatildi"
    else: return s.send(uid, "❌ Premium emoji yuboring (yoki o'chirish uchun 0).")
    STATE.pop(uid, None)
    s.send(uid, f"💎 {esc(k)}: {done}", main_rows(uid))


@state("emoji_bulk")
def st_emoji_bulk(s, uid, st, m):
    if not is_admin(uid): return s.menu(uid)
    ids = emoji_ids(m)
    if not ids: return s.send(uid, "❌ Xabarda premium emoji yo'q. Premium emojilarni yuboring.")
    ks = menu_keys(s, uid)
    for k, e in zip(ks, ids): bset(k, emoji=e)
    STATE.pop(uid, None)
    s.send(uid, f"💎 {min(len(ks), len(ids))} ta tugmaga premium emoji qo'yildi.", main_rows(uid))


# ----------------------------- 📢 majburiy kanallar -----------------------------
def ch_panel():
    chs = channels()
    txt = ("📢 <b>Majburiy kanallar</b>\n" +
           ("\n".join(f"• {esc(c['title'])} — <code>{esc(c['id'])}</code>" for c in chs) or "Hozircha yo'q.") +
           "\n\n⚠️ Bot kanalda <b>admin</b> bo'lishi shart. O'chirish uchun kanal tugmasini bosing.")
    rows = [[ib("❌ " + str(c["title"] or c["id"])[:30], "danger", cb="cd|" + c["id"])] for c in chs]
    rows.append([ib("➕ Kanal qo'shish", "success", cb="ca")])
    return txt, ik(rows)


def f_channels(s, uid):
    t, mk = ch_panel(); s.send(uid, t, inl=mk)


@cbq("ca")
def cb_chadd(s, uid, c, a):
    if not is_admin(uid): return None
    STATE[uid] = ("chadd",)
    s.send(uid, "➕ Kanalni yuboring: <code>@kanal_nomi</code>, <code>-100…</code> ID yoki kanaldan biror postni forward qiling.\n"
                "Avval botni kanalga <b>admin</b> qiling.", [[("🏠 Menyu", "")]])


@cbq("cd")
def cb_chdel(s, uid, c, a):
    if not is_admin(uid): return None
    run("DELETE FROM channels WHERE id=?", ("|".join(a),))
    t, mk = ch_panel()
    s.call("editMessageText", chat_id=c["message"]["chat"]["id"], message_id=c["message"]["message_id"],
           text=t, parse_mode="HTML", reply_markup=mk)
    return "🗑 O'chirildi"


@state("chadd")
def st_chadd(s, uid, st, m):
    if not is_admin(uid): return s.menu(uid)
    t = (m.get("text") or "").strip()
    fo = m.get("forward_origin") or {}
    cid = None
    if fo.get("type") == "channel": cid = fo["chat"]["id"]
    elif "t.me/" in t: cid = "@" + t.split("t.me/")[-1].split("/")[0].split("?")[0]
    elif t.startswith("@") or t.lstrip("-").isdigit(): cid = t
    if cid is None: return s.send(uid, "❌ @kanal_nomi, -100… ID yoki forward qilingan post yuboring.")
    ch = s.call("getChat", chat_id=cid)
    if not ch: return s.send(uid, f"❌ Kanal topilmadi: {esc(s.err)}")
    me = s.call("getChatMember", chat_id=ch["id"], user_id=s.id) or {}
    if me.get("status") not in ("administrator", "creator"):
        return s.send(uid, "❌ Bot bu kanalda admin emas. Avval botni kanalga <b>admin</b> qiling, so'ng qayta yuboring.")
    uname = ch.get("username")
    link = f"https://t.me/{uname}" if uname else (ch.get("invite_link") or s.call("exportChatInviteLink", chat_id=ch["id"]) or "")
    run("INSERT OR REPLACE INTO channels VALUES(?,?,?)", ("@" + uname if uname else str(ch["id"]), ch.get("title") or uname, link))
    STATE.pop(uid, None)
    t, mk = ch_panel()
    s.send(uid, "✅ Kanal qo'shildi.\n\n" + t, inl=mk)


@cbq("chk")
def cb_chk(s, uid, c, a):
    reg(uid)
    if gate(s, uid): return "❌ Hali hamma kanalga a'zo emassiz."
    s.call("deleteMessage", chat_id=c["message"]["chat"]["id"], message_id=c["message"]["message_id"])
    s.menu(uid, g("welcome_text"))
    return None


# ----------------------------- ⚡ Tezcheck va 💳 Click ulash -----------------------------
def f_tc_setup(s, uid):
    STATE[uid] = ("tc1",)
    s.send(uid, "⚡ <b>Avto to'lov ulash — tezcheck.uz</b>\n\n1/2 — <b>Hisob API</b> kalitini yuboring:", [[("🏠 Menyu", "")]])


@state("tc1")
def st_tc1(s, uid, st, m):
    if not is_admin(uid): return s.menu(uid)
    t = (m.get("text") or "").strip()
    if len(t) < 8: return s.send(uid, "❌ Kalit noto'g'ri ko'rinadi. Hisob API kalitini qayta yuboring.")
    s.call("deleteMessage", chat_id=uid, message_id=m["message_id"])
    setv("tc_hisob", t)
    STATE[uid] = ("tc2",)
    s.send(uid, "✅ Hisob API saqlandi.\n\n2/2 — endi <b>Kassa API</b> kalitini yuboring:")


@state("tc2")
def st_tc2(s, uid, st, m):
    if not is_admin(uid): return s.menu(uid)
    t = (m.get("text") or "").strip()
    if len(t) < 8: return s.send(uid, "❌ Kalit noto'g'ri ko'rinadi. Kassa API kalitini qayta yuboring.")
    s.call("deleteMessage", chat_id=uid, message_id=m["message_id"])
    setv("tc_key", t)
    setv("autopay", "1")                                   # ikkala kalit kiritilgach avto to'lov avtomatik yonadi
    STATE.pop(uid, None)
    try: res = f"💼 Tezcheck balansi: <b>{esc(tc_balance())}</b>"
    except Exception as e:
        res = (f"⚠️ Kalitlar saqlandi, lekin tekshiruvda xato: {esc(e)}\n"
               "Kalitlarni tekshiring yoki «⚡ Tezcheck» bo'limidagi «🛣 … yo'li» tugmalarini Tezcheck hujjatiga moslang.")
    s.send(uid, "✅ <b>Avto to'lov yoqildi!</b>\n" + res, main_rows(uid))


def f_click_setup(s, uid):
    STATE[uid] = ("clk",)
    s.send(uid, "💳 <b>Click ulash (Telegram Payments)</b>\n1) @BotFather → /mybots → shu botni tanlang → <b>Payments</b>\n"
                "2) <b>Click</b> ni tanlab, ulanishni yakunlang\n3) BotFather bergan <b>provider token</b>ni shu yerga yuboring:",
           [[("🏠 Menyu", "")]])


@state("clk")
def st_clk(s, uid, st, m):
    if not is_admin(uid): return s.menu(uid)
    t = (m.get("text") or "").strip()
    if ":" not in t or len(t) < 20: return s.send(uid, "❌ Bu provider tokenga o'xshamaydi (123456789:TEST:xxxx). Qayta yuboring.")
    s.call("deleteMessage", chat_id=uid, message_id=m["message_id"])
    r = s.call("createInvoiceLink", title="Test", description="Test", payload="test", provider_token=t, currency="UZS",
               prices=[{"label": "Test", "amount": int((num("min_topup") or 5000) * 100)}])
    if r is None and re.search(r"provider|token", s.err or "", re.I):
        return s.send(uid, f"❌ Telegram tokenni qabul qilmadi: {esc(s.err)}\nTokenni qayta yuboring.")
    setv("click_token", t)
    setv("click_on", "1")
    STATE.pop(uid, None)
    warn = "" if r else f"\n⚠️ Tekshiruvda ogohlantirish: {esc(s.err)}"
    s.send(uid, "✅ <b>Click yoqildi!</b> Endi «💳 Balans to'ldirish» da «💳 Click orqali» tugmasi chiqadi." + warn, main_rows(uid))


# ----------------------------- 🕘 Tarixim (PDF) -----------------------------
@route("🕘 Tarixim")
def r_chat_hist(s, uid, m):
    rs = q("SELECT chat, COALESCE(MAX(chat_name), MAX(CASE WHEN out=0 THEN who END), '') nm, COUNT(*) n, MAX(ts) last "
           "FROM msgs WHERE owner=? GROUP BY chat ORDER BY last DESC LIMIT 30", (uid,))
    if not rs:
        return s.send(uid, "🕘 Hozircha tarix yo'q. Akkauntni ulang — shundan so'ng xabarlar shu yerda saqlanadi.", main_rows(uid))
    rows = [[ib(f"👤 {(r['nm'] or r['chat'])[:28]} ({r['n']})", "primary", cb=f"h|{r['chat']}")] for r in rs]
    s.send(uid, "🕘 <b>Tarix</b> — shaxsiy chatni tanlang, men uni PDF fayl qilib yuboraman:", inl=ik(rows))


def _send_hist(s, uid, chat):
    rows = q("SELECT * FROM msgs WHERE owner=? AND chat=? ORDER BY ts, mid LIMIT 5000", (uid, chat))
    if not rows: return s.send(uid, "ℹ️ Bu chat bo'yicha tarix topilmadi.")
    nm = next((r["chat_name"] for r in rows if r["chat_name"]), None) or next((r["who"] for r in rows if not r["out"] and r["who"]), None) or str(chat)
    data = pdfgen.build(nm, rows)
    safe = re.sub(r"[^\w\-]+", "_", nm)[:30] or "chat"
    if not s.upload("sendDocument", "document", f"tarix_{safe}.pdf", data, chat_id=uid,
                    caption=f"🕘 {nm} — {len(rows)} ta xabar"):
        s.send(uid, "⚠️ PDF yuborib bo'lmadi. Keyinroq urinib ko'ring.")


@cbq("h")
def cb_hist(s, uid, c, a):
    if not active(uid): return "💎 Tarix uchun obuna kerak."
    try: chat = int(a[0])
    except (IndexError, ValueError): return None
    bg(_send_hist, s, uid, chat)
    return "⏳ PDF tayyorlanmoqda…"
