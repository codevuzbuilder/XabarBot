"""ops.py — admin panel funksiyalari/amallari, tugma bosilganda ishlovchi run_item va foydalanuvchining kichik tugmalari."""
import os, sys, io, csv, time, html, sqlite3
from core import *
from pay import *


# ----------------------------- ADMIN: funksiyalar -----------------------------
def _list(rows, fmt, empty="—"):
    return "\n".join(fmt(r) for r in rows) or empty


def f_last_users(s, uid):
    return "👥 So'nggi 10 user:\n" + _list(q("SELECT * FROM users ORDER BY joined DESC LIMIT 10"),
                                           lambda r: f"• <code>{r['id']}</code> — {time.strftime('%d.%m %H:%M', time.localtime(r['joined']))}")


def f_banned(s, uid):
    return "🚷 Banlanganlar:\n" + _list(q("SELECT id FROM users WHERE banned=1 LIMIT 50"), lambda r: f"• <code>{r['id']}</code>")


def f_partners(s, uid):
    return "🤝 Hamkorlar:\n" + _list(q("SELECT * FROM users WHERE is_partner=1 LIMIT 50"),
                                     lambda r: f"• <code>{r['id']}</code> — {money(r['balance'])} so'm")


def f_clones(s, uid):
    if not s.main: return "❌ Bu amal faqat asosiy botda."
    return "🤖 Klon botlar:\n" + _list(q("SELECT * FROM clones"),
                                       lambda r: f"• @{BOTS[r['token']].username if r['token'] in BOTS else '?'} — hamkor <code>{r['owner']}</code>")


def f_top_partners(s, uid):
    return "🏆 Top hamkorlar:\n" + _list(q("SELECT * FROM users WHERE is_partner=1 ORDER BY balance DESC LIMIT 10"),
                                         lambda r: f"• <code>{r['id']}</code> — {money(r['balance'])} so'm")


def f_pending(s, uid):
    return "📋 Kutilayotgan to'lovlar:\n" + _list(q("SELECT * FROM payments WHERE status='pending' ORDER BY id DESC LIMIT 20"),
                                                 lambda r: f"• #{r['id']} {r['user_id']} — {money(r['amount'])} ({r['method']})"
                                                           + (f"  /ok_{r['id']} /no_{r['id']}" if r['method'] == 'receipt' else ""))


def f_last_payments(s, uid):
    return "🧾 So'nggi 10 to'lov:\n" + _list(q("SELECT * FROM payments ORDER BY id DESC LIMIT 10"),
                                            lambda r: f"• #{r['id']} {r['user_id']} — {money(r['amount'])} [{r['status']}]")


def f_promos(s, uid):
    return "🎁 Promokodlar:\n" + _list(q("SELECT * FROM promos LIMIT 50"),
                                      lambda r: f"• <code>{r['code']}</code> — {r['days']} kun / {money(r['money'])} so'm — {r['used']}/{r['lim']} {'✅' if r['active'] else '⏸'}")


def f_promo_stats(s, uid):
    a, b = q("SELECT COUNT(*) FROM promos", one=True)[0], q("SELECT COUNT(*) FROM promo_uses", one=True)[0]
    return f"📊 Promokodlar: {a} ta\n🎟 Ishlatilgan: {b} marta"


def f_promo_clean(s, uid):
    return f"🧹 {run('DELETE FROM promos WHERE used>=lim')} ta tugagan promokod o'chirildi."


def f_admins(s, uid):
    return "👮 Adminlar:\n• <code>%d</code> (asosiy)\n" % s.admin + _list(q("SELECT id FROM admins"), lambda r: f"• <code>{r['id']}</code>", "")


def f_bot_info(s, uid):
    me = s.call("getMe") or {}
    return (f"🤖 @{me.get('username')}\n🆔 {me.get('id')}\n🏢 Business: {'✅ yoqilgan' if me.get('can_connect_to_business') else '❌ o‘chiq'}\n"
            + (f"\n👥 Klonlar: {len(BOTS) - 1}" if s.main else ""))


def f_biz(s, uid):
    me = s.call("getMe") or {}
    if me.get("can_connect_to_business"):
        return "✅ Business Mode yoqilgan. Ulash: Sozlamalar → Telegram Business → Chatbotlar."
    return ("❌ Business Mode <b>o'chiq</b> — shu sababli «yaroqsiz» deyapti.\n\n"
            "Tuzatish: @BotFather → /mybots → botni tanlang → <b>Bot Settings</b> → <b>Business Mode</b> → <b>Turn on</b>.\n"
            "So'ng akkauntda botni qayta kiriting (@username).")


def f_errors(s, uid):
    if not s.main: return "❌ Bu amal faqat asosiy botda."
    try: return "🧾 Xatolar:\n<pre>" + esc(open("errors.log").read()[-3000:]) + "</pre>"
    except OSError: return "✅ Xatolar yo'q."


def f_restart(s, uid):
    if not s.main: return "❌ Bu amal faqat asosiy botda."
    s.send(uid, "🔁 Qayta ishga tushmoqda…")
    os.execv(sys.executable, [sys.executable] + sys.argv)


def f_ping(s, uid):
    t0 = time.time()
    s.call("getMe")
    return f"🏓 {int((time.time() - t0) * 1000)} ms"


def f_db_size(s, uid): return f"🧮 DB hajmi: {os.path.getsize(D().path) / 1024:.1f} KB"
def f_vacuum(s, uid):
    with D().lock: D().con.execute("VACUUM")
    return "🪄 DB optimallashtirildi."


def f_clear_old(s, uid):
    return f"🧹 {run('DELETE FROM msgs WHERE ts<?', (int(time.time() - num('cache_days') * 86400),))} ta eski xabar o'chirildi."


def f_clear_all(s, uid): return f"🗑 {run('DELETE FROM msgs')} ta xabar o'chirildi."


def f_backup(s, uid):
    s.upload("sendDocument", "document", "bot_backup.db", backup_bytes(), chat_id=uid)


def _csv(s, uid, sql, name, head):
    buf = io.StringIO()
    w = csv.writer(buf); w.writerow(head)
    for r in q(sql): w.writerow(list(r))
    s.upload("sendDocument", "document", name, buf.getvalue().encode(), chat_id=uid)


def f_csv_users(s, uid):
    _csv(s, uid, "SELECT id,partner_id,referrer,sub_until,is_partner,balance,banned,joined FROM users", "users.csv",
         ["id", "partner_id", "referrer", "sub_until", "is_partner", "balance", "banned", "joined"])


def f_csv_pay(s, uid):
    _csv(s, uid, "SELECT id,user_id,kind,amount,status,method,ext_id,ts FROM payments", "payments.csv",
         ["id", "user_id", "kind", "amount", "status", "method", "ext_id", "ts"])


def f_tc_balance(s, uid):
    try: return f"💼 Tezcheck balansi: <b>{esc(tc_balance())}</b>"
    except Exception as e: return f"❌ Hisob API xatosi: {esc(e)}"


def f_tc_test(s, uid):
    miss = [n for n, k in (("Hisob API", "tc_hisob"), ("Kassa API", "tc_key"), ("API manzil", "tc_base")) if not g(k)]
    if miss: return "❌ Sozlanmagan: " + ", ".join(miss)
    try: return f"✅ Ulanish ishlayapti. Balans: {esc(tc_balance())}"
    except Exception as e: return f"❌ Ulanish xatosi: {esc(e)}"


# ----------------------------- ADMIN: amallar (ID/matn qabul qiladiganlar) -----------------------------
def _need_user(a):
    u = U(int(a[0]))
    if not u: raise ValueError
    return u


def op_info(s, a, raw):
    u = _need_user(a)
    n = q("SELECT COUNT(*) FROM conns WHERE user_id=?", (u["id"],), True)[0]
    r = q("SELECT COUNT(*) FROM users WHERE referrer=?", (u["id"],), True)[0]
    return (f"👤 <code>{u['id']}</code>\n💰 Balans: {money(u['balance'])}\n📅 Obuna: {dt(u['sub_until'])}\n"
            f"🤝 Hamkor: {'ha' if u['is_partner'] else 'yo‘q'}\n🚫 Ban: {'ha' if u['banned'] else 'yo‘q'}\n🔗 Akkaunt: {n}\n👥 Referal: {r}")


def op_ban(s, a, raw): u = _need_user(a); run("UPDATE users SET banned=1 WHERE id=?", (u["id"],)); return "🚫 Bloklandi."
def op_unban(s, a, raw): u = _need_user(a); run("UPDATE users SET banned=0 WHERE id=?", (u["id"],)); return "✅ Blokdan chiqarildi."


def op_addays(s, a, raw):
    u, d = _need_user(a), int(a[1])
    run("UPDATE users SET sub_until=? WHERE id=?", (max(int(time.time()), u["sub_until"]) + d * 86400, u["id"]))
    return f"✅ {d} kun qo'shildi."


def op_cancelsub(s, a, raw): u = _need_user(a); run("UPDATE users SET sub_until=0 WHERE id=?", (u["id"],)); return "✅ Obuna bekor qilindi."


def op_addbal(s, a, raw):
    u, x = _need_user(a), float(a[1])
    run("UPDATE users SET balance=balance+? WHERE id=?", (x, u["id"]))
    s.send(u["id"], f"💰 Balansingizga {money(x)} so'm qo'shildi.")
    return "✅ Qo'shildi."


def op_subbal(s, a, raw):
    u, x = _need_user(a), float(a[1])
    run("UPDATE users SET balance=balance-? WHERE id=?", (x, u["id"]))
    return "✅ Ayirildi."


def op_sendmsg(s, a, raw):
    u = _need_user(a)
    s.send(u["id"], html.escape(raw.split(None, 1)[1]))
    return "✅ Yuborildi."


def op_partner_add(s, a, raw):
    u = _need_user(a); run("UPDATE users SET is_partner=1 WHERE id=?", (u["id"],))
    s.send(u["id"], "🎉 Siz hamkor qilindingiz! «🤖 Mening botim» tugmasi orqali o'z botingizni qo'shing."); return "✅ Hamkor qilindi."


def op_partner_del(s, a, raw): u = _need_user(a); run("UPDATE users SET is_partner=0 WHERE id=?", (u["id"],)); return "✅ Hamkorlikdan chiqarildi."


def op_clone_del(s, a, raw):
    if not s.main: return "❌ Bu amal faqat asosiy botda."
    owner, n = int(a[0]), 0
    for c in q("SELECT token FROM clones WHERE owner=?", (owner,)):
        b = BOTS.pop(c["token"], None)
        if b: b.alive = False
        n += 1
    run("DELETE FROM clones WHERE owner=?", (owner,))
    return f"🗑 {n} ta klon o'chirildi."


def op_promo_days(s, a, raw):
    run("INSERT OR REPLACE INTO promos(code,days,money,lim) VALUES(?,?,0,?)", (a[0].upper(), int(a[1]), int(a[2])))
    return f"✅ Promokod <code>{a[0].upper()}</code> yaratildi."


def op_promo_money(s, a, raw):
    run("INSERT OR REPLACE INTO promos(code,days,money,lim) VALUES(?,0,?,?)", (a[0].upper(), float(a[1]), int(a[2])))
    return f"✅ Promokod <code>{a[0].upper()}</code> yaratildi."


def op_promo_del(s, a, raw): return f"🗑 O'chirildi: {run('DELETE FROM promos WHERE code=?', (a[0].upper(),))}"


def op_promo_info(s, a, raw):
    p = q("SELECT * FROM promos WHERE code=?", (a[0].upper(),), True)
    if not p: raise ValueError
    return f"🎁 <code>{p['code']}</code>\n📅 {p['days']} kun\n💵 {money(p['money'])} so'm\n🎟 {p['used']}/{p['lim']}\n{'✅ faol' if p['active'] else '⏸ o‘chiq'}"


def op_promo_toggle(s, a, raw):
    if not run("UPDATE promos SET active=1-active WHERE code=?", (a[0].upper(),)): raise ValueError
    return "🔄 Holat o'zgartirildi."


def op_promo_announce(s, a, raw):
    p = q("SELECT * FROM promos WHERE code=?", (a[0].upper(),), True)
    if not p: raise ValueError
    broadcast(s, s.admin, "all", f"🎁 Yangi promokod: {p['code']}\n«🎁 Promokod» tugmasini bosib kiriting!")
    return "📣 E'lon yuborilmoqda."


def op_promo_users(s, a, raw):
    return "👥 Ishlatganlar:\n" + _list(q("SELECT user_id FROM promo_uses WHERE code=? LIMIT 50", (a[0].upper(),)), lambda r: f"• <code>{r['user_id']}</code>")


def op_admin_add(s, a, raw): run("INSERT OR IGNORE INTO admins VALUES(?)", (int(a[0]),)); return "✅ Admin qo'shildi."
def op_admin_del(s, a, raw): run("DELETE FROM admins WHERE id=?", (int(a[0]),)); return "✅ Admin o'chirildi."


OPS = {k[3:]: v for k, v in globals().items() if k.startswith("op_") and callable(v)}


# ----------------------------- Admin tugmasini bajarish -----------------------------
def btn_style(it):
    if any(e in it[0] for e in "🗑🚫➖🧹"): return "danger"
    return {"set": "primary", "toggle": "success", "op": "primary", "bc": "primary", "sql": "primary", "fn": "primary"}.get(it[1], "primary")


def run_item(s, uid, it):
    label, kind, a = it[0], it[1], it[2]
    if kind == "sql":
        now = int(time.time())
        v = q(a.format(now=now, day=now - now % 86400), one=True)[0]
        s.send(uid, f"{label}: <b>{money(v)}</b>")
    elif kind == "set":
        STATE[uid] = ("set", a, label)
        shown = "••••••" if a in SECRET and g(a) else g(a)
        s.send(uid, f"✏️ {label}\nHozirgi: <code>{esc(shown)}</code>\n\nYangi qiymatni yuboring:", [[("🏠 Menyu", "")]])
    elif kind == "toggle":
        v = "0" if g(a) == "1" else "1"
        setv(a, v)
        s.send(uid, f"{label}: {'✅ yoqildi' if v == '1' else '❌ o‘chirildi'}")
    elif kind == "fn":
        out = a(s, uid)
        if out: s.send(uid, out)
    elif kind == "op":
        STATE[uid] = ("op", a, label, it[3])
        s.send(uid, f"{label}\n{it[3]}")
    elif kind == "bc":
        STATE[uid] = ("bc", a)
        s.send(uid, f"{label}\nYuboriladigan matnni yozing:")


# ----------------------------- Foydalanuvchining kichik tugmalari -----------------------------
def _toggle(col, label):
    def f(s, uid, m):
        u = U(uid)
        v = 0 if u[col] else 1
        run(f"UPDATE users SET {col}=? WHERE id=?", (v, uid))
        s.send(uid, f"{label}: {'✅ yoqildi' if v else '❌ o‘chirildi'}", main_rows(uid))
    return f


ROUTES["🔔 O'chirilganlar"] = _toggle("n_del", "🔔 O'chirilgan xabarlar")
ROUTES["✏️ Tahrirlanganlar"] = _toggle("n_edit", "✏️ Tahrirlangan xabarlar")


@route("📊 Statistikam")
def r_stats(s, uid, m):
    n = q("SELECT COUNT(*) c FROM msgs WHERE owner=?", (uid,), True)["c"]
    c = q("SELECT COUNT(*) c FROM conns WHERE user_id=?", (uid,), True)["c"]
    s.send(uid, f"📊 Keshdagi xabarlar: {n}\n🔗 Ulangan akkaunt: {c}\n📅 Obuna: {dt(U(uid)['sub_until'])}", main_rows(uid))


@route("🗑 Keshni tozalash")
def r_clear(s, uid, m):
    n = run("DELETE FROM msgs WHERE owner=?", (uid,))
    s.send(uid, f"🗑 {n} ta xabar keshdan o'chirildi.", main_rows(uid))


for _lab, _key in (("📖 Qo'llanma", "guide_text"), ("❓ Savol-javob", "faq_text"),
                   ("🆘 Yordam", "support_text"), ("📜 Shartlar", "terms_text")):
    ROUTES[_lab] = (lambda key: lambda s, uid, m: s.send(uid, g(key), main_rows(uid)))(_key)
