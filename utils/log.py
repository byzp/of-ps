import logging
import queue
import threading
from logging.handlers import QueueHandler
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.shortcuts import print_formatted_text
from colorama import Fore, Style, init as color_init

color_init(wrap=False)

_log_queue = None
_consumer_thread = None
_formatter = None


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
            record = q.get(timeout=0.1)
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


def start(stop_event: threading.Event = None):
    global _log_queue, _consumer_thread, _formatter
    if stop_event is None:
        stop_event = threading.Event()
    if _log_queue is not None:
        return stop_event
    root = logging.getLogger()
    for h in root.handlers:
        if getattr(h, "formatter", None):
            _formatter = h.formatter
            break
    _log_queue = queue.Queue()
    qh = QueueHandler(_log_queue)
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(qh)
    _consumer_thread = threading.Thread(
        target=_log_consumer_loop, args=(_log_queue, stop_event), daemon=True
    )
    _consumer_thread.start()
    return stop_event
