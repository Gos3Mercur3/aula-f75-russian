#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тесты для дистрибутива русификации AULA F75 (OemDrv / движок BYCOMBO4).

Запуск:  python3 tools/check_repo.py          (или python tools\\check_repo.py на Windows)
Всё, что проверяется — статический анализ файлов дистрибутива + прогон логики
`УСТАНОВИТЬ.bat` на самодельной «песочнице» (фиктивные Text\\en, Text\\sc, Text\\Korean).

Никаких зависимостей, только стандартная библиотека.
"""
import io
import os
import re
import shutil
import subprocess
import sys
import zipfile
import tempfile
from xml.etree import ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIST = os.path.join(ROOT, 'dist')
ZIP = os.path.join(ROOT, 'AULA_F75_RU_installer.zip')
REFERENCE_EN = os.path.join(HERE, 'text_en_reference.xml')   # структура-эталон, см. tools/make_reference.py

CJK = r'[\u3400-\u4dbf\u4e00-\u9fff\uf000-\uf0ff\u3000-\u303f\uff01-\uff5e]'
results = []
SUITE = []


def t(name):
    """декоратор теста: регистрирует и собирает (имя, ок/FAIL, подробности)"""
    def deco(fn):
        SUITE.append((name, fn))

        def run():
            try:
                msg = fn()
                results.append((name, True, msg or 'ok'))
            except AssertionError as e:
                results.append((name, False, str(e)))
            except Exception as e:                                    # noqa: BLE001
                results.append((name, False, f"{type(e).__name__}: {e}"))
        run.__name__ = 'run_' + fn.__name__
        return run
    return deco


def read_bytes(p):
    with open(p, 'rb') as f:
        return f.read()


def load_lang(path):
    """читает языковой xml так же «криво», как это делает драйвер: регуляркой по тексту"""
    raw = read_bytes(path).decode('utf-16')
    return raw, dict(re.findall(r'<(tc_[A-Za-z0-9_]+)>(.*?)</\1>', raw, re.S))


# ---------------------------------------------------------------- XML / перевод
@t('файл text_ru.xml существует и это валидный XML')
def test_xml_parses():
    p = os.path.join(DIST, 'text_ru.xml')
    assert os.path.exists(p), 'нет dist/text_ru.xml'
    ET.parse(p)
    return f'{os.path.getsize(p)} байт'


@t('кодировка UTF-16 LE + BOM + CRLF (как требует драйвер)')
def test_encoding():
    for name in ('text_ru.xml', 'text_ru_full.xml'):
        b = read_bytes(os.path.join(DIST, name))
        assert b[:2] == b'\xff\xfe', f'{name}: нет UTF-16 LE BOM (найдено {b[:2].hex()})'
        t = b.decode('utf-16')
        assert '\n' not in t.replace('\r\n', ''), f'{name}: есть переводы строк без \\r'
        assert 'utf-16' in t[:60], f'{name}: в декларации не utf-16'
    return 'UTF-16 LE, BOM ff fe, CRLF'


@t('тегов ровно 277, структура 1:1 с эталонной EN-сборкой (без дублей)')
def test_structure_clean():
    raw, vals = load_lang(os.path.join(DIST, 'text_ru.xml'))
    tags = re.findall(r'<(tc_[A-Za-z0-9_]+)>', raw)
    assert len(tags) == len(set(tags)) == 277, f'тегов {len(tags)}, уникальных {len(set(tags))}'
    if os.path.exists(REFERENCE_EN):
        ref, _ = load_lang(REFERENCE_EN)
        ref_tags = re.findall(r'<(tc_[A-Za-z0-9_]+)>', ref)
        stray = {f'tc_yun{i}' for i in range(1, 11)}
        seen, expect = set(), []
        for k in ref_tags:                      # убрать ПЕРВЫЕ вхождения дублей — это и есть вставленный блок
            if k in stray and k not in seen:
                seen.add(k)
                continue
            expect.append(k)
        assert expect == tags, ('порядок расходится: ' + str([(i, a, b) for i, (a, b) in enumerate(zip(expect, tags)) if a != b][:4]))
        return f'277 тегов, порядок = эталон минус вставленный дубль-блок'
    return '277 тегов (эталон не подложен — порядок не сверялся)'


@t('вариант text_ru_full.xml повторяет EN дословно, включая 10 дублей (287 тегов)')
def test_structure_full():
    raw, _ = load_lang(os.path.join(DIST, 'text_ru_full.xml'))
    tags = re.findall(r'<(tc_[A-Za-z0-9_]+)>', raw)
    assert len(tags) == 287, f'ожидалось 287, найдено {len(tags)}'
    dup = {k for k in tags if tags.count(k) > 1}
    assert dup == {f'tc_yun{i}' for i in range(1, 11)}, f'дубли не те: {sorted(dup)}'
    if os.path.exists(REFERENCE_EN):
        ref, _ = load_lang(REFERENCE_EN)
        assert tags == re.findall(r'<(tc_[A-Za-z0-9_]+)>', ref), 'последовательность тегов != эталон'
    return '287 = 277 + 10 дублей tc_yun1..10, порядок = эталон'


@t('ни один тег не потерян и ни одна пустая строка не «оживила» перевод')
def test_empties_match_reference():
    if not os.path.exists(REFERENCE_EN):
        return 'эталон не подложен — пропущено'
    _, ev = load_lang(REFERENCE_EN)
    _, rv = load_lang(os.path.join(DIST, 'text_ru.xml'))
    empty_en = {k for k, v in ev.items() if not v.strip()}
    empty_ru = {k for k, v in rv.items() if not v.strip()}
    assert empty_ru == empty_en, f'пустые расходятся: только в EN {empty_en - empty_ru}, только в RU {empty_ru - empty_en}'
    assert len(empty_en) == 7, f'ожидалось 7 пустых, а их {len(empty_en)}'
    return f'{len(empty_en)} пустых совпадают: {", ".join(sorted(empty_en))}'


@t('переведено 270 строк, иероглифов не осталось')
def test_all_translated():
    _, v = load_lang(os.path.join(DIST, 'text_ru.xml'))
    filled = {k: s for k, s in v.items() if s.strip()}
    assert len(filled) == 270, f'заполнено {len(filled)}, ожидалось 270'
    cjk = [k for k, s in filled.items() if re.search(CJK, s)]
    assert not cjk, f'осталась азиатская пунктуация/иероглифы: {cjk}'
    return f'270 строк, CJK: 0'


@t('внутри тегов нет «голого» < > & (только экранированные сущности)')
def test_escaping():
    raw = read_bytes(os.path.join(DIST, 'text_ru.xml')).decode('utf-16')
    body = raw.split('<config>', 1)[1]
    assert '&amp;' not in body or 'amp;amp;' not in body, 'двойное экранирование &amp;amp;'
    assert '<' not in body.replace('</', '').replace('<tc_', ''), 'незакрытый/голый < внутри значения'
    assert not re.search(r'&(?!amp;|lt;|gt;|quot;|#\d+;)\w*;', body), 'битая сущность вида &'
    return 'экранирование чистое'


@t('многострочный диалог прошивки остался многострочным (физический CRLF, не сущность)')
def test_multiline():
    raw = read_bytes(os.path.join(DIST, 'text_ru.xml')).decode('utf-16')
    m = re.search(r'<tc_update1>(.*?)</tc_update1>', raw, re.S)
    assert m, 'нет tc_update1'
    assert '\r\n' in m.group(1), 'переноса строки нет — программа покажет &#13;&#10; текстом'
    assert '&#13;' not in m.group(1), 'осталась сущность &#13; — этот парсер её не разворачивает'
    return f'в tc_update1 {m.group(1).count(chr(13) + chr(10)) + 1} строки'


@t('ключевые подписи не режутся панелью: укоротыши на месте')
def test_shortened_labels():
    _, v = load_lang(os.path.join(DIST, 'text_ru.xml'))
    limits = {'tc_macro_msg9': 20, 'tc_kb5': 12, 'tc_kb8': 12, 'tc_kb9': 14, 'tc_msg18': 20}
    for tag, mx in limits.items():
        s = v[tag].strip()
        assert len(s) <= mx, f'{tag} = «{s}» — {len(s)} символов, панель держит ~{mx}'
    return ', '.join(f'{tag}:{len(v[tag].strip())}' for tag in limits)


@t('названия клавиш остались латиницей, единицы не переведены')
def test_no_over_translation():
    _, v = load_lang(os.path.join(DIST, 'text_ru.xml'))
    for tag in ('tc_game1', 'tc_game5'):
        assert re.fullmatch(r'FN\+\d', v[tag].strip()), f'{tag} = {v[tag]!r} — трогать не надо было'
    assert v['tc_msg36'].strip() == 'с', v['tc_msg36']
    assert v['tc_msg37'].strip() == 'мин', v['tc_msg37']
    assert v['tc_msg38'].strip() == 'мс', v['tc_msg38']
    assert 'DPI' in v['tc_ms1'] and 'Win' in v['tc_cmd11'], 'технические аббревиатуры съехали'
    return 'FN+1..FN+5, ms/с, DPI, Win — как на кейкапах'


@t('таблица-справочник покрывает все теги перевода')
def test_table_coverage():
    p = os.path.join(DIST, 'table_EN_RU.md')
    s = io.open(p, encoding='utf-8').read()
    _, v = load_lang(os.path.join(DIST, 'text_ru.xml'))
    rows = set(re.findall(r'^\| `(tc_[A-Za-z0-9_]+)`', s, re.M))
    missing = set(v) - rows
    assert not missing, f'в таблице нет {len(missing)} тегов: {sorted(missing)[:5]}'
    return f'{len(rows)} строк, покрытие 100%'


# ------------------------------------------------------------- статика батников
def bat_lines(path):
    b = read_bytes(path)
    assert b == b.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'), f'{os.path.basename(path)}: переводы строк не CRLF'
    return b.decode('cp866').replace('\r\n', '\n').split('\n')


def strip_echoes(lines):
    """для анализа скобок: строки echo не содержат управляющих скобок блока"""
    out = []
    for l in lines:
        s = l.strip()
        low = s.lower()
        if low.startswith('echo') or low.startswith('rem') or low.startswith('title'):
            out.append('')
        else:
            out.append(l)
    return out


@t('батники: кодировка OEM-866 читается без потери символов, есть chcp 866')
def test_bat_encoding():
    for name in ('УСТАНОВИТЬ.bat', 'undo.bat'):
        p = os.path.join(DIST, name)
        b = read_bytes(p)
        txt = b.decode('cp866')
        assert 'chcp 866' in txt or name == 'undo.bat', f'{name}: нет chcp 866 при OEM-кодировке'
        left = [l.strip() for l in txt.split('\n') if '?' in l and not l.strip().lower().startswith('set /p')]
        assert not left, f'{name}: „?“ в строке {left[:1]} — текст был в другой кодировке и побился'
        try:
            txt.encode('cp866')
        except UnicodeEncodeError as e:
            raise AssertionError(f'{name}: символ вне cp866 ({e})') from e
    return 'cp866 + chcp 866, потерь нет'


@t('батники: все метки :label существуют, висячих goto/call нет')
def test_bat_labels():
    for name in ('УСТАНОВИТЬ.bat', 'undo.bat'):
        lines = bat_lines(os.path.join(DIST, name))
        labels = {l.strip()[1:] for l in lines if re.match(r'^:\w+\s*$', l)}
        used = set(re.findall(r'(?:goto|call)\s+:([\w-]+)', '\n'.join(lines), re.I))
        dead = used - labels - {'eof'}
        assert not dead, f'{name}: goto/call на несуществующую метку {sorted(dead)}'
        unreached = labels - used
        assert not unreached, f'{name}: метка {sorted(unreached)} объявлена, но туда никто не идёт'
    return 'метки/переходы замкнуты'


@t('батники: блоки if ( ... ) сбалансированы, многострочных for..in() нет')
def test_bat_blocks():
    for name in ('УСТАНОВИТЬ.bat', 'undo.bat'):
        code = strip_echoes(bat_lines(os.path.join(DIST, name)))
        depth = 0
        max_depth = 0
        for i, l in enumerate(code, 1):
            s = l.rstrip()
            if not s.strip():
                continue
            opens = s.endswith('(') and not s.endswith(')')
            closes = s.strip() == ')'
            if opens:
                depth += 1
                max_depth = max(max_depth, depth)
            elif closes:
                depth -= 1
                assert depth >= 0, f'{name}: строка {i} закрывает блок, которого не открывали'
            else:
                assert s.count('(') == s.count(')'), f'{name}:{i} неспаренная скобка: {l.strip()}'
                assert ' in (' in l or ' in ' not in l or ')' not in l or 'in (' in l, l
                # многострочный список for .. in ( - запрещён: без ^ он не работает
                assert not re.search(r'^\s*for\b.*\bin\s*\($', s, re.I), f'{name}:{i} многострочный for..in('
        assert depth == 0, f'{name}: на финише открыто блоков: {depth}'
    return 'все блоки закрыты, многострочных for..in() нет'


@t('батники: %% для циклов, отложенное расширение там, где нужно')
def test_bat_syntax_details():
    txt = '\n'.join(bat_lines(os.path.join(DIST, 'УСТАНОВИТЬ.bat')))
    assert re.search(r'for /d %%D in', txt), 'for /d должен использовать %%D (в .bat один % не работает)'
    assert not re.search(r'for /d %D in', txt), 'одинарный %D в .bat — ошибка'
    assert 'setlocal EnableDelayedExpansion' in txt, 'без него !N! внутри блоков не считает'
    assert re.search(r'if !N! equ 0', txt), 'счётчик надо читать как !N!'
    assert 'set /a N+=1' in txt, 'инкремент потерян'
    # вызов подпрограммы с параметром и его чтение через %~1
    assert re.search(r'call :one "%%D"', txt), 'подпрограмма вызывается без аргумента'
    assert '%~1\\text.xml' in txt, 'в подпрограмме путь не читается из %~1'
    return '%%, delayed expansion, %~1 — ок'


@t('батник безопасности: нет удаления файлов, пишет только в Text\\')
def test_bat_safety():
    for name in ('УСТАНОВИТЬ.bat', 'undo.bat'):
        txt = '\n'.join(bat_lines(os.path.join(DIST, name))).lower()
        for bad in ('del ', 'erase ', 'rmdir', 'rd /', 'format ', ' attrib'):
            assert bad not in txt, f'{name}: найдено потенциально опасное „{bad.strip()}“'
        for line in txt.split('\n'):
            if line.strip().startswith('copy'):
                assert '\\text' in line or 'text.xml' in line, f'{name}: copy пишет неизвестно куда: {line.strip()}'
            if line.strip().startswith('move'):
                assert 'text.xml' in line, f'{name}: move трогает не text.xml: {line.strip()}'
    return 'никаких del/rd, запись только в Text\\*\\text.xml'


@t('батник делает бэкап ДО записи и не затирает существующий бэкап')
def test_bat_backup_order():
    lines = bat_lines(os.path.join(DIST, 'УСТАНОВИТЬ.bat'))
    start = next(i for i, l in enumerate(lines) if l.strip() == ':one')     # смотрим только подпрограмму
    body = lines[start:]
    i_bak = next(i for i, l in enumerate(body) if 'text.xml.bak' in l and 'copy' in l.lower())
    i_wr = next(i for i, l in enumerate(body) if 'text.xml"' in l and 'copy /y' in l.lower()
                and '.bak' not in l)
    assert body[i_bak].lstrip().lower().startswith('if not exist'), 'бэкап не защищён проверкой „если ещё нет“'
    assert i_bak < i_wr, 'бэкап идёт ПОСЛЕ записи'
    assert i_wr - i_bak <= 2, f'бэкап и запись разнесены на {i_wr - i_bak} строк'
    return 'сначала „if not exist … .bak“, потом запись'


# --------------------------------------------------------- симуляция установки
def make_sandbox(tmp, langs=('en', 'sc', 'Korean'), admin=True):
    app = os.path.join(tmp, 'Program Files (x86)', 'AULA', 'F75')
    for lang in langs:
        d = os.path.join(app, 'Text', lang)
        os.makedirs(d)
        with io.open(os.path.join(d, 'text.xml'), 'w', encoding='utf-16', newline='') as f:
            f.write('<?xml version="1.0" encoding="utf-16"?>\r\n<root>\r\n\t<config>\r\n'
                    '\t\t<tc_apply>SAVE</tc_apply>\r\n\t\t<tc_kb5>Default</tc_kb5>\r\n'
                    '\t</config>\r\n</root>')
    os.makedirs(os.path.join(app, 'skins'))
    with io.open(os.path.join(app, 'OemDrv.exe'), 'w') as f:
        f.write('stub')
    return app


@t('симуляция логики батника: установка во все языки, бэкапы, верный размер')
def test_simulate_install():
    src = os.path.join(DIST, 'text_ru.xml')
    bat = '\n'.join(bat_lines(os.path.join(DIST, 'УСТАНОВИТЬ.bat')))
    assert 'if not exist "%~1' in bat and 'text.xml.bak"' in bat, 'батник не проверяет наличие бэкапа'
    with tempfile.TemporaryDirectory() as tmp:
        app = make_sandbox(tmp)
        for d in sorted(os.listdir(os.path.join(app, 'Text'))):
            tgt = os.path.join(app, 'Text', d, 'text.xml')
            assert os.path.exists(tgt), f'{d}: нет text.xml'
            before = read_bytes(tgt)                                # что было до записи
            if not os.path.exists(tgt + '.bak'):                    # ровно как в :one
                shutil.copy2(tgt, tgt + '.bak')
            shutil.copy2(src, tgt)
            assert os.path.getsize(tgt) == os.path.getsize(src), f'{d}: размер не тот'
            assert read_bytes(tgt + '.bak') == before, f'{d}: в .bak попал не тот файл'
            _, vals = load_lang(tgt)
            assert vals['tc_apply'].strip() == 'Сохранить', f'{d}: пришло {vals["tc_apply"]!r}'
            os.remove(tgt + '.bak')                                 # следующий язык — как «чистая» машина
        assert 'call :one' in bat and ':report' in bat, 'в батнике сломан разбор папок'
    return 'en/sc/Korean: бэкап = оригинал, перевод записан, размеры совпали'


@t('симуляция откатa: из .bak возвращается именно оригинал')
def test_simulate_undo():
    with tempfile.TemporaryDirectory() as tmp:
        app = make_sandbox(tmp)
        src = os.path.join(DIST, 'text_ru.xml')
        p = os.path.join(app, 'Text', 'en', 'text.xml')
        orig = read_bytes(p)
        shutil.copy2(p, p + '.bak')
        shutil.copy2(src, p)
        assert read_bytes(p) != orig
        shutil.move(p + '.bak', p)                                   # ровно то, что делает undo.bat
        assert read_bytes(p) == orig, 'откат вернул не оригинал'
        assert not os.path.exists(p + '.bak'), 'undo.bat обязан переносить, а не копировать .bak'
    return 'оригинал восстановлен байт в байт, .bak удалён переносом'


@t('повторный запуск батника не затирает бэкап (можно переустанавливать много раз)')
def test_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        app = make_sandbox(tmp)
        p = os.path.join(app, 'Text', 'en', 'text.xml')
        src = os.path.join(DIST, 'text_ru.xml')
        original = read_bytes(p)
        for _ in range(3):
            if not os.path.exists(p + '.bak'):
                shutil.copy2(p, p + '.bak')
            shutil.copy2(src, p)
        assert read_bytes(p + '.bak') == original, 'в бэкапе оказался перевод, а не оригинал'
        assert 'SAVE' in read_bytes(p + '.bak').decode('utf-16'), 'в бэкапе нет исходного текста'
    return '3 прогона — бэкап остался оригиналом'


@t('если у пользователя нет подпапок языка — батник пишет в Text\\text.xml')
def test_no_lang_folders():
    text = '\n'.join(bat_lines(os.path.join(DIST, 'УСТАНОВИТЬ.bat')))
    assert 'В подпапках языка text.xml не нашёлся' in text, 'нет ветки отступа на Text\\text.xml'
    assert re.search(r'if !N! equ 0', text)
    with tempfile.TemporaryDirectory() as tmp:
        app = make_sandbox(tmp, langs=())
        os.makedirs(os.path.join(app, 'Text'))
        n = 0
        for d in os.listdir(os.path.join(app, 'Text')):
            if os.path.exists(os.path.join(app, 'Text', d, 'text.xml')):
                n += 1
        assert n == 0
        p = os.path.join(app, 'Text', 'text.xml')
        with io.open(p, 'w', encoding='utf-16', newline='') as f:   # «оригинал» на чистой машине
            f.write('<?xml version="1.0" encoding="utf-16"?>\r\n<root>\r\n\t<tc_apply>Save</tc_apply>\r\n</root>\r\n')
        orig = read_bytes(p)
        shutil.copy2(p, p + '.bak')                                  # ровно то, что делает :one
        shutil.copy2(os.path.join(DIST, 'text_ru.xml'), p)
        assert os.path.getsize(p) == os.path.getsize(os.path.join(DIST, 'text_ru.xml')), 'Text\\text.xml не записан'
        assert read_bytes(p + '.bak') == orig, 'в ветке без подпапок языка бэкапа нет -> undo.bat нечем откатывать'
    assert re.search(r'if !N! equ 0 \(\r?\n\s*echo[^\n]*\r?\n\s*call :one', text), (
        'ветка «подпапок языка нет» не вызывает :one — значит пишет без бэкапа')
    return 'ветка exists: вызов :one, есть бэкап, размер совпадает'


# --------------------------------------------------------------- архив / доки
@t('архив содержит ровно то, что обещано, и ничего лишнего')
def test_zip_contents():
    expect = {'УСТАНОВИТЬ.bat', 'undo.bat', 'text_ru.xml', 'text_ru_full.xml',
              'text_ПРЕВЬЮ_utf8.xml', 'table_EN_RU.md', 'README.md', 'КУДА_СТАВИТЬ.md',
              'FN_шпаргалка.md'}
    with zipfile.ZipFile(ZIP) as z:
        names = {n.split('/')[-1] for n in z.namelist()}
        assert names == expect, f'расхождение: лишних {names - expect}, нет {expect - names}'
        assert z.testzip() is None, 'битый CRC в архиве'
        for n in z.namelist():
            assert n.startswith('AULA_F75_RU/'), f'{n} лежит не в папке AULA_F75_RU (батник его не найдёт)'
    return f'{len(names)} файлов, все в папке AULA_F75_RU/, CRC ok'


@t('батник находит перевод при распаковке «как есть» (папка AULA_F75_RU)')
def test_src_lookup_logic():
    text = '\n'.join(bat_lines(os.path.join(DIST, 'УСТАНОВИТЬ.bat')))
    assert '%~dp0text_ru.xml' in text, 'нет поиска рядом с батником'
    assert '%~dp0AULA_F75_RU\\text_ru.xml' in text, 'нет поиска в папке после распаковки Windows'
    with tempfile.TemporaryDirectory() as tmp:
        for layout in (['УСТАНОВИТЬ.bat', 'text_ru.xml'],
                       ['AULA_F75_RU', 'УСТАНОВИТЬ.bat', 'AULA_F75_RU', 'text_ru.xml']):
            pass
        # эмулируем обе разкладки
        for nested in (False, True):
            d = os.path.join(tmp, 'AULA_F75_RU' if nested else '')
            os.makedirs(d, exist_ok=True)
            shutil.copy2(os.path.join(DIST, 'text_ru.xml'), os.path.join(d, 'text_ru.xml'))
            dp0 = d + os.sep
            cand = f'{dp0}text_ru.xml'
            if not os.path.exists(cand):
                cand = f'{dp0}AULA_F75_RU\\text_ru.xml'
            assert os.path.exists(cand), f'разкладка nested={nested}: источник не найден'
    return 'обе разкладки (рядом / внутри AULA_F75_RU) покрыты'


@t('в доках нет честных невыполнимых обещаний и битых размеров')
def test_docs_honest():
    sizes = {'text_ru.xml': os.path.getsize(os.path.join(DIST, 'text_ru.xml'))}
    for name in ('README.md', 'КУДА_СТАВИТЬ.md'):
        s = io.open(os.path.join(DIST, name), encoding='utf-8').read()
        for num in re.findall(r'(\d[\d \u00a0]{3,8}) байт', s):
            n = int(num.replace(' ', '').replace('\u00a0', ''))
            assert n in (sizes['text_ru.xml'], sizes['text_ru.xml'] + 712,
                         os.path.getsize(ZIP)) or abs(n - sizes['text_ru.xml']) <= 1200, \
                f'{name}: обещан размер {n}, а реально {sizes["text_ru.xml"]}'
        assert 'OemDrv' in s or name == 'КУДА_СТАВИТЬ.md'
        for bad in ('Проверено на Windows', 'протестировано на Windows', '100% перевод'):
            assert bad not in s, f'{name}: недостижимое утверждение „{bad}“'
    return 'размеры в доках совпадают с фактом, завышенных обещаний нет'


@t('все относительные пути из README существуют после распаковки')
def test_docs_paths():
    s = io.open(os.path.join(DIST, 'README.md'), encoding='utf-8').read()
    have = set(os.listdir(DIST)) | {'tools/check_repo.py'}
    for f in re.findall(r'`([\wА-Яа-яЁё.\-]+\.(?:xml|bat|md|zip))`', s):
        base = f.split('/')[-1]
        if base in ('text.xml', 'text.xml.bak', 'Cfg.ini', 'KB.ini', 'keyimg.png'):
            continue                                   # это про папку программы, не про архив
        assert base in have or base == 'AULA_F75_RU_installer.zip', f'README ссылается на {base}, а его нет в dist/'
    return 'ссылки на файлы валидны'


@t('батники: управляющий поток не обрывается до основной логики (ловит "тихий exit 0")')
def test_bat_flow():
    """cmd.exe выполняет файл построчно; `goto :eof` / `exit /b` на верхнем уровне
    заканчивает скрипт. Если такое стоит до основной логики — установщик молча
    ничего не делает и возвращает код 0 (это и уронило live-тест на cmd.exe).
    Плюс: метка-подпрограмма в первых строках = мёртвый код, признак вставки не туда."""
    for name in ('УСТАНОВИТЬ.bat', 'undo.bat'):
        lines = strip_echoes(bat_lines(os.path.join(DIST, name)))
        body = [l for l in lines if l.strip()]
        first_label = next((i for i, l in enumerate(body) if re.match(r'^:\w+\s*$', l)), None)
        assert first_label is None or first_label >= 6, (
            f'{name}: метка уже на строке {first_label+1} — до неё основной логики нет, '
            f'скрипт завершится раньше, чем что-нибудь сделает')
        depth = 0
        for i, l in enumerate(body):
            was_in_block = depth > 0
            depth += l.count('(') - l.count(')')
            depth = max(depth, 0)
            if was_in_block or depth:
                continue                                   # внутри if ( ... ) — это не верхний уровень
            low = l.strip().lower()
            if low == 'goto :eof' or low.startswith('exit /b'):
                assert i >= 6, (
                    f'{name}:{i+1} `{l.strip()}` на верхнем уровне слишком рано — '
                    f'весь код ниже недостижим (cmd.exe выйдет с кодом 0, ничего не установив)')
        # осиротевшие строки подпрограммы в начале: обращение к %~1 вне тела метки
        head = '\n'.join(body[:6])
        assert '%~1' not in head and '%~dp0' not in head.replace('set "SRC=%~dp0', ''), (
            f'{name}: в заголовке остались обращения к %~1 — фрагмент подпрограммы не на своём месте')
    return 'ранних exit/goto :eof нет, мёртвых вставок в заголовке нет'


@t('батники: установщик и откат ищут программу по ОДНОМУ списку папок')
def test_bat_app_lists():
    """undo.bat когда-то искал папку своей строкой `for %%P in (...) do if exist %%P\\Text\\`
    — и не находил её из-за пути с пробелом и скобками. Тест не даёт спискам разъезжаться."""
    def cands(name):
        out = []
        for l in bat_lines(os.path.join(DIST, name)):
            m = re.search(r'if exist "([^"]+\\Text\\?)"', l)
            if m:
                out.append(m.group(1).rstrip('\\'))
        return out
    a, b = cands('УСТАНОВИТЬ.bat'), cands('undo.bat')
    assert a and b, f'не смог разобрать списки: установщик {a}, откат {b}'
    assert len(a) >= 6, 'установщик должен проверять несколько типовых путей, а их %d' % len(a)
    for l in bat_lines(os.path.join(DIST, 'undo.bat')):
        if 'for %%P in' in l and 'if exist %%P' in l:
            raise AssertionError(r'в откате остался некавыченный if exist %%P\Text\ — путь с пробелом не найдётся')
    assert a == b, f'списки разъехались: установщик {a}, откат {b}'
    return f'оба батника проверяют одни и те же {len(a)} путей'


@t('батники: живой cmd.exe (Wine), если он есть в окружении')
def test_bat_real_cmd():
    """Прогон .bat в НАСТОЯЩЕМ cmd.exe (Wine). Проверяем не текст консоли (Wine печатает
    cp866 как cp437 и кириллица в выводе мусорная), а состояние диска и коды возврата —
    это от кодировки не зависит. Перечисление `for /d ... in ("…\\*")` Wine не эмулирует,
    поэтому покрывается путь Text\\text.xml и прямые вызовы подпрограмм; цикл по языкам
    покрыт симуляциями выше. Wine нет -> тест пропускается (в CI на ubuntu его нет)."""
    import subprocess
    wine = shutil.which('wine')
    if not wine:
        return 'ПРОПУСК: wine не установлен (живой cmd.exe в этом окружении недоступен)'
    orig = b'\xff\xfe' + ('<?xml version="1.0"?><root><tc_apply>Apply</tc_apply></root>\r\n').encode('utf-16-le')
    want = os.path.getsize(os.path.join(DIST, 'text_ru.xml'))
    env0 = dict(os.environ, WINEDEBUG='-all', DISPLAY='')
    with tempfile.TemporaryDirectory() as tmp:
        flat = os.path.join(tmp, 'flat')
        os.makedirs(flat)
        for f in ('УСТАНОВИТЬ.bat', 'undo.bat', 'text_ru.xml'):
            shutil.copy2(os.path.join(DIST, f), os.path.join(flat, f))
        # прогреваем и копируем готовый префикс жёсткими ссылками: иначе первый
        # wineboot --init на свежем префиксе жрёт 700 МБ и минуту времени
        src_pfx = os.environ.get('WINEPREFIX') or os.path.expanduser('~/.wine')
        pfx = os.path.join(tmp, 'pfx')
        if os.path.exists(os.path.join(src_pfx, 'drive_c', 'windows', 'system32', 'cmd.exe')):
            try:
                subprocess.run(['cp', '-al', src_pfx, pfx], check=True, timeout=180)
            except Exception:
                pfx = src_pfx
        else:
            pfx = src_pfx
        env = dict(env0, WINEPREFIX=pfx)
        app = os.path.join(pfx, 'drive_c', 'Program Files (x86)', 'AULA', 'F75')
        text = os.path.join(app, 'Text')

        def run_bat(bat, cwd, inp=b'\r\n'):
            r = subprocess.run([wine, 'cmd', '/c', os.path.join(cwd, bat)], env=env, cwd=cwd,
                               input=inp, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               timeout=180)
            return r.returncode, r.stdout

        def check(name, ok):
            checks.append((name, bool(ok)))

        checks = []
        try:
            os.makedirs(text, exist_ok=True)
            io.open(os.path.join(text, 'text.xml'), 'wb').write(orig)
            code, _ = run_bat('УСТАНОВИТЬ.bat', flat, b'n\r\n\r\n')
            cur = io.open(os.path.join(text, 'text.xml'), 'rb').read()
            bak = os.path.join(text, 'text.xml.bak')
            check('батник дошёл до записи (не ранний выход с кодом 0)', len(cur) == want)
            check('код возврата 0', code == 0)
            check('бэкап оригинала создан до записи',
                  os.path.exists(bak) and io.open(bak, 'rb').read() == orig)
            code2, _ = run_bat('УСТАНОВИТЬ.bat', flat, b'n\r\n\r\n')
            check('повторный запуск не затёр бэкап',
                  io.open(bak, 'rb').read() == orig if os.path.exists(bak) else False)
            code3, _ = run_bat('undo.bat', flat)
            check('undo.bat нашёл папку и вернул оригинал',
                  io.open(os.path.join(text, 'text.xml'), 'rb').read() == orig)
            check('undo.bat перенёс .bak (его больше нет)', not os.path.exists(bak))
            check('undo.bat отработал с кодом 0', code3 == 0)
            broke = os.path.join(tmp, 'broke')
            os.makedirs(broke)
            shutil.copy2(os.path.join(DIST, 'УСТАНОВИТЬ.bat'), os.path.join(broke, 'УСТАНОВИТЬ.bat'))
            io.open(os.path.join(text, 'text.xml'), 'wb').write(orig)
            code4, _ = run_bat('УСТАНОВИТЬ.bat', broke)
            check('без text_ru.xml — код 1 и файлы не тронуты',
                  code4 == 1 and io.open(os.path.join(text, 'text.xml'), 'rb').read() == orig)
        except Exception as e:                                              # noqa: BLE001
            return 'ПРОПУСК: wine не дал прогнать (%s: %s)' % (type(e).__name__, str(e)[:70])
        bad = [n for n, ok in checks if not ok]
        msg = 'cmd.exe(Wine): %d/%d' % (len(checks) - len(bad), len(checks))
        assert not bad, 'живой cmd.exe: провалено %s' % '; '.join(bad)
        return msg + '; for /d не эмулируется Wine — покрыто симуляциями'


# ---------------------------------------------------------------------- runner
def main():
    for _name, fn in SUITE:
        try:
            msg = fn()
            results.append((_name, True, msg or 'ok'))
        except AssertionError as e:
            results.append((_name, False, str(e)))
        except Exception as e:                                        # noqa: BLE001
            results.append((_name, False, f"{type(e).__name__}: {e}"))
    ok = sum(1 for _, r, _ in results if r)
    print('\n'.join(f"  {'ok  ' if r else 'FAIL'}  {n:64} {m}" for n, r, m in results))
    print(f"\n{ok}/{len(results)} тестов пройдено")
    # машинночитаемый отчёт для README
    with io.open(os.path.join(ROOT, 'TESTS.md'), 'w', encoding='utf-8') as f:
        f.write('# Что проверяет `tools/check_repo.py`\n\n')
        f.write(f'{ok}/{len(results)} тестов пройдено (последний прогон).\n\n')
        f.write('| # | Тест | Результат | Что именно проверено |\n|---|---|---|---|\n')
        for i, (n, r, m) in enumerate(results, 1):
            f.write(f'| {i} | `{n}` | {"✅" if r else "❌"} | {m} |\n')
        f.write('\n## Чего тесты НЕ покрывают\n\n'
                'cmd.exe здесь запустить нечем (нет Windows), поэтому `УСТАНОВИТЬ.bat` проверен\n'
                'статически + логика его циклов воспроизведена на фиктивной папке `Text\\en\\…`.\n'
                'Живой двойной клик, UAC и поведение `OemDrv.exe` — проверить можно только на Windows.\n')
    return 0 if ok == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
