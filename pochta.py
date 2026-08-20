"""
ОТПРАВКА ПИСЬМА С КЛЮЧОМ — живёт на Render, рядом с движком голоса.

Зачем отдельно: Cloudflare не умеет обычную почтовую связь, а Render умеет.
Оракул шлёт письма ровно так же — через Gmail, паролем приложения.
Платить не надо: почта твоя, Render уже оплачен.

Как зовётся:
    POST /api/send-key
    { "secret": "<пароль>", "email": "покупатель@почта", "key": "LF-XXXX-XXXX-XXXX" }

⚠️ ПАРОЛЬ ОБЯЗАТЕЛЕН — иначе любой прохожий разошлёт письма от твоего имени.
"""

import os
import re
import ssl
import socket
import smtplib
import asyncio
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

логи = logging.getLogger("pochta")
роутер = APIRouter()

# ── настройки: всё из переменных окружения, в коде ничего ──
ЯЩИК   = os.getenv("SMTP_USER", "makx518@gmail.com")
ПАРОЛЬ = os.getenv("SMTP_PASS", "")
СЕРВЕР = os.getenv("SMTP_HOST", "smtp.gmail.com")
ПОРТ   = int(os.getenv("SMTP_PORT", "587"))
ОТ     = os.getenv("MAIL_FROM", "Luck Forecast <vlad@quantareon.com>")
ПРОПУСК = os.getenv("MAIL_SECRET", "")

ВИД_КЛЮЧА = re.compile(r"^LF-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$")
ВИД_ПОЧТЫ = re.compile(r"^[^\s@]{1,64}@[^\s@]{1,190}\.[a-zA-Z]{2,24}$")


def _отправить(куда: str, ключ: str) -> None:
    """Шлём письмо. Работает в отдельной нити — smtplib не умеет иначе."""
    письмо = MIMEMultipart("alternative")
    письмо["Subject"] = "Your Luck Forecast key"
    письмо["From"] = ОТ
    письмо["To"] = куда
    письмо.attach(MIMEText(ПРОСТЫМ.replace("{{KEY}}", ключ), "plain", "utf-8"))
    письмо.attach(MIMEText(НАРЯДНЫМ.replace("{{KEY}}", ключ), "html", "utf-8"))

    защита = ssl.create_default_context()
    if ПОРТ == 465:
        связь = smtplib.SMTP_SSL(СЕРВЕР, ПОРТ, context=защита, timeout=25)
    else:
        связь = smtplib.SMTP(СЕРВЕР, ПОРТ, timeout=25)
        связь.starttls(context=защита)
    try:
        связь.login(ЯЩИК, ПАРОЛЬ)
        связь.send_message(письмо)
    finally:
        try:
            связь.quit()
        except Exception:
            pass


@роутер.post("/api/send-key")
async def отправить_ключ(запрос: Request):
    try:
        данные = await запрос.json()
    except Exception:
        return JSONResponse({"ok": False, "reason": "bad_request"}, status_code=400)

    # ── пропуск ──
    if not ПРОПУСК or str(данные.get("secret", "")) != ПРОПУСК:
        return JSONResponse({"ok": False, "reason": "forbidden"}, status_code=403)

    почта = str(данные.get("email", "")).strip().lower()
    ключ = str(данные.get("key", "")).strip().upper()

    if not ВИД_ПОЧТЫ.match(почта):
        return JSONResponse({"ok": False, "reason": "bad_email"}, status_code=400)
    if not ВИД_КЛЮЧА.match(ключ):
        return JSONResponse({"ok": False, "reason": "bad_key"}, status_code=400)
    if not ПАРОЛЬ:
        логи.error("POCHTA: нет SMTP_PASS — письмо не отправлено")
        return JSONResponse({"ok": False, "reason": "not_configured"}, status_code=500)

    try:
        # отправка идёт в отдельной нити, чтобы не держать весь сервер
        await asyncio.wait_for(asyncio.to_thread(_отправить, почта, ключ), timeout=40)
        логи.info("POCHTA: письмо ушло на %s", почта)
        return JSONResponse({"ok": True})
    except asyncio.TimeoutError:
        логи.error("POCHTA: не дождались отправки на %s", почта)
        return JSONResponse({"ok": False, "reason": "timeout"}, status_code=504)
    except Exception as e:
        логи.error("POCHTA: %s %s", type(e).__name__, str(e)[:200])
        return JSONResponse({"ok": False, "reason": "send_failed"}, status_code=502)


@роутер.get("/api/mail-health")
async def здоровье():
    """Проверка: настроено ли всё. Пароли наружу не отдаём."""
    return JSONResponse({
        "ok": True,
        "сервер": СЕРВЕР,
        "порт": ПОРТ,
        "ящик_задан": bool(ЯЩИК),
        "пароль_задан": bool(ПАРОЛЬ),
        "пропуск_задан": bool(ПРОПУСК),
        "от_кого": ОТ,
    })


# ═══════════════════════════════════════════════════════════════
#  ТЕКСТ ПИСЬМА
# ═══════════════════════════════════════════════════════════════

ПРОСТЫМ = """Payment received. Thank you.

YOUR ACCESS KEY: {{KEY}}

What now:
1. Open Luck Forecast on your phone
2. On the screen where you enter your birth data, scroll to the bottom -
   there you will find "Full version" with a small lock
3. Tap it, paste the key and tap Activate

The full version opens at once: the month arrows come alive
and the golden days of the year appear.

Activation needs the internet once. After that the app works offline.
Your key works on two devices.
Keep this email - the key is your proof of purchase.

Questions: vlad@quantareon.com
quantareon.com/luck"""


НАРЯДНЫМ = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Your Luck Forecast key</title></head>
<body style="margin:0; padding:0; background:#0a0e27;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0a0e27;">
<tr><td align="center" style="padding:0;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"
       style="width:600px; max-width:600px; background:#0f1729;">

  <tr><td style="padding:0; background:#0a0e27;">
    <img src="https://quantareon.com/mail/shapka.png" width="600" alt=""
         style="display:block; width:100%; max-width:600px; height:auto; border:0;">
  </td></tr>

  <tr><td style="padding:38px 40px 0 40px; text-align:center;">
    <div style="font-family:Georgia,'Times New Roman',serif; font-size:27px; color:#f0e6d2; line-height:1.25;">Luck Forecast</div>
    <div style="font-family:Georgia,'Times New Roman',serif; font-size:17px; color:rgba(240,230,210,0.72); padding-top:5px;">Full Version</div>
    <div style="font-family:Georgia,'Times New Roman',serif; font-size:11px; color:#a855f7; letter-spacing:3px; padding-top:14px; text-transform:uppercase;">QUANTAREON&nbsp;LABS</div>
  </td></tr>

  <tr><td style="padding:32px 40px 0 40px; text-align:center; font-family:Georgia,'Times New Roman',serif; font-size:16px; color:#e8e4dc; line-height:1.7;">
    Payment received. Thank you.
  </td></tr>

  <tr><td style="padding:26px 40px 0 40px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#151a35; border:1px solid #4a3c1a;">
      <tr><td align="center" style="padding:26px 16px 24px 16px;">
        <div style="font-family:Georgia,'Times New Roman',serif; font-size:11px; color:rgba(232,228,220,0.55); letter-spacing:2.5px; text-transform:uppercase; padding-bottom:16px;">Your access key</div>
        <div style="font-family:'Courier New',Courier,monospace; font-size:25px; color:#e8bd6a; letter-spacing:2px; word-break:break-all;">{{KEY}}</div>
      </td></tr>
    </table>
  </td></tr>

  <tr><td style="padding:34px 40px 0 40px;">
    <div style="font-family:Georgia,'Times New Roman',serif; font-size:11px; color:#c9993f; letter-spacing:2.5px; text-transform:uppercase; padding-bottom:16px;">What now</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr>
        <td width="30" valign="top" style="font-family:Georgia,serif; font-size:14px; color:#c9993f; padding:0 0 14px 0;">1.</td>
        <td valign="top" style="font-family:Georgia,'Times New Roman',serif; font-size:15px; color:#e8e4dc; line-height:1.65; padding:0 0 14px 0;">Open Luck Forecast on your phone</td>
      </tr>
      <tr>
        <td width="30" valign="top" style="font-family:Georgia,serif; font-size:14px; color:#c9993f; padding:0 0 14px 0;">2.</td>
        <td valign="top" style="font-family:Georgia,'Times New Roman',serif; font-size:15px; color:#e8e4dc; line-height:1.65; padding:0 0 14px 0;">On the screen where you enter your birth data, scroll to the bottom &mdash; there you will find <b style="color:#f0e6d2;">Full version</b> with a small lock</td>
      </tr>
      <tr>
        <td width="30" valign="top" style="font-family:Georgia,serif; font-size:14px; color:#c9993f; padding:0 0 14px 0;">3.</td>
        <td valign="top" style="font-family:Georgia,'Times New Roman',serif; font-size:15px; color:#e8e4dc; line-height:1.65; padding:0 0 14px 0;">Tap it, paste the key and tap <b style="color:#f0e6d2;">Activate</b></td>
      </tr>
    </table>
  </td></tr>

  <tr><td style="padding:12px 40px 0 40px; font-family:Georgia,'Times New Roman',serif; font-size:15px; color:rgba(232,228,220,0.72); line-height:1.7;">
    The full version opens at once: the month arrows come alive and the golden days of the year appear.
  </td></tr>

  <tr><td style="padding:26px 40px 0 40px; font-family:Georgia,'Times New Roman',serif; font-size:13px; color:rgba(232,228,220,0.5); line-height:1.7;">
    Activation needs the internet once. After that the app works offline.<br>
    Your key works on two devices.<br>
    Keep this email &mdash; the key is your proof of purchase.
  </td></tr>

  <tr><td style="padding:34px 40px 40px 40px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr><td style="border-top:1px solid rgba(255,255,255,0.09); font-size:0; line-height:0; height:1px;">&nbsp;</td></tr>
    </table>
    <div style="font-family:Georgia,'Times New Roman',serif; font-size:13px; color:rgba(232,228,220,0.42); line-height:1.8; padding-top:20px;">
      Questions: <a href="mailto:vlad@quantareon.com" style="color:#a855f7; text-decoration:none;">vlad@quantareon.com</a><br>
      <a href="https://quantareon.com/luck" style="color:#a855f7; text-decoration:none;">quantareon.com/luck</a>
    </div>
  </td></tr>

</table>
</td></tr></table>
</body></html>"""
