"""Camera panel, explicit input state, progress, and clickable controls."""

import cv2
import numpy as np


class FeedbackOverlay:
    BUTTONS = (("E: Input", "enable"), ("P: Pause", "pause"), ("M: Mode", "mode"),
               ("H: Help", "help"), ("T: Test", "practice"), ("Q: Quit", "quit"))

    def __init__(self):
        self.buttons = []

    @staticmethod
    def text(canvas, value, x, y, width, color=(230,235,240), scale=.5):
        # Fit status text to small webcam resolutions instead of clipping it.
        while cv2.getTextSize(value, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)[0][0] > width and scale > .33:
            scale -= .02
        if cv2.getTextSize(value, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)[0][0] > width:
            while value and cv2.getTextSize(value + "...", cv2.FONT_HERSHEY_SIMPLEX, scale, 1)[0][0] > width:
                value = value[:-1]
            value += "..."
        cv2.putText(canvas, value, (x,y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)

    def hit_test(self, x, y):
        for left,top,right,bottom,action in self.buttons:
            if left <= x <= right and top <= y <= bottom:
                return action
        return None

    def render(self, frame, gesture, enabled, status, last_action, *, mode="mouse",
               paused=False, progress=0., help_visible=False, fps=0., margin=.15,
               max_width=None, max_height=None, navigation_target="browser"):
        height,width = frame.shape[:2]
        header,footer = 132,52
        direction_action = "browser Back/Forward" if navigation_target == "browser" else "slide arrows"
        help_lines = (
            ["POINT: move. Add MIDDLE finger: one click at locked target.",
             "Keep two fingers raised: no repeat. Fold middle to move again.",
             "THUMB UP: hold until bar fills = one double click.",
             "THUMB DOWN: short hold, then point = right click.",
             "FIST: hold until bar fills = play/pause once. PALM: cancel.",
             "PALM until READY, then two fingers UP/DOWN: scroll.",
             f"PALM then LEFT/RIGHT: {direction_action}; PINCH: zoom.",
             "Real mouse takes priority. Open palm resumes gestures."]
            if mode == "mouse" else
            ["OPEN PALM: wait for READY before each interaction.",
             f"TWO FINGERS: up/down scroll, left/right {direction_action}.",
             "PINCH then spread/close: zoom. FIST: play/pause once.",
             "Focus the browser/player. Grey Back/Forward means no history.",
             "Use Mouse mode to point and click on browser controls."]
        )
        help_height = (len(help_lines)*23 + 12) if help_visible else 0
        canvas = np.full((header+height+footer+help_height,width,3),(27,24,21),dtype=np.uint8)
        canvas[header:header+height] = frame
        output = "PAUSED" if paused else "LIVE INPUT" if enabled else "DRY RUN - no OS input"
        color = (100,230,150) if enabled and not paused else (80,205,250)
        mode_label = "POINT + TWO-FINGER CLICK" if mode == "mouse" else "NAVIGATION"
        self.text(canvas, f"NEO HandNav | {mode_label} | {output}",12,25,width-24,color,.60)
        self.text(canvas, f"Gesture: {gesture.display_name}   |   {fps:.0f} FPS",12,49,width-24)
        self.text(canvas, status,12,74,width-24,(100,215,255),.54)
        cv2.rectangle(canvas,(12,86),(width-12,92),(65,62,59),-1)
        cv2.rectangle(canvas,(12,86),(12+round((width-24)*min(1.,max(0.,progress))),92),color,-1)
        message = "Last input: none"
        if last_action:
            prefix = "ERROR" if last_action.error else "WAITING" if last_action.blocked_reason else "SENT" if last_action.executed else "DRY RUN"
            detail = last_action.error or last_action.blocked_reason or f"{last_action.command.description} {last_action.command.arguments}"
            message = f"{prefix}: {detail}"
        self.text(canvas,message,12,116,width-24)
        if mode == "mouse":
            cv2.rectangle(canvas,(round(width*margin),header+round(height*margin)),
                          (round(width*(1-margin)),header+round(height*(1-margin))),(220,185,70),1)
            self.text(canvas,"Pointer area -> primary monitor",round(width*margin)+5,header+round(height*margin)+18,
                      round(width*(1-2*margin))-10,(220,185,70),.4)
        self.buttons=[]
        top=header+height+8
        cell=width/len(self.BUTTONS)
        for i,(label,action) in enumerate(self.BUTTONS):
            left,right=round(i*cell)+4,round((i+1)*cell)-4
            cv2.rectangle(canvas,(left,top),(right,top+32),(57,53,48),-1)
            self.text(canvas,label,left+5,top+21,right-left-10,scale=.42)
            self.buttons.append((left,top,right,top+32,action))
        if help_visible:
            for i,line in enumerate(help_lines):
                self.text(canvas,line,12,header+height+footer+22+i*23,width-24)
        scale = min(1., (max_width or canvas.shape[1])/canvas.shape[1],
                    (max_height or canvas.shape[0])/canvas.shape[0])
        if scale < 1:
            canvas = cv2.resize(canvas, (round(canvas.shape[1]*scale),round(canvas.shape[0]*scale)),
                                interpolation=cv2.INTER_AREA)
            self.buttons = [(round(l*scale),round(t*scale),round(r*scale),round(b*scale),action)
                            for l,t,r,b,action in self.buttons]
        return canvas
