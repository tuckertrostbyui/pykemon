"""
Battle server.

Listens on TCP, accepts exactly 2 clients, runs the full 6v6 battle loop,
and sends FULL_STATE messages each turn. Clients send ACTION messages back.
"""

from __future__ import annotations

import random
import socket
import threading

from .damage import accuracy_check, damage_calc
from .default_teams import load_default_teams
from .models import Field, MoveSlot, Pokemon, Trainer
from .protocol import recv, send

DEFAULT_PORT = 5555


# ── Serialization helpers ─────────────────────────────────────────────────────

def _pokemon_to_dict(p: Pokemon) -> dict:
    return {
        "name":           p.name,
        "primary_type":   p.primary_type,
        "secondary_type": p.secondary_type,
        "current_hp":     p.current_hp,
        "max_hp":         p.max_hp,
        "is_fainted":     p.is_fainted,
        "level":          p.level,
        "nature":         p.nature,
        "status":         None,
    }


def _roster_entry(p: Pokemon) -> dict:
    return {
        "name":       p.name,
        "current_hp": p.current_hp,
        "max_hp":     p.max_hp,
        "is_fainted": p.is_fainted,
    }


def _moveslot_to_dict(slot_index: int, ms: MoveSlot) -> dict:
    return {
        "slot":       slot_index,
        "move_name":  ms.move.move_name,
        "type":       ms.move.type,
        "category":   ms.move.category,
        "power":      ms.move.power,
        "accuracy":   ms.move.accuracy,
        "current_pp": ms.current_pp,
        "max_pp":     ms.move.pp,
    }


# ── Battle server ─────────────────────────────────────────────────────────────

class BattleServer:
    def __init__(self, port: int = DEFAULT_PORT) -> None:
        self.port = port

        self.trainer1: Trainer | None = None
        self.trainer2: Trainer | None = None
        self.field: Field | None = None

        # PP state persists through switch-outs; keyed by team_pokemon_id
        self.move_slots: dict[int, list[MoveSlot]] = {}

        self.turn: int = 0
        self.is_over: bool = False
        self.winner: Trainer | None = None
        self.events: list[str] = []

        self.sock1: socket.socket | None = None
        self.sock2: socket.socket | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        self._accept_connections()
        self._init_battle()
        self._battle_loop()

    def _accept_connections(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("", self.port))
        srv.listen(2)
        print(f"\n  Battle server listening on port {self.port}.")
        print("  Waiting for 2 players to connect...\n")
        self.sock1, addr1 = srv.accept()
        print(f"  Player 1 connected: {addr1[0]}")
        self.sock2, addr2 = srv.accept()
        print(f"  Player 2 connected: {addr2[0]}")
        srv.close()
        print("  Both players connected. Starting battle!\n")

    def _init_battle(self) -> None:
        print("  Loading battle data...")
        t1, t2, poke_moves = load_default_teams()
        self.trainer1 = t1
        self.trainer2 = t2

        # Initialize persistent MoveSlot state for all 12 Pokemon
        for tid, moves in poke_moves.items():
            self.move_slots[tid] = [MoveSlot(move=m, current_pp=m.pp) for m in moves]

        self.field = Field(
            active_t1=t1.roster[0],
            active_t2=t2.roster[0],
            moves_t1=self.move_slots[t1.roster[0].team_pokemon_id],
            moves_t2=self.move_slots[t2.roster[0].team_pokemon_id],
        )
        print(f"  {t1.name}'s team: {', '.join(p.name for p in t1.roster)}")
        print(f"  {t2.name}'s team: {', '.join(p.name for p in t2.roster)}\n")

    def _battle_loop(self) -> None:
        self.events = []
        self._broadcast_full_state(awaiting="action")

        while not self.is_over:
            action1, action2 = self._collect_actions()
            self.turn += 1
            self.events = [f"Turn {self.turn} begins."]
            self._resolve_turn(action1, action2)
            if not self.is_over:
                self._broadcast_full_state(awaiting="action")

        # Final broadcast after battle ends
        self._broadcast_full_state(awaiting="none")
        print(f"\n  Battle over! Winner: {self.winner.name if self.winner else 'draw'}")
        self.sock1.close()
        self.sock2.close()

    # ── Action collection ─────────────────────────────────────────────────────

    def _collect_actions(self) -> tuple[dict, dict]:
        """Block until both clients send an action; collect concurrently."""
        holder: list[dict] = [{}, {}]
        events = [threading.Event(), threading.Event()]

        def _recv_action(idx: int, sock: socket.socket) -> None:
            try:
                holder[idx] = recv(sock)
            except Exception:
                holder[idx] = {"type": "move", "slot": 0}
            events[idx].set()

        threading.Thread(target=_recv_action, args=(0, self.sock1), daemon=True).start()
        threading.Thread(target=_recv_action, args=(1, self.sock2), daemon=True).start()
        events[0].wait()
        events[1].wait()
        return holder[0], holder[1]

    # ── Turn resolution ───────────────────────────────────────────────────────

    def _resolve_turn(self, action1: dict, action2: dict) -> None:
        f = self.field

        # Resolve switches first
        if action1["type"] == "switch":
            self._do_switch(self.trainer1, action1["roster_index"], side=1)
        if action2["type"] == "switch":
            self._do_switch(self.trainer2, action2["roster_index"], side=2)

        # Both switched — nothing more to do this turn
        if action1["type"] == "switch" and action2["type"] == "switch":
            return

        # Determine attack order
        pairs = [
            (self.trainer1, action1, 1),
            (self.trainer2, action2, 2),
        ]
        if f.active_t1.speed > f.active_t2.speed:
            ordered = pairs
        elif f.active_t2.speed > f.active_t1.speed:
            ordered = [pairs[1], pairs[0]]
        else:
            random.shuffle(pairs)
            ordered = pairs

        for trainer, action, side in ordered:
            # Re-check after each attack — a faint may have been handled mid-turn
            if self.is_over:
                break
            if f.active_t1.is_fainted or f.active_t2.is_fainted:
                break
            if action["type"] == "move":
                self._do_attack(trainer, action["slot"], side)

    def _do_attack(self, trainer: Trainer, slot: int, side: int) -> None:
        f = self.field
        if side == 1:
            attacker = f.active_t1
            defender = f.active_t2
            slots    = f.moves_t1
            def_trainer = self.trainer2
            def_side = 2
        else:
            attacker = f.active_t2
            defender = f.active_t1
            slots    = f.moves_t2
            def_trainer = self.trainer1
            def_side = 1

        # Clamp slot to available moves
        slot = max(0, min(slot, len(slots) - 1))
        ms = slots[slot]
        move = ms.move

        # Decrement PP (minimum 0)
        ms.current_pp = max(0, ms.current_pp - 1)

        # Announce move
        if move.category == "Status":
            self.events.append(f"{trainer.name}'s {attacker.name} used {move.move_name}!")
            return  # Status moves have no mechanical effect in v1

        pwr_str = f"{move.power} power" if move.power else "??"
        acc_str = f"{move.accuracy} acc" if move.accuracy else "---"
        self.events.append(
            f"{trainer.name}'s {attacker.name} used {move.move_name}!"
            f" ({pwr_str} | {move.type} | {move.category} | {acc_str})"
        )

        # Accuracy check
        if not accuracy_check(move):
            self.events.append(f"{trainer.name}'s {attacker.name}'s {move.move_name} missed!")
            return

        # Damage calculation
        damage, dmg_events = damage_calc(attacker, move, defender)
        self.events.extend(dmg_events)

        if damage == 0:
            return  # immune — event already appended by damage_calc

        # Apply damage
        defender.current_hp = max(0, defender.current_hp - damage)
        self.events.append(f"{defender.name} took {damage} damage.")

        if defender.current_hp <= 0:
            defender.current_hp = 0
            defender.is_fainted = True
            self.events.append(f"{defender.name} fainted!")
            self._handle_faint(def_trainer, def_side)

    def _do_switch(self, trainer: Trainer, roster_index: int, side: int) -> None:
        roster_index = max(0, min(roster_index, len(trainer.roster) - 1))
        new_pokemon = trainer.roster[roster_index]

        if side == 1:
            old_name = self.field.active_t1.name
            self.field.active_t1 = new_pokemon
            self.field.moves_t1 = self.move_slots[new_pokemon.team_pokemon_id]
        else:
            old_name = self.field.active_t2.name
            self.field.active_t2 = new_pokemon
            self.field.moves_t2 = self.move_slots[new_pokemon.team_pokemon_id]

        self.events.append(
            f"{trainer.name} withdrew {old_name}. Go, {new_pokemon.name}!"
        )

    def _handle_faint(self, trainer: Trainer, side: int) -> None:
        available = [i for i, p in enumerate(trainer.roster) if not p.is_fainted]

        if not available:
            other = self.trainer2 if side == 1 else self.trainer1
            self.winner = other
            self.is_over = True
            self.events.append(
                f"{trainer.name} has no Pokémon left. {other.name} wins!"
            )
            return

        # Send force-switch directly to the affected client
        target_sock = self.sock1 if side == 1 else self.sock2
        send(target_sock, {
            "type":      "force_switch",
            "reason":    "fainted",
            "available": available,
        })

        try:
            switch_action = recv(target_sock)
        except Exception:
            switch_action = {"type": "switch", "roster_index": available[0]}

        self._do_switch(trainer, switch_action["roster_index"], side)

    # ── FULL_STATE broadcast ──────────────────────────────────────────────────

    def _build_full_state(self, perspective: int, awaiting: str) -> dict:
        if perspective == 1:
            you, opp     = self.trainer1, self.trainer2
            your_active  = self.field.active_t1
            opp_active   = self.field.active_t2
            your_moves   = self.field.moves_t1
        else:
            you, opp     = self.trainer2, self.trainer1
            your_active  = self.field.active_t2
            opp_active   = self.field.active_t1
            your_moves   = self.field.moves_t2

        return {
            "type":              "full_state",
            "turn":              self.turn,
            "your_trainer":      you.name,
            "opponent_trainer":  opp.name,
            "your_active":       _pokemon_to_dict(your_active),
            "opponent_active":   _pokemon_to_dict(opp_active),
            "your_moves":        [_moveslot_to_dict(i, ms) for i, ms in enumerate(your_moves)],
            "your_roster":       [_roster_entry(p) for p in you.roster],
            "events":            list(self.events),
            "awaiting":          awaiting,
        }

    def _broadcast_full_state(self, awaiting: str) -> None:
        send(self.sock1, self._build_full_state(perspective=1, awaiting=awaiting))
        send(self.sock2, self._build_full_state(perspective=2, awaiting=awaiting))


# ── Entry point ───────────────────────────────────────────────────────────────

def run_host(port: int = DEFAULT_PORT) -> None:
    """Start the battle server and run a full battle."""
    BattleServer(port).run()
