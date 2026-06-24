import numpy as np


class SmoothingFilter:
    def __init__(self, factor: float = 0.45, deadzone: float = 5.0):
        self._factor = factor
        self._deadzone = deadzone
        self._prev_x = None
        self._prev_y = None

    def update(self, x: float, y: float) -> tuple[float, float]:
        if self._prev_x is None:
            self._prev_x = x
            self._prev_y = y
            return x, y

        dx = x - self._prev_x
        dy = y - self._prev_y
        dist = (dx * dx + dy * dy) ** 0.5

        if dist < self._deadzone:
            return self._prev_x, self._prev_y

        smoothed_x = self._prev_x + self._factor * dx
        smoothed_y = self._prev_y + self._factor * dy
        self._prev_x = smoothed_x
        self._prev_y = smoothed_y
        return smoothed_x, smoothed_y

    def reset(self, x: float = None, y: float = None):
        self._prev_x = x
        self._prev_y = y

    @property
    def factor(self) -> float:
        return self._factor

    @factor.setter
    def factor(self, val: float):
        self._factor = max(0.0, min(1.0, val))

    @property
    def deadzone(self) -> float:
        return self._deadzone

    @deadzone.setter
    def deadzone(self, val: float):
        self._deadzone = max(0.0, val)


class GazeSmoothingFilter:
    def __init__(self, factor: float = 0.6, deadzone: float = 8.0):
        self._factor = factor
        self._deadzone = deadzone
        self._buffer_x = []
        self._buffer_y = []
        self._max_len = 4

    def update(self, x: float, y: float) -> tuple[float, float]:
        self._buffer_x.append(x)
        self._buffer_y.append(y)
        if len(self._buffer_x) > self._max_len:
            self._buffer_x.pop(0)
            self._buffer_y.pop(0)

        avg_x = float(np.mean(self._buffer_x))
        avg_y = float(np.mean(self._buffer_y))

        dx = x - avg_x
        dy = y - avg_y
        dist = (dx * dx + dy * dy) ** 0.5

        if dist < self._deadzone:
            return avg_x, avg_y

        smoothed_x = avg_x + self._factor * dx
        smoothed_y = avg_y + self._factor * dy
        return smoothed_x, smoothed_y

    def reset(self):
        self._buffer_x.clear()
        self._buffer_y.clear()
