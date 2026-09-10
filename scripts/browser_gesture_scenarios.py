"""Generate browser-test commands through the production gesture controller.

This program uses synthetic landmarks and DRY RUN only; no OS input or camera.
The optional Playwright checker consumes the JSON commands in its own browser.
"""

from dataclasses import asdict
import json
import sys

from backend.action_mapper import ActionMapper
from backend.gesture_classifier import GestureClassifier
from backend.gesture_controller import GestureController
from backend.pointer_controller import PointerController
from tests.test_gesture_classifier import copy_hand, fist_hand, point_hand, translated, two_finger_hand
from tests.test_pointer_controller import thumb_hand


def scenario(name, target, viewport):
    pointer = PointerController(viewport)
    controller = GestureController(GestureClassifier(), ActionMapper(
        actions_enabled=False, play_pause_key='playpause', scroll_amount=1,
        scroll_cooldown_ms=60), pointer, 'mouse')
    x = (target[0]/(viewport[0]-1)*.7+.15)*640
    y = (target[1]/(viewport[1]-1)*.7+.15)*480
    aim = translated(point_hand(), x-75, y-40)
    endings = {
        'single': ((two_finger_hand(), 2.),),
        'single_shake': ((translated(aim,18,10),2/30),(two_finger_hand(),2.)),
        'double': ((thumb_hand(), 2.),),
        'right': ((thumb_hand(down=True), .4), (aim, .1)),
        'scroll': ((copy_hand(), .5), (two_finger_hand((0,1)), .7)),
        'playback': ((fist_hand(), 2.),),
        'back': ((copy_hand(),.5),(two_finger_hand((-1,0)),2.)),
        'forward': ((copy_hand(),.5),(two_finger_hand((1,0)),2.)),
    }
    commands=[]
    frame=0
    for hand, seconds in ((aim,1.5),)+endings[name]:
        for _ in range(round(seconds*30)):
            _,action=controller.process([hand],frame/30,640,480)
            if action:
                assert not action.executed
                commands.append(asdict(action.command))
            frame+=1
    return commands


if __name__ == '__main__':
    print(json.dumps(scenario(**json.load(sys.stdin))))
