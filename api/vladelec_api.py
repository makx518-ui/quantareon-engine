# -*- coding: utf-8 -*-
"""28.09 · РЕЖИМ ВЛАДЕЛЬЦА на razbor-ru (админ-ссылка #admin=…): правка готового гороскопа и
отправка файла на любую почту.

Его слово: «мне заказали гороскоп мимо сайта — я сделал, посмотрел, подредактировал, ввёл почту
клиента и сразу отправил». Только с ключом владельца (QUANTAREON_ADMIN_KEY на Render, та же
проверка, что у бесплатного заказа в кассе). Клиент эти двери не видит, а без ключа они отвечают 403.

POST /api/vladelec/pravka    {admin, klyuch, html}               — сохранить правку (QN- классика, QS- срок);
                                                                  прежняя версия ложится рядом
POST /api/vladelec/otpravit  {admin, pochta, html, imya_fayla}   — письмо с HTML-файлом на любую почту
"""
import re
import time

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

роутер = APIRouter()
_КЛЮЧ = re.compile(r"(Q[NS])-([0-9A-F]{4})-([0-9A-F]{4})-([0-9A-F]{4})-([0-9A-F]{4})")
_ПОЧТА = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
ПРЕДЕЛ = 6_000_000          # символов HTML — гороскоп весит сотни килобайт, запас большой


def _владелец(ключ):
    import oplata_api as O
    return O._владелец(str(ключ or ""))


def _чисто(html):
    """Следы правки в файл не идут: клиент не должен получить возможность править свой гороскоп."""
    html = re.sub(r'\s(contenteditable|spellcheck)="[^"]*"', "", html)
    html = re.sub(r'<div class="pravka">.*?</div>\s*(<script>.*?</script>)?', "", html, flags=re.S)
    return html


def _модуль(вид):
    if вид == "QN":
        import klassika_api as M
    else:
        import srok_api as M
    return M


def _сохранить(ключ, html):
    м = _КЛЮЧ.fullmatch(ключ.strip().upper())
    if not м:
        return {"ok": False, "reason": "bad_key"}, 400
    вид, номер = м.group(1), "".join(м.groups()[1:]).lower()
    M = _модуль(вид)
    к = M._карточка(номер)
    if not к or к.get("состояние") != "готово":
        return {"ok": False, "reason": "not_ready"}, 404
    from engine import arhiv as A
    путь = f"{M._префикс()}/{номер}/итог.html"
    было = A._взять(путь) or ""
    if было:
        M._в_облако(f"{M._префикс()}/{номер}/итог__было-{time.strftime('%Y%m%d-%H%M%S')}.html",
                    было, "text/html; charset=utf-8")
    M._в_облако(путь, html, "text/html; charset=utf-8")
    зд = M.ЗАДАЧИ.get(номер)
    if зд is not None and зд.get("gotovo"):
        зд["html"] = html
    # копия в «Истории разборов» (классика её помнит) — тоже правленая
    if к.get("arhiv"):
        try:
            A._положить(к["arhiv"], html, "text/html; charset=utf-8")
        except Exception as e:
            print(f"владелец: копия в истории не обновилась: {e}")
    return {"ok": True}, 200


@роутер.post("/api/vladelec/pravka")
async def pravka(request: Request):
    try:
        т = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "reason": "bad_request"}, status_code=400)
    if not _владелец(т.get("admin")):
        return JSONResponse({"ok": False, "reason": "locked"}, status_code=403)
    html = str(т.get("html") or "")
    if "<html" not in html.lower() or len(html) > ПРЕДЕЛ:
        return JSONResponse({"ok": False, "reason": "bad_html"}, status_code=400)
    ответ, код = await run_in_threadpool(_сохранить, str(т.get("klyuch") or ""), _чисто(html))
    return JSONResponse(ответ, status_code=код)


@роутер.post("/api/vladelec/otpravit")
async def otpravit(request: Request):
    try:
        т = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "reason": "bad_request"}, status_code=400)
    if not _владелец(т.get("admin")):
        return JSONResponse({"ok": False, "reason": "locked"}, status_code=403)
    почта = str(т.get("pochta") or "").strip()[:200]
    if not _ПОЧТА.match(почта):
        return JSONResponse({"ok": False, "reason": "bad_mail"}, status_code=400)
    html = str(т.get("html") or "")
    if "<html" not in html.lower() or len(html) > ПРЕДЕЛ:
        return JSONResponse({"ok": False, "reason": "bad_html"}, status_code=400)
    имя = re.sub(r'[\\/:*?"<>|\r\n]+', " ", str(т.get("imya_fayla") or "Квантареон.html")).strip()[:120]
    if not имя.lower().endswith(".html"):
        имя += ".html"
    название = имя[:-5].split(" · ")[0] or "Разбор"
    тема = f"{название} · Квантареон"
    текст = (f"{название} — во вложении к этому письму. Откройте файл в любом браузере: "
             f"на телефоне или на компьютере.\n\nКвантареон")
    import pochta as П
    ушло = await run_in_threadpool(П.отправить_файл, почта, тема, текст, имя, _чисто(html))
    if not ушло:
        return JSONResponse({"ok": False, "reason": "mail_failed"}, status_code=502)
    try:
        import oplata_api as O
        O._в_телеграм(f"📨 Владелец отправил файл «{имя}» на {почта}")
    except Exception:
        pass
    return {"ok": True}
