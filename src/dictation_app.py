from __future__ import annotations

import ctypes
import json
import math
import os
import platform
import queue
import subprocess
import re
import sys
import tempfile
import threading
import time
import traceback
import tkinter as tk
from tkinter import messagebox, simpledialog
import wave

import pystray
from pathlib import Path

from PIL import Image, ImageDraw

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

APP_VERSION = "1.1.0"

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None
from pynput import keyboard

try:
    import winsound
except ImportError:  # pragma: no cover
    winsound = None


if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parents[1]

CONFIG_PATH = ROOT / "config.json"
ENV_PATH = ROOT / ".env"


def load_env_file() -> None:
    if not ENV_PATH.exists():
        return
    for raw_line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def save_env_value(key: str, value: str) -> None:
    lines = []
    updated = False
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8-sig").splitlines()
    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        current_key, _current_value = stripped.split("=", 1)
        if current_key.strip() == key:
            lines[index] = f"{key}={value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def validate_openai_api_key(config: dict, api_key: str) -> None:
    if OpenAI is None:
        raise RuntimeError("No se encontro el paquete de OpenAI en esta instalacion.")
    openai_config = config.get("openai", {})
    client = OpenAI(
        api_key=api_key,
        timeout=float(openai_config.get("timeout_seconds", 25)),
        max_retries=0,
    )
    # A lightweight authenticated request validates the key without depending on
    # whether a transcription model is exposed through the models retrieve API.
    client.models.list()


def short_error_message(exc: Exception) -> str:
    message = str(exc).strip().replace("\n", " ")
    return message[:220] if message else exc.__class__.__name__


def usage_help_text(config: dict, api_key_validated: bool = False) -> str:
    hotkey = "+".join(str(key).capitalize() for key in config.get("hotkey", ["ctrl", "space"]))
    local = str(config.get("transcription_provider", "local")).lower() == "local"
    provider = "Dictado local, sin API key ni costo por minuto." if local else "Dictado mediante la API de OpenAI."
    if api_key_validated:
        provider += " API key validada."
    text = (
        f"TravelDesk Whisper {APP_VERSION}\n{provider}\n\n"
        "1. Coloca el cursor donde quieres escribir.\n"
        f"2. Mantén presionado {hotkey}, habla y suelta para pegar el texto.\n"
    )
    if config.get("enable_toggle_recording", True):
        text += f"3. Para manos libres, toca {hotkey} dos veces. Tócalo otra vez para detener.\n"
    else:
        text += "El modo manos libres por doble toque está desactivado.\n"
    limit = float(config.get("max_record_seconds", 0) or 0)
    if limit > 0:
        text += f"Cada grabación se detiene a los {limit:g} segundos.\n"
    return text + "\nLa app queda en la bandeja de Windows: puedes mostrarla, ocultarla o salir."


def show_usage_message(parent: tk.Tk, config: dict, api_key_validated: bool = False) -> None:
    messagebox.showinfo(
        "TravelDesk Whisper activo",
        usage_help_text(config, api_key_validated),
        parent=parent,
    )


def ensure_openai_api_key(config: dict) -> bool:
    openai_config = config.get("openai", {})
    env_name = str(openai_config.get("api_key_env", "OPENAI_API_KEY"))
    prompt = tk.Tk()
    prompt.withdraw()
    prompt.attributes("-topmost", True)

    current_key = str(os.environ.get(env_name) or openai_config.get("api_key") or "").strip()
    if current_key:
        try:
            validate_openai_api_key(config, current_key)
            prompt.destroy()
            return True
        except Exception as exc:
            messagebox.showwarning(
                "TravelDesk Whisper",
                "La OpenAI API Key guardada no pudo validarse. Ingresa una llave valida para continuar.\n\n"
                f"Detalle: {short_error_message(exc)}",
                parent=prompt,
            )

    while True:
        api_key = simpledialog.askstring(
            "TravelDesk Whisper",
            "Ingresa tu OpenAI API Key para usar TravelDesk Whisper:",
            parent=prompt,
            show="*",
        )
        api_key = (api_key or "").strip()
        if not api_key:
            messagebox.showerror(
                "TravelDesk Whisper",
                "No se ingreso una OpenAI API Key. La aplicacion se cerrara.",
                parent=prompt,
            )
            prompt.destroy()
            return False

        try:
            validate_openai_api_key(config, api_key)
        except Exception as exc:
            messagebox.showerror(
                "TravelDesk Whisper",
                "Esa OpenAI API Key no pudo validarse. Revisa que este correcta, activa y con acceso al modelo configurado.\n\n"
                f"Detalle: {short_error_message(exc)}",
                parent=prompt,
            )
            continue

        os.environ[env_name] = api_key
        save_env_value(env_name, api_key)
        show_usage_message(prompt, config, api_key_validated=True)
        prompt.destroy()
        return True


class WinClipboard:
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    user32 = ctypes.windll.user32 if os.name == "nt" else None
    kernel32 = ctypes.windll.kernel32 if os.name == "nt" else None

    if os.name == "nt":
        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.restype = ctypes.c_bool
        kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
        kernel32.GlobalFree.restype = ctypes.c_void_p
        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.restype = ctypes.c_bool
        user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        user32.SetClipboardData.restype = ctypes.c_void_p
        user32.CloseClipboard.restype = ctypes.c_bool

    @classmethod
    def set_text(cls, text: str) -> None:
        if os.name != "nt":
            raise RuntimeError("WinClipboard is only available on Windows")
        data = text.encode("utf-16-le") + b"\x00\x00"
        h_global = cls.kernel32.GlobalAlloc(cls.GMEM_MOVEABLE, len(data))
        if not h_global:
            raise RuntimeError("GlobalAlloc failed")
        locked = cls.kernel32.GlobalLock(h_global)
        if not locked:
            cls.kernel32.GlobalFree(h_global)
            raise RuntimeError("GlobalLock failed")
        ctypes.memmove(locked, data, len(data))
        cls.kernel32.GlobalUnlock(h_global)
        if not cls.user32.OpenClipboard(None):
            cls.kernel32.GlobalFree(h_global)
            raise RuntimeError("OpenClipboard failed")
        try:
            cls.user32.EmptyClipboard()
            if not cls.user32.SetClipboardData(cls.CF_UNICODETEXT, h_global):
                cls.kernel32.GlobalFree(h_global)
                raise RuntimeError("SetClipboardData failed")
        finally:
            cls.user32.CloseClipboard()


def set_clipboard_text(text: str) -> None:
    system = platform.system().lower()
    if system == "windows":
        WinClipboard.set_text(text)
        return
    if system == "darwin":
        subprocess.run(["pbcopy"], input=text, text=True, check=True)
        return
    raise RuntimeError("Clipboard paste is not configured for this OS")



class TargetWindow:
    user32 = ctypes.windll.user32 if os.name == "nt" else None

    if os.name == "nt":
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        user32.GetWindowThreadProcessId.restype = ctypes.c_uint
        user32.GetFocus.restype = ctypes.c_void_p
        user32.SetFocus.argtypes = [ctypes.c_void_p]
        user32.SetFocus.restype = ctypes.c_void_p
        user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        user32.SetForegroundWindow.restype = ctypes.c_bool
        user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.ShowWindow.restype = ctypes.c_bool
        user32.IsIconic.argtypes = [ctypes.c_void_p]
        user32.IsIconic.restype = ctypes.c_bool
        user32.IsWindow.argtypes = [ctypes.c_void_p]
        user32.IsWindow.restype = ctypes.c_bool
        user32.AttachThreadInput.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_bool]
        user32.AttachThreadInput.restype = ctypes.c_bool
        user32.GetCurrentThreadId = ctypes.windll.kernel32.GetCurrentThreadId
        user32.GetCurrentThreadId.restype = ctypes.c_uint

    @classmethod
    def capture(cls):
        if os.name != "nt":
            return None
        window = cls.user32.GetForegroundWindow()
        thread_id = cls.user32.GetWindowThreadProcessId(window, None) if window else 0
        current_thread_id = cls.user32.GetCurrentThreadId()
        attached = False
        if thread_id and current_thread_id != thread_id:
            attached = bool(cls.user32.AttachThreadInput(current_thread_id, thread_id, True))
        try:
            focus = cls.user32.GetFocus()
        finally:
            if attached:
                cls.user32.AttachThreadInput(current_thread_id, thread_id, False)
        return {"window": window, "focus": focus, "thread_id": thread_id}

    @classmethod
    def restore(cls, target) -> None:
        if os.name != "nt" or not target:
            return
        if isinstance(target, dict):
            window = target.get("window")
            focus = target.get("focus")
            target_thread_id = target.get("thread_id") or 0
        else:
            window = target
            focus = None
            target_thread_id = 0
        if not window or not cls.user32.IsWindow(window):
            return
        if not target_thread_id:
            target_thread_id = cls.user32.GetWindowThreadProcessId(window, None)
        current_thread_id = cls.user32.GetCurrentThreadId()
        foreground = cls.user32.GetForegroundWindow()
        foreground_thread_id = cls.user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
        attached_threads = []
        for thread_id in {target_thread_id, foreground_thread_id}:
            if thread_id and thread_id != current_thread_id:
                if cls.user32.AttachThreadInput(current_thread_id, thread_id, True):
                    attached_threads.append(thread_id)
        try:
            if cls.user32.IsIconic(window):
                cls.user32.ShowWindow(window, 9)
            cls.user32.SetForegroundWindow(window)
            if focus and cls.user32.IsWindow(focus):
                cls.user32.SetFocus(focus)
            time.sleep(0.12)
        finally:
            for thread_id in attached_threads:
                cls.user32.AttachThreadInput(current_thread_id, thread_id, False)
def load_config() -> dict:
    load_env_file()
    with CONFIG_PATH.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def normalize_key_name(key) -> str | None:
    if isinstance(key, keyboard.KeyCode):
        return (key.char or "").lower()
    mapping = {
        keyboard.Key.ctrl: "ctrl",
        keyboard.Key.ctrl_l: "ctrl",
        keyboard.Key.ctrl_r: "ctrl",
        keyboard.Key.shift: "shift",
        keyboard.Key.shift_l: "shift",
        keyboard.Key.shift_r: "shift",
        keyboard.Key.alt: "alt",
        keyboard.Key.alt_l: "alt",
        keyboard.Key.alt_r: "alt",
        keyboard.Key.cmd: "cmd",
        keyboard.Key.cmd_l: "cmd",
        keyboard.Key.cmd_r: "cmd",
        keyboard.Key.space: "space",
        keyboard.Key.f8: "f8",
        keyboard.Key.f9: "f9",
    }
    return mapping.get(key)


def write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    samples = np.clip(samples.reshape(-1), -1.0, 1.0)
    int_samples = (samples * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sample_rate)
        fh.writeframes(int_samples.tobytes())


def protect_literal_phrases(text: str, phrases: list[str]) -> tuple[str, dict[str, str]]:
    protected: dict[str, str] = {}
    for phrase in phrases:
        phrase = str(phrase).strip()
        if not phrase:
            continue

        pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"

        def replace_match(match: re.Match[str]) -> str:
            token = f"\ue000{len(protected)}\ue001"
            protected[token] = match.group(0)
            return token

        text = re.sub(pattern, replace_match, text, flags=re.IGNORECASE)
    return text, protected


def clean_text(text: str, config: dict) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text, protected_phrases = protect_literal_phrases(
        text,
        config.get("protected_phrases", []),
    )
    commands = {
        source.strip().casefold(): replacement
        for source, replacement in config.get("command_replacements", {}).items()
        if source.strip()
    }
    if commands:
        # Match complete commands once, longest first. Whisper may capitalize a
        # standalone command or add a final period that should not be pasted.
        alternatives = "|".join(re.escape(source) for source in sorted(commands, key=len, reverse=True))
        pattern = rf"(?<!\w)(?P<command>{alternatives})(?!\w)(?:[.!?](?=\s|$))?"
        text = re.sub(pattern, lambda match: commands[match.group("command").casefold()], text, flags=re.IGNORECASE)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r" +([,.;:!?\)])", r"\1", text)
    text = re.sub(r"\( +", "(", text).strip(" \t")
    for token, phrase in protected_phrases.items():
        text = text.replace(token, phrase)
    for source, replacement in config.get("custom_terms", {}).items():
        text = re.sub(re.escape(source), replacement, text, flags=re.IGNORECASE)
    if config.get("prepend_space") and text and not text.startswith("\n"):
        text = " " + text
    if config.get("append_space") and text and not text.endswith((" ", "\n")):
        text += " "
    return text



def log_runtime_error(context: str, exc: Exception) -> None:
    try:
        log_path = ROOT / "traveldesk-whisper-error.log"
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {context}: {exc}\n")
            fh.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            fh.write("\n")
    except Exception:
        pass
def user_error_message(exc: Exception) -> str:
    message = str(exc)
    lower = message.lower()
    if "insufficient_quota" in lower or "exceeded your current quota" in lower:
        return "OpenAI quota/billing"
    if "missing openai_api_key" in lower:
        return "Missing OPENAI_API_KEY"
    if "rate limit" in lower or "429" in lower:
        return "OpenAI rate limit"
    return message[:42]

class FloatingStatusBar:
    def __init__(self, app: "DictationApp") -> None:
        self.app = app
        self.state = "idle"
        self.message = "Ready"
        self.spinner_index = 0
        self.visible_until = 0.0
        self.idle_width = 64
        self.active_width = 94
        self.processing_width = 58
        self.status_width = 74
        self.height = 22
        self.root = tk.Tk()
        self.root.title(f"TravelDesk Whisper {APP_VERSION}")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.94)
        self.last_topmost_refresh = 0.0
        self.root.configure(bg="#101418")
        self.root.wm_attributes("-transparentcolor", "#101418")
        self.canvas = tk.Canvas(self.root, width=self.active_width, height=self.height, highlightthickness=0, bg="#101418")
        self.canvas.pack(fill="both", expand=True)
        self.root.bind("<Double-Button-1>", lambda _event: self.hide())
        self.root.bind("<Button-3>", self.toggle_help)
        self.position_bottom_center(self.idle_width)
        self.draw()
        if time.time() - self.last_topmost_refresh > 0.8:
            self.last_topmost_refresh = time.time()
            self.keep_on_top()
        self.root.after(55, self.animate)

    def current_width(self) -> int:
        if self.state == "recording":
            return self.active_width
        if self.state == "transcribing":
            return self.processing_width
        if self.state in {"done", "error"}:
            return self.status_width
        return self.idle_width if not self.visible_until else 104

    def position_bottom_center(self, width: int | None = None) -> None:
        width = width or self.current_width()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = int((screen_width - width) / 2)
        y = int(screen_height - self.height - 54)
        self.root.geometry(f"{width}x{self.height}+{x}+{y}")
        self.canvas.configure(width=width, height=self.height)

    def toggle_help(self, _event=None) -> None:
        self.set_state("idle", "Ctrl+Space", 2.0)

    def set_state(self, state: str, message: str | None = None, transient_seconds: float = 0) -> None:
        def apply() -> None:
            self.state = state
            if message:
                self.message = message
            self.visible_until = time.time() + transient_seconds if transient_seconds else 0.0
            self.position_bottom_center()
            self.draw()
        self.root.after(0, apply)

    def draw_round_rect(self, x1, y1, x2, y2, radius, fill, outline="", width=1) -> None:
        points = [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        ]
        self.canvas.create_polygon(points, smooth=True, fill=fill, outline=outline, width=width)

    def draw(self) -> None:
        self.canvas.delete("all")
        width = self.current_width()
        palettes = {
            "idle": ("#17151f", "#7c3aed", "#a78bfa"),
            "recording": ("#181321", "#8b5cf6", "#c4b5fd"),
            "transcribing": ("#171821", "#8b5cf6", "#c4b5fd"),
            "done": ("#101b17", "#2dd4bf", "#99f6e4"),
            "error": ("#211316", "#fb7185", "#fecdd3"),
        }
        bg, accent, soft = palettes.get(self.state, palettes["idle"])
        self.draw_round_rect(1, 1, width - 1, self.height - 1, 11, bg, "#3b3348", 1)
        if self.state == "recording":
            self.draw_recording(width, accent, soft)
        elif self.state == "transcribing":
            self.draw_processing(width, accent)
        elif self.state == "done":
            self.draw_done(width, accent)
        elif self.state == "error":
            self.draw_error(width, accent)
        else:
            self.draw_idle(width, accent)

    def draw_idle(self, width: int, accent: str) -> None:
        cx = 16 if self.visible_until else width / 2
        self.canvas.create_oval(cx - 3, 8, cx + 3, 14, fill=accent, outline="")
        if self.visible_until:
            self.canvas.create_text(cx + 10, 11, text=self.message, fill="#b8b0c9", font=("Segoe UI", 7), anchor="w")

    def draw_recording(self, width: int, accent: str, soft: str) -> None:
        level = max(0.04, min(1.0, self.app.audio_level * 7.5))
        now = time.time() * 8
        center = width / 2
        self.canvas.create_oval(7, 8, 13, 14, fill=accent, outline="")
        for i in range(13):
            distance = abs(i - 6) / 6
            wave = (math.sin(now + i * 0.72) + 1) / 2
            bar = 3 + (12 * level * (0.38 + wave) * (1 - distance * 0.35))
            x = center - 33 + i * 5.5
            color = accent if i % 2 else soft
            self.canvas.create_line(x, 11 - bar / 2, x, 11 + bar / 2, fill=color, width=1.6, capstyle="round")
        if self.app.toggle_recording:
            self.canvas.create_oval(width - 13, 8, width - 7, 14, outline=soft, width=1)

    def draw_processing(self, width: int, accent: str) -> None:
        cx, cy = width / 2, 11
        for i in range(10):
            angle = (i + self.spinner_index) * (math.pi * 2 / 10)
            amount = 0.16 + (i / 10) * 0.84
            color = self.mix("#343246", accent, amount)
            x = cx + math.cos(angle) * 7
            y = cy + math.sin(angle) * 7
            self.canvas.create_oval(x - 1.4, y - 1.4, x + 1.4, y + 1.4, fill=color, outline="")

    def draw_done(self, width: int, accent: str) -> None:
        cx = width / 2 - 10
        self.canvas.create_line(cx - 5, 11, cx - 1, 15, fill=accent, width=1.7, capstyle="round")
        self.canvas.create_line(cx - 1, 15, cx + 7, 7, fill=accent, width=1.7, capstyle="round")
        self.canvas.create_text(cx + 13, 11, text="OK", fill="#b9f8e8", font=("Segoe UI", 7), anchor="w")

    def draw_error(self, width: int, accent: str) -> None:
        cx = width / 2 - 12
        self.canvas.create_line(cx - 4, 7, cx + 4, 15, fill=accent, width=1.7, capstyle="round")
        self.canvas.create_line(cx + 4, 7, cx - 4, 15, fill=accent, width=1.7, capstyle="round")
        self.canvas.create_text(cx + 11, 11, text="Retry", fill="#fecdd3", font=("Segoe UI", 7), anchor="w")

    def mix(self, left: str, right: str, amount: float) -> str:
        amount = max(0, min(1, amount))
        l = tuple(int(left[i:i + 2], 16) for i in (1, 3, 5))
        r = tuple(int(right[i:i + 2], 16) for i in (1, 3, 5))
        return "#" + "".join(f"{int(a + (b - a) * amount):02x}" for a, b in zip(l, r))

    def keep_on_top(self) -> None:
        if self.root.state() == "withdrawn":
            return
        self.root.attributes("-topmost", True)
        if os.name == "nt":
            try:
                hwnd_topmost = -1
                flags = 0x0001 | 0x0002 | 0x0010 | 0x0040
                ctypes.windll.user32.SetWindowPos(self.root.winfo_id(), hwnd_topmost, 0, 0, 0, 0, flags)
            except Exception:
                pass
    def animate(self) -> None:
        self.spinner_index = (self.spinner_index + 1) % 10
        if self.state in {"recording", "transcribing"}:
            self.draw()
        elif self.visible_until and time.time() > self.visible_until:
            self.visible_until = 0.0
            self.state = "idle"
            self.message = "Ready"
            self.position_bottom_center()
            self.draw()
        if time.time() - self.last_topmost_refresh > 0.8:
            self.last_topmost_refresh = time.time()
            self.keep_on_top()
        self.root.after(55, self.animate)

    def show(self) -> None:
        def apply() -> None:
            self.root.deiconify()
            self.keep_on_top()
        self.root.after(0, apply)

    def hide(self) -> None:
        self.root.after(0, self.root.withdraw)

    def toggle_visibility(self) -> None:
        def apply() -> None:
            if self.root.state() == "withdrawn":
                self.root.deiconify()
                self.position_bottom_center()
                self.keep_on_top()
            else:
                self.root.withdraw()
        self.root.after(0, apply)

    def close(self) -> None:
        self.root.after(0, self.root.destroy)
    def run(self) -> None:
        self.root.mainloop()


class DictationApp:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.sample_rate = int(config.get("sample_rate", 16000))
        self.hotkey = set(config.get("hotkey", ["ctrl", "space"]))
        self.double_tap_seconds = float(config.get("toggle_double_tap_seconds", 0.55))
        self.pressed: set[str] = set()
        self.hotkey_active = False
        self.last_hotkey_press_at = 0.0
        self.toggle_recording = False
        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self.frames: list[np.ndarray] = []
        self.stream: sd.InputStream | None = None
        self.recording_started_at = 0.0
        self.recording_timer: threading.Timer | None = None
        self.recording = False
        self.transcribing = False
        self.audio_level = 0.0
        self.processing_progress = 0.0
        self.model: WhisperModel | None = None
        self.openai_client = None
        self.keyboard = keyboard.Controller()
        self.status: FloatingStatusBar | None = None
        self.listener: keyboard.Listener | None = None
        self.target_window = None
        self.tray_icon = None
        self.model_lock = threading.Lock()
        self.recording_lock = threading.RLock()

    def make_tray_image(self) -> Image.Image:
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 18, 56, 46), radius=14, fill=(24, 19, 33, 255), outline=(139, 92, 246, 255), width=3)
        draw.ellipse((26, 27, 38, 39), fill=(167, 139, 250, 255))
        return image

    def start_tray_icon(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem("Mostrar/Ocultar", lambda _icon, _item: self.toggle_pill()),
            pystray.MenuItem("Mostrar", lambda _icon, _item: self.show_pill()),
            pystray.MenuItem("Ocultar", lambda _icon, _item: self.hide_pill()),
            pystray.MenuItem("Ayuda de uso", lambda _icon, _item: self.show_usage_help()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", lambda _icon, _item: self.quit_app()),
        )
        self.tray_icon = pystray.Icon("TravelDeskWhisper", self.make_tray_image(), f"TravelDesk Whisper {APP_VERSION}", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_pill(self) -> None:
        if self.status:
            self.status.show()

    def hide_pill(self) -> None:
        if self.status:
            self.status.hide()

    def toggle_pill(self) -> None:
        if self.status:
            self.status.toggle_visibility()

    def show_usage_help(self) -> None:
        if self.status:
            self.status.root.after(0, lambda: show_usage_message(self.status.root, self.config))

    def quit_app(self) -> None:
        with self.recording_lock:
            self.recording = False
            if self.recording_timer:
                self.recording_timer.cancel()
                self.recording_timer = None
            self.close_audio_stream()
        if self.listener:
            self.listener.stop()
        if self.tray_icon:
            self.tray_icon.stop()
        if self.status:
            self.status.close()
    def beep(self, frequency: int, duration: int) -> None:
        if self.config.get("status_beeps") and winsound:
            try:
                winsound.Beep(frequency, duration)
            except RuntimeError:
                pass  # An unavailable sound output must not disable dictation.

    def set_status(self, state: str, message: str | None = None, transient_seconds: float = 0) -> None:
        if self.status:
            self.status.set_state(state, message, transient_seconds)

    def transcription_provider(self) -> str:
        return str(self.config.get("transcription_provider", "local")).strip().lower()

    def openai_key_configured(self) -> tuple[bool, str]:
        openai_config = self.config.get("openai", {})
        env_name = str(openai_config.get("api_key_env", "OPENAI_API_KEY"))
        return bool(os.environ.get(env_name) or openai_config.get("api_key")), env_name
    def load_openai_client(self):
        if self.openai_client is not None:
            return self.openai_client
        if OpenAI is None:
            raise RuntimeError("Missing openai package")
        openai_config = self.config.get("openai", {})
        env_name = str(openai_config.get("api_key_env", "OPENAI_API_KEY"))
        api_key = os.environ.get(env_name) or openai_config.get("api_key")
        if not api_key:
            raise RuntimeError(f"Missing {env_name}")
        self.openai_client = OpenAI(
            api_key=str(api_key),
            timeout=float(openai_config.get("timeout_seconds", 20)),
            max_retries=int(openai_config.get("max_retries", 1)),
        )
        return self.openai_client

    def transcribe_openai(self, temp_path: Path) -> str:
        client = self.load_openai_client()
        openai_config = self.config.get("openai", {})
        transcription_config = self.config.get("transcription", {})
        model = str(openai_config.get("model", "gpt-4o-transcribe"))
        request = {
            "model": model,
            "response_format": str(openai_config.get("response_format", "text")),
        }
        prompt = openai_config.get("prompt") or transcription_config.get("initial_prompt")
        if prompt and model != "gpt-4o-transcribe-diarize":
            request["prompt"] = str(prompt)
        language = openai_config.get("language", self.config.get("language"))
        if language:
            request["language"] = str(language)
        with temp_path.open("rb") as audio_file:
            result = client.audio.transcriptions.create(file=audio_file, **request)
        if isinstance(result, str):
            return result
        return str(getattr(result, "text", ""))

    def transcribe_local(self, temp_path: Path, samples: np.ndarray) -> str:
        model = self.load_model()
        self.set_status("transcribing", "Thinking")
        language = self.config.get("language")
        transcription_config = self.config.get("transcription", {})
        kwargs = {
            "vad_filter": bool(transcription_config.get("vad_filter", True)),
            "beam_size": int(transcription_config.get("beam_size", 1)),
            "condition_on_previous_text": bool(transcription_config.get("condition_on_previous_text", False)),
        }
        initial_prompt = transcription_config.get("initial_prompt")
        if initial_prompt:
            kwargs["initial_prompt"] = str(initial_prompt)
        if language:
            kwargs["language"] = language
        segments, _info = model.transcribe(str(temp_path), **kwargs)
        duration_seconds = max(float(samples.shape[0]) / float(self.sample_rate), 0.1)
        segment_texts = []
        for segment in segments:
            segment_texts.append(segment.text)
            if getattr(segment, "end", None) is not None:
                self.processing_progress = min(0.96, max(self.processing_progress, float(segment.end) / duration_seconds))
        return "".join(segment_texts)
    def load_model(self) -> WhisperModel:
        with self.model_lock:
            if self.model is not None:
                return self.model
            print("Loading Whisper model...")
            self.set_status("transcribing", "Loading")
            model_name = str(self.config.get("model_size", "small"))
            bundled_model = ROOT / "models" / model_name
            model_source = str(bundled_model) if (bundled_model / "model.bin").is_file() else model_name
            self.model = WhisperModel(
                model_source,
                device=self.config.get("device", "cpu"),
                compute_type=self.config.get("compute_type", "int8"),
            )
            return self.model

    def preload_model(self) -> None:
        try:
            self.load_model()
            if not self.recording and not self.transcribing:
                self.set_status("idle", "Ready")
        except Exception as exc:
            print(f"Model preload error: {exc}")
            if not self.recording and not self.transcribing:
                self.set_status("error", user_error_message(exc), 2.4)

    def audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            print(f"Audio status: {status}")
        self.audio_level = float(np.sqrt(np.mean(np.square(indata)))) if indata.size else 0.0
        self.audio_queue.put(indata.copy())

    def start_recording(self, toggle: bool = False) -> None:
        with self.recording_lock:
            if self.recording or self.transcribing:
                return
            self.toggle_recording = toggle
            self.target_window = TargetWindow.capture()
            self.frames = []
            self.audio_level = 0.0
            while not self.audio_queue.empty():
                self.audio_queue.get_nowait()
            try:
                self.stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="float32",
                    callback=self.audio_callback,
                )
                self.stream.start()
            except Exception as exc:
                self.recording_failed("start_recording", exc)
                return
            self.recording_started_at = time.time()
            self.recording = True
            max_record_seconds = float(self.config.get("max_record_seconds", 0) or 0)
            if max_record_seconds > 0:
                self.recording_timer = threading.Timer(max_record_seconds, self.stop_recording)
                self.recording_timer.daemon = True
                self.recording_timer.start()
            self.set_status("recording", "Toggle" if toggle else "Hold")
            self.beep(880, 80)
            print("Recording...")

    def close_audio_stream(self) -> Exception | None:
        stream, self.stream = self.stream, None
        error = None
        if stream is not None:
            try:
                stream.stop()
            except Exception as exc:
                error = exc
            finally:
                try:
                    stream.close()
                except Exception as exc:
                    error = error or exc
        return error

    def recording_failed(self, context: str, exc: Exception) -> None:
        log_runtime_error(context, exc)
        self.recording = False
        self.toggle_recording = False
        self.audio_level = 0.0
        if self.recording_timer:
            self.recording_timer.cancel()
            self.recording_timer = None
        self.close_audio_stream()
        self.frames = []
        while not self.audio_queue.empty():
            self.audio_queue.get_nowait()
        self.set_status("error", "Revisa el micrófono", 3.0)
        self.beep(220, 100)

    def stop_recording(self) -> None:
        with self.recording_lock:
            if not self.recording:
                return
            self.recording = False
            self.toggle_recording = False
            if self.recording_timer:
                self.recording_timer.cancel()
                self.recording_timer = None
            error = self.close_audio_stream()
            if error:
                self.recording_failed("stop_recording", error)
                return
            while not self.audio_queue.empty():
                self.frames.append(self.audio_queue.get_nowait())
            duration = time.time() - self.recording_started_at
            if duration < float(self.config.get("min_record_seconds", 0.35)) or not self.frames:
                print("Recording too short.")
                self.set_status("idle", "Too short", 1.2)
                self.beep(440, 80)
                return
            samples = np.concatenate(self.frames, axis=0)
            self.transcribing = True
            self.set_status("transcribing", "Processing")
            threading.Thread(target=self.transcribe_and_paste, args=(samples,), daemon=True).start()

    def transcribe_and_paste(self, samples: np.ndarray) -> None:
        self.transcribing = True
        self.processing_progress = 0.0
        temp_path = Path(tempfile.gettempdir()) / f"local_whisper_{int(time.time() * 1000)}.wav"
        try:
            self.beep(660, 80)
            write_wav(temp_path, samples, self.sample_rate)
            provider = self.transcription_provider()
            duration_seconds = max(float(samples.shape[0]) / float(self.sample_rate), 0.1)
            if provider == "openai":
                self.set_status("transcribing", "OpenAI")
                self.log_openai_usage(duration_seconds)
                raw_text = self.transcribe_openai(temp_path)
            elif provider == "local":
                raw_text = self.transcribe_local(temp_path, samples)
            else:
                raise RuntimeError(f"Unknown provider: {provider}")
            self.processing_progress = 1.0
            text = clean_text(raw_text, self.config)
            if not text:
                print("No text detected.")
                self.set_status("idle", "No text", 1.4)
                self.beep(330, 120)
                return
            print(f"Text: {text}")
            self.set_status("transcribing", "Pasting")
            self.paste_text(text)
            self.set_status("done", "OK", 1.0)
            self.beep(1040, 80)
        except Exception as exc:
            print(f"Error: {exc}")
            log_runtime_error("transcribe_and_paste", exc)
            self.processing_progress = 0.0
            self.set_status("error", user_error_message(exc), 2.4)
            self.beep(220, 180)
        finally:
            self.transcribing = False
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def log_openai_usage(self, duration_seconds: float) -> None:
        log_path = ROOT / "openai-usage-local.jsonl"
        event = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "model": str(self.config.get("openai", {}).get("model", "")),
            "audio_seconds": round(duration_seconds, 2),
            "audio_minutes": round(duration_seconds / 60, 4),
        }
        try:
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=True) + "\n")
        except OSError:
            pass

    def paste_text(self, text: str) -> None:
        TargetWindow.restore(self.target_window)
        set_clipboard_text(text)
        time.sleep(0.05)
        modifier = keyboard.Key.cmd if platform.system().lower() == "darwin" else keyboard.Key.ctrl
        with self.keyboard.pressed(modifier):
            self.keyboard.press("v")
            self.keyboard.release("v")

    def hotkey_is_down(self) -> bool:
        return self.hotkey.issubset(self.pressed)

    def handle_hotkey_down(self) -> None:
        now = time.time()
        is_double_tap = now - self.last_hotkey_press_at <= self.double_tap_seconds
        self.last_hotkey_press_at = now
        if self.transcribing:
            return
        if self.recording and self.toggle_recording:
            self.stop_recording()
            return
        toggle_enabled = bool(self.config.get("enable_toggle_recording", True))
        if is_double_tap:
            if not toggle_enabled:
                return
            if self.recording:
                self.toggle_recording = True
                self.set_status("recording", "Toggle")
            else:
                self.start_recording(toggle=True)
            return
        self.start_recording(toggle=False)

    def on_press(self, key) -> None:
        name = normalize_key_name(key)
        if not name:
            return
        self.pressed.add(name)
        if self.hotkey_is_down() and not self.hotkey_active:
            self.hotkey_active = True
            self.handle_hotkey_down()

    def on_release(self, key) -> None:
        name = normalize_key_name(key)
        was_down = self.hotkey_is_down()
        if name:
            self.pressed.discard(name)
        if was_down and not self.hotkey_is_down():
            self.hotkey_active = False
            if self.recording and not self.toggle_recording:
                self.stop_recording()

    def run(self) -> None:
        hotkey_label = "+".join(self.hotkey)
        print(f"TravelDesk Whisper {APP_VERSION}")
        print(f"Hold {hotkey_label} to dictate.")
        print("Double-click the floating pill to hide. Use tray icon to show or exit.")
        self.status = FloatingStatusBar(self)
        if self.transcription_provider() == "openai":
            configured, env_name = self.openai_key_configured()
            if not configured:
                self.set_status("error", f"Missing {env_name}", 4.0)
        if self.transcription_provider() == "local" and self.config.get("preload_model", True):
            threading.Thread(target=self.preload_model, daemon=True).start()
        self.listener = keyboard.Listener(on_press=self.on_press, on_release=self.on_release)
        self.listener.daemon = True
        self.listener.start()
        self.start_tray_icon()
        self.status.run()
        if self.listener:
            self.listener.stop()
        if self.tray_icon:
            self.tray_icon.stop()

def show_startup_error(exc: Exception) -> None:
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showerror(
            "TravelDesk Whisper",
            "No se pudo iniciar TravelDesk Whisper.\n\n"
            f"Detalle: {short_error_message(exc)}",
            parent=root,
        )
        root.destroy()
    except Exception:
        pass


def run_self_test(output_path: Path, audio_path: Path | None = None) -> int:
    """Exercise the packaged local engine without recording, hotkeys or paste."""
    import ctranslate2
    import faster_whisper

    result = {
        "version": APP_VERSION,
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable,
        "faster_whisper": faster_whisper.__version__,
        "ctranslate2": ctranslate2.__version__,
        "sounddevice": sd.__version__,
        "ok": False,
    }
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        app = DictationApp(config)
        started = time.perf_counter()
        app.load_model()
        result["model_load_seconds"] = round(time.perf_counter() - started, 3)
        result["model"] = config.get("model_size", "small")
        result["bundled_model"] = (ROOT / "models" / result["model"] / "model.bin").is_file()
        probe_config = {**config, "append_space": False, "prepend_space": False}
        assert clean_text("Primera nueva línea segunda", probe_config) == "Primera\nsegunda"
        assert clean_text("Nueva línea.", probe_config) == "\n"
        assert clean_text("punto de venta", probe_config) == "punto de venta"
        result["text_commands"] = "passed"
        if audio_path:
            from faster_whisper.audio import decode_audio

            samples = decode_audio(str(audio_path), sampling_rate=app.sample_rate)
            started = time.perf_counter()
            text = app.transcribe_local(audio_path, samples)
            result["transcribe_seconds"] = round(time.perf_counter() - started, 3)
            result["text"] = clean_text(text, config)
            if not result["text"].strip():
                raise RuntimeError("El audio de prueba no produjo texto.")
        result["ok"] = True
    except Exception as exc:
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if result["ok"] else 1


def main() -> None:
    if "--self-test" in sys.argv:
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--self-test", type=Path, required=True)
        parser.add_argument("--audio", type=Path)
        args = parser.parse_args()
        raise SystemExit(run_self_test(args.self_test, args.audio))
    try:
        os.chdir(ROOT)
        config = load_config()
        if str(config.get("transcription_provider", "local")).strip().lower() == "openai":
            if not ensure_openai_api_key(config):
                return
        app = DictationApp(config)
        app.run()
    except Exception as exc:
        show_startup_error(exc)


if __name__ == "__main__":
    main()
