from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from typing import Any, Callable

from niannian_desktop.settings import load_base_url, save_base_url
from niannian_desktop.tasks import BackgroundTasks

from .api import ApiError, ClientError, NetworkError, NianNianClient

BG = "#F5F3EE"
CARD = "#FFFFFF"
INK = "#24352F"
MUTED = "#66756F"
GREEN = "#2E6B57"
LIGHT_GREEN = "#DCEBE4"
AMBER = "#A86518"
RED = "#A53B32"


class FamilyClientApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("念念 · Windows 子女端")
        self.geometry("1120x760")
        self.minsize(920, 650)
        self.configure(bg=BG)
        self.client: NianNianClient | None = None
        self.families: list[dict[str, Any]] = []
        self.messages: dict[str, dict[str, Any]] = {}
        self.selected_family_id: str | None = None
        self.tasks = BackgroundTasks()
        self.busy = False
        self.polling = False
        self._poll_after_id: str | None = None
        self._configure_styles()
        self._build_ui()
        self._load_settings()
        self.after(80, self._drain_tasks)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("Title.TLabel", background=BG, foreground=INK, font=("Microsoft YaHei UI", 22, "bold"))
        style.configure("Sub.TLabel", background=BG, foreground=MUTED, font=("Microsoft YaHei UI", 10))
        style.configure("CardTitle.TLabel", background=CARD, foreground=INK, font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("Card.TLabel", background=CARD, foreground=INK, font=("Microsoft YaHei UI", 10))
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(14, 8))
        style.configure("TButton", font=("Microsoft YaHei UI", 9), padding=(10, 7))
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=("Microsoft YaHei UI", 10), padding=(18, 9))
        style.configure("Treeview", font=("Microsoft YaHei UI", 9), rowheight=30)
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=(28, 22, 28, 8))
        header.pack(fill="x")
        ttk.Label(header, text="念念", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="Windows 子女端 · 课堂联机版", style="Sub.TLabel").pack(side="left", padx=(12, 0), pady=(10, 0))
        self.status = tk.Label(header, text="未连接", bg="#EEE2CA", fg=AMBER, padx=13, pady=7,
                               font=("Microsoft YaHei UI", 9, "bold"))
        self.status.pack(side="right")

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=28, pady=(8, 10))
        self.connect_tab = ttk.Frame(self.tabs, padding=18)
        self.family_tab = ttk.Frame(self.tabs, padding=18)
        self.message_tab = ttk.Frame(self.tabs, padding=18)
        self.tabs.add(self.connect_tab, text=" 连接与登录 ")
        self.tabs.add(self.family_tab, text=" 家庭与设备 ")
        self.tabs.add(self.message_tab, text=" 消息 ")
        self._build_connect_tab()
        self._build_family_tab()
        self._build_message_tab()

        log_card = ttk.Frame(self, style="Card.TFrame", padding=(14, 8))
        log_card.pack(fill="x", padx=28, pady=(0, 22))
        self.log_text = tk.Text(log_card, height=4, bg=CARD, fg=MUTED, relief="flat", state="disabled",
                                font=("Consolas", 9), wrap="word")
        self.log_text.pack(fill="x")

    def _card(self, parent: tk.Widget, *, padding: int = 18) -> ttk.Frame:
        return ttk.Frame(parent, style="Card.TFrame", padding=padding)

    def _build_connect_tab(self) -> None:
        left = self._card(self.connect_tab)
        left.pack(side="left", fill="both", expand=True, padx=(0, 9))
        right = self._card(self.connect_tab)
        right.pack(side="left", fill="both", expand=True, padx=(9, 0))

        ttk.Label(left, text="服务器连接", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(left, text="填写 API 根地址；不要在末尾添加 /v1。", style="Muted.TLabel").pack(anchor="w", pady=(4, 14))
        self.url_var = tk.StringVar(value="http://127.0.0.1:8000")
        ttk.Entry(left, textvariable=self.url_var, font=("Consolas", 11)).pack(fill="x", pady=(0, 12))
        row = ttk.Frame(left, style="Card.TFrame")
        row.pack(fill="x")
        ttk.Button(row, text="测试连接", command=self.test_connection).pack(side="left")
        ttk.Button(row, text="登录演示子女", style="Accent.TButton", command=self.login).pack(side="left", padx=8)
        ttk.Label(left, text="演示账号：demo-child（仅 Mock 环境可用）", style="Muted.TLabel").pack(anchor="w", pady=(16, 0))
        self.identity_label = ttk.Label(left, text="当前未登录", style="Card.TLabel")
        self.identity_label.pack(anchor="w", pady=(6, 0))

        ttk.Label(right, text="连接状态", style="CardTitle.TLabel").pack(anchor="w")
        self.probe_output = scrolledtext.ScrolledText(right, height=13, bg="#FAFBF9", fg=INK, relief="flat",
                                                       font=("Microsoft YaHei UI", 9), wrap="word")
        self.probe_output.pack(fill="both", expand=True, pady=(12, 0))
        self.probe_output.insert("1.0", "点击“测试连接”查看服务器状态。当前 main 提供登录、家庭和邀请；消息及设备注册 API 尚未实现。")
        self.probe_output.configure(state="disabled")

    def _build_family_tab(self) -> None:
        left = self._card(self.family_tab)
        left.pack(side="left", fill="both", expand=True, padx=(0, 9))
        right = self._card(self.family_tab)
        right.pack(side="left", fill="both", expand=True, padx=(9, 0))
        ttk.Label(left, text="我的家庭", style="CardTitle.TLabel").pack(anchor="w")
        actions = ttk.Frame(left, style="Card.TFrame")
        actions.pack(fill="x", pady=10)
        self.family_name_var = tk.StringVar(value="念念演示家庭")
        ttk.Entry(actions, textvariable=self.family_name_var).pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="创建", command=self.create_family).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="刷新", command=self.refresh_families).pack(side="left", padx=(8, 0))
        self.family_list = tk.Listbox(left, bg="#FAFBF9", fg=INK, relief="flat", highlightthickness=0,
                                      selectbackground=GREEN, font=("Microsoft YaHei UI", 10), activestyle="none")
        self.family_list.pack(fill="both", expand=True)
        self.family_list.bind("<<ListboxSelect>>", self._family_selected)

        ttk.Label(right, text="设备与邀请", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(right, text="先选择家庭，再注册本机或生成老人端邀请。", style="Muted.TLabel").pack(anchor="w", pady=(4, 10))
        buttons = ttk.Frame(right, style="Card.TFrame")
        buttons.pack(fill="x")
        ttk.Button(buttons, text="注册本机为子女端", command=self.register_device).pack(side="left")
        ttk.Button(buttons, text="生成老人端邀请", command=self.create_elder_invite).pack(side="left", padx=8)
        self.binding_label = ttk.Label(right, text="本会话尚未绑定设备", style="Muted.TLabel")
        self.binding_label.pack(anchor="w", pady=(10, 6))
        self.invite_text = tk.Text(right, height=5, bg="#FAFBF9", fg=INK, relief="flat", font=("Consolas", 9), wrap="word")
        self.invite_text.pack(fill="x", pady=(0, 10))
        ttk.Button(right, text="复制邀请令牌", command=self.copy_invite).pack(anchor="w", pady=(0, 10))
        self.device_tree = ttk.Treeview(right, columns=("kind", "state", "seen"), show="headings", height=8)
        for key, label, width in (("kind", "端类型", 135), ("state", "状态", 75), ("seen", "最后在线", 180)):
            self.device_tree.heading(key, text=label)
            self.device_tree.column(key, width=width, anchor="w")
        self.device_tree.pack(fill="both", expand=True)

    def _build_message_tab(self) -> None:
        composer = self._card(self.message_tab)
        composer.pack(fill="x", pady=(0, 10))
        ttk.Label(composer, text="给家中老人留言", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w")
        self.message_var = tk.StringVar(value="我晚些给您打电话，记得按时吃饭。")
        ttk.Entry(composer, textvariable=self.message_var, font=("Microsoft YaHei UI", 10)).grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.priority_var = tk.StringVar(value="NORMAL")
        ttk.Combobox(composer, textvariable=self.priority_var, values=("NORMAL", "IMPORTANT"), width=12,
                     state="readonly").grid(row=1, column=1, padx=8, pady=(10, 0))
        ttk.Button(composer, text="发送", style="Accent.TButton", command=self.send_message).grid(row=1, column=2, pady=(10, 0))
        ttk.Button(composer, text="刷新收发箱", command=self.refresh_messages).grid(row=1, column=3, padx=(8, 0), pady=(10, 0))
        composer.columnconfigure(0, weight=1)

        table_card = self._card(self.message_tab, padding=10)
        table_card.pack(fill="both", expand=True)
        self.message_tree = ttk.Treeview(table_card, columns=("box", "time", "priority", "text", "delivery"), show="headings")
        specs = (("box", "方向", 70), ("time", "时间", 155), ("priority", "优先级", 80),
                 ("text", "内容", 420), ("delivery", "投递", 170))
        for key, label, width in specs:
            self.message_tree.heading(key, text=label)
            self.message_tree.column(key, width=width, anchor="w")
        self.message_tree.pack(fill="both", expand=True)
        bottom = ttk.Frame(table_card, style="Card.TFrame")
        bottom.pack(fill="x", pady=(8, 0))
        ttk.Button(bottom, text="将选中收件标为已读", command=self.mark_selected_read).pack(side="left")
        self.auto_poll_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bottom, text="每 3 秒自动刷新", variable=self.auto_poll_var,
                        command=self._toggle_polling).pack(side="right")

    def _run(self, label: str, operation: Callable[[], Any], success: Callable[[Any], None] | None = None) -> None:
        if self.busy:
            self._log("当前操作尚未完成，请稍候。")
            return
        self.busy = True
        self.status.configure(text=label + "…", bg="#EEE2CA", fg=AMBER)

        self.tasks.submit(label, operation, success)

    def _drain_tasks(self) -> None:
        for ok, value, success, label in self.tasks.drain():
            self.busy = False
            if ok:
                self.status.configure(text="已连接", bg=LIGHT_GREEN, fg=GREEN)
                self._log(label + "完成。")
                if success:
                    success(value)
            else:
                self.status.configure(text="操作失败", bg="#F4DAD6", fg=RED)
                self._show_error(value)
        self.after(80, self._drain_tasks)

    def _show_error(self, exc: Exception) -> None:
        if isinstance(exc, NetworkError):
            hint = "\n\n若服务器在 VMware Kali 中：当前主机必须能访问虚拟机 IP，或先配置 NAT 端口转发。"
        elif isinstance(exc, ApiError) and exc.status == 429:
            hint = "\n\n登录请求过多，请等待约 60 秒再试。"
        else:
            hint = ""
        message = str(exc) + hint
        self._log("失败：" + message.replace("\n", " "))
        messagebox.showerror("操作未完成", message, parent=self)

    def _log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def test_connection(self) -> None:
        base_url = self.url_var.get()

        def operation() -> dict[str, Any]:
            client = NianNianClient(base_url)
            health = client.health()
            return {"client": client, "health": health}

        def success(result: dict[str, Any]) -> None:
            self.client = result["client"]
            self._save_settings()
            self.probe_output.configure(state="normal")
            self.probe_output.delete("1.0", "end")
            self.probe_output.insert("1.0", f"HTTP：/health 正常\n环境：{result['health'].get('environment', 'unknown')}\n"
                                     f"请求编号：{result['health'].get('request_id', '-')}")
            self.probe_output.configure(state="disabled")

        self._run("连接检查", operation, success)

    def login(self) -> None:
        base_url = self.url_var.get()

        def operation() -> tuple[NianNianClient, dict[str, Any]]:
            client = NianNianClient(base_url)
            return client, client.login("demo-child")

        def success(result: tuple[NianNianClient, dict[str, Any]]) -> None:
            self.client, payload = result
            user = payload["user"]
            self.identity_label.configure(text=f"已登录：{user['display_name']}  ·  {user['id']}")
            self._save_settings()
            self.refresh_families()

        self._run("登录", operation, success)

    def _require_client(self) -> NianNianClient:
        if not self.client or not self.client.access_token:
            raise ClientError("请先在“连接与登录”页登录。")
        return self.client

    def refresh_families(self) -> None:
        def success(items: list[dict[str, Any]]) -> None:
            self.families = items
            self.family_list.delete(0, "end")
            for item in items:
                self.family_list.insert("end", f"{item.get('name', '未命名家庭')}  ·  {item.get('role', '-')}")
            if items:
                self.family_list.selection_set(0)
                self._family_selected()
            else:
                self.selected_family_id = None
                self._log("当前账号还没有家庭，可创建“念念演示家庭”。")

        try:
            client = self._require_client()
        except ClientError as exc:
            self._show_error(exc)
            return
        self._run("刷新家庭", client.list_families, success)

    def create_family(self) -> None:
        name = self.family_name_var.get().strip()
        if not name:
            self._show_error(ClientError("家庭名称不能为空。"))
            return
        try:
            client = self._require_client()
        except ClientError as exc:
            self._show_error(exc)
            return
        self._run("创建家庭", lambda: client.create_family(name), lambda _: self.refresh_families())

    def _family_selected(self, _event: Any = None) -> None:
        selection = self.family_list.curselection()
        if not selection or selection[0] >= len(self.families):
            return
        self.selected_family_id = str(self.families[selection[0]]["id"])
        self.refresh_devices()

    def register_device(self) -> None:
        try:
            client = self._require_client()
            family_id = self.selected_family_id or ""
            if not family_id:
                raise ClientError("请先选择一个家庭。")
        except ClientError as exc:
            self._show_error(exc)
            return

        def success(binding: dict[str, Any]) -> None:
            self.binding_label.configure(text=f"已绑定：{binding['id']}  ·  {binding['client_kind']}")
            self.refresh_devices()

        self._run("注册设备", lambda: client.register_family_device(family_id), success)

    def refresh_devices(self) -> None:
        if not self.client or not self.client.access_token or not self.selected_family_id:
            return

        def success(items: list[dict[str, Any]]) -> None:
            for item in self.device_tree.get_children():
                self.device_tree.delete(item)
            for item in items:
                if str(item.get("family_id")) == self.selected_family_id:
                    self.device_tree.insert("", "end", values=(item.get("client_kind"), item.get("status"), item.get("last_seen_at", "-")))

        self._run("刷新设备", self.client.list_devices, success)

    def create_elder_invite(self) -> None:
        try:
            client = self._require_client()
            family_id = self.selected_family_id or ""
            if not family_id:
                raise ClientError("请先选择一个家庭。")
        except ClientError as exc:
            self._show_error(exc)
            return

        def success(invite: dict[str, Any]) -> None:
            self.invite_text.delete("1.0", "end")
            self.invite_text.insert("1.0", str(invite["token"]))
            self._log("老人端邀请已生成，有效期 1 小时；令牌只应交给测试老人端。")

        self._run("生成邀请", lambda: client.create_invitation(family_id), success)

    def copy_invite(self) -> None:
        token = self.invite_text.get("1.0", "end").strip()
        if not token:
            self._show_error(ClientError("当前没有可复制的邀请令牌。"))
            return
        self.clipboard_clear()
        self.clipboard_append(token)
        self._log("邀请令牌已复制到剪贴板。")

    def send_message(self) -> None:
        try:
            client = self._require_client()
            if not client.binding:
                raise ClientError("请先在“家庭与设备”页注册本机。")
            text = self.message_var.get().strip()
            if not text:
                raise ClientError("消息内容不能为空。")
        except ClientError as exc:
            self._show_error(exc)
            return

        def success(message: dict[str, Any]) -> None:
            count = len(message.get("deliveries", []))
            if count:
                self._log(f"消息已进入服务器队列，共 {count} 个目标设备。")
            else:
                messagebox.showwarning("已接收但尚无投递目标", "服务器已接收消息，但当前家庭没有已注册的老人端设备。", parent=self)
            self.refresh_messages()

        priority = self.priority_var.get()
        self._run("发送消息", lambda: client.send_text_to_role(text, "ELDER", priority), success)

    def refresh_messages(self) -> None:
        try:
            client = self._require_client()
            if not client.binding:
                raise ClientError("请先注册本机设备。")
        except ClientError as exc:
            if not self.polling:
                self._show_error(exc)
            return

        def operation() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            return client.list_messages("INBOX"), client.list_messages("OUTBOX")

        def success(result: tuple[list[dict[str, Any]], list[dict[str, Any]]]) -> None:
            inbox, outbox = result
            self.messages.clear()
            for item in self.message_tree.get_children():
                self.message_tree.delete(item)
            combined = [("收件", item) for item in inbox] + [("发件", item) for item in outbox]
            combined.sort(key=lambda pair: str(pair[1].get("created_at", "")), reverse=True)
            for direction, message in combined:
                message_id = str(message.get("id"))
                key = direction + ":" + message_id
                self.messages[key] = {"box": direction, **message}
                text = str(message.get("payload", {}).get("text", ""))
                delivery = ", ".join(str(d.get("status", "-")) for d in message.get("deliveries", [])) or "无目标"
                self.message_tree.insert("", "end", iid=key, values=(direction, message.get("created_at", "-"),
                                                                        message.get("priority", "-"), text, delivery))

        self._run("刷新消息", operation, success)

    def mark_selected_read(self) -> None:
        selection = self.message_tree.selection()
        if not selection:
            self._show_error(ClientError("请先选择一条收件消息。"))
            return
        message = self.messages.get(selection[0], {})
        if message.get("box") != "收件":
            self._show_error(ClientError("只有收件消息可以由当前设备确认已读。"))
            return
        deliveries = message.get("deliveries", [])
        if not deliveries:
            self._show_error(ClientError("该消息没有当前设备可确认的投递。"))
            return
        delivery = deliveries[0]
        try:
            client = self._require_client()
        except ClientError as exc:
            self._show_error(exc)
            return

        def operation() -> dict[str, Any]:
            state = str(delivery.get("status"))
            if state not in ("RECEIVED", "READ"):
                client.acknowledge(str(delivery["id"]), "received")
            if state != "READ":
                return client.acknowledge(str(delivery["id"]), "read")
            return delivery

        self._run("确认已读", operation, lambda _: self.refresh_messages())

    def _toggle_polling(self) -> None:
        if self._poll_after_id is not None:
            self.after_cancel(self._poll_after_id)
            self._poll_after_id = None
        self.polling = self.auto_poll_var.get()
        if self.polling:
            self._poll_tick()

    def _poll_tick(self) -> None:
        self._poll_after_id = None
        if not self.polling:
            return
        if not self.busy:
            self.refresh_messages()
        self._poll_after_id = self.after(3000, self._poll_tick)

    def _load_settings(self) -> None:
        value = load_base_url("NianNianFamily")
        if value:
            self.url_var.set(value)

    def _save_settings(self) -> None:
        try:
            save_base_url("NianNianFamily", self.url_var.get())
        except (OSError, ValueError) as exc:
            self._log(f"无法保存本地设置：{exc}")


def main() -> None:
    app = FamilyClientApp()
    app.mainloop()


if __name__ == "__main__":
    main()
