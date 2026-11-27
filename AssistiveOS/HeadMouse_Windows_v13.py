import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import pyautogui
import time
import math
import threading
import tkinter as tk
import urllib.request
import os
import json
import webbrowser
import ctypes
from ctypes import wintypes

pyautogui.FAILSAFE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
MODEL_PATH = os.path.join(BASE_DIR, "face_landmarker.task")
CONFIG_PATH = os.path.join(BASE_DIR, "head_mouse_config.json")
WEB_APP_PATH = os.path.join(BASE_DIR, "AssistiveOS_Pro.html")

DEFAULT_CONFIG = {
    "sensitivity_x": 2.6,
    "sensitivity_y": 3.2,
    "smoothing": 0.25,
    "deadzone": 0.004,
    "dwell_time": 1.4,
    "dwell_radius": 28,
    "click_cooldown": 0.9,
    "scroll_speed": 350,
    "dwell_enabled": True,
    "invert_x": False,
    "invert_y": False,
    "beep_on_click": True,
    "camera_index": 0,
    "panel_scale": 1.0,
    "auto_resume_minutes": 5
}

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                cfg = DEFAULT_CONFIG.copy()
                cfg.update(data)
                return cfg
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
    except Exception:
        pass

def ensure_model_downloaded(status_callback):
    if os.path.exists(MODEL_PATH) and os.path.getsize(MODEL_PATH) > 1000000:
        return MODEL_PATH
    status_callback("جاري تحميل نموذج تتبع الوجه لأول مرة...", "blue")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    return MODEL_PATH

def play_click_sound():
    try:
        import winsound
        winsound.Beep(950, 45)
    except Exception:
        pass




class LocalFileAndAppBridge:
    """خادم محلي خفيف على 127.0.0.1:8765 لعرض الأقراص الافتراضية والمجلدات وتشغيل الأفلام والتحكم بالبرامج داخل AssistiveOS_Pro.html"""
    MEDIA_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv", ".flv", ".mp3", ".wav", ".m4a", ".ogg"}

    @staticmethod
    def list_drives():
        drives = []
        try:
            bitmask = ctypes.windll.kernel32.GetLogicalDrives()
            for i in range(26):
                if bitmask & (1 << i):
                    letter = chr(65 + i)
                    root_path = f"{letter}:\\"
                    vol_buf = ctypes.create_unicode_buffer(261)
                    ctypes.windll.kernel32.GetVolumeInformationW(
                        ctypes.c_wchar_p(root_path), vol_buf, 261, None, None, None, None, 0
                    )
                    drives.append({
                        "type": "drive",
                        "name": f"القرص ({letter}:)",
                        "label": vol_buf.value.strip(),
                        "path": root_path
                    })
        except Exception:
            drives.append({"type": "drive", "name": "القرص (C:)", "label": "System", "path": "C:\\"})
        return drives

    @staticmethod
    def list_directory(path_str):
        if not path_str or not os.path.exists(path_str):
            return {"parent": "", "items": LocalFileAndAppBridge.list_drives()}

        norm_path = os.path.abspath(path_str)
        parent = os.path.dirname(norm_path)
        if parent == norm_path:
            parent = ""

        dirs = []
        files = []
        try:
            for entry in os.scandir(norm_path):
                if entry.name.startswith("$") or entry.name.startswith("."):
                    continue
                try:
                    if entry.is_dir():
                        dirs.append({"type": "dir", "name": entry.name, "path": entry.path})
                    elif entry.is_file():
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in LocalFileAndAppBridge.MEDIA_EXTS:
                            files.append({"type": "file", "name": entry.name, "path": entry.path})
                except Exception:
                    continue
        except Exception:
            pass

        dirs.sort(key=lambda x: x["name"].lower())
        files.sort(key=lambda x: x["name"].lower())
        return {"parent": parent, "items": dirs + files}

    @staticmethod
    def start_server(panel_ref, port=8765):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import urllib.parse
        import mimetypes

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def _send_cors(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Range, Content-Type")

            def do_OPTIONS(self):
                self.send_response(204)
                self._send_cors()
                self.end_headers()

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                qs = urllib.parse.parse_qs(parsed.query)

                if parsed.path == "/api/list":
                    req_path = qs.get("path", [""])[0]
                    payload = json.dumps(LocalFileAndAppBridge.list_directory(req_path), ensure_ascii=False).encode("utf-8")
                    self.send_response(200)
                    self._send_cors()
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return

                if parsed.path == "/api/click-mode":
                    enabled_val = qs.get("enabled", ["1"])[0]
                    if panel_ref and panel_ref.ctrl:
                        panel_ref.ctrl.click_enabled = (enabled_val == "1")
                    self.send_response(200)
                    self._send_cors()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"ok":true}')
                    return

                if parsed.path == "/api/app/launch":
                    cmd = qs.get("cmd", [""])[0]
                    label = qs.get("label", ["برنامج"])[0]
                    if cmd and panel_ref:
                        panel_ref.root.after(0, lambda: panel_ref.launch_windows_app(cmd, label))
                    self.send_response(200)
                    self._send_cors()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"ok":true}')
                    return

                if parsed.path == "/api/app/close":
                    if panel_ref:
                        panel_ref.root.after(0, panel_ref.close_active_external_window)
                    self.send_response(200)
                    self._send_cors()
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"ok":true}')
                    return

                if parsed.path == "/api/stream":
                    file_path = qs.get("path", [""])[0]
                    if not file_path or not os.path.isfile(file_path):
                        self.send_response(404)
                        self._send_cors()
                        self.end_headers()
                        return

                    file_size = os.path.getsize(file_path)
                    mime_type, _ = mimetypes.guess_type(file_path)
                    if not mime_type:
                        mime_type = "video/mp4"

                    range_header = self.headers.get("Range")
                    start = 0
                    end = file_size - 1
                    status_code = 200

                    if range_header and range_header.startswith("bytes="):
                        status_code = 206
                        parts = range_header.replace("bytes=", "").split("-")
                        if parts[0].isdigit():
                            start = int(parts[0])
                        if len(parts) > 1 and parts[1].isdigit():
                            end = min(int(parts[1]), file_size - 1)

                    length = max(0, end - start + 1)
                    self.send_response(status_code)
                    self._send_cors()
                    self.send_header("Content-Type", mime_type)
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(length))
                    if status_code == 206:
                        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                    self.end_headers()

                    try:
                        with open(file_path, "rb") as f:
                            f.seek(start)
                            remaining = length
                            while remaining > 0:
                                chunk = f.read(min(65536, remaining))
                                if not chunk:
                                    break
                                self.wfile.write(chunk)
                                remaining -= len(chunk)
                    except Exception:
                        pass
                    return

                self.send_response(404)
                self._send_cors()
                self.end_headers()

        def _serve():
            try:
                server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
                server.serve_forever()
            except Exception:
                pass

        threading.Thread(target=_serve, daemon=True).start()


class SpeechHelper:
    """نطق صوتي خفيف عبر Windows SAPI دون تعطيل واجهة المستخدم"""
    @staticmethod
    def speak(text):
        if not text or not text.strip():
            return
        def _run():
            try:
                safe_text = text.replace("'", "''")
                cmd = f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{safe_text}')"
                import subprocess
                subprocess.run(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", cmd], check=False, timeout=8)
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()


class ClipboardHelper:
    """تنفيذ اختصارات تحديد الكل والنسخ واللصق في النافذة الخارجية النشطة"""
    @staticmethod
    def shortcut(key_char, target_hwnd=None):
        WindowsUnicodeTyper.activate_external_window(target_hwnd)
        try:
            pyautogui.hotkey("ctrl", key_char)
        except Exception:
            pass


class WindowsUnicodeTyper:
    """توجيه التركيز وإرسال النصوص والأوامر بشكل موثوق إلى المتصفح وأي تطبيق خارجي"""
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002
    INPUT_KEYBOARD = 1

    @staticmethod
    def activate_external_window(target_hwnd):
        if not target_hwnd:
            return
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            if not user32.IsWindow(target_hwnd):
                return

            SW_RESTORE = 9
            if user32.IsIconic(target_hwnd):
                user32.ShowWindow(target_hwnd, SW_RESTORE)

            fg_hwnd = user32.GetForegroundWindow()
            cur_tid = kernel32.GetCurrentThreadId()
            fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
            target_tid = user32.GetWindowThreadProcessId(target_hwnd, None)

            if fg_tid and fg_tid != cur_tid:
                user32.AttachThreadInput(cur_tid, fg_tid, True)
            if target_tid and target_tid != cur_tid:
                user32.AttachThreadInput(cur_tid, target_tid, True)

            user32.BringWindowToTop(target_hwnd)
            user32.SetForegroundWindow(target_hwnd)

            if fg_tid and fg_tid != cur_tid:
                user32.AttachThreadInput(cur_tid, fg_tid, False)
            if target_tid and target_tid != cur_tid:
                user32.AttachThreadInput(cur_tid, target_tid, False)

            time.sleep(0.05)
        except Exception:
            pass

    @staticmethod
    def send_text(text, target_hwnd=None):
        WindowsUnicodeTyper.activate_external_window(target_hwnd)
        try:
            user32 = ctypes.windll.user32
            ULONG_PTR = wintypes.WPARAM

            class KEYBDINPUT(ctypes.Structure):
                _fields_ = [
                    ("wVk", wintypes.WORD),
                    ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR),
                ]

            class MOUSEINPUT(ctypes.Structure):
                _fields_ = [
                    ("dx", wintypes.LONG),
                    ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR),
                ]

            class HARDWAREINPUT(ctypes.Structure):
                _fields_ = [
                    ("uMsg", wintypes.DWORD),
                    ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD),
                ]

            class INPUT_UNION(ctypes.Union):
                _fields_ = [
                    ("ki", KEYBDINPUT),
                    ("mi", MOUSEINPUT),
                    ("hi", HARDWAREINPUT),
                ]

            class INPUT(ctypes.Structure):
                _fields_ = [
                    ("type", wintypes.DWORD),
                    ("union", INPUT_UNION),
                ]

            cb_size = ctypes.sizeof(INPUT)
            for ch in text:
                for unit in ch.encode("utf-16-le"):
                    pass
                utf16_bytes = ch.encode("utf-16-le")
                for i in range(0, len(utf16_bytes), 2):
                    code = int.from_bytes(utf16_bytes[i:i+2], "little")
                    inp_down = INPUT(
                        type=WindowsUnicodeTyper.INPUT_KEYBOARD,
                        union=INPUT_UNION(ki=KEYBDINPUT(0, code, WindowsUnicodeTyper.KEYEVENTF_UNICODE, 0, 0))
                    )
                    inp_up = INPUT(
                        type=WindowsUnicodeTyper.INPUT_KEYBOARD,
                        union=INPUT_UNION(ki=KEYBDINPUT(0, code, WindowsUnicodeTyper.KEYEVENTF_UNICODE | WindowsUnicodeTyper.KEYEVENTF_KEYUP, 0, 0))
                    )
                    user32.SendInput(1, ctypes.byref(inp_down), cb_size)
                    user32.SendInput(1, ctypes.byref(inp_up), cb_size)
                time.sleep(0.01)
        except Exception:
            try:
                pyautogui.write(text)
            except Exception:
                pass

    @staticmethod
    def send_special(key_name, target_hwnd=None):
        WindowsUnicodeTyper.activate_external_window(target_hwnd)
        try:
            pyautogui.press(key_name)
        except Exception:
            pass


class AssistiveOnScreenKeyboard:
    """لوحة مفاتيح مدمجة كبيرة وعالية التباين مصممة لذوي الاحتياجات الخاصة والتحكم بالرأس"""
    ARABIC_ROWS = [
        ["١", "٢", "٣", "٤", "٥", "٦", "٧", "٨", "٩", "٠"],
        ["ض", "ص", "ث", "ق", "ف", "غ", "ع", "ه", "خ", "ح", "ج", "د"],
        ["ش", "س", "ي", "ب", "ل", "ا", "ت", "ن", "م", "ك", "ط", "ذ"],
        ["ئ", "ء", "ؤ", "ر", "لا", "ى", "ة", "و", "ز", "ظ", "أ", "إ"]
    ]

    ENGLISH_ROWS = [
        ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
        ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
        ["A", "S", "D", "F", "G", "H", "J", "K", "L", "@"],
        ["Z", "X", "C", "V", "B", "N", "M", ".", ",", "?"]
    ]

    QUICK_PHRASES = [
        "السلام عليكم",
        "نعم",
        "لا",
        "شكراً جزيلاً",
        "أحتاج مساعدة",
        "انتظر من فضلك"
    ]

    def __init__(self, parent, get_target_hwnd_cb=None, status_callback=None):
        self.parent = parent
        self.get_target_hwnd_cb = get_target_hwnd_cb
        self.status_callback = status_callback
        self.lang = "AR"
        self.shift_active = False

        self.win = tk.Toplevel(parent)
        self.win.title("⌨️ لوحة المفاتيح الذكية لذوي الاحتياجات الخاصة")
        self.win.attributes("-topmost", True)
        self.win.configure(bg="#020617")
        self.win.resizable(True, True)

        screen_w = self.win.winfo_screenwidth()
        screen_h = self.win.winfo_screenheight()
        kb_w = min(1040, screen_w - 40)
        kb_h = 370
        pos_x = max(10, (screen_w - kb_w) // 2)
        pos_y = max(40, screen_h - kb_h - 48)
        self.win.geometry(f"{kb_w}x{kb_h}+{pos_x}+{pos_y}")
        self.win.after(50, self._apply_no_activate_style)

        top_bar = tk.Frame(self.win, bg="#0f172a", pady=5, padx=6)
        top_bar.pack(fill="x")

        self.lang_btn = tk.Button(
            top_bar, text="🌐 عربي / EN", bg="#0284c7", fg="white",
            font=("Segoe UI", 11, "bold"), bd=0, padx=12, pady=6,
            command=self.toggle_language
        )
        self.lang_btn.pack(side="right", padx=3)

        self.shift_btn = tk.Button(
            top_bar, text="⬆️ Shift", bg="#334155", fg="white",
            font=("Segoe UI", 11, "bold"), bd=0, padx=10, pady=6,
            command=self.toggle_shift
        )
        self.shift_btn.pack(side="right", padx=3)

        tk.Button(
            top_bar, text="✖ إغلاق", bg="#dc2626", fg="white",
            font=("Segoe UI", 11, "bold"), bd=0, padx=12, pady=6,
            command=self.win.destroy
        ).pack(side="left", padx=3)

        phrases_frame = tk.Frame(top_bar, bg="#0f172a")
        phrases_frame.pack(side="right", fill="x", expand=True, padx=6)

        for phrase in self.QUICK_PHRASES:
            tk.Button(
                phrases_frame, text=phrase, bg="#1e293b", fg="#38bdf8",
                font=("Segoe UI", 10, "bold"), bd=0, padx=8, pady=6,
                command=lambda p=phrase: self.type_phrase(p + " ")
            ).pack(side="right", padx=2)

        self.keys_frame = tk.Frame(self.win, bg="#020617", padx=6, pady=4)
        self.keys_frame.pack(fill="both", expand=True)

        bottom_bar = tk.Frame(self.win, bg="#0f172a", padx=6, pady=6)
        bottom_bar.pack(fill="x")

        ctrl_style = {"font": ("Segoe UI", 12, "bold"), "bd": 0, "fg": "white", "height": 2}

        tk.Button(
            bottom_bar, text="⌫ مسح حرف", bg="#b91c1c",
            command=lambda: self.send_special_key("backspace"), **ctrl_style
        ).grid(row=0, column=0, padx=3, sticky="ew")

        tk.Button(
            bottom_bar, text="مسافة (Space)", bg="#334155",
            command=lambda: self.type_char(" "), **ctrl_style
        ).grid(row=0, column=1, columnspan=3, padx=3, sticky="ew")

        tk.Button(
            bottom_bar, text="↵ إدخال (Enter)", bg="#16a34a",
            command=lambda: self.send_special_key("enter"), **ctrl_style
        ).grid(row=0, column=4, padx=3, sticky="ew")

        tk.Button(
            bottom_bar, text="⬅️", bg="#1e293b",
            command=lambda: self.send_special_key("left"), **ctrl_style
        ).grid(row=0, column=5, padx=2, sticky="ew")

        tk.Button(
            bottom_bar, text="➡️", bg="#1e293b",
            command=lambda: self.send_special_key("right"), **ctrl_style
        ).grid(row=0, column=6, padx=2, sticky="ew")

        for c in range(7):
            bottom_bar.columnconfigure(c, weight=1)

        self.speak_enabled = False
        self.speak_btn = tk.Button(
            top_bar, text="🔊 نطق: متوقف", bg="#334155", fg="white",
            font=("Segoe UI", 10, "bold"), bd=0, padx=10, pady=6,
            command=self.toggle_speech
        )
        self.speak_btn.pack(side="right", padx=3)

        edit_bar = tk.Frame(self.win, bg="#111827", padx=6, pady=4)
        edit_bar.pack(fill="x")
        edit_style = {"font": ("Segoe UI", 10, "bold"), "bd": 0, "fg": "white", "pady": 5}
        tk.Button(edit_bar, text="☑ تحديد الكل", bg="#334155", command=lambda: self.send_shortcut("a"), **edit_style).pack(side="right", padx=3, expand=True, fill="x")
        tk.Button(edit_bar, text="📋 نسخ", bg="#0284c7", command=lambda: self.send_shortcut("c"), **edit_style).pack(side="right", padx=3, expand=True, fill="x")
        tk.Button(edit_bar, text="📥 لصق", bg="#0d9488", command=lambda: self.send_shortcut("v"), **edit_style).pack(side="right", padx=3, expand=True, fill="x")

        self.render_keys()

    def _get_root_hwnd(self):
        try:
            user32 = ctypes.windll.user32
            GA_ROOT = 2
            child_hwnd = self.win.winfo_id()
            root_hwnd = user32.GetAncestor(child_hwnd, GA_ROOT)
            return root_hwnd or child_hwnd
        except Exception:
            return None

    def _apply_no_activate_style(self):
        try:
            user32 = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TOPMOST = 0x00000008
            hwnd = self._get_root_hwnd()
            if hwnd:
                style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOPMOST)
        except Exception:
            pass

    def _target_hwnd(self):
        if self.get_target_hwnd_cb:
            return self.get_target_hwnd_cb()
        return None

    def render_keys(self):
        for w in self.keys_frame.winfo_children():
            w.destroy()

        rows = self.ARABIC_ROWS if self.lang == "AR" else self.ENGLISH_ROWS
        for r_idx, row_chars in enumerate(rows):
            row_frame = tk.Frame(self.keys_frame, bg="#020617")
            row_frame.pack(fill="both", expand=True, pady=2)
            for c_idx, ch in enumerate(row_chars):
                disp = ch.upper() if (self.lang == "EN" and self.shift_active) else (ch.lower() if self.lang == "EN" else ch)
                btn = tk.Button(
                    row_frame,
                    text=disp,
                    bg="#1e293b",
                    fg="#f8fafc",
                    activebackground="#0284c7",
                    activeforeground="white",
                    font=("Segoe UI", 14, "bold"),
                    bd=0,
                    command=lambda char=disp: self.type_char(char)
                )
                btn.grid(row=0, column=c_idx, padx=2, sticky="nsew")
                row_frame.columnconfigure(c_idx, weight=1)
            row_frame.rowconfigure(0, weight=1)

    def toggle_language(self):
        self.lang = "EN" if self.lang == "AR" else "AR"
        self.lang_btn.config(text="🌐 EN / عربي" if self.lang == "EN" else "🌐 عربي / EN")
        self.render_keys()

    def toggle_shift(self):
        self.shift_active = not self.shift_active
        self.shift_btn.config(bg="#0284c7" if self.shift_active else "#334155")
        self.render_keys()

    def toggle_speech(self):
        self.speak_enabled = not self.speak_enabled
        if self.speak_enabled:
            self.speak_btn.config(text="🔊 نطق: مفعّل", bg="#16a34a")
            SpeechHelper.speak("تم تفعيل النطق الصوتي")
        else:
            self.speak_btn.config(text="🔇 نطق: متوقف", bg="#334155")

    def send_shortcut(self, key_char):
        ClipboardHelper.shortcut(key_char, self._target_hwnd())
        if self.speak_enabled:
            labels = {"a": "تحديد الكل", "c": "نسخ", "v": "لصق"}
            SpeechHelper.speak(labels.get(key_char, ""))

    def type_char(self, ch):
        WindowsUnicodeTyper.send_text(ch, self._target_hwnd())
        if self.speak_enabled and ch.strip():
            SpeechHelper.speak(ch)
        if self.lang == "EN" and self.shift_active:
            self.shift_active = False
            self.shift_btn.config(bg="#334155")
            self.render_keys()

    def type_phrase(self, phrase):
        WindowsUnicodeTyper.send_text(phrase, self._target_hwnd())
        if self.speak_enabled:
            SpeechHelper.speak(phrase)

    def send_special_key(self, key_name):
        WindowsUnicodeTyper.send_special(key_name, self._target_hwnd())


class HeadMouseController:
    def __init__(self):
        self.cfg = load_config()
        self.running = False
        self.paused = False
        self.restart_camera_flag = False
        self.center_x = None
        self.center_y = None
        self.latest_nose = (0.5, 0.5)

        self.screen_w, self.screen_h = pyautogui.size()
        self.curr_x = self.screen_w / 2
        self.curr_y = self.screen_h / 2

        self.dwell_start_time = None
        self.dwell_anchor = (self.curr_x, self.curr_y)
        self.last_click_time = 0
        self.click_mode = "left"
        self.click_enabled = True
        self.scroll_left_panel = False  # هل غادر المؤشر نافذة التحكم بعد تفعيل التمرير؟
        self.pause_deadline = None

    def recenter(self):
        self.center_x, self.center_y = self.latest_nose

    def update_setting(self, key, value):
        self.cfg[key] = value
        save_config(self.cfg)
        if key == "camera_index":
            self.restart_camera_flag = True

    def reset_defaults(self):
        old_cam = self.cfg.get("camera_index", 0)
        self.cfg = DEFAULT_CONFIG.copy()
        save_config(self.cfg)
        if old_cam != self.cfg["camera_index"]:
            self.restart_camera_flag = True

    def perform_scroll(self, direction):
        scroll_amt = int(self.cfg.get("scroll_speed", 350))
        pyautogui.scroll(direction * scroll_amt)

    def tracking_loop(self, status_callback, progress_callback=None):
        try:
            model_file = ensure_model_downloaded(status_callback)
        except Exception as e:
            status_callback(f"خطأ في تحميل النموذج: {e}", "red")
            return

        use_legacy_solutions = hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh")

        if use_legacy_solutions:
            face_mesh = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1,
                refine_landmarks=False,
                min_detection_confidence=0.6,
                min_tracking_confidence=0.6
            )
            landmarker = None
        else:
            base_options = python.BaseOptions(model_asset_path=model_file)
            options = vision.FaceLandmarkerOptions(
                base_options=base_options,
                running_mode=vision.RunningMode.IMAGE,
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5
            )
            landmarker = vision.FaceLandmarker.create_from_options(options)
            face_mesh = None

        while self.running:
            self.restart_camera_flag = False
            cam_idx = int(self.cfg.get("camera_index", 0))
            cap = cv2.VideoCapture(cam_idx)

            if not cap.isOpened():
                status_callback(f"خطأ: تعذر فتح الكاميرا رقم {cam_idx}!", "red")
                time.sleep(1.5)
                continue

            status_callback("يعمل الآن — حرك رأسك للتحكم بالماوس", "green")

            while self.running and not self.restart_camera_flag:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue

                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                nose_coords = None

                if use_legacy_solutions and face_mesh:
                    results = face_mesh.process(rgb_frame)
                    if results.multi_face_landmarks:
                        nose = results.multi_face_landmarks[0].landmark[1]
                        nose_coords = (nose.x, nose.y)
                elif landmarker:
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                    detection = landmarker.detect(mp_image)
                    if detection.face_landmarks and len(detection.face_landmarks) > 0:
                        nose = detection.face_landmarks[0][1]
                        nose_coords = (nose.x, nose.y)

                if nose_coords is not None:
                    self.latest_nose = nose_coords

                    if self.center_x is None:
                        self.recenter()

                    if self.paused and self.pause_deadline is not None and time.time() >= self.pause_deadline:
                        self.paused = False
                        self.pause_deadline = None
                        status_callback("تم الاستئناف تلقائياً — حرك رأسك للتحكم بالماوس", "green")

                    if not self.paused:
                        sens_x = self.cfg["sensitivity_x"]
                        sens_y = self.cfg["sensitivity_y"]
                        smooth = self.cfg["smoothing"]
                        deadzone = self.cfg["deadzone"]

                        raw_dx = self.center_x - nose_coords[0]
                        raw_dy = nose_coords[1] - self.center_y

                        if self.cfg.get("invert_x", False):
                            raw_dx = -raw_dx
                        if self.cfg.get("invert_y", False):
                            raw_dy = -raw_dy

                        if abs(raw_dx) < deadzone:
                            raw_dx = 0.0
                        if abs(raw_dy) < deadzone:
                            raw_dy = 0.0

                        dx = raw_dx * sens_x
                        dy = raw_dy * sens_y

                        target_x = (0.5 + dx) * self.screen_w
                        target_y = (0.5 + dy) * self.screen_h

                        target_x = max(5, min(self.screen_w - 5, target_x))
                        target_y = max(5, min(self.screen_h - 5, target_y))

                        self.curr_x += (target_x - self.curr_x) * smooth
                        self.curr_y += (target_y - self.curr_y) * smooth

                        pyautogui.moveTo(int(self.curr_x), int(self.curr_y))
                        self.handle_dwell_click(progress_callback)
                    else:
                        if progress_callback:
                            progress_callback(0)
                else:
                    self.dwell_start_time = None
                    if progress_callback:
                        progress_callback(0)

                time.sleep(0.015)

            cap.release()

        if face_mesh:
            face_mesh.close()
        if landmarker:
            landmarker.close()

    def handle_dwell_click(self, progress_callback=None):
        if not self.cfg.get("dwell_enabled", True):
            if progress_callback:
                progress_callback(0)
            return

        now = time.time()
        cooldown = self.cfg.get("click_cooldown", 0.9)
        if now - self.last_click_time < cooldown:
            if progress_callback:
                progress_callback(0)
            return

        dwell_radius = self.cfg["dwell_radius"]
        dwell_time = self.cfg["dwell_time"]
        dist = math.hypot(self.curr_x - self.dwell_anchor[0], self.curr_y - self.dwell_anchor[1])

        if dist <= dwell_radius:
            if self.dwell_start_time is None:
                self.dwell_start_time = now
            elapsed = now - self.dwell_start_time
            if progress_callback:
                progress_callback(min(100, int((elapsed / dwell_time) * 100)))
            if elapsed >= dwell_time:
                self.execute_action()
                self.last_click_time = now
                self.dwell_start_time = None
                if progress_callback:
                    progress_callback(0)
        else:
            self.dwell_anchor = (self.curr_x, self.curr_y)
            self.dwell_start_time = now
            if progress_callback:
                progress_callback(0)

    def execute_action(self):
        if self.cfg.get("beep_on_click", True):
            threading.Thread(target=play_click_sound, daemon=True).start()

        if not getattr(self, "click_enabled", True):
            return

        if self.click_mode == "left":
            pyautogui.click()
        elif self.click_mode == "double":
            pyautogui.doubleClick()
            self.click_mode = "left"
        elif self.click_mode == "right":
            pyautogui.rightClick()
            self.click_mode = "left"
        elif self.click_mode == "scroll_down":
            self.perform_scroll(-1)
        elif self.click_mode == "scroll_up":
            self.perform_scroll(1)


class SettingsWindow:
    def __init__(self, parent, controller, on_change_callback):
        self.ctrl = controller
        self.on_change_callback = on_change_callback

        self.win = tk.Toplevel(parent)
        self.win.title("إعدادات نظام التحكم بالرأس")
        self.win.attributes("-topmost", True)
        self.win.geometry("620x650+450+20")
        self.win.configure(bg="#0f172a")
        self.win.resizable(False, False)

        header = tk.Label(
            self.win, text="⚙️ إعدادات الماوس والتتبع الشاملة",
            bg="#020617", fg="#38bdf8", font=("Segoe UI", 14, "bold"), pady=12
        )
        header.pack(fill="x")

        tab_bar = tk.Frame(self.win, bg="#0f172a", pady=8, padx=10)
        tab_bar.pack(fill="x")

        self.tab_buttons = {}
        tabs = [
            ("motion", "🎯 الحركة والسرعة"),
            ("click", "🖱️ النقر والتمرير"),
            ("system", "📷 الكاميرا والنظام")
        ]

        for idx, (key, title) in enumerate(tabs):
            btn = tk.Button(
                tab_bar, text=title, font=("Segoe UI", 11, "bold"),
                bg="#1e293b", fg="white", bd=0, height=2,
                command=lambda k=key: self.show_tab(k)
            )
            btn.grid(row=0, column=2 - idx, padx=4, sticky="ew")
            tab_bar.columnconfigure(idx, weight=1)
            self.tab_buttons[key] = btn

        self.content_frame = tk.Frame(self.win, bg="#1e293b", padx=15, pady=12)
        self.content_frame.pack(fill="both", expand=True, padx=12, pady=4)

        footer = tk.Frame(self.win, bg="#0f172a", pady=10, padx=12)
        footer.pack(fill="x")

        tk.Button(
            footer, text="✅ حفظ وإغلاق الإعدادات", bg="#16a34a", fg="white",
            font=("Segoe UI", 11, "bold"), bd=0, height=2, command=self.win.destroy
        ).pack(side="right", fill="x", expand=True, padx=(4, 0))

        tk.Button(
            footer, text="🔄 استعادة الافتراضي", bg="#475569", fg="white",
            font=("Segoe UI", 11, "bold"), bd=0, height=2, command=self.reset_defaults
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.current_tab = "motion"
        self.show_tab("motion")

    def show_tab(self, tab_key):
        self.current_tab = tab_key
        for k, btn in self.tab_buttons.items():
            btn.config(bg="#0284c7" if k == tab_key else "#1e293b")

        for widget in self.content_frame.winfo_children():
            widget.destroy()

        if tab_key == "motion":
            self.add_stepper(0, "السرعة الأفقية (يمين / يسار)", "sensitivity_x", 0.3, 0.5, 8.0)
            self.add_stepper(1, "السرعة الرأسية (أعلى / أسفل)", "sensitivity_y", 0.3, 0.5, 8.0)
            self.add_stepper(2, "نعومة المؤشر (تقليل الاهتزاز)", "smoothing", 0.05, 0.05, 0.90)
            self.add_stepper(3, "منطقة السكون (تجاهل الحركة الدقيقة)", "deadzone", 0.002, 0.000, 0.020, fmt="{:.3f}")
            self.add_toggle(4, "عكس الاتجاه الأفقي (يمين ↔ يسار)", "invert_x")
            self.add_toggle(5, "عكس الاتجاه الرأسي (أعلى ↔ أسفل)", "invert_y")

        elif tab_key == "click":
            self.add_toggle(0, "تفعيل النقر التلقائي بالتحديق", "dwell_enabled")
            self.add_stepper(1, "زمن التحديق للنقر (بالثواني)", "dwell_time", 0.2, 0.4, 4.0)
            self.add_stepper(2, "نطاق الثبات المسموح (بالبكسل)", "dwell_radius", 5, 10, 80, is_int=True)
            self.add_stepper(3, "فترة الانتظار بعد كل نقرة (ث)", "click_cooldown", 0.2, 0.3, 3.0)
            self.add_stepper(4, "سرعة التمرير (Scroll Speed)", "scroll_speed", 50, 100, 1000, is_int=True)
            self.add_toggle(5, "صوت تنبيه خفيف عند النقر", "beep_on_click")

        elif tab_key == "system":
            self.add_stepper(0, "رقم الكاميرا المتصلة (0 = الأساسية)", "camera_index", 1, 0, 4, is_int=True)
            self.add_stepper(1, "حجم نافذة التحكم العائمة", "panel_scale", 0.1, 0.8, 1.4)
            self.add_stepper(2, "العودة التلقائية بعد الإيقاف (دقائق)", "auto_resume_minutes", 1, 1, 60, is_int=True)

            info_lbl = tk.Label(
                self.content_frame,
                text="💡 يتم حفظ جميع التغييرات تلقائياً في ملف:\nhead_mouse_config.json\n\nيمكنك تعديل القيم بسهولة عبر أزرار (+) و (-) الكبيرة.",
                bg="#0f172a", fg="#94a3b8", font=("Segoe UI", 10), pady=15, padx=10, justify="center"
            )
            info_lbl.grid(row=3, column=0, columnspan=4, sticky="ew", pady=15)

        self.content_frame.columnconfigure(3, weight=1)

    def add_stepper(self, row, title, key, step, min_v, max_v, is_int=False, fmt="{:.2f}"):
        tk.Label(
            self.content_frame, text=title, bg="#1e293b", fg="#f8fafc",
            font=("Segoe UI", 11, "bold"), anchor="e"
        ).grid(row=row, column=3, sticky="e", pady=7, padx=(8, 0))

        val = self.ctrl.cfg[key]
        val_str = f"{int(val)}" if is_int else fmt.format(val)
        val_lbl = tk.Label(
            self.content_frame, text=val_str, width=7, bg="#0f172a", fg="#38bdf8",
            font=("Segoe UI", 11, "bold"), height=2
        )
        val_lbl.grid(row=row, column=1, padx=6, pady=7)

        btn_cfg = {"font": ("Segoe UI", 13, "bold"), "bd": 0, "fg": "white", "bg": "#334155", "width": 4, "height": 1}

        def adjust(delta):
            new_v = round(self.ctrl.cfg[key] + delta, 4)
            if is_int:
                new_v = int(round(new_v))
            new_v = max(min_v, min(max_v, new_v))
            self.ctrl.update_setting(key, new_v)
            val_lbl.config(text=f"{int(new_v)}" if is_int else fmt.format(new_v))
            if self.on_change_callback:
                self.on_change_callback()

        tk.Button(self.content_frame, text="+", command=lambda: adjust(step), **btn_cfg).grid(row=row, column=2, pady=7)
        tk.Button(self.content_frame, text="-", command=lambda: adjust(-step), **btn_cfg).grid(row=row, column=0, pady=7)

    def add_toggle(self, row, title, key):
        tk.Label(
            self.content_frame, text=title, bg="#1e293b", fg="#f8fafc",
            font=("Segoe UI", 11, "bold"), anchor="e"
        ).grid(row=row, column=3, sticky="e", pady=7, padx=(8, 0))

        state = self.ctrl.cfg.get(key, False)
        btn = tk.Button(
            self.content_frame,
            text="مفعّل ✅" if state else "معطّل ❌",
            bg="#16a34a" if state else "#dc2626",
            fg="white", font=("Segoe UI", 10, "bold"), bd=0, width=14, height=2
        )

        def toggle():
            new_s = not self.ctrl.cfg.get(key, False)
            self.ctrl.update_setting(key, new_s)
            btn.config(
                text="مفعّل ✅" if new_s else "معطّل ❌",
                bg="#16a34a" if new_s else "#dc2626"
            )
            if self.on_change_callback:
                self.on_change_callback()

        btn.config(command=toggle)
        btn.grid(row=row, column=0, columnspan=3, sticky="w", pady=7)

    def reset_defaults(self):
        self.ctrl.reset_defaults()
        self.show_tab(self.current_tab)
        if self.on_change_callback:
            self.on_change_callback()


class WindowSwitcherModal:
    """قائمة اختيار النوافذ المفتوحة في ويندوز لتسهيل اختيار نافذة بالرأس أو بالماوس"""
    def __init__(self, parent, windows_list, on_select_callback, on_close_callback):
        self.on_select_callback = on_select_callback
        self.on_close_callback = on_close_callback

        self.win = tk.Toplevel(parent)
        self.win.title("اختيار نافذة مفتوحة (Alt + Tab)")
        self.win.attributes("-topmost", True)
        self.win.configure(bg="#0f172a")
        self.win.geometry("540x420+460+60")
        self.win.resizable(True, True)
        self.win.protocol("WM_DELETE_WINDOW", self._handle_close)

        tk.Label(
            self.win, text="🪟 اختر النافذة المطلوب الانتقال إليها",
            bg="#020617", fg="#38bdf8", font=("Segoe UI", 13, "bold"), pady=10
        ).pack(fill="x")

        list_container = tk.Frame(self.win, bg="#1e293b", padx=10, pady=10)
        list_container.pack(fill="both", expand=True, padx=10, pady=8)

        if not windows_list:
            tk.Label(
                list_container, text="لا توجد نوافذ مفتوحة أخرى حالياً",
                bg="#1e293b", fg="#cbd5e1", font=("Segoe UI", 11)
            ).pack(pady=30)
        else:
            for hwnd, title in windows_list[:12]:
                display_title = title if len(title) <= 65 else title[:62] + "..."
                btn = tk.Button(
                    list_container,
                    text=f"🗗 {display_title}",
                    bg="#334155", fg="white",
                    font=("Segoe UI", 10, "bold"),
                    anchor="e", bd=0, pady=8, padx=12,
                    command=lambda h=hwnd, t=display_title: self._choose(h, t)
                )
                btn.pack(fill="x", pady=3)

        tk.Button(
            self.win, text="إغلاق القائمة", bg="#475569", fg="white",
            font=("Segoe UI", 10, "bold"), bd=0, height=2,
            command=self._handle_close
        ).pack(fill="x", padx=10, pady=(0, 10))

    def _choose(self, hwnd, title):
        try:
            self.win.destroy()
        finally:
            self.on_select_callback(hwnd, title)

    def _handle_close(self):
        try:
            self.win.destroy()
        finally:
            if self.on_close_callback:
                self.on_close_callback()


class FloatingControlPanel:
    def __init__(self, controller):
        self.ctrl = controller
        self.settings_win = None
        self.switcher_win = None
        self.keyboard_win = None
        self.last_external_hwnd = None

        self.root = tk.Tk()
        self.root.title("تحكم الماوس بالرأس")
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#0f172a")
        self.root.resizable(False, False)

        self.status_lbl = tk.Label(
            self.root, text="جاري تشغيل الكاميرا...", bg="#0f172a", fg="#38bdf8",
            font=("Segoe UI", 10, "bold")
        )
        self.status_lbl.pack(pady=(6, 3))
        self.status_lbl.bind("<Enter>", self._on_status_enter)
        self.status_lbl.bind("<Leave>", self._on_status_leave)
        self.status_click_toggle_armed = True

        self.progress_bg = tk.Frame(self.root, bg="#1e293b", height=6, width=390)
        self.progress_bg.pack(pady=(0, 5))
        self.progress_fill = tk.Frame(self.progress_bg, bg="#22c55e", height=6, width=0)
        self.progress_fill.place(x=0, y=0)

        btn_frame = tk.Frame(self.root, bg="#0f172a")
        btn_frame.pack(pady=3, padx=8, fill="both", expand=True)

        style = {"font": ("Segoe UI", 10, "bold"), "bd": 0, "fg": "white", "height": 2}

        # الصف 0: توسيط الرأس + إيقاف مؤقت / استئناف
        tk.Button(btn_frame, text="🎯 توسيط الرأس", bg="#0284c7", command=self.ctrl.recenter, **style).grid(row=0, column=0, padx=3, pady=3, sticky="ew")
        self.pause_btn = tk.Button(btn_frame, text="⏸️ إيقاف مؤقت", bg="#d97706", command=self.toggle_pause, **style)
        self.pause_btn.grid(row=0, column=1, padx=3, pady=3, sticky="ew")

        # الصف 1: زر Alt+Tap (قائمة النوافذ المفتوحة) + إظهار الكيبورد المدمج
        tk.Button(btn_frame, text="🪟 Alt+Tap", bg="#0d9488", command=self.open_window_switcher, **style).grid(row=1, column=0, padx=3, pady=3, sticky="ew")
        tk.Button(btn_frame, text="⌨️ إظهار الكيبورد", bg="#2563eb", command=self.open_on_screen_keyboard, **style).grid(row=1, column=1, padx=3, pady=3, sticky="ew")

        # الصف 2: نقر مزدوج + زر أيمن
        tk.Button(btn_frame, text="🖱️ نقر مزدوج", bg="#334155", command=lambda: self.set_mode("double"), **style).grid(row=2, column=0, padx=3, pady=3, sticky="ew")
        tk.Button(btn_frame, text="📋 زر أيمن", bg="#334155", command=lambda: self.set_mode("right"), **style).grid(row=2, column=1, padx=3, pady=3, sticky="ew")

        # الصف 3: تمرير لأسفل + تمرير لأعلى (تمرير بالتحديق خارج النافذة ويعود تلقائياً عند العودة للنافذة)
        self.scroll_down_btn = tk.Button(btn_frame, text="⬇️ تمرير لأسفل", bg="#1e293b", command=lambda: self.activate_scroll_mode("scroll_down"), **style)
        self.scroll_down_btn.grid(row=3, column=0, padx=3, pady=3, sticky="ew")
        self.scroll_up_btn = tk.Button(btn_frame, text="⬆️ تمرير لأعلى", bg="#1e293b", command=lambda: self.activate_scroll_mode("scroll_up"), **style)
        self.scroll_up_btn.grid(row=3, column=1, padx=3, pady=3, sticky="ew")

        # الصف 4: فتح صفحة AssistiveOS_Pro.html + الإعدادات الكاملة
        tk.Button(btn_frame, text="🌐 صفحة AssistiveOS", bg="#16a34a", command=self.open_assistive_web, **style).grid(row=4, column=0, padx=3, pady=3, sticky="ew")
        tk.Button(btn_frame, text="⚙️ الإعدادات", bg="#4f46e5", command=self.open_settings, **style).grid(row=4, column=1, padx=3, pady=3, sticky="ew")

        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        self.tray_icon = None
        self._start_tray_icon()
        LocalFileAndAppBridge.start_server(self)

        self.apply_panel_scale()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(120, self._monitor_windows_and_cursor)

    def _own_hwnds(self):
        hwnds = set()
        try:
            user32 = ctypes.windll.user32
            GA_ROOT = 2
            for w in (self.root, getattr(self.settings_win, "win", None), getattr(self.switcher_win, "win", None), getattr(self.keyboard_win, "win", None)):
                if w is not None and w.winfo_exists():
                    h = w.winfo_id()
                    r = user32.GetAncestor(h, GA_ROOT) or h
                    hwnds.add(int(h))
                    hwnds.add(int(r))
        except Exception:
            pass
        return hwnds

    def _is_cursor_inside_panel(self):
        try:
            x = self.root.winfo_rootx()
            y = self.root.winfo_rooty()
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            cx = self.ctrl.curr_x
            cy = self.ctrl.curr_y
            return (x - 8) <= cx <= (x + w + 8) and (y - 32) <= cy <= (y + h + 8)
        except Exception:
            return False

    def _on_status_enter(self, event=None):
        if not self.status_click_toggle_armed:
            return
        self.status_click_toggle_armed = False

        if self.ctrl.click_enabled:
            self.ctrl.click_enabled = False
            self.status_lbl.config(text="⛔ النقر متوقف (مرّر هنا للعودة)", fg="#f59e0b")
        else:
            self.ctrl.click_enabled = True
            self.status_lbl.config(text="✅ تم تفعيل النقر", fg="#22c55e")

    def _on_status_leave(self, event=None):
        self.status_click_toggle_armed = True

    def _monitor_windows_and_cursor(self):
        try:
            if not (self.ctrl.running and self.root.winfo_exists()):
                return

            # 0. تحديث زر الإيقاف المؤقت إذا تمت العودة التلقائية للعمل بعد انتهاء المدة
            if not self.ctrl.paused and self.pause_btn.cget("text").startswith("▶️"):
                self.pause_btn.config(text="⏸️ إيقاف مؤقت", bg="#d97706")
            elif self.ctrl.paused and self.ctrl.pause_deadline is not None:
                rem_sec = max(0, int(self.ctrl.pause_deadline - time.time()))
                mins, secs = divmod(rem_sec, 60)
                self.status_lbl.config(text=f"متوقف مؤقتاً — عودة خلال {mins:02d}:{secs:02d}", fg="#38bdf8")

            # 1. تتبع آخر نافذة خارجية نشطة حتى لو لم يتم النقر على زر الكيبورد مباشرة
            fg = int(ctypes.windll.user32.GetForegroundWindow())
            if fg and fg not in self._own_hwnds():
                self.last_external_hwnd = fg

            # 2. مراقبة وضع التمرير: عند مغادرة المؤشر لنافذة التحكم ثم عودته إليها يعود تلقائياً للنقر الطبيعي
            if self.ctrl.click_mode in ("scroll_down", "scroll_up"):
                inside = self._is_cursor_inside_panel()
                if not inside:
                    self.ctrl.scroll_left_panel = True
                elif inside and self.ctrl.scroll_left_panel:
                    self.ctrl.click_mode = "left"
                    self.ctrl.scroll_left_panel = False
                    self._reset_scroll_buttons()
                    self.update_status("تمت العودة لوضع النقر الطبيعي", "green")

            self.root.after(120, self._monitor_windows_and_cursor)
        except Exception:
            pass

    def get_last_external_hwnd(self):
        if self.last_external_hwnd and ctypes.windll.user32.IsWindow(self.last_external_hwnd):
            return self.last_external_hwnd
        # احتياطي: البحث عن أول نافذة خارجية مرئية إذا لم تُسجّل نافذة سابقة
        wins = self._enumerate_open_windows()
        if wins:
            self.last_external_hwnd = wins[0][0]
            return self.last_external_hwnd
        return None

    def apply_panel_scale(self):
        scale = self.ctrl.cfg.get("panel_scale", 1.0)
        w = int(430 * scale)
        h = int(355 * scale)
        self.root.geometry(f"{w}x{h}+20+20")

    def _enumerate_open_windows(self):
        windows = []
        try:
            user32 = ctypes.windll.user32
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            own = self._own_hwnds()

            def callback(hwnd, _):
                if not user32.IsWindowVisible(hwnd):
                    return True
                if int(hwnd) in own:
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()
                if not title:
                    return True
                if title in ("Program Manager", "Windows Input Experience", "Microsoft Text Input Application", "Settings"):
                    return True
                windows.append((int(hwnd), title))
                return True

            user32.EnumWindows(EnumWindowsProc(callback), 0)
        except Exception:
            pass
        return windows

    def open_window_switcher(self):
        if self.switcher_win is not None and self.switcher_win.win.winfo_exists():
            self.switcher_win.win.lift()
            return
        windows = self._enumerate_open_windows()
        self.switcher_win = WindowSwitcherModal(
            self.root,
            windows,
            on_select_callback=self._activate_window,
            on_close_callback=lambda: self.update_status("تم إغلاق قائمة النوافذ", "blue")
        )
        self.update_status("اختر نافذة للانتقال إليها", "blue")

    def _activate_window(self, hwnd, title):
        try:
            WindowsUnicodeTyper.activate_external_window(hwnd)
            self.last_external_hwnd = int(hwnd)
            self.update_status(f"تم التبديل إلى: {title[:28]}", "green")
        except Exception as e:
            self.update_status(f"تعذر تبديل النافذة: {e}", "red")

    def open_on_screen_keyboard(self):
        try:
            if self.keyboard_win is not None and self.keyboard_win.win.winfo_exists():
                self.keyboard_win.win.lift()
                self.keyboard_win.win.after(40, self.keyboard_win._apply_no_activate_style)
                self.update_status("لوحة المفاتيح الذكية مفتوحة", "green")
                return
            self.keyboard_win = AssistiveOnScreenKeyboard(
                self.root,
                get_target_hwnd_cb=self.get_last_external_hwnd,
                status_callback=self.update_status
            )
            self.update_status("تم فتح لوحة المفاتيح الذكية", "green")
        except Exception as e:
            self.update_status(f"خطأ في فتح الكيبورد: {e}", "red")

    def _close_existing_assistive_windows(self):
        try:
            user32 = ctypes.windll.user32
            WM_CLOSE = 0x0010
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            to_close = []

            def cb(hwnd, _):
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
                if "Assistive OS Pro" in title or "AssistiveOS_Pro.html" in title:
                    to_close.append(int(hwnd))
                return True

            user32.EnumWindows(EnumWindowsProc(cb), 0)
            for h in to_close:
                user32.PostMessageW(h, WM_CLOSE, 0, 0)
            if to_close:
                time.sleep(0.25)
        except Exception:
            pass


    def close_active_external_window(self):
        try:
            target = self.get_last_external_hwnd()
            if target and ctypes.windll.user32.IsWindow(target):
                ctypes.windll.user32.PostMessageW(target, 0x0010, 0, 0)
                self.update_status("تم إغلاق البرنامج النشط", "green")
            else:
                self.update_status("لا يوجد برنامج خارجي نشط لإغلاقه", "blue")
        except Exception as e:
            self.update_status(f"تعذر إغلاق البرنامج: {e}", "red")

    def launch_windows_app(self, app_cmd, label):
        try:
            import subprocess
            subprocess.Popen(app_cmd, shell=True)
            self.update_status(f"تم تشغيل {label}", "green")
        except Exception as e:
            self.update_status(f"تعذر تشغيل {label}: {e}", "red")

    def open_assistive_web(self):
        target = WEB_APP_PATH if os.path.exists(WEB_APP_PATH) else r"C:\AssistiveOS\AssistiveOS_Pro.html"
        try:
            if os.path.exists(target):
                self._close_existing_assistive_windows()
                webbrowser.open(f"file:///{target.replace(os.sep, '/')}", new=1)
                self.update_status("تم إغلاق النسخة السابقة وفتح صفحة AssistiveOS_Pro.html", "green")
            else:
                self.update_status("الملف غير موجود في C:\\AssistiveOS", "red")
        except Exception as e:
            self.update_status(f"خطأ في فتح الصفحة: {e}", "red")

    def open_settings(self):
        if self.settings_win is not None and self.settings_win.win.winfo_exists():
            self.settings_win.win.lift()
            return
        self.settings_win = SettingsWindow(self.root, self.ctrl, self.apply_panel_scale)

    def update_status(self, text, color):
        color_map = {"green": "#22c55e", "red": "#ef4444", "blue": "#38bdf8"}
        self.status_lbl.config(text=text, fg=color_map.get(color, "#38bdf8"))

    def update_progress(self, percent):
        scale = self.ctrl.cfg.get("panel_scale", 1.0)
        max_w = int(390 * scale)
        self.progress_bg.config(width=max_w)
        width = int((percent / 100.0) * max_w)
        self.progress_fill.config(width=width)

    def toggle_pause(self):
        self.ctrl.paused = not self.ctrl.paused
        if self.ctrl.paused:
            mins = int(self.ctrl.cfg.get("auto_resume_minutes", 5))
            self.ctrl.pause_deadline = time.time() + (mins * 60)
            self.pause_btn.config(text="▶️ استئناف", bg="#16a34a")
            self.update_status(f"متوقف مؤقتاً ({mins} د)", "blue")
        else:
            self.ctrl.pause_deadline = None
            self.pause_btn.config(text="⏸️ إيقاف مؤقت", bg="#d97706")
            self.update_status("يعمل الآن — حرك رأسك للتحكم بالماوس", "green")

    def show_panel(self):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
        except Exception:
            pass

    def hide_panel(self):
        try:
            self.root.withdraw()
        except Exception:
            pass

    def _start_tray_icon(self):
        try:
            import pystray
            from PIL import Image, ImageDraw

            img = Image.new("RGB", (64, 64), "#0f172a")
            draw = ImageDraw.Draw(img)
            draw.ellipse((10, 10, 54, 54), fill="#0284c7", outline="#38bdf8", width=3)
            draw.ellipse((24, 24, 40, 40), fill="#ffffff")

            menu = pystray.Menu(
                pystray.MenuItem("إظهار نافذة التحكم", lambda icon, item: self.root.after(0, self.show_panel), default=True),
                pystray.MenuItem("إخفاء نافذة التحكم", lambda icon, item: self.root.after(0, self.hide_panel)),
                pystray.MenuItem("إغلاق البرنامج", lambda icon, item: self.root.after(0, self.on_close))
            )
            self.tray_icon = pystray.Icon("HeadMouse", img, "تحكم الماوس بالرأس", menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except Exception:
            self.tray_icon = None

    def _reset_scroll_buttons(self):
        self.scroll_down_btn.config(bg="#1e293b")
        self.scroll_up_btn.config(bg="#1e293b")

    def set_mode(self, mode):
        self.ctrl.scroll_left_panel = False
        self._reset_scroll_buttons()
        self.ctrl.click_mode = mode
        self.update_status(f"الوضع القادم: {mode}", "blue")

    def activate_scroll_mode(self, mode):
        """تفعيل وضع التمرير بالتحديق في الصفحة ويعود للنقر الطبيعي فور عودة المؤشر إلى نافذة التحكم"""
        self.ctrl.click_mode = mode
        self.ctrl.scroll_left_panel = False
        self._reset_scroll_buttons()
        if mode == "scroll_down":
            self.scroll_down_btn.config(bg="#0284c7")
            self.update_status("ثبّت المؤشر في الصفحة للتمرير لأسفل — عد للنافذة للإيقاف", "blue")
        else:
            self.scroll_up_btn.config(bg="#0284c7")
            self.update_status("ثبّت المؤشر في الصفحة للتمرير لأعلى — عد للنافذة للإيقاف", "blue")

    def on_close(self):
        self.ctrl.running = False
        try:
            if self.tray_icon is not None:
                self.tray_icon.stop()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self):
        self.ctrl.running = True
        t = threading.Thread(
            target=self.ctrl.tracking_loop,
            args=(self.update_status, self.update_progress),
            daemon=True
        )
        t.start()
        self.root.mainloop()

if __name__ == "__main__":
    controller = HeadMouseController()
    app = FloatingControlPanel(controller)
    app.run()
