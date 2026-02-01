import sys
import types
import logging
import threading
import time
import traceback
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.shortcuts import print_formatted_text
from prompt_toolkit.application import get_app_or_none

import utils.log as log_module
import utils.command_handler as cmd_h
import utils.cmd_exec as cmd_exec

_stop_event = threading.Event()
_prompt_thread = None
_session = None
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


def _restore_terminal():
    try:
        app = None
        if _session is not None:
            app = getattr(_session, "app", None)
        if app is None:
            app = get_app_or_none()
        if app is not None and getattr(app, "is_running", False):
            try:
                app.exit()
            except Exception:
                pass
    except Exception:
        pass


def _handle_uncaught_main(exc_type, exc_value, exc_traceback):
    try:
        logging.error(
            "Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback)
        )
        try:
            sys.__stderr__.write("Uncaught exception in main thread:\n")
            sys.__stderr__.write(
                "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            )
        except Exception:
            pass
    finally:
        _restore_terminal()
        _stop_event.set()


def _handle_uncaught_thread(args):
    try:
        logging.error(
            "Uncaught exception in thread %s",
            getattr(args, "thread", getattr(args, "thread_name", "<unknown>")),
            exc_info=(
                getattr(args, "exc_type", None),
                getattr(args, "exc_value", None),
                getattr(args, "exc_traceback", None),
            ),
        )
        try:
            sys.__stderr__.write(
                "Uncaught exception in thread %s:\n"
                % getattr(args, "thread", getattr(args, "thread_name", "<unknown>"))
            )
            sys.__stderr__.write(
                "".join(
                    traceback.format_exception(
                        getattr(args, "exc_type", None),
                        getattr(args, "exc_value", None),
                        getattr(args, "exc_traceback", None),
                    )
                )
            )
        except Exception:
            pass
    finally:
        _restore_terminal()
        _stop_event.set()


if hasattr(threading, "excepthook"):
    threading.excepthook = _handle_uncaught_thread
else:
    _orig_thread_run = threading.Thread.run

    def _thread_run_with_excepthook(self):
        try:
            _orig_thread_run(self)
        except Exception:
            exc_type, exc_value, exc_tb = sys.exc_info()
            args = types.SimpleNamespace(
                thread=self,
                exc_type=exc_type,
                exc_value=exc_value,
                exc_traceback=exc_tb,
            )
            try:
                _handle_uncaught_thread(args)
            except Exception:
                pass
            raise

    threading.Thread.run = _thread_run_with_excepthook


sys.excepthook = _handle_uncaught_main


def _prompt_loop():
    global _sigint_count, _sigint_deadline, _session
    session = PromptSession()
    _session = session
    try:
        with patch_stdout():
            while not _stop_event.is_set():
                try:
                    text = session.prompt("> ")
                except EOFError:
                    _stop_event.set()
                    return
                except KeyboardInterrupt:
                    now = time.time()
                    if now > _sigint_deadline:
                        _sigint_count = 0
                    if _sigint_count == 0:
                        logging.warning(
                            "Press Ctrl+C again within "
                            + str(_SIGINT_WINDOW)
                            + " seconds to exit"
                        )
                        _sigint_count = 1
                        _sigint_deadline = now + _SIGINT_WINDOW
                    else:
                        _stop_event.set()
                    continue
                cmd = text.strip()
                if cmd:
                    if cmd == "stop":
                        _stop_event.set()
                        return
                    if cmd == "help":
                        print(",".join(cmd_h.COMMANDS.keys()))
                        print(
                            "give player_id/all item_id [num]\nfirework id [dur_time] [start_time]\ntime 1-86400\ntp player_id/all scene_id [channel_id]"
                        )
                        continue
                    if cmd in cmd_h.COMMANDS:
                        cmd_h.COMMANDS[cmd]()
                        continue
                    cmd_exec.cmd_exec(cmd)

    finally:
        _session = None
        _restore_terminal()


def start():
    global _prompt_thread
    log_module.start(_stop_event)
    _prompt_thread = threading.Thread(target=_prompt_loop, daemon=True)
    _prompt_thread.start()
    return _stop_event


def wait(timeout=None):
    return _stop_event.wait(timeout)
