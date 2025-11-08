
import os
from flask import Flask, request, jsonify
from threading import Lock
from collections import deque

from case_closed_game import Game, Direction

# Flask API server setup
app = Flask(__name__)

GLOBAL_GAME = Game()
LAST_POSTED_STATE = {}

game_lock = Lock()

PARTICIPANT = os.getenv("PARTICIPANT", "TAMU-Datathon")
AGENT_NAME = os.getenv("AGENT_NAME", "FloodVoronoiV1")


@app.route("/", methods=["GET"])
def info():
    """Basic health/info endpoint used by the judge to check connectivity.

    Returns participant and agent_name (so Judge.check_latency can create Agent objects).
    """
    return jsonify({"participant": PARTICIPANT, "agent_name": AGENT_NAME}), 200


def _update_local_game_from_post(data: dict):
    """Update the local GLOBAL_GAME using the JSON posted by the judge.

    The judge posts a dictionary with keys matching the Judge.send_state payload
    (board, agent1_trail, agent2_trail, agent1_length, agent2_length, agent1_alive,
    agent2_alive, agent1_boosts, agent2_boosts, turn_count).
    """
    with game_lock:
        LAST_POSTED_STATE.clear()
        LAST_POSTED_STATE.update(data)

        # Lightweight mirror (best-effort) to keep helpers available if needed
        try:
            if "board" in data:
                GLOBAL_GAME.board.grid = data["board"]
            if "agent1_trail" in data:
                GLOBAL_GAME.agent1.trail = deque(tuple(p) for p in data["agent1_trail"])
            if "agent2_trail" in data:
                GLOBAL_GAME.agent2.trail = deque(tuple(p) for p in data["agent2_trail"])
            if "agent1_length" in data:
                GLOBAL_GAME.agent1.length = int(data["agent1_length"])
            if "agent2_length" in data:
                GLOBAL_GAME.agent2.length = int(data["agent2_length"])
            if "agent1_alive" in data:
                GLOBAL_GAME.agent1.alive = bool(data["agent1_alive"])
            if "agent2_alive" in data:
                GLOBAL_GAME.agent2.alive = bool(data["agent2_alive"])
            if "agent1_boosts" in data:
                GLOBAL_GAME.agent1.boosts_remaining = int(data["agent1_boosts"])
            if "agent2_boosts" in data:
                GLOBAL_GAME.agent2.boosts_remaining = int(data["agent2_boosts"])
            if "turn_count" in data:
                GLOBAL_GAME.turns = int(data["turn_count"])
        except Exception:
            pass


@app.route("/send-state", methods=["POST"])
def receive_state():
    """Judge calls this to push the current game state to the agent server.

    The agent should update its local representation and return 200.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "no json body"}), 400
    _update_local_game_from_post(data)
    return jsonify({"status": "state received"}), 200


# -------------- Helper logic (stateless w.r.t. Flask thread) -----------------

DIRS = {
    "UP": Direction.UP.value,
    "DOWN": Direction.DOWN.value,
    "LEFT": Direction.LEFT.value,
    "RIGHT": Direction.RIGHT.value,
}
DIR_ORDER = ["UP", "RIGHT", "DOWN", "LEFT"]  # used for tie-breakers

def _torus(p, W, H):
    return (p[0] % W, p[1] % H)

def _neighbors(p, W, H):
    x, y = p
    for dx, dy in [(1,0),(-1,0),(0,1),(0,-1)]:
        yield _torus((x+dx, y+dy), W, H)

def _reverse_dir(d):
    rev = {"UP":"DOWN", "DOWN":"UP", "LEFT":"RIGHT", "RIGHT":"LEFT"}
    return rev.get(d)

def _infer_current_dir(trail, W, H):
    if len(trail) < 2:
        return None
    (x2,y2) = trail[-1]
    (x1,y1) = trail[-2]
    dx = (x2 - x1)
    dy = (y2 - y1)
    # normalize wrap-around to {-1,0,1}
    if dx > 1: dx = -1
    if dx < -1: dx = 1
    if dy > 1: dy = -1
    if dy < -1: dy = 1
    if dx == 1 and dy == 0: return "RIGHT"
    if dx == -1 and dy == 0: return "LEFT"
    if dx == 0 and dy == 1: return "DOWN"
    if dx == 0 and dy == -1: return "UP"
    return None

def _is_cell_free(board, p):
    x, y = p
    return 0 <= y < len(board) and 0 <= x < len(board[0]) and board[y][x] == 0

def _simulate_step(board, pos, move_dir, W, H):
    dx, dy = DIRS[move_dir]
    nxt = _torus((pos[0]+dx, pos[1]+dy), W, H)
    # collision if board already occupied
    if board[nxt[1]][nxt[0]] != 0:
        return nxt, True  # pos, crashed
    return nxt, False

def _flood_fill_count(board, start, W, H, limit=None):
    """Count reachable empty cells using BFS from start (including start if empty)."""
    from collections import deque as dq
    if not _is_cell_free(board, start):
        return 0
    seen = {start}
    q = dq([start])
    c = 1
    while q:
        v = q.popleft()
        for n in _neighbors(v, W, H):
            if n not in seen and _is_cell_free(board, n):
                seen.add(n); q.append(n); c += 1
                if limit is not None and c >= limit:
                    return c
    return c

def _voronoi_score(board, my_head, opp_head, W, H, cap=200):
    """Count cells closer to me than opponent (Manhattan on torus)."""
    # Precompute all empty cells until cap to bound runtime
    my_count = 0
    Hh = len(board); Ww = len(board[0])
    def torus_dist(a, b):
        dx = min((a[0]-b[0])%Ww, (b[0]-a[0])%Ww)
        dy = min((a[1]-b[1])%Hh, (b[1]-a[1])%Hh)
        return dx + dy
    counted = 0
    for y in range(Hh):
        for x in range(Ww):
            if board[y][x] != 0: 
                continue
            counted += 1
            if counted > cap:
                break
            p = (x,y)
            d_my = torus_dist(p, my_head)
            d_opp = torus_dist(p, opp_head)
            if d_my < d_opp:
                my_count += 1
        if counted > cap:
            break
    return my_count

def _choose_move(state, player_number):
    board = state.get("board")
    if not board:
        return "RIGHT"
    H = len(board)
    W = len(board[0]) if H>0 else 0

    # Trails and heads
    a1 = state.get("agent1_trail", [])
    a2 = state.get("agent2_trail", [])
    my_trail = a1 if player_number == 1 else a2
    opp_trail = a2 if player_number == 1 else a1
    my_head = tuple(my_trail[-1]) if my_trail else (0,0)
    opp_head = tuple(opp_trail[-1]) if opp_trail else (W-1,H-1)

    my_dir = _infer_current_dir(my_trail, W, H) or "RIGHT"
    opp_dir = _infer_current_dir(opp_trail, W, H) or None

    boosts = state.get("agent1_boosts" if player_number==1 else "agent2_boosts", 0)
    turn = state.get("turn_count", 0)

    # Candidate dirs: avoid reversing
    candidates = [d for d in DIR_ORDER if d != _reverse_dir(my_dir)]

    # Score each move
    best = None
    best_score = -1e9
    for d in candidates:
        # Step once (no boost for safety evaluation)
        nxt, crash = _simulate_step(board, my_head, d, W, H)
        if crash:
            score = -1e6  # impossible move
        else:
            # Create a cheap copy board mark next cell as occupied (simulate our trail growth)
            # We don't simulate opponent fully; we add a soft penalty if we step adjacent to opp head.
            # This keeps runtime tiny.
            b2 = board  # we will not deep-copy the whole board; instead, adjust scoring heuristically
            # Local safety via flood-fill radius-limited
            area = _flood_fill_count(b2, nxt, W, H, limit=300)
            # Voronoi-ish territory advantage
            vscore = _voronoi_score(b2, nxt, opp_head, W, H, cap=200)
            # Proximity penalty: don't walk into cells directly adjacent to opponent head (possible head-on)
            danger = 0
            if opp_dir is not None:
                # Opp likely options: keep going or turn left/right (not reverse)
                opp_opts = [x for x in DIR_ORDER if x != _reverse_dir(opp_dir)]
            else:
                opp_opts = DIR_ORDER
            opp_future = set()
            for od in opp_opts:
                o_nxt, _ = _simulate_step(board, opp_head, od, W, H)
                opp_future.add(o_nxt)
            if nxt in opp_future:
                danger -= 400  # avoid likely head-on / immediate clash

            # Straight preference and gentle turn penalty
            straight_bonus = 10 if d == my_dir else 0

            # Compose score
            score = 2.0*area + 1.2*vscore + danger + straight_bonus

        if score > best_score:
            best_score = score
            best = d

    chosen = best or my_dir or "RIGHT"

    # Boost policy (conservative):
    # - Use boost when corridor ahead is long and safe, or when boxed (few spaces) to dash to open area.
    use_boost = False
    if boosts > 0:
        # Compute forward safety depth by simulating K steps until hit
        depth = 0
        probe = my_head
        for _ in range(5):
            probe, crash = _simulate_step(board, probe, chosen, W, H)
            if crash:
                break
            depth += 1
        # If we have runway AND midgame, sprint; or if area is tiny, sprint to escape
        if (depth >= 2 and 20 <= turn <= 120) or (best_score < 80 and depth >= 1):
            use_boost = True

    return f"{chosen}:BOOST" if use_boost else chosen


@app.route("/send-move", methods=["GET"])
def send_move():
    """Judge calls this (GET) to request the agent's move for the current tick.

    Query params the judge sends (optional): player_number, attempt_number,
    random_moves_left, turn_count. Agents can use this to decide.

    Return format: {"move": "DIRECTION"} or {"move": "DIRECTION:BOOST"}
    where DIRECTION is UP, DOWN, LEFT, or RIGHT
    and :BOOST is optional to use a speed boost (move twice)
    """
    player_number = request.args.get("player_number", default=1, type=int)

    with game_lock:
        state = dict(LAST_POSTED_STATE)

    move = _choose_move(state, player_number)
    return jsonify({"move": move}), 200


@app.route("/end", methods=["POST"])
def end_game():
    """Judge notifies agent that the match finished and provides final state.

    We update local state for record-keeping and return OK.
    """
    data = request.get_json()
    if data:
        _update_local_game_from_post(data)
    return jsonify({"status": "acknowledged"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5008"))
    app.run(host="0.0.0.0", port=port, debug=False)
