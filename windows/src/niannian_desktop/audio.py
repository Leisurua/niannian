"""Bounded in-memory recording/playback; no personal audio is written to disk."""
import io
import queue
import subprocess
import threading
import wave


RATE = 24000
MAX_SAMPLE = RATE * 2 * 60


def wav_bytes(pcm):
    output = io.BytesIO()
    with wave.open(output, 'wb') as result:
        result.setnchannels(1)
        result.setsampwidth(2)
        result.setframerate(RATE)
        result.writeframes(pcm)
    return output.getvalue()


class Audio:
    def __init__(self, failed=lambda message: None):
        self.failed = failed
        self.generation = 0
        self.capture = None
        self.player = None
        self.process = None
        self.frames = bytearray()
        self.queue = queue.Queue(maxsize=12)
        self.lock = threading.RLock()

    def stop(self):
        with self.lock:
            self.generation += 1
            for name in ('capture', 'player'):
                stream = getattr(self, name)
                setattr(self, name, None)
                if stream:
                    try:
                        stream.abort()
                        stream.close()
                    except Exception:
                        pass
            if self.process:
                self.process.kill()
                self.process = None
            self.queue = queue.Queue(maxsize=12)

    def record(self):
        import sounddevice as sd
        self.stop()
        self.frames = bytearray()
        epoch = self.generation
        def captured(data, count, timing, status):
            if epoch != self.generation:
                raise sd.CallbackStop
            if status:
                self.failed('录音设备发生溢出，请重新录制。')
                raise sd.CallbackAbort
            self.frames.extend(bytes(data)[:max(0, MAX_SAMPLE - len(self.frames))])
            if len(self.frames) >= MAX_SAMPLE:
                raise sd.CallbackStop
        self.capture = sd.RawInputStream(samplerate=RATE, channels=1, dtype='int16', callback=captured)
        self.capture.start()

    def finish_recording(self):
        self.stop()
        if len(self.frames) < RATE * 2 * 10:
            raise ValueError('请录制至少 10 秒，建议 15–20 秒。')
        result = wav_bytes(self.frames)
        self.frames = bytearray()
        return result

    def begin(self):
        self.stop()
        epoch, packets = self.generation, self.queue
        def run():
            stream = None
            try:
                import sounddevice as sd
                stream = sd.RawOutputStream(samplerate=RATE, channels=1, dtype='int16')
                with self.lock:
                    if epoch != self.generation:
                        stream.close()
                        return
                    self.player = stream
                    stream.start()
                while epoch == self.generation:
                    try:
                        packet = packets.get(timeout=.2)
                    except queue.Empty:
                        continue
                    if packet is None:
                        stream.stop()
                        break
                    stream.write(packet)
            except Exception:
                if epoch == self.generation:
                    self.failed('声音播放不可用，请阅读文字。')
            finally:
                if stream:
                    try:
                        stream.close()
                    except Exception:
                        pass
                with self.lock:
                    if self.player is stream:
                        self.player = None
        threading.Thread(target=run, daemon=True).start()

    def feed(self, data):
        if data is not None and (len(data) > 8192 or len(data) % 2):
            raise ValueError('无效音频片段。')
        try:
            self.queue.put(data, timeout=.5)
        except queue.Full:
            self.stop()
            raise ValueError('音频缓冲已满，已停止播放。') from None

    def preview(self, data):
        with wave.open(io.BytesIO(data), 'rb') as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, RATE):
                raise ValueError('不支持此试听音频格式。')
            pcm = source.readframes(source.getnframes())
        self.begin()
        epoch = self.generation
        def fill():
            try:
                for start in range(0, len(pcm), 8192):
                    if epoch != self.generation:
                        return
                    self.feed(pcm[start:start + 8192])
                if epoch == self.generation:
                    self.feed(None)
            except Exception:
                self.failed('试听已停止，请重试。')
        threading.Thread(target=fill, daemon=True).start()

    def speak(self, text, slow=False):
        self.stop()
        epoch = self.generation
        # Constant command; model/user text is data on stdin, never PowerShell code.
        command = "$ErrorActionPreference='Stop'; [Console]::InputEncoding=[System.Text.Encoding]::UTF8; Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::NotSet,[System.Speech.Synthesis.VoiceAge]::NotSet,0,[System.Globalization.CultureInfo]::GetCultureInfo('zh-CN')); $s.Rate=" + ('-3' if slow else '0') + "; $s.Speak([Console]::In.ReadToEnd()); $s.Dispose()"
        def run():
            try:
                with self.lock:
                    if epoch != self.generation:
                        return
                    proc = subprocess.Popen(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    self.process = proc
                proc.communicate(text.encode('utf-8'))
                if proc.returncode and epoch == self.generation:
                    self.failed('没有可用的系统中文声音，请阅读文字。')
            except Exception:
                if epoch == self.generation:
                    self.failed('系统朗读不可用，请阅读文字。')
            finally:
                with self.lock:
                    if epoch == self.generation:
                        self.process = None
        threading.Thread(target=run, daemon=True).start()
