"""
Multiplayer Pokemon battle over TCP sockets.

Host a battle:
    python -m pykemon host [port]

Join a battle:
    python -m pykemon join <host_ip> [port]

Protocol summary (newline-delimited JSON over TCP):
    choose_pokemon  → server → client   (roster list)
    pick            → client → server   (chosen index)
    battle_start    → server → client   (pokemon data)
    your_turn       → server → client   (HP snapshot, triggers move prompt)
    move            → client → server   (chosen move index)
    turn_result     → server → client   (event lines, updated HP)
    game_over       → server → client   (win / lose / draw)
"""

import json
import socket
import threading

from .battle import (
    BattlePokemon,
    Move,
    format_events,
    get_pokemon_list,
    load_pokemon,
    resolve_turn,
)

DEFAULT_PORT = 5555


# ── Buffered connection ───────────────────────────────────────────────────────

class _Conn:
    """Wraps a TCP socket with a persistent buffer for newline-delimited JSON."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._buf = b""

    def send(self, data: dict) -> None:
        self._sock.sendall((json.dumps(data) + "\n").encode())

    def recv(self) -> dict:
        while b"\n" not in self._buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("Remote end disconnected.")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return json.loads(line)

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


# ── Display helpers ───────────────────────────────────────────────────────────

def _show_roster(roster: list) -> None:
    print("\n  Available Pokemon:")
    print("  " + "─" * 42)
    for i, (_, name, t1, t2) in enumerate(roster):
        types = f"{t1}/{t2}" if t2 else t1
        print(f"  {i + 1:2}. {name:<16} [{types}]")
    print("  " + "─" * 42)


def _prompt_int(prompt: str, lo: int, hi: int) -> int:
    while True:
        try:
            val = int(input(prompt))
            if lo <= val <= hi:
                return val
        except (ValueError, EOFError):
            pass
        print(f"  Enter a number from {lo} to {hi}.")


def _show_turn_header(turn: int) -> None:
    print(f"\n{'─' * 44}")
    print(f"  Turn {turn}")
    print(f"{'─' * 44}")


def _enemy_bar(hp: int, max_hp: int, width: int = 20) -> str:
    ratio = max(0.0, hp / max_hp) if max_hp else 0.0
    filled = round(ratio * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {hp}/{max_hp}"


def _show_field(
    your_poke: BattlePokemon,
    enemy_name: str,
    enemy_hp: int,
    enemy_max_hp: int,
) -> None:
    print(f"  Opp  {enemy_name:<16} {_enemy_bar(enemy_hp, enemy_max_hp)}")
    print(f"  You  {your_poke.name:<16} {your_poke.hp_bar()}")


def _show_moves(poke: BattlePokemon) -> None:
    print("  Moves:")
    for i, m in enumerate(poke.moves):
        print(
            f"    {i + 1}. {m.name:<24} [{m.type:>10}]"
            f"  Pwr: {m.power:>3}   Acc: {m.accuracy}%"
        )


# ── Pokemon serialization ─────────────────────────────────────────────────────

def _poke_to_dict(p: BattlePokemon) -> dict:
    return {
        "pokemon_id":    p.pokemon_id,
        "name":          p.name,
        "primary_type":  p.primary_type,
        "secondary_type": p.secondary_type,
        "max_hp":        p.max_hp,
        "current_hp":    p.current_hp,
        "attack":        p.attack,
        "defense":       p.defense,
        "sp_atk":        p.sp_atk,
        "sp_def":        p.sp_def,
        "speed":         p.speed,
        "moves": [
            {
                "move_id":  m.move_id,
                "name":     m.name,
                "type":     m.type,
                "category": m.category,
                "power":    m.power,
                "accuracy": m.accuracy,
            }
            for m in p.moves
        ],
    }


def _dict_to_poke(d: dict) -> BattlePokemon:
    moves = [Move(**m) for m in d["moves"]]
    return BattlePokemon(
        pokemon_id=d["pokemon_id"],
        name=d["name"],
        primary_type=d["primary_type"],
        secondary_type=d["secondary_type"],
        max_hp=d["max_hp"],
        current_hp=d["current_hp"],
        attack=d["attack"],
        defense=d["defense"],
        sp_atk=d["sp_atk"],
        sp_def=d["sp_def"],
        speed=d["speed"],
        moves=moves,
    )


# ── Host (server) ─────────────────────────────────────────────────────────────

def run_host(port: int = DEFAULT_PORT) -> None:
    """Start a battle server and wait for one opponent to connect."""
    roster = get_pokemon_list()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("", port))
    srv.listen(1)

    print(f"\n  Hosting on port {port} — share your IP address with your opponent.")
    print("  Waiting for opponent to connect...\n")

    raw_sock, addr = srv.accept()
    srv.close()
    conn = _Conn(raw_sock)
    print(f"  Opponent connected from {addr[0]}!\n")

    # ── Pokemon selection ──────────────────────────────────────────────────────
    conn.send({"action": "choose_pokemon", "roster": [list(r) for r in roster]})

    _show_roster(roster)
    host_idx = _prompt_int("  Pick your Pokemon (number): ", 1, len(roster)) - 1

    opp_msg = conn.recv()
    opp_idx = opp_msg["index"]

    host_poke = load_pokemon(roster[host_idx][0])
    opp_poke  = load_pokemon(roster[opp_idx][0])

    print(f"\n  You chose:      {host_poke.name}")
    print(f"  Opponent chose: {opp_poke.name}\n")

    conn.send({
        "action":       "battle_start",
        "your_pokemon": _poke_to_dict(opp_poke),
        "enemy_name":   host_poke.name,
        "enemy_max_hp": host_poke.max_hp,
    })

    # ── Battle loop ────────────────────────────────────────────────────────────
    for turn in range(1, 9999):
        _show_turn_header(turn)
        _show_field(host_poke, opp_poke.name, opp_poke.current_hp, opp_poke.max_hp)
        _show_moves(host_poke)

        conn.send({
            "action":    "your_turn",
            "turn":      turn,
            "your_hp":   opp_poke.current_hp,
            "enemy_hp":  host_poke.current_hp,
            "enemy_max_hp": host_poke.max_hp,
        })

        # Collect moves from both players simultaneously
        opp_move_holder = [0]
        opp_ready = threading.Event()

        def _recv_opp_move():
            try:
                msg = conn.recv()
                opp_move_holder[0] = msg["index"]
            except Exception:
                pass
            opp_ready.set()

        t = threading.Thread(target=_recv_opp_move, daemon=True)
        t.start()

        host_move_idx = (
            _prompt_int(f"  Your move (1-{len(host_poke.moves)}): ", 1, len(host_poke.moves)) - 1
        )
        opp_ready.wait()
        opp_move_idx = opp_move_holder[0]

        host_move = host_poke.moves[host_move_idx]
        opp_move  = opp_poke.moves[opp_move_idx]

        events = resolve_turn(host_poke, host_move, opp_poke, opp_move)

        print()
        for line in format_events(events, "host"):
            print(f"  {line}")

        conn.send({
            "action":    "turn_result",
            "events":    format_events(events, "opp"),
            "your_hp":   opp_poke.current_hp,
            "enemy_hp":  host_poke.current_hp,
        })

        # Game over check
        if host_poke.is_fainted or opp_poke.is_fainted:
            if host_poke.is_fainted and opp_poke.is_fainted:
                print("\n  It's a draw!")
                conn.send({"action": "game_over", "result": "draw"})
            elif host_poke.is_fainted:
                print(f"\n  {host_poke.name} fainted — you lose!")
                conn.send({"action": "game_over", "result": "win"})
            else:
                print(f"\n  {opp_poke.name} fainted — you win!")
                conn.send({"action": "game_over", "result": "lose"})
            break

    conn.close()
    print("\n  Battle over. Good game!")


# ── Client (guest) ────────────────────────────────────────────────────────────

def run_client(host_ip: str, port: int = DEFAULT_PORT) -> None:
    """Connect to a host and start a battle."""
    print(f"\n  Connecting to {host_ip}:{port}...")
    raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw_sock.connect((host_ip, port))
    conn = _Conn(raw_sock)
    print("  Connected!\n")

    # ── Pokemon selection ──────────────────────────────────────────────────────
    msg = conn.recv()  # choose_pokemon
    roster = [tuple(r) for r in msg["roster"]]

    _show_roster(roster)
    idx = _prompt_int("  Pick your Pokemon (number): ", 1, len(roster)) - 1
    conn.send({"index": idx})

    # ── Battle start ───────────────────────────────────────────────────────────
    msg = conn.recv()  # battle_start
    my_poke      = _dict_to_poke(msg["your_pokemon"])
    enemy_name   = msg["enemy_name"]
    enemy_max_hp = msg["enemy_max_hp"]
    enemy_hp     = enemy_max_hp

    print(f"\n  You chose:      {my_poke.name}")
    print(f"  Opponent chose: {enemy_name}\n")

    # ── Battle loop ────────────────────────────────────────────────────────────
    while True:
        msg = conn.recv()

        if msg["action"] == "your_turn":
            my_poke.current_hp = msg["your_hp"]
            enemy_hp = msg["enemy_hp"]

            _show_turn_header(msg["turn"])
            _show_field(my_poke, enemy_name, enemy_hp, enemy_max_hp)
            _show_moves(my_poke)

            move_idx = (
                _prompt_int(f"  Your move (1-{len(my_poke.moves)}): ", 1, len(my_poke.moves)) - 1
            )
            conn.send({"index": move_idx})

        elif msg["action"] == "turn_result":
            my_poke.current_hp = msg["your_hp"]
            enemy_hp = msg["enemy_hp"]
            print()
            for line in msg["events"]:
                print(f"  {line}")

        elif msg["action"] == "game_over":
            result = msg["result"]
            if result == "win":
                print("\n  You win! Great battle!")
            elif result == "lose":
                print("\n  You lose! Better luck next time.")
            else:
                print("\n  It's a draw!")
            break

    conn.close()
    print("\n  Battle over. Good game!")
