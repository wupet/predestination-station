# agentw.py

class AgentC:
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

    def choose_action(self, game_state):
        """
        Always return 'RIGHT' as the action.
        Modify this function later for actual AI logic.
        """
        return "RIGHT"
