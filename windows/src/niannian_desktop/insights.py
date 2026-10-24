"""Shared weather and weekly report view. All displayed data stays in memory."""
import tkinter as tk
from datetime import datetime, timedelta, timezone
from tkinter import scrolledtext, ttk

from niannian_desktop.api import ClientError


class InsightsPanel(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=16)
        self.app = app
        self.cities, self.subjects = [], []
        self.context = None
        self.generation = 0
        self.expiry = None
        self.weather_expiry = None
        self.watch = None
        weather = ttk.LabelFrame(self, text='城市天气 · Open-Meteo', padding=10)
        weather.pack(fill='x')
        ttk.Label(weather, text='手动选择关注城市；城市名发送至 Open-Meteo，不读取设备位置。').pack(anchor='w')
        row = ttk.Frame(weather)
        row.pack(fill='x', pady=6)
        self.city_query = tk.StringVar()
        ttk.Entry(row, textvariable=self.city_query, width=18).pack(side='left')
        ttk.Button(row, text='搜索城市', command=self.search_city).pack(side='left', padx=6)
        self.city_choice = ttk.Combobox(row, state='readonly', width=25)
        self.city_choice.pack(side='left')
        ttk.Button(row, text='查询 / 刷新天气', command=self.weather).pack(side='left', padx=6)
        self.weather_text = tk.StringVar(value='请选择城市。')
        ttk.Label(weather, textvariable=self.weather_text, wraplength=750).pack(anchor='w')
        report = ttk.LabelFrame(self, text='统计与周报 · 交流观察线索', padding=10)
        report.pack(fill='both', expand=True, pady=(12, 0))
        row = ttk.Frame(report)
        row.pack(fill='x')
        ttk.Button(row, text='读取长辈列表', command=self.load_subjects).pack(side='left')
        self.subject_choice = ttk.Combobox(row, state='readonly', width=14)
        self.subject_choice.pack(side='left', padx=6)
        self.subject_choice.bind('<<ComboboxSelected>>', lambda _: self.clear_report())
        monday = datetime.now(timezone(timedelta(hours=8))).date()
        monday -= timedelta(days=monday.weekday())
        self.week = ttk.Combobox(row, state='readonly', width=11, values=[str(monday - timedelta(weeks=i)) for i in range(4)])
        self.week.current(0)
        self.week.pack(side='left')
        self.week.bind('<<ComboboxSelected>>', lambda _: self.clear_report())
        self.reason = ttk.Combobox(row, state='readonly', width=10, values=['关心近况', '跟进交流'])
        self.reason.pack(side='left', padx=6)
        ttk.Button(row, text='生成周报', command=self.report).pack(side='left')
        ttk.Label(report, text='需长辈开启本人统计并向家属授权；可在 Android 家庭设置中管理。页面离开或 30 秒后清除报告，请刷新复验权限。',
            wraplength=780).pack(anchor='w', pady=8)
        self.report_text = scrolledtext.ScrolledText(report, wrap='word', font=('Microsoft YaHei UI', 11), height=12, state='disabled')
        self.report_text.pack(fill='both', expand=True)
        self.bind('<Unmap>', lambda _: self.clear())
        self.bind('<Destroy>', self.dispose)
        self.observe()

    def dispose(self, event):
        if event.widget == self:
            for handle in (self.watch, self.expiry, self.weather_expiry):
                if handle:
                    self.after_cancel(handle)
            self.generation += 1

    def observe(self):
        context = (id(self.app.client), self.app.selected_family_id,
            bool(self.app.client and self.app.client.access_token), self.app._exit_requested)
        if context != self.context:
            self.clear()
            self.context = context
            self.subjects = []; self.subject_choice.set(''); self.subject_choice['values'] = []
            self.cities = []; self.city_choice.set(''); self.city_choice['values'] = []
            self.city_query.set(''); self.reason.set('')
        if self.winfo_ismapped() and self.app.focus_displayof() is None:
            self.clear()
        self.watch = self.after(1000, self.observe)

    def clear_report(self):
        self.generation += 1
        self.set_report('')
        if self.expiry:
            self.after_cancel(self.expiry)
            self.expiry = None

    def clear(self):
        self.clear_report()
        if self.weather_expiry:
            self.after_cancel(self.weather_expiry)
            self.weather_expiry = None
        self.weather_text.set('请选择城市并刷新天气。')

    def set_report(self, value):
        self.report_text.configure(state='normal')
        self.report_text.delete('1.0', 'end')
        self.report_text.insert('1.0', value)
        self.report_text.configure(state='disabled')

    def run(self, label, operation, success):
        if self.app.busy:
            return
        try:
            client = self.app._require_client()
        except ClientError as error:
            self.app._show_error(error)
            return
        generation = self.generation
        family = self.app.selected_family_id
        def accept(value):
            if (self.winfo_exists() and self.winfo_ismapped() and generation == self.generation
                    and family == self.app.selected_family_id and client is self.app.client):
                success(value)
        self.app._run(label, lambda: operation(client), accept)

    def search_city(self):
        query = self.city_query.get().strip()
        if not 2 <= len(query) <= 80:
            self.weather_text.set('请输入 2—80 个字符的城市名。')
            return
        self.clear()
        self.cities = []; self.city_choice['values'] = []; self.city_choice.set('')
        def show(items):
            self.cities = items
            self.city_choice['values'] = [city['label'] for city in items]
            self.weather_text.set('请选择搜索结果，再查询天气。' if items else '未找到城市，请尝试拼音。')
        self.run('搜索城市', lambda client: client.weather_cities(query), show)

    def weather(self):
        index = self.city_choice.current()
        self.clear()
        if not 0 <= index < len(self.cities):
            return
        city = self.cities[index]
        def show(value):
            stamp = datetime.fromisoformat(value['observed_at']).astimezone(timezone(timedelta(seconds=value['utc_offset_seconds'])))
            self.weather_text.set(f"{city['label']} · {value['temperature_c']}°C · {value['description']}\n"
                f"数据时间：{stamp:%m-%d %H:%M %z}；来源：Open-Meteo（https://open-meteo.com/）")
            remaining = max(0, (stamp + timedelta(hours=3) - datetime.now(timezone.utc)).total_seconds())
            self.weather_expiry = self.after(int(min(900, remaining) * 1000),
                lambda: self.weather_text.set('天气需要更新，请点击刷新。'))
        self.run('读取天气', lambda client: client.weather_current(city['id']), show)

    def load_subjects(self):
        family = self.app.selected_family_id
        self.clear_report()
        if not family:
            self.set_report('请先登录并选择家庭。')
            return
        self.subjects = []; self.subject_choice.set(''); self.subject_choice['values'] = []
        def show(items):
            self.subjects = items
            self.subject_choice['values'] = [item.get('display_name', '长辈') for item in items]
            if items:
                self.subject_choice.current(0)
            else:
                self.set_report('当前家庭暂无可选长辈。')
        self.run('读取长辈', lambda client: client.report_subjects(family), show)

    def report(self):
        self.clear_report()
        index = self.subject_choice.current()
        if not 0 <= index < len(self.subjects):
            self.set_report('请先读取并选择长辈。')
            return
        elder = self.app.client and self.app.client.login_kind == 'elder'
        reasons = {'关心近况': 'FAMILY_CHECK_IN', '跟进交流': 'FOLLOW_UP'}
        reason = None if elder else reasons.get(self.reason.get())
        if not elder and reason is None:
            self.set_report('请选择本次查看理由。')
            return
        family, owner, week = self.app.selected_family_id, self.subjects[index]['id'], self.week.get()
        def show(value):
            self.set_report(value['text'])
            self.expiry = self.after(30_000, self.clear_report)
        self.run('生成周报', lambda client: client.weekly_report(family, owner, week, reason), show)
