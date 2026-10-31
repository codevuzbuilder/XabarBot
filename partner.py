"""partner.py — hamkor paneli: faqat o'z foydalanuvchilari uchun (statistika, xabar, matnlar, blok, kun, promokod)."""
import re, time, threading
from core import *


def _is_partner(uid):
    u = U(uid)
    return bool(u and u["is_partner"])


def day_cost(days):
    """Hamkor uchun narx: 1 kun = (30 kunlik narx / 30). Admin narxlaridan olinadi."""
    return num("price_30") / 30 * days


def _own(uid, a):
    t = U(int(a[0]))
    if not t or t["partner_id"] != uid: raise ValueError
    return t


def _current(uid, key):
    r = q("SELECT v FROM pset WHERE partner=? AND k=?", (uid, key), True)
    return r["v"] if r and r["v"] else g(key)


def _spend(uid, cost):
    return run("UPDATE users SET balance=balance-? WHERE id=? AND balance>=?", (cost, uid, cost))


# ----------------------------- ma'lumot funksiyalari -----------------------------
def p_stats(s, uid):
    now = int(time.time())
    n = lambda sql, *a: q(sql, a, True)[0]
    sales = q("SELECT COUNT(*), COALESCE(SUM(price),0) FROM pearn WHERE partner=?", (uid,), True)
    return (f"📈 <b>Hamkor statistikasi</b>\n👥 Foydalanuvchilar: {n('SELECT COUNT(*) FROM users WHERE partner_id=?', uid)}\n"
            f"💎 Faol obuna: {n('SELECT COUNT(*) FROM users WHERE partner_id=? AND sub_until>?', uid, now)}\n"
            f"🆕 Bugun qo'shilgan: {n('SELECT COUNT(*) FROM users WHERE partner_id=? AND joined>=?', uid, now - now % 86400)}\n"
            f"🤖 Botlaringiz: {n('SELECT COUNT(*) FROM clones WHERE owner=?', uid)}\n"
            f"🛒 Xaridlar: {sales[0]} ta ({money(sales[1])} so'm)")


def p_income(s, uid):
    tot = q("SELECT COALESCE(SUM(share),0) FROM pearn WHERE partner=?", (uid,), True)[0]
    last = q("SELECT * FROM pearn WHERE partner=? ORDER BY ts DESC LIMIT 5", (uid,))
    lines = "\n".join(f"• {time.strftime('%d.%m %H:%M', time.localtime(r['ts']))} — {r['user_id']}: +{money(r['share'])}"
                      for r in last) or "—"
    return (f"💼 Balans: <b>{money(U(uid)['balance'])}</b> so'm\n📈 Jami daromad: {money(tot)} so'm "
            f"({g('commission')}% ulush)\n\n{lines}")


def p_users(s, uid):
    rows = q("SELECT * FROM users WHERE partner_id=? ORDER BY joined DESC LIMIT 10", (uid,))
    now = time.time()
    return "👥 So'nggi 10 foydalanuvchi:\n" + ("\n".join(
        f"• <code>{r['id']}</code> {'💎' if r['sub_until'] > now else '—'}" for r in rows) or "—")


def p_promos(s, uid):
    rows = q("SELECT * FROM promos WHERE owner=?", (uid,))
    return "📋 Promokodlaringiz:\n" + ("\n".join(
        f"• <code>{r['code']}</code> — {r['days']} kun — {r['used']}/{r['lim']}" for r in rows) or "—")


# ----------------------------- amallar (ID/matn qabul qiladiganlar) -----------------------------
def pop_pban(s, uid, a, raw):
    t = _own(uid, a)
    run("INSERT OR IGNORE INTO pbans VALUES(?,?)", (uid, t["id"]))
    return "🚫 Bloklandi (faqat sizning botlaringizda)."


def pop_punban(s, uid, a, raw):
    t = _own(uid, a)
    run("DELETE FROM pbans WHERE partner=? AND user_id=?", (uid, t["id"]))
    return "✅ Blokdan chiqarildi."


def pop_pgive(s, uid, a, raw):
    t, d = _own(uid, a), int(a[1])
    if not 1 <= d <= 365: raise ValueError
    cost = day_cost(d)
    if not _spend(uid, cost): return f"❌ Balans yetarli emas. Kerak: {money(cost)} so'm."
    run("UPDATE users SET sub_until=? WHERE id=?", (max(int(time.time()), t["sub_until"]) + d * 86400, t["id"]))
    notify(t["id"], t["via"], f"🎁 Sizga {d} kun obuna sovg'a qilindi!")
    return f"✅ {d} kun berildi. Balansdan yechildi: {money(cost)} so'm."


def pop_pcreate(s, uid, a, raw):
    code, d, lim = a[0].upper(), int(a[1]), int(a[2])
    if not (re.fullmatch(r"[A-Z0-9]{3,20}", code) and 1 <= d <= 365 and 1 <= lim <= 1000): raise ValueError
    if q("SELECT 1 FROM promos WHERE code=?", (code,), True): return "❌ Bu kod band, boshqasini tanlang."
    cost = day_cost(d) * lim
    if not _spend(uid, cost): return f"❌ Balans yetarli emas. Kerak: {money(cost)} so'm ({d} kun × {lim} ta)."
    run("INSERT INTO promos(code,days,money,lim,owner) VALUES(?,?,0,?,?)", (code, d, lim, uid))
    return f"✅ Promokod <code>{code}</code>: {d} kun × {lim} ta. Balansdan yechildi: {money(cost)} so'm."


def pop_pdel(s, uid, a, raw):
    p = q("SELECT * FROM promos WHERE code=? AND owner=?", (a[0].upper(), uid), True)
    if not p: raise ValueError
    back = day_cost(p["days"]) * max(0, p["lim"] - p["used"])
    run("DELETE FROM promos WHERE code=?", (p["code"],))
    run("UPDATE users SET balance=balance+? WHERE id=?", (back, uid))
    return f"🗑 O'chirildi. Ishlatilmagan qism qaytarildi: {money(back)} so'm."


POPS = {k[4:]: v for k, v in globals().items() if k.startswith("pop_") and callable(v)}


def p_broadcast(s, uid, text):
    rows = q("SELECT id, via FROM users WHERE partner_id=? AND banned=0 AND id NOT IN "
             "(SELECT user_id FROM pbans WHERE partner=?)", (uid, uid))

    def work():
        n = 0
        for r in rows:
            b = BOTS.get(r["via"])
            if b and b.call("sendMessage", chat_id=r["id"], text=text[:4000]): n += 1
            time.sleep(0.05)
        s.send(uid, f"📣 Yuborildi: {n}/{len(rows)}")
    threading.Thread(target=work, daemon=True).start()
    return f"📣 Yuborish boshlandi ({len(rows)} ta foydalanuvchi)."


def partner_state(s, uid, st, m):
    """bot.py dagi state() shu funksiyani chaqiradi; javob matnini qaytaradi."""
    t, k = (m.get("text") or "").strip(), st[0]
    if not _is_partner(uid):
        STATE.pop(uid, None)
        return None
    if k == "pset":
        run("INSERT OR REPLACE INTO pset VALUES(?,?,?)", (uid, st[1], t[:1000]))
        STATE.pop(uid, None)
        return f"✅ {st[2]} yangilandi."
    if k == "pop":
        try: out = POPS[st[1]](s, uid, t.split(), t)
        except (ValueError, IndexError): return f"❌ Format noto'g'ri.\n{st[3]}"
        STATE.pop(uid, None)
        return out
    if k == "pbc":
        STATE.pop(uid, None)
        return p_broadcast(s, uid, t)


# ----------------------------- panel tugmalari (12 ta) -----------------------------
PANEL = [
    ("📈 Hamkor statistikasi", "fn", p_stats), ("💼 Daromadim", "fn", p_income),
    ("👥 Mening userlarim", "fn", p_users), ("📣 Userlarimga xabar", "bc"),
    ("👋 Bot salomlashuvi", "set", "welcome_text"), ("🆘 Bot yordam matni", "set", "support_text"),
    ("🚫 Userni bloklash", "op", "pban", "ID yuboring. Masalan: 123456789"),
    ("✅ Blokdan olish", "op", "punban", "ID yuboring."),
    ("🎁 Userga kun berish", "op", "pgive", "ID va kun: 123456789 7\n(narx balansingizdan yechiladi)"),
    ("🎟 Promokod yaratish", "op", "pcreate", "KOD KUN LIMIT: MENIKI7 7 20\n(narx balansingizdan oldindan yechiladi)"),
    ("📋 Promokodlarim", "fn", p_promos), ("🗑 Promokodimni o'chirish", "op", "pdel", "KOD yuboring."),
]


def _style(it):
    if any(e in it[0] for e in "🚫🗑"): return "danger"
    return "success" if any(e in it[0] for e in "✅🎁🎟") else "primary"


def panel_rows():
    rows = [[(it[0], _style(it)) for it in PANEL[i:i + 2]] for i in range(0, len(PANEL), 2)]
    rows.append([("🏠 Menyu", "")])
    return rows


def _mk(it):
    def f(s, uid, m):
        if not _is_partner(uid): return
        kind = it[1]
        if kind == "fn": s.send(uid, it[2](s, uid))
        elif kind == "set":
            STATE[uid] = ("pset", it[2], it[0])
            s.send(uid, f"✏️ {it[0]}\nHozirgi: {esc(_current(uid, it[2]))}\n\nYangi matnni yuboring:")
        elif kind == "op":
            STATE[uid] = ("pop", it[2], it[0], it[3])
            s.send(uid, f"{it[0]}\n{it[3]}")
        elif kind == "bc":
            STATE[uid] = ("pbc",)
            s.send(uid, f"{it[0]}\nFaqat o'z foydalanuvchilaringizga yuboriladigan matnni yozing:")
    return f


@route("🛠 Hamkor paneli")
def r_panel(s, uid, m):
    if _is_partner(uid):
        s.send(uid, "🛠 <b>Hamkor paneli</b> — faqat o'z foydalanuvchilaringiz uchun:", panel_rows())


for _it in PANEL:
    assert _it[0] not in ROUTES, "takroriy tugma nomi: " + _it[0]
    ROUTES[_it[0]] = _mk(_it)
