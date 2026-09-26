#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
个人程序集绿色版（Program Files 兼容版）
- 程序文件在 Program Files，可移动程序也在同一目录
- 所有可写数据（数据库、图标、已删除程序）存储在用户目录，避免权限问题
- 支持添加、运行、删除、更换图标、编辑简介
"""

import os
import sys
import shutil
import json
import uuid
import subprocess
import time
import ctypes
import copy
from ctypes import wintypes
from suite_core import collect, program_name, unique, application_root
from suite_storage import read_database, merge_database, database_lock, atomic_write, DataConflict
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from tkinter import ttk

# Pillow 可选
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# ---------- 路径配置 ----------
USER_HOME = Path(os.environ['USERPROFILE'])
DATA_DIR = Path(os.environ.get('APPDATA', str(USER_HOME / 'AppData' / 'Roaming'))) / 'PersonalSuite'

DB_FILE = DATA_DIR / 'programs.json'
BACKUP_DIR = DATA_DIR / 'backups'
ICONS_DIR = DATA_DIR / 'icons'
DELETED_DIR = DATA_DIR / '已删除'

for d in (DATA_DIR, BACKUP_DIR, ICONS_DIR, DELETED_DIR):
    d.mkdir(parents=True, exist_ok=True)

APP_DIR = application_root(sys.executable, __file__, getattr(sys, 'frozen', False))
PROGRAMS_DIR = APP_DIR  # 所有被管理程序直接放在程序目录
RESOURCE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
THUMB_SIZE = (96, 96)
SUPPORTED_SUFFIXES = {'.exe', '.py', '.bat', '.cmd'}

# ---------- DB helpers ----------
_DB_SNAPSHOTS = {}

def load_db():
    # 损坏数据不得当作空数据库继续写回。
    db = read_database(DB_FILE)
    _DB_SNAPSHOTS[str(DB_FILE.resolve())] = copy.deepcopy(db)
    return db


def save_db(db):
    key = str(DB_FILE.resolve())
    with database_lock(DB_FILE):
        current = read_database(DB_FILE)
        base = _DB_SNAPSHOTS.get(key)
        if base is None:
            raise DataConflict('尚未读取当前数据库，已停止保存。')
        merged = merge_database(base, db, current)
        if merged != current:
            backup_db()
            atomic_write(DB_FILE, merged)
        db[:] = merged
        _DB_SNAPSHOTS[key] = copy.deepcopy(merged)

DB_LOAD_ERROR = None
try:
    DB = load_db()
except (ValueError, OSError) as error:
    DB = []
    DB_LOAD_ERROR = error

def backup_db():
    if not DB_FILE.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime('%Y%m%d_%H%M%S')
    target = unique_target(BACKUP_DIR / f"programs_{ts}.json")
    # 备份失败即停止本次写入；不再静默忽略。
    shutil.copy2(str(DB_FILE), str(target))
    backups = sorted(BACKUP_DIR.glob('programs_*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[20:]:
        old.unlink()

# ---------- 文件操作 ----------
def unique_target(path: Path):
    p = Path(path)
    if not p.exists():
        return p
    stem = p.stem
    suffix = p.suffix
    parent = p.parent
    i = 1
    while True:
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1

def move_into_programs(selected: Path):
    """移动文件或文件夹到程序目录"""
    selected = Path(selected)
    if not selected.exists():
        raise FileNotFoundError(selected)

    if selected.is_file():
        target = APP_DIR / selected.name
    else:
        target = APP_DIR / selected.name

    target = unique_target(target)
    shutil.move(str(selected), str(target))
    return (target.relative_to(APP_DIR), target)

def rel_to_app(path: Path):
    return str(Path(path).resolve().relative_to(APP_DIR))

def is_supported_exec(path: Path):
    path = Path(path)
    return path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES

def is_self_file(path: Path):
    try:
        resolved = Path(path).resolve()
        if resolved == Path(__file__).resolve():
            return True
        if getattr(sys, 'frozen', False) and resolved == Path(sys.executable).resolve():
            return True
        if resolved.stem == Path(__file__).stem and resolved.suffix.lower() in {'.py', '.exe'}:
            return True
        return False
    except Exception:
        return False

def find_launchers(base: Path):
    base = Path(base)
    if is_supported_exec(base) and not is_self_file(base):
        return [base]
    if not base.is_dir():
        return []
    found = []
    for child in base.rglob('*'):
        if is_supported_exec(child) and not is_self_file(child):
            found.append(child)
    return sorted(found, key=lambda p: str(p).lower())

def pick_primary_launcher(paths):
    if not paths:
        return None
    exe_files = [p for p in paths if p.suffix.lower() == '.exe']
    return exe_files[0] if exe_files else paths[0]

def sync_manual_programs():
    global DB
    updated, errors = collect(APP_DIR, DB)
    if updated != DB:
        DB = updated
        save_db(DB)

def system_icon(path):
    if not PIL_AVAILABLE or sys.platform != 'win32':
        return None
    class Info(ctypes.Structure):
        _fields_ = [('icon', wintypes.HANDLE), ('index', ctypes.c_int), ('attributes', wintypes.DWORD),
                    ('name', wintypes.WCHAR * 260), ('type', wintypes.WCHAR * 80)]
    shell, user, gdi = ctypes.windll.shell32, ctypes.windll.user32, ctypes.windll.gdi32
    shell.SHGetFileInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(Info), ctypes.c_uint, ctypes.c_uint]
    user.GetDC.restype = wintypes.HDC
    gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi.CreateCompatibleDC.restype = wintypes.HDC
    gdi.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
    gdi.CreateDIBSection.restype = wintypes.HANDLE
    gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    gdi.SelectObject.restype = wintypes.HANDLE
    user.DrawIconEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_uint, wintypes.HANDLE, ctypes.c_uint]
    gdi.DeleteObject.argtypes = [wintypes.HANDLE]
    gdi.DeleteDC.argtypes = [wintypes.HDC]
    user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user.DestroyIcon.argtypes = [wintypes.HANDLE]
    info = Info()
    if not shell.SHGetFileInfoW(str(path), 0, ctypes.byref(info), ctypes.sizeof(info), 0x100):
        return None
    dc = user.GetDC(None)
    memory = gdi.CreateCompatibleDC(dc)
    header = ctypes.create_string_buffer(40)
    import struct
    header.raw = struct.pack('<IiiHHIIiiII', 40, 64, -64, 1, 32, 0, 16384, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    bitmap = gdi.CreateDIBSection(dc, header, 0, ctypes.byref(bits), None, 0)
    if not bitmap:
        gdi.DeleteDC(memory); user.ReleaseDC(None, dc); user.DestroyIcon(info.icon)
        return None
    old = gdi.SelectObject(memory, bitmap)
    try:
        ctypes.memset(bits, 255, 16384)
        user.DrawIconEx(memory, 0, 0, info.icon, 64, 64, 0, None, 3)
        return Image.frombytes('RGB', (64, 64), ctypes.string_at(bits, 16384), 'raw', 'BGRX')
    finally:
        gdi.SelectObject(memory, old)
        gdi.DeleteObject(bitmap); gdi.DeleteDC(memory)
        user.ReleaseDC(None, dc); user.DestroyIcon(info.icon)

def save_icon_from_image(img_path, program_id):
    if not PIL_AVAILABLE:
        return ''
    try:
        im = Image.open(img_path)
        im.thumbnail(THUMB_SIZE)
        target = ICONS_DIR / f"{program_id}.png"
        im.save(target, format='PNG')
        return os.path.relpath(target, DATA_DIR)
    except Exception as e:
        print('save_icon error', e)
        return ''

# ---------- GUI组件 ----------
STYLE_BG = '#f7f8fa'
CARD_BG = '#ffffff'
HOVER_BG = '#eef3ff'

class ProgramCard(ttk.Frame):
    def __init__(self, master, entry, refresh_callback, *args, **kwargs):
        super().__init__(master, style='Card.TFrame', padding=8, *args, **kwargs)
        self.configure(width=190, height=210)
        self.pack_propagate(False)
        self.entry = entry
        self.refresh_callback = refresh_callback
        self.icon_img = None
        self.build()
        self.bind_events()

    def build(self):
        self.inner = tk.Frame(self, bg=STYLE_BG)
        self.inner.pack(fill='both', expand=True)

        icon_path = (ICONS_DIR / Path(self.entry.get('icon')).name) if self.entry.get('icon') else None
        if PIL_AVAILABLE and icon_path and icon_path.exists():
            try:
                im = Image.open(icon_path)
                im.thumbnail(THUMB_SIZE)
                self.icon_img = ImageTk.PhotoImage(im)
            except Exception:
                self.icon_img = None

        if self.icon_img:
            self.icon_label = tk.Label(self.inner, image=self.icon_img, bg=STYLE_BG)
        else:
            im = system_icon(APP_DIR / self.entry['exec_path'])
            if im:
                self.icon_img = ImageTk.PhotoImage(im)
                self.icon_label = tk.Label(self.inner, image=self.icon_img, bg=STYLE_BG)
            else:
                self.icon_label = tk.Label(self.inner, text=self.entry.get('exec_path', '').split('.')[-1].upper(), font=('Segoe UI', 20, 'bold'), bg=STYLE_BG)
        self.icon_label.place(x=0, y=10, relwidth=1, height=86)
        self.icon_label.bind('<Button-3>', self.open_context_menu)

        display_name = self.entry.get('name', '')
        self.name_label = tk.Label(self.inner, text=display_name, bg=STYLE_BG, wraplength=170, font=('Segoe UI', 10, 'bold'))
        self.name_label.place(x=0, y=104, relwidth=1, height=46)

        desc_text = self.entry.get('description', '')
        self.desc_label = tk.Label(self.inner, text=desc_text, fg='#1565c0', bg=STYLE_BG, wraplength=160, justify='left')
        self.desc_label.place(x=0, y=154, relwidth=1, height=32)

    def bind_events(self):
        for w in (self, self.inner, self.icon_label, self.name_label, self.desc_label):
            w.bind('<Button-3>', self.open_context_menu)
            w.bind('<ButtonPress-1>', self.drag_start)
            w.bind('<B1-Motion>', self.drag_motion)
            w.bind('<ButtonRelease-1>', self.drag_end)
            w.bind('<Double-Button-1>', self.run_program)

    def drag_start(self, event):
        self.start = (event.x_root, event.y_root)
        self.dragging = False

    def drag_motion(self, event):
        if abs(event.x_root-self.start[0]) + abs(event.y_root-self.start[1]) > 8:
            self.dragging = True
            self.configure(cursor='fleur')

    def drag_end(self, event):
        self.configure(cursor='')
        if not getattr(self, 'dragging', False):
            return
        widget = next((card for card in self.master.winfo_children()
                       if card.winfo_rootx() <= event.x_root < card.winfo_rootx() + card.winfo_width()
                       and card.winfo_rooty() <= event.y_root < card.winfo_rooty() + card.winfo_height()), None)
        if widget and widget != self:
            DB.remove(self.entry)
            DB.insert(DB.index(widget.entry), self.entry)
            save_db(DB)
            self.refresh_callback()

    def run_program(self, event=None):
        exec_rel = self.entry['exec_path']
        exec_abspath = (APP_DIR / exec_rel).resolve()
        if not exec_abspath.exists():
            messagebox.showerror('错误', '程序文件不存在: ' + str(exec_abspath))
            return
        suffix = exec_abspath.suffix.lower()
        try:
            if suffix == '.py':
                interpreter = shutil.which('pythonw') or shutil.which('python') or shutil.which('py')
                if not interpreter:
                    raise RuntimeError('运行 Python 脚本需要安装 Python。')
                subprocess.Popen([interpreter, str(exec_abspath)], cwd=str(exec_abspath.parent))
            else:
                if sys.platform == 'win32':
                    os.startfile(str(exec_abspath), cwd=str(exec_abspath.parent))
                else:
                    subprocess.Popen([str(exec_abspath)], cwd=str(exec_abspath.parent))
        except Exception as e:
            messagebox.showerror('运行错误', str(e))

    def open_context_menu(self, event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label='打开目录', command=self.open_program_dir)
        menu.add_command(label='编辑简介', command=self.edit_description)
        menu.add_command(label='删除', command=self.delete_program)
        menu.add_command(label='更换图标', command=self.change_icon)
        menu.tk_popup(event.x_root, event.y_root)

    def open_program_dir(self):
        exec_abspath = (APP_DIR / self.entry['exec_path']).resolve()
        target_dir = exec_abspath if exec_abspath.is_dir() else exec_abspath.parent
        try:
            if sys.platform == 'win32':
                os.startfile(str(target_dir))
            else:
                subprocess.Popen([str(target_dir)])
        except Exception as e:
            messagebox.showerror('打开目录失败', str(e))

    def delete_program(self):
        if not messagebox.askyesno('删除程序', '将整个程序文件夹移到“已删除”目录？'):
            return
        exec_rel = self.entry['exec_path']
        exec_abspath = APP_DIR / (self.entry.get('folder') or exec_rel)
        dest = DELETED_DIR / exec_abspath.name
        dest = unique_target(dest)
        try:
            if exec_abspath.exists():
                shutil.move(str(exec_abspath), str(dest))
        except Exception as exc:
            messagebox.showerror('删除失败', str(exc))
            return

        if self.entry.get('icon'):
            try:
                p = ICONS_DIR / Path(self.entry['icon']).name
                if p.exists():
                    p.unlink()
            except Exception:
                pass

        global DB
        DB = [e for e in DB if e['id'] != self.entry['id']]
        save_db(DB)
        self.refresh_callback()

    def change_icon(self):
        img = filedialog.askopenfilename(title='选择图片作为图标', filetypes=[('Image files', '*.png;*.jpg;*.jpeg;*.ico;*.bmp;*.gif')])
        if not img:
            return
        icon_rel = save_icon_from_image(img, self.entry['id'])
        if icon_rel:
            for e in DB:
                if e['id'] == self.entry['id']:
                    e['icon'] = icon_rel
                    break
            save_db(DB)
            self.refresh_callback()

    def edit_description(self, event=None):
        cur = self.entry.get('description', '')
        new = simpledialog.askstring('编辑简介', '请输入简介：', initialvalue=cur, parent=self.winfo_toplevel())
        if new is not None:
            for e in DB:
                if e['id'] == self.entry['id']:
                    e['description'] = new
                    break
            save_db(DB)
            self.refresh_callback()

# ---------- 主程序 ----------
class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        if sys.platform == 'win32':
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('PersonalSuite.Desktop')
        app_icon = RESOURCE_DIR / 'assets' / 'personal-suite.ico'
        if app_icon.exists():
            master.iconbitmap(default=str(app_icon))
        master.title('个人程序集')
        master.geometry('900x640')
        master.configure(bg=STYLE_BG)

        self.style = ttk.Style()
        try:
            self.style.theme_use('clam')
        except Exception:
            pass
        self.style.configure('Card.TFrame', background=CARD_BG, relief='flat')

        self.pack(fill='both', expand=True, padx=12, pady=12)
        self.create_header()
        self.create_canvas()
        sync_manual_programs()
        self.load_programs()

    def create_header(self):
        header = ttk.Frame(self, style='Card.TFrame')
        header.pack(fill='x', pady=(0,10))
        tk.Label(header, text='个人程序集', font=('Microsoft YaHei', 18, 'bold'), bg='white').pack(fill='x', pady=12)

        add_btn = tk.Button(header, text='+', font=('Segoe UI', 18, 'bold'), width=3, height=1, bg='#4a90e2', fg='white', bd=0, command=self.add_program)
        add_btn.pack(side='left')

        add_folder_btn = tk.Button(header, text='添加文件夹', font=('Segoe UI', 10, 'bold'), height=2, bg='#e4edf8', relief='raised', bd=1, command=self.add_folder)
        add_folder_btn.pack(side='left', padx=(8,0))

        scan_btn = tk.Button(header, text='扫描整理', font=('Segoe UI', 10, 'bold'), height=2, bg='#e4edf8', relief='raised', bd=1, command=self.scan_programs)
        scan_btn.pack(side='left', padx=(8,0))

        tk.Button(header, text='已删除', command=lambda: os.startfile(str(DELETED_DIR)), height=2).pack(side='right', padx=8)

        info_btn = tk.Button(header, text='说明', bg=STYLE_BG, bd=0, command=self.show_info)
        info_btn.pack(side='right')

    def create_canvas(self):
        container = tk.Frame(self, bg=STYLE_BG)
        container.pack(fill='both', expand=True)

        self.canvas = tk.Canvas(container, bg=STYLE_BG, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(container, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.inner_frame = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0,0), window=self.inner_frame, anchor='nw')
        self.canvas.bind('<Configure>', self.resize_cards)
        self.canvas.bind_all('<MouseWheel>', lambda e: self.canvas.yview_scroll(-int(e.delta / 120), 'units'))
        self.inner_frame.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))

        self.canvas.pack(side='left', fill='both', expand=True)
        self.scrollbar.pack(side='right', fill='y')

    def show_info(self):
        messagebox.showinfo('说明', '本程序为绿色便携，程序和管理文件可放在 Program Files 下，\n数据库、图标和已删除程序存储在用户目录 AppData，避免权限问题。')

    def load_programs(self):
        for w in self.inner_frame.winfo_children():
            w.destroy()
        cols = max(1, self.canvas.winfo_width() // 206)
        r = 0
        c = 0
        for entry in DB:
            card = ProgramCard(self.inner_frame, entry, self.load_programs)
            card.grid(row=r, column=c, padx=8, pady=8, sticky='n')
            c += 1
            if c >= cols:
                c = 0
                r += 1

    def resize_cards(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)
        cols = max(1, event.width // 206)
        for i, card in enumerate(self.inner_frame.winfo_children()):
            card.grid(row=i // cols, column=i % cols, padx=8, pady=8)

    def add_program(self):
        f = filedialog.askopenfilename(title='选择可执行文件或 .py', filetypes=[('Executables and Python', '*.exe;*.py;*.bat;*.cmd;*.*')])
        if not f:
            return
        sel = Path(f)
        try:
            rel_exec, moved_top = move_into_programs(sel)
        except Exception as e:
            messagebox.showerror('移动失败', str(e))
            return

        pid = uuid.uuid4().hex
        name = sel.stem
        entry = {
            'id': pid,
            'name': name,
            'exec_path': str(rel_exec),
            'icon': '',
            'description': ''
        }
        DB.append(entry)
        save_db(DB)
        self.scan_programs()

    def add_folder(self):
        folder = filedialog.askdirectory(title='选择要收纳的程序文件夹')
        if not folder:
            return
        sel = Path(folder)
        try:
            rel_top, moved_top = move_into_programs(sel)
        except Exception as e:
            messagebox.showerror('移动失败', str(e))
            return

        launchers = find_launchers(moved_top)
        primary = pick_primary_launcher(launchers)
        if not primary:
            messagebox.showwarning('未找到启动文件', '文件夹已移动，但没有发现 .exe/.py/.bat/.cmd 文件。')
            self.load_programs()
            return

        entry = {
            'id': uuid.uuid4().hex,
            'name': moved_top.name,
            'exec_path': rel_to_app(primary),
            'icon': '',
            'description': ''
        }
        DB.append(entry)
        save_db(DB)
        self.scan_programs()

    def scan_programs(self):
        global DB
        backup_db()
        DB, errors = collect(APP_DIR, DB, organize=True)
        save_db(DB)
        self.load_programs()
        messagebox.showinfo('扫描完成', f'已整理更新 {len(DB)} 个程序。' + ('\n未完成：\n' + '\n'.join(errors) if errors else ''))

def main():
    root = tk.Tk()
    if DB_LOAD_ERROR is not None:
        root.withdraw()
        messagebox.showerror('数据读取失败', '已停止启动，未修改原数据。\n' + str(DB_LOAD_ERROR), parent=root)
        root.destroy()
        return
    def report_error(kind, error, traceback):
        if isinstance(error, (DataConflict, ValueError)):
            global DB
            try:
                DB = load_db()
                app.load_programs()
            except (ValueError, OSError):
                pass
        messagebox.showerror('操作未保存', str(error), parent=root)
    root.report_callback_exception = report_error
    app = App(root)
    root.mainloop()

if __name__ == '__main__':
    main()
