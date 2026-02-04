"""
Start API server in background thread, then open Windows GUI.
При ошибке запуска сервера показываем её в окне.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import traceback
import urllib.request

# В exe без консоли sys.stdout/stderr = None, uvicorn падает на isatty()
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# Явный импорт, чтобы PyInstaller включил пакеты в exe
import uvicorn  # noqa: F401
import fastapi  # noqa: F401
import httpx  # noqa: F401

# Ошибка из потока uvicorn (если сервер не поднялся)
_server_error: list[BaseException] = []


def run_uvicorn():
    global _server_error
    try:
        from config import API_HOST, API_PORT
        uvicorn.run("main:app", host=API_HOST, port=API_PORT, log_level="warning")
    except Exception as e:
        _server_error.append(e)


def _wait_for_api(max_wait_sec: float = 10, interval: float = 0.2) -> bool:
    """Ждём, пока API начнёт отвечать. Возвращает True если готов."""
    from config import API_HOST, API_PORT
    url = f"http://{API_HOST}:{API_PORT}/api/funding?symbol=BTCUSDT"
    deadline = time.monotonic() + max_wait_sec
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except OSError:
            pass
        except Exception:
            pass
        time.sleep(interval)
    return False


def _show_error_and_exit(msg: str) -> None:
    """Показать ошибку в окне и выйти (без tkinter)."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "FundingRate — ошибка", 0x10)
    except Exception:
        print(msg, file=sys.stderr)
    sys.exit(1)


def main():
    global _server_error
    t = threading.Thread(target=run_uvicorn, daemon=True)
    t.start()

    if not _wait_for_api():
        if _server_error:
            err = _server_error[0]
            tb = traceback.format_exception(type(err), err, err.__traceback__)
            _show_error_and_exit("Сервер не запустился.\n\n" + str(err) + "\n\n" + "".join(tb))
        _show_error_and_exit("Сервер не ответил. Запустите exe из командной строки для вывода ошибок.")

    from gui.window import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()
