# -*- coding: utf-8 -*-
"""按读取快照合并修改，锁内备份并原子写入。"""
import copy
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

class DataConflict(RuntimeError):
    pass


def read_database(path):
    path = Path(path)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, list) or any(not isinstance(e, dict) or not e.get('id') or not isinstance(e.get('exec_path'), str) for e in data):
        raise ValueError('程序数据格式错误，已停止保存。')
    if len({e['id'] for e in data}) != len(data):
        raise ValueError('程序标识重复，已停止保存。')
    return data


def merge_database(base, incoming, current):
    previous = {e['id']: e for e in base}
    local = {e['id']: e for e in incoming}
    disk = {e['id']: copy.deepcopy(e) for e in current}
    missing = object()
    for key in previous.keys() | local.keys():
        before, after, latest = previous.get(key), local.get(key), disk.get(key)
        if before == after:
            continue
        if before is None:
            if latest is not None and latest != after:
                raise DataConflict('新增程序与最新数据冲突，请重新操作。')
            disk[key] = copy.deepcopy(after)
        elif after is None:
            if latest is not None and latest != before:
                raise DataConflict('待删除程序已被其他窗口修改，请重新操作。')
            disk.pop(key, None)
        elif latest is None:
            raise DataConflict('程序已被其他窗口删除，请重新操作。')
        else:
            for field in before.keys() | after.keys():
                old_value, new_value = before.get(field, missing), after.get(field, missing)
                if old_value == new_value:
                    continue
                disk_value = latest.get(field, missing)
                if disk_value != old_value and disk_value != new_value:
                    raise DataConflict('同一程序的数据已被其他窗口修改，请重新操作。')
                if new_value is missing:
                    latest.pop(field, None)
                else:
                    latest[field] = copy.deepcopy(new_value)
    old_order = [e['id'] for e in base]
    local_order = [e['id'] for e in incoming]
    disk_order = [e['id'] for e in current]
    # 只有本窗口改变顺序时才采用本窗口的顺序。
    order = local_order if local_order != old_order else disk_order
    order = list(dict.fromkeys(order + disk_order + local_order))
    return [disk[key] for key in order if key in disk]


@contextmanager
def database_lock(path):
    lock_path = Path(path).with_suffix('.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a+b') as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def atomic_write(path, data):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=path.stem + '_', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
