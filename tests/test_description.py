# -*- coding: utf-8 -*-
import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import 小程序集合 as suite

class DescriptionTests(unittest.TestCase):
    def test_context_edit_save_cancel_and_double_click(self):
        with tempfile.TemporaryDirectory(prefix='中文 简介 ') as tmp:
            root = tk.Tk()
            root.withdraw()
            entry = {'id': 'test', 'name': '测试', 'exec_path': 'test.cmd', 'description': '', 'icon': ''}
            with patch.object(suite, 'DB', [entry]), patch.object(suite, 'DB_FILE', Path(tmp) / '简介.json'), \
                 patch.object(suite, 'BACKUP_DIR', Path(tmp)), patch.object(suite, 'system_icon', return_value=None):
                suite.load_db()  # 初始化当前临时数据库的读取快照
                card = suite.ProgramCard(root, entry, lambda: None)
                self.assertEqual(card.desc_label.cget('text'), '')
                binding = card.desc_label.bind('<Double-Button-1>')
                self.assertIn('run_program', binding)
                self.assertNotIn('edit_description', binding)
                with patch.object(suite.tk, 'Menu') as factory:
                    card.open_context_menu(SimpleNamespace(x_root=0, y_root=0))
                    commands = {call.kwargs['label']: call.kwargs['command'] for call in factory.return_value.add_command.call_args_list}
                    self.assertIn('编辑简介', commands)
                    with patch.object(suite.simpledialog, 'askstring', return_value='中文简介测试'):
                        commands['编辑简介']()
                self.assertEqual(json.loads(suite.DB_FILE.read_text(encoding='utf-8'))[0]['description'], '中文简介测试')
                with patch.object(suite.simpledialog, 'askstring', return_value=None):
                    card.edit_description()
                self.assertEqual(entry['description'], '中文简介测试')
            root.destroy()
