#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Собирает tools/text_en_reference.xml — структуру-эталон для тестов.

В репозитории оригинального `text.xml` из программы нет (это файл OEM-сборки). Эталон
восстанавливается из нашего же dist/text_ru_full.xml: он построен 1:1 по английскому
оригиналу, поэтому порядок и состав тегов в нём — и есть порядок из сборки. Подмениваем
русские значения на короткие ASCII-заглушки, чтобы тесты сравнивали структуру, а не текст.

    python3 tools/make_reference.py
"""
import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), 'dist', 'text_ru_full.xml')
OUT = os.path.join(HERE, 'text_en_reference.xml')

t = io.open(SRC, 'rb').read().decode('utf-16')


def fill(m):
    # пустой тег у нас = пустой и в эталоне (это перенос из оригинала)
    return m.group(0) if not m.group(2).strip() else f'<{m.group(1)}>x</{m.group(1)}>'


t = re.sub(r'<(tc_[A-Za-z0-9_]+)>(.*?)</\1>', fill, t, flags=re.S)
io.open(OUT, 'wb').write(b'\xff\xfe' + t.encode('utf-16-le'))
print('готово:', os.path.basename(OUT), os.path.getsize(OUT), 'байт | тегов:',
      len(re.findall(r'<tc_[A-Za-z0-9_]+>', t)), '| уникальных:',
      len(set(re.findall(r'<tc_[A-Za-z0-9_]+>', t))))
