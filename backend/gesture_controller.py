"""Shared live/replay boundary: tracking loss must also revoke OS controls."""

from backend.action_mapper import ActionMapper, ActionResult
from backend.gesture_classifier import Gesture, GestureClassifier, GestureResult
from backend.pointer_controller import PointerController


class GestureController:
    def __init__(self, classifier: GestureClassifier, mapper: ActionMapper,
                 pointer: PointerController | None = None, mode: str = "navigation"):
        self.classifier = classifier
        self.mapper = mapper
        self.pointer = pointer or PointerController()
        self.paused = False
        self.tracking_status = "SHOW ONE HAND"
        self.set_mode(mode)

    def reset(self):
        self.classifier.reset()
        self.mapper.reset()
        self.pointer.reset()

    def set_mode(self, mode):
        if mode not in ("mouse", "navigation"):
            raise ValueError("Control mode must be mouse or navigation")
        self.mode = mode
        self.classifier.zoom_enabled = True
        self.reset()

    def set_paused(self, paused):
        self.paused = bool(paused)
        self.reset()

    def set_actions_enabled(self, enabled):
        self.mapper.set_actions_enabled(enabled)
        self.reset()

    @property
    def control_status(self):
        if self.paused:
            return "PAUSED: press P to resume"
        if self.tracking_status != "TRACKING":
            return self.tracking_status
        if self.mode == "mouse":
            return self.pointer.status
        if self.mapper.control_status == "SHOW OPEN PALM":
            return "WAITING: show open palm until READY"
        return self.mapper.control_status

    def process(self, hands, timestamp: float, image_width: float,
                image_height: float | None = None) -> tuple[GestureResult, ActionResult | None]:
        if self.paused:
            return GestureResult(Gesture.NONE), None
        if len(hands) != 1:
            self.reset()
            self.tracking_status = "SHOW ONE HAND" if not hands else "MULTIPLE HANDS: paused"
            return GestureResult(Gesture.NONE), None
        try:
            result = self.classifier.classify(hands[0], timestamp, image_width,
                                             click_context=self.mode == "mouse" and self.pointer.click_context)
        except ValueError:
            self.reset()
            self.tracking_status = "INVALID LANDMARKS: paused"
            return GestureResult(Gesture.NONE), None
        self.tracking_status = "TRACKING"
        if self.mode == "navigation":
            return result, self.mapper.handle(result, timestamp)
        if image_height is None:
            raise ValueError("Mouse mode needs the image height")
        two_finger_shapes = (Gesture.TWO_FINGER, Gesture.PREVIOUS_PAGE, Gesture.NEXT_PAGE,
                             Gesture.SCROLL_UP, Gesture.SCROLL_DOWN)
        if self.pointer.click_context and result.gesture in two_finger_shapes:
            # Intent comes from the preceding interaction, not finger direction.
            # Once pointing has armed a click, no V orientation may scroll or
            # send arrows, even when held after the click has completed.
            result = GestureResult(Gesture.TWO_FINGER_CLICK, result.confidence)
        command = self.pointer.process(result.gesture, hands[0], timestamp, (image_width, image_height))
        if self.pointer.suspended:
            self.mapper.reset()
            return result, None
        # Mouse movement/clicks and legacy navigation share one mode. Keep the
        # existing palm gate for scroll/arrows/zoom. Pointing consumes that gate
        # and selects clicking instead. A fist has its own one-shot dwell.
        navigation = (Gesture.PREVIOUS_PAGE, Gesture.NEXT_PAGE, Gesture.PINCH,
                      Gesture.ZOOM_IN, Gesture.ZOOM_OUT, Gesture.SCROLL_UP, Gesture.SCROLL_DOWN)
        if (result.gesture is Gesture.POINT and self.pointer.click_context) or result.gesture in (Gesture.TWO_FINGER_CLICK, Gesture.FIST, Gesture.THUMBS_UP, Gesture.THUMBS_DOWN):
            self.mapper.reset()
        routed = result.gesture if result.gesture in navigation + (Gesture.OPEN_PALM, Gesture.NONE, Gesture.TWO_FINGER) else Gesture.POINT
        navigation_action = self.mapper.handle(routed, timestamp)
        if result.gesture in navigation:
            self.pointer.status = ("Show open palm until READY for navigation/zoom"
                                   if self.mapper.control_status == "SHOW OPEN PALM"
                                   else self.mapper.control_status)
        elif result.gesture is Gesture.OPEN_PALM and self.mapper.control_status == "READY":
            self.pointer.status = "READY: point/click, fist, scroll, left/right or pinch zoom"
        if command is not None and result.gesture is Gesture.FIST:
            command = self.mapper.commands[Gesture.FIST]
        action = self.mapper.execute(command) if command is not None else navigation_action
        if action is not None and action.error:
            self.pointer.reset()
        if result.gesture is Gesture.NONE and any(
            lm[1] < 0 or lm[1] >= image_width or lm[2] < 0 or lm[2] >= image_height
            for lm in hands[0]
        ):
            self.pointer.status = "Hand clipped: move back, then point again before clicking"
        elif result.gesture is Gesture.POINT and not self.pointer.suspended and any(
            lm[1] < image_width * .04 or lm[1] >= image_width * .96
            or lm[2] < image_height * .04 or lm[2] >= image_height * .96
            for lm in hands[0]
        ):
            # Warn before a pointing-to-click transition clips the lower hand.
            # This is feedback only: keep the pointer mapping and click gates.
            self.pointer.status = "Hand near camera edge: move back to keep whole hand visible"
        return result, action
