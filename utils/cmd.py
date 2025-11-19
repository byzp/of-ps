import logging
import threading
import time
import signal
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.shortcuts import print_formatted_text
import utils.log as log_module

_stop_event = threading.Event()
_prompt_thread = None
_sigint_lock = threading.Lock()
_sigint_count = 0
_sigint_deadline = 0.0
_SIGINT_WINDOW = 10.0


def _print_to_console(text):
    try:
        print_formatted_text(ANSI(text))
    except Exception:
        try:
            print(text)
        except Exception:
            pass


def _handle_sigint():
    global _sigint_count, _sigint_deadline
    with _sigint_lock:
        now = time.time()
        if now > _sigint_deadline:
            _sigint_count = 0
        _sigint_count += 1
        _sigint_deadline = now + _SIGINT_WINDOW
        if _sigint_count == 1:
            logging.getLogger(__name__).warning(
                "Press Ctrl+C again within "+str(_SIGINT_WINDOW)+" seconds to exit"
            )
        else:
            _stop_event.set()


def _prompt_loop():
    session = PromptSession()
    with patch_stdout():
        while not _stop_event.is_set():
            try:
                text = session.prompt("> ")
            except KeyboardInterrupt:
                _handle_sigint()
                continue
            cmd=text.strip()
            if cmd:
                if cmd=="stop":
                    _stop_event.set()
                pass


def start():
    global _prompt_thread
    log_module.start(_stop_event, desired_level=logging.INFO)
    try:
        signal.signal(signal.SIGINT, _handle_sigint)
    except Exception:
        pass
    _prompt_thread = threading.Thread(target=_prompt_loop, daemon=True)
    _prompt_thread.start()
    return _stop_event


def wait(timeout=None):
    return _stop_event.wait(timeout)


