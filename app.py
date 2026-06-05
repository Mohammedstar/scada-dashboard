"""
=============================================================
SCADA Dashboard - Python/Flask Web-Based HMI
=============================================================
Author:  Mohammed Satar | Automation & SCADA Engineer
Version: 1.0
Purpose: Simulates a basic SCADA/HMI system for a 
         3-tank process control system.
         
         Career path: Automation Engineer → SCADA Engineer
=============================================================
"""

from flask import Flask, render_template, jsonify, request
import threading
import time
import math
import random
import json
from datetime import datetime
from collections import deque

app = Flask(__name__)

# ─── Process Simulation ───────────────────────────────────
class ProcessSimulator:
    """
    Simulates a 3-tank level control system with:
    - PID controller for level regulation
    - Feed pump and drain valve control
    - Temperature and pressure simulation
    - Alarm generation
    """

    def __init__(self):
        self.t = 0
        self.tanks = {
            "T-101": {"level": 50.0, "setpoint": 60.0, "temp": 25.0},
            "T-102": {"level": 35.0, "setpoint": 40.0, "temp": 30.0},
            "T-103": {"level": 70.0, "setpoint": 65.0, "temp": 28.0},
        }
        self.pumps = {
            "P-101": {"running": False, "speed_pct": 0, "current_A": 0},
            "P-102": {"running": True,  "speed_pct": 75, "current_A": 12.3},
        }
        self.valves = {
            "FCV-101": {"position_pct": 45, "flow_m3h": 2.3},
            "FCV-102": {"position_pct": 60, "flow_m3h": 3.1},
            "XV-101":  {"position_pct": 100, "flow_m3h": 0},  # ON/OFF valve
        }
        self.history = deque(maxlen=500)
        self.alarms = []
        self.lock = threading.Lock()

    def pid_control(self, pv: float, sp: float, Kp=1.2, Ki=0.1) -> float:
        """Simple proportional-integral controller."""
        error = sp - pv
        output = Kp * error + Ki * error * 0.5
        return max(0, min(100, output))

    def update(self):
        """Simulate one time step of the process."""
        self.t += 0.5  # 500ms steps
        new_alarms = []

        with self.lock:
            for tank_id, tank in self.tanks.items():
                # Apply PID control output to level
                cv = self.pid_control(tank["level"], tank["setpoint"])
                noise = random.gauss(0, 0.3)
                drift = 0.5 * math.sin(self.t / 20)
                tank["level"] = max(0, min(100, tank["level"] + (cv - 50) * 0.02 + noise + drift))
                tank["temp"]  = 25 + 10 * math.sin(self.t / 60) + random.gauss(0, 0.5)

                # Check alarms (ISA-18.2)
                if tank["level"] > 90:
                    new_alarms.append({"tag": tank_id, "type": "LEVEL_HH", "priority": 1,
                                       "value": round(tank["level"], 1),
                                       "ts": datetime.now().strftime("%H:%M:%S")})
                elif tank["level"] < 10:
                    new_alarms.append({"tag": tank_id, "type": "LEVEL_LL", "priority": 1,
                                       "value": round(tank["level"], 1),
                                       "ts": datetime.now().strftime("%H:%M:%S")})

            # Update pump simulation
            for pump_id, pump in self.pumps.items():
                if pump["running"]:
                    pump["current_A"] = 10 + random.gauss(0, 0.5)
                else:
                    pump["current_A"] = 0

            # Update valve simulation
            for v_id, valve in self.valves.items():
                valve["flow_m3h"] = valve["position_pct"] / 100 * 5.0 + random.gauss(0, 0.1)

            # Log snapshot
            self.history.append({
                "ts": datetime.now().isoformat(),
                "T101_level": round(self.tanks["T-101"]["level"], 2),
                "T102_level": round(self.tanks["T-102"]["level"], 2),
                "T103_level": round(self.tanks["T-103"]["level"], 2),
                "P101_current": round(self.pumps["P-101"]["current_A"], 2),
                "P102_current": round(self.pumps["P-102"]["current_A"], 2),
            })

            # Keep only last 5 alarms
            self.alarms = (new_alarms + self.alarms)[:10]

    def get_snapshot(self):
        with self.lock:
            return {
                "tanks":  {k: {kk: round(vv, 2) if isinstance(vv, float) else vv
                               for kk, vv in v.items()}
                           for k, v in self.tanks.items()},
                "pumps":  self.pumps.copy(),
                "valves": {k: {kk: round(vv, 2) if isinstance(vv, float) else vv
                               for kk, vv in v.items()}
                           for k, v in self.valves.items()},
                "alarms": self.alarms[:5],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

    def get_history(self):
        with self.lock:
            return list(self.history)


sim = ProcessSimulator()


def simulation_loop():
    while True:
        sim.update()
        time.sleep(0.5)


# ─── Flask Routes ─────────────────────────────────────────

@app.route("/")
def index():
    return render_template("scada.html")


@app.route("/api/snapshot")
def api_snapshot():
    return jsonify(sim.get_snapshot())


@app.route("/api/history")
def api_history():
    return jsonify({"history": sim.get_history()[-100:]})


@app.route("/api/control", methods=["POST"])
def api_control():
    """Accept control commands from HMI."""
    data = request.json
    tag  = data.get("tag")
    cmd  = data.get("command")
    val  = data.get("value")

    with sim.lock:
        if tag in sim.pumps:
            if cmd == "START":
                sim.pumps[tag]["running"] = True
                sim.pumps[tag]["speed_pct"] = val or 75
            elif cmd == "STOP":
                sim.pumps[tag]["running"] = False
                sim.pumps[tag]["speed_pct"] = 0
        elif tag in sim.valves:
            if cmd == "SET_POSITION":
                sim.valves[tag]["position_pct"] = int(val)
        elif tag in sim.tanks:
            if cmd == "SET_SETPOINT":
                sim.tanks[tag]["setpoint"] = float(val)

    return jsonify({"status": "OK", "tag": tag, "command": cmd})


@app.route("/api/alarms")
def api_alarms():
    return jsonify({"alarms": sim.alarms})


if __name__ == "__main__":
    t = threading.Thread(target=simulation_loop, daemon=True)
    t.start()
    print("[OK] SCADA Dashboard running at http://localhost:5001")
    app.run(host="0.0.0.0", port=5001, debug=False)
