# -*- coding: utf-8 -*-
"""
Обратное преобразование: применяет файл-дельту (созданный blockly_xml_diff.py)
к XML-файлу и восстанавливает второй файл пары.

Направления:
  - вперёд (по умолчанию):  файл 1 + дельта -> файл 2;
  - назад (ключ --reverse): файл 2 + дельта -> файл 1 (возврат к исходной схеме).

Что учитывается:
  - diff:status="Изменено"  — берётся новое значение (текст/атрибуты) из дельты;
                              для --reverse — старое из diff:old / diff:old-*;
  - diff:status="Добавлен"  — элемент вставляется на позицию diff:index
                              (для --reverse — удаляется);
  - diff:status="Удален"    — элемент файла 1 исключается
                              (для --reverse — вставляется на diff:old-index);
  - элементы выше изменения — берутся из базового файла целиком;
  - diff:added-<атрибут>    — атрибут, появившийся в файле 2 (для --reverse удаляется).

Запуск (аргументы необязательны — используются пути по умолчанию):
    python blockly_xml_apply.py [база.xml] [дельта.xml] [результат.xml] [эталон.xml] [--reverse]

Если задан 4-й аргумент, скрипт проверит каноническое совпадение результата с эталоном.
"""

import sys
from copy import deepcopy
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------- namespaces
BL = 'https://developers.google.com/blockly/xml'   # пространство Blockly
DIFF = 'urn:blockly-diff'                          # пространство пометок diff

ET.register_namespace('', BL)
ET.register_namespace('diff', DIFF)


def q(t):   return '{%s}%s' % (BL, t)
def dq(t):  return '{%s}%s' % (DIFF, t)


def local(el):
    return el.tag.split('}')[-1] if isinstance(el.tag, str) else ''


def isdiff(k):
    return k.startswith('{%s}' % DIFF)


STATUS = dq('status')
CHANGED, REMOVED, ADDED = 'Изменено', 'Удален', 'Добавлен'
IGNORED = ('x', 'y')

# ---------------------------------------------------------------- пути по умолчанию
DEFAULT_FILE1 = '/home/user/.perplexity/attachments/48f77c41a73a4e1dabad4d905918f4ef/Dom1CZUP3-1-12-142_Blockly_ChastnoeLitso_update.xml'
DEFAULT_DELTA = '/home/user/workspace/Dom1CZUP3-1-12-142_Blockly_ChastnoeLitso_diff.xml'
DEFAULT_OUT   = '/home/user/workspace/Dom1CZUP3-1-12-142_Blockly_ChastnoeLitso_update-1_restored.xml'
DEFAULT_CHECK = '/home/user/.perplexity/attachments/48f77c41a73a4e1dabad4d905918f4ef/Dom1CZUP3-1-12-142_Blockly_ChastnoeLitso_update-1.xml'
DEFAULT_REV_OUT   = '/home/user/workspace/Dom1CZUP3-1-12-142_Blockly_ChastnoeLitso_update_restored.xml'
DEFAULT_REV_CHECK = DEFAULT_FILE1


# ---------------------------------------------------------------- утилиты
def strip_diff_attrs(el):
    """Глубокая копия элемента без атрибутов пространства diff."""
    c = deepcopy(el)

    def rec(e):
        for k in list(e.attrib):
            if isdiff(k):
                del e.attrib[k]
        for child in e:
            if isinstance(child.tag, str):
                rec(child)

    rec(c)
    return c


def key(el):
    """Ключ элемента — тот же алгоритм, что в blockly_xml_diff.py."""
    t = local(el)
    if 'name' in el.attrib:
        return '%s@%s' % (t, el.attrib['name'])
    if 'id' in el.attrib:
        return '%s#%s' % (t, el.attrib['id'])
    if 'type' in el.attrib:
        return '%s:%s' % (t, el.attrib['type'])
    return t


def _find(children, k):
    for c in children:
        if key(c) == k:
            return c
    return None


def _num(el, name):
    raw = el.get(dq(name))
    if raw is None or not raw.lstrip('-').isdigit():
        return None
    return int(raw)


# ---------------------------------------------------------------- склейка
def rebuild(base, delta, reverse=False):
    """
    base   — элемент базового файла (вперёд: файл 1, назад: файл 2);
    delta  — соответствующий элемент дельты (только изменённые пути);
    reverse— направление склейки.
    Возвращает новый элемент — фрагмент восстанавливаемого файла.
    """
    if base is None:
        return strip_diff_attrs(delta)

    # ---------------- атрибуты
    attrs = {}
    for k, v in delta.attrib.items():
        if not isdiff(k):
            attrs[k] = v
    if reverse:
        for k, v in delta.attrib.items():
            if not isdiff(k):
                continue
            name = k.split('}')[-1]
            if name.startswith('old-'):
                attrs[name[4:]] = v                     # вернуть старое значение
            elif name.startswith('added-'):
                attrs.pop(name[6:], None)               # убрать добавленный атрибут

    res = ET.Element(delta.tag, attrs)

    # ---------------- текст
    if reverse and dq('old') in delta.attrib:
        res.text = delta.get(dq('old'))
    else:
        res.text = delta.text

    # ---------------- дети
    bchildren = [c for c in base if isinstance(c.tag, str)]
    dchildren = [c for c in delta if isinstance(c.tag, str)]

    repl, drop, inserts = {}, set(), []

    for d in dchildren:
        st = d.get(STATUS)
        k = key(d)

        if st == REMOVED:
            if reverse:
                # возвращаем удалённый элемент на его место в файле 1
                inserts.append((_num(d, 'old-index'), strip_diff_attrs(d)))
            else:
                drop.add(k)                            # в файле 2 его нет

        elif st == ADDED:
            if reverse:
                drop.add(k)                            # в файле 1 его не было
            else:
                inserts.append((_num(d, 'index'), strip_diff_attrs(d)))

        else:
            bc = _find(bchildren, k)
            if bc is None:
                # пары не нашлось — считаем вставкой
                idx = _num(d, 'old-index' if reverse else 'index')
                inserts.append((idx, strip_diff_attrs(d)))
            else:
                repl[k] = rebuild(bc, d, reverse)

    out = []
    for c in bchildren:
        k = key(c)
        if k in drop:
            continue
        out.append(repl.get(k, deepcopy(c)))

    # вставки по позициям восстанавливаемого файла (по возрастанию индекса)
    for idx, el in sorted(inserts, key=lambda p: (p[0] is None,
                                                  p[0] if p[0] is not None else 0)):
        if idx is None or idx > len(out):
            out.append(el)
        else:
            out.insert(idx, el)

    for el in out:
        res.append(el)
    return res


# ---------------------------------------------------------------- проверка
def canon(el, ignore_xy=True):
    """Каноническое представление для сравнения двух деревьев."""
    parts = [local(el)]
    for k, v in sorted(el.attrib.items()):
        if isdiff(k):
            continue
        if ignore_xy and k.split('}')[-1] in IGNORED:
            continue
        parts.append('%s=%s' % (k, v))
    if el.text and el.text.strip():
        parts.append('T:' + el.text)
    for c in el:
        if isinstance(c.tag, str):
            parts.append(canon(c, ignore_xy))
    return '(' + ' '.join(parts) + ')'


def restore(base_path, delta_path, out_path, check_path=None, reverse=False):
    base_root = ET.parse(base_path).getroot()
    delta_root = ET.parse(delta_path).getroot()

    restored = rebuild(base_root, delta_root, reverse=reverse)

    ET.indent(restored, space='\t')
    ET.ElementTree(restored).write(out_path, encoding='unicode', xml_declaration=False)
    ET.parse(out_path)                          # проверка корректности результата

    if check_path:
        ref = ET.parse(check_path).getroot()
        sem = canon(restored) == canon(ref)                     # без координат x/y
        strict = canon(restored, False) == canon(ref, False)
        return sem, strict
    return None, None


if __name__ == '__main__':
    raw = sys.argv[1:]
    reverse = '--reverse' in raw
    args = [a for a in raw if a != '--reverse']

    if reverse:
        base  = args[0] if len(args) > 0 else DEFAULT_CHECK
        delta = args[1] if len(args) > 1 else DEFAULT_DELTA
        out   = args[2] if len(args) > 2 else DEFAULT_REV_OUT
        check = args[3] if len(args) > 3 else DEFAULT_REV_CHECK
    else:
        base  = args[0] if len(args) > 0 else DEFAULT_FILE1
        delta = args[1] if len(args) > 1 else DEFAULT_DELTA
        out   = args[2] if len(args) > 2 else DEFAULT_OUT
        check = args[3] if len(args) > 3 else DEFAULT_CHECK

    sem, strict = restore(base, delta, out, check, reverse=reverse)

    print('Направление:        ', 'назад (файл 2 + дельта -> файл 1)' if reverse
          else 'вперёд (файл 1 + дельта -> файл 2)')
    print('База:               ', base)
    print('Дельта:             ', delta)
    print('Результат:          ', out)
    if sem is not None:
        print('Проверка с эталоном:  структура и значения %s; координаты x/y %s'
              % ('совпадают' if sem else 'НЕ совпадают',
                 'совпадают' if strict else 'НЕ совпадают (на смысл не влияет)'))
    else:
        print('Эталон для проверки не задан.')
