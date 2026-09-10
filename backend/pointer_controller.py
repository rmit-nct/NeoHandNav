"""Time-based mouse interaction, independent of cameras and OS input.

Point positions the cursor; extending the middle finger clicks the frozen
target once. A short thumbs-up, released back to pointing, also clicks once;
a sustained thumbs-up double-clicks once. There is never a
speculative single click before a double click. A held fist toggles playback;
open palm cancels. Clicks use the current cursor, including at startup.
"""

from dataclasses import dataclass
from collections import deque
from math import hypot, isfinite, pi

from backend.action_mapper import ActionCommand
from backend.gesture_classifier import Gesture, GestureClassifier


@dataclass(frozen=True)
class PointerSettings:
    margin: float = .15
    min_cutoff: float = 1.5
    speed_coefficient: float = 6.0
    point_hold_seconds: float = .18
    motion_buffer_seconds: float = .10
    pointer_deadzone_pixels: float = 2.
    click_min_seconds: float = .15
    two_finger_click_seconds: float = .18
    click_confirmation_window_seconds: float = .6
    double_click_hold_seconds: float = .9
    transition_grace_seconds: float = .8
    fist_hold_seconds: float = .6
    max_frame_gap_seconds: float = .5
    scroll_interval_seconds: float = .06
    scroll_amount: int = 1

    def __post_init__(self):
        for name, value in vars(self).items():
            if not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if not 0 <= self.margin < .45:
            raise ValueError("margin must be between 0 and .45")
        if self.min_cutoff <= 0 or self.point_hold_seconds <= 0:
            raise ValueError("filter cutoff and point hold must be positive")
        if not 0 < self.click_min_seconds < self.double_click_hold_seconds:
            raise ValueError("double click hold must exceed the positive minimum click hold")
        if self.transition_grace_seconds <= 0 or self.max_frame_gap_seconds <= 0 or self.fist_hold_seconds <= 0 or self.two_finger_click_seconds <= 0:
            raise ValueError("transition grace, frame gap and fist hold must be positive")
        if not isinstance(self.scroll_amount, int) or self.scroll_amount < 1:
            raise ValueError("scroll_amount must be a positive integer")
        if self.click_confirmation_window_seconds <= self.two_finger_click_seconds:
            raise ValueError("click confirmation window must exceed the click hold")
        if self.motion_buffer_seconds > .25:
            raise ValueError("motion buffer must be between 0 and .25 seconds")
        if self.pointer_deadzone_pixels > 10:
            raise ValueError("pointer deadzone must be between 0 and 10 pixels")


class AdaptiveFilter:
    """One Euro low-pass filter in normalized screen coordinates.

    Slow movement gets stronger smoothing; faster movement raises the cutoff.
    Casiez, Roussel & Vogel, CHI 2012: https://gery.casiez.net/1euro/
    """

    def __init__(self, value: float, cutoff: float, beta: float):
        self.value = self.raw = value
        self.derivative = 0.0
        self.cutoff, self.beta = cutoff, beta

    @staticmethod
    def alpha(cutoff, dt):
        return 1 / (1 + 1 / (2 * pi * cutoff * dt))

    def update(self, value, dt):
        derivative = (value - self.raw) / dt
        self.raw = value
        a = self.alpha(1.0, dt)
        self.derivative += a * (derivative - self.derivative)
        a = self.alpha(self.cutoff + self.beta * abs(self.derivative), dt)
        self.value += a * (value - self.value)
        return self.value


class PointerController:
    def __init__(self, screen_size=(1920, 1080), settings=None, initial_position=None):
        if len(screen_size) != 2 or any(not isfinite(v) or v < 8 for v in screen_size):
            raise ValueError("screen_size must contain two dimensions of at least 8 pixels")
        self.screen_size = tuple(int(v) for v in screen_size)
        self.settings = settings or PointerSettings()
        self.position = initial_position or tuple(v // 2 for v in self.screen_size)
        if len(self.position) != 2 or any(not isfinite(v) for v in self.position):
            raise ValueError("initial_position must contain two finite coordinates")
        self.position = tuple(self.position)
        self.suspended = False
        self.reset()

    def reset(self):
        # Losing tracking or resetting controls must not repeat a held click or
        # playback toggle. A deliberate point/palm releases these latches.
        self._click_consumed = getattr(self, '_click_consumed', False) or getattr(self, '_click_started', None) is not None
        self._fist_consumed = getattr(self, '_fist_consumed', False) or getattr(self, '_fist_started', None) is not None
        self._last_time = None
        self._point_since = None
        self._last_point = None
        self._unknown_since = None
        self._click_started = None
        self._click_last_seen = None
        self._click_pose = None
        self._fist_started = None
        self._two_finger_started = None
        self._two_finger_wall_started = None
        self.click_context = False
        self._middle_baseline = None
        self._pointer_frozen = False
        self._release_since = None
        self._last_scroll = None
        self._resume_after = 0.0
        self._filter_x = self._filter_y = None
        self._filter_time = None
        self._motion_samples = deque()
        self.progress = 0.0
        self.status = "Point your index finger to move"

    def physical_pointer_moved(self, position):
        """Give the real mouse precedence until an explicit neutral pose."""
        if hypot(position[0] - self.position[0], position[1] - self.position[1]) > 30:
            self.position = tuple(position)
            self.reset()
            self.suspended = True
            self.status = "Mouse moved manually: show open palm to resume"

    def _cancel_click(self):
        self._click_started = self._click_last_seen = self._click_pose = None
        self.progress = 0.0

    def _discard_pending_motion(self):
        """Keep the visible target; never replay transition movement later."""
        self._motion_samples.clear()
        self._filter_x = self._filter_y = None
        self._filter_time = None

    def _click(self, count, button):
        x, y = self.position
        self._discard_pending_motion()
        self._cancel_click()
        self._click_consumed = True
        self._point_since = self._last_point = None
        self._middle_baseline = None
        self._pointer_frozen = False
        self.progress = 1.0
        label = "right click" if button == "right" else "double click" if count == 2 else "single click"
        self.status = f"{label.title()} selected; point again to move"
        return ActionCommand("click", (x, y, count, button), label)

    def _move(self, point, now, image_size):
        width, height = self.screen_size
        margin = self.settings.margin
        x = min(1., max(0., (point[0] / image_size[0] - margin) / (1 - 2*margin)))
        y = min(1., max(0., (point[1] / image_size[1] - margin) / (1 - 2*margin)))
        # Hold a short interval of raw pointing motion before displaying it.
        # A pose transition can then discard tremor without rewinding a click
        # to an unseen historical target. Interpolation makes delay independent
        # of frame rate, including irregular webcam timestamps.
        self._motion_samples.append((now,x,y))
        cutoff = now-self.settings.motion_buffer_seconds
        while len(self._motion_samples) > 1 and self._motion_samples[1][0] <= cutoff:
            self._motion_samples.popleft()
        first = self._motion_samples[0]
        if first[0] > cutoff + 1e-9:
            return None
        x,y = first[1:]
        if len(self._motion_samples) > 1:
            following = self._motion_samples[1]
            fraction = max(0., min(1., (cutoff-first[0])/(following[0]-first[0])))
            x += fraction*(following[1]-x)
            y += fraction*(following[2]-y)
        if self._filter_x is None:
            self._filter_x = AdaptiveFilter(self.position[0] / (width-1), self.settings.min_cutoff, self.settings.speed_coefficient)
            self._filter_y = AdaptiveFilter(self.position[1] / (height-1), self.settings.min_cutoff, self.settings.speed_coefficient)
            # Resuming at a displaced hand location is not a velocity sample.
            # Seed raw input separately so it cannot spike the adaptive cutoff.
            self._filter_x.raw, self._filter_y.raw = x,y
        dt = max(.001, min(.1, now - self._filter_time)) if self._filter_time is not None else 1/30
        self._filter_time = now
        x, y = self._filter_x.update(x, dt), self._filter_y.update(y, dt)
        # Leave physical fail-safe corners reachable with the real mouse, but
        # never accidentally enter them through the gesture mapping.
        target = (max(2, min(width-3, round(x*(width-1)))), max(2, min(height-3, round(y*(height-1)))))
        if hypot(target[0]-self.position[0],target[1]-self.position[1]) <= self.settings.pointer_deadzone_pixels:
            return None
        self.position = target
        return ActionCommand("move", target, "move pointer")

    @staticmethod
    def _middle_shape(landmarks, image_width):
        """Rotation/translation invariant early signal, before a full V pose.

        Compare the middle finger's bend and reach with its curled pointing
        baseline. Use raw coordinates so classifier debounce cannot move the
        cursor while this finger is opening.
        """
        p = {int(lm[0]): tuple(lm[1:4]) for lm in landmarks}
        angle = GestureClassifier._angle_3d(p[9], p[10], p[12], image_width)
        scale = max(GestureClassifier._distance_3d(p[0], p[9], image_width), 1.)
        reach = GestureClassifier._distance_3d(p[9], p[12], image_width)/scale
        return angle, reach

    def process(self, gesture, landmarks, timestamp, image_size):
        if not isfinite(timestamp) or any(not isfinite(v) or v <= 0 for v in image_size):
            self.reset()
            raise ValueError("Mouse input needs finite time and positive image dimensions")
        now = timestamp
        if self._last_time is not None and (
            now <= self._last_time or now-self._last_time > self.settings.max_frame_gap_seconds
        ):
            self.reset()
        self._last_time = now
        if gesture is not Gesture.POINT:
            self._discard_pending_motion()
        if self.suspended:
            if gesture is Gesture.OPEN_PALM:
                self.suspended = False
                self.reset()
            else:
                self.status = "Mouse moved manually: show open palm to resume"
            return None

        if gesture in (Gesture.POINT, Gesture.OPEN_PALM):
            if self._release_since is None:
                self._release_since = now
            if now-self._release_since >= self.settings.point_hold_seconds:
                self._click_consumed = self._fist_consumed = False
        else:
            self._release_since = None

        if gesture in (Gesture.NONE, Gesture.TWO_FINGER):
            if self._unknown_since is None:
                self._unknown_since = now
            if now-self._unknown_since > self.settings.transition_grace_seconds:
                self.reset()
                self._last_time = now
            self.status = "Hold a clear pose; no input sent"
            return None

        if self._unknown_since is not None:
            if now-self._unknown_since > self.settings.transition_grace_seconds:
                self.reset()
                self._last_time = now
            elif self._click_started is not None and gesture is self._click_pose:
                # An uncertain frame never advances a long-press timer.
                self._click_started += now-self._unknown_since
            if self._fist_started is not None and gesture is Gesture.FIST:
                self._fist_started += now-self._unknown_since
            if self._two_finger_started is not None and gesture is Gesture.TWO_FINGER_CLICK:
                self._two_finger_started += now-self._unknown_since
            self._unknown_since = None

        if gesture is not Gesture.FIST:
            self._fist_started = None

        if gesture is Gesture.POINT:
            self._two_finger_started = None
            self._two_finger_wall_started = None
            if self._click_started is not None:
                duration = self._click_last_seen - self._click_started
                button = "left" if self._click_pose is Gesture.THUMBS_UP else "right"
                can_click = duration >= self.settings.click_min_seconds and not self._click_consumed
                self._cancel_click()
                if can_click:
                    command = self._click(1, button)
                    self._resume_after = now + .18
                    return command
            if self._point_since is None:
                self._point_since = now
            self._last_point = now
            self.progress = min(1., (now-self._point_since) / self.settings.point_hold_seconds)
            if self.progress < 1 or now < self._resume_after:
                self.status = "Hold point briefly to position the cursor"
                return None
            self.click_context = True
            middle = self._middle_shape(landmarks, image_size[0])
            if self._middle_baseline is None:
                self._middle_baseline = middle
            opening = middle[0] > self._middle_baseline[0]+20 and middle[1] > self._middle_baseline[1]+.08
            if opening:
                self._pointer_frozen = True
            elif self._pointer_frozen:
                # A clear return to the original curled middle finger cancels
                # the transition without firing anything.
                self._pointer_frozen = False
            if self._pointer_frozen:
                self._discard_pending_motion()
                self.status = "Target locked: extend middle finger fully to click"
                return None
            self.status = "Point: move | Add middle finger: single click"
            points = {int(lm[0]): lm for lm in landmarks}
            return self._move(points[8][1:3], now, image_size)

        if gesture is Gesture.TWO_FINGER_CLICK:
            if not self.click_context:
                self.status = "Point first to click; open palm first to scroll"
                return None
            if self._click_consumed:
                self.status = "Single click finished; fold middle finger to point again"
                return None
            if (self._two_finger_started is None or
                now-self._two_finger_wall_started > self.settings.click_confirmation_window_seconds):
                self._two_finger_started = now
                self._two_finger_wall_started = now
            self.progress = min(1., (now-self._two_finger_started)/self.settings.two_finger_click_seconds)
            self.status = "Target locked: hold two fingers briefly for one click"
            if self.progress >= 1:
                return self._click(1, "left")
            return None

        if gesture in (Gesture.THUMBS_UP, Gesture.THUMBS_DOWN):
            self.click_context = False
            self._two_finger_started = None
            if self._click_consumed:
                self.status = "Click finished; point again before another click"
                return None
            if self._click_started is None:
                # The cursor already has a target, from either pointing or the
                # real mouse. Forming a thumb pose must not have a 400 ms deadline.
                self._click_started = now
                self._click_pose = gesture
            if gesture is not self._click_pose:
                self._cancel_click()
                self._click_consumed = True
                self._point_since = self._last_point = None
                self.status = "Click cancelled: point at the target again"
                return None
            self._click_last_seen = now
            held = now-self._click_started
            self.progress = min(1., held/self.settings.double_click_hold_seconds)
            self.status = ("Return to point: single click | Keep holding: double click"
                           if gesture is Gesture.THUMBS_UP else "Return to point: right click")
            if held >= self.settings.double_click_hold_seconds:
                return self._click(2 if gesture is Gesture.THUMBS_UP else 1,
                                   "left" if gesture is Gesture.THUMBS_UP else "right")
            return None

        self._cancel_click()
        self.click_context = False
        self._two_finger_started = None
        self._middle_baseline = None
        self._pointer_frozen = False
        self._point_since = self._last_point = None
        self._filter_x = self._filter_y = None
        self._last_scroll = None
        if gesture is Gesture.FIST:
            if self._fist_consumed:
                self.status = "Play/pause sent; show palm or point before another fist"
                return None
            if self._fist_started is None:
                self._fist_started = now
            self.progress = min(1., (now-self._fist_started)/self.settings.fist_hold_seconds)
            self.status = "Hold fist until bar fills: play/pause once"
            if self.progress >= 1:
                self._fist_consumed = True
                self.status = "Play/pause sent; show palm or point before another fist"
                return ActionCommand("key", ("playpause",), "play or pause")
            return None
        self.status = ("Open palm: movement and pending clicks stopped" if gesture is Gesture.OPEN_PALM
                       else "Show open palm before navigation or pinch zoom")
        return None
