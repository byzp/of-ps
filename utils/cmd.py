import logging
import threading
import time
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.shortcuts import print_formatted_text

import utils.log as log_module
import utils.command_handler as cmd_h
import utils.cmd_exec as cmd_exec

_stop_event = threading.Event()
_prompt_thread = None
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


def _prompt_loop():
    global _sigint_count, _sigint_deadline

    session = PromptSession()
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
                    continue
                if cmd in cmd_h.COMMANDS:
                    cmd_h.COMMANDS[cmd]()
                    continue
                cmd_exec.cmd_exec(cmd)


def start():
    global _prompt_thread
    log_module.start(_stop_event, desired_level=logging.INFO)
    _prompt_thread = threading.Thread(target=_prompt_loop, daemon=True)
    _prompt_thread.start()
    return _stop_event


def wait(timeout=None):
    return _stop_event.wait(timeout)
