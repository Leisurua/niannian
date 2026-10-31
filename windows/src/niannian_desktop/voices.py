import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .audio import Audio
from .voice_api import VoiceApi


class VoicePanel(ttk.Frame):
    """Shared context/lifecycle for family voice management and elder chat."""
    def __init__(self, parent, app):
        super().__init__(parent, padding=14)
        self.app = app
        self.epoch = 0
        self.context = None
        self.events = queue.Queue(maxsize=32)
        self.disposed = False
        self.pending = False
        self.audio = Audio(lambda text: self.post(lambda: self.status.set(text)))
        self.status = tk.StringVar(value='请登录并选择家庭，再刷新。')
        ttk.Label(self, textvariable=self.status, wraplength=850).pack(fill='x', pady=6)
        self.bind('<Unmap>', lambda event: self.reset() if event.widget == self else None)
        self.bind('<Destroy>', self.dispose)
        self.watch = self.after(100, self.tick)

    def post(self, callback, epoch=None):
        if self.disposed:
            return
        try:
            self.events.put_nowait((self.epoch if epoch is None else epoch, callback))
        except queue.Full:
            self.audio.stop()

    def run(self, operation, done):
        if self.pending:
            self.status.set('正在处理，请稍候。')
            return
        if not self.app.client or not self.app.client.access_token or not self.app.selected_family_id:
            self.status.set('请先登录并选择家庭。')
            return
        self.pending = True
        epoch = self.epoch
        api, family = VoiceApi(self.app.client), self.app.selected_family_id
        def work():
            try:
                value = operation(api, family)
                def success():
                    self.pending = False
                    done(value)
                self.post(success, epoch)
            except Exception:
                self.post(lambda: self.failure('操作未完成，请检查配置、授权和网络后刷新重试。'), epoch)
        threading.Thread(target=work, daemon=True).start()

    def failure(self, message):
        self.pending = False
        self.status.set(message)

    def reset(self):
        self.epoch += 1
        self.pending = False
        self.audio.stop()
        self.audio.frames = bytearray()

    def tick(self):
        context = (id(self.app.client), self.app.selected_family_id,
            bool(self.app.client and self.app.client.access_token), self.app._exit_requested)
        if context != self.context:
            self.reset()
            self.context = context
        if self.winfo_ismapped() and self.app.focus_displayof() is None:
            self.suspend()
        while True:
            try:
                epoch, callback = self.events.get_nowait()
            except queue.Empty:
                break
            if epoch == self.epoch:
                try:
                    callback()
                except Exception:
                    self.status.set('操作失败，请刷新重试。')
        self.watch = self.after(100, self.tick)

    def suspend(self):
        self.audio.stop()

    def dispose(self, event):
        if event.widget == self:
            self.disposed = True
            self.after_cancel(self.watch)
            VoicePanel.reset(self)
            connection = getattr(self, 'connection', None)
            if connection:
                connection.close()
                self.connection = None


class FamilyVoices(VoicePanel):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.profiles, self.members = [], []
        self.sample = None
        ttk.Label(self, text='念念使用家人授权音色，始终是 AI。演示账号不能证明真实身份。', wraplength=850).pack(anchor='w')
        ttk.Label(self, text='请在安静环境，用自然普通话朗读 15–20 秒：\n“你好，我是念念的声音提供者。今天的天气很舒服，我们可以聊聊生活中的小事，也可以一起回忆开心的时光。”', wraplength=850).pack(anchor='w', pady=8)
        row = ttk.Frame(self); row.pack(fill='x')
        ttk.Button(row, text='刷新成员和声音', command=self.refresh).pack(side='left')
        self.owner = ttk.Combobox(row, state='readonly', width=24); self.owner.pack(side='left', padx=8)
        self.name = tk.StringVar()
        ttk.Entry(row, textvariable=self.name, width=18).pack(side='left')
        ttk.Label(row, text='音色名称').pack(side='left')
        row = ttk.Frame(self); row.pack(fill='x', pady=8)
        for title, action in [('开始 / 重录', self.record), ('录完了', self.finish), ('试听录音', self.listen_sample), ('上传待本人确认', self.upload), ('停止', self.audio.stop)]:
            ttk.Button(row, text=title, command=action).pack(side='left', padx=3)
        self.list = tk.Listbox(self, height=9, font=('Microsoft YaHei UI', 12)); self.list.pack(fill='both', expand=True)
        row = ttk.Frame(self); row.pack(fill='x', pady=8)
        for title, action in [('试听原录音', lambda: self.preview('sample')), ('本人授权制作', self.approve), ('试听合成', lambda: self.preview('preview')), ('满意，发布', lambda: self.mutate('activate')), ('撤回 / 删除', self.revoke)]:
            ttk.Button(row, text=title, command=action).pack(side='left', padx=3)

    def reset(self):
        super().reset()
        self.sample = None
        if hasattr(self, 'list'):
            self.list.delete(0, 'end')
            self.profiles, self.members = [], []
            self.owner.set(''); self.owner['values'] = []

    def suspend(self):
        super().suspend()
        self.sample = None
        self.audio.frames = bytearray()

    def refresh(self):
        def show(value):
            self.members, result = value
            self.profiles = result.get('items', [])
            self.owner['values'] = [row.get('display_name', row['user_id']) for row in self.members]
            if self.members:
                mine = str(self.app.client.user['id'])
                self.owner.current(next((i for i, row in enumerate(self.members) if str(row['user_id']) == mine), 0))
            self.list.delete(0, 'end')
            for row in self.profiles:
                self.list.insert('end', f"{row['display_name']} · {row['status']}")
            self.status.set('已刷新。制作中请稍后刷新；只有声音本人能授权和发布。')
        self.run(lambda api, family: (api.members(family), api.profiles(family)), show)

    def selected(self):
        selection = self.list.curselection()
        return self.profiles[selection[0]] if selection else None

    def record(self):
        try:
            self.sample = None
            self.audio.record()
            self.status.set('正在录音，15–20 秒后点击“录完了”；最长 60 秒。')
        except Exception:
            self.status.set('无法录音，请检查麦克风权限与设备，或安装 sounddevice。')

    def finish(self):
        try:
            self.sample = self.audio.finish_recording()
            self.status.set('录音完成，可试听或上传。')
        except ValueError as exc:
            self.status.set(str(exc))

    def listen_sample(self):
        if self.sample:
            self.audio.preview(self.sample)

    def upload(self):
        if not self.sample or self.owner.current() < 0:
            self.status.set('请先选择声音主人并录音。'); return
        sample = self.sample
        owner = self.members[self.owner.current()]['user_id']
        name = self.name.get().strip() or self.owner.get()
        if not messagebox.askyesno('私密上传', '录音将私密上传至念念服务器，供声音本人确认，未确认最多保存 7 天。确认前不发送给声音云服务。', parent=self):
            return
        def upload(api, family):
            row = api.request('POST', '/v1/voice-profiles', dict(family_id=family, owner_user_id=owner, display_name=name))
            return api.audio(row['id'], 'sample', sample)
        self.run(upload, lambda _: self.uploaded())

    def uploaded(self):
        self.sample = None
        self.refresh()

    def preview(self, kind):
        row = self.selected()
        if row:
            self.run(lambda api, _: api.audio(row['id'], kind), self.audio.preview)

    def approve(self):
        if messagebox.askyesno('声音本人授权', '仅声音本人确认：允许将这次录音交给阿里云百炼制作音色，供本家庭当前及以后加入的老人使用。念念仍是 AI，可随时撤回。云服务可能留存调用数据，删除音色不代表所有副本已删除。', parent=self):
            self.mutate('approve')

    def mutate(self, action):
        row = self.selected()
        if row:
            self.run(lambda api, _: api.request('POST', f"/v1/voice-profiles/{row['id']}/{action}", {}), lambda _: self.refresh())

    def revoke(self):
        row = self.selected()
        if row and messagebox.askyesno('撤回声音', '立即停用所选音色，并安排清理录音与云端音色。', parent=self):
            self.run(lambda api, _: api.request('DELETE', f"/v1/voice-profiles/{row['id']}"), lambda _: self.refresh())
