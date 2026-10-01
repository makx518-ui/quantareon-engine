"""Conservative, identity-bound checks of explicit natal claims.

No section topic, previous pronoun or neighbouring ruler is treated as an owner.
An invalid explicit claim is replaced as a whole: changing only an aspect name
would leave its incorrect interpretation in place. Ambiguous prose is not guessed.
This checks recognizable factual claims, not the truth of an interpretation.
"""
import re

from engine import storozh_faktov as SF
from engine import sverka as SV
from engine.machine_natal import library


def _owner(before, attribute=None):
    mentions = SF._упоминания(before)
    if attribute:
        labels = list(re.finditer(attribute, before, re.I))
        if labels:
            tail = before[labels[-1].end():]
            owners = SF._упоминания(tail)
            if owners and not tail[:owners[0][0]].strip(' :—–-'):
                return owners[0][2]
    # A nominative subject cannot own every later coordinate: a sentence may
    # also give its ruler or aspect partner's position in an oblique case.
    # Without an explicit attribute label, require exactly one named point.
    if len({m[2] for m in mentions}) != 1:
        return None
    subjects = [m[2] for m in mentions if SF._подлежащее(before, m) and not re.search(
        r'(?:диспозитор|хозяин|управитель|направляет|управляет)[^.;!?]*$', before[:m[0]], re.I)]
    unique = set(subjects)
    return next(iter(unique)) if len(unique) == 1 else None


def _point_basis(p):
    data = library()
    return (f"{p['name']} — {p['position']}" + (f", дом {p['house']}" if p.get('house') else '') + '. '
            + data['functions'][p['name']]['theme'].capitalize()+'. '
            + f"Смысл собственного градуса: {p['code']['действие']}")


def _aspect_basis(row, machine):
    data = library()
    a, b = machine['points'][row['A']], machine['points'][row['B']]
    link = f"{a['name']} — {b['name']}: {row['kind']}. "
    if not row['direct']:
        link += 'Это связь через соединение, а не самостоятельный прямой аспект. '
    return (link+data['aspects'][row['kind']]['principle']+' '
            + f"Задача собственного градуса {a['name']}: {a['code']['действие']} "
            + f"Задача собственного градуса {b['name']}: {b['code']['действие']}")


def check(text, machine):
    """Return repaired prose and an owner report; never call an LLM or old guard."""
    points = machine['points']
    aspects = {frozenset((r['A'], r['B'])): r for r in machine['aspects']}
    parts = SF._предложения(text)
    changes = []
    for i in range(0, len(parts), 2):
        sentence = parts[i]
        if not sentence.strip() or SF._ЗАГОЛОВОК.match(sentence):
            continue
        replacement, reason = None, None
        for match in SF.Сторож._КОД.finditer(sentence):
            owner = _owner(sentence[:match.start()], r'код(?:\s+(?:жизни|градуса))?')
            if owner in points and match.group(1).strip() != points[owner]['code']['tag']:
                replacement = _point_basis(points[owner])
                reason = f"{owner}: неверный код — фрагмент заменён собственным машинным основанием"
                break
        if replacement is None:
            for match in SF.Сторож._ДИСП.finditer(sentence):
                owner = _owner(sentence[:match.start()])
                if owner in points and match.group(1) != points[owner]['ruler']:
                    replacement = _point_basis(points[owner])+f" Диспозитор — {points[owner]['ruler']}."
                    reason = f"{owner}: неверный диспозитор — фрагмент восстановлен по машине"
                    break
        if replacement is None:
            claims = list(SF._АСП_ВЫР.finditer(sentence))
            mentions = SF._упоминания(sentence)
            names = list(dict.fromkeys(m[2] for m in mentions))
            # Three names / several aspect words require syntactic interpretation:
            # do not silently reassign Mercury's opposition to MC's sextile.
            if len(claims) == 1 and len(names) == 2:
                match = claims[0]
                before = sentence[max(0, match.start()-35):match.start()]
                negative = re.search(r'\b(?:нет|без|не|если|возможно)\b', before, re.I)
                kind = SF._АСП_ФОРМА[match.group(1).lower()][0]
                row = aspects.get(frozenset(names))
                explicit = (any(SF._подлежащее(sentence, m) for m in mentions) or
                            re.search(r'\bмежду\b', sentence, re.I) or '↔' in sentence)
                if not negative and explicit and (row is None or kind != row['kind']):
                    replacement = _aspect_basis(row, machine) if row else ''
                    reason = '–'.join(names)+(': неверный аспект — фрагмент восстановлен по машине'
                                             if row else ': неподтверждённый аспект — фрагмент удалён')
                elif not negative and explicit and row and not row['exact'] and re.search(r'\bточн\w*', sentence, re.I):
                    replacement = re.sub(r'\bточн\w*\s*', '', sentence, flags=re.I)
                    reason = '–'.join(names)+f": слово «точный» убрано (орб {row['orb']:.2f}°)"
        if replacement is None:
            # Only an explicitly named owner before a DMS coordinate. No
            # inherited section topic, approximate degree or symbolic ordinal.
            coordinate = re.compile(r'(\d{1,2})°(\d{1,2})[′\'](?:\d{1,2}[″\"])?\s*('
                                    +SV.ЗНАК_ЛЮБОЙ+r')[а-яё]{0,3}', re.I)
            for match in coordinate.finditer(sentence):
                owner = _owner(sentence[:match.start()])
                if owner in ('ASC', 'MC') and owner not in points:
                    replacement = 'При неизвестном времени рождения углы карты не определяются.'
                    reason = f"{owner}: выдуманная координата угла убрана при неизвестном времени"
                    break
                if owner not in points:
                    continue
                p = points[owner]
                actual = p['longitude'] % 30
                degree, minute = int(match.group(1)), int(match.group(2))
                sign = SV._имен(match.group(3)[:1].upper()+match.group(3)[1:].lower())
                # A printed minute is rounded by some sources and truncated by
                # others; accept both, but never a different degree/sign.
                if sign != p['sign'] or degree != int(actual) or abs(minute-(actual%1)*60) > 1.01:
                    replacement = _point_basis(p)
                    reason = f"{owner}: неверная координата — фрагмент восстановлен по машине"
                    break
        if replacement is None:
            for match in re.finditer(r'\bв\s+(\d{1,2}|'+SF._ПОРЯДК+r')\s+доме\b', sentence, re.I):
                owner = _owner(sentence[:match.start()])
                if owner not in points:
                    continue
                raw = match.group(1).lower()
                house = int(raw) if raw.isdigit() else SF._ДОМ_ЧИСЛО[raw]
                if house != points[owner].get('house'):
                    replacement = _point_basis(points[owner])
                    reason = f"{owner}: неверный или неизвестный дом — фрагмент восстановлен по машине"
                    break
        if replacement is not None and replacement != sentence:
            parts[i] = replacement
            changes.append(reason)
    return ''.join(parts), changes
