"""core.py — sozlamalar, har bir bot uchun ALOHIDA baza, yordamchilar, tugma dizayni, majburiy kanallar."""
import os, re, sys, io, csv, time, json, sqlite3, threading, traceback, html
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
try:                                   # vaqt O'zbekiston bo'yicha (TZ o'zgaruvchisi bilan almashtirish mumkin)
    os.environ.setdefault("TZ", "Asia/Tashkent")
    time.tzset()
except Exception:
    pass

TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
DB_FILE = os.getenv("DB_FILE", "bot.db")
if not TOKEN or not ADMIN_ID:
    sys.exit("❌ BOT_TOKEN va ADMIN_ID topilmadi. .env fayl yarating (namuna: _env.example) "
             "yoki muhit o'zgaruvchilarini kiriting.")

CLONE_DIR = os.path.join(os.path.dirname(os.path.abspath(DB_FILE)), "clones")
os.makedirs(CLONE_DIR, exist_ok=True)


def clone_path(token): return os.path.join(CLONE_DIR, token.split(":")[0] + ".db")


SCHEMA = """
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
CREATE TABLE IF NOT EXISTS channels(id TEXT PRIMARY KEY, title TEXT, link TEXT);
CREATE TABLE IF NOT EXISTS btns(key TEXT PRIMARY KEY, label TEXT, style TEXT, emoji TEXT);
"""

# eski bot.db bilan moslik: yetishmayotgan ustunlarni avtomatik qo'shadi
MIGRATE = {
    "users": {"partner_id": "INTEGER", "referrer": "INTEGER", "sub_until": "INTEGER DEFAULT 0",
              "is_partner": "INTEGER DEFAULT 0", "balance": "REAL DEFAULT 0", "banned": "INTEGER DEFAULT 0",
              "n_del": "INTEGER DEFAULT 1", "n_edit": "INTEGER DEFAULT 1", "joined": "INTEGER DEFAULT 0"},
    "msgs": {"ts": "INTEGER DEFAULT 0", "out": "INTEGER DEFAULT 0", "chat_name": "TEXT",
             "deleted": "INTEGER DEFAULT 0", "old": "TEXT"},
    "payments": {"user_id": "INTEGER", "kind": "TEXT", "amount": "REAL", "status": "TEXT DEFAULT 'pending'",
                 "via": "TEXT", "method": "TEXT", "ext_id": "TEXT", "url": "TEXT", "ts": "INTEGER DEFAULT 0"},
}

DEF = {
    "price_7": "7000", "price_30": "20000", "price_90": "50000", "price_365": "180000",
    "partner_price": "100000", "ref_percent": "10", "topup_bonus": "0",
    "min_topup": "5000", "max_topup": "5000000", "trial_days": "1", "cache_days": "30",
    # Tezcheck: Hisob API (balans) va Kassa API (schot) alohida kalitlar
    "tc_base": "https://tezcheck.uz/api", "tc_hisob": "", "tc_key": "", "tc_secret": "", "tc_kassa": "", "tc_ttl": "30",
    "tc_p_balance": "/account/balance", "tc_p_create": "/cashbox/invoice", "tc_p_status": "/cashbox/invoice/{id}",
    # Click (BotFather -> Payments -> Click provider tokeni)
    "click_token": "", "click_on": "0",
    "pay_info": "Karta: 0000 0000 0000 0000 (Ism Familiya)",
    "autopay": "0", "manual_pay": "1", "bot_on": "1", "reg_on": "1", "trial_on": "1",
    "notify_deleted": "1", "notify_edited": "1", "save_media": "1", "save_once": "1", "partner_on": "1", "ref_on": "1",
    "promo_on": "1", "notify_admin_new": "1", "req_channel": "", "log_chat": "",
    "welcome_text": "👋 Salom! Men chatlaringizdagi o'chirilgan va tahrirlangan xabarlarni (media bilan) sizga yetkazaman.\n\n"
                    "Boshlash uchun «📲 Botni ulash» tugmasini bosing.",
    "guide_text": "📖 <b>Qo'llanma</b>\n1) «📲 Botni ulash» tugmasi orqali akkauntni ulang (Telegram Business → Chatbotlar).\n"
                  "2) «💳 Balans to'ldirish» va «💎 Obuna olish» orqali obuna oling.\n"
                  "3) Suhbatdosh xabarni o'chirsa yoki tahrirlasa, sizga shu yerda keladi.\n"
                  "4) 👁 O'chib ketuvchi rasm/video/ovozni saqlash: unga <b>javob (reply)</b> qilib istalgan so'z yozing — bot uni sizga yuboradi.\n"
                  "5) «🕘 Tarixim» — tanlangan shaxsiy chat tarixini PDF qilib beradi.",
    "faq_text": "❓ <b>Savol-javob</b>\n• Bot qanday ishlaydi? — Telegram Business orqali ulangan chatlarni kuzatadi.\n"
                "• Premium kerakmi? — Ha, Telegram Business uchun Premium kerak.\n"
                "• Ma'lumotlar saqlanadimi? — Vaqtincha kesh, «🗑 Keshni tozalash» bilan o'chirasiz.",
    "terms_text": "📜 <b>Shartlar</b>\nBotdan faqat o'z suhbatlaringizda va qonunga muvofiq foydalaning. "
                  "Boshqalarning shaxsiy ma'lumotlarini tarqatish taqiqlanadi.",
    "support_text": "🆘 Yordam uchun adminga yozing.",
    "partner_text": "🤝 <b>Hamkorlik</b>\nHamkor bo'ling: o'z botingizni oling va uni <b>to'liq o'zingiz boshqaring</b> — "
                    "o'z narxlaringiz, o'z to'lov tizimingiz, o'z foydalanuvchilaringiz, o'z admin panelingiz!",
}
NUM = {"price_7", "price_30", "price_90", "price_365", "partner_price", "ref_percent", "topup_bonus",
       "min_topup", "max_topup", "trial_days", "cache_days", "tc_ttl"}
SECRET = {"tc_key", "tc_hisob", "tc_secret", "click_token"}   # ko'rsatilmaydi, yuborilgach xabar o'chiriladi


class DB:
    """Har bir bot (asosiy va har bir klon) uchun alohida SQLite fayl."""
    def __init__(s, path):
        s.path = path
        s.lock = threading.RLock()
        s.con = sqlite3.connect(path, check_same_thread=False)
        s.con.row_factory = sqlite3.Row
        s.con.executescript(SCHEMA)
        for t, cols in MIGRATE.items():
            have = {r["name"] for r in s.con.execute(f"PRAGMA table_info({t})")}
            for c, d in cols.items():
                if c not in have: s.con.execute(f"ALTER TABLE {t} ADD COLUMN {c} {d}")
        for k, v in DEF.items():
            s.con.execute("INSERT OR IGNORE INTO settings VALUES(?,?)", (k, v))
        old = s.con.execute("SELECT v FROM settings WHERE k='req_channel'").fetchone()
        if old and old[0] and not s.con.execute("SELECT 1 FROM channels").fetchone():     # eski bitta kanalni ko'chirish
            ch = old[0].strip()
            s.con.execute("INSERT OR IGNORE INTO channels VALUES(?,?,?)",
                          (ch, ch, "https://t.me/" + ch.lstrip("@") if ch.startswith("@") else ""))
        s.con.commit()
        s.btn = None      # tugma dizayni keshi
        s.rev = None      # tugma matni -> kalit keshi


def open_db(path): return DB(path)


TL = threading.local()                 # TL.bot — shu oqim qaysi botga xizmat qilayotgani
BOTS, ROUTES, SH, CB = {}, {}, {}, {}  # botlar, tugma yo'llari, holat ishlovchilari, callback ishlovchilari
ADMIN_KEYS, MAIN_ONLY = set(), set()   # admin tugmalari, faqat asosiy botda ko'rinadigan tugmalar
_ST = {}


def cur(): return TL.bot
def D(): return TL.bot.db
def main_bot(): return BOTS[TOKEN]


class ctx:
    """with ctx(bot): — vaqtincha boshqa botning bazasi bilan ishlash."""
    def __init__(s, bot): s.b = bot
    def __enter__(s): s.old = getattr(TL, "bot", None); TL.bot = s.b
    def __exit__(s, *a): TL.bot = s.old


def bg(fn, *a):
    """Fon oqimida ishga tushirish (joriy bot konteksti bilan)."""
    b = TL.bot
    def w():
        TL.bot = b
        try: fn(*a)
        except Exception: elog()
    threading.Thread(target=w, daemon=True).start()


class _State:
    """Foydalanuvchi holati — har bir bot uchun alohida (kalit: bot tokeni + user id)."""
    def _k(s, uid): return (TL.bot.t, uid)
    def get(s, uid, d=None): return _ST.get(s._k(uid), d)
    def pop(s, uid, d=None): return _ST.pop(s._k(uid), d)
    def __setitem__(s, uid, v): _ST[s._k(uid)] = v
    def __getitem__(s, uid): return _ST[s._k(uid)]
    def __contains__(s, uid): return s._k(uid) in _ST


STATE = _State()


# ----------------------------- yordamchilar -----------------------------
def q(sql, a=(), one=False):
    d = D()
    with d.lock:
        c = d.con.execute(sql, a)
        d.con.commit()
        return c.fetchone() if one else c.fetchall()


def run(sql, a=()):
    d = D()
    with d.lock:
        c = d.con.execute(sql, a)
        d.con.commit()
        return c.rowcount


def ins(sql, a):
    d = D()
    with d.lock:
        c = d.con.execute(sql, a)
        d.con.commit()
        return c.lastrowid


def g(k):
    r = q("SELECT v FROM settings WHERE k=?", (k,), True)
    return r["v"] if r else DEF.get(k, "")


def setv(k, v): run("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, v))
def num(k):
    try: return float(g(k))
    except ValueError: return 0.0


def esc(x): return html.escape(str(x if x not in (None, "") else "—"))
def money(x): return f"{int(round(float(x))):,}".replace(",", " ")
def dt(ts): return time.strftime("%d.%m.%Y %H:%M", time.localtime(ts)) if ts > time.time() else "tugagan"
def U(uid): return q("SELECT * FROM users WHERE id=?", (uid,), True)
def is_admin(uid): return uid == cur().admin or bool(q("SELECT 1 FROM admins WHERE id=?", (uid,), True))


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
    (BOTS.get(via) or cur()).send(uid, text)


def log(text):
    c = g("log_chat")
    if c: cur().send(c, text)


# ----------------------------- tugma dizayni (rang / nom / premium emoji) -----------------------------
STYLES = ("primary", "success", "danger")          # ko'k, yashil, qizil
DEF_STYLE = {                                      # tugmalarning boshlang'ich ranglari (qolgani — ko'k)
    "📲 Botni ulash": "success", "💎 Obuna olish": "success", "💳 Balans to'ldirish": "success",
    "🕘 Tarixim": "success", "🤝 Hamkorlik": "success", "⚡ Avto to'lov": "success", "💳 Click orqali": "success",
    "✅ To'lovni tekshirish": "success", "✅ Hamkor bo'lish": "success",
    "🛒 7 kun": "success", "🛒 30 kun": "success", "🛒 90 kun": "success", "🛒 365 kun": "success",
    "🗑 Keshni tozalash": "danger", "⚙️ Admin panel": "danger", "🏠 Menyu": "danger",
    "⚡ Avto to'lov ulash": "success", "💳 Click ulash": "success", "📢 Majburiy kanallar": "success",
    "🎨 Dizayn": "primary", "✏️ Tugmalarni tahrirlash": "primary", "💎 Premium emoji": "success",
}


def strip_emoji(label):
    s2 = re.sub(r"^[^\w]+", "", label)
    return s2 or label


def _btns():
    d = D()
    if d.btn is None:
        with d.lock:
            d.btn = {r["key"]: dict(r) for r in d.con.execute("SELECT * FROM btns")}
    return d.btn


def bset(key, **kw):
    c = dict(_btns().get(key) or {"key": key, "label": None, "style": None, "emoji": None})
    c.update(kw)
    run("INSERT OR REPLACE INTO btns(key,label,style,emoji) VALUES(?,?,?,?)", (key, c["label"], c["style"], c["emoji"]))
    D().btn = None; D().rev = None


def reset_design():
    run("DELETE FROM btns")
    D().btn = None; D().rev = None


def shown(key):
    """Tugmada ko'rinadigan matn (premium emoji qo'yilgan bo'lsa, boshidagi oddiy emoji olib tashlanadi)."""
    c = _btns().get(key) or {}
    lab = c.get("label") or key
    return strip_emoji(lab) if c.get("emoji") else lab


def cur_style(key):
    return (_btns().get(key) or {}).get("style") or DEF_STYLE.get(key) or "primary"


def btn(key, st=""):
    c = _btns().get(key) or {}
    d = {"text": shown(key), "style": c.get("style") or DEF_STYLE.get(key) or st or "primary"}
    if c.get("emoji"): d["icon_custom_emoji_id"] = c["emoji"]
    return d


def rev(text):
    """Bosilgan tugma matnini (nomi o'zgartirilgan bo'lsa ham) asl kalitga qaytaradi."""
    d = D()
    if d.rev is None:
        m = {}
        for k in ROUTES:
            m.setdefault(k, k); m.setdefault(strip_emoji(k), k)
        for k in ROUTES: m[shown(k)] = k
        d.rev = m
    return d.rev.get(text, text)


def label_conflict(key, new):
    n = new.strip().lower()
    return any(k != key and n in (k.lower(), shown(k).lower(), strip_emoji(k).lower()) for k in ROUTES)


def strip_markup(mk, lvl):
    """Telegram rang/ikonka xatosi bersa: 1 — ikonkasiz, 2 — ikonkasiz va ranglarsiz."""
    mk = json.loads(json.dumps(mk))
    for key in ("keyboard", "inline_keyboard"):
        for row in mk.get(key, []):
            for b in row:
                b.pop("icon_custom_emoji_id", None)
                if lvl > 1: b.pop("style", None)
    return mk


def kb(rows):
    """Pastki (reply) klaviatura. Element: "matn" yoki ("matn", "rang")."""
    out = []
    for r in rows:
        line = []
        for b in r:
            t, st = (b, "") if isinstance(b, str) else b
            line.append(btn(t, st))
        out.append(line)
    return {"keyboard": out, "resize_keyboard": True}


def ib(text, st="primary", cb=None, url=None, copy=None):
    """Inline tugma."""
    d = {"text": text, "style": st}
    if cb: d["callback_data"] = cb
    if url: d["url"] = url
    if copy: d["copy_text"] = {"text": copy}
    return d


def ik(rows): return {"inline_keyboard": rows}


def main_rows(uid):
    s = cur()
    rows = [
        [("📲 Botni ulash", "success"), ("💎 Obuna olish", "success")],
        [("💳 Balans to'ldirish", "success"), ("💰 Balansim", "primary")],
        [("📅 Obunam", "primary"), ("🧾 To'lovlarim", "primary")],
        [("🕘 Tarixim", "success"), ("📊 Statistikam", "primary")],
        [("🎁 Promokod", "primary"), ("🔗 Referal", "primary")],
    ]
    if s.main: rows.append([("🤝 Hamkorlik", "success"), ("🤖 Mening botim", "primary")])
    elif is_admin(uid): rows.append([("⚙️ Admin panel", "danger")])      # klon botda Hamkorlik o'rnida — admin panel
    rows += [
        [("🔔 O'chirilganlar", "primary"), ("✏️ Tahrirlanganlar", "primary")],
        [("🗑 Keshni tozalash", "danger"), ("📖 Qo'llanma", "primary")],
        [("❓ Savol-javob", "primary"), ("🆘 Yordam", "primary")],
        [("📜 Shartlar", "primary")],
    ]
    if s.main and is_admin(uid): rows.append([("⚙️ Admin panel", "danger")])
    return rows


def route(label):
    def d(f):
        ROUTES[label] = f
        return f
    return d


def state(name):
    def d(f):
        SH[name] = f
        return f
    return d


def cbq(name):
    def d(f):
        CB[name] = f
        return f
    return d


# ----------------------------- majburiy kanallar -----------------------------
def channels(): return q("SELECT * FROM channels")


def gate(s, uid):
    """A'zo bo'lmagan majburiy kanallar ro'yxati (bo'sh ro'yxat = hammasi joyida)."""
    if is_admin(uid): return []
    miss = []
    for ch in channels():
        r = s.call("getChatMember", chat_id=ch["id"], user_id=uid)
        if r is None: continue          # bot kanalda admin emas / xato — foydalanuvchini to'sib qo'ymaymiz
        st = r.get("status")
        if st in ("member", "administrator", "creator") or (st == "restricted" and r.get("is_member", True)): continue
        miss.append(ch)
    return miss


def gate_send(s, uid, miss):
    rows = [[ib("📢 " + str(c["title"] or c["id"])[:40], "primary", url=c["link"])] for c in miss if c["link"]]
    rows.append([ib("✅ Tekshirish", "success", cb="chk")])
    s.send(uid, "📢 Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling, so'ng «✅ Tekshirish» tugmasini bosing:",
           inl=ik(rows))


# ----------------------------- umumiy funksiyalar -----------------------------
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
            cur().send(u["referrer"], f"🎉 Referalingiz xaridi uchun +{money(x)} so'm balansingizga tushdi.")


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
    bg(work)
    s.send(uid, f"📢 Yuborish boshlandi ({len(ids)} ta).")
