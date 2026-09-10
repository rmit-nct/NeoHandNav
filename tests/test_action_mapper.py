from __future__ import annotations

import unittest

from backend.action_mapper import ActionMapper
from backend.gesture_classifier import Gesture


class ActionMapperTests(unittest.TestCase):
    def test_browser_navigation_default_uses_platform_history_shortcuts(self):
        from unittest.mock import patch
        for system,modifier in (('Windows','alt'),('Linux','alt'),('Darwin','command')):
            with patch('backend.action_mapper.platform.system',return_value=system):
                mapper=ActionMapper(require_open_palm=False,cooldown_ms=0)
                for pose,key,label in ((Gesture.PREVIOUS_PAGE,'left','browser back'),(Gesture.NEXT_PAGE,'right','browser forward')):
                    command=mapper.commands[pose]
                    self.assertEqual((command.kind,command.arguments,command.description),('hotkey',(modifier,key),label))

    def test_invalid_navigation_target_is_rejected(self):
        with self.assertRaises(ValueError): ActionMapper(navigation_target='guess')

    @staticmethod
    def legacy_mapper(**overrides) -> ActionMapper:
        """Build a mapper without the application-level palm gate."""

        settings = {"require_open_palm": False, "navigation_target": "slides"}
        settings.update(overrides)
        return ActionMapper(**settings)

    @staticmethod
    def arm(mapper: ActionMapper, timestamp: float = 0.0) -> None:
        mapper.handle(Gesture.OPEN_PALM, timestamp=timestamp)
        mapper.handle(Gesture.OPEN_PALM, timestamp=timestamp + 0.13)

    def test_dry_run_returns_action_without_executing(self):
        executed = []
        mapper = self.legacy_mapper(
            actions_enabled=False,
            executor=executed.append,
        )

        result = mapper.handle(Gesture.NEXT_PAGE, timestamp=0.0)

        self.assertIsNotNone(result)
        self.assertFalse(result.executed)
        self.assertEqual(result.command.description, "next page")
        self.assertEqual(executed, [])

    def test_enabled_mapper_executes_after_scroll_cooldown(self):
        executed = []
        mapper = self.legacy_mapper(
            actions_enabled=True,
            cooldown_ms=800,
            scroll_cooldown_ms=150,
            executor=executed.append,
        )

        self.assertIsNotNone(mapper.handle(Gesture.SCROLL_UP, timestamp=0.0))
        self.assertIsNone(mapper.handle(Gesture.SCROLL_UP, timestamp=0.1))
        self.assertIsNotNone(mapper.handle(Gesture.SCROLL_UP, timestamp=0.2))
        self.assertEqual(len(executed), 2)

    def test_page_directions_map_to_matching_arrow_keys(self):
        mapper = self.legacy_mapper(actions_enabled=False, cooldown_ms=0)

        previous = mapper.handle(Gesture.PREVIOUS_PAGE, timestamp=0.0)
        following = mapper.handle(Gesture.NEXT_PAGE, timestamp=0.1)

        self.assertEqual(previous.command.arguments, ("left",))
        self.assertEqual(previous.command.description, "previous page")
        self.assertEqual(following.command.arguments, ("right",))
        self.assertEqual(following.command.description, "next page")

    def test_old_swipe_names_remain_compatible_aliases(self):
        mapper = self.legacy_mapper(actions_enabled=False, cooldown_ms=0)

        previous = mapper.handle(Gesture.SWIPE_LEFT, timestamp=0.0)
        following = mapper.handle(Gesture.SWIPE_RIGHT, timestamp=0.1)

        self.assertEqual(previous.command.arguments, ("left",))
        self.assertEqual(following.command.arguments, ("right",))

    def test_point_has_no_os_action(self):
        mapper = self.legacy_mapper(actions_enabled=False)
        self.assertIsNone(mapper.handle(Gesture.POINT, timestamp=0.0))

    def test_open_palm_is_required_before_first_action(self):
        mapper = ActionMapper(actions_enabled=False, cooldown_ms=0)

        self.assertEqual(mapper.control_status, "SHOW OPEN PALM")
        self.assertIsNone(mapper.handle(Gesture.NEXT_PAGE, timestamp=0.0))

        self.arm(mapper, timestamp=0.1)
        self.assertEqual(mapper.control_status, "READY")
        self.assertIsNotNone(mapper.handle(Gesture.NEXT_PAGE, timestamp=0.3))

    def test_open_palm_itself_is_debounced(self):
        mapper = ActionMapper(
            actions_enabled=False,
            cooldown_ms=0,
            open_palm_hold_ms=120,
        )

        mapper.handle(Gesture.OPEN_PALM, timestamp=0.0)
        self.assertEqual(mapper.control_status, "SHOW OPEN PALM")
        self.assertIsNone(mapper.handle(Gesture.NEXT_PAGE, timestamp=0.1))

        self.arm(mapper, timestamp=0.2)
        self.assertEqual(mapper.control_status, "READY")

    def test_page_pose_is_one_shot_until_another_open_palm(self):
        mapper = ActionMapper(actions_enabled=False, cooldown_ms=0)
        self.arm(mapper)

        first = mapper.handle(Gesture.NEXT_PAGE, timestamp=0.2)
        held = mapper.handle(Gesture.NEXT_PAGE, timestamp=1.0)
        switched = mapper.handle(Gesture.PREVIOUS_PAGE, timestamp=1.1)

        self.assertIsNotNone(first)
        self.assertIsNone(held)
        self.assertIsNone(switched)
        self.assertEqual(mapper.control_status, "SHOW OPEN PALM")

        self.arm(mapper, timestamp=1.2)
        self.assertIsNotNone(
            mapper.handle(Gesture.PREVIOUS_PAGE, timestamp=1.4)
        )

    def test_held_scroll_pose_repeats_at_scroll_interval(self):
        mapper = ActionMapper(
            actions_enabled=False,
            cooldown_ms=800,
            scroll_cooldown_ms=150,
        )
        self.arm(mapper)

        first = mapper.handle(Gesture.SCROLL_UP, timestamp=0.2)
        early = mapper.handle(Gesture.SCROLL_UP, timestamp=0.3)
        repeated = mapper.handle(Gesture.SCROLL_UP, timestamp=0.4)

        self.assertIsNotNone(first)
        self.assertIsNone(early)
        self.assertIsNotNone(repeated)
        self.assertEqual(mapper.control_status, "ACTIVE: Scroll Up")

    def test_scroll_direction_cannot_change_without_open_palm(self):
        mapper = ActionMapper(
            actions_enabled=False,
            cooldown_ms=0,
            scroll_cooldown_ms=0,
        )
        self.arm(mapper)

        self.assertIsNotNone(
            mapper.handle(Gesture.SCROLL_UP, timestamp=0.2)
        )
        self.assertIsNone(
            mapper.handle(Gesture.SCROLL_DOWN, timestamp=0.3)
        )
        self.assertEqual(mapper.control_status, "SHOW OPEN PALM")

        self.arm(mapper, timestamp=0.4)
        self.assertIsNotNone(
            mapper.handle(Gesture.SCROLL_DOWN, timestamp=0.6)
        )

    def test_first_palm_frame_stops_scroll_but_does_not_rearm(self):
        mapper = ActionMapper(
            actions_enabled=False,
            cooldown_ms=0,
            scroll_cooldown_ms=0,
            open_palm_hold_ms=120,
        )
        self.arm(mapper)
        mapper.handle(Gesture.SCROLL_UP, timestamp=0.2)

        mapper.handle(Gesture.OPEN_PALM, timestamp=0.3)

        self.assertEqual(mapper.control_status, "SHOW OPEN PALM")
        self.assertIsNone(mapper.handle(Gesture.NEXT_PAGE, timestamp=0.4))

    def test_fist_is_one_shot_and_requires_new_open_palm(self):
        executed = []
        mapper = ActionMapper(
            actions_enabled=True,
            cooldown_ms=0,
            executor=executed.append,
        )
        self.arm(mapper)

        self.assertIsNotNone(mapper.handle(Gesture.FIST, timestamp=0.2))
        self.assertIsNone(mapper.handle(Gesture.FIST, timestamp=1.0))
        self.arm(mapper, timestamp=1.1)
        self.assertIsNotNone(mapper.handle(Gesture.FIST, timestamp=1.3))
        self.assertEqual(len(executed), 2)

    def test_invalid_open_palm_hold_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "open_palm_hold_ms"):
            ActionMapper(open_palm_hold_ms=-1)


if __name__ == "__main__":
    unittest.main()
