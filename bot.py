"""bot.py — Telegram bot (ishga tushirish: python bot.py). core.py, ops.py, buttons.py bilan bir papkada turishi kerak."""
import re, sys, time, threading
import requests
from core import *
from pay import *
from ops import *
from buttons import *   # tugmalarni ro'yxatga oladi (ROUTES)
from partner import *   # hamkor paneli

MEDIA = {"photo": ("sendPhoto", "photo"), "video": ("sendVideo", "video"), "voice": ("sendVoice", "voice"),
         "video_note": ("sendVideoNote", "video_note"), "document": ("sendDocument", "document"),
         "audio": ("sendAudio", "audio"), "animation": ("sendAnimation", "animation"),
         "sticker": ("sendSticker", "sticker")}
UPDATES = ["message", "business_connection", "business_message", "edited_business_message",
           "deleted_business_messages"]


# ----------------------------- Bot -----------------------------
class Bot:
    def __init__(s, token, partner=None):
        s.t, s.partner, s.alive, s.err, s.code = token, partner, True, "", None
        s.api = f"https://api.telegram.org/bot{token}/"
        me = s.call("getMe") or {}
        s.username = me.get("username", "bot")
        s.biz = bool(me.get("can_connect_to_business"))

    def call(s, method, **p):
        s.code = None
        try:
            r = requests.post(s.api + method, json=p, timeout=60).json()
            if r.get("ok"): return r["result"]
            s.err, s.code = str(r.get("description")), r.get("error_code")
            print(method, r)
        except Exception as e:
            s.err = str(e)
            print(method, e)

    def upload(s, method, field, name, data, **p):
        try:
            r = requests.post(s.api + method, data=p, files={field: (name, data)}, timeout=120).json()
            if r.get("ok"): return r["result"]
            print(method, r)
        except Exception: elog()

    def fetch_file(s, fid):
        f = s.call("getFile", file_id=fid)
        if f: return requests.get(f"https://api.telegram.org/file/bot{s.t}/{f['file_path']}", timeout=60).content

    def send(s, chat, text, rows=None):
        p = dict(chat_id=chat, text=text[:4000], parse_mode="HTML")
        if rows: p["reply_markup"] = kb(rows)
        r = s.call("sendMessage", **p)
        if r is None and "parse entities" in s.err:
            p.pop("parse_mode")
            r = s.call("sendMessage", **p)
        return r

    def run(s):
        off = 0
        while s.alive:
            ups = s.call("getUpdates", offset=off, timeout=30, allowed_updates=UPDATES)
            if ups is None:
                if s.code == 401: return s.dead()
                time.sleep(3); continue
            for u in ups:
                off = u["update_id"] + 1
                try: s.handle(u)
                except Exception: elog()

    def dead(s):
        """Token yaroqsiz (401) bo'lsa botni to'xtatadi va klonni bazadan o'chiradi."""
        s.alive = False
        BOTS.pop(s.t, None)
        print("Bot to'xtatildi (token yaroqsiz):", s.t.split(":")[0])
        if s.t != TOKEN:
            run("DELETE FROM clones WHERE token=?", (s.t,))
            if s.partner: main_bot().send(s.partner, "⚠️ Botingiz tokeni yaroqsiz (bekor qilingan), bot to'xtatildi. Yangi token bilan qayta qo'shing.")
            main_bot().send(ADMIN_ID, f"⚠️ Klon bot (hamkor {s.partner}) tokeni yaroqsiz — o'chirildi.")

    def handle(s, u):
        if "business_connection" in u: return s.conn(u["business_connection"])
        if "business_message" in u: return s.bmsg(u["business_message"])
        if "edited_business_message" in u: return s.bedit(u["edited_business_message"])
        if "deleted_business_messages" in u: return s.bdel(u["deleted_business_messages"])
        if "message" in u: return s.msg(u["message"])

    # ---------- Business ----------
    def conn(s, c):
        uid = c["user"]["id"]
        if c.get("is_enabled"):
            reg(uid, s.partner, None, s.t)
            q("INSERT OR REPLACE INTO conns VALUES(?,?)", (c["id"], uid))
            s.send(c["user_chat_id"], "✅ Akkaunt ulandi. O'chirilgan va tahrirlangan xabarlar shu yerga keladi.")
        else:
            q("DELETE FROM conns WHERE id=?", (c["id"],))

    def bmsg(s, m):
        c = q("SELECT user_id FROM conns WHERE id=?", (m["business_connection_id"],), True)
        if not c or m["from"]["id"] == c["user_id"]: return
        kind, fid = media(m) if g("save_media") == "1" else (None, None)
        who = (m["from"].get("first_name", "") + " " + m["from"].get("last_name", "")).strip()
        q("INSERT OR REPLACE INTO msgs VALUES(?,?,?,?,?,?,?,?,?)",
          (m["business_connection_id"], m["chat"]["id"], m["message_id"], c["user_id"], who, kind,
           m.get("text") or m.get("caption"), fid, int(time.time())))

    def find(s, cid, chat, mid):
        return q("SELECT * FROM msgs WHERE cid=? AND chat=? AND mid=?", (cid, chat, mid), True)

    def bedit(s, m):
        r = s.find(m["business_connection_id"], m["chat"]["id"], m["message_id"])
        if not r: return
        new = m.get("text") or m.get("caption")
        u = U(r["owner"])
        if u and u["n_edit"] and g("notify_edited") == "1" and active(r["owner"]):
            s.send(r["owner"], f"✏️ <b>{esc(r['who'])}</b> xabarni tahrirladi\n\n"
                               f"<b>Eski:</b> {esc(r['text'])}\n<b>Yangi:</b> {esc(new)}")
        q("UPDATE msgs SET text=? WHERE cid=? AND chat=? AND mid=?", (new, r["cid"], r["chat"], r["mid"]))

    def bdel(s, d):
        for mid in d["message_ids"]:
            r = s.find(d["business_connection_id"], d["chat"]["id"], mid)
            if not r: continue
            u = U(r["owner"])
            if not (u and u["n_del"] and g("notify_deleted") == "1" and active(r["owner"])): continue
            s.send(r["owner"], f"🗑 <b>{esc(r['who'])}</b> xabarni o'chirdi:\n{esc(r['text'])}")
            if r["kind"] and r["fid"]:
                meth, key = MEDIA[r["kind"]]
                s.call(meth, chat_id=r["owner"], **{key: r["fid"]})

    # ---------- Suhbat ----------
    def menu(s, uid, text="🏠 Bosh menyu"):
        STATE.pop(uid, None)
        s.send(uid, text, main_rows(uid))

    def msg(s, m):
        if m["chat"]["type"] != "private": return
        uid, t = m["from"]["id"], (m.get("text") or "").strip()
        if not is_admin(uid) and g("bot_on") != "1":
            return s.send(uid, "🔧 Bot vaqtincha o'chirilgan. Keyinroq urinib ko'ring.")
        ref = None
        if t.startswith("/start ref_") and t[11:].isdigit(): ref = int(t[11:])
        new = reg(uid, s.partner, ref, s.t)
        if new is None: return s.send(uid, "🔒 Hozircha ro'yxatdan o'tish yopiq.")
        u = U(uid)
        if u["banned"]: return s.send(uid, "🚫 Siz bloklangansiz.")
        if s.partner and q("SELECT 1 FROM pbans WHERE partner=? AND user_id=?", (s.partner, uid), True):
            return s.send(uid, "🚫 Siz bloklangansiz.")
        if new and g("notify_admin_new") == "1":
            main_bot().send(ADMIN_ID, f"🆕 Yangi foydalanuvchi: <code>{uid}</code> ({esc(m['from'].get('first_name'))})")
        if not gate(s, uid):
            return s.send(uid, f"📢 Botdan foydalanish uchun kanalga a'zo bo'ling: {g('req_channel')}\n"
                               f"So'ng /start bosing.")
        if t.startswith("/start"): return s.menu(uid, ptext(s, "welcome_text"))
        mt = re.match(r"/(ok|no)_(\d+)$", t)
        if mt and is_admin(uid): return s.receipt_decision(uid, mt.group(1), int(mt.group(2)))
        if t in ROUTES:
            STATE.pop(uid, None)
            return ROUTES[t](s, uid, m)
        st = STATE.get(uid)
        if st: return s.state(uid, st, m)
        s.menu(uid)

    def receipt_decision(s, uid, act, pid):
        p = q("SELECT * FROM payments WHERE id=? AND method='receipt'", (pid,), True)
        if not p or p["status"] != "pending": return s.send(uid, "ℹ️ Bu to'lov allaqachon ko'rib chiqilgan.")
        if act == "ok":
            credit(pid); s.send(uid, f"✅ #{pid} tasdiqlandi.")
        else:
            run("UPDATE payments SET status='rejected' WHERE id=?", (pid,))
            notify(p["user_id"], p["via"], f"❌ To'lov #{pid} rad etildi.")
            s.send(uid, f"❌ #{pid} rad etildi.")

    def state(s, uid, st, m):
        t, k = (m.get("text") or "").strip(), st[0]
        back = [[("🏠 Menyu", "")]]
        if k == "amt":
            digits = re.sub(r"\D", "", t)
            if not digits: return s.send(uid, "❌ Summani raqam bilan yuboring.", back)
            amt = int(digits)
            if amt < num("min_topup") or amt > num("max_topup"):
                return s.send(uid, f"❌ Summa {money(num('min_topup'))} dan {money(num('max_topup'))} gacha bo'lsin.", back)
            if st[1] == "receipt":
                STATE[uid] = ("receipt", amt)
                return s.send(uid, f"{esc(g('pay_info'))}\n\n💵 {money(amt)} so'm o'tkazing va <b>chek rasmini</b> yuboring.", back)
            pid = ins("INSERT INTO payments(user_id,kind,amount,via,method,ts) VALUES(?,?,?,?,?,?)",
                      (uid, "topup", amt, s.t, "tc", int(time.time())))
            try:
                ext, url = tc_create(pid, amt)
                run("UPDATE payments SET ext_id=?, url=? WHERE id=?", (ext, url, pid))
                STATE.pop(uid, None)
                s.send(uid, f"⚡ <b>To'lov #{pid}</b>\n💵 {money(amt)} so'm\n⏱ {int(num('tc_ttl'))} daqiqa ichida to'lang:\n{url}\n\n"
                            f"To'lovdan so'ng hisob avtomatik to'ldiriladi.",
                       [[("✅ To'lovni tekshirish", "success")], [("🏠 Menyu", "")]])
            except Exception as e:
                elog(); run("UPDATE payments SET status='failed' WHERE id=?", (pid,))
                s.send(uid, "⚠️ To'lov tizimi vaqtincha ishlamayapti. Keyinroq urinib ko'ring.", main_rows(uid))
                main_bot().send(ADMIN_ID, f"⚠️ Tezcheck xatosi: {esc(e)}")
        elif k == "receipt":
            if not m.get("photo"): return s.send(uid, "🧾 Chek rasmini yuboring.", back)
            fid, amt = m["photo"][-1]["file_id"], st[1]
            pid = ins("INSERT INTO payments(user_id,kind,amount,via,method,ts) VALUES(?,?,?,?,?,?)",
                      (uid, "topup", amt, s.t, "receipt", int(time.time())))
            cap = f"🧾 To'lov #{pid}\n👤 {uid}\n💵 {money(amt)} so'm\n\n✅ /ok_{pid}\n❌ /no_{pid}"
            mb = main_bot()
            if s is mb: mb.call("sendPhoto", chat_id=ADMIN_ID, photo=fid, caption=cap)
            else:
                data = s.fetch_file(fid)
                mb.upload("sendPhoto", "photo", "chek.jpg", data, chat_id=ADMIN_ID, caption=cap)
            STATE.pop(uid, None)
            s.send(uid, "✅ Chek adminga yuborildi. Tasdiqlangach xabar keladi.", main_rows(uid))
        elif k == "promo":
            STATE.pop(uid, None)
            s.send(uid, redeem(uid, t.upper()), main_rows(uid))
        elif k == "token":
            tok = t
            s.call("deleteMessage", chat_id=uid, message_id=m["message_id"])
            try: me = requests.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=20).json()
            except Exception: me = {}
            if not me.get("ok"): return s.send(uid, "❌ Token noto'g'ri. Qayta yuboring.", back)
            if q("SELECT 1 FROM clones WHERE token=?", (tok,), True) or tok == TOKEN:
                return s.send(uid, "❌ Bu token allaqachon ishlatilgan.", back)
            run("INSERT INTO clones VALUES(?,?)", (tok, uid))
            nb = start(tok, uid)
            STATE.pop(uid, None)
            warn = "" if nb.biz else "\n\n⚠️ Bu botda <b>Business Mode</b> yoqilmagan: @BotFather → Bot Settings → Business Mode."
            s.send(uid, f"✅ @{nb.username} ishga tushdi!{warn}", main_rows(uid))
        elif k == "set" and is_admin(uid):
            key = st[1]
            if key in NUM:
                t = t.replace(" ", "")
                try: float(t)
                except ValueError: return s.send(uid, "❌ Faqat raqam yuboring.")
            if key == "req_channel" and t and not (t.startswith("@") or t.lstrip("-").isdigit()):
                return s.send(uid, "❌ @kanal yoki -100... ko'rinishida yuboring.")
            setv(key, t)
            if key in ("tc_key", "tc_secret"): s.call("deleteMessage", chat_id=uid, message_id=m["message_id"])
            STATE.pop(uid, None)
            s.send(uid, f"✅ {esc(st[2])} yangilandi.")
        elif k == "op" and is_admin(uid):
            try: out = OPS[st[1]](s, t.split(), t)
            except (ValueError, IndexError): return s.send(uid, f"❌ Format noto'g'ri.\n{st[3]}")
            STATE.pop(uid, None)
            s.send(uid, out)
        elif k == "bc" and is_admin(uid):
            STATE.pop(uid, None)
            broadcast(s, uid, st[1], t)
        elif k in ("pset", "pop", "pbc"):
            out = partner_state(s, uid, st, m)
            if out: s.send(uid, out)
        else:
            s.menu(uid)


def media(m):
    for k in MEDIA:
        if k in m:
            v = m[k]
            return k, (v[-1] if isinstance(v, list) else v)["file_id"]
    return None, None


def start(token, partner):
    b = Bot(token, partner)
    if b.code == 401:
        run("DELETE FROM clones WHERE token=?", (token,))
        print("Yaroqsiz klon token o'chirildi:", token.split(":")[0])
        return b
    BOTS[token] = b
    threading.Thread(target=b.run, daemon=True).start()
    return b


# ----------------------------- Ishga tushirish -----------------------------
BIZ_WARN = ("⚠️ Bu botda <b>Business Mode</b> yoqilmagan — akkauntga ulashda «yaroqsiz» deydi.\n"
            "@BotFather → /mybots → bot → Bot Settings → Business Mode → Turn on.")

if __name__ == "__main__":
    BOTS[TOKEN] = main = Bot(TOKEN)
    if main.code == 401: sys.exit("❌ Asosiy bot tokeni yaroqsiz. core.py dagi TOKEN ni tekshiring.")
    print("Bot: @" + main.username, "| Business Mode:", "YOQILGAN" if main.biz else "O'CHIQ!")
    if not main.biz:
        print(BIZ_WARN.replace("<b>", "").replace("</b>", ""))
        main.send(ADMIN_ID, BIZ_WARN)
    for r in q("SELECT * FROM clones"): start(r["token"], r["owner"])
    threading.Thread(target=poller, daemon=True).start()
    threading.Thread(target=cleaner, daemon=True).start()
    main.run()
