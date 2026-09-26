# -*- coding: utf-8 -*-
import re
import shutil
import uuid
from pathlib import Path

SUFFIXES = {'.exe', '.py', '.bat', '.cmd'}
EXCLUDED = {'程序集文件', '打包输出', '打包临时', 'versions', 'docs', 'tests', '__pycache__', '.git'}

def application_root(executable, source, frozen=False):
    if frozen:
        return Path(executable).resolve().parent
    parent = Path(source).resolve().parent
    return parent.parent if parent.name == '程序集文件' else parent

def program_name(value):
    value = re.sub(r'(?i)[._ -]+(?:v\d+(?:\.\d+)*|\d+\.\d+(?:\.\d+)*)(?:.*)$', '', value)
    value = re.sub(r'(?i)[._ -]+(?:windows|win|x64|x86|amd64|arm64)(?:[._ -].*)?$', '', value)
    value = re.sub(r'(?:汉化版|绿色版|便携版)(?:_\d+)?$', '', value)
    value = re.sub(r'(?i)[._ -]+(?:32|64)$', '', value)
    value = value.strip(' ._-')
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).rstrip(' .') or 'Program'
    if re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', value):
        value = '_' + value
    return value

def unique(path):
    path = Path(path)
    result = path
    index = 2
    while result.exists():
        result = path.with_name(f'{path.stem}_{index}{path.suffix}')
        index += 1
    return result

def launchers(folder):
    return sorted((p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in SUFFIXES
                   and p.name not in {'小程序集合.py', '小程序集合.exe', 'suite_core.py', 'suite_storage.py'}
                   and not any(part in EXCLUDED for part in p.relative_to(folder).parts)),
                  key=lambda p: (len(p.relative_to(folder).parts), p.suffix.lower() != '.exe', str(p).casefold()))

def collect(root, entries, organize=False):
    root = Path(root).resolve()
    old = {str((root / e['exec_path']).resolve()).casefold(): e for e in entries}
    updates = []
    errors = []
    for item in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
        if item.name in EXCLUDED or item.name.startswith('.') or item.name in {'小程序集合.py', '小程序集合.exe', 'suite_core.py', 'suite_storage.py'}:
            continue
        if item.is_file() and item.suffix.lower() not in SUFFIXES:
            continue
        paths = launchers(item) if item.is_dir() else [item]
        if not paths:
            continue
        # One package owns its dependency tree; helper executables stay in place.
        primary = next((p for p in paths if str(p.resolve()).casefold() in old), None)
        if primary is None:
            primary = next((p for p in paths if program_name(p.stem).casefold() == program_name(item.stem).casefold()), paths[0])
        previous = old.get(str(primary.resolve()).casefold())
        if previous is None:
            previous = next((old[str(p.resolve()).casefold()] for p in paths if str(p.resolve()).casefold() in old), None)
        name = program_name(primary.stem)
        target = item
        try:
            if organize:
                destination = root / name
                if item.is_file():
                    if destination.exists() and not destination.is_dir():
                        raise ValueError(f'目标不是文件夹：{destination}')
                    destination.mkdir(exist_ok=True)
                    moved = unique(destination / item.name)
                    shutil.move(str(item), str(moved))
                    primary, target = moved, destination
                elif destination != item:
                    if destination.exists() and re.fullmatch(re.escape(name) + r'_\d+', item.name):
                        destination = item
                    if destination.exists():
                        # Never merge two dependency trees automatically.
                        if destination != item:
                            destination = unique(destination)
                    relative = primary.relative_to(item)
                    if destination != item:
                        shutil.move(str(item), str(destination))
                    primary, target = destination / relative, destination
            entry = dict(previous) if previous else {'id': uuid.uuid4().hex, 'icon': '', 'description': ''}
            entry.update(name=name, exec_path=str(primary.relative_to(root)),
                         folder=str(target.relative_to(root)) if target.is_dir() else '')
            updates.append(entry)
        except Exception as exc:
            errors.append(f'{item.name}：{exc}')
            updates.extend(e for e in entries if (root / e['exec_path']).is_relative_to(item) or root / e['exec_path'] == item)
    positions = {e['id']: i for i, e in enumerate(entries)}
    updates.sort(key=lambda e: positions.get(e['id'], len(entries)))
    return updates, errors
