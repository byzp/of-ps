import logging
import queue
import threading
from logging.handlers import QueueHandler
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.shortcuts import print_formatted_text
from colorama import Fore, Style, init as color_init

color_init()

_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_formatter = logging.Formatter(_FORMAT)

_log_queue = None
_consumer_thread = None


def _format_record_to_ansi(record):
    try:
        text = _formatter.format(record)
    except Exception:
        text = f"{record.levelname}: {record.getMessage()}"
    lvl = record.levelno
    if lvl >= logging.ERROR:
        color = Fore.RED
    elif lvl >= logging.WARNING:
        color = Fore.YELLOW
    elif lvl >= logging.INFO:
        color = Fore.GREEN
    else:
        color = Fore.CYAN
    return color + text + Style.RESET_ALL


def _log_consumer_loop(q: queue.Queue, stop_event: threading.Event):
    while not stop_event.is_set():
        try:
            record = q.get(timeout=0.2)
        except queue.Empty:
            continue
        try:
            msg = _format_record_to_ansi(record)
            print_formatted_text(ANSI(msg))
        except Exception:
            pass
    while True:
        try:
            record = q.get_nowait()
        except queue.Empty:
            break
        try:
            msg = _format_record_to_ansi(record)
            print_formatted_text(ANSI(msg))
        except Exception:
            pass


def start(stop_event: threading.Event, desired_level=logging.INFO):
    global _log_queue, _consumer_thread
    if _log_queue is not None:
        return
    _log_queue = queue.Queue()
    qh = QueueHandler(_log_queue)
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(desired_level)
    qh.setLevel(desired_level)
    root.addHandler(qh)
    _consumer_thread = threading.Thread(
        target=_log_consumer_loop, args=(_log_queue, stop_event), daemon=True
    )
    _consumer_thread.start()
