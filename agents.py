# agentw.py

class AgentS:
    """
    Minimal agent template for the Tron-like game.
    Currently always returns the move "RIGHT".
    """

    ACTIONS = [
        "UP", "DOWN", "LEFT", "RIGHT",
        "UP:BOOST", "DOWN:BOOST", "LEFT:BOOST", "RIGHT:BOOST"
    ]

    def __init__(self):
        pass

    def choose_action(self, game_state) -> str:
        """
        Stage-based (early/mid/late) Flood-fill + Voronoi agent with torus topology.
        - Early: detect kamikaze, prioritize safety + higher Voronoi (vspace)
        - Mid: balance Voronoi and flood-fill
        - Late: flood-fill high priority
        Includes configurable Player 1 head-on bias and boost policy.
        """

        # ===============================
        # CONFIGURATION (tuning section)
        # ===============================
        CFG = {
            # --- Stage switching mode ---
            # "turns": use turn count thresholds
            # "spaces": use number of remaining empty cells
            "STAGE_MODE": "turns",

            # If STAGE_MODE == "turns"
            "EARLY_TURN_END": 28,   # turns 0..EARLY_TURN_END => early
            "MID_TURN_END": 120,    # turns (EARLY_TURN_END+1)..MID_TURN_END => mid, else late

            # If STAGE_MODE == "spaces"  (grid empties out)
            "EARLY_EMPTY_MIN": 220,   # >= this -> early
            "MID_EMPTY_MIN": 120,     # >= this -> mid, else late

            # --- Stage weights / penalties ---
            # Each stage can override weights; unspecified keys fall back to BASE_* defaults.
            "STAGES": {
                "early": {
                    "W_AREA": 1.6,         # flood-fill (reachable cells)
                    "W_VORONOI": 2.1,      # vspace (territory control)
                    "HEADON_PENALTY": -900 # very strong avoidance in early game
                },
                "mid": {
                    "W_AREA": 2.0,
                    "W_VORONOI": 2.0,
                    "HEADON_PENALTY": -550
                },
                "late": {
                    "W_AREA": 3.0,
                    "W_VORONOI": 0.8,
                    "HEADON_PENALTY": -450
                }
            },

            # Base (fallback) weights / constants used if a stage doesn't override them
            "BASE_W_AREA": 2.0,
            "BASE_W_VORONOI": 1.2,
            "BASE_HEADON_PENALTY": -400,
            "STRAIGHT_BONUS": 10,
            "CRASH_PENALTY": -1e9,

            # Search / estimation limits (perf vs. fidelity)
            "FLOOD_LIMIT": 320,
            "VORONOI_CAP": 240,

            # Kamikaze detection (early stage only)
            "KAMI_NEAR_DIST": 3,        # trigger if opponent within this torus-Manhattan dist
            "KAMI_MIN_LINE": 2,         # min clear straight steps they have toward us
            "KAMI_EVASION_W": 12.0,     # extra score * distance from opponent if kamikaze detected
            "KAMI_EXTRA_HEADON": -400,  # additional penalty stacked onto stage head-on

            # Player 1 slight head-on advantage (trail added first)
            "P1_HEADON_MULT": 0.82,     # multiply danger if player_number==1 ( <1 favors P1 )

            # Direction / tie-breaking
            "DIR_ORDER": ["UP", "RIGHT", "DOWN", "LEFT"],
            "AVOID_HARD_REVERSE": True,

            # Boost logic
            "BOOST_LOOKAHEAD_STEPS": 5,
            "BOOST_OPEN_DEPTH_MIN": 2,
            "BOOST_OPEN_TURN_MIN": 24,
            "BOOST_OPEN_TURN_MAX": 120,
            "BOOST_CRAMPED_SCORE": 80,

            # Boost safety around opponent
            "NO_BOOST_IF_NEAR_DIST": 2,  # if opp within this dist, avoid boosting
        }

        # ===============================
        # Helper functions
        # ===============================
        DIRS = {
            "UP":    (0, -1),
            "DOWN":  (0,  1),
            "LEFT":  (-1, 0),
            "RIGHT": (1,  0),
        }

        def dims(board):
            H = len(board)
            W = len(board[0]) if H else 0
            return W, H

        def torus(p, W, H):
            return (p[0] % W, p[1] % H)

        def neighbors(p, W, H):
            x, y = p
            for dx, dy in [(1,0),(-1,0),(0,1),(0,-1)]:
                yield torus((x+dx, y+dy), W, H)

        def is_cell_free(board, p):
            x, y = p
            return 0 <= y < len(board) and 0 <= x < len(board[0]) and board[y][x] == 0

        def simulate_step(board, pos, move_dir, W, H):
            dx, dy = DIRS[move_dir]
            nxt = torus((pos[0] + dx, pos[1] + dy), W, H)
            if board[nxt[1]][nxt[0]] != 0:
                return nxt, True
            return nxt, False

        def reverse_dir(d):
            return {"UP": "DOWN", "DOWN": "UP", "LEFT": "RIGHT", "RIGHT": "LEFT"}[d]

        def infer_current_dir(trail, W, H):
            if len(trail) < 2:
                return None
            x2, y2 = trail[-1]
            x1, y1 = trail[-2]
            dx = x2 - x1
            dy = y2 - y1
            # Normalize wrap-around
            if dx > 1: dx = -1
            if dx < -1: dx = 1
            if dy > 1: dy = -1
            if dy < -1: dy = 1
            if dx == 1 and dy == 0: return "RIGHT"
            if dx == -1 and dy == 0: return "LEFT"
            if dx == 0 and dy == 1: return "DOWN"
            if dx == 0 and dy == -1: return "UP"
            return None

        def flood_fill_count(board, start, W, H, limit=None):
            from collections import deque
            if not is_cell_free(board, start):
                return 0
            seen = {start}
            q = deque([start])
            c = 1
            while q:
                v = q.popleft()
                for n in neighbors(v, W, H):
                    if n not in seen and is_cell_free(board, n):
                        seen.add(n)
                        q.append(n)
                        c += 1
                        if limit is not None and c >= limit:
                            return c
            return c

        def tdist(a, b, W, H):
            dx = min((a[0]-b[0]) % W, (b[0]-a[0]) % W)
            dy = min((a[1]-b[1]) % H, (b[1]-a[1]) % H)
            return dx + dy

        def voronoi_score(board, my_head, opp_head, W, H, cap=200):
            my_count = 0
            counted = 0
            for y in range(H):
                for x in range(W):
                    if board[y][x] != 0:
                        continue
                    counted += 1
                    if counted > cap:
                        return my_count
                    p = (x, y)
                    if tdist(p, my_head, W, H) < tdist(p, opp_head, W, H):
                        my_count += 1
            return my_count

        def dir_towards(a, b, W, H):
            """Return a set of directions that move a closer to b on torus-Manhattan grid."""
            dirs = set()
            ax, ay = a; bx, by = b
            # X axis choice that decreases torus distance
            dx_right = (bx - ax) % W
            dx_left  = (ax - bx) % W
            if dx_right < dx_left: dirs.add("RIGHT")
            elif dx_left < dx_right: dirs.add("LEFT")
            # Y axis choice
            dy_down = (by - ay) % H
            dy_up   = (ay - by) % H
            if dy_down < dy_up: dirs.add("DOWN")
            elif dy_up < dy_down: dirs.add("UP")
            return dirs or {"UP","DOWN","LEFT","RIGHT"}  # equidistant: any

        def straight_clear_len(board, pos, move_dir, W, H, max_steps=6):
            """How many free cells ahead in a straight line (<= max_steps)."""
            steps = 0
            probe = pos
            for _ in range(max_steps):
                probe, crash = simulate_step(board, probe, move_dir, W, H)
                if crash:
                    break
                steps += 1
            return steps

        # ===============================
        # Parse game state
        # ===============================
        board = game_state.get("board")
        if board is None:
            return "RIGHT"

        W, H = dims(board)
        pnum = int(game_state.get("player_number", 1))
        a1 = game_state.get("agent1_trail", []) or []
        a2 = game_state.get("agent2_trail", []) or []
        my_trail = a1 if pnum == 1 else a2
        opp_trail = a2 if pnum == 1 else a1

        my_head = tuple(my_trail[-1]) if my_trail else (0, 0)
        opp_head = tuple(opp_trail[-1]) if opp_trail else (W - 1, H - 1)
        my_dir = infer_current_dir(my_trail, W, H) or "RIGHT"
        opp_dir = infer_current_dir(opp_trail, W, H)

        boosts = int(game_state.get("agent1_boosts" if pnum == 1 else "agent2_boosts", 0))
        turn = int(game_state.get("turn_count", 0))

        # Count empties (for STAGE_MODE == "spaces")
        empty_cells = sum(1 for y in range(H) for x in range(W) if board[y][x] == 0)

        # ===============================
        # Determine stage & stage weights
        # ===============================
        def resolve_stage():
            if CFG["STAGE_MODE"] == "turns":
                if turn <= CFG["EARLY_TURN_END"]:
                    return "early"
                elif turn <= CFG["MID_TURN_END"]:
                    return "mid"
                return "late"
            else:  # "spaces"
                if empty_cells >= CFG["EARLY_EMPTY_MIN"]:
                    return "early"
                elif empty_cells >= CFG["MID_EMPTY_MIN"]:
                    return "mid"
                return "late"

        stage = resolve_stage()
        stage_cfg = {
            "W_AREA": CFG["STAGES"].get(stage, {}).get("W_AREA", CFG["BASE_W_AREA"]),
            "W_VORONOI": CFG["STAGES"].get(stage, {}).get("W_VORONOI", CFG["BASE_W_VORONOI"]),
            "HEADON_PENALTY": CFG["STAGES"].get(stage, {}).get("HEADON_PENALTY", CFG["BASE_HEADON_PENALTY"]),
        }

        # ===============================
        # Early-stage kamikaze detection
        # ===============================
        def is_kamikaze():
            if stage != "early" or opp_dir is None:
                return False
            # Opponent near and moving in a direction that tends to reduce distance to us,
            # with a sufficiently clear straight path and (likely) incentive to collide.
            if tdist(opp_head, my_head, W, H) > CFG["KAMI_NEAR_DIST"]:
                return False
            dirs_toward_us = dir_towards(opp_head, my_head, W, H)
            if opp_dir not in dirs_toward_us:
                return False
            lane = straight_clear_len(board, opp_head, opp_dir, W, H, max_steps=6)
            return lane >= CFG["KAMI_MIN_LINE"]

        kamikaze = is_kamikaze()

        # ===============================
        # Decision making
        # ===============================
        candidates = [
            d for d in CFG["DIR_ORDER"]
            if not (CFG["AVOID_HARD_REVERSE"] and d == reverse_dir(my_dir))
        ]

        # Precompute opponent plausible next cells for head-on check
        if opp_dir:
            opp_opts = [x for x in CFG["DIR_ORDER"] if x != reverse_dir(opp_dir)]
        else:
            opp_opts = CFG["DIR_ORDER"]
        opp_future = {
            simulate_step(board, opp_head, od, W, H)[0]
            for od in opp_opts
        }

        best, best_score = None, -1e18
        for d in candidates:
            nxt, crash = simulate_step(board, my_head, d, W, H)
            if crash:
                score = CFG["CRASH_PENALTY"]
            else:
                area = flood_fill_count(board, nxt, W, H, limit=CFG["FLOOD_LIMIT"])
                vscore = voronoi_score(board, nxt, opp_head, W, H, cap=CFG["VORONOI_CAP"])

                # Head-on danger
                danger = stage_cfg["HEADON_PENALTY"] if nxt in opp_future else 0

                # Player 1 small advantage in head-on races
                if danger and pnum == 1:
                    danger = int(danger * CFG["P1_HEADON_MULT"])

                # Extra early-game safety if kamikaze suspected
                if kamikaze and nxt in opp_future:
                    danger += CFG["KAMI_EXTRA_HEADON"]

                straight_bonus = CFG["STRAIGHT_BONUS"] if d == my_dir else 0

                # Base stage scoring
                score = (
                    stage_cfg["W_AREA"] * area
                    + stage_cfg["W_VORONOI"] * vscore
                    + danger
                    + straight_bonus
                )

                # If kamikaze: prefer increasing distance from opponent (evasion)
                if kamikaze:
                    dist_after = tdist(nxt, opp_head, W, H)
                    score += CFG["KAMI_EVASION_W"] * dist_after

            if score > best_score:
                best_score, best = score, d

        chosen = best or my_dir or "RIGHT"

        # ===============================
        # Boost policy
        # ===============================
        use_boost = False
        if boosts > 0:
            depth = 0
            probe = my_head
            for _ in range(CFG["BOOST_LOOKAHEAD_STEPS"]):
                probe, crash = simulate_step(board, probe, chosen, W, H)
                if crash:
                    break
                depth += 1

            # Avoid boosting if opponent is very close (too volatile)
            near_opp = tdist(my_head, opp_head, W, H) <= CFG["NO_BOOST_IF_NEAR_DIST"]

            if (
                not near_opp and
                (
                    (depth >= CFG["BOOST_OPEN_DEPTH_MIN"]
                    and CFG["BOOST_OPEN_TURN_MIN"] <= turn <= CFG["BOOST_OPEN_TURN_MAX"])
                    or (best_score < CFG["BOOST_CRAMPED_SCORE"] and depth >= 1)
                )
            ):
                # If kamikaze detected, only boost if it clearly increases distance
                if not kamikaze or tdist(probe, opp_head, W, H) > tdist(my_head, opp_head, W, H):
                    use_boost = True

        return f"{chosen}:BOOST" if use_boost else chosen
