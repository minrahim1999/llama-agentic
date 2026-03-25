"""Session statistics — turns, tool calls, token estimates, wall-clock time."""

import time
from dataclasses import dataclass, field


@dataclass
class Stats:
    session_start: float = field(default_factory=time.time)
    turns: int = 0
    tool_calls: int = 0
    chars_in: int = 0   # user + system prompt chars
    chars_out: int = 0  # assistant output chars

    @property
    def elapsed_secs(self) -> float:
        return time.time() - self.session_start

    @property
    def estimated_tokens(self) -> int:
        """Rough estimate: 1 token ≈ 4 chars."""
        return (self.chars_in + self.chars_out) // 4

    def record_turn(self, user_input: str, assistant_output: str):
        self.turns += 1
        self.chars_in += len(user_input)
        self.chars_out += len(assistant_output)

    def record_tool_call(self, output: str):
        self.tool_calls += 1
        self.chars_in += len(output)  # tool output fed back to model

    def summary(self) -> str:
        elapsed = self.elapsed_secs
        mins, secs = divmod(int(elapsed), 60)
        time_str = f"{mins}m{secs:02d}s" if mins else f"{secs}s"
        return (
            f"Turns: {self.turns}  "
            f"Tool calls: {self.tool_calls}  "
            f"~{self.estimated_tokens:,} tokens  "
            f"Time: {time_str}"
        )


# Global singleton for the current session
session_stats = Stats()


def reset():
    global session_stats
    session_stats = Stats()
