# Gesture integration review — 9 September 2026

The reviewed checkout matched `origin/feature/pyautogui` at `c654124` after fetching. The original 43 tests passed. They largely used isolated synthetic poses; many explicitly disabled smoothing and settling, so they could not establish live-camera reliability.

## Confirmed defects and fixes

| Finding | Reproduction / consequence | Change |
|---|---|---|
| Distal finger joint ignored | A hooked middle fingertip still passed MCP/PIP/tip straightness and made an index point scroll | Check the DIP joint in both image and depth geometry |
| Conflicting 2D/3D finger rules | Ring/pinky extended toward camera were considered folded by the 2D control rule, causing an open hand to scroll | Require agreement with depth extension and positive folded-finger evidence |
| Degenerate landmarks classified as fist | Collapsed landmarks could send Space after arming | Reject duplicate, missing, nonfinite, fractional-ID and collapsed input; revoke control on invalid tracking |
| Stillness reapplied throughout a held pose | Hand translation beyond 10% of a palm width repeatedly restarted the timer | Apply stillness on entry; keep the same accepted direction active |
| Mapper state survived loss/pose changes | Scroll could resume after hand loss or a point pose without another palm | Shared controller resets classifier and mapper on tracking loss; pose changes end consumed sessions |
| Pinch zoom treated as one shot | Every zoom step required a new palm | Keep a pinch session active for zoom in/out, subject to cooldown |
| Real actions paused capture | PyAutoGUI's default 100 ms delay ran synchronously on every command | Skip the post-call sleep; retain fail-safe checks and explicit cooldowns |
| Webcam used IMAGE mode | Each frame was independently detected; tracking confidence was not wired to its intended option | Use VIDEO mode, increasing timestamps and actual tracking confidence; preserve subpixel coordinates |
| Error recovery resumed OS input | An execution exception left live controls enabled | Disable OS actions and reset the gate after an execution error |

Also added a 150 ms fist dwell to reject brief fist-like transitions, a 500 ms frame-gap reset, and detection of two hands so controls pause instead of selecting an arbitrary result. Short uncertain classifications pause commands immediately; an established interaction gets up to 350 ms to recover. No-hand detection resets immediately.

## Why fist can still move a browser page

Fist intentionally maps to **Space**. A normal page can interpret Space as page-down; a focused video player can interpret it as play/pause. This is target-application behavior. The gesture engine cannot infer which page element should receive Space from hand landmarks.

The overlay now includes the actual command arguments. If it says `play or pause ('space',)` while the page moves, focus the player and retry. If it says `scroll down (-1,)` while only pointing, record a trace: that is a recognition/control issue.

The same limitation applies to Left/Right: those keys work for slide navigation in supporting viewers, but do not universally navigate browser history or links. PyAutoGUI is system input; no hosted test website is required.

## Verification performed

- Original tests retained; the isolated-pose helper explicitly disables the new fist dwell.
- 69 tests passed, covering geometry regressions, production debounce/smoothing, 10/15/30/60 FPS transitions, mirrored and rotated hands, scaled/noisy index points, one-shot actions, repeated/reversed pinch zoom, hand loss, multiple hands, malformed input, OS failures, video-tracker wiring, application cleanup, and trace replay.
- The actual installed MediaPipe model initialized in VIDEO mode and processed 20 generated blank frames with no hands. Median processing time in that smoke run was approximately 10.7 ms. This is not a live-hand recognition or webcam frame-rate benchmark.
- No OS keyboard/scroll commands were sent during automated tests. Live-action tests used injected or mocked executors.

Synthetic fixtures cannot establish accuracy across real users, occlusion, lighting, camera angles, or noisy MediaPipe predictions. No failing recording from the reported session was available. These fixes address reproduced code defects; the exact cause of that session remains unconfirmed.

## Meeting test procedure

1. Start in dry run and record a fresh trace: `python main.py --trace recordings/person1-test1.jsonl`.
2. Use one hand. Hold open palm until `READY`, then hold an index-only point for five seconds. Repeat pointing toward the camera and slowly moving around the frame. Expect no commands.
3. Open and close the hand slowly, then quickly, at least ten times. Expect no wheel-scroll commands. A deliberate held fist after arming should produce one Space; an already consumed action needs a new palm.
4. Arm again, hold two fingers vertically up/down with ring/pinky folded, and move the hand slightly after scrolling starts. Expect regular scroll steps. Release to point: commands must stop. Show palm before changing direction.
5. Try left/right and upper diagonals for one page action each. Hold the pose for several seconds: no extra page actions. Check both hands against the mirrored preview.
6. Arm, pinch thumb/index with the other fingers folded, then spread and close several times. Expect zoom in/out steps. Open the hand to end the session.
7. During scroll, remove the hand or introduce a second hand. Expect an immediate pause/reset and no resumed commands until another open palm.
8. Repeat with each teammate, several distances, normal and dim lighting, and the actual demonstration camera. Keep the whole hand visible. Record expected versus actual behavior and approximate timestamps for failures.
9. Enable real actions and repeat against the intended slide viewer and a **focused** video player. Check wheel direction/pacing, page shortcuts and Space separately. Check the fail-safe: after an execution error, the overlay must remain in dry run. Restart to re-enable after moving the pointer away from the corner.
10. Replay any failure with `python -m scripts.replay_gestures recordings/person1-test1.jsonl`. Replay never sends OS input. With unchanged code/settings it should report zero label/action differences; compare a future fix against the same trace.

If your `.env` includes the old `SCROLL_COOLDOWN_MS=220`, try `SCROLL_COOLDOWN_MS=60` and `SCROLL_AMOUNT=1`. Actual scroll distance depends on OS/app wheel settings. Keep `DIRECTION_SETTLE_MS=220` and `OPEN_PALM_HOLD_MS=120` initially.

Current code uses static two-finger page/scroll controls. The original project Word documents specify swipes/open-palm motion; that existing scope difference needs agreement for the final submission.

## Reference material checked

- [MediaPipe Hand Landmarker Python guide](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/python): VIDEO mode and tracking configuration.
- [PyAutoGUI documentation](https://pyautogui.readthedocs.io/en/latest/index.html): default 0.1-second pause and fail-safe behavior. The installed 0.9.54 source also confirms `_pause=False` skips the post-call sleep while retaining the wrapper's fail-safe check.
- [Firefox media keyboard controls](https://support.mozilla.org/en-US/kb/html5-audio-and-video-firefox): media needs focus for keyboard playback control.
- [Mozilla keyboard shortcut reference](https://www-archive.mozilla.org/docs/end-user/moz_shortcuts.html): Space as page-down in page viewing.
