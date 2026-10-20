from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable

from niannian_desktop.settings import load_base_url, save_base_url
from niannian_desktop.tasks import BackgroundTasks

from .api import ApiError, ClientError, ElderClient, NetworkError

BG = "#F3F0E8"
CARD = "#FFFFFF"
INK = "#20312B"
MUTED = "#63716B"
GREEN = "#26634F"
GREEN_LIGHT = "#DCEAE3"
AMBER = "#9A611D"
RED = "#A23831"
RED_LIGHT = "#F2D9D5"
BLUE = "#315E80"


class ElderDemoApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("念念 · Windows 老人演示端")
        self.geometry("1120x760")
        self.minsize(960, 680)
        self.configure(bg=BG)
        self.client: ElderClient | None = None
        self.families: list[dict[str, Any]] = []
        self.selected_family_id: str | None = None
        self.inbox: list[dict[str, Any]] = []
        self.current_message_index = 0
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
        style.configure("Title.TLabel", background=BG, foreground=INK, font=("Microsoft YaHei UI", 24, "bold"))
        style.configure("Sub.TLabel", background=BG, foreground=MUTED, font=("Microsoft YaHei UI", 11))
        style.configure("CardTitle.TLabel", background=CARD, foreground=INK, font=("Microsoft YaHei UI", 15, "bold"))
        style.configure("Card.TLabel", background=CARD, foreground=INK, font=("Microsoft YaHei UI", 12))
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=("Microsoft YaHei UI", 10))
        style.configure("Big.TButton", font=("Microsoft YaHei UI", 13, "bold"), padding=(18, 13))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(12, 9))
        style.configure("TCombobox", font=("Microsoft YaHei UI", 11))

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=(28, 20, 28, 10))
        header.pack(fill="x")
        ttk.Label(header, text="念念", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="老人演示端", style="Sub.TLabel").pack(side="left", padx=(12, 0), pady=(11, 0))
        self.status_label = tk.Label(
            header,
            text="尚未连接",
            bg="#EEE2CA",
            fg=AMBER,
            padx=16,
            pady=9,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        self.status_label.pack(side="right")

        body = ttk.Frame(self, padding=(28, 6, 28, 12))
        body.pack(fill="both", expand=True)
        self.left = ttk.Frame(body, style="Card.TFrame", padding=18)
        self.left.pack(side="left", fill="y", padx=(0, 10))
        self.right = ttk.Frame(body, style="Card.TFrame", padding=22)
        self.right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self._build_setup_panel()
        self._build_message_panel()

        footer = ttk.Frame(self, padding=(28, 0, 28, 22))
        footer.pack(fill="x")
        self.feedback_label = ttk.Label(footer, text="请先连接服务器。", style="Sub.TLabel")
        self.feedback_label.pack(side="left")
        ttk.Label(
            footer,
            text="演示程序 · 不提供真实急救或电话呼叫",
            style="Sub.TLabel",
        ).pack(side="right")

    def _build_setup_panel(self) -> None:
        ttk.Label(self.left, text="开始使用", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(self.left, text="服务器地址", style="Muted.TLabel").pack(anchor="w", pady=(15, 4))
        self.url_var = tk.StringVar(value="http://127.0.0.1:8000")
        ttk.Entry(self.left, textvariable=self.url_var, width=35, font=("Consolas", 10)).pack(fill="x")
        setup_actions = ttk.Frame(self.left, style="Card.TFrame")
        setup_actions.pack(fill="x", pady=(10, 0))
        ttk.Button(setup_actions, text="测试连接", command=self.test_connection).pack(side="left")
        ttk.Button(setup_actions, text="登录老人演示账号", command=self.login).pack(side="left", padx=(8, 0))

        ttk.Separator(self.left).pack(fill="x", pady=18)
        ttk.Label(self.left, text="加入家庭", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(self.left, text="首次使用时，粘贴子女端生成的邀请令牌。", style="Muted.TLabel", wraplength=310).pack(
            anchor="w", pady=(5, 8)
        )
        self.invite_var = tk.StringVar()
        ttk.Entry(self.left, textvariable=self.invite_var, font=("Consolas", 9)).pack(fill="x")
        ttk.Button(self.left, text="接受邀请", command=self.accept_invite).pack(anchor="w", pady=(8, 0))

        ttk.Label(self.left, text="选择家庭", style="Muted.TLabel").pack(anchor="w", pady=(15, 4))
        self.family_var = tk.StringVar()
        self.family_box = ttk.Combobox(self.left, textvariable=self.family_var, state="readonly", width=31)
        self.family_box.pack(fill="x")
        self.family_box.bind("<<ComboboxSelected>>", self._select_family)
        ttk.Button(self.left, text="启用这台老人端", style="Big.TButton", command=self.register_device).pack(
            fill="x", pady=(12, 0)
        )
        self.device_label = ttk.Label(self.left, text="设备尚未启用", style="Muted.TLabel", wraplength=310)
        self.device_label.pack(anchor="w", pady=(8, 0))

    def _build_message_panel(self) -> None:
        top = ttk.Frame(self.right, style="Card.TFrame")
        top.pack(fill="x")
        ttk.Label(top, text="家人留言", style="CardTitle.TLabel").pack(side="left")
        ttk.Button(top, text="刷新", command=self.refresh_messages).pack(side="right")
        self.auto_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="自动接收", variable=self.auto_var, command=self._toggle_polling).pack(
            side="right", padx=(0, 12)
        )

        self.message_meta = tk.Label(
            self.right,
            text="暂无留言",
            bg=CARD,
            fg=MUTED,
            font=("Microsoft YaHei UI", 11),
            anchor="w",
        )
        self.message_meta.pack(fill="x", pady=(18, 7))
        self.message_text = tk.Text(
            self.right,
            height=7,
            bg="#F8F8F4",
            fg=INK,
            relief="flat",
            font=("Microsoft YaHei UI", 20),
            wrap="word",
            padx=22,
            pady=20,
            state="disabled",
        )
        self.message_text.pack(fill="both", expand=True)

        navigation = ttk.Frame(self.right, style="Card.TFrame")
        navigation.pack(fill="x", pady=(10, 15))
        ttk.Button(navigation, text="上一条", command=lambda: self.move_message(-1)).pack(side="left")
        self.counter_label = ttk.Label(navigation, text="0 / 0", style="Muted.TLabel")
        self.counter_label.pack(side="left", padx=12)
        ttk.Button(navigation, text="下一条", command=lambda: self.move_message(1)).pack(side="left")
        ttk.Button(navigation, text="我已读完这条", style="Big.TButton", command=self.mark_current_read).pack(side="right")

        ttk.Separator(self.right).pack(fill="x", pady=(0, 12))
        ttk.Label(self.right, text="快速回复子女", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 9))
        replies = ttk.Frame(self.right, style="Card.TFrame")
        replies.pack(fill="x")
        ttk.Button(replies, text="我很好", style="Big.TButton", command=lambda: self.quick_reply("我很好，不用担心。")) \
            .pack(side="left", expand=True, fill="x", padx=(0, 6))
        ttk.Button(replies, text="我已看到", style="Big.TButton", command=lambda: self.quick_reply("我已经看到留言了。")) \
            .pack(side="left", expand=True, fill="x", padx=6)
        call_button = tk.Button(
            replies,
            text="请给我打电话",
            bg="#E5B04B",
            fg="#382A12",
            activebackground="#D9A33D",
            relief="flat",
            font=("Microsoft YaHei UI", 13, "bold"),
            padx=16,
            pady=12,
            command=lambda: self.quick_reply("方便时请给我打个电话。", important=True),
        )
        call_button.pack(side="left", expand=True, fill="x", padx=(6, 0))

    def _run(self, label: str, operation: Callable[[], Any], success: Callable[[Any], None] | None = None) -> None:
        if self.busy:
            self.feedback_label.configure(text="上一项操作还没有完成，请稍等。")
            return
        self.busy = True
        self.status_label.configure(text=label + "…", bg="#EEE2CA", fg=AMBER)

        self.tasks.submit(label, operation, success)

    def _drain_tasks(self) -> None:
        for ok, value, success, label in self.tasks.drain():
            self.busy = False
            if ok:
                self.status_label.configure(text="连接正常", bg=GREEN_LIGHT, fg=GREEN)
                self.feedback_label.configure(text=label + "完成。")
                if success:
                    success(value)
            else:
                self.status_label.configure(text="操作失败", bg=RED_LIGHT, fg=RED)
                self._show_error(value)
        self.after(80, self._drain_tasks)

    def _show_error(self, exc: Exception) -> None:
        if isinstance(exc, NetworkError):
            hint = "\n\n如果服务端在 VMware 中，请先确认 Windows 能访问虚拟机端口。"
        elif isinstance(exc, ApiError) and exc.status == 429:
            hint = "\n\n登录次数较多，请等待约一分钟再试。"
        else:
            hint = ""
        text = str(exc) + hint
        self.feedback_label.configure(text=text.replace("\n", " "))
        messagebox.showerror("暂时不能完成", text, parent=self)

    def _require_client(self) -> ElderClient:
        if not self.client or not self.client.access_token:
            raise ClientError("请先登录老人演示账号。")
        return self.client

    def _require_device(self) -> ElderClient:
        client = self._require_client()
        if not client.binding:
            raise ClientError("请先选择家庭并启用这台老人端。")
        return client

    def test_connection(self) -> None:
        base_url = self.url_var.get()

        def operation() -> tuple[ElderClient, str]:
            client = ElderClient(base_url)
            health = client.health()
            if health.get("status") != "ok":
                raise ClientError("服务器健康检查没有返回正常状态。")
            return client, f"HTTP 连接正常，环境 {health.get('environment', 'unknown')}。"

        def success(result: tuple[ElderClient, str]) -> None:
            self.client = result[0]
            self.feedback_label.configure(text=result[1])
            self._save_settings()

        self._run("测试连接", operation, success)

    def login(self) -> None:
        base_url = self.url_var.get()

        def operation() -> tuple[ElderClient, dict[str, Any]]:
            client = ElderClient(base_url)
            return client, client.login()

        def success(result: tuple[ElderClient, dict[str, Any]]) -> None:
            self.client = result[0]
            name = result[1].get("user", {}).get("display_name", "演示老人")
            self.feedback_label.configure(text=f"{name}，您好。请选择或加入家庭。")
            self._save_settings()
            self.refresh_families()

        self._run("登录", operation, success)

    def refresh_families(self) -> None:
        try:
            client = self._require_client()
        except ClientError as exc:
            self._show_error(exc)
            return

        def success(items: list[dict[str, Any]]) -> None:
            self.families = [item for item in items if item.get("member_status") == "ACTIVE"]
            labels = [f"{item.get('name', '未命名家庭')} · {item.get('role', '-') }" for item in self.families]
            self.family_box.configure(values=labels)
            if labels:
                self.family_box.current(0)
                self._select_family()
                self.feedback_label.configure(text="家庭已找到，请点击“启用这台老人端”。")
            else:
                self.family_var.set("")
                self.selected_family_id = None
                self.feedback_label.configure(text="还没有家庭，请粘贴子女端邀请令牌。")

        self._run("读取家庭", client.list_families, success)

    def accept_invite(self) -> None:
        try:
            client = self._require_client()
            token = self.invite_var.get().strip()
            if not token:
                raise ClientError("请先粘贴邀请令牌。")
        except ClientError as exc:
            self._show_error(exc)
            return
        self._run("接受邀请", lambda: client.accept_invitation(token), lambda _: self.refresh_families())

    def _select_family(self, _event: Any = None) -> None:
        index = self.family_box.current()
        if 0 <= index < len(self.families):
            self.selected_family_id = str(self.families[index]["id"])

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
            self.device_label.configure(text=f"老人端已启用\n设备编号：{binding['id']}")
            self.feedback_label.configure(text="现在可以接收家人的留言。")
            self._toggle_polling()
            if not self.polling:
                self.refresh_messages()

        self._run("启用设备", lambda: client.register_device(family_id), success)

    def refresh_messages(self) -> None:
        try:
            client = self._require_device()
        except ClientError as exc:
            if not self.polling:
                self._show_error(exc)
            return

        def operation() -> list[dict[str, Any]]:
            items = client.list_messages("INBOX")
            for item in items:
                for delivery in item.get("deliveries", []):
                    if delivery.get("status") not in ("RECEIVED", "READ"):
                        client.acknowledge(str(delivery["id"]), "received")
                        delivery["status"] = "RECEIVED"
            return items

        def success(items: list[dict[str, Any]]) -> None:
            current_id = self.current_message().get("id") if self.current_message() else None
            self.inbox = sorted(items, key=lambda item: str(item.get("created_at", "")), reverse=True)
            self.current_message_index = 0
            if current_id:
                for index, item in enumerate(self.inbox):
                    if item.get("id") == current_id:
                        self.current_message_index = index
                        break
            self._render_message()

        self._run("接收留言", operation, success)

    def current_message(self) -> dict[str, Any] | None:
        if not self.inbox or not 0 <= self.current_message_index < len(self.inbox):
            return None
        return self.inbox[self.current_message_index]

    def _render_message(self) -> None:
        message = self.current_message()
        self.message_text.configure(state="normal")
        self.message_text.delete("1.0", "end")
        if not message:
            self.message_meta.configure(text="暂无留言", fg=MUTED)
            self.message_text.insert("1.0", "暂时没有新的家人留言。")
            self.counter_label.configure(text="0 / 0")
        else:
            priority = str(message.get("priority", "NORMAL"))
            status = ", ".join(str(item.get("status", "-")) for item in message.get("deliveries", []))
            self.message_meta.configure(
                text=f"{message.get('created_at', '')}  ·  {'重要留言' if priority == 'IMPORTANT' else '普通留言'}  ·  {status}",
                fg=RED if priority == "IMPORTANT" else MUTED,
            )
            self.message_text.insert("1.0", str(message.get("payload", {}).get("text", "留言内容已不可用。")))
            self.counter_label.configure(text=f"{self.current_message_index + 1} / {len(self.inbox)}")
        self.message_text.configure(state="disabled")

    def move_message(self, offset: int) -> None:
        if not self.inbox:
            return
        self.current_message_index = max(0, min(len(self.inbox) - 1, self.current_message_index + offset))
        self._render_message()

    def mark_current_read(self) -> None:
        message = self.current_message()
        if not message:
            self._show_error(ClientError("当前没有可确认的留言。"))
            return
        deliveries = message.get("deliveries", [])
        if not deliveries:
            self._show_error(ClientError("当前留言没有可确认的投递。"))
            return
        try:
            client = self._require_device()
        except ClientError as exc:
            self._show_error(exc)
            return
        delivery = deliveries[0]

        def operation() -> dict[str, Any]:
            if delivery.get("status") not in ("RECEIVED", "READ"):
                client.acknowledge(str(delivery["id"]), "received")
            if delivery.get("status") != "READ":
                return client.acknowledge(str(delivery["id"]), "read")
            return delivery

        def success(_result: dict[str, Any]) -> None:
            delivery["status"] = "READ"
            self._render_message()
            self.feedback_label.configure(text="已告诉家人：这条留言您已经读过。")

        self._run("确认已读", operation, success)

    def quick_reply(self, text: str, important: bool = False) -> None:
        try:
            client = self._require_device()
        except ClientError as exc:
            self._show_error(exc)
            return

        def success(message: dict[str, Any]) -> None:
            count = len(message.get("deliveries", []))
            if count:
                self.feedback_label.configure(text=f"回复已发给家人，共 {count} 个子女端设备。")
            else:
                messagebox.showwarning(
                    "回复已保存",
                    "服务器已保存回复，但这个家庭还没有已注册的子女端设备。",
                    parent=self,
                )

        self._run("发送回复", lambda: client.reply_to_children(text, important=important), success)

    def _toggle_polling(self) -> None:
        if self._poll_after_id is not None:
            self.after_cancel(self._poll_after_id)
            self._poll_after_id = None
        self.polling = self.auto_var.get() and bool(self.client and self.client.binding)
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
        value = load_base_url("NianNianElderDemo")
        if value:
            self.url_var.set(value)

    def _save_settings(self) -> None:
        try:
            save_base_url("NianNianElderDemo", self.url_var.get())
        except (OSError, ValueError):
            pass


def main() -> None:
    app = ElderDemoApp()
    app.mainloop()


if __name__ == "__main__":
    main()
