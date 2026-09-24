#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Пересборка дистрибутива из исходника перевода.

    python3 tools/build_dist.py            # собрать dist/ и AULA_F75_RU_installer.zip
    python3 tools/build_dist.py --check     # только сверить, что dist/ совпадает с пересборкой

Исходники:
  tools/text_en_reference.xml   — эталон структуры (языковой файл английской сборки)
  tools/ru.json                 — перевод: тег -> русская строка (правь его, не XML)

Правила, которые обеспечивает сборщик:
  * порядок и состав тегов берутся из эталона 1:1, ничего не добавляется и не переставляется;
  * тегов нет в переводе -> остаются как в эталоне (пустые так и остаются пустыми);
  * экранируются & < > ; \r\n внутри значения пишется физически, а не сущностью;
  * текст переводится по ПОСЛЕДНЕМУ вхождению тега (в EN-файле есть вставленный дубль-блок,
    его корректные подписи — вторые вхождения);
  * dist/text_ru.xml — дубль-блок вырезан; dist/text_ru_full.xml — сохранён как в эталоне.
"""
import io
import json
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REF = os.path.join(HERE, 'text_en_reference.xml')
SRC = os.path.join(HERE, 'ru.json')
DIST = os.path.join(ROOT, 'dist')
ZIP = os.path.join(ROOT, 'AULA_F75_RU_installer.zip')
STRAY = tuple(f'tc_yun{i}' for i in range(1, 11))      # вставленный в EN дубль-блок


def load(path):
    return io.open(path, 'rb').read().decode('utf-16')


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def build(ref_text, ru):
    seen = set()

    def repl(m):
        tag = m.group(1)
        if tag not in ru:
            return m.group(0)
        # первые вхождения tc_yun1..10 — это мусор из EN-сборки: значения берём из перевода
        # как есть, но колонки списка подписываем коротко (см. ru.json: __short__)
        val = ru[tag]
        if tag in STRAY and tag not in seen and f'{tag}__short' in ru:
            val = ru[f'{tag}__short']
        seen.add(tag)
        return f'<{tag}>{esc(val)}</{tag}>'

    return re.sub(r'<(tc_[A-Za-z0-9_]+)>(.*?)</\1>', repl, ref_text, flags=re.S)


def strip_stray(full_text):
    """вырезать вставленный блок tc_yun1..tc_yun10, если он идёт раньше нормального"""
    first = full_text.find('<tc_yun1>')
    nxt = full_text.find('<tc_macro_msg1>')
    if first == -1 or nxt == -1 or first > nxt:
        return full_text
    start = full_text.rfind('\r\n', 0, first)
    end = full_text.rfind('\r\n', 0, nxt)
    return full_text[:start] + full_text[end:]


def write_u16(path, text):
    with open(path, 'wb') as f:
        f.write(b'\xff\xfe' + text.encode('utf-16-le'))


def main():
    check = '--check' in sys.argv
    ref = load(REF)
    ru = json.load(io.open(SRC, encoding='utf-8'))
    full = build(ref, ru)
    clean = strip_stray(full)

    want = {'text_ru.xml': clean, 'text_ru_full.xml': full}
    if check:
        bad = []
        for name, txt in want.items():
            p = os.path.join(DIST, name)
            if not os.path.exists(p):
                bad.append(f'{name}: файла нет')
            elif load(p) != txt:
                bad.append(f'{name}: расходится с пересборкой')
        if bad:
            print('РАСХОЖДЕНИЯ:\n  ' + '\n  '.join(bad))
            return 1
        print('dist/ совпадает с пересборкой из tools/ru.json')
        return 0

    os.makedirs(DIST, exist_ok=True)
    for name, txt in want.items():
        write_u16(os.path.join(DIST, name), txt)
    io.open(os.path.join(DIST, 'text_ПРЕВЬЮ_utf8.xml'), 'w', encoding='utf-8').write(clean)
    tags = len(re.findall(r'<tc_[A-Za-z0-9_]+>', clean))
    filled = sum(1 for v in re.findall(r'<tc_[A-Za-z0-9_]+>(.*?)</tc_[A-Za-z0-9_]+>', clean, re.S) if v.strip())
    print(f'dist/ пересобран: {tags} тегов, {filled} заполнено, дубль-блок вырезан')

    files = ['УСТАНОВИТЬ.bat', 'undo.bat', 'text_ru.xml', 'text_ru_full.xml', 'text_ПРЕВЬЮ_utf8.xml',
             'table_EN_RU.md', 'README.md', 'КУДА_СТАВИТЬ.md', 'FN_шпаргалка.md']
    with zipfile.ZipFile(ZIP, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in files:
            p = os.path.join(DIST, f)
            if os.path.exists(p):
                z.write(p, 'AULA_F75_RU/' + f)
    print(f'архив: {os.path.basename(ZIP)}  {os.path.getsize(ZIP)} байт')
    return 0


if __name__ == '__main__':
    sys.exit(main())
