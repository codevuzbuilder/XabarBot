"""core.py — sozlamalar, baza, yordamchilar, Tezcheck to'lov, umumiy funksiyalar."""
import os, re, sys, io, csv, time, json, hmac, hashlib, sqlite3, threading, traceback, html
import requests



def _load_env(path=".env"):
    """.env faylidan KEY=VALUE qatorlarini o'qiydi (token GitHub'ga tushmasligi uchun)."""
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


_load_env()
TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
DB_FILE = os.getenv("DB_FILE", "bot.db")
if not TOKEN or not ADMIN_ID:
    sys.exit("❌ BOT_TOKEN va ADMIN_ID topilmadi. .env fayl yarating (namuna: .env.example) "
             "yoki muhit o'zgaruvchilarini kiriting.")

# ======================= TEZCHECK (hujjatga moslang) =======================
# Hisob API (balans) va Kassa API (schot yaratish / holat) manzillari.
# Tezcheck hujjatidagi haqiqiy yo'llar bilan almashtiring.
TC_PATHS = {
    "balance": ("GET", "/account/balance"),         # hisob API
    "create": ("POST", "/cashbox/invoice"),         # kassa API: schot yaratish
    "status": ("GET", "/cashbox/invoice/{id}"),     # kassa API: schot holati
}
# ===========================================================================

lock = threading.RLock()
con = sqlite3.connect(DB_FILE, check_same_thread=False)
con.row_factory = sqlite3.Row
con.executescript("""
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, partner_id INTEGER, referrer INTEGER, sub_until INTEGER DEFAULT 0,
  is_partner INTEGER DEFAULT 0, balance REAL DEFAULT 0, banned INTEGER DEFAULT 0, n_del INTEGER DEFAULT 1,
  n_edit INTEGER DEFAULT 1, joined INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS conns(id TEXT PRIMARY KEY, user_id INTEGER);
CREATE TABLE IF NOT EXISTS msgs(cid TEXT, chat INTEGER, mid INTEGER, owner INTEGER, who TEXT, kind TEXT, text TEXT,
  fid TEXT, ts INTEGER, PRIMARY KEY(cid,chat,mid));
CREATE TABLE IF NOT EXISTS clones(token TEXT PRIMARY KEY, owner INTEGER);
CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, kind TEXT, amount REAL,
  status TEXT DEFAULT 'pending', via TEXT, method TEXT, ext_id TEXT, url TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS promos(code TEXT PRIMARY KEY, days INTEGER DEFAULT 0, money REAL DEFAULT 0, lim INTEGER DEFAULT 1,
  used INTEGER DEFAULT 0, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS promo_uses(code TEXT, user_id INTEGER, PRIMARY KEY(code,user_id));
CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY);
""")

# eski bot.db bilan moslik: yetishmayotgan ustunlarni avtomatik qo'shadi
MIGRATE = {
    "users": {"partner_id": "INTEGER", "referrer": "INTEGER", "sub_until": "INTEGER DEFAULT 0",
              "is_partner": "INTEGER DEFAULT 0", "balance": "REAL DEFAULT 0", "banned": "INTEGER DEFAULT 0",
              "n_del": "INTEGER DEFAULT 1", "n_edit": "INTEGER DEFAULT 1", "joined": "INTEGER DEFAULT 0"},
    "msgs": {"ts": "INTEGER DEFAULT 0"},
    "payments": {"user_id": "INTEGER", "kind": "TEXT", "amount": "REAL", "status": "TEXT DEFAULT 'pending'",
                 "via": "TEXT", "method": "TEXT", "ext_id": "TEXT", "url": "TEXT", "ts": "INTEGER DEFAULT 0"},
}
for _t, _cols in MIGRATE.items():
    _have = {r["name"] for r in con.execute(f"PRAGMA table_info({_t})")}
    for _c, _def in _cols.items():
        if _c not in _have: con.execute(f"ALTER TABLE {_t} ADD COLUMN {_c} {_def}")
con.commit()

DEF = {
    "price_7": "7000", "price_30": "20000", "price_90": "50000", "price_365": "180000",
    "partner_price": "100000", "commission": "30", "ref_percent": "10", "topup_bonus": "0",
    "min_topup": "5000", "max_topup": "5000000", "trial_days": "1", "cache_days": "7",
    "tc_base": "https://tezcheck.uz/api", "tc_key": "", "tc_secret": "", "tc_kassa": "", "tc_ttl": "30",
    "pay_info": "Karta: 0000 0000 0000 0000 (Ism Familiya)",
    "autopay": "1", "manual_pay": "1", "bot_on": "1", "reg_on": "1", "trial_on": "1",
    "notify_deleted": "1", "notify_edited": "1", "save_media": "1", "partner_on": "1", "ref_on": "1",
    "promo_on": "1", "notify_admin_new": "1", "req_channel": "", "log_chat": "",
    "welcome_text": "👋 Salom! Men chatlaringizdagi o'chirilgan va tahrirlangan xabarlarni (media bilan) sizga yetkazaman.\n\n"
                    "Boshlash uchun «📲 Botni ulash» tugmasini bosing.",
    "guide_text": "📖 <b>Qo'llanma</b>\n1) «📲 Botni ulash» dagi ko'rsatma bo'yicha akkauntni ulang.\n"
                  "2) «💳 Balans to'ldirish» va «💎 Obuna olish» orqali obuna oling.\n"
                  "3) Suhbatdosh xabarni o'chirsa yoki tahrirlasa, sizga shu yerda keladi.",
    "faq_text": "❓ <b>Savol-javob</b>\n• Bot qanday ishlaydi? — Telegram Business orqali ulangan chatlarni kuzatadi.\n"
                "• Premium kerakmi? — Ha, Telegram Business uchun Premium kerak.\n"
                "• Ma'lumotlar saqlanadimi? — Vaqtincha kesh, «🗑 Keshni tozalash» bilan o'chirasiz.",
    "terms_text": "📜 <b>Shartlar</b>\nBotdan faqat o'z suhbatlaringizda va qonunga muvofiq foydalaning. "
                  "Boshqalarning shaxsiy ma'lumotlarini tarqatish taqiqlanadi.",
    "support_text": "🆘 Yordam uchun adminga yozing.",
    "partner_text": "🤝 <b>Hamkorlik</b>\nHamkor bo'ling: o'z botingizni oling, foydalanuvchilaringiz xarididan ulush oling.",
}
NUM = {"price_7", "price_30", "price_90", "price_365", "partner_price", "commission", "ref_percent", "topup_bonus",
       "min_topup", "max_topup", "trial_days", "cache_days", "tc_ttl"}
for _k, _v in DEF.items():
    con.execute("INSERT OR IGNORE INTO settings VALUES(?,?)", (_k, _v))
con.commit()

BOTS, STATE, ROUTES = {}, {}, {}


# ----------------------------- yordamchilar -----------------------------
def q(sql, a=(), one=False):
    with lock:
        cur = con.execute(sql, a)
        con.commit()
        return cur.fetchone() if one else cur.fetchall()


def run(sql, a=()):
    with lock:
        cur = con.execute(sql, a)
        con.commit()
        return cur.rowcount


def ins(sql, a):
    with lock:
        cur = con.execute(sql, a)
        con.commit()
        return cur.lastrowid


def g(k): return q("SELECT v FROM settings WHERE k=?", (k,), True)["v"]
def setv(k, v): run("UPDATE settings SET v=? WHERE k=?", (v, k))
def num(k):
    try: return float(g(k))
    except ValueError: return 0.0


def esc(x): return html.escape(str(x if x not in (None, "") else "—"))
def money(x): return f"{int(round(float(x))):,}".replace(",", " ")
def dt(ts): return time.strftime("%d.%m.%Y %H:%M", time.localtime(ts)) if ts > time.time() else "tugagan"
def U(uid): return q("SELECT * FROM users WHERE id=?", (uid,), True)
def is_admin(uid): return uid == ADMIN_ID or bool(q("SELECT 1 FROM admins WHERE id=?", (uid,), True))
def main_bot(): return BOTS[TOKEN]


def active(uid):
    if is_admin(uid): return True
    u = U(uid)
    return bool(u and u["sub_until"] > time.time())


def elog():
    err = traceback.format_exc()
    print(err)
    with open("errors.log", "a") as f:
        f.write(time.strftime("[%d.%m.%Y %H:%M:%S]\n") + err + "\n")


def notify(uid, via, text):
    (BOTS.get(via) or main_bot()).send(uid, text)


def log(text):
    c = g("log_chat")
    if c: main_bot().send(c, text)


def kb(rows):
    out = []
    for r in rows:
        line = []
        for b in r:
            t, st = (b, "") if isinstance(b, str) else b
            line.append({"text": t, **({"style": st} if st else {})})
        out.append(line)
    return {"keyboard": out, "resize_keyboard": True}


def main_rows(uid):
    rows = [
        [("📲 Botni ulash", "primary"), ("💎 Obuna olish", "success")],
        [("💳 Balans to'ldirish", "success"), "💰 Balansim"],
        ["📅 Obunam", "🧾 To'lovlarim"],
        [("🎁 Promokod", "primary"), ("🔗 Referal", "primary")],
        [("🤝 Hamkorlik", "success"), ("🤖 Mening botim", "primary")],
        ["🔔 O'chirilganlar", "✏️ Tahrirlanganlar"],
        ["📊 Statistikam", ("🗑 Keshni tozalash", "danger")],
        ["📖 Qo'llanma", "❓ Savol-javob"],
        ["🆘 Yordam", "📜 Shartlar"],
    ]
    if is_admin(uid): rows.append([("⚙️ Admin panel", "danger")])
    return rows


def route(label):
    def d(f):
        ROUTES[label] = f
        return f
    return d


# ----------------------------- Tezcheck -----------------------------
def _pick(d, keys):
    if isinstance(d, dict):
        for k in keys:
            if d.get(k) not in (None, ""): return d[k]


def tc_call(name, payload=None, **fmt):
    meth, path = TC_PATHS[name]
    body = json.dumps(payload, separators=(",", ":")) if payload is not None else ""
    h = {"Content-Type": "application/json", "Accept": "application/json", "Authorization": "Bearer " + g("tc_key")}
    if g("tc_secret"):
        h["X-Signature"] = hmac.new(g("tc_secret").encode(), body.encode(), hashlib.sha256).hexdigest()
    r = requests.request(meth, g("tc_base").rstrip("/") + path.format(**fmt), data=body or None, headers=h, timeout=30)
    try: j = r.json()
    except ValueError: raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    if r.status_code >= 400: raise RuntimeError(f"HTTP {r.status_code}: {str(j)[:200]}")
    if not isinstance(j, dict): return {"value": j}
    for k in ("data", "result"):
        if isinstance(j.get(k), dict): return j[k]
    return j


def tc_create(pid, amount):
    j = tc_call("create", {"kassa_id": g("tc_kassa"), "amount": int(amount), "order_id": str(pid),
                           "description": "Balans to'ldirish"})
    url = _pick(j, ("pay_url", "payment_url", "checkout_url", "url", "link"))
    if not url: raise RuntimeError("to'lov havolasi kelmadi: " + str(j)[:200])
    return str(_pick(j, ("id", "invoice_id", "transaction_id", "order_id")) or pid), url


def tc_state(p):
    j = tc_call("status", id=p["ext_id"])
    st = str(_pick(j, ("status", "state")) or "").lower()
    if st in ("paid", "success", "succeeded", "completed", "done", "approved") or j.get("paid") is True: return "paid"
    if st in ("expired", "canceled", "cancelled", "failed", "rejected"): return "failed"
    return "pending"


def tc_balance():
    j = tc_call("balance")
    return _pick(j, ("balance", "amount", "available", "value")) or j


def credit(pid):
    if not run("UPDATE payments SET status='approved' WHERE id=? AND status='pending'", (pid,)): return False
    p = q("SELECT * FROM payments WHERE id=?", (pid,), True)
    add = p["amount"] * (1 + num("topup_bonus") / 100)
    run("UPDATE users SET balance=balance+? WHERE id=?", (add, p["user_id"]))
    notify(p["user_id"], p["via"], f"✅ Hisobingiz <b>{money(add)}</b> so'mga to'ldirildi!")
    log(f"💵 To'lov #{pid}: {p['user_id']} — {money(p['amount'])} so'm ({p['method']})")
    return True


def check_payment(p):
    st = tc_state(p)
    if st == "paid": credit(p["id"])
    elif st == "failed" or time.time() - p["ts"] > num("tc_ttl") * 60:
        if run("UPDATE payments SET status='expired' WHERE id=? AND status='pending'", (p["id"],)):
            notify(p["user_id"], p["via"], f"⌛ To'lov #{p['id']} muddati tugadi yoki bekor qilindi.")


def poller():
    while True:
        time.sleep(15)
        try:
            if g("autopay") != "1" or not g("tc_key"): continue
            for p in q("SELECT * FROM payments WHERE status='pending' AND method='tc'"):
                try: check_payment(p)
                except Exception: elog()
        except Exception: elog()


def backup_to_admin():
    """Bazaning zaxira nusxasini adminga yuboradi (GitHub Actions kabi vaqtinchalik muhit uchun)."""
    dst = sqlite3.connect("backup_tmp.db")
    with lock: con.backup(dst)
    dst.close()
    with open("backup_tmp.db", "rb") as f: data = f.read()
    os.remove("backup_tmp.db")
    main_bot().upload("sendDocument", "document", "bot_backup.db", data, chat_id=ADMIN_ID,
                      caption=time.strftime("💾 Zaxira %d.%m.%Y %H:%M"), disable_notification="true")


def cleaner():
    hours = 0
    while True:
        try:
            run("DELETE FROM msgs WHERE ts<?", (int(time.time() - num("cache_days") * 86400),))
            n = int(os.getenv("BACKUP_HOURS", "0") or 0)     # 0 = o'chiq
            if n and hours and hours % n == 0: backup_to_admin()
        except Exception: elog()
        hours += 1
        time.sleep(3600)


# ----------------------------- Umumiy funksiyalar -----------------------------
def gate(s, uid):
    ch = g("req_channel")
    if not ch or is_admin(uid): return True
    r = s.call("getChatMember", chat_id=ch, user_id=uid)
    if r is None: return True
    return r.get("status") in ("member", "administrator", "creator", "restricted")


def reg(uid, partner=None, ref=None):
    if U(uid): return False
    if g("reg_on") != "1" and not is_admin(uid): return None
    trial = int(num("trial_days") * 86400) if g("trial_on") == "1" else 0
    r = ref if (ref and ref != uid and g("ref_on") == "1" and U(ref)) else None
    run("INSERT INTO users(id,partner_id,referrer,sub_until,joined) VALUES(?,?,?,?,?)",
        (uid, partner, r, int(time.time()) + trial, int(time.time())))
    return True


def shares(u, price):
    if u["referrer"] and g("ref_on") == "1":
        x = price * num("ref_percent") / 100
        if x > 0:
            run("UPDATE users SET balance=balance+? WHERE id=?", (x, u["referrer"]))
            notify(u["referrer"], TOKEN, f"🎉 Referalingiz xaridi uchun +{money(x)} so'm balansingizga tushdi.")
    if u["partner_id"] and g("partner_on") == "1":
        x = price * num("commission") / 100
        if x > 0:
            run("UPDATE users SET balance=balance+? WHERE id=?", (x, u["partner_id"]))
            notify(u["partner_id"], TOKEN, f"🤝 Botingiz xaridi uchun +{money(x)} so'm balansingizga tushdi.")


def redeem(uid, code):
    if g("promo_on") != "1": return "🎁 Promokodlar hozircha o'chirilgan."
    p = q("SELECT * FROM promos WHERE code=?", (code,), True)
    if not p or not p["active"] or p["used"] >= p["lim"]: return "❌ Promokod topilmadi yoki tugagan."
    if not run("INSERT OR IGNORE INTO promo_uses VALUES(?,?)", (code, uid)): return "ℹ️ Bu promokodni allaqachon ishlatgansiz."
    run("UPDATE promos SET used=used+1 WHERE code=?", (code,))
    if p["days"]:
        u = U(uid)
        run("UPDATE users SET sub_until=? WHERE id=?", (max(int(time.time()), u["sub_until"]) + p["days"] * 86400, uid))
    if p["money"]: run("UPDATE users SET balance=balance+? WHERE id=?", (p["money"], uid))
    got = []
    if p["days"]: got.append(f"{p['days']} kun obuna")
    if p["money"]: got.append(f"{money(p['money'])} so'm")
    return "🎉 Promokod faollashdi: " + " + ".join(got)


def broadcast(s, uid, group, text):
    now = int(time.time())
    cond = {"all": "1=1", "active": f"sub_until>{now}", "expired": f"sub_until<={now}", "partners": "is_partner=1"}[group]
    ids = [r["id"] for r in q(f"SELECT id FROM users WHERE banned=0 AND {cond}")]

    def work():
        n = 0
        for i in ids:
            if s.call("sendMessage", chat_id=i, text=text[:4000]): n += 1
            time.sleep(0.05)
        s.send(uid, f"📢 Yuborildi: {n}/{len(ids)}")
    threading.Thread(target=work, daemon=True).start()
    s.send(uid, f"📢 Yuborish boshlandi ({len(ids)} ta).")
