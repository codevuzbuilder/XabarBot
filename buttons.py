"""buttons.py — foydalanuvchi tugmalari (18 ta) va admin panel menyulari (100 ta tugma)."""
import os, sys, time, html
from core import *
from ops import *

# ----------------------------- Foydalanuvchi tugmalari -----------------------------
@route("🏠 Menyu")
def r_home(s, uid, m): s.menu(uid)


@route("📲 Botni ulash")
def r_connect(s, uid, m):
    s.send(uid, f"📲 <b>Ulash</b>\n1) Telegram → Sozlamalar → <b>Telegram Business</b> → <b>Chatbotlar</b> "
                f"(Chat avtomatlashtirish)\n2) <code>@{s.username}</code> ni kiriting\n"
                f"3) Qaysi chatlar uchun ishlashini tanlang va ruxsatlarni yoqing.\n\n"
                f"ℹ️ Telegram Premium kerak. Bot «yaroqsiz» desa, adminga xabar bering.", main_rows(uid))


@route("💎 Obuna olish")
def r_plans(s, uid, m):
    u = U(uid)
    s.send(uid, "💎 <b>Tariflar</b> (balansdan yechiladi)\n" +
           "\n".join(f"🛒 {d} kun — {money(num(f'price_{d}'))} so'm" for d in (7, 30, 90, 365)) +
           f"\n\n💰 Balansingiz: {money(u['balance'])} so'm",
           [[("🛒 7 kun", "success"), ("🛒 30 kun", "success")], [("🛒 90 kun", "success"), ("🛒 365 kun", "success")],
            [("💳 Balans to'ldirish", "primary"), ("🏠 Menyu", "")]])


def _buy(days):
    def f(s, uid, m):
        price, u = num(f"price_{days}"), U(uid)
        if u["balance"] < price:
            return s.send(uid, f"❌ Balans yetarli emas.\n💰 Balans: {money(u['balance'])}\n🛒 Narx: {money(price)}\n\n"
                               f"«💳 Balans to'ldirish» tugmasini bosing.")
        until = max(int(time.time()), u["sub_until"]) + days * 86400
        run("UPDATE users SET balance=balance-?, sub_until=? WHERE id=?", (price, until, uid))
        shares(u, price)
        s.send(uid, f"✅ Obuna {days} kunga faollashdi!\n📅 Tugash: {dt(until)}", main_rows(uid))
        log(f"🛒 {uid} — {days} kun ({money(price)} so'm)")
    return f


for _d in (7, 30, 90, 365): ROUTES[f"🛒 {_d} kun"] = _buy(_d)


@route("💳 Balans to'ldirish")
def r_topup(s, uid, m):
    rows = []
    if g("autopay") == "1" and g("tc_key"): rows.append([("⚡ Avto to'lov", "success")])
    if g("manual_pay") == "1": rows.append([("🧾 Chek bilan to'lov", "primary")])
    if not rows: return s.send(uid, "❌ To'lov usullari hozircha o'chirilgan.", main_rows(uid))
    rows.append([("🏠 Menyu", "")])
    s.send(uid, f"💳 To'lov usulini tanlang.\nMin: {money(num('min_topup'))} • Max: {money(num('max_topup'))} so'm", rows)


@route("⚡ Avto to'lov")
def r_auto(s, uid, m):
    STATE[uid] = ("amt", "tc")
    s.send(uid, "💵 To'ldirish summasini yozing (so'mda):", [[("🏠 Menyu", "")]])


@route("🧾 Chek bilan to'lov")
def r_manual(s, uid, m):
    STATE[uid] = ("amt", "receipt")
    s.send(uid, "💵 To'ldirish summasini yozing (so'mda):", [[("🏠 Menyu", "")]])


@route("✅ To'lovni tekshirish")
def r_check(s, uid, m):
    ps = q("SELECT * FROM payments WHERE user_id=? AND status='pending' AND method='tc'", (uid,))
    if not ps: return s.send(uid, "ℹ️ Kutilayotgan to'lov yo'q.", main_rows(uid))
    for p in ps:
        try: check_payment(p)
        except Exception: elog()
    left = q("SELECT COUNT(*) c FROM payments WHERE user_id=? AND status='pending' AND method='tc'", (uid,), True)["c"]
    if left: s.send(uid, "⏳ To'lov hali kelmadi. To'lagan bo'lsangiz, 1-2 daqiqadan so'ng qayta tekshiring.")


@route("💰 Balansim")
def r_balance(s, uid, m):
    u = U(uid)
    s.send(uid, f"💰 Balans: <b>{money(u['balance'])}</b> so'm", main_rows(uid))


@route("📅 Obunam")
def r_sub(s, uid, m):
    u = U(uid)
    n = q("SELECT COUNT(*) c FROM conns WHERE user_id=?", (uid,), True)["c"]
    st = f"✅ Faol — {dt(u['sub_until'])} gacha" if u["sub_until"] > time.time() else "❌ Obuna yo'q"
    s.send(uid, f"📅 Obuna: {st}\n🔗 Ulangan akkaunt: {n}", main_rows(uid))


@route("🧾 To'lovlarim")
def r_history(s, uid, m):
    ps = q("SELECT * FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,))
    ic = {"approved": "✅", "pending": "⏳", "rejected": "❌", "expired": "⌛", "failed": "⚠️"}
    s.send(uid, "🧾 <b>So'nggi to'lovlar</b>\n" + ("\n".join(
        f"{ic.get(p['status'], '•')} #{p['id']} — {money(p['amount'])} so'm ({time.strftime('%d.%m %H:%M', time.localtime(p['ts']))})"
        for p in ps) or "—"), main_rows(uid))


@route("🎁 Promokod")
def r_promo(s, uid, m):
    if g("promo_on") != "1": return s.send(uid, "🎁 Promokodlar hozircha o'chirilgan.", main_rows(uid))
    STATE[uid] = ("promo",)
    s.send(uid, "🎁 Promokodni yuboring:", [[("🏠 Menyu", "")]])


@route("🔗 Referal")
def r_ref(s, uid, m):
    if g("ref_on") != "1": return s.send(uid, "🔗 Referal dasturi hozircha o'chirilgan.", main_rows(uid))
    n = q("SELECT COUNT(*) c FROM users WHERE referrer=?", (uid,), True)["c"]
    s.send(uid, f"🔗 Havolangiz:\nhttps://t.me/{s.username}?start=ref_{uid}\n\n👥 Taklif qilinganlar: {n}\n"
                f"🎁 Ularning har bir xarididan {g('ref_percent')}% balansingizga tushadi.", main_rows(uid))


@route("🤝 Hamkorlik")
def r_partner(s, uid, m):
    if g("partner_on") != "1": return s.send(uid, "🤝 Hamkorlik dasturi hozircha yopiq.", main_rows(uid))
    u = U(uid)
    if u["is_partner"]:
        n = q("SELECT COUNT(*) c FROM users WHERE partner_id=?", (uid,), True)["c"]
        return s.send(uid, f"🤝 Siz hamkorsiz.\n💰 Balans: {money(u['balance'])} so'm\n👥 Foydalanuvchilaringiz: {n}\n"
                           f"📈 Ulush: {g('commission')}%\n\n«🤖 Mening botim» orqali o'z botingizni oling.", main_rows(uid))
    s.send(uid, f"{g('partner_text')}\n\n💎 Narxi: {money(num('partner_price'))} so'm (balansdan)\n💰 Balansingiz: {money(u['balance'])}",
           [[("✅ Hamkor bo'lish", "success")], [("🏠 Menyu", "")]])


@route("✅ Hamkor bo'lish")
def r_bepartner(s, uid, m):
    u, price = U(uid), num("partner_price")
    if g("partner_on") != "1" or u["is_partner"]: return s.menu(uid)
    if u["balance"] < price: return s.send(uid, f"❌ Balans yetarli emas ({money(u['balance'])} / {money(price)}).")
    run("UPDATE users SET balance=balance-?, is_partner=1 WHERE id=?", (price, uid))
    s.send(uid, "🎉 Siz endi hamkorsiz! «🤖 Mening botim» tugmasini bosing.", main_rows(uid))
    log(f"🤝 Yangi hamkor: {uid}")


@route("🤖 Mening botim")
def r_mybot(s, uid, m):
    if not U(uid)["is_partner"]: return s.send(uid, "🤖 Avval «🤝 Hamkorlik» bo'limidan hamkor bo'ling.", main_rows(uid))
    cl = q("SELECT token FROM clones WHERE owner=?", (uid,))
    lst = "\n".join("• @" + (BOTS[c["token"]].username if c["token"] in BOTS else "?") for c in cl) or "—"
    STATE[uid] = ("token",)
    s.send(uid, f"🤖 Botlaringiz:\n{lst}\n\n@BotFather dan olgan yangi bot tokenini yuboring.\n"
                f"⚠️ BotFather → Bot Settings → <b>Business Mode</b> ni yoqing.", [[("🏠 Menyu", "")]])


# ----------------------------- ADMIN: 10 bo'lim x 10 tugma = 100 -----------------------------
# (nom, tur, argument, [yo'riqnoma])
CATS = [
    ("📊 Statistika", [
        ("👥 Jami userlar", "sql", "SELECT COUNT(*) FROM users"),
        ("🆕 Bugun qo'shilgan", "sql", "SELECT COUNT(*) FROM users WHERE joined>={day}"),
        ("📆 Haftalik yangi", "sql", "SELECT COUNT(*) FROM users WHERE joined>={now}-604800"),
        ("🗓 Oylik yangi", "sql", "SELECT COUNT(*) FROM users WHERE joined>={now}-2592000"),
        ("💎 Faol obuna", "sql", "SELECT COUNT(*) FROM users WHERE sub_until>{now}"),
        ("⌛ Obunasi tugagan", "sql", "SELECT COUNT(*) FROM users WHERE sub_until<={now}"),
        ("🔗 Ulangan akkaunt", "sql", "SELECT COUNT(*) FROM conns"),
        ("💬 Keshdagi xabarlar", "sql", "SELECT COUNT(*) FROM msgs"),
        ("🤝 Hamkorlar soni", "sql", "SELECT COUNT(*) FROM users WHERE is_partner=1"),
        ("💵 Jami tushum", "sql", "SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='approved'"),
    ]),
    ("💰 Narxlar", [
        ("💲 7 kunlik narx", "set", "price_7"), ("💲 30 kunlik narx", "set", "price_30"),
        ("💲 90 kunlik narx", "set", "price_90"), ("💲 365 kunlik narx", "set", "price_365"),
        ("🤝 Hamkorlik narxi", "set", "partner_price"), ("📈 Hamkor ulushi %", "set", "commission"),
        ("🔗 Referal ulushi %", "set", "ref_percent"), ("🎁 To'ldirish bonusi %", "set", "topup_bonus"),
        ("⬇️ Min to'ldirish", "set", "min_topup"), ("⬆️ Max to'ldirish", "set", "max_topup"),
    ]),
    ("💳 To'lov tizimi", [
        ("🔑 Tezcheck API kalit", "set", "tc_key"), ("🔐 Tezcheck maxfiy kalit", "set", "tc_secret"),
        ("🏪 Tezcheck kassa ID", "set", "tc_kassa"), ("🌐 Tezcheck API manzil", "set", "tc_base"),
        ("💳 Karta rekviziti", "set", "pay_info"), ("⚡ Avto-to'lov yoq/o'ch", "toggle", "autopay"),
        ("🧾 Chek rejimi yoq/o'ch", "toggle", "manual_pay"), ("⏱ Schot muddati (daq)", "set", "tc_ttl"),
        ("💼 Tezcheck balansi", "fn", f_tc_balance), ("🧪 Ulanishni tekshirish", "fn", f_tc_test),
    ]),
    ("👤 Userlar", [
        ("🔎 User ma'lumoti", "op", "info", "ID yuboring. Masalan: 123456789"),
        ("🚫 User ban", "op", "ban", "ID yuboring."), ("✅ Bandan chiqarish", "op", "unban", "ID yuboring."),
        ("➕ Kun qo'shish", "op", "addays", "ID va kun: 123456789 30"),
        ("➖ Obunani bekor qilish", "op", "cancelsub", "ID yuboring."),
        ("💵 Balans qo'shish", "op", "addbal", "ID va summa: 123456789 10000"),
        ("💸 Balans ayirish", "op", "subbal", "ID va summa: 123456789 10000"),
        ("📋 So'nggi 10 user", "fn", f_last_users), ("🚷 Banlanganlar", "fn", f_banned),
        ("💬 Userga xabar", "op", "sendmsg", "ID va matn: 123456789 Salom"),
    ]),
    ("🤝 Hamkorlar", [
        ("📋 Hamkorlar ro'yxati", "fn", f_partners), ("➕ Hamkor qilish", "op", "partner_add", "ID yuboring."),
        ("➖ Hamkorlikdan chiqarish", "op", "partner_del", "ID yuboring."),
        ("💰 Hamkor balansi", "op", "partner_bal", "ID yuboring."),
        ("🤖 Klon botlar", "fn", f_clones), ("🗑 Klonni o'chirish", "op", "clone_del", "Hamkor ID sini yuboring."),
        ("🏆 Top hamkorlar", "fn", f_top_partners),
        ("👥 Hamkor userlari", "op", "partner_users", "Hamkor ID sini yuboring."),
        ("💸 Hamkorga to'lash", "op", "partner_pay", "ID va summa: 123456789 50000"),
        ("🏦 Hamkorlar balansi jami", "sql", "SELECT COALESCE(SUM(balance),0) FROM users WHERE is_partner=1"),
    ]),
    ("📢 Xabarlar", [
        ("📢 Hammaga xabar", "bc", "all"), ("💎 Faollarga xabar", "bc", "active"),
        ("⌛ Tugaganlarga xabar", "bc", "expired"), ("🤝 Hamkorlarga xabar", "bc", "partners"),
        ("👋 Salomlashuv matni", "set", "welcome_text"), ("📖 Qo'llanma matni", "set", "guide_text"),
        ("❓ Savol-javob matni", "set", "faq_text"), ("📜 Shartlar matni", "set", "terms_text"),
        ("🆘 Yordam matni", "set", "support_text"), ("🤝 Hamkorlik matni", "set", "partner_text"),
    ]),
    ("⚙️ Sozlamalar", [
        ("🔌 Bot yoq/o'ch", "toggle", "bot_on"), ("🆕 Ro'yxat yoq/o'ch", "toggle", "reg_on"),
        ("🎁 Sinov yoq/o'ch", "toggle", "trial_on"), ("🗑 O'chirilgan xabar yoq/o'ch", "toggle", "notify_deleted"),
        ("✏️ Tahrir xabari yoq/o'ch", "toggle", "notify_edited"), ("🖼 Media saqlash yoq/o'ch", "toggle", "save_media"),
        ("🤝 Hamkorlik yoq/o'ch", "toggle", "partner_on"), ("🔗 Referal yoq/o'ch", "toggle", "ref_on"),
        ("🎟 Promokod yoq/o'ch", "toggle", "promo_on"), ("🔔 Yangi user xabari", "toggle", "notify_admin_new"),
    ]),
    ("🗄 Ma'lumotlar", [
        ("💾 Zaxira nusxa", "fn", f_backup), ("👥 Userlar CSV", "fn", f_csv_users), ("🧾 To'lovlar CSV", "fn", f_csv_pay),
        ("🧹 Eski keshni tozalash", "fn", f_clear_old), ("🗑 Butun keshni tozalash", "fn", f_clear_all),
        ("📅 Kesh saqlash kuni", "set", "cache_days"), ("🧮 DB hajmi", "fn", f_db_size),
        ("🪄 DB optimallash", "fn", f_vacuum), ("📋 Kutilayotgan to'lovlar", "fn", f_pending),
        ("🧾 So'nggi 10 to'lov", "fn", f_last_payments),
    ]),
    ("🎁 Promokodlar", [
        ("➕ Kunli promokod", "op", "promo_days", "KOD KUN LIMIT: YANGI30 30 100"),
        ("💵 Pulli promokod", "op", "promo_money", "KOD SUMMA LIMIT: BONUS 10000 50"),
        ("🗑 Promokodni o'chirish", "op", "promo_del", "KOD yuboring."), ("📋 Promokodlar ro'yxati", "fn", f_promos),
        ("🔎 Promokod ma'lumoti", "op", "promo_info", "KOD yuboring."),
        ("🔄 Promokod yoq/o'ch", "op", "promo_toggle", "KOD yuboring."), ("📊 Promokod statistikasi", "fn", f_promo_stats),
        ("🧹 Tugaganlarni tozalash", "fn", f_promo_clean), ("📣 Promokodni e'lon qilish", "op", "promo_announce", "KOD yuboring."),
        ("👁 Promokod ishlatganlar", "op", "promo_users", "KOD yuboring."),
    ]),
    ("🛠 Qo'shimcha", [
        ("📺 Majburiy kanal", "set", "req_channel"), ("📝 Log chat ID", "set", "log_chat"),
        ("👮 Admin qo'shish", "op", "admin_add", "Yangi admin ID sini yuboring."),
        ("👮 Admin o'chirish", "op", "admin_del", "Admin ID sini yuboring."), ("📋 Adminlar", "fn", f_admins),
        ("🤖 Bot haqida", "fn", f_bot_info), ("🩺 Business holati", "fn", f_biz), ("🐞 Xatolar logi", "fn", f_errors),
        ("🔁 Qayta ishga tushirish", "fn", f_restart), ("🏓 Ping", "fn", f_ping),
    ]),
]


def admin_rows():
    rows = [[(c[0], "primary") for c in CATS[i:i + 2]] for i in range(0, len(CATS), 2)]
    rows.append([("🏠 Menyu", "")])
    return rows


def cat_rows(ci):
    items = CATS[ci][1]
    rows = [[(it[0], btn_style(it)) for it in items[i:i + 2]] for i in range(0, len(items), 2)]
    rows.append([("⬅️ Admin panel", "primary"), ("🏠 Menyu", "")])
    return rows


@route("⚙️ Admin panel")
def r_admin(s, uid, m):
    if is_admin(uid): s.send(uid, "⚙️ <b>Admin panel</b> — bo'lim tanlang:", admin_rows())


@route("⬅️ Admin panel")
def r_admin_back(s, uid, m): r_admin(s, uid, m)


def _mk_cat(ci):
    def f(s, uid, m):
        if is_admin(uid): s.send(uid, f"{CATS[ci][0]} — tugmani tanlang:", cat_rows(ci))
    return f


def _mk_item(it):
    def f(s, uid, m):
        if is_admin(uid): run_item(s, uid, it)
    return f


for _ci, (_cl, _items) in enumerate(CATS):
    ROUTES[_cl] = _mk_cat(_ci)
    for _it in _items: ROUTES[_it[0]] = _mk_item(_it)
