import json
import os
import sys
import time
import urllib.parse
import urllib.request


def load_token():
    token = os.getenv("BOT_TOKEN")
    if token:
        return token
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == "BOT_TOKEN":
                    return v.strip()
    return None


def api_call(token, method, params=None):
    base = f"https://api.telegram.org/bot{token}/{method}"
    data = None
    if params:
        data = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(base, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
        return json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 409:
            req_del = urllib.request.Request(f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=True")
            with urllib.request.urlopen(req_del, timeout=30) as resp:
                json.loads(resp.read().decode("utf-8"))
            return {"ok": False, "result": []}
        raise e


def main():
    token = load_token()
    if not token:
        sys.exit(1)

    offset = None
    print("Бот запущен (стандартная библиотека). Ожидание апдейтов...")
    while True:
        try:
            api_call(token, "deleteWebhook", {"drop_pending_updates": True})
            break
        except Exception as e:
            if "409" in str(e):
                print("Удаление конфликтующего вебхука...")
                time.sleep(1)
                continue
            raise e

    while True:
        try:
            params = {"timeout": 25}
            if offset is not None:
                params["offset"] = offset
            res = api_call(token, "getUpdates", params)
            if not res.get("ok"):
                time.sleep(2)
                continue
            for upd in res.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                chat = msg.get("chat") or {}
                text = msg.get("text") or ""
                if not chat or not text:
                    continue
                chat_id = chat.get("id")
                from_user = msg.get("from") or {}
                uid = from_user.get("id")
                full_name = (from_user.get("first_name") or "") + (" " + from_user.get("last_name") if from_user.get("last_name") else "")

                if text.strip().lower().startswith("/start"):
                    reply = (
                        f"Привет, {full_name.strip() or 'друг'}!\n\n"
                        f"Твой Telegram ID: <code>{uid}</code>\n"
                        "Чтобы завершить регистрацию в сервисе знакомств, отправь команду /confirm"
                    )
                    print(f"[LOG] User {uid} (@{from_user.get('username', 'N/A')}) started the bot.")
                    api_call(token, "sendMessage", {"chat_id": chat_id, "text": reply, "parse_mode": "HTML"})

                elif text.strip().lower().startswith("/confirm"):
                    # Здесь в будущем будет вызов Profile Service
                    print(f"[LOG] User {uid} (@{from_user.get('username', 'N/A')}) confirmed registration.")
                    
                    confirmation_reply = (
                        "✅ <b>Регистрация успешно подтверждена!</b>\n\n"
                        "Твоя анкета создана. Теперь ты можешь искать мэтчи и общаться.\n"
                        "Удачи в поисках!"
                    )
                    api_call(token, "sendMessage", {"chat_id": chat_id, "text": confirmation_reply, "parse_mode": "HTML"})
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(3)


if __name__ == "__main__":
    main()
