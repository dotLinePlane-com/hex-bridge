#!/usr/bin/env python3
"""
HEX-Bridge Full Test Suite Runner

Usage:
    python run_all.py                      # all tests
    python run_all.py system               # system tests only
    python run_all.py uart                 # UART tests only
    python run_all.py protocol             # protocol tests only
    python run_all.py uart --com24 COM24   # UART tests with COM24
"""

import sys, os, subprocess

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

SCRIPTS = {
    'system':   'test_system.py',
    'uart':     'test_uart.py',
    'protocol': 'test_protocol.py',
}

if __name__ == '__main__':
    args = sys.argv[1:]

    if not args or args[0] not in SCRIPTS:
        selection = list(SCRIPTS.keys())
    else:
        selection = [args[0]]

    total_rc = 0
    for name in selection:
        script = os.path.join(TESTS_DIR, SCRIPTS[name])
        print(f'\n{"#" * 50}')
        print(f'# Running: {name}')
        print(f'{"#" * 50}')
        extra_args = sys.argv[2:] if args and args[0] == name else []
        rc = subprocess.call([sys.executable, script] + extra_args)
        total_rc |= rc

    sys.exit(total_rc)
