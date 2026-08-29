from __future__ import annotations

import unittest

from backend.action_mapper import ActionMapper
from backend.gesture_classifier import Gesture


class ActionMapperTests(unittest.TestCase):
    def test_dry_run_returns_action_without_executing(self):
        executed = []
        mapper = ActionMapper(actions_enabled=False, executor=executed.append)

        result = mapper.handle(Gesture.SWIPE_RIGHT, timestamp=0.0)

        self.assertIsNotNone(result)
        self.assertFalse(result.executed)
        self.assertEqual(result.command.description, "next page")
        self.assertEqual(executed, [])

    def test_enabled_mapper_executes_after_cooldown(self):
        executed = []
        mapper = ActionMapper(
            actions_enabled=True,
            cooldown_ms=500,
            executor=executed.append,
        )

        self.assertIsNotNone(mapper.handle(Gesture.SCROLL_UP, timestamp=0.0))
        self.assertIsNone(mapper.handle(Gesture.SCROLL_UP, timestamp=0.2))
        self.assertIsNotNone(mapper.handle(Gesture.SCROLL_UP, timestamp=0.6))
        self.assertEqual(len(executed), 2)

    def test_held_fist_triggers_only_once_until_released(self):
        executed = []
        mapper = ActionMapper(
            actions_enabled=True,
            cooldown_ms=100,
            executor=executed.append,
        )

        self.assertIsNotNone(mapper.handle(Gesture.FIST, timestamp=0.0))
        self.assertIsNone(mapper.handle(Gesture.FIST, timestamp=1.0))
        mapper.handle(Gesture.OPEN_PALM, timestamp=1.1)
        self.assertIsNotNone(mapper.handle(Gesture.FIST, timestamp=1.2))
        self.assertEqual(len(executed), 2)

    def test_single_none_frame_does_not_retrigger_held_fist(self):
        mapper = ActionMapper(
            actions_enabled=False,
            cooldown_ms=0,
            fist_release_ms=250,
        )
        self.assertIsNotNone(mapper.handle(Gesture.FIST, timestamp=0.0))
        mapper.handle(Gesture.NONE, timestamp=0.1)
        self.assertIsNone(mapper.handle(Gesture.FIST, timestamp=0.2))

    def test_sustained_none_releases_held_fist(self):
        mapper = ActionMapper(
            actions_enabled=False,
            cooldown_ms=0,
            fist_release_ms=250,
        )
        self.assertIsNotNone(mapper.handle(Gesture.FIST, timestamp=0.0))
        mapper.handle(Gesture.NONE, timestamp=0.1)
        mapper.handle(Gesture.NONE, timestamp=0.4)
        self.assertIsNotNone(mapper.handle(Gesture.FIST, timestamp=0.5))

    def test_opposite_zoom_directions_share_cooldown(self):
        mapper = ActionMapper(actions_enabled=False, cooldown_ms=800)
        self.assertIsNotNone(mapper.handle(Gesture.ZOOM_IN, timestamp=0.0))
        self.assertIsNone(mapper.handle(Gesture.ZOOM_OUT, timestamp=0.1))
        self.assertIsNotNone(mapper.handle(Gesture.ZOOM_OUT, timestamp=0.9))

    def test_opposite_swipe_directions_share_cooldown(self):
        mapper = ActionMapper(actions_enabled=False, cooldown_ms=800)
        self.assertIsNotNone(mapper.handle(Gesture.SWIPE_LEFT, timestamp=0.0))
        self.assertIsNone(mapper.handle(Gesture.SWIPE_RIGHT, timestamp=0.1))

    def test_swipe_directions_map_to_matching_arrow_keys(self):
        mapper = ActionMapper(actions_enabled=False, cooldown_ms=0)
        previous = mapper.handle(Gesture.SWIPE_LEFT, timestamp=0.0)
        following = mapper.handle(Gesture.SWIPE_RIGHT, timestamp=0.1)
        self.assertEqual(previous.command.arguments, ("left",))
        self.assertEqual(previous.command.description, "previous page")
        self.assertEqual(following.command.arguments, ("right",))
        self.assertEqual(following.command.description, "next page")

    def test_opposite_scroll_directions_share_cooldown(self):
        mapper = ActionMapper(actions_enabled=False, cooldown_ms=800)
        self.assertIsNotNone(mapper.handle(Gesture.SCROLL_UP, timestamp=0.0))
        self.assertIsNone(mapper.handle(Gesture.SCROLL_DOWN, timestamp=0.1))

    def test_point_has_no_os_action(self):
        mapper = ActionMapper(actions_enabled=False)
        self.assertIsNone(mapper.handle(Gesture.POINT, timestamp=0.0))


if __name__ == "__main__":
    unittest.main()
