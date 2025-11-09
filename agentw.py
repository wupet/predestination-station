# agentw.py
# AgentW using (x,y) coordinate convention where x is horizontal (columns), y is vertical (rows).
# Outputs moves as "UP"/"DOWN"/"LEFT"/"RIGHT" or "DIR:BOOST" (all caps).
# Minimal: choose_action + supporting helpers.

import collections
import random

ROWS = 18  # number of rows (y)
COLS = 20  # number of columns (x)

# Directions are (dx, dy) because positions are (x, y)
DIRS = {
    "UP": (0, -1),
    "DOWN": (0, 1),
    "LEFT": (-1, 0),
    "RIGHT": (1, 0),
}
DIR_NAMES = list(DIRS.keys())
OPPOSITE = {"UP": "DOWN", "DOWN": "UP", "LEFT": "RIGHT", "RIGHT": "LEFT"}


class AgentW:
    def __init__(self, rng_seed=None):
        if rng_seed is not None:
            random.seed(rng_seed)

    # --- coordinate helpers (positions are (x, y)) ---
    @staticmethod
    def wrap(x, y):
        return (x % COLS, y % ROWS)

    @staticmethod
    def pos_to_tuple(p):
        return (int(p[0]), int(p[1]))

    @staticmethod
    def simulate_step(pos, direction, steps=1):
        dx, dy = DIRS[direction]
        x, y = pos
        return AgentW.wrap(x + dx * steps, y + dy * steps)

    # --- board / occupied helpers ---
    @staticmethod
    def _safe_get_board(state):
        board = state.get("board")
        if board is None:
            return [[0 for _ in range(COLS)] for _ in range(ROWS)]
        return board

    @staticmethod
    def build_occupied_set(state):
        """
        Board is a matrix indexed [row][col] but positions are (x,y) = (col,row).
        Add board cells with 1 plus both trails.
        """
        occ = set()
        board = AgentW._safe_get_board(state)
        try:
            for y in range(min(ROWS, len(board))):
                row = board[y] or []
                for x in range(min(COLS, len(row))):
                    try:
                        if row[x] == 1:
                            occ.add((x, y))
                    except Exception:
                        continue
        except Exception:
            pass

        for key in ("agent1_trail", "agent2_trail"):
            trail = state.get(key, []) or []
            for p in trail:
                try:
                    occ.add(AgentW.pos_to_tuple(p))
                except Exception:
                    continue
        return occ

    @staticmethod
    def head_positions(state):
        def head_from_trail(trail):
            if not trail:
                return None
            try:
                return AgentW.pos_to_tuple(trail[-1])
            except Exception:
                return None
        return head_from_trail(state.get("agent1_trail", []) or []), head_from_trail(state.get("agent2_trail", []) or [])

    @staticmethod
    def neighbors(pos):
        x, y = pos
        for dx, dy in DIRS.values():
            yield AgentW.wrap(x + dx, y + dy)

    @staticmethod
    def flood_fill_area(start, occ, max_nodes=ROWS * COLS):
        if start is None or start in occ:
            return 0
        q = collections.deque([start])
        seen = {start}
        while q and len(seen) < max_nodes:
            cur = q.popleft()
            for n in AgentW.neighbors(cur):
                if n in seen or n in occ:
                    continue
                seen.add(n)
                q.append(n)
        return len(seen)

    # --- trail helpers to prevent reversing into the most recent previous cell ---
    @staticmethod
    def last_positions(state):
        """
        Return (last_pos, prev_pos) in (x,y) form.
        last_pos = trail[-1], prev_pos = trail[-2] if available.
        """
        me = int(state.get("player_number", 1))
        trail = state.get("agent1_trail", []) if me == 1 else state.get("agent2_trail", [])
        if not trail:
            return None, None
        try:
            last = AgentW.pos_to_tuple(trail[-1])
        except Exception:
            last = None
        prev = None
        if len(trail) >= 2:
            try:
                prev = AgentW.pos_to_tuple(trail[-2])
            except Exception:
                prev = None
        return last, prev

    # --- propose candidate moves (exclude moves that step into prev_pos) ---
    @staticmethod
    def propose_moves(state):
        me_num = int(state.get("player_number", 1))
        a1_head, a2_head = AgentW.head_positions(state)
        my_head = a1_head if me_num == 1 else a2_head
        opp_head = a2_head if me_num == 1 else a1_head
        occ = AgentW.build_occupied_set(state)
        boosts_left = int(state.get("agent1_boosts", 0) if me_num == 1 else state.get("agent2_boosts", 0))

        last_pos, prev_pos = AgentW.last_positions(state)

        candidates = []
        if my_head is None:
            for d in DIR_NAMES:
                candidates.append((d, None, False, False))
            return candidates, my_head, opp_head, occ, boosts_left

        for d in DIR_NAMES:
            nxt = AgentW.simulate_step(my_head, d, steps=1)
            dead_single = (nxt in occ) or (prev_pos is not None and nxt == prev_pos)
            candidates.append((d, nxt, False, dead_single))

            if boosts_left > 0:
                mid = AgentW.simulate_step(my_head, d, steps=1)
                final = AgentW.simulate_step(my_head, d, steps=2)
                dead_boost = (mid in occ) or (final in occ) or (prev_pos is not None and (mid == prev_pos or final == prev_pos))
                candidates.append((d + ":BOOST", final, True, dead_boost))

        return candidates, my_head, opp_head, occ, boosts_left

    @staticmethod
    def head_on_survivor(my_len, opp_len):
        if my_len > opp_len:
            return "ME"
        if opp_len > my_len:
            return "OPP"
        return "BOTH"

    # --- top-level chooser ---
    def choose_action(self, game_state, boost_threshold=1.30):
        candidates, my_head, opp_head, occ, boosts_left = AgentW.propose_moves(game_state)

        if my_head is None:
            return random.choice(DIR_NAMES)

        opp_one_step = set()
        if opp_head is not None:
            for d in DIR_NAMES:
                opp_one_step.add(AgentW.simulate_step(opp_head, d, steps=1))

        safe = []
        for move_str, result_cell, used_boost, dead in candidates:
            if dead:
                continue
            headon_risk = False
            if result_cell in opp_one_step:
                my_len = int(game_state.get("agent1_length", 0) if game_state.get("player_number", 1) == 1 else game_state.get("agent2_length", 0))
                opp_len = int(game_state.get("agent2_length", 0) if game_state.get("player_number", 1) == 1 else game_state.get("agent1_length", 0))
                survivor = AgentW.head_on_survivor(my_len, opp_len)
                if survivor == "OPP" or survivor == "BOTH":
                    headon_risk = True
            safe.append((move_str, result_cell, used_boost, headon_risk))

        if not safe:
            non_dead = [c for c in candidates if not c[3]]
            if non_dead:
                sel = non_dead[0][0].upper()
                if sel.endswith(":BOOST"):
                    dir_part = sel.split(":")[0]
                    sel = f"{dir_part}:BOOST"
                return sel
            return random.choice(DIR_NAMES)

        scored = []
        for move_str, result_cell, used_boost, headon_risk in safe:
            occ2 = set(occ)
            if result_cell is not None:
                occ2.add(result_cell)
            if used_boost:
                base_dir = move_str.split(":")[0]
                mid = AgentW.simulate_step(my_head, base_dir, steps=1)
                occ2.add(mid)
            start_for_area = result_cell if result_cell is not None else my_head
            area = AgentW.flood_fill_area(start_for_area, occ2)
            scored.append((area, headon_risk, used_boost, move_str))

        scored.sort(key=lambda x: (x[0], -int(x[2])), reverse=True)

        best_non_boost = next((s for s in scored if not s[2]), None)
        best_boost = next((s for s in scored if s[2]), None)

        chosen = None
        if best_non_boost and best_boost:
            nb_area = best_non_boost[0]
            b_area = best_boost[0]
            if (b_area >= nb_area * boost_threshold) or (best_non_boost[1] and not best_boost[1]):
                chosen = best_boost[3]
            else:
                chosen = best_non_boost[3]
        else:
            for area, headon_risk, used_boost, move_str in scored:
                if not headon_risk:
                    chosen = move_str
                    break
            if chosen is None:
                chosen = scored[0][3]

        chosen = chosen.upper()
        if chosen.endswith(":BOOST"):
            dir_part = chosen.split(":")[0]
            chosen = f"{dir_part}:BOOST"
        return chosen