"""pay.py — Tezcheck (hisob/kassa API), avto-to'lov, balans to'ldirish, fon vazifalari (poller, cleaner, zaxira)."""
import os, time, json, hmac, hashlib, sqlite3
import requests
from core import *

# ======================= TEZCHECK (hujjatga moslang) =======================
# Hisob API (balans) va Kassa API (schot yaratish / holat) manzillari.
# Tezcheck hujjatidagi haqiqiy yo'llar bilan almashtiring.
TC_PATHS = {
    "balance": ("GET", "/account/balance"),         # hisob API
    "create": ("POST", "/cashbox/invoice"),         # kassa API: schot yaratish
    "status": ("GET", "/cashbox/invoice/{id}"),     # kassa API: schot holati
}
# ===========================================================================


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
