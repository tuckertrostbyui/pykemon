"""
Entry point for `python -m pykemon`.

Usage:
    python -m pykemon host [port]        # Host a battle (default port 5555)
    python -m pykemon join <ip> [port]   # Join a battle
"""

import sys

from .battle import DEFAULT_PORT, run_client, run_host


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        print("\n  pykemon — Pokemon socket battle")
        print("\n  Usage:")
        print("    python -m pykemon host [port]         # Host a battle")
        print("    python -m pykemon join <ip> [port]    # Join a battle")
        print(f"\n  Default port: {DEFAULT_PORT}\n")
        sys.exit(0)

    cmd = args[0].lower()

    if cmd == "host":
        port = int(args[1]) if len(args) > 1 else DEFAULT_PORT
        run_host(port)

    elif cmd == "join":
        if len(args) < 2:
            print("  Error: 'join' requires a host IP address.")
            print("  Example: python -m pykemon join 192.168.1.42")
            sys.exit(1)
        host_ip = args[1]
        port = int(args[2]) if len(args) > 2 else DEFAULT_PORT
        run_client(host_ip, port)

    else:
        print(f"  Unknown command: '{cmd}'")
        print("  Run 'python -m pykemon --help' for usage.")
        sys.exit(1)


main()
