# agentc.py

class AgentC:
    """
    Aggressive collision-seeking agent for Tron-like game.
    Rushes down opponent and attempts head-on collisions.
    """

    ACTIONS = [
        "UP", "DOWN", "LEFT", "RIGHT",
        "UP:BOOST", "DOWN:BOOST", "LEFT:BOOST", "RIGHT:BOOST"
    ]

    def __init__(self):
        self.last_action = "RIGHT"
        self.current_direction = (1, 0)  # Track current direction (dx, dy)
        self.boost_threshold = 1  # Save at least 1 boost
        self.last_opponent_pos = None
        self.predicted_opponent_dir = None
        print("AgentC initialized successfully")

    def choose_action(self, game_state):
        try:
            board = game_state.get("board")
            player_number = game_state.get("player_number", 1)
            turn_count = game_state.get("turn_count", 0)
            
            print(f"Turn {turn_count}: Player {player_number}")
            
            # Get our trail and opponent's trail
            if player_number == 1:
                my_trail = game_state.get("agent1_trail", [])
                opponent_trail = game_state.get("agent2_trail", [])
                my_boosts = game_state.get("agent1_boosts", 3)
                my_length = game_state.get("agent1_length", len(my_trail))
                opponent_length = game_state.get("agent2_length", len(opponent_trail))
            else:
                my_trail = game_state.get("agent2_trail", [])
                opponent_trail = game_state.get("agent1_trail", [])
                my_boosts = game_state.get("agent2_boosts", 3)
                my_length = game_state.get("agent2_length", len(my_trail))
                opponent_length = game_state.get("agent1_length", len(opponent_trail))
            
            print(f"My trail length: {my_length}, Opponent trail length: {opponent_length}")
            
            # Determine if we should be aggressive or defensive
            should_be_aggressive = my_length > opponent_length
            print(f"Strategy: {'AGGRESSIVE (longer trail)' if should_be_aggressive else 'DEFENSIVE (shorter trail)'}")
            
            # Update current direction from trail
            if len(my_trail) >= 2:
                last_pos = my_trail[-1]
                prev_pos = my_trail[-2]
                dx = last_pos[0] - prev_pos[0]
                dy = last_pos[1] - prev_pos[1]
                
                # Handle torus wrapping
                width = len(board[0]) if board else 20
                height = len(board)
                if abs(dx) > 1:
                    dx = -1 if dx > 0 else 1
                if abs(dy) > 1:
                    dy = -1 if dy > 0 else 1
                
                self.current_direction = (dx, dy)
                print(f"Current direction from trail: {self.current_direction}")
            
            if not my_trail or not opponent_trail or not board:
                print("Missing game data, using default")
                return self.last_action if self.last_action in self.ACTIONS else "RIGHT"
            
            # Get current positions
            my_head = tuple(my_trail[-1])
            opponent_head = tuple(opponent_trail[-1])
            
            print(f"My position: {my_head}, Opponent position: {opponent_head}")
            
            # Get board dimensions
            height = len(board)
            width = len(board[0]) if height > 0 else 0
            
            # Predict opponent's next position
            opponent_dir = self._predict_opponent_direction(opponent_trail)
            predicted_opp_pos = self._get_predicted_position(
                opponent_head, opponent_dir, width, height
            )
            
            print(f"Predicted opponent position: {predicted_opp_pos}")
            
            best_move = None
            
            # Choose strategy based on trail length
            if should_be_aggressive:
                # Aggressive: Try to intercept and collide
                best_move = self._find_interception_move(
                    my_head, opponent_head, predicted_opp_pos,
                    board, my_trail, opponent_trail, height, width
                )
                print(f"Interception move: {best_move}")
                
                if best_move is None:
                    # Fallback to aggressive chase
                    best_move = self._find_aggressive_chase(
                        my_head, opponent_head, board, 
                        my_trail, opponent_trail, height, width
                    )
                    print(f"Aggressive chase move: {best_move}")
            else:
                # Defensive: Prioritize survival and space control
                best_move = self._find_space_control_move(
                    my_head, opponent_head, board, 
                    my_trail, opponent_trail, height, width
                )
                print(f"Space control move: {best_move}")
                
                if best_move is None:
                    # Try to move away from opponent
                    best_move = self._find_evasive_move(
                        my_head, opponent_head, board, 
                        my_trail, opponent_trail, height, width
                    )
                    print(f"Evasive move: {best_move}")
            
            if best_move is None:
                # Last resort: find any safe move
                best_move = self._find_safe_move(
                    my_head, board, my_trail, opponent_trail, height, width
                )
                print(f"Safe move: {best_move}")
            
            if best_move is None:
                # Extract direction from last action
                if ":" in self.last_action:
                    best_move = self.last_action.split(":")[0]
                else:
                    best_move = self.last_action
                print(f"Using last action: {best_move}")
            
            # Decide whether to use boost
            use_boost = self._should_boost_for_collision(
                my_head, opponent_head, predicted_opp_pos,
                my_boosts, board, my_trail, opponent_trail, 
                height, width, turn_count, should_be_aggressive
            )
            
            print(f"Use boost: {use_boost}, Boosts remaining: {my_boosts}")
            
            # Create final action
            if use_boost and my_boosts > self.boost_threshold:
                action = f"{best_move}:BOOST"
            else:
                action = best_move
            
            # Validate action
            if action not in self.ACTIONS:
                action = best_move
            
            # Update current direction based on chosen move
            direction_map = {
                "UP": (0, -1),
                "DOWN": (0, 1),
                "LEFT": (-1, 0),
                "RIGHT": (1, 0)
            }
            
            # Extract base direction from action (might have :BOOST)
            base_direction = action.split(":")[0] if ":" in action else action
            if base_direction in direction_map:
                self.current_direction = direction_map[base_direction]
            
            self.last_action = action
            self.last_opponent_pos = opponent_head
            
            print(f"Final action: {action}")
            return action
                
        except Exception as e:
            print(f"Error in choose_action: {e}")
            import traceback
            traceback.print_exc()
            return self.last_action if self.last_action in self.ACTIONS else "RIGHT"

    def _predict_opponent_direction(self, opponent_trail):
        """Predict opponent's current direction based on last moves"""
        if len(opponent_trail) < 2:
            return None
        
        last_pos = opponent_trail[-1]
        prev_pos = opponent_trail[-2]
        
        dx = last_pos[0] - prev_pos[0]
        dy = last_pos[1] - prev_pos[1]
        
        # Handle torus wrapping
        if abs(dx) > 1:
            dx = -1 if dx > 0 else 1
        if abs(dy) > 1:
            dy = -1 if dy > 0 else 1
        
        return (dx, dy)

    def _get_predicted_position(self, pos, direction, width, height):
        """Get predicted next position given current direction"""
        if direction is None:
            return pos
        
        dx, dy = direction
        new_x = (pos[0] + dx) % width
        new_y = (pos[1] + dy) % height
        return (new_x, new_y)

    def _find_interception_move(self, my_pos, opp_pos, predicted_opp_pos,
                                 board, my_trail, opp_trail, height, width):
        """
        Find move that intercepts opponent's predicted path for head-on collision
        """
        directions = {
            "UP": (0, -1),
            "DOWN": (0, 1),
            "LEFT": (-1, 0),
            "RIGHT": (1, 0)
        }
        
        best_move = None
        best_score = float('inf')
        valid_moves = []
        
        for move_name, (dx, dy) in directions.items():
            # Skip if this is opposite to current direction (invalid move)
            if self._is_opposite_direction((dx, dy), self.current_direction):
                print(f"  {move_name}: Skipped (opposite direction)")
                continue
            
            # Calculate new position
            new_x = (my_pos[0] + dx) % width
            new_y = (my_pos[1] + dy) % height
            new_pos = (new_x, new_y)
            
            # Check if move is valid
            if not self._is_position_safe(new_pos, board, my_trail, opp_trail):
                print(f"  {move_name}: Unsafe position {new_pos}")
                continue
            
            valid_moves.append(move_name)
            
            # Calculate score based on interception potential
            # Distance to predicted opponent position
            dist_to_predicted = self._torus_distance(new_pos, predicted_opp_pos, width, height)
            
            # Distance to current opponent position
            dist_to_current = self._torus_distance(new_pos, opp_pos, width, height)
            
            # Prefer moves that get closer to predicted position
            # and are on collision course
            score = dist_to_predicted
            
            # Bonus for being very close (collision imminent)
            if dist_to_current <= 2:
                score -= 10
            
            # Check if we're moving toward opponent's predicted path
            if self._is_on_collision_course(new_pos, predicted_opp_pos, (dx, dy), width, height):
                score -= 5
            
            print(f"  {move_name}: Score {score} (dist to predicted: {dist_to_predicted}, dist to current: {dist_to_current})")
            
            if score < best_score:
                best_score = score
                best_move = move_name
        
        print(f"  Valid moves: {valid_moves}, Best: {best_move}")
        return best_move

    def _is_on_collision_course(self, my_pos, target_pos, my_dir, width, height):
        """Check if current direction leads toward target"""
        # Calculate if continuing in this direction reduces distance
        dx, dy = my_dir
        next_pos = ((my_pos[0] + dx) % width, (my_pos[1] + dy) % height)
        
        current_dist = self._torus_distance(my_pos, target_pos, width, height)
        next_dist = self._torus_distance(next_pos, target_pos, width, height)
        
        return next_dist < current_dist

    def _find_aggressive_chase(self, my_pos, opp_pos, board, my_trail, opp_trail, height, width):
        """
        Aggressive chase - move directly toward opponent
        """
        directions = {
            "UP": (0, -1),
            "DOWN": (0, 1),
            "LEFT": (-1, 0),
            "RIGHT": (1, 0)
        }
        
        best_move = None
        best_distance = float('inf')
        
        for move_name, (dx, dy) in directions.items():
            # Skip if this is opposite to current direction (invalid move)
            if self._is_opposite_direction((dx, dy), self.current_direction):
                continue
            
            new_x = (my_pos[0] + dx) % width
            new_y = (my_pos[1] + dy) % height
            new_pos = (new_x, new_y)
            
            if self._is_position_safe(new_pos, board, my_trail, opp_trail):
                distance = self._torus_distance(new_pos, opp_pos, width, height)
                
                if distance < best_distance:
                    best_distance = distance
                    best_move = move_name
        
        return best_move

    def _find_space_control_move(self, my_pos, opp_pos, board, my_trail, opp_trail, height, width):
        """
        Defensive strategy: Find moves that maximize available space
        """
        directions = {
            "UP": (0, -1),
            "DOWN": (0, 1),
            "LEFT": (-1, 0),
            "RIGHT": (1, 0)
        }
        
        best_move = None
        best_space = -1
        
        for move_name, (dx, dy) in directions.items():
            # Skip if this is opposite to current direction
            if self._is_opposite_direction((dx, dy), self.current_direction):
                continue
            
            new_x = (my_pos[0] + dx) % width
            new_y = (my_pos[1] + dy) % height
            new_pos = (new_x, new_y)
            
            if self._is_position_safe(new_pos, board, my_trail, opp_trail):
                # Calculate available space using flood fill
                available_space = self._calculate_available_space(
                    new_pos, board, my_trail, opp_trail, height, width
                )
                
                print(f"  {move_name}: Available space = {available_space}")
                
                if available_space > best_space:
                    best_space = available_space
                    best_move = move_name
        
        return best_move

    def _find_evasive_move(self, my_pos, opp_pos, board, my_trail, opp_trail, height, width):
        """
        Evasive strategy: Move away from opponent while staying safe
        """
        directions = {
            "UP": (0, -1),
            "DOWN": (0, 1),
            "LEFT": (-1, 0),
            "RIGHT": (1, 0)
        }
        
        best_move = None
        best_distance = -1
        
        for move_name, (dx, dy) in directions.items():
            # Skip if this is opposite to current direction
            if self._is_opposite_direction((dx, dy), self.current_direction):
                continue
            
            new_x = (my_pos[0] + dx) % width
            new_y = (my_pos[1] + dy) % height
            new_pos = (new_x, new_y)
            
            if self._is_position_safe(new_pos, board, my_trail, opp_trail):
                # Calculate distance from opponent (we want to maximize this)
                distance = self._torus_distance(new_pos, opp_pos, width, height)
                
                if distance > best_distance:
                    best_distance = distance
                    best_move = move_name
        
        return best_move

    def _calculate_available_space(self, start_pos, board, my_trail, opp_trail, height, width, max_depth=15):
        """
        Use BFS to calculate reachable empty space from a position
        Limited depth to avoid performance issues
        """
        from collections import deque
        
        visited = set()
        queue = deque([(start_pos, 0)])
        visited.add(start_pos)
        space_count = 0
        
        directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        
        while queue and space_count < max_depth:
            pos, depth = queue.popleft()
            
            if depth >= max_depth:
                continue
            
            space_count += 1
            
            for dx, dy in directions:
                new_x = (pos[0] + dx) % width
                new_y = (pos[1] + dy) % height
                new_pos = (new_x, new_y)
                
                if new_pos not in visited:
                    visited.add(new_pos)
                    
                    # Check if this position is reachable
                    if new_pos not in my_trail and new_pos not in opp_trail and board[new_y][new_x] == 0:
                        queue.append((new_pos, depth + 1))
        
        return space_count
        """Find any safe move when no better option exists"""
        directions = {
            "UP": (0, -1),
            "DOWN": (0, 1),
            "LEFT": (-1, 0),
            "RIGHT": (1, 0)
        }
        
        for move_name, (dx, dy) in directions.items():
            # Skip if this is opposite to current direction (invalid move)
            if self._is_opposite_direction((dx, dy), self.current_direction):
                continue
            
            new_x = (my_pos[0] + dx) % width
            new_y = (my_pos[1] + dy) % height
            new_pos = (new_x, new_y)
            
            if self._is_position_safe(new_pos, board, my_trail, opp_trail):
                return move_name
        
        return "RIGHT"

    def _is_opposite_direction(self, new_dir, current_dir):
        """Check if new direction is opposite to current direction"""
        dx_new, dy_new = new_dir
        dx_cur, dy_cur = current_dir
        return (dx_new, dy_new) == (-dx_cur, -dy_cur)

    def _is_position_safe(self, pos, board, my_trail, opp_trail):
        """Check if position is safe to move to"""
        x, y = pos
        
        # In Tron, trails are permanent. We cannot move into any trail position
        # EXCEPT we want to allow moving into opponent's head for head-on collision
        
        # Check if position is in our trail
        if pos in my_trail:
            return False
        
        # Check if position is in opponent's trail
        # Allow moving to opponent's current head position (for head-on collision)
        if len(opp_trail) > 0:
            opponent_head = tuple(opp_trail[-1])
            # Allow head-on collision
            if pos == opponent_head:
                return True
            # Don't move into opponent's trail body
            if pos in [tuple(p) for p in opp_trail]:
                return False
        
        # Check board state (walls, etc)
        if board[y][x] != 0:  # 0 is EMPTY
            return False
        
        return True

    def _torus_distance(self, pos1, pos2, width, height):
        """Calculate Manhattan distance with torus wrapping"""
        x1, y1 = pos1
        x2, y2 = pos2
        
        dx = min(abs(x2 - x1), width - abs(x2 - x1))
        dy = min(abs(y2 - y1), height - abs(y2 - y1))
        
        return dx + dy

    def _should_boost_for_collision(self, my_pos, opp_pos, predicted_opp_pos,
                                     my_boosts, board, my_trail, opp_trail,
                                     height, width, turn_count, should_be_aggressive):
        """
        Decide when to use boost for aggressive collision
        Save at least 1 boost for final collision
        Only boost aggressively when we have the longer trail
        """
        if my_boosts <= self.boost_threshold:
            return False
        
        # Distance to opponent
        dist_to_opp = self._torus_distance(my_pos, opp_pos, width, height)
        
        # Distance to predicted position
        dist_to_predicted = self._torus_distance(my_pos, predicted_opp_pos, width, height)
        
        # Only use aggressive boosting if we have the advantage
        if should_be_aggressive:
            # Use boost when very close for collision (distance 2-4)
            if 2 <= dist_to_opp <= 4:
                return True
            
            # Use boost when approaching predicted interception point
            if dist_to_predicted <= 3 and dist_to_opp <= 6:
                return True
            
            # Use boost early game to close distance quickly
            if turn_count < 50 and dist_to_opp <= 8 and my_boosts > 2:
                return True
            
            # Use boost mid-game for aggressive positioning
            if 50 <= turn_count < 120 and dist_to_opp <= 5 and my_boosts > 1:
                return True
            
            # Save last boost for late game collision
            if turn_count >= 120 and my_boosts == 2 and dist_to_opp <= 3:
                return True
        else:
            # Defensive: only boost to escape immediate danger
            if dist_to_opp <= 3 and my_boosts > 2:
                return True
        
        return False