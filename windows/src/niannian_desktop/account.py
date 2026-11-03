"""Self-service account operations; saved receipt remains usable without login."""
import json
import re
import secrets
import tkinter as tk
from contextlib import contextmanager
from tempfile import NamedTemporaryFile
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, simpledialog

from niannian_desktop.api import ApiClient, ApiError, normalize_base_url


def receipt_text(value):
    providers = value.get('providers', [])
    complete = (value.get('status') == 'COMPLETED' and value.get('local_status') == 'ERASED'
        and value.get('backup', {}).get('status') == 'CONFIRMED'
        and all(p.get('status') == 'CONFIRMED' for p in providers))
    lines = ['全部删除已核验完成' if complete else '删除尚未全部完成',
        '服务端本地数据：' + ('已清理' if value.get('local_status') == 'ERASED' else '处理中 / 待重试'),
        '备份：' + ('已核验' if value.get('backup', {}).get('status') == 'CONFIRMED' else '未核验，仍未完成')]
    for p in providers:
        lines.append('供应商 ' + str(p.get('provider', '')) + '：' + ('已核验' if p.get('status') == 'CONFIRMED' else '未核验，仍未完成'))
    if value.get('backup', {}).get('overdue'):
        lines.append('备份核验已超期，仍需处理。')
    if value.get('last_error_code'):
        lines.append('服务端清理需重试：' + str(value['last_error_code']))
    lines.extend([value.get('retained', ''), value.get('device_notice', '')])
    return '\n'.join(lines)


def read_receipt(path):
    if Path(path).stat().st_size > 4096:
        raise ValueError('凭证文件过大')
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    value['server'] = normalize_base_url(value['server'])
    if not re.fullmatch(r'[A-Za-z0-9_-]{43,128}', value['receipt_token']):
        raise ValueError('无效凭证')
    return value


@contextmanager
def save_file(path):
    destination = Path(path)
    output = NamedTemporaryFile(dir=destination.parent, delete=False)
    temporary = Path(output.name)
    try:
        with output:
            yield output
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


class AccountWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.receipt = None
        self.resume_polling = app.polling
        app._stop_polling()
        self.title('本人数据管理')
        self.geometry('700x560')
        self.transient(app)
        self.grab_set()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.status = tk.StringVar(value='导出仅含本人可访问的数据。删除账户不可撤销，其他人的共享记录可能保留。')
        ttk.Label(self, textvariable=self.status, wraplength=650).pack(fill='x', padx=20, pady=20)
        self.progress = ttk.Progressbar(self, mode='indeterminate')
        self.progress.pack(fill='x', padx=20)
        for title, command in [('导出并保存 ZIP', self.export), ('删除我的账户', self.delete),
                ('打开独立凭证 / 查询删除进度', self.lookup)]:
            ttk.Button(self, text=title, command=command).pack(fill='x', padx=20, pady=10)
        self.refresh = ttk.Button(self, text='刷新删除进度', command=self.query, state='disabled')
        self.refresh.pack(fill='x', padx=20, pady=10)
        ttk.Label(self, text='独立凭证等同查询权限，请妥善保管。查询不需要登录；供应商及备份未核验时仍显示未完成。', wraplength=650).pack(padx=20, pady=10)

    def close(self):
        if not self.app.busy:
            self.destroy()
            if self.resume_polling:
                self.app._toggle_polling()

    def run(self, label, operation, deleted=False):
        if self.app.busy:
            return
        self.status.set(label + '…')
        self.progress.start()
        def work():
            try:
                return True, operation()
            except Exception:
                return False, None
        def done(result):
            self.progress.stop()
            if deleted:
                self.app.client = None
                self.app._reset_session_view()
            ok, value = result
            if not deleted and self.app.client and not self.app.client.access_token:
                self.app._reset_session_view()
            self.status.set(value if ok else ('删除结果未确认，本机已退出。请用已保存的独立凭证查询。' if deleted else '操作未完成，请检查网络、登录或凭证后重试。'))
        self.app._run(label, work, done)

    def export(self):
        if self.app.busy:
            return
        client = self.app.client
        if not client or not client.access_token:
            self.status.set('请先登录本人账户。'); return
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.zip', initialfile='niannian-account.zip')
        if path:
            def work():
                with save_file(path) as output:
                    client.export_account(output)
                return '本人数据已下载并保存。导出文件由您保管。'
            self.run('生成并下载导出文件', work)

    def delete(self):
        if self.app.busy:
            return
        client = self.app.client
        if not client or not client.user:
            self.status.set('请先登录本人账户。'); return
        name = client.user.get('display_name') or '当前本人账户'
        if not messagebox.askyesno('删除账户', f'将删除「{name}」并撤销全部登录。此操作不可撤销。继续保存查询凭证？', parent=self):
            return
        receipt = dict(server=client.base_url, receipt_token=secrets.token_urlsafe(32))
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.json', initialfile='niannian-deletion-receipt.json')
        if not path:
            return
        try:
            with save_file(path) as output:
                output.write(json.dumps(receipt).encode('utf-8'))
        except OSError:
            self.status.set('凭证未保存，未提交删除。'); return
        if simpledialog.askstring('再次确认本人删除', '请输入“删除我的账户”确认不可撤销的删除。', parent=self) != '删除我的账户':
            return
        self.receipt = receipt
        self.refresh.configure(state='normal')
        self.app._stop_polling()
        self.app.tasks.invalidate()
        for name in ('voice_panel', 'insights'):
            panel = getattr(self.app, name, None)
            if panel and panel.winfo_exists() and hasattr(panel, 'reset'):
                panel.reset()
            elif panel and panel.winfo_exists() and hasattr(panel, 'clear'):
                panel.clear()
        self.app._clear_message_view()
        for name in ('conversation_window', 'insights_window'):
            window = getattr(self.app, name, None)
            if window and window.winfo_exists():
                window.destroy()
        self.run('提交账户删除', lambda: receipt_text(client.delete_account(receipt['receipt_token'])), deleted=True)

    def lookup(self):
        if self.app.busy:
            return
        path = filedialog.askopenfilename(parent=self, filetypes=[('删除查询凭证', '*.json')])
        if not path:
            return
        try:
            receipt = read_receipt(path)
        except Exception:
            self.status.set('凭证文件无效，无法查询。'); return
        if not messagebox.askyesno('确认查询服务器', '将凭证发送到：' + receipt['server'] + '\n仅在确认这是原删除服务器时继续。', parent=self):
            return
        self.receipt = receipt
        self.refresh.configure(state='normal')
        self.query()

    def query(self):
        receipt = self.receipt
        if not receipt:
            return
        def work():
            try:
                return receipt_text(ApiClient(receipt['server']).deletion_receipt(receipt['receipt_token']))
            except ApiError as error:
                if error.status == 404:
                    return '未找到删除回执。请核对凭证和服务器。若提交结果未确认，请稍后再查，确认未受理后可重新登录。'
                if error.status == 429:
                    return '查询过于频繁，请稍后再试。'
                raise
        self.run('查询删除进度', work)


def open_account(app):
    if app.busy:
        return
    AccountWindow(app)
