"""
Battle client.

Connects to the battle server, renders the battle state in the terminal,
and sends the player's actions back to the server.
"""

from __future__ import annotations

import socket

from .protocol import recv, send
from .server import DEFAULT_PORT


# ── Display helpers ───────────────────────────────────────────────────────────

def _hp_bar(current: int, maximum: int, width: int = 24) -> str:
    ratio = max(0.0, current / maximum) if maximum else 0.0
    filled = round(ratio * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {current}/{maximum}"


def _clear() -> None:
    print("\033[2J\033[H", end="", flush=True)


def _render_full_state(state: dict) -> None:
    print("\n" + "=" * 60)
    turn = state["turn"]
    you  = state["your_trainer"]
    opp  = state["opponent_trainer"]
    print(f"{'─' * 60}")
    print(f"  Turn {turn}  |  {you} vs {opp}")
    print(f"{'─' * 60}\n")

    # Opponent's active (top)
    oa = state["opponent_active"]
    oa_types = oa["primary_type"] + (f"/{oa['secondary_type']}" if oa["secondary_type"] else "")
    print(f"  OPP  {oa['name']:<18}  {_hp_bar(oa['current_hp'], oa['max_hp'])}")
    print(f"       Lv.{oa['level']}  {oa['nature']}  [{oa_types}]")
    if oa["is_fainted"]:
        print("       ** FAINTED **")
    print()

    # Your active (bottom)
    ya = state["your_active"]
    ya_types = ya["primary_type"] + (f"/{ya['secondary_type']}" if ya["secondary_type"] else "")
    print(f"  YOU  {ya['name']:<18}  {_hp_bar(ya['current_hp'], ya['max_hp'])}")
    print(f"       Lv.{ya['level']}  {ya['nature']}  [{ya_types}]")
    if ya["is_fainted"]:
        print("       ** FAINTED **")
    print()

    # Events from the last-resolved turn
    if state["events"]:
        print("  ── Events ─────────────────────────────────────")
        for line in state["events"]:
            print(f"  {line}")
        print()

    # Roster summary
    print("  ── Your Roster ─────────────────────────────────")
    active_name = ya["name"]
    for i, p in enumerate(state["your_roster"]):
        if p["is_fainted"]:
            status = "FAINTED"
        else:
            status = f"{p['current_hp']}/{p['max_hp']} HP"
        marker = ">" if p["name"] == active_name else " "
        print(f"  {marker} {i + 1}. {p['name']:<16}  {status}")
    print()

    # Move list (only when it's your turn to act)
    if state.get("your_moves") and state["awaiting"] in ("action",):
        print("  ── Moves ────────────────────────────────────────")
        for m in state["your_moves"]:
            pwr = f"Pwr {m['power']:>3}" if m["power"] is not None else "Status  "
            acc = f"Acc {m['accuracy']:>3}" if m["accuracy"] is not None else "Acc ---"
            pp  = f"PP {m['current_pp']:>2}/{m['max_pp']}"
            print(
                f"    {m['slot'] + 1}. {m['move_name']:<22}"
                f"  [{m['type']:>10}]  {pwr}  {acc}  {pp}"
            )
        print()


def _render_force_switch(state: dict, available: list[int]) -> None:
    print("\n" + "=" * 60)
    print("  ── FORCE SWITCH ────────────────────────────────")
    print("  Your Pokemon fainted! Choose a replacement.\n")
    roster = state["your_roster"]
    for idx in available:
        p = roster[idx]
        print(f"    {idx + 1}. {p['name']:<16}  {p['current_hp']}/{p['max_hp']} HP")
    print()


# ── Action prompts ────────────────────────────────────────────────────────────

def _prompt_action(state: dict) -> dict:
    """Prompt the player to choose a move or switch."""
    n_moves = len(state.get("your_moves", []))
    roster  = state["your_roster"]
    active_name = state["your_active"]["name"]

    available_switches = [
        i for i, p in enumerate(roster)
        if not p["is_fainted"] and p["name"] != active_name
    ]

    if available_switches:
        print(f"  Choose: 1–{n_moves} to use a move, or s<n> to switch (e.g. s2)")
    else:
        print(f"  Choose: 1–{n_moves} to use a move")

    while True:
        try:
            raw = input("  > ").strip().lower()
        except EOFError:
            return {"type": "move", "slot": 0}

        if raw.isdigit():
            slot = int(raw) - 1
            if 0 <= slot < n_moves:
                return {"type": "move", "slot": slot}

        elif raw.startswith("s") and raw[1:].isdigit():
            idx = int(raw[1:]) - 1
            if idx in available_switches:
                return {"type": "switch", "roster_index": idx}

        print(f"  Invalid. Enter 1–{n_moves} for a move" +
              (f", or s<n> to switch." if available_switches else "."))


def _prompt_force_switch(available: list[int], roster: list[dict]) -> dict:
    """Prompt the player to choose a replacement after a faint."""
    display = [str(i + 1) for i in available]
    print(f"  Enter roster number ({', '.join(display)}):")
    while True:
        try:
            raw = input("  > ").strip()
        except EOFError:
            return {"type": "switch", "roster_index": available[0]}

        if raw.isdigit():
            idx = int(raw) - 1
            if idx in available:
                return {"type": "switch", "roster_index": idx}

        print(f"  Invalid. Choose from: {', '.join(display)}")


# ── Main client loop ──────────────────────────────────────────────────────────

def run_client(host_ip: str, port: int = DEFAULT_PORT) -> None:
    """Connect to the battle server and play the full battle."""
    print(f"\n  Connecting to {host_ip}:{port}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host_ip, port))
    print("  Connected! Waiting for battle to start...\n")

    # Keep a reference to the last full_state so we can show roster on force-switch
    last_state: dict | None = None

    while True:
        msg = recv(sock)

        if msg["type"] == "full_state":
            last_state = msg
            _render_full_state(msg)

            if msg["awaiting"] == "action":
                action = _prompt_action(msg)
                send(sock, action)

            elif msg["awaiting"] == "none":
                # Battle is over — events already rendered
                break

        elif msg["type"] == "force_switch":
            available = msg["available"]
            roster = last_state["your_roster"] if last_state else []
            _render_force_switch(last_state or {}, available)
            action = _prompt_force_switch(available, roster)
            send(sock, action)

    sock.close()
    print("\n  Battle over. Good game!")
