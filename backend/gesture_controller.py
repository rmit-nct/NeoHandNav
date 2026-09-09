"""Shared live/replay boundary: tracking loss must also revoke OS controls."""

from backend.action_mapper import ActionMapper, ActionResult
from backend.gesture_classifier import Gesture, GestureClassifier, GestureResult


class GestureController:
    def __init__(self, classifier: GestureClassifier, mapper: ActionMapper):
        self.classifier = classifier
        self.mapper = mapper
        self.tracking_status = "SHOW ONE HAND"

    def process(self, hands, timestamp: float, image_width: float) -> tuple[GestureResult, ActionResult | None]:
        if len(hands) != 1:
            self.classifier.reset()
            self.mapper.reset()
            self.tracking_status = "SHOW ONE HAND" if not hands else "MULTIPLE HANDS: paused"
            return GestureResult(Gesture.NONE), None
        try:
            result = self.classifier.classify(hands[0], timestamp, image_width)
        except ValueError:
            self.classifier.reset()
            self.mapper.reset()
            self.tracking_status = "INVALID LANDMARKS: paused"
            return GestureResult(Gesture.NONE), None
        self.tracking_status = "TRACKING"
        return result, self.mapper.handle(result, timestamp)
