"""
orb.py  -  Alexa ka GUI (animated orb + window + device info)
Developer : Akshat Rajput

alexa.py me sirf ye use hota hai:
    from orb import bridge, run_app

    bridge.state_changed.emit("SPEAKING" / "LISTENING" / "IDLE")
    bridge.message.emit("YOU" / "ALEXA", "text")
    run_app(target_function)

NEW (buttons + terminal):
    bridge.wake_event     -> Wake Up button dabane par set hota hai
    bridge.restart_event  -> Restart button dabane par set hota hai
    Terminal ka print / error GUI ke "TERMINAL" panel me bhi dikhta hai.

NEW (stuck detection):
    bridge.heartbeat      -> alexa.py jab bhi kaam kare, ise time.time() se update kare
    bridge.stage          -> alexa.py yahan likhti hai ki abhi kya kar rahi hai
    Agar heartbeat STUCK_AFTER sec se purana ho to terminal panel me
    "[STUCK] ... stage: ..." aur code ki exact line print hoti hai.
    Kuch restart NAHI hota, sirf print hota hai.

Note: "IDLE" ko GUI me SLEEPING mode ki tarah dikhaya jata hai
(Alexa wake-word "alexa" ka wait kar rahi hoti hai).

NEW (auto recover): Alexa STUCK ho jaye (heartbeat STUCK_AFTER sec se purana) to Alexa bolti hai
"Restarting Alexa" aur program khud restart ho jaata hai. Side column "STUCK" me ginti dikhti hai
(kitni baar atki) - restart ke baad bhi ginti yaad rehti hai.

NEW (intro): boot HUD ke baad main screen TURANT nahi aati. Pehle JARVIS jaisa WELCOME scene chalta hai:
AI core + voice bars + neural nodes, Alexa bolti hai ("Welcome sir... let me introduce myself...
created by Akshat Rajput") aur subtitles saath me type hote hain. Uske baad hi main screen ubharti hai.
Click karke intro skip kar sakte ho. Alexa (mic) intro khatam hone ke baad hi start hoti hai.

NEW (chat): conversation ab sundar bubbles me dikhti hai, Alexa ka jawab typewriter jaisa type hota hai.

NEW: JARVIS jaisa BOOT screen (dark HUD, typing text, 0-100% loading) + JARVIS style sound,
uske baad orb aur poora UI ek ek karke ubharta hai.

FIX (welcome voice): pehle sirf pehli line ("Good afternoon sir, welcome") bolti thi, uske baad awaaz band ho jaati thi
(pyttsx3 ka purana engine cache me atak jaata tha). Ab Windows SAPI seedha use hota hai (har line ke liye
naya voice object), isliye saari welcome lines bolti hain. pyttsx3 sirf backup hai.

NEW (theme): welcome animation wali cyan / blue HUD theme ab MAIN SCREEN me bhi hai
(dark navy background, cyan grid + scan line, cyan orb, cyan cards / buttons / borders).

Pehle wala INTRO: Pehle sirf ek cheez (sphere) aati hai, phir dheere dheere
plasma, glow, particles, rings aur poora UI judta jaata hai, saath me layered sound
bajti hai (sound code se hi banti hai, koi file nahi chahiye).
  - Intro band karna ho:   INTRO_SOUND = False  (sirf sound band)
  - Restart par intro nahi chalta (ALEXA_SKIP_LOGIN=1 hone par skip).
"""

import os
import sys
import math
import random
import platform
import threading
import subprocess
import traceback
import io
import wave
from array import array
from datetime import datetime
from time import perf_counter, time as _now, sleep as _sleep

try:
    import winsound          # sirf Windows (intro sound ke liye)
except ImportError:
    winsound = None

try:
    import psutil
except ImportError:          # pip install psutil  (optional, device info ke liye)
    psutil = None

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QFrame,
    QLabel,
    QTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QLayout,
    QScrollArea,
)

from PySide6.QtCore import (
    Qt,
    QTimer,
    QPointF,
    QRectF,
    QObject,
    Signal,
    QPropertyAnimation,
    QEasingCurve,
    qInstallMessageHandler,      # Qt ki warnings bhi terminal panel me aayengi
)
from PySide6.QtGui import (
    QPainter,
    QColor,
    QRadialGradient,
    QConicalGradient,
    QPainterPath,
    QPen,
    QBrush,
    QFont,
    QCursor,
    QLinearGradient,
    QFontMetricsF,
    QFontMetrics,
)


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _rgba(c, a):
    return QColor(c.red(), c.green(), c.blue(), max(0, min(255, int(a))))


def _shift(c, dh=0, light=1.0, a=255):
    h, s, v, _ = c.getHsv()
    if h < 0:
        h = 0
    return QColor.fromHsv(
        (h + dh) % 360,
        min(255, s),
        min(255, int(v * light)),
        max(0, min(255, int(a))),
    )


def _font(base, bold=True, family="Segoe UI"):
    f = QFont(family)
    f.setPointSizeF(base)
    f.setBold(bold)
    return f


# ----------------------------------------------------------------------
# INTRO  (movie jaisa: pehle ek cheez, phir dheere dheere sab judta hai) + SOUND
# ----------------------------------------------------------------------

INTRO_ENABLED = os.environ.get("ALEXA_SKIP_LOGIN") != "1"    # restart par intro nahi
INTRO_SOUND = True                                           # sound band karni ho to False
INTRO_TOTAL = 6.4                                            # intro ki lambai (second)

# orb ki kaun si cheez kab ubharti hai: (shuru, khatam) second
INTRO_STAGES = {
    "body":      (0.00, 1.30),    # pehle sirf sphere
    "plasma":    (1.00, 2.40),    # andar ka rangeen plasma
    "glow":      (2.00, 3.40),    # glow, halo, ghoomte arcs
    "particles": (3.20, 4.40),    # udte particles
    "rings":     (4.20, 5.40),    # ripple rings + voice bars
}
INTRO_FLASH = 5.2                 # aakhir me halka sa flash
INTRO_SPEED = 1.8                 # boot animation ke baad orb/UI reveal itna tez chalta hai

# JARVIS jaisa BOOT animation (dark HUD + 0-100% loading) + sound
WELCOME_AT = 5.6                  # boot HUD ke baad Alexa yahan se bolna shuru karti hai
WELCOME_HOLD = 1.0                # bolna khatam hone ke baad itni der ruk ke main screen laao
WELCOME_MAX = 60.0                # safety: awaaz atak jaye to bhi itne sec baad aage badho
EXIT_DUR = 1.6                    # welcome scene ke fade-out ki lambai
BOOT_LINES = [                    # (kab, text) - loading log lines
    (0.5, "BOOTING NEURAL CORE"),
    (1.2, "LOADING VOICE MODULES"),
    (2.0, "CALIBRATING MICROPHONE"),
    (2.8, "SYNCING DEVICE SENSORS"),
    (3.6, "ESTABLISHING INTERFACE"),
    (4.4, "ALL SYSTEMS ONLINE"),
]
SOUND_TOTAL = 6.8                 # startup sound ki lambai (second)


def _build_intro_wav(sr=22050):
    # JARVIS / Iron-Man jaisa startup sound code se banata hai:
    # gehri rising hum -> whoosh -> digital beeps/chirps -> riser -> "ONLINE" boom + chord
    n = int(sr * SOUND_TOTAL)
    buf = [0.0] * n
    tau = math.tau
    exp = math.exp
    sin = math.sin
    rnd = random.Random(7)

    def add(start, dur, fn):
        i0 = int(start * sr)
        i1 = min(n, int((start + dur) * sr))
        for i in range(i0, i1):
            t = (i - i0) / sr
            buf[i] += fn(t, t / dur)

    # 1) neeche ki hum jo dheere dheere upar chadhti hai (power charging)
    def hum(t, k):
        f = 38 + 34 * min(1.0, t / 5.0)
        a = min(1.0, t / 1.5)
        if t > 5.2:
            a *= max(0.0, 1.0 - (t - 5.2) / 1.4)
        return 0.16 * a * (sin(tau * f * t) + 0.5 * sin(tau * 2 * f * t + 0.3) + 0.25 * sin(tau * 3.01 * f * t))
    add(0.0, SOUND_TOTAL, hum)

    # 2) whoosh (noise + badalta filter): shuru me aur riser ke saath
    def whoosh(start, dur, gain, c0, c1):
        i0 = int(start * sr)
        i1 = min(n, int((start + dur) * sr))
        lp = 0.0
        for i in range(i0, i1):
            k = (i - i0) / (i1 - i0)
            env = sin(math.pi * k) ** 2
            lp += (c0 + (c1 - c0) * k) * ((rnd.random() * 2 - 1) - lp)
            buf[i] += gain * env * lp
    whoosh(0.1, 2.5, 0.9, 0.02, 0.30)
    whoosh(3.6, 1.5, 1.0, 0.05, 0.55)

    # 3) digital beeps (loading ke saath tik tik tik)
    tones = (1320.0, 1568.0, 1760.0, 2093.0, 2349.0, 2637.0, 3136.0)

    def blip(st, fr, gain=0.07):
        def f(t, k):
            att = min(1.0, t / 0.004)
            return gain * att * exp(-t * 42) * (sin(tau * fr * t) + 0.3 * sin(tau * 2 * fr * t))
        add(st, 0.12, f)
        add(st + 0.13, 0.12, lambda t, k, f=f: 0.4 * f(t, k))     # halki echo

    j = 0
    while 0.55 + 0.19 * j < 5.0:
        if rnd.random() < 0.78:
            blip(0.55 + 0.19 * j, rnd.choice(tones))
        j += 1

    # 4) har log line par ek upar chadhti chirp (data load)
    def chirp(st):
        def f(t, k):
            return 0.12 * sin(k * math.pi) * sin(tau * (800 * t + (800 / (2 * 0.14)) * t * t))
        add(st, 0.14, f)
    for st, _txt in BOOT_LINES:
        chirp(st)

    # 5) riser: upar chadhti sweep (3.4 -> 5.0)
    def riser(t, k):
        ph = tau * (300 * t + (2500 / (2 * 1.6)) * t * t)
        return 0.10 * (k ** 2) * (sin(ph) + 0.4 * sin(2 * ph))
    add(3.4, 1.6, riser)

    # 6) bell / chord helper
    def bell(start, freq, dur=1.9, gain=0.30, dec=2.3):
        def f(t, k):
            att = min(1.0, t / 0.012)
            return gain * att * exp(-t * dec) * (
                sin(tau * freq * t)
                + 0.40 * sin(tau * 2 * freq * t) * exp(-t * 3)
                + 0.20 * sin(tau * 3 * freq * t) * exp(-t * 5)
            )
        add(start, dur, f)

    # 7) 5.0 sec par "ALEXA ONLINE": gehra boom + poora chord + sparkle
    add(5.0, 2.5, lambda t, k: 0.62 * exp(-t * 2.0) * sin(tau * (48 * t + 18 * (1 - exp(-4 * t)))))
    for fr in (220.0, 330.0, 440.0, 660.0, 880.0):
        bell(5.0, fr, dur=3.0, gain=0.15, dec=1.3)
    for st, fr in ((5.10, 2637.0), (5.18, 3136.0), (5.27, 3951.0)):
        add(st, 0.8, lambda t, k, fr=fr: 0.09 * exp(-t * 5) * sin(tau * fr * t))

    # 8) orb/UI reveal ke saath halki chimes
    for st, fr in ((5.8, 659.25),):
        bell(st, fr, dur=1.0, gain=0.07, dec=3.0)

    # normalize + halka fade out
    peak = max(1e-9, max(abs(x) for x in buf))
    scale = 0.85 * 32767 / peak
    fade_n = int(sr * 0.5)
    pcm = array("h", [0]) * n
    for i, x in enumerate(buf):
        g = 1.0 if i < n - fade_n else (n - i) / fade_n
        pcm[i] = int(max(-32767, min(32767, x * scale * g)))

    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return bio.getvalue()


_intro_wav = None
_intro_thread = None


def _prepare_intro_sound():
    global _intro_wav
    try:
        _intro_wav = _build_intro_wav()
    except Exception as e:
        print("Intro sound error:", e)


# import ke waqt background me bana lo (taaki window ke waqt turant bajne ko tayyar ho)
if INTRO_ENABLED and INTRO_SOUND and winsound is not None:
    _intro_thread = threading.Thread(target=_prepare_intro_sound, daemon=True)
    _intro_thread.start()


def _play_intro_sound():
    def run():
        try:
            winsound.PlaySound(_intro_wav, winsound.SND_MEMORY)
        except Exception as e:
            print("Intro sound error:", e)
    threading.Thread(target=run, daemon=True).start()


# ----------------------------------------------------------------------
# ORB
# ----------------------------------------------------------------------

class AnimatedOrb(QWidget):
    """
    Smooth, colourful glass-plasma orb.

    States : SLEEPING (wake-word ka wait) / LISTENING / SPEAKING
    - Dt-based animation (frame drop pe bhi smooth)
    - Hover pe zoom-in + cursor ki taraf light follow karti hai
    - SLEEPING: dheemi saans jaisi breathing, moon halo, floating  z Z Z
    - LISTENING: soft radar sweep, sonar rings, dotted ring, ghoomti voice wave
    - SPEAKING : ripple rings + voice bars + zyada energy
    """

    # (primary, secondary, accent)   -> welcome HUD jaisi cyan / blue theme
    PALETTES = {
        "SLEEPING": ((0, 150, 235), (96, 140, 255), (0, 208, 255)),      # cyan-blue / periwinkle / HUD cyan
        "LISTENING": ((0, 182, 235), (0, 222, 156), (92, 160, 255)),     # electric cyan / mint / sky blue
        "SPEAKING": ((226, 80, 200), (96, 140, 255), (0, 208, 255)),     # pink (voice) / blue / HUD cyan
    }

    PRESETS = {
        "SLEEPING": dict(radius=56.0, amp=3.0, speed=0.50, glow=0.70, act=0.0),
        "LISTENING": dict(radius=76.0, amp=7.5, speed=1.35, glow=0.95, act=0.90),
        "SPEAKING": dict(radius=82.0, amp=11.0, speed=1.90, glow=1.05, act=1.0),
    }

    def __init__(self):
        super().__init__()

        self.setMinimumSize(420, 380)

        self.state = "SLEEPING"
        self.t = 0.0            # animation time (speed ke saath)
        self.real = 0.0         # real time
        self.level = 0.0        # voice energy 0..1
        self.ripple = 0.0
        self.sonar = 0.0        # listening: andar ki taraf aati rings
        self.lm = 0.0           # listening mix 0..1
        self.sm = 1.0           # sleeping mix 0..1
        self.zoom = 1.0         # hover zoom
        self.lx = 0.0           # light follow (cursor)
        self.ly = 0.0
        self.last = perf_counter()
        # intro clock: -1 = abhi shuru nahi (sab chhupa hai), INTRO_TOTAL+ = poora dikh raha hai
        self.intro_t = -1.0 if INTRO_ENABLED else INTRO_TOTAL + 10.0

        self.pal = [list(map(float, c)) for c in self.PALETTES["SLEEPING"]]
        self.burst = 1.0        # state badalne par shockwave (0..1, 1 = khatam)
        self._first_state = True
        # satellites: (start angle, orbit factor, speed, size)
        self.sats = [(0.0, 1.50, 0.9, 3.6), (2.1, 1.72, -0.7, 3.0), (4.2, 1.36, 1.25, 2.6)]
        self.cur = dict(self.PRESETS["SLEEPING"])

        rnd = random.Random(11)
        self.particles = [
            (
                rnd.uniform(0, math.tau),
                rnd.uniform(1.30, 1.80),
                rnd.uniform(0.12, 0.50) * rnd.choice([-1, 1]),
                rnd.uniform(1.0, 2.5),
                rnd.uniform(0, math.tau),
            )
            for _ in range(24)
        ]

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.animate)
        self.timer.start(16)

    # ------------------------------------------------------------------
    def set_state(self, state):
        state = state.upper()
        if state == "IDLE":
            state = "SLEEPING"
        if state != self.state and not self._first_state:
            self.burst = 0.0          # shockwave ring
        self._first_state = False
        self.state = state

    def start_intro(self):
        self.intro_t = 0.0

    def _rev(self, name):
        """0..1 : intro me ye cheez kitni ubhar chuki hai (smooth)."""
        a, b = INTRO_STAGES[name]
        x = max(0.0, min(1.0, (self.intro_t - a) / (b - a)))
        return x * x * (3 - 2 * x)

    def _col(self, i):
        return QColor(*[max(0, min(255, int(v))) for v in self.pal[i]])

    # ------------------------------------------------------------------
    def animate(self):
        now = perf_counter()
        dt = min(0.05, max(0.001, now - self.last))
        self.last = now

        key = self.state if self.state in self.PRESETS else "SLEEPING"
        tgt = self.PRESETS[key]
        pal = self.PALETTES[key]

        k = 1 - math.exp(-dt * 4.5)

        for name in ("radius", "amp", "speed", "glow", "act"):
            self.cur[name] += (tgt[name] - self.cur[name]) * k

        for i in range(3):
            for j in range(3):
                self.pal[i][j] += (pal[i][j] - self.pal[i][j]) * k

        if 0.0 <= self.intro_t < INTRO_TOTAL + 1.0:
            self.intro_t += dt * INTRO_SPEED

        self.real += dt
        self.t += dt * self.cur["speed"]
        self.ripple = (self.ripple + dt * 0.42 * self.cur["speed"]) % 1.0
        self.sonar = (self.sonar + dt * 0.55) % 1.0
        if self.burst < 1.0:
            self.burst = min(1.0, self.burst + dt * 0.85)

        self.lm += ((1.0 if key == "LISTENING" else 0.0) - self.lm) * (1 - math.exp(-dt * 5.0))
        self.sm += ((1.0 if key == "SLEEPING" else 0.0) - self.sm) * (1 - math.exp(-dt * 3.5))

        # ---- hover zoom + cursor light follow ----
        hov = False
        tx = ty = 0.0
        if self.underMouse():
            pos = self.mapFromGlobal(QCursor.pos())
            dx = pos.x() - self.width() / 2
            dy = pos.y() - self.height() / 2
            if math.hypot(dx, dy) < self.cur["radius"] * 2.0:
                hov = True
            tx = max(-1.0, min(1.0, dx / (self.width() / 2)))
            ty = max(-1.0, min(1.0, dy / (self.height() / 2)))

        self.zoom += ((1.22 if hov else 1.0) - self.zoom) * (1 - math.exp(-dt * 9))
        self.lx += (tx - self.lx) * (1 - math.exp(-dt * 6))
        self.ly += (ty - self.ly) * (1 - math.exp(-dt * 6))

        # ---- smooth voice-like energy ----
        r = self.real
        if key == "SPEAKING":
            target = 0.40 + 0.60 * abs(
                0.55 * math.sin(r * 7.3) + 0.30 * math.sin(r * 3.1 + 1.0) + 0.15 * math.sin(r * 12.7 + 2.0)
            )
        elif key == "LISTENING":
            target = 0.18 + 0.22 * (0.5 + 0.5 * math.sin(r * 2.3)) + 0.10 * (0.5 + 0.5 * math.sin(r * 5.1 + 1.0))
        else:
            target = 0.05

        self.level += (target - self.level) * (1 - math.exp(-dt * 12))

        self.update()

    # ------------------------------------------------------------------
    @staticmethod
    def _blob(cx, cy, r, amp, ph, k1=3, k2=5, n=200):
        path = QPainterPath()
        for i in range(n + 1):
            a = math.tau * i / n
            rad = r + amp * 0.6 * (math.sin(k1 * a + ph) + 0.6 * math.sin(k2 * a - ph * 1.3))
            x = cx + math.cos(a) * rad
            y = cy + math.sin(a) * rad
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()
        return path

    # ------------------------------------------------------------------
    def paintEvent(self, event):

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        half = min(W, H) / 2

        # hover zoom
        p.translate(cx, cy)
        p.scale(self.zoom, self.zoom)
        p.translate(-cx, -cy)

        c1, c2, c3 = self._col(0), self._col(1), self._col(2)
        light = c1.lighter(175)

        cur = self.cur
        t = self.t
        level = self.level
        act = cur["act"]
        lm = self.lm
        sm = self.sm
        lx, ly = self.lx, self.ly

        breath = 0.5 + 0.5 * math.sin(self.real * 1.1)

        glow = cur["glow"] * (1 + sm * 0.40 * breath)
        r = (cur["radius"] * (1 + 0.03 * math.sin(t * 1.2)) + level * cur["radius"] * 0.08) \
            * (1 + sm * 0.04 * math.sin(self.real * 1.1))
        amp = cur["amp"] * (0.55 + level)

        # ---- intro: kaun si cheez kitni dikhni chahiye ----
        rv_body = self._rev("body")
        rv_plasma = self._rev("plasma")
        rv_glow = self._rev("glow")
        rv_part = self._rev("particles")
        rv_rings = self._rev("rings")
        r = r * (0.30 + 0.70 * rv_body)          # sphere chhoti se bhari hoti hai

        PLUS = QPainter.CompositionMode.CompositionMode_Plus
        OVER = QPainter.CompositionMode.CompositionMode_SourceOver
        NOPEN = Qt.PenStyle.NoPen
        NOBRUSH = Qt.BrushStyle.NoBrush

        # ============ 1. colourful ambient glow ============
        p.setOpacity(rv_glow)
        p.setCompositionMode(PLUS)
        p.setPen(NOPEN)

        gr = min(r * 2.4, half - 1)
        g = QRadialGradient(cx, cy, gr)
        g.setColorAt(0.0, _rgba(c1, 135 * glow))
        g.setColorAt(0.45, _rgba(c1, 62 * glow))
        g.setColorAt(1.0, _rgba(c1, 0))
        p.setBrush(g)
        p.drawEllipse(QPointF(cx, cy), gr, gr)

        for col, sx, sy, ph in ((c3, 0.7, 0.9, 0.0), (c2, -0.8, 0.6, 2.4)):
            ox = math.cos(t * sx + ph) * r * 0.45
            oy = math.sin(t * sy + ph) * r * 0.40
            g2 = QRadialGradient(cx + ox, cy + oy, gr * 0.75)
            g2.setColorAt(0.0, _rgba(col, 80 * glow))
            g2.setColorAt(1.0, _rgba(col, 0))
            p.setBrush(g2)
            p.drawEllipse(QPointF(cx + ox, cy + oy), gr * 0.75, gr * 0.75)

        # ============ 1b. SLEEPING highlight (moon halo) ============
        if sm > 0.02:
            hr = min(r * 2.0, half - 1)
            ha = 80 * sm * (0.55 + 0.45 * breath)
            halo = QRadialGradient(cx, cy, hr)
            halo.setColorAt(0.0, _rgba(c3, 0))
            halo.setColorAt(0.50, _rgba(c3, 0))
            halo.setColorAt(0.66, _rgba(c3, ha))
            halo.setColorAt(0.85, _rgba(c3, 0))
            halo.setColorAt(1.0, _rgba(c3, 0))
            p.setPen(NOPEN)
            p.setBrush(halo)
            p.drawEllipse(QPointF(cx, cy), hr, hr)

        # ============ 1c. LISTENING highlights ============
        if lm > 0.02:
            p.setCompositionMode(PLUS)
            p.setBrush(NOBRUSH)

            # soft radar sweep (concentric strokes = smooth radial fade)
            ang = (-self.real * 140) % 360
            for kk in range(7):
                fade = (1 - kk / 7) ** 1.6
                rad = r * (1.12 + kk * 0.085)
                sg = QConicalGradient(cx, cy, ang)
                sg.setColorAt(0.0, _rgba(c2.lighter(130), 125 * lm * fade))
                sg.setColorAt(0.25, _rgba(c3, 42 * lm * fade))
                sg.setColorAt(0.50, _rgba(c3, 0))
                sg.setColorAt(0.94, _rgba(c3, 0))
                sg.setColorAt(1.0, _rgba(c2.lighter(130), 125 * lm * fade))
                p.setPen(QPen(QBrush(sg), r * 0.1))
                p.drawEllipse(QPointF(cx, cy), rad, rad)

            # sonar rings: bahar se orb ki taraf aati hui
            for i in range(4):
                ph = (self.sonar + i / 4) % 1.0
                rr = r * (1.95 - 0.85 * ph)
                a = 150 * math.sin(math.pi * ph) * lm
                p.setPen(QPen(_rgba(c2.lighter(140), a), 1.8))
                p.drawEllipse(QPointF(cx, cy), rr, rr)

            # rotating dotted ring (round dots)
            dpen = QPen(_rgba(c3.lighter(150), 190 * lm), 2.6)
            dpen.setCapStyle(Qt.PenCapStyle.RoundCap)
            dpen.setDashPattern([0.01, 4.2])
            dpen.setDashOffset(self.real * 5)
            p.setPen(dpen)
            p.drawEllipse(QPointF(cx, cy), r * 1.64, r * 1.64)

        # ============ 2. ripple rings ============
        p.setOpacity(rv_rings)
        if act > 0.02:
            p.setBrush(NOBRUSH)
            for i in range(3):
                ph = (self.ripple + i / 3) % 1.0
                rr = r * 1.12 + ph * r * 0.85
                a = 120 * (1 - ph) ** 2 * act
                p.setPen(QPen(_rgba(c3.lighter(130), a), 1.6))
                p.drawEllipse(QPointF(cx, cy), rr, rr)

        # ============ 3. circular voice bars ============
        if act > 0.02:
            n = 60
            base_r = r * 1.30
            pen = QPen(Qt.PenStyle.SolidLine)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setWidthF(2.6)
            for i in range(n):
                a = math.tau * i / n + t * 0.15
                wave_s = abs(math.sin(t * 3.0 + i * 0.7) * math.sin(t * 1.7 + i * 0.31))
                wave_l = 0.5 + 0.5 * math.sin(i * 0.55 - self.real * 7.0)
                wave = wave_s * (1 - lm) + wave_l * lm
                h = 2.0 + (6 + 24 * level) * wave * act
                mix = 0.5 + 0.5 * math.sin(a * 2 + t)
                bc = QColor(
                    int(c1.red() + (c3.red() - c1.red()) * mix),
                    int(c1.green() + (c3.green() - c1.green()) * mix),
                    int(c1.blue() + (c3.blue() - c1.blue()) * mix),
                )
                pen.setColor(_rgba(bc.lighter(130), 225 * act))
                p.setPen(pen)
                x1 = cx + math.cos(a) * base_r
                y1 = cy + math.sin(a) * base_r
                x2 = cx + math.cos(a) * (base_r + h)
                y2 = cy + math.sin(a) * (base_r + h)
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # ============ 4. rotating energy arcs ============
        p.setOpacity(rv_glow)
        arc_a = 0.40 + 0.60 * max(act, 0.30)
        p.setBrush(NOBRUSH)

        for rad_f, colr, spd, width in ((1.19, c3, 55.0, 2.6), (1.11, c2, -38.0, 1.8)):
            ring_r = r * rad_f
            p.setPen(QPen(_rgba(colr, 26 * arc_a), 1.0))
            p.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

            cg = QConicalGradient(cx, cy, (t * spd) % 360)
            cg.setColorAt(0.0, _rgba(colr.lighter(145), 240 * arc_a))
            cg.setColorAt(0.18, _rgba(colr, 0))
            cg.setColorAt(0.82, _rgba(colr, 0))
            cg.setColorAt(1.0, _rgba(colr.lighter(145), 240 * arc_a))
            pen = QPen(QBrush(cg), width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

        # ============ 4b. fine HUD tick ring + comet satellites ============
        p.setOpacity(rv_glow)
        tr = min(r * 1.88, half - 6)
        nt = 72
        rot = self.real * (5.0 + 14.0 * act)
        vis = 0.35 + 0.65 * max(act, 0.35)
        for i in range(nt):
            a = math.radians(i * 360.0 / nt + rot)
            major = (i % 6 == 0)
            ln = 7.0 if major else 3.5
            p.setPen(QPen(_rgba(c3.lighter(145), (160 if major else 55) * vis), 1.6 if major else 1.0))
            p.drawLine(QPointF(cx + math.cos(a) * tr, cy + math.sin(a) * tr),
                       QPointF(cx + math.cos(a) * (tr + ln), cy + math.sin(a) * (tr + ln)))

        p.setOpacity(rv_part)
        p.setPen(NOPEN)
        sat_cols = (c3, c2, c1)
        for si, (a0, of, sp, size) in enumerate(self.sats):
            ang = a0 + self.real * sp * (0.45 + 1.1 * max(act, 0.25))
            d = r * of
            sgn = 1.0 if sp > 0 else -1.0
            pc = sat_cols[si % 3].lighter(165)
            for k in range(14):
                aa = ang - sgn * k * 0.05
                fk = 1.0 - k / 14.0
                p.setBrush(_rgba(pc, 210 * fk * fk * vis))
                p.drawEllipse(QPointF(cx + math.cos(aa) * d, cy + math.sin(aa) * d * 0.92),
                              size * (0.35 + 0.65 * fk), size * (0.35 + 0.65 * fk))
            p.setBrush(_rgba(pc, 60 * vis))
            p.drawEllipse(QPointF(cx + math.cos(ang) * d, cy + math.sin(ang) * d * 0.92), size * 2.8, size * 2.8)

        # ============ 5. orbiting particles ============
        p.setOpacity(rv_part)
        p.setPen(NOPEN)
        cols = (c1, c2, c3)
        for i, (ang0, orb, spd, size, ph) in enumerate(self.particles):
            a = ang0 + t * spd
            d = r * orb + math.sin(t * 1.5 + ph) * 6
            x = cx + math.cos(a) * d
            y = cy + math.sin(a) * d * 0.92
            alpha = abs(65 + 65 * math.sin(t * 2 + ph)) * (0.45 + glow * 0.5)
            pc = cols[i % 3].lighter(155)
            p.setBrush(_rgba(pc, alpha * 0.35))
            p.drawEllipse(QPointF(x, y), size * 2.2, size * 2.2)
            p.setBrush(_rgba(pc, alpha))
            p.drawEllipse(QPointF(x, y), size, size)

        # ============ 6. flowing outline ============
        p.setOpacity(rv_glow)
        p.setBrush(NOBRUSH)
        energy = min(1.0, cur["amp"] / 6.0) * 0.7 + 0.3
        path = self._blob(cx, cy, r * 1.05, amp, t * 1.1, 3, 5)
        open_ = QPen(_rgba(light, 160 * energy), 1.5)
        open_.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(open_)
        p.drawPath(path)

        # ============ 7. sphere body ============
        p.setOpacity(rv_body)
        p.setCompositionMode(OVER)
        body = QPainterPath()
        body.addEllipse(QPointF(cx, cy), r, r)

        base = QRadialGradient(cx - r * 0.3 + lx * r * 0.18, cy - r * 0.35 + ly * r * 0.18, r * 1.45)
        base.setColorAt(0.0, c1.lighter(175))
        base.setColorAt(0.45, c1)
        base.setColorAt(1.0, c1.darker(310))
        p.setPen(NOPEN)
        p.setBrush(base)
        p.drawPath(body)

        # ============ 8. inner plasma (multi colour) ============
        p.save()
        p.setClipPath(body)
        p.setCompositionMode(PLUS)
        p.setOpacity(rv_plasma)

        layers = (
            (c1.lighter(125), 0.0, 3, 5, 135, 0.0),
            (c2, 2.1, 2, 4, 130, 2.0),
            (c3, 4.2, 4, 6, 115, 4.0),
            (_shift(c1, 40, 1.25), 5.5, 5, 3, 90, 1.0),
        )
        for col, ph, k1, k2, alpha, off in layers:
            bx = cx + math.cos(t * 0.8 + off) * r * 0.20
            by = cy + math.sin(t * 0.6 + off) * r * 0.20
            blob = self._blob(bx, by, r * 0.62, r * 0.16 * (0.6 + level), t * 1.3 + ph, k1, k2)
            grad = QRadialGradient(bx, by, r * 0.88)
            grad.setColorAt(0.0, _rgba(col, alpha))
            grad.setColorAt(1.0, _rgba(col, 0))
            p.setPen(NOPEN)
            p.setBrush(grad)
            p.drawPath(blob)

        core_r = r * (0.36 + 0.10 * level + 0.05 * lm * (0.5 + 0.5 * math.sin(self.real * 5))
                      + 0.04 * sm * breath)
        core = QRadialGradient(cx + lx * r * 0.06, cy + ly * r * 0.06, core_r)
        core.setColorAt(0.0, QColor(255, 255, 255, int(160 + 80 * min(1.0, level))))
        core.setColorAt(0.5, _rgba(light, 90))
        core.setColorAt(1.0, _rgba(light, 0))
        p.setBrush(core)
        p.drawEllipse(QPointF(cx, cy), core_r * 1.0, core_r * 1.0)

        # bolte / sunte waqt andar bijli jaisi lehrein
        if act > 0.05:
            p.setBrush(NOBRUSH)
            for fi in range(6):
                base = t * 0.9 + fi * math.tau / 6
                fp = QPainterPath()
                fp.moveTo(cx, cy)
                for s in range(1, 10):
                    f = s / 9.0
                    a = base + math.sin(t * 3.0 + fi * 1.7 + f * 5.0) * 0.42 * f
                    rad = r * 0.97 * f
                    fp.lineTo(cx + math.cos(a) * rad, cy + math.sin(a) * rad)
                p.setPen(QPen(QColor(255, 255, 255, int(80 * act * (0.35 + level))), 1.0))
                p.drawPath(fp)
        p.restore()

        # ============ 9. rim light (fresnel) ============
        p.setOpacity(rv_body)
        p.setCompositionMode(OVER)
        rim = QRadialGradient(cx, cy, r)
        rim.setColorAt(0.0, _rgba(c1, 0))
        rim.setColorAt(0.72, _rgba(c1, 0))
        rim.setColorAt(0.93, _rgba(c3.lighter(155), 120))
        rim.setColorAt(1.0, _rgba(light.lighter(130), 225))
        p.setPen(NOPEN)
        p.setBrush(rim)
        p.drawEllipse(QPointF(cx, cy), r, r)

        # ============ 10. glass highlights ============
        p.save()
        p.setClipPath(body)
        p.setOpacity(rv_plasma)

        bl = QRadialGradient(cx, cy + r * 0.78, r * 0.55)
        bl.setColorAt(0.0, _rgba(c2.lighter(145), 90))
        bl.setColorAt(1.0, _rgba(c2, 0))
        p.setBrush(bl)
        p.drawEllipse(QPointF(cx, cy + r * 0.78), r * 0.55, r * 0.55)

        # specular: cursor ki taraf thoda khisakti hai
        p.translate(cx - r * 0.33 + lx * r * 0.14, cy - r * 0.42 + ly * r * 0.14)
        p.rotate(-35)
        p.scale(1.0, 0.55)
        hl = QRadialGradient(0, 0, r * 0.42)
        hl.setColorAt(0.0, QColor(255, 255, 255, 190))
        hl.setColorAt(0.6, QColor(255, 255, 255, 55))
        hl.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(hl)
        p.drawEllipse(QPointF(0, 0), r * 0.42, r * 0.42)
        p.restore()

        # ============ 11. glass edge ============
        p.setOpacity(rv_body)
        p.setBrush(NOBRUSH)
        p.setPen(QPen(_rgba(light, 150), 1.6))
        p.drawEllipse(QPointF(cx, cy), r, r)

        # ============ 12. SLEEPING: floating  z  Z  Z ============
        if sm > 0.02:
            p.setOpacity(rv_rings)
            p.setCompositionMode(OVER)
            letters = ("z", "z", "Z")
            for i in range(3):
                ph = (self.real * 0.28 + i / 3) % 1.0
                zx = cx + r * 0.80 + ph * r * 0.55 + math.sin(ph * 6 + i) * 4
                zy = cy - r * 0.80 - ph * r * 0.95
                size = 12 + ph * 22
                a = (math.sin(math.pi * ph) ** 1.2) * 235 * sm
                f = QFont("Segoe UI")
                f.setPixelSize(int(size))
                f.setBold(True)
                f.setItalic(True)
                p.setFont(f)
                p.setPen(_rgba(c3.lighter(165), a))
                p.drawText(QPointF(zx, zy), letters[i])

        # ============ 12b. state badalne par shockwave ============
        if self.burst < 1.0:
            k = self.burst
            p.setOpacity(1.0)
            p.setCompositionMode(PLUS)
            p.setBrush(NOBRUSH)
            for off, wd in ((0.0, 3.2), (0.14, 1.8)):
                kk = max(0.0, k - off)
                if kk <= 0:
                    continue
                p.setPen(QPen(_rgba(c3.lighter(165), 210 * (1 - kk) ** 1.6), wd * (1 - kk) + 0.8))
                rr = r * (1.0 + 2.2 * kk)
                p.drawEllipse(QPointF(cx, cy), rr, rr)

        # ============ 13. intro ka aakhri flash ============
        if INTRO_ENABLED and 0.0 <= self.intro_t < INTRO_TOTAL:
            fl = max(0.0, 1.0 - abs(self.intro_t - (INTRO_FLASH + 0.15)) / 0.6)
            if fl > 0.01:
                p.setOpacity(1.0)
                p.setCompositionMode(PLUS)
                p.setPen(NOPEN)
                fr = min(r * 3.2, half - 1)
                fg = QRadialGradient(cx, cy, fr)
                fg.setColorAt(0.0, _rgba(QColor(255, 255, 255), 140 * fl))
                fg.setColorAt(0.35, _rgba(c3, 90 * fl))
                fg.setColorAt(1.0, _rgba(c3, 0))
                p.setBrush(fg)
                p.drawEllipse(QPointF(cx, cy), fr, fr)

        p.end()


# ----------------------------------------------------------------------
# BOOT SCREEN  (JARVIS jaisa dark HUD: ghoomti rings + typing text + 0-100% loading)
# ----------------------------------------------------------------------

_BOOT_KEYS = [(0.3, 0.0), (1.2, 22.0), (1.5, 24.0), (2.4, 52.0), (2.7, 55.0),
              (3.6, 84.0), (3.9, 86.0), (4.8, 100.0)]


def _boot_progress(t):
    # 0..100 : kabhi tez, kabhi thoda ruk ke (asli loading jaisa)
    if t <= _BOOT_KEYS[0][0]:
        return 0.0
    for (t0, v0), (t1, v1) in zip(_BOOT_KEYS, _BOOT_KEYS[1:]):
        if t <= t1:
            x = (t - t0) / (t1 - t0)
            x = x * x * (3 - 2 * x)
            return v0 + (v1 - v0) * x
    return 100.0


def _sstep(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _welcome_lines():
    """(text, kind)  -  Alexa ye lines bolti hai, saath me screen par bilkul yahi type hoti hain."""
    now = datetime.now()
    h = now.hour
    greet = "Good morning" if h < 12 else ("Good afternoon" if h < 17 else "Good evening")
    when = f"Today is {now.strftime('%A')}, {now.day} {now.strftime('%B')}. The time is {now.strftime('%I:%M %p').lstrip('0')}."

    lines = [
        (f"{greet}, sir. Welcome.", "plain"),
        (when, "plain"),
        ("All systems are online and fully operational.", "plain"),
    ]

    # battery (agar mil sake)
    try:
        if psutil is not None:
            bat = psutil.sensors_battery()
            if bat is not None:
                lines.append((f"Your battery is at {int(bat.percent)} percent"
                              f"{', and charging' if bat.power_plugged else ''}.", "plain"))
    except Exception:
        pass

    lines += [
        ("Allow me to introduce myself.", "plain"),
        ("I am Alexa, an intelligent AI agent, built to automate your tasks and save your valuable time.", "plain"),
        ("I can open apps and websites, control your system, send messages, play music, "
         "and obey your voice commands.", "caps"),
        ("My neural core, voice engine and automation modules are synchronized and standing by.", "plain"),
        ("I was designed and created by Akshat Rajput.", "creator"),
        ("I am ready whenever you are, sir. Just say, Alexa.", "ready"),
    ]
    return lines


def _wrap_text(text, fm, maxw):
    words = text.split(" ")
    lines, cur = [], ""
    for wd in words:
        test = (cur + " " + wd).strip()
        if cur and fm.horizontalAdvance(test) > maxw:
            lines.append(cur)
            cur = wd
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def _sapi_say(text, rate=165, skip=None):
    """
    Windows SAPI se seedha bolta hai (blocking).
    FIX: pyttsx3 ka engine cache hota hai, isliye dusri line se awaaz band ho jaati thi.
    Yahan har baar bilkul naya SpVoice banta hai, to har line bolti hai.
    Return True = bol diya, False = SAPI available nahi / fail.
    """
    com = False
    try:
        import pythoncom
        pythoncom.CoInitialize()
        com = True
    except Exception:
        pass

    try:
        import win32com.client
        v = win32com.client.Dispatch("SAPI.SpVoice")
        try:
            voices = v.GetVoices()
            if voices.Count > 1:
                v.Voice = voices.Item(1)          # alexa.py jaisi voices[1] (female)
        except Exception:
            pass
        try:
            v.Rate = max(-10, min(10, int(round((rate - 200) / 20.0))))
            v.Volume = 100
        except Exception:
            pass

        v.Speak(text, 1)                          # 1 = async, taaki skip kar sakein
        while not v.WaitUntilDone(60):
            if skip is not None and skip():
                v.Speak("", 3)                    # 3 = async + purge (bolna turant band)
                break
        return True
    except Exception as e:
        print("TTS error (SAPI):", e)
        return False
    finally:
        if com:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


def _tts_say(text, rate=165, skip=None):
    """
    Bolta hai (blocking).
    1) Windows SAPI (har baar naya voice object)   2) backup: pyttsx3 (naya engine, cache ke bina)
    Dono fail -> False (error terminal panel me dikhega).
    """
    spoken = text.replace("AI", "A I")

    if _sapi_say(spoken, rate, skip):
        return True

    try:
        import pyttsx3
        from pyttsx3.engine import Engine
        eng = Engine(None)                        # pyttsx3.init() ki cache ke bina naya engine
        voices = eng.getProperty("voices")
        if len(voices) > 1:
            eng.setProperty("voice", voices[1].id)
        eng.setProperty("rate", rate)
        eng.setProperty("volume", 1.0)
        if skip is None or not skip():
            eng.say(spoken)
            eng.runAndWait()
        try:
            eng.stop()
        except Exception:
            pass
        return True
    except Exception as e:
        print("TTS error (pyttsx3):", e)
    return False


def _speak_once(text, rate=170):
    """Ek chhota sa sentence bolta hai (blocking)."""
    return _tts_say(text, rate)


class BootOverlay(QWidget):
    """
    JARVIS style intro, 3 phases:
      boot    : dark HUD + 0-100% loading + ALEXA ONLINE
      welcome : HUD ek AI core me badal jaata hai, Alexa bolti hai, subtitles type hote hain
                (main screen is waqt tak nahi aati)
      exit    : shockwave + fade, tab main screen ubharti hai
    Click karne par intro skip ho jaata hai.
    """

    line_started = Signal(int)
    line_done = Signal(int)
    speech_done = Signal()

    CHIPS = ("APPS", "WEBSITES", "SYSTEM CONTROL", "MESSAGES", "MUSIC", "VOICE COMMANDS")
    MODULES = ("NEURAL CORE", "VOICE ENGINE", "SPEECH RECOGNITION", "AUTOMATION", "DEVICE LINK", "INTERFACE")

    def __init__(self, parent):
        super().__init__(parent)
        self.t = -1.0
        self.last = perf_counter()
        self.on_reveal = None            # exit shuru hote hi (main UI ubharna shuru)
        self.on_finished = None          # overlay poori tarah hat jaye tab
        self._revealed = False
        self.phase = "boot"
        self.w = 0.0                     # welcome mix 0..1
        self.lvl = 0.0                   # voice energy
        self.spin = 0.0
        self.speaking = False
        self.lines = _welcome_lines()
        self.cur_line = -1
        self.line_t0 = 0.0
        self.line_full = False
        self.hold_until = None
        self.exit_t = 0.0
        self._skip = False

        self.line_started.connect(self._on_line_started)
        self.line_done.connect(self._on_line_done)
        self.speech_done.connect(self._on_speech_done)

        rnd = random.Random(5)
        self.nodes = [
            (rnd.uniform(0, math.tau), rnd.uniform(1.95, 2.45), rnd.uniform(0.10, 0.28) * rnd.choice([-1, 1]),
             rnd.uniform(1.6, 3.2), rnd.uniform(0, math.tau))
            for _ in range(14)
        ]
        self.motes = [
            (rnd.random(), rnd.random(), rnd.uniform(0.8, 2.2), rnd.uniform(0.4, 1.6), rnd.uniform(0, math.tau))
            for _ in range(70)
        ]

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.hide()

    # ------------------------------------------------------------------
    def begin(self):
        self.t = 0.0
        self.last = perf_counter()
        self._revealed = False
        self.phase = "boot"
        self.w = 0.0
        self._skip = False
        self.setGeometry(self.parentWidget().rect())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.show()
        self.raise_()
        self.timer.start(16)

    def mousePressEvent(self, ev):
        self._begin_exit(skipped=True)

    # ------------------------------------------------------------------
    # speech (alag thread)  -  har sentence ke saath subtitle sync hota hai
    # ------------------------------------------------------------------
    def _speech_worker(self):
        for i, (text, _kind) in enumerate(self.lines):
            if self._skip:
                break
            self.line_started.emit(i)
            t0 = perf_counter()
            try:
                ok = _tts_say(text, 160, skip=lambda: self._skip)
                if not ok:
                    print(f"[Welcome] line {i + 1} bol nahi payi (TTS fail)")
            except Exception as e:
                print(f"[Welcome] TTS crash on line {i + 1}: {e}")
            # awaaz na aaye / jaldi khatam ho to bhi subtitle poora type ho
            need = len(text) / 17.0
            while not self._skip and perf_counter() - t0 < need:
                _sleep(0.03)
            self.line_done.emit(i)
            _sleep(0.30)
        self.speech_done.emit()

    def _on_line_started(self, i):
        self.cur_line = i
        self.line_t0 = self.t
        self.line_full = False
        self.speaking = True

    def _on_line_done(self, i):
        if i == self.cur_line:
            self.line_full = True
            self.speaking = False

    def _on_speech_done(self):
        self.speaking = False
        self.line_full = True
        if self.hold_until is None:
            self.hold_until = self.t + WELCOME_HOLD

    # ------------------------------------------------------------------
    def _begin_exit(self, skipped=False):
        if self.phase == "exit":
            return
        if skipped:
            self._skip = True
            self.speaking = False
            if winsound is not None:
                try:
                    winsound.PlaySound(None, winsound.SND_PURGE)
                except Exception:
                    pass
        self.phase = "exit"
        self.exit_t = 0.0
        self.w = 1.0 if self.w > 0.5 else self.w
        if not self._revealed:
            self._revealed = True
            if self.on_reveal:
                self.on_reveal()          # neeche orb + UI ubharna shuru

    def tick(self):
        now = perf_counter()
        dt = min(0.05, max(0.001, now - self.last))
        self.last = now
        self.t += dt
        t = self.t

        if self.geometry() != self.parentWidget().rect():
            self.setGeometry(self.parentWidget().rect())

        if self.phase == "boot" and t >= WELCOME_AT:
            self.phase = "welcome"
            threading.Thread(target=self._speech_worker, daemon=True).start()

        if self.phase != "exit":
            self.w = _sstep((t - 4.9) / 1.4)

        if self.speaking:
            tgt = 0.35 + 0.65 * abs(0.55 * math.sin(t * 7.3) + 0.30 * math.sin(t * 3.1 + 1.0)
                                    + 0.15 * math.sin(t * 12.7 + 2.0))
        else:
            tgt = 0.07 + 0.04 * math.sin(t * 2.0)
        self.lvl += (tgt - self.lvl) * (1 - math.exp(-dt * 12))
        self.spin += dt * (40.0 + 110.0 * self.w * self.lvl)

        if self.phase == "welcome":
            if (self.hold_until is not None and t >= self.hold_until) or t >= WELCOME_AT + WELCOME_MAX:
                self._begin_exit()
        elif self.phase == "exit":
            self.exit_t += dt
            if self.exit_t >= EXIT_DUR:
                self.timer.stop()
                self.hide()
                if self.on_finished:
                    cb, self.on_finished = self.on_finished, None
                    cb()
                return
        self.update()

    # ------------------------------------------------------------------
    def paintEvent(self, ev):
        if self.t < 0:
            return
        t = self.t
        w = self.w
        lvl = self.lvl
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        NOPEN = Qt.PenStyle.NoPen
        NOBRUSH = Qt.BrushStyle.NoBrush
        CENTER = Qt.AlignmentFlag.AlignCenter

        W, H = self.width(), self.height()
        m = 26
        ex = min(1.0, self.exit_t / EXIT_DUR) if self.phase == "exit" else 0.0
        fade = 1.0 - _sstep((ex - 0.18) / 0.82)
        p.setOpacity(fade)

        R = min(W, H) * 0.17
        cx = W / 2
        cy = H / 2 - 24 - H * 0.07 * w
        center = QPointF(cx, cy)

        # ---- dark background ----
        bg = QRadialGradient(W / 2, H / 2, max(W, H) * 0.7)
        bg.setColorAt(0.0, QColor(7, 17, 36))
        bg.setColorAt(0.6, QColor(3, 7, 18))
        bg.setColorAt(1.0, QColor(1, 2, 6))
        p.fillRect(self.rect(), bg)

        cyan = QColor(0, 208, 255)
        blue = QColor(96, 140, 255)
        pink = QColor(255, 122, 224)
        appear = min(1.0, t / 1.0)
        boot_a = appear * (1.0 - w)          # sirf boot phase wali cheezein

        # ---- faint grid + scan line ----
        p.setPen(QPen(_rgba(cyan, 12 * appear), 1))
        for x in range(0, W, 48):
            p.drawLine(x, 0, x, H)
        for y in range(0, H, 48):
            p.drawLine(0, y, W, y)

        sy = ((t * 0.28) % 1.0) * H
        sg = QLinearGradient(0, sy - 60, 0, sy + 4)
        sg.setColorAt(0.0, _rgba(cyan, 0))
        sg.setColorAt(1.0, _rgba(cyan, 26 * appear))
        p.fillRect(QRectF(0, sy - 60, W, 64), sg)

        # ---- floating motes (welcome) ----
        if w > 0.01:
            p.setPen(NOPEN)
            for fx, fy, sz, sp, ph in self.motes:
                yy = (fy - t * sp * 0.04) % 1.0
                xx = fx + math.sin(t * 0.4 + ph) * 0.01
                p.setBrush(_rgba(cyan.lighter(130), (38 + 38 * math.sin(t * 1.3 + ph)) * w))
                p.drawEllipse(QPointF(xx * W, yy * H), sz, sz)
            p.setBrush(NOBRUSH)

        # ---- corner brackets ----
        L = 30
        p.setPen(QPen(_rgba(cyan, 150 * appear), 2))
        for (x, y, dx, dy) in ((m, m, 1, 1), (W - m, m, -1, 1), (m, H - m, 1, -1), (W - m, H - m, -1, -1)):
            p.drawLine(x, y, x + dx * L, y)
            p.drawLine(x, y, x, y + dy * L)

        # ---- corner texts ----
        hf = QFont("Consolas")
        hf.setPixelSize(12)
        p.setFont(hf)
        p.setPen(_rgba(cyan.lighter(130), 170 * appear))
        p.drawText(QPointF(m + 12, m + 26), "A.L.E.X.A  //  PERSONAL VOICE ASSISTANT")
        stamp = datetime.now().strftime("%d %b %Y   %H:%M:%S")
        fmh = QFontMetricsF(hf)
        p.drawText(QPointF(W - m - 12 - fmh.horizontalAdvance(stamp), m + 26), stamp)

        # ---- radar sweep (welcome) ----
        if w > 0.01:
            sw = QConicalGradient(cx, cy, (-t * 70) % 360)
            sw.setColorAt(0.0, _rgba(cyan, 85 * w))
            sw.setColorAt(0.22, _rgba(cyan, 0))
            sw.setColorAt(1.0, _rgba(cyan, 0))
            p.setPen(NOPEN)
            p.setBrush(sw)
            p.drawEllipse(center, R * 1.5, R * 1.5)
            p.setBrush(NOBRUSH)

        # ---- centre glow ----
        pulse = 0.5 + 0.5 * math.sin(t * 3.0)
        p.setPen(NOPEN)
        cg = QRadialGradient(cx, cy, R * 1.6)
        cg.setColorAt(0.0, _rgba(cyan, 70 * appear * (0.7 + 0.3 * pulse + 0.5 * w * lvl)))
        cg.setColorAt(0.5, _rgba(cyan, 22 * appear))
        cg.setColorAt(1.0, _rgba(cyan, 0))
        p.setBrush(cg)
        p.drawEllipse(center, R * 1.6, R * 1.6)
        p.setBrush(NOBRUSH)

        # ---- circular voice bars (welcome) ----
        if w > 0.01:
            n = 96
            base_r = R * 1.55 + 16
            bpen = QPen(Qt.PenStyle.SolidLine)
            bpen.setCapStyle(Qt.PenCapStyle.RoundCap)
            bpen.setWidthF(2.4)
            for i in range(n):
                a = math.tau * i / n - math.pi / 2 + t * 0.10
                wv = abs(math.sin(t * 3.2 + i * 0.55) * math.sin(t * 1.9 + i * 0.23))
                hh = 2.0 + (4.0 + 32.0 * lvl) * wv
                mix = 0.5 + 0.5 * math.sin(a * 2 + t)
                col = QColor(
                    int(cyan.red() + (pink.red() - cyan.red()) * mix * (lvl * 0.9)),
                    int(cyan.green() + (pink.green() - cyan.green()) * mix * (lvl * 0.9)),
                    int(cyan.blue() + (pink.blue() - cyan.blue()) * mix * (lvl * 0.9)),
                )
                bpen.setColor(_rgba(col.lighter(125), 215 * w))
                p.setPen(bpen)
                p.drawLine(QPointF(cx + math.cos(a) * base_r, cy + math.sin(a) * base_r),
                           QPointF(cx + math.cos(a) * (base_r + hh), cy + math.sin(a) * (base_r + hh)))

        # ---- neural nodes + lines (welcome) ----
        if w > 0.01:
            pts = []
            for ang0, orb_, spd, size, ph in self.nodes:
                a = ang0 + t * spd
                pts.append((cx + math.cos(a) * R * orb_, cy + math.sin(a) * R * orb_ * 0.62, size, ph))
            p.setBrush(NOBRUSH)
            for i in range(len(pts)):
                for j in range(i + 1, len(pts)):
                    d = math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1])
                    if d < R * 1.25:
                        p.setPen(QPen(_rgba(cyan, 70 * w * (1 - d / (R * 1.25))), 1.0))
                        p.drawLine(QPointF(pts[i][0], pts[i][1]), QPointF(pts[j][0], pts[j][1]))
            p.setPen(NOPEN)
            for x, y, size, ph in pts:
                al = (150 + 90 * math.sin(t * 2.2 + ph)) * w
                p.setBrush(_rgba(cyan, al * 0.25))
                p.drawEllipse(QPointF(x, y), size * 2.6, size * 2.6)
                p.setBrush(_rgba(QColor(200, 245, 255), al))
                p.drawEllipse(QPointF(x, y), size, size)
            p.setBrush(NOBRUSH)

        # ---- tick ring (dheere ghoomti) ----
        r_t = R * 1.55 * (0.6 + 0.4 * appear)
        p.save()
        p.translate(cx, cy)
        p.rotate(t * 14)
        for i in range(90):
            long_ = (i % 6 == 0)
            p.setPen(QPen(_rgba(cyan, (150 if long_ else 60) * appear), 1.4 if long_ else 1.0))
            p.save()
            p.rotate(i * 4)
            p.drawLine(QPointF(r_t, 0), QPointF(r_t + (10 if long_ else 5), 0))
            p.restore()
        p.restore()

        # ---- 3 moti arcs (speech ke saath tez ghoomte hain) ----
        r_a = R * 1.32
        apen = QPen(_rgba(cyan, 225 * appear), 3.6)
        apen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(apen)
        for i in range(3):
            p.drawArc(QRectF(cx - r_a, cy - r_a, 2 * r_a, 2 * r_a), int((-self.spin + i * 120) * 16), int(70 * 16))

        # ---- dotted ring (ulti disha) ----
        r_d = R * 1.14
        dpen = QPen(_rgba(blue, 200 * appear), 2.4)
        dpen.setCapStyle(Qt.PenCapStyle.RoundCap)
        dpen.setDashPattern([0.01, 4.0])
        dpen.setDashOffset(-t * 6)
        p.setPen(dpen)
        p.drawEllipse(center, r_d, r_d)

        # ---- progress ring: 0 -> 100% ----
        prog = _boot_progress(t)
        r_p = R * 0.98
        p.setPen(QPen(_rgba(cyan, 40 * appear), 5))
        p.drawEllipse(center, r_p, r_p)
        span = -int(360 * prog / 100.0 * 16)
        if span != 0:
            gpen = QPen(_rgba(cyan, 48), 13)
            gpen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(gpen)
            p.drawArc(QRectF(cx - r_p, cy - r_p, 2 * r_p, 2 * r_p), 90 * 16, span)
            bpen2 = QPen(_rgba(cyan.lighter(130), 255), 5)
            bpen2.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(bpen2)
            p.drawArc(QRectF(cx - r_p, cy - r_p, 2 * r_p, 2 * r_p), 90 * 16, span)

        # ---- inner disc + ghoomta hexagon ----
        p.setPen(QPen(_rgba(cyan, 90 * appear), 1.2))
        p.setBrush(_rgba(QColor(3, 10, 24), 215 * appear))
        p.drawEllipse(center, R * 0.80, R * 0.80)
        p.setBrush(NOBRUSH)
        hx = QPainterPath()
        for i in range(7):
            a = math.radians(i * 60 - t * 25)
            x, y = cx + math.cos(a) * R * 0.66, cy + math.sin(a) * R * 0.66
            if i == 0:
                hx.moveTo(x, y)
            else:
                hx.lineTo(x, y)
        p.setPen(QPen(_rgba(cyan, 80 * appear), 1.2))
        p.drawPath(hx)

        # ---- AI core (welcome): glow + pulse rings + voice waveform ----
        if w > 0.01:
            cr = R * (0.46 + 0.12 * lvl + 0.02 * math.sin(t * 5))
            core = QRadialGradient(cx, cy, cr * 1.7)
            core.setColorAt(0.0, QColor(255, 255, 255, int(120 * w)))
            core.setColorAt(0.35, _rgba(cyan.lighter(150), 120 * w))
            core.setColorAt(1.0, _rgba(cyan, 0))
            p.setPen(NOPEN)
            p.setBrush(core)
            p.drawEllipse(center, cr * 1.7, cr * 1.7)
            p.setBrush(NOBRUSH)

            for i in range(3):
                ph = (t * 0.7 + i / 3) % 1.0
                rr = R * (0.80 + 0.95 * ph)
                p.setPen(QPen(_rgba(cyan.lighter(140), 120 * (1 - ph) ** 1.5 * w * (0.25 + lvl)), 1.6))
                p.drawEllipse(center, rr, rr)

            # oscilloscope waveform
            wp = QPainterPath()
            half_w = R * 0.62
            amp = R * 0.30 * (0.12 + lvl)
            steps = 70
            for i in range(steps + 1):
                u = i / steps
                x = cx - half_w + 2 * half_w * u
                env = math.sin(math.pi * u) ** 1.3
                y = cy + env * amp * (math.sin(u * 17 + t * 9.0) * 0.65 + math.sin(u * 7.0 - t * 5.0) * 0.45)
                if i == 0:
                    wp.moveTo(x, y)
                else:
                    wp.lineTo(x, y)
            gl = QPen(_rgba(cyan, 70 * w), 7)
            gl.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(gl)
            p.drawPath(wp)
            wl = QPen(_rgba(QColor(215, 248, 255), 255 * w), 2.2)
            wl.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(wl)
            p.drawPath(wp)

        # ---- percent text (boot) ----
        pf = QFont("Segoe UI")
        pf.setPixelSize(int(R * 0.52))
        pf.setBold(True)
        p.setFont(pf)
        p.setPen(_rgba(QColor(210, 245, 255), 255 * boot_a))
        p.drawText(QRectF(cx - R, cy - R * 0.45, 2 * R, R * 0.9), CENTER, f"{int(prog)}%")

        # ---- "ALEXA" tag (boot: neeche, welcome: AI core ke neeche) ----
        sf = QFont("Segoe UI")
        sf.setPixelSize(int(max(9, R * 0.11)))
        sf.setBold(True)
        sf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4)
        p.setFont(sf)
        p.setPen(_rgba(cyan, 200 * appear))
        p.drawText(QRectF(cx - R, cy + R * 0.34 + R * 0.08 * w, 2 * R, R * 0.3), CENTER, "ALEXA")

        # ---- "ONLINE" burst ----
        if 4.85 < t < 5.75:
            k = (t - 4.85) / 0.9
            rr = R * (1.0 + 2.6 * k)
            p.setPen(QPen(_rgba(QColor(190, 240, 255), 210 * (1 - k) ** 1.5), 3))
            p.drawEllipse(center, rr, rr)
            fg = QRadialGradient(cx, cy, R * 3.0)
            fg.setColorAt(0.0, _rgba(QColor(255, 255, 255), 110 * (1 - k)))
            fg.setColorAt(0.4, _rgba(cyan, 60 * (1 - k)))
            fg.setColorAt(1.0, _rgba(cyan, 0))
            p.setPen(NOPEN)
            p.setBrush(fg)
            p.drawEllipse(center, R * 3.0, R * 3.0)
            p.setBrush(NOBRUSH)

        # ---- typing title + loading bar + log (sirf boot) ----
        if boot_a > 0.01:
            online = t >= 4.85
            title = "ALEXA ONLINE" if online else "INITIALIZING ALEXA"
            cnt = int(max(0.0, t - 4.85) * 20) if online else int(max(0.0, t - 0.3) * 16)
            tf = QFont("Segoe UI")
            tf.setPixelSize(int(max(14, R * 0.20)))
            tf.setBold(True)
            tf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 5)
            p.setFont(tf)
            fullw = QFontMetricsF(tf).horizontalAdvance(title)
            ty = cy + R * 1.85
            cursor = "▌" if (int(t * 4) % 2 == 0 and cnt < len(title) + 4) else ""
            p.setPen(_rgba(QColor(190, 255, 230) if online else cyan.lighter(150), 240 * boot_a))
            p.drawText(QPointF(cx - fullw / 2, ty), title[:cnt] + cursor)

            bw = min(W * 0.46, 520.0)
            bh = 6.0
            bx, by = cx - bw / 2, ty + 22
            p.setPen(NOPEN)
            p.setBrush(_rgba(cyan, 28 * boot_a))
            p.drawRoundedRect(QRectF(bx, by, bw, bh), 3, 3)
            fw = bw * prog / 100.0
            if fw > 1:
                gl2 = QLinearGradient(bx, 0, bx + bw, 0)
                gl2.setColorAt(0.0, blue)
                gl2.setColorAt(1.0, cyan)
                p.setBrush(_rgba(cyan, 50 * (1 - w)))
                p.drawRoundedRect(QRectF(bx - 2, by - 3, fw + 4, bh + 6), 5, 5)
                p.setOpacity(fade * (1 - w))
                p.setBrush(gl2)
                p.drawRoundedRect(QRectF(bx, by, fw, bh), 3, 3)
                p.setOpacity(fade)
            p.setBrush(NOBRUSH)
            lf2 = QFont("Consolas")
            lf2.setPixelSize(11)
            p.setFont(lf2)
            p.setPen(_rgba(cyan.lighter(130), 170 * boot_a))
            p.drawText(QPointF(bx, by + 24), "SYSTEM LOAD")
            pr = f"{int(prog)}%"
            p.drawText(QPointF(bx + bw - QFontMetricsF(lf2).horizontalAdvance(pr), by + 24), pr)

            lg = QFont("Consolas")
            lg.setPixelSize(12)
            p.setFont(lg)
            total = len(BOOT_LINES)
            for idx, (at, txt) in enumerate(BOOT_LINES):
                if t < at:
                    continue
                chars = int((t - at) * 40)
                done = chars >= len(txt) + 3
                shown = "> " + txt[:chars] + ("   ✓" if done else "")
                last = idx == total - 1
                col = QColor(120, 255, 190) if (done and last) else (cyan.lighter(150) if not done else QColor(0, 170, 220))
                p.setPen(_rgba(col, 235 * (1 - w)))
                p.drawText(QPointF(m + 12, H - m - 12 - (total - 1 - idx) * 18), shown)

        # ==================================================================
        # WELCOME phase: side panels + subtitles + lower thirds
        # ==================================================================
        if w > 0.02:
            self._paint_panels(p, W, H, m, cx, cy, R, w, lvl, t, cyan)
            self._paint_subtitle(p, W, H, cx, cy, R, w, t, cyan, pink)

            if self.phase == "welcome":
                kf = QFont("Consolas")
                kf.setPixelSize(11)
                p.setFont(kf)
                p.setPen(_rgba(cyan.lighter(130), 90 + 40 * math.sin(t * 3)))
                txt = "CLICK TO SKIP  ▸▸"
                p.drawText(QPointF(W - m - 12 - QFontMetricsF(kf).horizontalAdvance(txt), H - m - 12), txt)

        # ---- exit: shockwave + flash ----
        if self.phase == "exit":
            k = min(1.0, ex / 0.45)
            p.setOpacity(1.0)
            p.setBrush(NOBRUSH)
            rr = R * (1.0 + 6.5 * k)
            p.setPen(QPen(_rgba(QColor(200, 245, 255), 230 * (1 - k) ** 1.3), 3.0))
            p.drawEllipse(center, rr, rr)
            rr2 = R * (1.0 + 4.0 * max(0.0, k - 0.1))
            p.setPen(QPen(_rgba(cyan, 150 * (1 - k) ** 1.3), 2.0))
            p.drawEllipse(center, rr2, rr2)
            fg2 = QRadialGradient(cx, cy, R * 4.0)
            fg2.setColorAt(0.0, _rgba(QColor(255, 255, 255), 150 * (1 - k)))
            fg2.setColorAt(0.5, _rgba(cyan, 60 * (1 - k)))
            fg2.setColorAt(1.0, _rgba(cyan, 0))
            p.setPen(NOPEN)
            p.setBrush(fg2)
            p.drawEllipse(center, R * 4.0, R * 4.0)

        p.end()

    # ------------------------------------------------------------------
    def _paint_panels(self, p, W, H, m, cx, cy, R, w, lvl, t, cyan):
        if W < 1000:
            return
        NOPEN = Qt.PenStyle.NoPen
        pw = 200.0
        py = cy - R * 1.15
        hf = QFont("Consolas")
        hf.setPixelSize(11)
        hf.setBold(True)
        hf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        tf = QFont("Consolas")
        tf.setPixelSize(11)

        # ---- left: system status ----
        px = m + 16
        p.setFont(hf)
        p.setPen(_rgba(cyan.lighter(140), 210 * w))
        p.drawText(QPointF(px, py), "SYSTEM STATUS")
        p.setPen(QPen(_rgba(cyan, 90 * w), 1))
        p.drawLine(QPointF(px, py + 8), QPointF(px + pw * w, py + 8))
        p.setFont(tf)
        for i, name in enumerate(self.MODULES):
            a = _sstep(w * 1.7 - i * 0.2)
            if a <= 0.01:
                continue
            y = py + 34 + i * 38
            p.setPen(_rgba(cyan.lighter(150), 215 * a))
            p.drawText(QPointF(px, y), name)
            st = "ONLINE" if a > 0.95 else "..."
            p.setPen(_rgba(QColor(120, 255, 190), 230 * a))
            p.drawText(QPointF(px + pw - QFontMetricsF(tf).horizontalAdvance(st), y), st)
            p.setPen(NOPEN)
            p.setBrush(_rgba(cyan, 26 * a))
            p.drawRoundedRect(QRectF(px, y + 7, pw, 3), 1.5, 1.5)
            val = min(1.0, a * 1.3) * (0.80 + 0.20 * math.sin(t * (0.8 + 0.25 * i) + i))
            p.setBrush(_rgba(cyan.lighter(125), 210 * a))
            p.drawRoundedRect(QRectF(px, y + 7, pw * val, 3), 1.5, 1.5)
            p.setBrush(Qt.BrushStyle.NoBrush)

        # ---- right: data stream + equalizer ----
        px2 = W - m - 16 - pw
        p.setFont(hf)
        p.setPen(_rgba(cyan.lighter(140), 210 * w))
        p.drawText(QPointF(px2, py), "DATA STREAM")
        p.setPen(QPen(_rgba(cyan, 90 * w), 1))
        p.drawLine(QPointF(px2 + pw - pw * w, py + 8), QPointF(px2 + pw, py + 8))
        p.setFont(tf)
        speed = 14.0
        row0 = int(t * speed / 18.0)
        off = (t * speed) % 18.0
        rows = 11
        for i in range(rows + 1):
            row = row0 + i
            rnd = random.Random(row * 7919 + 13)
            txt = "%04X  %08X  %02X" % (rnd.randrange(65536), rnd.randrange(2 ** 32), rnd.randrange(256))
            y = py + 34 + (rows - i) * 18 - (18 - off)
            edge = min(1.0, (i + 0.5) / 2.0, (rows - i + 0.5) / 2.0)
            p.setPen(_rgba(cyan.lighter(130), (70 + 70 * rnd.random()) * w * max(0.0, edge)))
            p.drawText(QPointF(px2, y), txt)

        # equalizer
        ey = py + 34 + (rows + 1) * 18 + 22
        p.setPen(NOPEN)
        for i in range(22):
            hh = 3 + (4 + 34 * lvl) * abs(math.sin(t * 5.0 + i * 0.6) * math.sin(t * 2.3 + i * 0.21))
            p.setBrush(_rgba(cyan.lighter(130), 200 * w))
            p.drawRoundedRect(QRectF(px2 + i * (pw / 22.0), ey + 40 - hh, 6.0, hh), 2, 2)
        p.setBrush(Qt.BrushStyle.NoBrush)

    # ------------------------------------------------------------------
    def _paint_subtitle(self, p, W, H, cx, cy, R, w, t, cyan, pink):
        if self.cur_line < 0 or self.phase == "boot":
            return
        NOPEN = Qt.PenStyle.NoPen
        text, kind = self.lines[self.cur_line]
        dt = max(0.0, t - self.line_t0)
        a_in = min(1.0, dt / 0.25) * w

        sf = QFont("Segoe UI")
        sf.setPixelSize(22)
        sf.setBold(True)
        sf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        fm = QFontMetricsF(sf)
        maxw = min(W * 0.66, 900.0)
        wrapped = _wrap_text(text, fm, maxw)

        top = cy + R * 1.95 + 34
        # ---- tag ----
        tg = QFont("Consolas")
        tg.setPixelSize(11)
        tg.setBold(True)
        tg.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        p.setFont(tg)
        tag = "◉  ALEXA  •  SPEAKING" if self.speaking else "◉  ALEXA  •  STANDBY"
        tcol = pink if self.speaking else cyan
        tw = QFontMetricsF(tg).horizontalAdvance(tag)
        p.setPen(_rgba(tcol.lighter(120), 220 * w * (0.7 + 0.3 * math.sin(t * 6.0) if self.speaking else 0.8 * w)))
        p.drawText(QPointF(cx - tw / 2, top - 8), tag)

        # ---- typed subtitle (har line apni final jagah par, sirf akshar aate hain) ----
        total = len(text) + 1
        shown = total if self.line_full else int(dt * 21)
        p.setFont(sf)
        y = top + 24
        used = 0
        for ln in wrapped:
            n = max(0, min(len(ln), shown - used))
            x0 = cx - fm.horizontalAdvance(ln) / 2
            if n > 0:
                seg = ln[:n]
                p.setPen(_rgba(cyan, 60 * a_in))
                p.drawText(QPointF(x0 - 1, y + 1), seg)
                p.drawText(QPointF(x0 + 1, y + 1), seg)
                p.setPen(_rgba(QColor(228, 246, 255), 255 * a_in))
                p.drawText(QPointF(x0, y), seg)
                if n < len(ln) and not self.line_full:
                    cxp = x0 + fm.horizontalAdvance(seg)
                    p.setPen(_rgba(cyan.lighter(150), 230 * a_in * (1.0 if int(t * 5) % 2 == 0 else 0.25)))
                    p.drawText(QPointF(cxp, y), "▌")
            used += len(ln) + 1
            y += 32

        after = y + 6
        prog = 1.0 if self.line_full else min(1.0, dt / max(0.5, len(text) / 19.0))

        # ---- lower third: capabilities chips ----
        if kind == "caps":
            cf = QFont("Consolas")
            cf.setPixelSize(12)
            cf.setBold(True)
            cf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
            cfm = QFontMetricsF(cf)
            widths = [cfm.horizontalAdvance(c) + 28 for c in self.CHIPS]
            tot = sum(widths) + 10 * (len(widths) - 1)
            x = cx - tot / 2
            lit = len(self.CHIPS) if self.line_full else int(prog * len(self.CHIPS) * 1.15)
            p.setFont(cf)
            for i, (c, cw) in enumerate(zip(self.CHIPS, widths)):
                on = i < lit
                rect = QRectF(x, after, cw, 26)
                if on:
                    p.setPen(NOPEN)
                    p.setBrush(_rgba(cyan, 48 * a_in))
                    p.drawRoundedRect(rect.adjusted(-3, -3, 3, 3), 12, 12)
                p.setPen(QPen(_rgba(cyan, (230 if on else 55) * a_in), 1.2))
                p.setBrush(_rgba(QColor(4, 14, 30), 200 * a_in))
                p.drawRoundedRect(rect, 10, 10)
                p.setPen(_rgba(QColor(215, 248, 255) if on else cyan, (255 if on else 90) * a_in))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, c)
                x += cw + 10
            p.setBrush(Qt.BrushStyle.NoBrush)

        # ---- lower third: creator banner (glitch reveal) ----
        elif kind == "creator":
            gold = QColor(255, 206, 120)
            name = "AKSHAT RAJPUT"
            nf = QFont("Segoe UI")
            nf.setPixelSize(32)
            nf.setBold(True)
            nf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 9)
            nfm = QFontMetricsF(nf)
            fullw = nfm.horizontalAdvance(name)
            rev = _sstep(dt / 1.2)
            n_real = int(max(0.0, dt - 0.35) * 11)
            glyphs = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#$%&@"
            out = ""
            for i, ch in enumerate(name):
                if ch == " " or i < n_real or self.line_full:
                    out += ch
                elif i < n_real + 3:
                    out += glyphs[(int(t * 25) * 7 + i * 13) % len(glyphs)]
                else:
                    out += " "
            small = QFont("Consolas")
            small.setPixelSize(11)
            small.setBold(True)
            small.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 5)
            p.setFont(small)
            sw_ = QFontMetricsF(small).horizontalAdvance("CREATED BY")
            p.setPen(_rgba(gold, 200 * a_in))
            p.drawText(QPointF(cx - sw_ / 2, after + 6), "CREATED BY")
            p.setFont(nf)
            p.setPen(_rgba(gold, 70 * a_in))
            p.drawText(QPointF(cx - fullw / 2 + 1, after + 44), out)
            p.setPen(_rgba(QColor(255, 240, 205), 255 * a_in))
            p.drawText(QPointF(cx - fullw / 2, after + 43), out)
            ln_w = 140.0 * rev
            p.setPen(QPen(_rgba(gold, 200 * a_in), 1.4))
            p.drawLine(QPointF(cx - fullw / 2 - 24 - ln_w, after + 30), QPointF(cx - fullw / 2 - 24, after + 30))
            p.drawLine(QPointF(cx + fullw / 2 + 24, after + 30), QPointF(cx + fullw / 2 + 24 + ln_w, after + 30))

        # ---- lower third: ready ----
        elif kind == "ready":
            rf = QFont("Consolas")
            rf.setPixelSize(13)
            rf.setBold(True)
            rf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4)
            p.setFont(rf)
            msg = "SAY  “ALEXA”  TO  WAKE  ME  UP"
            mw = QFontMetricsF(rf).horizontalAdvance(msg)
            p.setPen(_rgba(QColor(150, 255, 210), (150 + 90 * math.sin(t * 3.2)) * a_in * min(1.0, prog * 1.5)))
            p.drawText(QPointF(cx - mw / 2, after + 14), msg)


# ----------------------------------------------------------------------
# DEVICE INFO CARD  (hover pe zoom-in)
# ----------------------------------------------------------------------

class InfoCard(QFrame):

    def __init__(self, title, bar_color=None):
        super().__init__()
        self.setObjectName("card")
        self.setFixedHeight(68)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(11, 7, 11, 7)
        lay.setSpacing(2)

        self.title = QLabel(title)
        self.title.setStyleSheet("color:#8fc4e0;")
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self.value = QLabel("--")
        self.value.setStyleSheet("color:#eaf9ff;")
        self.value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        lay.addWidget(self.title)
        lay.addWidget(self.value)

        self.bar = None
        if bar_color:
            self.bar = QProgressBar()
            self.bar.setRange(0, 100)
            self.bar.setTextVisible(False)
            self.bar.setFixedHeight(4)
            self.bar.setStyleSheet(
                "QProgressBar {background:#12304d; border:none; border-radius:2px;}"
                f"QProgressBar::chunk {{background:{bar_color}; border-radius:2px;}}"
            )
            lay.addWidget(self.bar)

        lay.addStretch(1)

        self.fx = QGraphicsDropShadowEffect(self)
        self.fx.setOffset(0, 0)
        self.fx.setBlurRadius(0)
        self.fx.setColor(QColor(0, 208, 255, 0))
        self.setGraphicsEffect(self.fx)

        self._hot = False
        self.set_zoom(0.0)

    def set_zoom(self, z):
        self.title.setFont(_font(7.2 + 2.4 * z))
        self.value.setFont(_font(9.2 + 3.4 * z))

        self.fx.setBlurRadius(36 * z)
        self.fx.setColor(QColor(0, 208, 255, int(170 * z)))

        hot = z > 0.3
        if hot != self._hot:
            self._hot = hot
            self.setStyleSheet(
                "QFrame#card {background-color:#08263d; border:1px solid #00d0ff; border-radius:14px;}"
                if hot else ""
            )

    def set(self, text, percent=None):
        if len(text) > 22:
            text = text[:21] + "…"
        self.value.setText(text)
        if self.bar is not None and percent is not None:
            self.bar.setValue(int(max(0, min(100, percent))))


def _rate(b):
    if b >= 1024 ** 2:
        return f"{b / 1024 ** 2:.1f}M"
    if b >= 1024:
        return f"{b / 1024:.0f}K"
    return f"{b:.0f}B"


# ----------------------------------------------------------------------
# CHAT VIEW  (sundar bubbles + Alexa ke jawab ka typewriter effect)
# ----------------------------------------------------------------------

class ChatView(QFrame):
    """
    YOU   : right side, cyan bubble
    ALEXA : left side, purple bubble, text akshar-akshar type hota hai (blinking cursor ke saath)
    Naye message par smooth fade-in + auto scroll (agar user upar scroll kare to zabardasti neeche nahi le jaata).
    """

    CPS = 34.0      # typing speed (characters / second)

    def __init__(self):
        super().__init__()
        self.setObjectName("chat")
        self.setMinimumHeight(120)
        self._items = []          # (row, bubble)
        self._typer = None
        self._follow = True
        self._anims = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            "QScrollArea {background: transparent; border: none;}"
            "QScrollArea > QWidget > QWidget {background: transparent;}"
        )
        outer.addWidget(self.scroll)

        inner = QWidget()
        inner.setObjectName("chatInner")
        inner.setStyleSheet("QWidget#chatInner {background: transparent;}")
        self.body = QVBoxLayout(inner)
        self.body.setContentsMargins(10, 10, 10, 10)
        self.body.setSpacing(12)

        self.empty = QLabel("Your conversation will appear here...")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setStyleSheet("color: #5f8fb0; font-size: 13px; padding: 24px;")
        self.body.addWidget(self.empty)
        self.body.addStretch(1)
        self.scroll.setWidget(inner)

        sb = self.scroll.verticalScrollBar()
        sb.rangeChanged.connect(self._on_range)
        sb.valueChanged.connect(self._on_value)

        self._type_timer = QTimer(self)
        self._type_timer.timeout.connect(self._type_step)

        self.set_accent("#4fb8ff", False)

    # ------------------------------------------------------------------
    def set_accent(self, acc, active):
        self.setStyleSheet(
            "QFrame#chat {"
            "background-color: rgba(5,14,30,215);"
            f"border: {2 if active else 1}px solid {acc if active else '#17406a'};"
            "border-radius: 16px;"
            "}"
        )

    def _on_range(self, lo, hi):
        if self._follow:
            self.scroll.verticalScrollBar().setValue(hi)

    def _on_value(self, v):
        self._follow = v >= self.scroll.verticalScrollBar().maximum() - 30

    def _max_bubble(self):
        return max(200, int(self.scroll.viewport().width() * 0.80) - 50)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        mw = self._max_bubble()
        for _row, bubble in self._items:
            bubble.setMaximumWidth(mw)

    # ------------------------------------------------------------------
    def clear(self):
        self._finish_typing()
        for row, _b in self._items:
            self.body.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._items.clear()
        self.empty.show()
        self._follow = True

    def _finish_typing(self):
        ty = self._typer
        self._typer = None
        self._type_timer.stop()
        if ty is not None:
            ty["lbl"].setText(ty["text"])
            ty["lbl"].setMinimumSize(0, 0)

    # ------------------------------------------------------------------
    def add(self, role, text):
        self._finish_typing()
        you = str(role).upper() == "YOU"
        text = str(text)
        self.empty.hide()

        if you:
            grad = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0f6a92, stop:1 #0a3a63)"
            border, name_col, av_bg, av_fg = "#2cc4f0", "#9af0ff", "#0f6a92", "#d9fbff"
            radius = "border-radius: 16px; border-bottom-right-radius: 4px;"
            name = "YOU"
        else:
            grad = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #14407a, stop:1 #0a2150)"
            border, name_col, av_bg, av_fg = "#00d0ff", "#bff3ff", "#0f5fa8", "#ffffff"
            radius = "border-radius: 16px; border-bottom-left-radius: 4px;"
            name = "ALEXA"

        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        bubble = QFrame()
        bubble.setObjectName("bubble")
        bubble.setStyleSheet(
            f"QFrame#bubble {{background: {grad}; border: 1px solid {border}; {radius}}}"
        )
        max_w = self._max_bubble()
        bubble.setMaximumWidth(max_w)
        v = QVBoxLayout(bubble)
        v.setContentsMargins(14, 8, 14, 10)
        v.setSpacing(3)

        hdr = QHBoxLayout()
        hdr.setSpacing(10)
        nm = QLabel(name)
        nf = _font(7.6)
        nf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        nm.setFont(nf)
        nm.setStyleSheet(f"color: {name_col}; background: transparent;")
        st = QLabel(datetime.now().strftime("%I:%M %p"))
        st.setFont(_font(7.2, bold=False))
        st.setStyleSheet("color: rgba(255,255,255,120); background: transparent;")
        hdr.addWidget(nm)
        hdr.addStretch(1)
        hdr.addWidget(st)
        v.addLayout(hdr)

        lbl = QLabel()
        lbl.setTextFormat(Qt.TextFormat.PlainText)
        lbl.setWordWrap(True)
        lbl.setFont(_font(11.2, bold=False))
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lbl.setStyleSheet("color: #ffffff; background: transparent;")
        v.addWidget(lbl)

        av = QLabel("Y" if you else "A")
        av.setFixedSize(30, 30)
        av.setAlignment(Qt.AlignmentFlag.AlignCenter)
        av.setFont(_font(9.5))
        av.setStyleSheet(
            f"background-color: {av_bg}; color: {av_fg}; border: 1px solid {border}; border-radius: 15px;"
        )

        if you:
            h.addStretch(1)
            h.addWidget(bubble, 0)
            h.addWidget(av, 0, Qt.AlignmentFlag.AlignTop)
        else:
            h.addWidget(av, 0, Qt.AlignmentFlag.AlignTop)
            h.addWidget(bubble, 0)
            h.addStretch(1)

        self.body.insertWidget(self.body.count() - 1, row)
        self._items.append((row, bubble))

        # ---- text ----
        if you or not text:
            lbl.setText(text)
        else:
            inner_w = max_w - 30
            flags = Qt.TextFlag.TextWordWrap.value | Qt.AlignmentFlag.AlignLeft.value
            rect = QFontMetrics(lbl.font()).boundingRect(0, 0, inner_w, 100000, flags, text)
            # bubble pehle se poore size ka rahe, taaki type hote waqt chhota-bada na ho
            lbl.setMinimumSize(min(rect.width() + 4, inner_w), rect.height() + 2)
            lbl.setText("▌")
            self._typer = {"lbl": lbl, "text": text, "pos": 0.0, "cps": max(self.CPS, len(text) / 4.5)}
            self._type_timer.start(30)

        self._fade_in(row)
        if self._follow:
            QTimer.singleShot(0, self._to_bottom)

    def _to_bottom(self):
        sb = self.scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _fade_in(self, row):
        eff = QGraphicsOpacityEffect(row)
        eff.setOpacity(0.0)
        row.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(320)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def done(r=row, a=anim):
            try:
                r.setGraphicsEffect(None)
            except RuntimeError:
                pass
            if a in self._anims:
                self._anims.remove(a)

        anim.finished.connect(done)
        anim.start()
        self._anims.append(anim)

    def _type_step(self):
        ty = self._typer
        if ty is None:
            self._type_timer.stop()
            return
        ty["pos"] += ty["cps"] * 0.03
        n = int(ty["pos"])
        full = ty["text"]
        if n >= len(full):
            ty["lbl"].setText(full)
            ty["lbl"].setMinimumSize(0, 0)
            self._typer = None
            self._type_timer.stop()
            return
        blink = "▌" if int(ty["pos"] / max(1.0, ty["cps"] * 0.25)) % 2 == 0 or n < 3 else " "
        ty["lbl"].setText(full[:n] + blink)
        if self._follow:
            self._to_bottom()


# ----------------------------------------------------------------------
# HUD BACKGROUND  (main screen ka jeevant background: welcome jaisi cyan HUD theme)
# ----------------------------------------------------------------------

class HudBackground(QWidget):
    """
    Main screen ke peeche chalta animated background. Welcome / boot screen jaisi hi theme:
    dark navy + cyan HUD grid + scan line. Rang Alexa ki state ke hisaab se thoda badalta hai
    (sleeping = blue-cyan, listening = cyan, speaking = pink).
      - dheere behte colour glows
      - halka seedha HUD grid + upar se neeche chalti scan line (boot screen jaisi)
      - neeche perspective floor grid (aapki taraf aati lines)
      - tairte particles + unke beech network lines
      - dheere chalti scan beam
      - upar / neeche chalti light strip, pulsing corner brackets, side rulers
      - corner HUD texts (A.L.E.X.A // PERSONAL VOICE ASSISTANT + live time)
    """

    def __init__(self):
        super().__init__()
        self.t = 0.0
        self.last = perf_counter()
        self.acc = [79.0, 184.0, 255.0]
        self.tgt = [79.0, 184.0, 255.0]
        rnd = random.Random(21)
        # x, y, vx, vy, size, phase
        self.pts = [
            [rnd.random(), rnd.random(), rnd.uniform(-0.012, 0.012), rnd.uniform(-0.010, 0.010),
             rnd.uniform(1.0, 2.4), rnd.uniform(0, math.tau)]
            for _ in range(46)
        ]
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.step)
        self.timer.start(33)

    def set_accent(self, color):
        self.tgt = [float(color.red()), float(color.green()), float(color.blue())]

    def step(self):
        now = perf_counter()
        dt = min(0.08, max(0.001, now - self.last))
        self.last = now
        self.t += dt
        k = 1 - math.exp(-dt * 3.0)
        for i in range(3):
            self.acc[i] += (self.tgt[i] - self.acc[i]) * k
        for pt in self.pts:
            pt[0] = (pt[0] + pt[2] * dt) % 1.0
            pt[1] = (pt[1] + pt[3] * dt) % 1.0
        self.update()

    def paintEvent(self, ev):
        t = self.t
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        NOPEN = Qt.PenStyle.NoPen
        W, H = self.width(), self.height()
        ac = QColor(int(self.acc[0]), int(self.acc[1]), int(self.acc[2]))
        cyan = QColor(0, 208, 255)

        # ---- base (boot screen jaisa dark navy) ----
        base = QRadialGradient(W / 2, H / 2, max(W, H) * 0.7)
        base.setColorAt(0.0, QColor(7, 17, 36))
        base.setColorAt(0.6, QColor(3, 7, 18))
        base.setColorAt(1.0, QColor(1, 2, 6))
        p.fillRect(self.rect(), base)

        # ---- behte colour glows ----
        for fx, fy, ph, rad in ((0.22, 0.45, 0.0, 0.55), (0.80, 0.30, 2.1, 0.50), (0.55, 0.85, 4.0, 0.40)):
            ox = math.cos(t * 0.15 + ph) * 0.09 * W
            oy = math.sin(t * 0.12 + ph) * 0.09 * H
            g = QRadialGradient(fx * W + ox, fy * H + oy, rad * max(W, H) * 0.6)
            g.setColorAt(0.0, _rgba(ac, 36))
            g.setColorAt(1.0, _rgba(ac, 0))
            p.fillRect(self.rect(), g)

        # ---- faint HUD grid + scan line (boot screen jaisa) ----
        p.setPen(QPen(_rgba(cyan, 11), 1))
        for x in range(0, W, 48):
            p.drawLine(x, 0, x, H)
        for y in range(0, H, 48):
            p.drawLine(0, y, W, y)

        sy = ((t * 0.20) % 1.0) * H
        sg = QLinearGradient(0, sy - 60, 0, sy + 4)
        sg.setColorAt(0.0, _rgba(cyan, 0))
        sg.setColorAt(1.0, _rgba(cyan, 24))
        p.fillRect(QRectF(0, sy - 60, W, 64), sg)

        # ---- perspective floor grid ----
        y0 = H * 0.72
        vx = W / 2
        p.setPen(QPen(_rgba(ac, 20), 1))
        for i in range(-16, 17):
            p.drawLine(QPointF(vx + i * 6, y0), QPointF(vx + i * W * 0.085, H))
        rows = 11
        sh = (t * 0.22) % 1.0
        for j in range(rows):
            f = (j + sh) / rows
            y = y0 + (H - y0) * f * f
            p.setPen(QPen(_rgba(ac, 8 + 30 * f), 1))
            p.drawLine(QPointF(0, y), QPointF(W, y))

        # ---- particles + network ----
        pos = [(pt[0] * W, pt[1] * H, pt[4], pt[5]) for pt in self.pts]
        for i in range(len(pos)):
            xi, yi = pos[i][0], pos[i][1]
            for j in range(i + 1, len(pos)):
                dx = xi - pos[j][0]
                if dx > 150 or dx < -150:
                    continue
                d = math.hypot(dx, yi - pos[j][1])
                if d < 150:
                    p.setPen(QPen(_rgba(ac, 46 * (1 - d / 150.0)), 1))
                    p.drawLine(QPointF(xi, yi), QPointF(pos[j][0], pos[j][1]))
        p.setPen(NOPEN)
        for x, y, sz, ph in pos:
            a = 90 + 70 * math.sin(t * 1.4 + ph)
            p.setBrush(_rgba(ac, a * 0.25))
            p.drawEllipse(QPointF(x, y), sz * 2.6, sz * 2.6)
            p.setBrush(_rgba(ac.lighter(150), a))
            p.drawEllipse(QPointF(x, y), sz, sz)
        p.setBrush(Qt.BrushStyle.NoBrush)

        # ---- scan beam (left -> right) ----
        bx = ((t * 0.045) % 1.3 - 0.15) * W
        bg = QLinearGradient(bx - 90, 0, bx + 90, 0)
        bg.setColorAt(0.0, _rgba(ac, 0))
        bg.setColorAt(0.5, _rgba(ac, 15))
        bg.setColorAt(1.0, _rgba(ac, 0))
        p.fillRect(QRectF(bx - 90, 0, 180, H), bg)

        # ---- top / bottom travelling light strips ----
        for yy, direction in ((1.5, 1.0), (H - 1.5, -1.0)):
            pp = ((t * 0.16) % 1.2 - 0.1) * W
            if direction < 0:
                pp = W - pp
            lg = QLinearGradient(pp - 220, 0, pp + 220, 0)
            lg.setColorAt(0.0, _rgba(ac.lighter(140), 0))
            lg.setColorAt(0.5, _rgba(ac.lighter(160), 210))
            lg.setColorAt(1.0, _rgba(ac.lighter(140), 0))
            p.setPen(QPen(QBrush(lg), 2.0))
            p.drawLine(QPointF(0, yy), QPointF(W, yy))

        # ---- pulsing corner brackets ----
        pa = 90 + 70 * (0.5 + 0.5 * math.sin(t * 2.0))
        p.setPen(QPen(_rgba(ac.lighter(150), pa), 2))
        m, L = 8, 26
        for (x, y, dx, dy) in ((m, m, 1, 1), (W - m, m, -1, 1), (m, H - m, 1, -1), (W - m, H - m, -1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + dx * L, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + dy * L))

        # ---- corner HUD texts (boot screen jaise) ----
        hf = QFont("Consolas")
        hf.setPixelSize(10)
        p.setFont(hf)
        p.setPen(_rgba(cyan.lighter(130), 120))
        p.drawText(QPointF(m + 14, m + 20), "A.L.E.X.A  //  PERSONAL VOICE ASSISTANT")
        stamp = datetime.now().strftime("%d %b %Y   %H:%M:%S")
        p.drawText(QPointF(W - m - 14 - QFontMetricsF(hf).horizontalAdvance(stamp), m + 20), stamp)

        # ---- side rulers (ticks upar chadhte hue) ----
        off = (t * 10.0) % 14.0
        n0 = int(t * 10.0 / 14.0)
        for side in (0, 1):
            x = 5 if side == 0 else W - 5
            sgn = 1 if side == 0 else -1
            y = H - off
            k = 0
            while y > 0:
                major = ((n0 + k) % 5 == 0)
                p.setPen(QPen(_rgba(ac, 70 if major else 28), 1))
                p.drawLine(QPointF(x, y), QPointF(x + sgn * (9 if major else 4), y))
                y -= 14.0
                k += 1

        p.end()


# ----------------------------------------------------------------------
# WINDOW
# ----------------------------------------------------------------------

class AssistantWindow(QMainWindow):

    # listen() 30 sec tak legit chal sakta hai, isliye 45 sec ke baad hi "stuck" maanenge
    STUCK_AFTER = 45

    def closeEvent(self, event):
        event.ignore()

    def __init__(self):

        super().__init__()

        self.state = "SLEEPING"
        self.accent = QColor("#4fb8ff")
        self.hl = 0.0
        self.pt = 0.0
        self.hover = []          # [widget, z, fn]
        self._last_log = ""      # terminal panel ke liye (repeat lines rokne ko)
        self._reveals = []       # intro: (kab, holder, effect)
        self._anims = []
        self._restarting = False
        # stuck ginti: restart ke baad bhi yaad rehti hai (env se aati hai)
        try:
            self.stuck_count = int(os.environ.get("ALEXA_STUCK_COUNT", "0"))
        except ValueError:
            self.stuck_count = 0
        self.stuck_last = os.environ.get("ALEXA_STUCK_LAST", "")
        self.stuck_stage = os.environ.get("ALEXA_STUCK_STAGE", "")

        self.setWindowTitle("ALEXA - Personal Assistant  |  Developer: Akshat Rajput")
        self.resize(1580, 740)   # terminal panel + stuck column ke liye chauda kiya

        self.setStyleSheet("""
            QMainWindow {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                                  stop:0 #030a1a, stop:0.55 #040c1c, stop:1 #010206);
            }

            QLabel {
                color: #eaf9ff;
            }

            QFrame#card {
                background-color: rgba(5, 16, 32, 205);
                border: 1px solid #17406a;
                border-radius: 14px;
            }

            QTextEdit {
                background-color: #050e1e;
                color: #eaf9ff;
                border: 1px solid #17406a;
                border-radius: 16px;
                padding: 12px;
                font-size: 14px;
            }

            QPushButton#clear {
                color: #b9e6f7;
                background-color: #0b2340;
                border: 1px solid #1c5a82;
                border-radius: 11px;
                padding: 3px 14px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton#clear:hover {
                color: #ffffff;
                background-color: #0f3a66;
                border: 1px solid #00d0ff;
            }

            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 6px 2px;
            }
            QScrollBar::handle:vertical {
                background: #1c5a82;
                border-radius: 3px;
                min-height: 26px;
            }
            QScrollBar::handle:vertical:hover {
                background: #00a8d8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

        central = HudBackground()           # animated HUD background
        self.bg = central
        self.setCentralWidget(central)

        layout = QHBoxLayout(central)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(24)

        left = QVBoxLayout()
        left.setSpacing(8)
        right = QVBoxLayout()
        right.setSpacing(10)

        # ---------------- header ----------------
        heading = QLabel("A L E X A")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setFixedHeight(62)
        heading.setFont(_font(25))
        heading.setStyleSheet("color: #b8f2ff;")

        self.heading = heading
        self.heading_fx = QGraphicsDropShadowEffect(heading)
        self.heading_fx.setOffset(0, 0)
        self.heading_fx.setBlurRadius(26)
        self.heading_fx.setColor(QColor(0, 208, 255, 190))
        heading.setGraphicsEffect(self.heading_fx)

        def heading_zoom(z):
            heading.setFont(_font(25 + 9 * z))
            self.heading_fx.setBlurRadius(26 + 36 * z)

        self.add_hover(heading, heading_zoom)

        subtitle = QLabel("PERSONAL VOICE ASSISTANT")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #8fc4e0; font-size: 10px; font-family: Consolas; letter-spacing: 2px;")

        self.dev = QLabel("DEVELOPED BY  •  AKSHAT RAJPUT")
        self.dev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dev.setFixedHeight(36)
        self.dev.setFont(_font(8.0))
        self.dev.setStyleSheet(
            "color: #c6f4ff;"
            "background-color: rgba(0,208,255,34); border: 1px solid #1d7fa8;"
            "border-radius: 13px; padding: 2px 16px;"
        )
        self.add_hover(self.dev, lambda z: self.dev.setFont(_font(8.0 + 3.2 * z)))

        self.orb = AnimatedOrb()

        self.status = QLabel("● SLEEPING")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setFont(_font(11.5))
        self.status.setFixedHeight(40)
        self.add_hover(self.status, lambda z: self.status.setFont(_font(11.5 + 2.5 * z)))

        self.hint = QLabel("")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setStyleSheet("color: #8fc4e0; font-size: 11px;")

        # ---------------- Wake Up / Restart buttons ----------------
        self.wake_btn = QPushButton("⏻  WAKE UP")
        self.restart_btn = QPushButton("⟳  RESTART")
        for b in (self.wake_btn, self.restart_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(36)
            b.setMinimumWidth(130)
        self.wake_btn.setStyleSheet(
            "QPushButton {color:#b3f2ff; background-color:rgba(0,208,255,36); border:1px solid #00d0ff;"
            "border-radius:12px; padding:4px 16px; font-weight:bold; font-size:11px;}"
            "QPushButton:hover {background-color:rgba(0,208,255,90); color:#ffffff;}"
        )
        self.restart_btn.setStyleSheet(
            "QPushButton {color:#d6e4ff; background-color:rgba(96,140,255,36); border:1px solid #608cff;"
            "border-radius:12px; padding:4px 16px; font-weight:bold; font-size:11px;}"
            "QPushButton:hover {background-color:rgba(96,140,255,90); color:#ffffff;}"
        )
        self.wake_btn.clicked.connect(self.on_wake)
        self.restart_btn.clicked.connect(self.on_restart)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self.wake_btn)
        btn_row.addWidget(self.restart_btn)
        btn_row.addStretch(1)

        # ---------------- device info ----------------
        info_title = QLabel("DEVICE INFORMATION")
        info_title.setStyleSheet("color: #8fd8f2; font-size: 11px; font-weight: bold; font-family: Consolas; letter-spacing: 2px;")

        grid = QGridLayout()
        grid.setSpacing(8)

        self.c_device = InfoCard("DEVICE")
        self.c_os = InfoCard("SYSTEM")
        self.c_time = InfoCard("DATE & TIME")
        self.c_cpu = InfoCard("CPU", "#00d0ff")
        self.c_ram = InfoCard("RAM", "#608cff")
        self.c_bat = InfoCard("BATTERY", "#3ddc97")
        self.c_disk = InfoCard("DISK", "#ffb347")
        self.c_net = InfoCard("NETWORK")
        self.c_up = InfoCard("UPTIME")

        cards = (
            self.c_device, self.c_os, self.c_time,
            self.c_cpu, self.c_ram, self.c_bat,
            self.c_disk, self.c_net, self.c_up,
        )
        for i, card in enumerate(cards):
            grid.addWidget(self._reveal(card, 3.7 + i * 0.12), i // 3, i % 3)
            self.add_hover(card, card.set_zoom)

        self.c_device.set(platform.node() or "Unknown")
        self.c_os.set(f"{platform.system()} {platform.release()}")

        self._net_prev = None

        # ---------------- conversation ----------------
        self.history_title = QLabel("CONVERSATION")
        self.history_title.setStyleSheet("color: #8fd8f2; font-size: 11px; font-weight: bold;")

        self.clear_btn = QPushButton("CLEAR")
        self.clear_btn.setObjectName("clear")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setFixedHeight(24)

        head_row = QHBoxLayout()
        head_row.setContentsMargins(0, 0, 0, 0)
        head_row.addWidget(self.history_title)
        head_row.addStretch(1)
        head_row.addWidget(self.clear_btn)

        self.history = ChatView()
        self.clear_btn.clicked.connect(self.history.clear)

        footer = QLabel("Designed & Developed by Akshat Rajput")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet("color: #5f8fb0; font-size: 9px;")

        # left: heading + orb + status + buttons
        # (orb sabse pehle aata hai, baaki cheezein intro me ek ek karke ubharti hain)
        left.addWidget(self._reveal(heading, 1.6))
        left.addWidget(self._reveal(subtitle, 2.0))
        left.addWidget(self._reveal(self.dev, 2.3), 0, Qt.AlignmentFlag.AlignHCenter)
        left.addWidget(self.orb, 1)
        left.addWidget(self._reveal(self.status, 2.7))
        left.addWidget(self._reveal(self.hint, 2.9))
        left.addWidget(self._reveal(btn_row, 3.1))          # Wake Up + Restart buttons
        left.addWidget(self._reveal(footer, 3.3))

        # right: device info + conversation
        right.addWidget(self._reveal(info_title, 3.5))
        right.addLayout(grid)                 # cards alag alag ubharte hain
        right.addSpacing(2)
        right.addWidget(self._reveal(head_row, 4.6))
        right.addWidget(self._reveal(self.history, 4.7), 1)

        layout.addLayout(left, 5)
        layout.addLayout(right, 6)

        # ---------------- terminal panel (live log) ----------------
        term_col = QVBoxLayout()
        term_col.setSpacing(10)

        term_title = QLabel("TERMINAL  •  LIVE LOG")
        term_title.setStyleSheet("color: #8fd8f2; font-size: 11px; font-weight: bold; font-family: Consolas; letter-spacing: 2px;")

        term_clear = QPushButton("CLEAR")
        term_clear.setObjectName("clear")
        term_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        term_clear.setFixedHeight(24)

        term_head = QHBoxLayout()
        term_head.setContentsMargins(0, 0, 0, 0)
        term_head.addWidget(term_title)
        term_head.addStretch(1)
        term_head.addWidget(term_clear)

        self.term = QTextEdit()
        self.term.setReadOnly(True)
        self.term.document().setMaximumBlockCount(500)     # purani lines apne aap hat jayengi
        self.term.setPlaceholderText("Terminal output yahan dikhega...")
        self.term.setStyleSheet(
            "QTextEdit {background-color:rgba(2,8,16,215); color:#7dffb0; border:1px solid #17406a;"
            "border-radius:16px; padding:10px; font-family:Consolas; font-size:12px;}"
        )
        term_clear.clicked.connect(self.term.clear)

        term_col.addWidget(self._reveal(term_head, 5.0))
        term_col.addWidget(self._reveal(self.term, 5.1), 1)
        layout.addLayout(term_col, 5)

        # ---------------- STUCK column (chhota side card) ----------------
        def _lbl(text, size, bold=True, color="#8fd8f2", spacing=0, wrap=False):
            lb = QLabel(text)
            lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            f = _font(size, bold)
            if spacing:
                f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
            lb.setFont(f)
            lb.setWordWrap(wrap)
            lb.setStyleSheet(f"color: {color}; background: transparent;")
            return lb

        self.stuck_card = QFrame()
        self.stuck_card.setObjectName("stuck")
        self.stuck_card.setFixedWidth(132)
        sl = QVBoxLayout(self.stuck_card)
        sl.setContentsMargins(10, 14, 10, 14)
        sl.setSpacing(4)

        sl.addWidget(_lbl("STUCK", 9.0, True, "#ff9aa8", 3))
        self.stuck_num = _lbl(str(self.stuck_count), 30, True, "#ffffff")
        sl.addWidget(self.stuck_num)
        sl.addWidget(_lbl("TIMES SO FAR", 6.8, True, "#6f9cba", 1))
        sl.addSpacing(6)
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #17406a;")
        sl.addWidget(sep)
        sl.addSpacing(6)
        sl.addWidget(_lbl("LAST", 6.8, True, "#6f9cba", 1))
        self.stuck_last_lbl = _lbl("—", 9.0, True, "#dbf4ff")
        sl.addWidget(self.stuck_last_lbl)
        sl.addSpacing(4)
        sl.addWidget(_lbl("STAGE", 6.8, True, "#6f9cba", 1))
        self.stuck_stage_lbl = _lbl("—", 7.6, False, "#b9d8e6", 0, True)
        sl.addWidget(self.stuck_stage_lbl)
        sl.addSpacing(6)
        self.stuck_state = _lbl("● MONITORING", 7.0, True, "#3ddc97", 1)
        sl.addWidget(self.stuck_state)

        self.add_hover(self.stuck_num, lambda z: self.stuck_num.setFont(_font(30 + 8 * z)))
        self.update_stuck_ui()

        stuck_col = QVBoxLayout()
        stuck_col.setSpacing(10)
        stuck_col.addSpacing(34)
        stuck_col.addWidget(self._reveal(self.stuck_card, 5.2))
        stuck_col.addStretch(1)
        layout.addLayout(stuck_col, 0)

        # ---------------- timers ----------------
        self.info_timer = QTimer(self)
        self.info_timer.timeout.connect(self.update_info)
        self.info_timer.start(1000)
        self.update_info()

        # Alexa atki ho to bolti hai "Restarting Alexa" aur khud restart ho jaati hai
        self.stuck_timer = QTimer(self)
        self.stuck_timer.timeout.connect(self.check_stuck)
        self.stuck_timer.start(5000)

        # glow effects (status + history)
        self.fx_status = QGraphicsDropShadowEffect(self.status)
        self.fx_status.setOffset(0, 0)
        self.fx_status.setBlurRadius(0)
        self.status.setGraphicsEffect(self.fx_status)

        self.fx_hist = QGraphicsDropShadowEffect(self.history)
        self.fx_hist.setOffset(0, 0)
        self.fx_hist.setBlurRadius(0)
        self.history.setGraphicsEffect(self.fx_hist)

        self.apply_theme()

        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self.pulse)
        self.pulse_timer.start(33)

        # IDLE -> SLEEPING thoda ruk ke (flicker na ho)
        self.sleep_timer = QTimer(self)
        self.sleep_timer.setSingleShot(True)
        self.sleep_timer.setInterval(700)
        self.sleep_timer.timeout.connect(lambda: self._apply_state("SLEEPING"))

        # JARVIS boot screen (sirf pehli baar, restart par nahi)
        self.boot = BootOverlay(central) if INTRO_ENABLED else None

        # smooth fade-in
        self.setWindowOpacity(0.0)
        self.fade = QPropertyAnimation(self, b"windowOpacity")
        self.fade.setDuration(700)
        self.fade.setStartValue(0.0)
        self.fade.setEndValue(1.0)
        self.fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.fade.start()

    # ------------------------------------------------------------------
    def add_hover(self, widget, fn):
        self.hover.append([widget, 0.0, fn])

    # ------------------------------------------------------------------
    # intro: cheezein dheere dheere ubharti hain
    # ------------------------------------------------------------------
    def _reveal(self, item, at):
        """item (widget ya layout) ko holder me daalta hai; intro me `at` second par fade-in hota hai."""
        holder = QWidget()
        if isinstance(item, QLayout):
            holder.setLayout(item)
            item.setContentsMargins(0, 0, 0, 0)
        else:
            lay = QVBoxLayout(holder)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(item)
        if INTRO_ENABLED:
            eff = QGraphicsOpacityEffect(holder)
            eff.setOpacity(0.0)
            holder.setGraphicsEffect(eff)
            self._reveals.append((at, holder, eff))
        return holder

    def start_intro(self):
        # pehle boot screen (HUD + 0-100%), uske fade hote hi orb + UI ubharte hain
        if self.boot is not None:
            self.boot.on_reveal = self._begin_reveal
            self.boot.begin()
        else:
            self._begin_reveal()

    def _begin_reveal(self):
        self.orb.start_intro()
        for at, holder, eff in self._reveals:
            QTimer.singleShot(int(at * 1000 / INTRO_SPEED), lambda h=holder, e=eff: self._fade_in(h, e))

    def _fade_in(self, holder, eff):
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(650)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        # fade khatam hote hi effect hata do (text saaf rahe, GPU/CPU bhi bache)
        anim.finished.connect(lambda h=holder: h.setGraphicsEffect(None))
        anim.start()
        self._anims.append(anim)

    # ------------------------------------------------------------------
    def update_info(self):

        self.c_time.set(datetime.now().strftime("%d %b  %I:%M %p"))

        if psutil is None:
            for c in (self.c_cpu, self.c_ram, self.c_bat, self.c_disk, self.c_net, self.c_up):
                c.set("pip install psutil")
            return

        cpu = psutil.cpu_percent(interval=None)
        self.c_cpu.set(f"{cpu:.0f}%", cpu)

        ram = psutil.virtual_memory()
        self.c_ram.set(
            f"{ram.percent:.0f}% ({ram.used / 1024 ** 3:.1f}/{ram.total / 1024 ** 3:.0f} GB)",
            ram.percent,
        )

        try:
            bat = psutil.sensors_battery()
        except Exception:
            bat = None

        if bat is None:
            self.c_bat.set("AC Power", 100)
        else:
            plug = " ⚡" if bat.power_plugged else ""
            self.c_bat.set(f"{bat.percent:.0f}%{plug}", bat.percent)

        try:
            disk = psutil.disk_usage(os.path.abspath(os.sep))
            self.c_disk.set(f"{disk.percent:.0f}% ({disk.used / 1024 ** 3:.0f}/{disk.total / 1024 ** 3:.0f} GB)", disk.percent)
        except Exception:
            self.c_disk.set("N/A")

        try:
            io = psutil.net_io_counters()
            ts = _now()
            if self._net_prev is not None:
                dt = max(0.1, ts - self._net_prev[0])
                down = (io.bytes_recv - self._net_prev[1]) / dt
                up = (io.bytes_sent - self._net_prev[2]) / dt
                self.c_net.set(f"↓{_rate(down)}  ↑{_rate(up)}")
            self._net_prev = (ts, io.bytes_recv, io.bytes_sent)
        except Exception:
            self.c_net.set("N/A")

        try:
            secs = int(_now() - psutil.boot_time())
            d, rem = divmod(secs, 86400)
            h, rem = divmod(rem, 3600)
            m = rem // 60
            self.c_up.set(f"{d}d {h}h {m}m" if d else f"{h}h {m}m")
        except Exception:
            self.c_up.set("N/A")

    # ------------------------------------------------------------------
    def set_state(self, state):

        state = state.upper()
        if state == "IDLE":
            state = "SLEEPING"

        if state == "SLEEPING":
            if self.state != "SLEEPING" and not self.sleep_timer.isActive():
                self.sleep_timer.start()
        else:
            self.sleep_timer.stop()
            self._apply_state(state)

    def _apply_state(self, state):
        self.state = state
        self.orb.set_state(state)
        self.apply_theme()

    def apply_theme(self):
        """State ke hisaab se status pill, hint, conversation box aur title highlight."""

        if self.state == "LISTENING":
            acc, soft, txt, active = "#00d0ff", "rgba(0,208,255,42)", "#b3f2ff", True
            self.status.setText("● LISTENING")
            self.hint.setText("I am listening to you...")
            self.history_title.setText("CONVERSATION   ●  LIVE")

        elif self.state == "SPEAKING":
            acc, soft, txt, active = "#ff7ae0", "rgba(255,122,224,42)", "#ffe3f7", True
            self.status.setText("● ALEXA IS SPEAKING")
            self.hint.setText("Alexa is responding...")
            self.history_title.setText("CONVERSATION")

        else:
            acc, soft, txt, active = "#4fb8ff", "rgba(79,184,255,36)", "#d0ecff", False
            self.status.setText("● SLEEPING")
            self.hint.setText("Say  “Alexa”  to wake me up")
            self.history_title.setText("CONVERSATION")

        self.accent = QColor(acc)
        self.bg.set_accent(self.accent)

        self.status.setStyleSheet(
            f"color: {txt}; background-color: {soft};"
            f"border: 1px solid {acc};"
            "border-radius: 18px; padding: 4px 18px;"
        )

        self.history_title.setStyleSheet(
            f"color: {acc if active else '#8fd8f2'}; font-size: 11px; font-weight: bold;"
        )

        self.history.set_accent(acc, active)

    def pulse(self):
        """Glow pulse + hover zoom animations + status text animation."""

        self.pt += 0.033

        # ---- heading glow: cyan <-> blue shimmer ----
        mixh = 0.5 + 0.5 * math.sin(self.pt * 0.9)
        self.heading_fx.setColor(QColor(int(0 + 96 * mixh), int(208 - 68 * mixh), 255, 200))

        # ---- state glow ----
        target = {"LISTENING": 1.0, "SPEAKING": 1.0, "SLEEPING": 0.55}.get(self.state, 0.0)
        self.hl += (target - self.hl) * 0.15

        speed = {"LISTENING": 5.0, "SPEAKING": 4.0}.get(self.state, 1.6)
        s = 0.5 + 0.5 * math.sin(self.pt * speed)

        col = QColor(self.accent)
        col.setAlpha(int(215 * self.hl))

        self.fx_status.setColor(col)
        self.fx_status.setBlurRadius(self.hl * (16 + 16 * s))

        self.fx_hist.setColor(col)
        self.fx_hist.setBlurRadius(self.hl * (10 + 10 * s) if self.state != "SLEEPING" else 0)

        # ---- animated status text ----
        if self.state == "LISTENING":
            text = "● LISTENING" + "." * (int(self.pt * 2.5) % 4)
        elif self.state == "SLEEPING":
            text = "● SLEEPING  " + " ".join(("z", "z", "Z")[: int(self.pt * 1.2) % 3 + 1])
        else:
            text = None

        if text is not None and self.status.text() != text:
            self.status.setText(text)

        # ---- hover zoom ----
        for item in self.hover:
            w, z, fn = item
            tgt = 1.0 if w.underMouse() else 0.0
            nz = z + (tgt - z) * 0.22
            if abs(nz - tgt) < 0.004:
                nz = tgt
            if nz != z:
                item[1] = nz
                fn(nz)

    def add_message(self, role, message):
        self.history.add(role, message)

    # ------------------------------------------------------------------
    # buttons + terminal log
    # ------------------------------------------------------------------
    def on_wake(self):
        self.add_log("[GUI] Wake Up pressed")
        bridge.wake_event.set()

    def on_restart(self):
        self.add_log("[GUI] Restart pressed -> restarting Alexa...")
        QTimer.singleShot(800, hard_restart)

    def update_stuck_ui(self, restarting=False):
        n = self.stuck_count
        self.stuck_num.setText(str(n))
        self.stuck_num.setStyleSheet(
            f"color: {'#ff7b8a' if n else '#ffffff'}; background: transparent;"
        )
        self.stuck_last_lbl.setText(self.stuck_last or "—")
        self.stuck_stage_lbl.setText(self.stuck_stage or "—")
        if restarting:
            self.stuck_state.setText("● RESTARTING")
            self.stuck_state.setStyleSheet("color: #ff7b8a; background: transparent;")
        else:
            self.stuck_state.setText("● MONITORING")
            self.stuck_state.setStyleSheet("color: #3ddc97; background: transparent;")
        border = "#ff5c73" if restarting else ("#5a2b3c" if n else "#17406a")
        self.stuck_card.setStyleSheet(
            f"QFrame#stuck {{background-color: rgba(5,16,32,205); border: 1px solid {border}; border-radius: 14px;}}"
        )

    def restart_env(self):
        """Restart ke baad bhi stuck ginti yaad rakhne ke liye."""
        return {
            "ALEXA_STUCK_COUNT": str(self.stuck_count),
            "ALEXA_STUCK_LAST": self.stuck_last,
            "ALEXA_STUCK_STAGE": self.stuck_stage,
        }

    def check_stuck(self):
        """Heartbeat purana ho to: stuck ginti +1, Alexa bolti hai 'Restarting Alexa', phir restart."""
        if self._restarting or bridge.alexa_thread is None:
            return
        idle = _now() - bridge.heartbeat
        if idle <= self.STUCK_AFTER:
            return

        self._restarting = True
        self.stuck_count += 1
        self.stuck_last = datetime.now().strftime("%I:%M %p")
        self.stuck_stage = str(bridge.stage)
        self.update_stuck_ui(restarting=True)

        self.add_log(f"[STUCK] Alexa {idle:.0f} sec se atki hai | stage: {bridge.stage} | total stuck: {self.stuck_count}")

        # exact kaunsi line par atki hai, wo bhi print karo
        t = bridge.alexa_thread
        frame = sys._current_frames().get(t.ident) if t is not None else None
        if frame is not None:
            for entry in traceback.format_stack(frame)[-3:]:
                for ln in entry.rstrip().splitlines():
                    self.add_log("[STUCK]   " + ln.strip())

        self.add_log("[STUCK] Restarting Alexa...")
        self.add_message("ALEXA", "Restarting Alexa...")
        self.sleep_timer.stop()
        self._apply_state("SPEAKING")

        def say_and_restart():
            _speak_once("Restarting Alexa.")
            bridge.restart_now.emit()

        threading.Thread(target=say_and_restart, daemon=True).start()
        QTimer.singleShot(8000, hard_restart)      # awaaz atak jaye to bhi restart ho jaye

    def add_log(self, text):
        # har line dikhegi (Listening.... bhi), kuch filter nahi hota
        self._last_log = text

        low = text.lower()
        if "error" in low or "traceback" in low or "exception" in low or "unavailable" in low or "stuck" in low:
            color = "#ff7b8a"          # laal: error
        elif text.startswith("Listening"):
            color = "#7fd8ff"          # neela: listening
        elif low.startswith("sorry"):
            color = "#ffcf70"          # peela: samajh nahi aaya
        else:
            color = "#7dffb0"          # hara: baaki sab

        safe = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        stamp = datetime.now().strftime("%H:%M:%S")
        self.term.append(
            f'<span style="color:#5f7799;">{stamp}</span>&nbsp;'
            f'<span style="color:{color};">{safe}</span>'
        )
        sb = self.term.verticalScrollBar()
        sb.setValue(sb.maximum())


# ----------------------------------------------------------------------
# BRIDGE  (alexa thread  ->  GUI)
# ----------------------------------------------------------------------

class Bridge(QObject):
    state_changed = Signal(str)     # "IDLE" (=sleeping) / "LISTENING" / "SPEAKING"
    message = Signal(str, str)      # ("YOU" / "ALEXA", text)
    log = Signal(str)               # terminal text -> GUI panel
    clear_log = Signal()            # "refresh yourself" par terminal panel saaf
    restart_now = Signal()          # stuck hone par bolne ke baad restart

    def __init__(self):
        super().__init__()
        self.wake_event = threading.Event()      # Wake Up button
        self.restart_event = threading.Event()   # Restart button
        self.heartbeat = _now()                  # alexa.py isse update karti hai (kuch restart nahi hota)
        self.stage = "starting"                  # alexa.py likhti hai ki abhi kya kar rahi hai
        self.alexa_thread = None                 # alexa wala thread (stuck line dhundne ke liye)


bridge = Bridge()

_win = None             # main window (restart ke waqt stuck ginti lene ke liye)
_pending_logs = []      # window banne se pehle ke prints yahan jama honge
_log_ready = False      # window ban jaye to True


def hard_restart():
    """Poora program naye sire se chalata hai (sirf Restart button se).
    Login dobara nahi maangta, Alexa seedha sleep mode me start hoti hai."""
    env = dict(os.environ)
    env["ALEXA_SKIP_LOGIN"] = "1"
    if _win is not None:
        try:
            env.update(_win.restart_env())         # stuck ginti naye process me bhi dikhe
        except Exception:
            pass
    args = [sys.executable] + (sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv)
    try:
        subprocess.Popen(args, env=env)
    except Exception as e:
        print("Restart error:", e)
        return
    os._exit(0)


class _LogStream:
    """print() aur errors ko terminal ke saath GUI panel me bhi bhejta hai."""

    def __init__(self, original):
        self.original = original

    def write(self, text):
        if self.original:
            try:
                self.original.write(text)
            except Exception:
                pass
        if text and text.strip():
            msg = text.rstrip()
            if _log_ready:
                bridge.log.emit(msg)
            else:
                _pending_logs.append(msg)      # window abhi nahi bani, baad me dikhayenge

    def flush(self):
        if self.original:
            try:
                self.original.flush()
            except Exception:
                pass

    def isatty(self):
        return False


# import hote hi pakad lo, taaki "Initalizing Alexa..." jaise prints bhi na chhoote
sys.stdout = _LogStream(sys.stdout)
sys.stderr = _LogStream(sys.stderr)


def _qt_msg(mode, context, msg):
    print("[Qt]", msg)            # qt.conf wali warning jaise Qt messages bhi panel me


def run_app(target):
    """GUI start karta hai aur `target` function ko background thread me chalata hai."""
    global _log_ready, _win

    qInstallMessageHandler(_qt_msg)

    app = QApplication.instance() or QApplication(sys.argv)

    window = AssistantWindow()
    _win = window
    bridge.restart_now.connect(hard_restart)
    bridge.state_changed.connect(window.set_state)
    bridge.message.connect(window.add_message)
    bridge.log.connect(window.add_log)
    bridge.clear_log.connect(window.term.clear)

    # window banne se pehle ke saare prints ab panel me daalo
    for m in _pending_logs:
        window.add_log(m)
    _pending_logs.clear()
    _log_ready = True

    bridge.heartbeat = _now()

    # intro sound bannne tak (import ke waqt se background me chal rahi hoti hai) thoda ruko
    if INTRO_ENABLED and _intro_thread is not None:
        _intro_thread.join(timeout=8)

    def runner():
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        target()

    def start_alexa():
        # Alexa (mic) tabhi start hoti hai jab intro / welcome speech khatam ho jaye,
        # warna welcome me bolta hua "Alexa" hi wake-word ban jaata
        bridge.heartbeat = _now()
        bridge.alexa_thread = threading.Thread(target=runner, daemon=True)
        bridge.alexa_thread.start()

    window.show()
    if INTRO_ENABLED and window.boot is not None:
        window.boot.on_finished = start_alexa
        window.start_intro()                       # boot HUD -> welcome speech -> main screen
        if _intro_wav is not None and winsound is not None:
            _play_intro_sound()                    # sound ek hi waqt par shuru
    else:
        start_alexa()

    sys.exit(app.exec())


if __name__ == "__main__":
    # sirf orb test karne ke liye:  python orb.py
    def demo():
        import time as _t
        while True:
            for st in ("IDLE", "LISTENING", "SPEAKING"):
                bridge.state_changed.emit(st)
                bridge.message.emit("ALEXA", f"Demo state: {st}")
                print(f"Demo state: {st}")        # terminal panel test
                _t.sleep(5)

    run_app(demo)