# -*- coding: utf-8 -*-
"""
Сравнение двух XML-файлов Blockly-схем и запись разницы в файл изменений.

Правила формирования результата:
  - сохраняются ТОЛЬКО изменённые, добавленные и удалённые фрагменты;
  - элементы выше уровня изменения остаются только в виде тега и атрибутов;
  - изменённый текст/атрибут: новое значение — в элементе,
    старое — в diff:old / diff:old-*; добавленный атрибут — diff:added-*;
  - элемент, оставшийся только в файле 1, помечается diff:status="Удален"
    и сохраняется целиком (+ diff:old-index — позиция в файле 1);
  - элемент, появившийся только в файле 2, помечается diff:status="Добавлен"
    и сохраняется целиком (+ diff:index — позиция в файле 2);
  - неизменённые процедуры и неизменённые переменные в результат не попадают.

Дельта ОБРАТИМА: blockly_xml_apply.py восстанавливает по ней как файл 2
из файла 1 (вперёд), так и файл 1 из файла 2 (назад, ключ --reverse).

Разное число процедур в файлах — нормальная ситуация (процедура добавлена
или удалена), ошибкой не считается.

Запуск (пути можно опустить — используются значения по умолчанию):
    python blockly_xml_diff.py [файл1_исходный.xml] [файл2_изменённый.xml] [результат.xml]
"""

import os
import sys
import difflib
import tempfile
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
    """Локальное имя элемента (без префикса пространства имён)."""
    return el.tag.split('}')[-1] if isinstance(el.tag, str) else ''


def isdiff(k):
    return k.startswith('{%s}' % DIFF)


STATUS = dq('status')
CHANGED, REMOVED, ADDED = 'Изменено', 'Удален', 'Добавлен'
IGNORED = ('x', 'y')          # координаты блоков на смысл не влияют

# ---------------------------------------------------------------- пути по умолчанию
DEFAULT_FILE1 = '/home/user/.perplexity/attachments/48f77c41a73a4e1dabad4d905918f4ef/Dom1CZUP3-1-12-142_Blockly_ChastnoeLitso_update.xml'
DEFAULT_FILE2 = '/home/user/.perplexity/attachments/48f77c41a73a4e1dabad4d905918f4ef/Dom1CZUP3-1-12-142_Blockly_ChastnoeLitso_update-1.xml'
DEFAULT_OUT   = '/home/user/workspace/Dom1CZUP3-1-12-142_Blockly_ChastnoeLitso_diff.xml'


# ---------------------------------------------------------------- сравнение
def canon(el):
    """
    Каноническое представление элемента для сравнения «как есть».
    Атрибуты x/y (координаты блоков) и служебные diff-атрибуты игнорируются.
    """
    parts = [local(el)]
    for k, v in sorted(el.attrib.items()):
        if isdiff(k) or k.split('}')[-1] in IGNORED:
            continue
        parts.append('%s=%s' % (k, v))
    if el.text and el.text.strip():
        parts.append('T:' + el.text)
    for c in el:
        if isinstance(c.tag, str):
            parts.append(canon(c))
    return '(' + ' '.join(parts) + ')'


def key(el):
    """
    Ключ дочернего элемента для выравнивания списков.
    Одинаково вычисляется в обоих скриптах, поэтому пара «элемент файла 1 —
    элемент файла 2» находится в любой момент.
    """
    t = local(el)
    if 'name' in el.attrib:                      # value/statement/field/arg
        return '%s@%s' % (t, el.attrib['name'])
    if 'id' in el.attrib:                        # block, variable, ...
        return '%s#%s' % (t, el.attrib['id'])
    if 'type' in el.attrib:
        return '%s:%s' % (t, el.attrib['type'])
    return t                                     # next, mutation, comment, variables


# ---------------------------------------------------------------- дельта
def diff_elements(e1, e2):
    """
    Рекурсивное сравнение старого (e1, файл 1) и нового (e2, файл 2) элементов.
    Возвращает копию e2 только с изменёнными путями и пометками diff,
    либо None, если изменений нет.
    """
    if canon(e1) == canon(e2):
        return None                              # совпадает полностью

    r = ET.Element(e2.tag, dict(e2.attrib))       # контейнер из нового элемента
    r.text = e2.text

    # изменение текста элемента (значение field, имя variable и т.п.)
    t1 = (e1.text or '').strip()
    t2 = (e2.text or '').strip()
    if t1 != t2:
        r.set(dq('old'), t1)                     # нужно для обратной склейки
        r.set(STATUS, CHANGED)

    # изменение атрибутов (x/y игнорируем)
    for k in sorted(set(e1.attrib) | set(e2.attrib)):
        name = k.split('}')[-1]
        if isdiff(k) or name in IGNORED:
            continue
        v1 = e1.attrib.get(k)
        v2 = e2.attrib.get(k)
        if v1 == v2:
            continue
        if v1 is None:
            r.set(dq('added-' + name), '1')      # атрибут появился
        else:
            r.set(dq('old-' + name), v1)         # атрибут изменён/удалён
        if STATUS not in r.attrib:
            r.set(STATUS, CHANGED)

    # выравнивание дочерних элементов
    c1 = [c for c in e1 if isinstance(c.tag, str)]
    c2 = [c for c in e2 if isinstance(c.tag, str)]
    sm = difflib.SequenceMatcher(a=[key(c) for c in c1],
                                 b=[key(c) for c in c2], autojunk=False)

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            for i, j in zip(range(i1, i2), range(j1, j2)):
                m = diff_elements(c1[i], c2[j])
                if m is not None:
                    r.append(m)

        # элементы, которых нет в файле 2 -> "Удален" (целиком, для отката)
        if op in ('delete', 'replace'):
            for i in range(i1, i2):
                d = deepcopy(c1[i])
                d.set(STATUS, REMOVED)
                d.set(dq('old-index'), str(i))   # позиция в файле 1
                r.append(d)

        # элементы, которых нет в файле 1 -> "Добавлен" (целиком)
        if op in ('insert', 'replace'):
            for j in range(j1, j2):
                a = deepcopy(c2[j])
                a.set(STATUS, ADDED)
                a.set(dq('index'), str(j))       # позиция в файле 2
                r.append(a)

    return r


HEADER = (' Разница двух файлов: показаны ТОЛЬКО изменённые, добавленные и удалённые фрагменты. '
          'diff:status: "Изменено" — новое значение в тексте/атрибутах, старое в diff:old / diff:old-*; '
          '"Удален" — элемент есть только в файле 1 (сохранён целиком, diff:old-index — его позиция); '
          '"Добавлен" — элемент есть только в файле 2 (сохранён целиком, diff:index — его позиция). '
          'Элементы выше изменения оставлены только как тег + атрибуты. '
          'Дельта обратима: blockly_xml_apply.py собирает по ней и файл 2, и файл 1. ')


def _procedure_names(root):
    """id верхнеуровневого блока -> имя процедуры (для комментариев в дельте)."""
    names = {}
    for b in root:
        if local(b) != 'block':
            continue
        for f in b:
            if isinstance(f.tag, str) and local(f) == 'field' \
               and f.attrib.get('name') == 'NAME':
                names[b.attrib.get('id')] = f.text
                break
    return names


def _annotate(delta, root2):
    """Комментарии перед процедурами верхнего уровня (на разбор не влияют)."""
    names = _procedure_names(root2)
    kids = list(delta)
    for c in kids:
        delta.remove(c)
    for c in kids:
        if isinstance(c.tag, str) and local(c) == 'block':
            nm = names.get(c.attrib.get('id')) or '(без имени)'
            st = c.get(STATUS)
            if st == ADDED:
                txt = ' процедура "%s" добавлена целиком ' % nm
            elif st == REMOVED:
                txt = ' процедура "%s" удалена (сохранена целиком для обратной склейки) ' % nm
            else:
                txt = ' процедура "%s" — только изменённые фрагменты ' % nm
            delta.append(ET.Comment(txt))
        delta.append(c)


# ---------------------------------------------------------------- сборка
def build_diff(file1, file2, out_path):
    r1 = ET.parse(file1).getroot()
    r2 = ET.parse(file2).getroot()

    delta = diff_elements(r1, r2)                # разное число процедур — не ошибка
    if delta is None:
        delta = ET.Element(q('xml'))             # файлы идентичны

    delta.set(dq('file1'), '%s (файл 1, исходный)' % file1)
    delta.set(dq('file2'), '%s (файл 2, изменённый)' % file2)

    _annotate(delta, r2)
    delta.insert(0, ET.Comment(HEADER))

    ET.indent(delta, space='\t')
    ET.ElementTree(delta).write(out_path, encoding='unicode', xml_declaration=False)
    ET.parse(out_path)                           # проверка корректности результата
    return out_path


def self_check(file1, file2, delta_path):
    """Круговая проверка: вперёд (1+дельта->2) и назад (2+дельта->1)."""
    try:
        import blockly_xml_apply as ap
    except Exception:
        return
    tmp = tempfile.mkdtemp(prefix='blockly_diff_')
    fwd = os.path.join(tmp, 'forward.xml')
    rev = os.path.join(tmp, 'reverse.xml')
    sem_f, _ = ap.restore(file1, delta_path, fwd, file2)
    sem_r, _ = ap.restore(file2, delta_path, rev, file1, reverse=True)
    print('Проверка вперёд (файл 1 + дельта -> файл 2): %s'
          % ('OK' if sem_f else 'РАСХОЖДЕНИЕ'))
    print('Проверка назад  (файл 2 + дельта -> файл 1): %s'
          % ('OK' if sem_r else 'РАСХОЖДЕНИЕ'))


if __name__ == '__main__':
    args = sys.argv[1:]
    file1 = args[0] if len(args) > 0 else DEFAULT_FILE1
    file2 = args[1] if len(args) > 1 else DEFAULT_FILE2
    out   = args[2] if len(args) > 2 else DEFAULT_OUT
    build_diff(file1, file2, out)
    print('Готово:', out)
    self_check(file1, file2, out)
