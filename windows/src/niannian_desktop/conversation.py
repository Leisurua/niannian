import base64
from datetime import datetime, timezone
import json
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from uuid import uuid4

from .voice_api import VoiceApi
from .voices import VoicePanel


class ConversationSocket:
    def __init__(self, client, family, voice, callback, failed):
        self.client, self.family, self.voice = client, family, voice
        self.callback, self.failed = callback, failed
        self.socket = None
        self.closed = threading.Event()
        self.lock = threading.Lock()
        self.sequence = 0
        self.server_sequence = None
        self.id = None
        self.floor = 0
        threading.Thread(target=self.connect, daemon=True).start()

    def connect(self):
        try:
            from websockets.sync.client import connect
            row = VoiceApi(self.client).request('POST', '/v1/conversations',
                dict(family_id=self.family, input_mode='TEXT', voice_profile_id=self.voice))
            self.id = row['id']
            if self.closed.is_set():
                return
            url = self.client.base_url.replace('https://', 'wss://').replace('http://', 'ws://')
            with connect(url + '/v1/ws/conversations/' + self.id,
                    additional_headers={'Authorization': 'Bearer ' + self.client.access_token},
                    max_size=16384, max_queue=8, open_timeout=10) as socket:
                self.socket = socket
                if self.closed.is_set():
                    return
                first = True
                for raw in socket:
                    if self.closed.is_set():
                        break
                    event = self.validate(raw)
                    if first:
                        if event['type'] != 'session.ready':
                            raise ValueError('Invalid handshake')
                        first = False
                        self.send('session.start', dict(client_session_id=str(uuid4()), input_mode='TEXT',
                            audio_capabilities=['pcm_v1'], voice_profile_id=self.voice))
                    self.callback(event)
        except Exception:
            if not self.closed.is_set():
                self.failed('对话已断开，请检查登录、语音授权和网络，再重新开始。')
        finally:
            self.socket = None

    def validate(self, raw):
        if not isinstance(raw, str) or len(raw.encode('utf-8')) > 16384:
            raise ValueError('Invalid frame')
        value = json.loads(raw)
        sequence = value['sequence']
        if (value['conversation_id'] != self.id or type(sequence) is not int or sequence < 1
                or self.server_sequence is not None and sequence != self.server_sequence + 1):
            raise ValueError('Invalid server sequence')
        self.server_sequence = sequence
        if not isinstance(value['payload'], dict):
            raise ValueError('Invalid payload')
        return value

    def send(self, kind, payload=None):
        with self.lock:
            if not self.socket or self.closed.is_set():
                raise ValueError('尚未连接。')
            self.sequence += 1
            if kind in ('text.input', 'repeat', 'slow_down', 'interrupt', 'session.end'):
                self.floor = self.sequence
            self.socket.send(json.dumps(dict(type=kind, conversation_id=self.id, sequence=self.sequence,
                occurred_at=datetime.now(timezone.utc).isoformat(), payload=payload or {}), ensure_ascii=False))

    def close(self):
        self.closed.set()
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass


class ConversationPanel(VoicePanel):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.connection = None
        self.playback = None
        self.selection_pending = False
        self.voice_allowed = False
        self.profiles = []
        self.slow = False
        self.cloud = tk.BooleanVar(value=False)
        self.title = tk.StringVar(value='念念 AI · 普通声音')
        ttk.Label(self, textvariable=self.title, font=('Microsoft YaHei UI', 16)).pack(anchor='w')
        ttk.Label(self, text='我是念念 AI，不是真实家人。Windows 当前支持打字输入。').pack(anchor='w')
        row = ttk.Frame(self); row.pack(fill='x', pady=8)
        self.choice = ttk.Combobox(row, state='readonly', values=['念念普通声音'], width=28)
        self.choice.current(0); self.choice.pack(side='left')
        self.choice.bind('<<ComboboxSelected>>', lambda _: self.select())
        ttk.Button(row, text='刷新声音', command=self.refresh).pack(side='left')
        ttk.Button(row, text='试听', command=self.preview).pack(side='left')
        ttk.Checkbutton(self, text='允许将回复文本发给阿里云百炼合成声音', variable=self.cloud,
            command=self.consent).pack(anchor='w')
        row = ttk.Frame(self); row.pack(fill='x', pady=8)
        ttk.Button(row, text='允许语音', command=lambda: self.voice_consent(True)).pack(side='left')
        ttk.Button(row, text='撤回全部语音', command=lambda: self.voice_consent(False)).pack(side='left')
        for title, action in [('开始聊天', self.start), ('停止', self.interrupt), ('再说一遍', lambda: self.command('repeat')), ('慢一点', self.slower), ('结束', self.reset)]:
            ttk.Button(row, text=title, command=action).pack(side='left', padx=3)
        self.transcript = scrolledtext.ScrolledText(self, height=14, state='disabled', wrap='word', font=('Microsoft YaHei UI', 15))
        self.transcript.pack(fill='both', expand=True)
        row = ttk.Frame(self); row.pack(fill='x', pady=8)
        self.input = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.input, font=('Microsoft YaHei UI', 14)); entry.pack(side='left', fill='x', expand=True)
        entry.bind('<Return>', lambda _: self.submit())
        ttk.Button(row, text='发送', command=self.submit).pack(side='left')

    def voice_consent(self, allowed):
        if allowed and not messagebox.askyesno('语音授权', '允许念念使用语音朗读？家人音色还需单独同意云端文本处理。您可随时撤回。', parent=self):
            return
        if not allowed:
            self.audio.stop(); self.playback = None; self.voice_allowed = False
        def operation(api, family):
            from urllib.parse import urlencode
            uid = api.client.user['id']
            if allowed:
                return api.request('POST', '/v1/consents', dict(family_id=family, subject_user_id=uid, grantee_user_id=uid, scope='VOICE', source='SETTINGS'))
            query = urlencode(dict(family_id=family, subject_user_id=uid, grantee_user_id=uid, scope='VOICE', limit=100))
            items = api.request('GET', '/v1/consents?' + query).get('items', [])
            latest = max(items, key=lambda r: r['version']) if items else None
            if latest and latest['status'] == 'GRANTED':
                return api.request('POST', '/v1/consents/' + latest['id'] + '/revoke', {})
        self.run(operation, lambda _: self.status.set('语音授权已更新。'))

    def reset(self):
        super().reset()
        if getattr(self, 'connection', None):
            self.connection.close()
        self.connection = None
        self.playback = None
        self.selection_pending = False
        self.voice_allowed = False
        if hasattr(self, 'transcript'):
            self.transcript.configure(state='normal'); self.transcript.delete('1.0', 'end'); self.transcript.configure(state='disabled')
            self.input.set('')
        if hasattr(self, 'title'):
            self.title.set('念念 AI · 普通声音')

    def suspend(self):
        if self.connection:
            self.reset()
            self.status.set('离开窗口已结束聊天；返回后请重新开始。')
        else:
            super().suspend()

    def refresh(self):
        def ready(value):
            result, pref = value
            self.profiles = result.get('items', [])
            self.choice['values'] = ['念念普通声音'] + [row['display_name'] for row in self.profiles]
            selected = next((i + 1 for i, row in enumerate(self.profiles) if row['id'] == pref.get('voice_profile_id')), 0)
            self.choice.current(selected)
            self.cloud.set(pref.get('cloud_tts_allowed', False))
            self.title.set('念念 AI · ' + self.choice.get())
            self.status.set('已读取声音；可在此开启或撤回本人的语音授权。')
        self.run(lambda api, family: (api.profiles(family, True), api.preference(family)), ready)

    def selected(self):
        index = self.choice.current() - 1
        return self.profiles[index]['id'] if 0 <= index < len(self.profiles) else None

    def consent(self):
        if self.cloud.get() and not messagebox.askyesno('回复文本外发', '使用家人音色会将念念的回复文本交给阿里云百炼合成声音，云服务可能保留调用数据。您可以随时关闭，改用普通声音。是否同意？', parent=self):
            self.cloud.set(False)
        if not self.cloud.get():
            self.choice.current(0)
        self.select()

    def select(self):
        self.audio.stop(); self.playback = None
        voice, allowed = self.selected(), self.cloud.get()
        if voice and not allowed:
            self.status.set('请先确认云端文本处理，或选择普通声音。'); return
        self.selection_pending = bool(self.connection)
        def saved(_):
            self.title.set('念念 AI · ' + self.choice.get() + ('（授权合成）' if voice else ''))
            if self.connection:
                self.command('voice.select', {'voice_profile_id': voice})
        self.run(lambda api, family: api.preference(family, voice, allowed), saved)

    def preview(self):
        voice = self.selected()
        if voice:
            self.run(lambda api, _: api.audio(voice, 'preview'), self.audio.preview)
        else:
            self.audio.speak('你好，我是念念 AI 陪伴助手。')

    def start(self):
        if not self.app.client or not self.app.client.access_token or not self.app.selected_family_id:
            self.status.set('请先登录并选择家庭。'); return
        if self.selected() and not self.cloud.get():
            self.status.set('请先同意云端文本处理，或选择普通声音。'); return
        self.reset()
        self.title.set('念念 AI · ' + self.choice.get() + ('（授权合成）' if self.selected() else ''))
        self.status.set('正在连接…')
        epoch = self.epoch
        self.connection = ConversationSocket(self.app.client, self.app.selected_family_id, self.selected(),
            lambda event: self.post(lambda: self.receive(event), epoch),
            lambda message: self.post(lambda: self.failed_connection(message), epoch))

    def failed_connection(self, message):
        self.reset(); self.status.set(message)

    def command(self, kind, payload=None):
        try:
            if not self.connection:
                raise ValueError('请先开始聊天。')
            self.connection.send(kind, payload)
        except Exception:
            self.status.set('尚未连接，请先开始聊天。')

    def append(self, text):
        self.transcript.configure(state='normal')
        self.transcript.insert('end', text + '\n\n')
        if int(self.transcript.index('end-1c').split('.')[0]) > 160:
            self.transcript.delete('1.0', '40.0')
        self.transcript.see('end'); self.transcript.configure(state='disabled')

    def submit(self):
        text = self.input.get().strip()
        if not text or len(text) > 2000 or not self.connection:
            self.status.set('请开始聊天，并输入 1–2000 字。'); return
        self.audio.stop(); self.playback = None
        self.command('text.input', {'text': text, 'timezone': 'Asia/Shanghai', 'speech_rate': 0.8 if self.slow else 1.0})
        self.append('您：' + text); self.input.set('')

    def interrupt(self):
        self.audio.stop(); self.playback = None
        self.command('interrupt')

    def slower(self):
        self.slow = True
        self.audio.stop(); self.playback = None
        self.command('slow_down')

    def receive(self, event):
        if not self.connection:
            return
        kind, payload = event['type'], event['payload']
        if kind == 'voice.selected':
            self.selection_pending = False
            return
        if kind.startswith('tts.') and (self.selection_pending or payload.get('voice_profile_id') != self.selected()):
            return
        if kind == 'voice.permission':
            self.voice_allowed = payload.get('allowed') is True
            if not self.voice_allowed:
                self.audio.stop(); self.playback = None
                self.status.set('语音授权已撤回，已停止所有朗读。')
            return
        if kind == 'session.ready':
            if 'voice_allowed' in payload:
                self.voice_allowed = payload['voice_allowed'] is True
            self.status.set('已连接，可以打字聊天。'); return
        reply = event.get('in_reply_to')
        if reply is not None and (type(reply) is not int or reply < self.connection.floor or reply > self.connection.sequence):
            return
        if kind == 'assistant.text':
            text = payload['text']
            self.append('念念：' + text)
            if self.voice_allowed and payload.get('speech_mode', 'device') == 'device' and reply is not None:
                self.audio.speak(text, self.slow)
        elif kind == 'tts.start' and self.voice_allowed:
            self.playback = payload['playback_id']
            self.audio.begin()
        elif kind == 'tts.chunk' and self.voice_allowed and payload.get('playback_id') == self.playback:
            self.audio.feed(base64.b64decode(payload['audio'], validate=True))
        elif kind == 'tts.end' and payload.get('playback_id') == self.playback:
            self.audio.feed(None)
        elif kind == 'tts.error':
            self.audio.stop(); self.playback = None
            self.status.set('家人声音暂不可用，已切换普通声音。')
            if self.voice_allowed and payload.get('fallback_text'):
                self.audio.speak(payload['fallback_text'], self.slow)
        elif kind == 'warning':
            self.status.set(payload.get('display_text', ''))
        elif kind == 'error':
            self.audio.stop(); self.playback = None
            self.status.set('本次请求未完成，请检查授权或稍后重试。')
