# Gesture integration review — 9 September 2026

## Fist playback follow-up — 11 September

The user confirmed `SENT: play or pause` while YouTube kept playing. That identifies delivery/player handling rather than an unfinished hold in this case. The local `.env` now selects `PLAY_PAUSE_KEY=k`, YouTube's player shortcut, instead of the Windows global media key. Explicit `k`/`space` playback commands prepare the window under the pointer before typing; a blocked target produces WAITING without a fallback toggle. This does not identify the active website or focus a video within a page: the user should focus the YouTube player first, avoiding an active search/comment text field. Other installations keep the existing media-key default.

Separately, an unfinished fist previously became consumed on tracking reset. It now restarts its complete dwell after recovery. Completed fists remain locked until a deliberate palm/point release, preventing double toggles. Status says `Fist completed` and refers to Last input instead of claiming a key was sent before execution. Regression tests cover interrupted and completed holds, target preparation ordering, and blocked playback without key emission. All 145 tests pass; the user's live YouTube playback remains unverified.

## Recognized scroll with no page movement — 10 September

Follow-up screenshot showed `ACTIVE: Scroll Down` and `SENT: scroll down (-1,)`. Inspection of the installed PyAutoGUI Windows `_scroll` implementation revealed that it passes the argument directly as raw `dwData`, without multiplying by WHEEL_DELTA. Thus the configured one-notch command was actually 1/120 of a notch. Windows delivery now uses `SendInput` with explicit `notches * 120`, verifies that the event was inserted, and preserves PyAutoGUI's fail-safe check. Other platforms retain PyAutoGUI scrolling. See [Microsoft's wheel-unit definition](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-mouse_event).

The improved native Chrome test measures wheel events, not merely nonzero page movement: the old one-unit pulse yielded about 1.04 CSS pixels and the corrected notch about 125, with correct signs in both directions. All 141 tests pass. This confirms a real delivery-unit bug; live gesture operation on YouTube Shorts still needs verification. The earlier focus fix remains in place, and click stabilization is unchanged.

The reported label is `Scroll Down`, so recognition alone does not establish that wheel input reached the page. Synthetic Point → Palm → Down sequences produce the same wheel commands with the pointer buffer enabled and disabled at 10/15/30/60 FPS. The buffer remains unchanged.

Windows scroll delivery now resolves the window under the actual pointer and requests foreground focus before sending the wheel. It never clicks to obtain focus or changes system settings. A pointer over HandNav, a missing target, or a refused focus request produces `WAITING` with an actionable reason, without disarming live input. The reason is also recorded in traces. This addresses a possible focus-related delivery failure; the user's exact failure has not been reproduced from a live trace.

Validation: 138 unit/integration tests pass, including mocked focus success/refusal, preview targeting, recovery, and no wheel emission when blocked. `node scripts/check_browser_input.cjs --desktop-scroll` also passed actual Windows PyAutoGUI down/up input in an isolated foreground Chrome page. The native check does not yet reproduce an inactive browser behind the camera preview; that focus path has mocked coverage.

To test: restart HandNav, point inside the browser's scrollable content, show palm until READY, then hold two fingers downward. `SENT` means input was emitted, not that the page necessarily moved (the page can already be at its bottom or the pointer can be over another scroll region). `WAITING` explains a target/focus problem; `SHOW OPEN PALM` means the gesture has not been armed.

## Transition-shake stabilization

The earlier target freeze started when a middle-finger opening signal or changed pose was observed. A hand shift just before that signal could already reach the OS cursor. The new pointer path buffers 100 ms of raw pointing positions, interpolated by timestamp, and discards the pending samples on a pose change, early opening signal, uncertainty, or reset. The click continues to use the actual visible cursor position; it does not silently rewind to a historical coordinate. A 2-pixel output deadzone suppresses tiny hover movements. Motion filters are re-seeded from the visible cursor and the newly observed raw input after a pause, avoiding an artificial velocity spike during resumption.

Settings are `POINTER_BUFFER_MS` (0–250, default 100) and `POINTER_DEADZONE_PX` (0–10, default 2). This trades roughly 100 ms of pointing latency for protection against brief transition tremor. It cannot remove every tremor or infer intent when movement begins earlier than the buffer. Existing traces without the new settings replay with buffering/deadzone disabled, matching their recorded pointer configuration.

Tests compare buffer-on and buffer-off runs of the same synthetic pre-click displacement at 10/15/30/60 FPS, plus discarded pending motion, intentional movement, stationary noise, and cursor resumption. Browser QA includes a 14-pixel target with a synthetic pre-click displacement. These checks are not a measurement of the user's live hand tremor.

## Browser-history and intermittent-click follow-up

The toolbar buttons highlighted in the new report mean browser history. The earlier plain Left/Right mapping was for slides and does not activate those buttons. `NAVIGATION_TARGET=browser` is now the application and mapper default: Alt+Left/Alt+Right on Windows/Linux, Command+Left/Command+Right on macOS. `slides` preserves the previous mapping. Old trace sessions without this setting retain their slide mapping when replayed. See [Chrome's official shortcut reference](https://support.google.com/chrome/answer/157179?hl=en).

The new click screenshot reports `None`, so classification failed before a click could be sent. A screenshot cannot provide the original depth coordinates or temporal sequence. Code review and synthetic regressions reproduced related failures: the shared two-finger direction rule rejected oblique/slightly bent fingers, and three-consecutive-frame classification plus click dwell could prevent confirmation under intermittent uncertainty. After pointing, a separate click pose now accepts perspective/mild bends while requiring both raised fingers, non-hooked distal joints, and positively curled ring/pinky. Directional navigation keeps its stricter rules. Click confirmation is time-based, freezes the target, and must complete within a bounded window so sparse noise cannot accumulate into a click. Out-of-frame landmarks now produce an explicit hand-position hint when recognition is uncertain.

Validation includes mirrored/oblique poses, 10/15/30/60 FPS, isolated unknown frames, sparse false detections, and gradual point-to-palm transitions. The `--desktop-history` browser check additionally used the **actual PyAutoGUI executor on Windows** against a uniquely titled isolated Chrome window: Back twice and Forward twice reached the exact expected local history entries. The helper refuses input unless that owned window is foreground and permits only Back/Forward. This establishes OS shortcut delivery, not live webcam recognition or click delivery. Other browser gesture checks still use synthetic hands and page-level input. Live landmark recordings remain needed to reproduce the exact screenshot session.

## 10 September follow-up: contextual two-finger click and restored playback

The reported screenshots showed recognized Thumbs Up rejected by a 400 ms recent-point gate, and recognized Fist intentionally doing nothing in Mouse mode. Both were interaction-layer defects, not evidence that MediaPipe failed to recognize those screenshots.

Following the requested control change, active index pointing now selects a **two-finger single click**: extend the middle finger, hold briefly, and the cursor target is clicked once. Finger direction is ignored throughout this click interaction. A raw middle-finger bend/reach signal freezes the cursor while the finger begins opening, before full two-finger recognition, reducing transition drift. Point again to release/rearm. Show an open palm first to select scroll/arrows/zoom instead; all are available without changing Mouse mode. Bare two fingers at startup do nothing until Point or Palm establishes intent.

Fist now toggles playback once after 600 ms of recognized holding in Mouse mode. Brief fist transitions cancel pending clicks without sending playback. The Windows application defaults to `playpause`, with configurable `k`/`space` fallback; navigation-only mode uses the same configured key. [YouTube's official keyboard guide](https://support.google.com/youtube/answer/7631406?hl=en) documents the media play/pause key. [PyAutoGUI's key list](https://pyautogui.readthedocs.io/en/latest/keyboard.html) and the installed Windows mapping support `playpause` (VK_MEDIA_PLAY_PAUSE). Media-session routing remains OS/browser-dependent.

Optional thumb clicks now use the existing cursor without a recent-point deadline. Uncertain pose transitions allow 800 ms; frame stalls over 500 ms still reset immediately. Uncertain time does not count toward holds. Completed click/playback latches survive tracking resets to prevent duplicate actions from the same held gesture. A newly forming pinch cannot briefly activate pointing while the pinch-distance filter catches up.

Regression coverage includes 10/15/30/60 FPS, all four two-finger directions in click context, repeated/held clicks, early target freeze, palm-versus-point activation, loss of context after hand loss, short/held fists, uncertain timing, replay, and application wiring. Browser QA now feeds synthetic landmarks through the production classifier/controller and dispatches its commands into isolated headless Chrome. Its counters verify two-finger single click, explicit double/right click, scrolling and a single playback-key event. This is **not** a webcam, PyAutoGUI desktop-injection, or Windows media-session test.

Current controls and restart/testing instructions are in the README. The following sections are historical findings; their old Mouse-mode fist/scroll/zoom rules have been superseded.

## 10 September update: Mouse mode

Mouse mode is now the startup default. Index pointing controls the primary-monitor cursor, using adaptive smoothing. Thumbs-up is distinct from Fist: a short thumbs-up followed by Point sends a single click; a held thumbs-up sends one double click. Thumbs-down provides right click. Two vertical fingers scroll; palm/fist cancel pending mouse actions. The original controls remain in Navigation mode, selected with M or the Mode button.

The current README and on-screen Help describe the new controls. The sections below document the earlier Navigation-only investigation, not the full current gesture scheme. In particular, the old `ARMED` label has been replaced with explicit LIVE INPUT/DRY RUN/PAUSED state, and Mouse pointing does not require an open-palm gate.

The local browser practice fixture (`python main.py --practice`) has been checked in an isolated Chrome session for single click, double click, right click, and wheel scrolling, with no JavaScript errors. This checks the browser fixture, not live webcam recognition or PyAutoGUI's desktop input delivery. Camera-loop tests use fake frames and injected executors. Live testing remains necessary before claiming accuracy for different users or applications.

Click tests cover 10/15/30/60 FPS, target locking, no speculative single click before double click, release debouncing, long holds, noisy transitions, hand loss, multiple hands, mode changes, enable/disable, pause/resume, malformed landmarks, backwards time/frame gaps, and physical-mouse takeover. Mouse-mode pinch cannot emit navigation zoom shortcuts. Trace version 2 records pointer coordinates and session controls, while replay remains dry run and still supports version 1.

The click design is explicit: software cannot generally determine whether the user intends to select, open, or activate a target. The user chooses single or double click, and the OS/app assigns the resulting meaning. Pointer smoothing follows the [One Euro filter](https://gery.casiez.net/1euro/) approach; click delivery uses [PyAutoGUI's mouse API](https://pyautogui.readthedocs.io/en/latest/mouse.html). The current pointer mapping targets the primary display, consistent with [PyAutoGUI's documented monitor support](https://pyautogui.readthedocs.io/en/latest/index.html).

Generated double clicks use an interval of at most 100 ms, reduced when necessary to fit inside the user's Windows setting read through [GetDoubleClickTime](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getdoubleclicktime). This does not change OS mouse settings.

---

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
