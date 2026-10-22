"""Shared Tk session exit: wait for HTTP work, revoke the session, then clear UI."""


class DesktopLifecycle:
    def _init_lifecycle(self):
        self._exit_requested = None
        self._exiting = False
        self._closed = False
        self._drain_after_id = None
        self.protocol('WM_DELETE_WINDOW', self.close_window)

    def _stop_polling(self):
        self.polling = False
        if self._poll_after_id is not None:
            self.after_cancel(self._poll_after_id)
            self._poll_after_id = None

    def logout(self):
        self._request_exit(False)

    def close_window(self):
        self._request_exit(True)

    def _request_exit(self, close):
        if self._exiting:
            if close:
                self._exit_requested = 'close'
            return
        self._exit_requested = 'close' if close else 'logout'
        self._stop_polling()
        self._clear_message_view()
        self._continue_exit()

    def _continue_exit(self):
        if not self._exit_requested or self.busy or self._exiting:
            return
        self._exiting = True
        self.busy = True
        self.tasks.invalidate()
        client = self.client

        def operation():
            try:
                if client:
                    client.logout()
            except Exception:
                return '本机已退出；服务器退出未确认，请联网后重新核对。'
            return ''

        def finish(warning):
            close = self._exit_requested == 'close'
            self._stop_polling()
            self.client = None
            self.selected_family_id = None
            self.families = []
            self._reset_session_view()
            self._exit_requested = None
            self._exiting = False
            if warning:
                self._show_error(RuntimeError(warning))
            if close:
                self._closed = True
                self.tasks.invalidate()
                if self._drain_after_id is not None:
                    self.after_cancel(self._drain_after_id)
                self.destroy()

        self.tasks.submit('退出登录', operation, finish)

    def _discard_for_exit(self, ok, value, label):
        if self._exit_requested and not self._exiting:
            # A login may finish after Close was clicked; revoke that new session too.
            if ok and label == '登录':
                self.client = value[0]
            return True
        return False

    def _schedule_drain(self):
        self._continue_exit()
        if not self._closed:
            self._drain_after_id = self.after(80, self._drain_tasks)
