import math
import random
import unittest
from unittest.mock import Mock, patch

from backend.action_mapper import ActionMapper
from backend.gesture_classifier import Gesture, GestureClassifier
from backend.gesture_controller import GestureController
from backend.pointer_controller import PointerController, PointerSettings
from tests.test_gesture_classifier import copy_hand, fist_hand, point_hand, pinch_hand, two_finger_hand, translated


def thumb_hand(down=False, mirror=False):
    hand = fist_hand()
    for i, xy in ((2,(55,160)), (3,(55,115)), (4,(55,65))):
        hand[i][1:3] = xy
    for lm in hand:
        if down:
            lm[1], lm[2] = 200-lm[1], 440-lm[2]
        if mirror:
            lm[1] = 640-lm[1]
    return hand


class ThumbTests(unittest.TestCase):
    def test_thumbs_are_distinct_from_fists_for_both_hands(self):
        for down in (False,True):
            for mirror in (False,True):
                with self.subTest(down=down,mirror=mirror):
                    classifier = GestureClassifier()
                    for i in range(20):
                        result = classifier.classify(thumb_hand(down,mirror), i/30, 640)
                    self.assertEqual(result.gesture, Gesture.THUMBS_DOWN if down else Gesture.THUMBS_UP)

    def test_thumb_never_sends_space_in_navigation(self):
        commands=[]
        c=GestureController(GestureClassifier(),ActionMapper(actions_enabled=True,executor=commands.append))
        for i in range(15): c.process([copy_hand()],i/30,640)
        for i in range(15,75): c.process([thumb_hand()],i/30,640)
        self.assertEqual(commands,[])


class PointerTests(unittest.TestCase):
    def setUp(self):
        self.pointer = PointerController((1920,1080))
        self.now = 0.
        self.commands=[]

    def hold(self, gesture, seconds, fps=30, hand=None):
        for _ in range(round(seconds*fps)):
            command=self.pointer.process(gesture,hand or point_hand(),self.now,(640,480))
            if command: self.commands.append(command)
            self.now+=1/fps

    def clicks(self):
        return [c for c in self.commands if c.kind=='click']

    def test_point_moves_without_open_palm_and_never_clicks(self):
        self.hold(Gesture.POINT,1.)
        self.assertTrue(any(c.kind=='move' for c in self.commands))
        self.assertEqual(self.clicks(),[])

    def test_single_click_only_on_return_to_point_at_frozen_target(self):
        self.hold(Gesture.POINT,.6)
        target=self.pointer.position
        self.commands=[]
        self.hold(Gesture.THUMBS_UP,.35)
        self.assertEqual(self.commands,[])
        self.hold(Gesture.NONE,.067)
        self.hold(Gesture.POINT,1/30)
        self.assertEqual(self.clicks()[0].arguments,(*target,1,'left'))

    def test_double_click_sends_no_speculative_single_click(self):
        self.hold(Gesture.POINT,.6)
        self.hold(Gesture.THUMBS_UP,3.)
        self.hold(Gesture.POINT,.2)
        self.assertEqual([c.arguments[2] for c in self.clicks()],[2])

    def test_click_duration_consistent_across_frame_rates(self):
        for fps in (10,15,30,60):
            with self.subTest(fps=fps):
                self.setUp()
                self.hold(Gesture.POINT,.6,fps)
                self.hold(Gesture.THUMBS_UP,.4,fps)
                self.hold(Gesture.POINT,.3,fps)
                self.assertEqual([c.arguments[2] for c in self.clicks()],[1])

    def test_short_thumb_glitch_does_not_click(self):
        self.hold(Gesture.POINT,.6)
        self.hold(Gesture.THUMBS_UP,.1)
        self.hold(Gesture.POINT,.2)
        self.assertEqual(self.clicks(),[])

    def test_thumb_can_double_click_current_cursor_without_recent_point(self):
        target = self.pointer.position
        self.hold(Gesture.THUMBS_UP,2.)
        self.assertEqual([c.arguments for c in self.clicks()], [(*target,2,'left')])

    def test_thumb_can_single_click_current_cursor_without_recent_point(self):
        target = self.pointer.position
        self.hold(Gesture.THUMBS_UP,.4)
        self.hold(Gesture.POINT,1/30)
        self.assertEqual([c.arguments for c in self.clicks()], [(*target,1,'left')])

    def test_slow_transition_to_thumb_keeps_the_cursor_target(self):
        self.hold(Gesture.POINT,.6)
        target = self.pointer.position
        self.hold(Gesture.NONE,.7)
        self.hold(Gesture.THUMBS_UP,.4)
        self.hold(Gesture.POINT,1/30)
        self.assertEqual([c.arguments for c in self.clicks()], [(*target,1,'left')])

    def test_short_transitional_fist_does_not_toggle_playback(self):
        self.hold(Gesture.POINT,.6)
        self.hold(Gesture.FIST,.3)
        self.hold(Gesture.THUMBS_UP,.4)
        self.hold(Gesture.POINT,.1)
        self.assertFalse(any(c.kind=='key' for c in self.commands))
        self.assertEqual(len(self.clicks()),1)

    def test_fist_toggles_once_and_needs_a_deliberate_release(self):
        for fps in (10,15,30,60):
            with self.subTest(fps=fps):
                self.setUp()
                self.hold(Gesture.FIST,3.,fps)
                self.hold(Gesture.NONE,.2,fps)
                self.hold(Gesture.FIST,1.,fps)
                self.assertEqual([c.arguments for c in self.commands],[('playpause',)])
                self.hold(Gesture.OPEN_PALM,.3,fps)
                self.hold(Gesture.FIST,1.,fps)
                self.assertEqual([c.arguments for c in self.commands],[('playpause',)]*2)

    def test_unknown_frames_do_not_count_toward_fist_hold(self):
        self.hold(Gesture.FIST,.3)
        self.hold(Gesture.NONE,.6)
        self.hold(Gesture.FIST,.2)
        self.assertEqual(self.commands,[])
        self.hold(Gesture.FIST,.3)
        self.assertEqual([c.arguments for c in self.commands],[('playpause',)])

    def test_holding_click_or_fist_after_tracking_reset_does_not_repeat(self):
        for gesture in (Gesture.THUMBS_UP,Gesture.FIST):
            self.setUp()
            self.hold(gesture,2.)
            self.pointer.reset()
            self.hold(gesture,2.)
            self.hold(Gesture.NONE,1.2)
            self.hold(gesture,2.)
            self.assertEqual(len(self.commands),1)

    def test_unfinished_fist_restarts_full_hold_after_tracking_reset(self):
        for fps in (10,15,30,60):
            with self.subTest(fps=fps):
                self.setUp()
                self.hold(Gesture.FIST,.3,fps)
                self.pointer.reset()
                self.hold(Gesture.FIST,.3,fps)
                self.assertEqual(self.commands,[])
                self.hold(Gesture.FIST,.8,fps)
                self.assertEqual([c.arguments for c in self.commands],[('playpause',)])
                self.pointer.reset()
                self.hold(Gesture.FIST,1.,fps)
                self.assertEqual(len(self.commands),1)

    def test_unfinished_fist_recovers_after_long_uncertainty(self):
        self.hold(Gesture.FIST,.3)
        self.hold(Gesture.NONE,1.)
        self.hold(Gesture.FIST,.3)
        self.assertEqual(self.commands,[])
        self.hold(Gesture.FIST,.8)
        self.assertEqual([c.arguments for c in self.commands],[('playpause',)])

    def test_cancelled_thumb_cannot_restart_until_released(self):
        self.hold(Gesture.THUMBS_UP,.4)
        self.hold(Gesture.NONE,1.)
        self.hold(Gesture.THUMBS_UP,2.)
        self.assertEqual(self.commands,[])
        self.hold(Gesture.POINT,.3)
        self.hold(Gesture.THUMBS_UP,1.2)
        self.assertEqual(len(self.clicks()),1)

    def test_palm_fist_or_pinch_cancel_a_pending_click(self):
        for neutral in (Gesture.OPEN_PALM,Gesture.FIST,Gesture.PINCH):
            self.setUp()
            self.hold(Gesture.POINT,.6)
            self.hold(Gesture.THUMBS_UP,.4)
            self.hold(neutral,.2)
            self.hold(Gesture.POINT,.2)
            self.assertEqual(self.clicks(),[])

    def test_long_unknown_gap_cancels_click(self):
        self.hold(Gesture.POINT,.6)
        self.hold(Gesture.THUMBS_UP,.4)
        self.hold(Gesture.NONE,1.)
        self.hold(Gesture.POINT,.3)
        self.assertEqual(self.clicks(),[])

    def test_frame_stall_cancels_click(self):
        self.hold(Gesture.POINT,.6)
        self.hold(Gesture.THUMBS_UP,.4)
        self.now+=2
        self.hold(Gesture.POINT,.3)
        self.assertEqual(self.clicks(),[])

    def test_backwards_timestamp_cancels_click(self):
        self.hold(Gesture.POINT,.6)
        self.hold(Gesture.THUMBS_UP,.4)
        self.now=0
        self.hold(Gesture.POINT,.3)
        self.assertEqual(self.clicks(),[])

    def test_right_click_is_explicit(self):
        self.hold(Gesture.POINT,.6)
        self.hold(Gesture.THUMBS_DOWN,.4)
        self.hold(Gesture.POINT,.3)
        self.assertEqual([c.arguments[2:] for c in self.clicks()],[(1,'right')])

    def test_switching_thumb_direction_cancels_click(self):
        self.hold(Gesture.POINT,.6)
        self.hold(Gesture.THUMBS_UP,.4)
        self.hold(Gesture.THUMBS_DOWN,.4)
        self.hold(Gesture.POINT,.3)
        self.assertEqual(self.clicks(),[])

    def test_mapped_cursor_stays_inside_monitor_away_from_failsafe_corners(self):
        for x,y in ((-100,-100),(2000,2000)):
            hand=point_hand(); hand[8][1:3]=[x,y]
            self.hold(Gesture.POINT,2,hand=hand)
            px,py=self.pointer.position
            self.assertTrue(2<=px<=1917 and 2<=py<=1077)

    def test_physical_mouse_takes_priority_and_cancels_click(self):
        self.hold(Gesture.POINT,.6)
        self.hold(Gesture.THUMBS_UP,.4)
        self.pointer.physical_pointer_moved((1000,700))
        count=len(self.commands)
        self.hold(Gesture.POINT,.5)
        self.assertEqual(len(self.commands),count)
        self.assertEqual(self.clicks(),[])
        self.hold(Gesture.OPEN_PALM,.1)
        self.hold(Gesture.POINT,.4)
        self.assertGreater(len(self.commands),count)

    def test_pointer_cannot_bypass_navigation_gate_for_scroll(self):
        self.hold(Gesture.SCROLL_UP,1.)
        self.assertEqual(self.commands,[])
        self.hold(Gesture.FIST,.5)
        self.assertEqual(self.commands,[])

    def test_invalid_settings_rejected(self):
        for kwargs in ({'margin':.5},{'min_cutoff':float('nan')},{'double_click_hold_seconds':.1},
                       {'scroll_amount':1.5},{'transition_grace_seconds':0},{'fist_hold_seconds':0}):
            with self.assertRaises(ValueError): PointerSettings(**kwargs)

    def test_sparse_two_finger_detections_cannot_accumulate_into_click(self):
        self.hold(Gesture.POINT,.6)
        for _ in range(12):
            self.hold(Gesture.TWO_FINGER_CLICK,1/30)
            self.hold(Gesture.NONE,.2)
        self.assertEqual(self.clicks(),[])
        self.hold(Gesture.TWO_FINGER_CLICK,.5)
        self.assertEqual(len(self.clicks()),1)

    def test_click_confirmation_window_is_validated(self):
        with self.assertRaises(ValueError): PointerSettings(click_confirmation_window_seconds=.1)

    def test_invalid_input_rejected(self):
        with self.assertRaises(ValueError): self.pointer.process(Gesture.POINT,point_hand(),float('inf'),(640,480))

    def test_stationary_noise_is_smoothed_without_drifting_outside_target(self):
        rng=random.Random(37)
        positions=[]
        for _ in range(180):
            hand=point_hand(); hand[8][1:3]=[320+rng.uniform(-2,2),240+rng.uniform(-2,2)]
            self.hold(Gesture.POINT,1/30,hand=hand)
            positions.append(self.pointer.position)
        # Raw 4-pixel camera jitter spans about 17 screen pixels with this ROI.
        xs=[p[0] for p in positions[-60:]]
        self.assertLess(max(xs)-min(xs),12)

    def test_bad_initial_cursor_is_rejected(self):
        with self.assertRaises(ValueError): PointerController(initial_position=(float('nan'),0))


class MousePipelineTests(unittest.TestCase):
    def test_oblique_middle_finger_clicks_without_strict_2d_direction_pose(self):
        for tip in ((136,63),(149,65)):
            for fps in (10,15,30,60):
                for mirror in (False,True):
                    with self.subTest(tip=tip,fps=fps,mirror=mirror):
                        hand=two_finger_hand()
                        hand[10][1:3]=[95,110]
                        hand[11][1:3]=[118,82]
                        hand[12][1:3]=tip
                        aim=point_hand()
                        if mirror:
                            for pose in (hand,aim):
                                for lm in pose: lm[1]=640-lm[1]
                        strict=GestureClassifier()
                        for i in range(fps): old=strict.classify(hand,i/fps,640)
                        self.assertNotIn(old.gesture,(Gesture.TWO_FINGER,Gesture.SCROLL_UP))
                        _,commands=self.run_sequence(((aim,1.),(hand,2.)),fps)
                        self.assertEqual([c.arguments[2:] for c in commands if c.kind=='click'],[(1,'left')])
                        self.assertFalse(any(c.kind in ('hotkey','scroll','key') for c in commands))

    def test_click_survives_isolated_unknown_frames_without_consecutive_frame_gate(self):
        commands=[]
        c=GestureController(GestureClassifier(),ActionMapper(actions_enabled=True,executor=commands.append),mode='mouse')
        for i in range(30): c.process([point_hand()],i/30,640,480)
        for i in range(30,90):
            hand=copy_hand() if i%3==0 else two_finger_hand()
            c.process([hand],i/30,640,480)
        self.assertEqual(len([x for x in commands if x.kind=='click']),1)
        self.assertFalse(any(x.kind in ('key','hotkey','scroll') for x in commands))

    def test_relaxed_click_rule_rejects_hooked_middle_and_extra_extended_fingers(self):
        hooked=two_finger_hand(); hooked[11][1:3]=[95,65]; hooked[12][1:3]=[115,105]
        for pose in (hooked,point_hand(),copy_hand(),fist_hand(),thumb_hand(),pinch_hand()):
            classifier=GestureClassifier()
            for i in range(30):
                result=classifier.classify(pose,i/30,640,click_context=True)
                self.assertIsNot(result.gesture,Gesture.TWO_FINGER_CLICK)

    def test_opening_from_point_to_palm_does_not_click(self):
        for fps in (10,15,30,60):
            for seconds in (.3,.6,1.,2.):
                with self.subTest(fps=fps,seconds=seconds):
                    start,end=point_hand(),copy_hand()
                    steps=round(fps*seconds)
                    poses=[(start,1.)]
                    for step in range(1,steps+1):
                        hand=[[a[0],*[x+(y-x)*step/steps for x,y in zip(a[1:],b[1:])]]
                              for a,b in zip(start,end)]
                        poses.append((hand,1/fps))
                    _,commands=self.run_sequence(poses,fps)
                    self.assertFalse(any(x.kind=='click' for x in commands))

    def run_sequence(self, poses, fps=30):
        commands=[]
        c=GestureController(GestureClassifier(),ActionMapper(actions_enabled=True,executor=commands.append,
                            scroll_cooldown_ms=60,scroll_amount=1,play_pause_key='playpause'),mode='mouse')
        i=0
        for hand,seconds in poses:
            for _ in range(round(seconds*fps)):
                c.process([] if hand is None else [hand],i/fps,640,480); i+=1
        return c,commands

    def test_point_then_two_fingers_clicks_once_in_every_direction(self):
        for fps in (10,15,30,60):
            for direction in ((0,-1),(0,1),(-1,0),(1,0)):
                with self.subTest(fps=fps,direction=direction):
                    aim=translated(point_hand(),265,220)
                    _, commands=self.run_sequence(((aim,1.),(two_finger_hand(direction),3.)),fps)
                    clicks=[c for c in commands if c.kind=='click']
                    self.assertEqual(len(clicks),1)
                    self.assertEqual(clicks[0].arguments[2:],(1,'left'))
                    self.assertFalse(any(c.kind in ('key','scroll','hotkey') for c in commands))
                    target=[c.arguments for c in commands if c.kind=='move'][-1]
                    self.assertEqual(clicks[0].arguments[:2],target)

    def test_two_finger_without_point_or_palm_does_nothing(self):
        _,commands=self.run_sequence(((two_finger_hand(),3.),))
        self.assertEqual(commands,[])

    def test_open_palm_selects_scroll_and_point_selects_click(self):
        c,commands=self.run_sequence(((copy_hand(),.5),(two_finger_hand(),1.),
                                     (point_hand(),.7),(two_finger_hand(),2.)))
        self.assertTrue(any(x.kind=='scroll' for x in commands))
        self.assertEqual([x.arguments[2:] for x in commands if x.kind=='click'],[(1,'left')])
        click_index=next(i for i,x in enumerate(commands) if x.kind=='click')
        self.assertFalse(any(x.kind=='scroll' for x in commands[click_index:]))
        self.assertEqual(c.control_status,'Single click finished; fold middle finger to point again')

    def test_two_finger_can_click_again_only_after_pointing(self):
        _,commands=self.run_sequence(((point_hand(),.7),(two_finger_hand(),1.),
                                     (point_hand(),.7),(two_finger_hand(),1.)))
        self.assertEqual(len([c for c in commands if c.kind=='click']),2)

    def test_hand_loss_between_point_and_two_fingers_revokes_click_context(self):
        _,commands=self.run_sequence(((point_hand(),1.),(None,.1),(two_finger_hand(),2.)))
        self.assertFalse(any(c.kind!='move' for c in commands))

    def test_partial_middle_extension_freezes_before_classifier_reports_two_fingers(self):
        c=GestureController(GestureClassifier(),ActionMapper(),mode='mouse')
        aim=translated(point_hand(),245,200)
        for i in range(30): c.process([aim],i/30,640,480)
        target=c.pointer.position
        opened=translated(two_finger_hand(),245,200)
        frozen_while_point=False
        # Gradually unfold only the middle finger; then deliberately displace
        # the index tip while classification still sees a partial pointing pose.
        for step in range(1,31):
            hand=copy_hand(aim)
            for lm_id in (10,11,12):
                hand[lm_id][1:4]=[a+(b-a)*step/30 for a,b in zip(aim[lm_id][1:4],opened[lm_id][1:4])]
            result,action=c.process([hand],(29+step)/30,640,480)
            if c.pointer._pointer_frozen and result.gesture is Gesture.POINT:
                frozen_while_point=True
                shifted=translated(hand,30,20)
                _,moved=c.process([shifted],(29+step+.1)/30,640,480)
                self.assertIsNone(moved)
                self.assertEqual(c.pointer.position,target)
        self.assertTrue(frozen_while_point)

    def test_classification_delay_at_low_fps_does_not_block_clicks(self):
        for fps in (10,15,30,60):
            with self.subTest(fps=fps):
                commands=[]
                c=GestureController(GestureClassifier(),ActionMapper(actions_enabled=True,executor=commands.append),mode='mouse')
                i=0
                for hand,frames in ((point_hand(),fps),(thumb_hand(),round(fps*.5)),(point_hand(),fps)):
                    for _ in range(frames):
                        c.process([hand],i/fps,640,480);i+=1
                self.assertEqual([x.arguments[2] for x in commands if x.kind=='click'],[1])

    def test_real_pose_sequence_clicks_and_mode_switch_cancels(self):
        for switch in (False,True):
            commands=[]
            c=GestureController(GestureClassifier(),ActionMapper(actions_enabled=True,executor=commands.append),mode='mouse')
            i=0
            for hand,frames in ((point_hand(),20),(thumb_hand(),12),(point_hand(),12)):
                if switch and i==32: c.set_mode('navigation')
                for _ in range(frames):
                    c.process([hand],i/30,640,480); i+=1
            clicks=[x for x in commands if x.kind=='click']
            self.assertEqual(len(clicks),0 if switch else 1)
            self.assertFalse(any(x.kind=='key' for x in commands))

    def test_tracking_loss_and_pause_cancel_pending_clicks(self):
        for interrupt in ('missing','two_hands','invalid','pause','disable'):
            commands=[]
            c=GestureController(GestureClassifier(),ActionMapper(actions_enabled=True,executor=commands.append),mode='mouse')
            for i in range(20): c.process([point_hand()],i/30,640,480)
            for i in range(20,32): c.process([thumb_hand()],i/30,640,480)
            if interrupt=='missing': c.process([],32/30,640,480)
            elif interrupt=='two_hands': c.process([thumb_hand(),thumb_hand()],32/30,640,480)
            elif interrupt=='invalid': c.process([[]],32/30,640,480)
            elif interrupt=='pause': c.set_paused(True); c.set_paused(False)
            else: c.set_actions_enabled(False); c.set_actions_enabled(True)
            for i in range(33,45): c.process([point_hand()],i/30,640,480)
            self.assertFalse(any(x.kind=='click' for x in commands),interrupt)

    def test_pinch_still_requires_palm_before_zoom_in_mouse_mode(self):
        commands=[]
        c=GestureController(GestureClassifier(),ActionMapper(actions_enabled=True,executor=commands.append),mode='mouse')
        for i in range(15): c.process([pinch_hand()],i/30,640,480)
        hand=pinch_hand(); hand[4][1]=30
        for i in range(15,40): c.process([hand],i/30,640,480)
        self.assertFalse(any(x.kind=='hotkey' for x in commands))

    def test_legacy_arrows_and_zoom_work_in_mouse_mode_after_palm(self):
        for fps in (10,15,30,60):
            for interaction in ('arrows','zoom'):
                with self.subTest(fps=fps,interaction=interaction):
                    commands=[]
                    c=GestureController(GestureClassifier(),ActionMapper(actions_enabled=True,executor=commands.append),mode='mouse')
                    spread=pinch_hand(); spread[4][1]=30
                    poses = ((two_finger_hand((1,0)),2.),) if interaction=='arrows' else ((pinch_hand(),.7),(spread,1.2),(pinch_hand(),1.2))
                    i=0
                    for hand,seconds in ((copy_hand(),.7),)+poses:
                        for _ in range(round(fps*seconds)):
                            c.process([hand],i/fps,640,480); i+=1
                    self.assertEqual([x.description for x in commands],
                                     ['browser forward'] if interaction=='arrows' else ['zoom in','zoom out'])

    def test_classified_fist_sends_configured_playback_key_in_mouse_mode(self):
        for fps in (10,15,30,60):
            for key in ('playpause','space','k'):
                with self.subTest(fps=fps,key=key):
                    commands=[]
                    c=GestureController(GestureClassifier(),ActionMapper(actions_enabled=True,executor=commands.append,play_pause_key=key),mode='mouse')
                    for i in range(fps*3): c.process([fist_hand()],i/fps,640,480)
                    self.assertEqual([x.arguments for x in commands],[(key,)])

    def test_bad_playback_key_is_rejected(self):
        with self.assertRaises(ValueError): ActionMapper(play_pause_key='unknown')

    def test_pyautogui_mouse_commands_include_coordinates_and_click_count(self):
        fake=Mock()
        with patch.dict('sys.modules',{'pyautogui':fake}), \
             patch.object(ActionMapper,'_double_click_interval',return_value=.1):
            from backend.action_mapper import ActionCommand
            ActionMapper._execute_with_pyautogui(ActionCommand('move',(100,200),'move'))
            ActionMapper._execute_with_pyautogui(ActionCommand('click',(100,200,2,'left'),'double'))
        fake.moveTo.assert_called_once_with(100,200,_pause=False)
        fake.click.assert_called_once_with(100,200,clicks=2,button='left',interval=.1,_pause=False)
        self.assertTrue(fake.FAILSAFE)

    def test_generated_double_click_respects_fast_windows_setting(self):
        fake=Mock()
        fake.windll.user32.GetDoubleClickTime.return_value=180
        with patch.dict('sys.modules',{'ctypes':fake}), \
             patch('backend.action_mapper.platform.system',return_value='Windows'):
            self.assertAlmostEqual(ActionMapper._double_click_interval(),.06)


if __name__=='__main__': unittest.main()
