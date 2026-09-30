import os
import threading
import traceback

from instagram_bot import (
    main as instagram_main,
    start_activity_session,
    finish_activity_session,
    stop_xray_proxy,
)
from telegram_bot import build_application

_worker_lock = threading.Lock()
_worker_thread = None
_worker_session = None
_stop_requested = False


def _worker(mode, location=None, location_index=None):
    global _worker_thread, _worker_session, _stop_requested

    _stop_requested = False
    _worker_session = start_activity_session()

    try:
        if mode == "saved":
            os.environ["BOT_USE_SAVED_USERS"] = "1"
            os.environ.pop("BOT_LOCATION_NAME", None)
            os.environ.pop("BOT_LOCATION_INDEX", None)
        else:
            os.environ["BOT_USE_SAVED_USERS"] = "2"
            os.environ["BOT_LOCATION_NAME"] = location or ""
            os.environ["BOT_LOCATION_INDEX"] = str(location_index or "")

        instagram_main()
        finish_activity_session(_worker_session, status="completed")
    except KeyboardInterrupt:
        finish_activity_session(_worker_session, status="stopped_by_user")
    except Exception as exc:
        traceback.print_exc()
        try:
            finish_activity_session(_worker_session, status="failed")
        except Exception:
            pass
        print(f"WORKER ERROR: {exc}")
    finally:
        try:
            stop_xray_proxy()
        except Exception:
            pass
        with _worker_lock:
            _worker_thread = None
            _worker_session = None


def start_worker(mode="saved", location=None, location_index=None):
    global _worker_thread
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return False, "A worker is already running."

        _worker_thread = threading.Thread(
            target=_worker,
            args=(mode, location, location_index),
            daemon=True,
            name="instagram-worker",
        )
        _worker_thread.start()

    return True, "Worker started. Use /status to monitor it."


def stop_worker():
    global _stop_requested
    _stop_requested = True
    try:
        stop_xray_proxy()
    except Exception:
        pass
    return "Stop requested. The current operation may finish before the worker exits."


def worker_status():
    alive = _worker_thread is not None and _worker_thread.is_alive()
    return "Worker status: RUNNING" if alive else "Worker status: STOPPED"


def main():
    app = build_application(start_worker, stop_worker, worker_status)
    print("Telegram control bot started.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
