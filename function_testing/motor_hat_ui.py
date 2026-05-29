#!/usr/bin/env python3
"""Web UI for controlling three pumps and one linear actuator on a motor HAT.

Default motor mapping:
  - M1: Pump 1
  - M2: Pump 2
  - M3: Pump 3
  - M4: Linear actuator

This program targets Adafruit-compatible Raspberry Pi DC Motor HAT boards using
the adafruit-circuitpython-motorkit library. If that library is unavailable, the
UI starts in dry-run mode so the interface can still be tested safely.
"""

from __future__ import annotations

import argparse
import atexit
import colorsys
import threading
import time
from dataclasses import asdict, dataclass

from flask import Flask, jsonify, render_template_string, request


MOTOR_CONFIG = {
    1: "Pump 1",
    2: "Pump 2",
    3: "Pump 3",
    4: "Linear actuator",
}

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080


@dataclass
class MotorState:
    channel: int
    name: str
    pwm: int = 0
    direction: str = "stop"

    @property
    def throttle(self) -> float:
        if self.direction == "stop" or self.pwm == 0:
            return 0.0
        throttle = self.pwm / 100
        if self.direction == "reverse":
            return -throttle
        return throttle


@dataclass
class ColorState:
    available: bool
    error: str = ""
    color_name: str = "Unavailable"
    red: int = 0
    green: int = 0
    blue: int = 0
    clear: int = 0
    lux: float = 0.0
    color_temperature: float = 0.0
    timestamp: float = 0.0


class MotorHatController:
    def __init__(self, dry_run: bool = False) -> None:
        self._lock = threading.Lock()
        self.states = {
            channel: MotorState(channel=channel, name=name)
            for channel, name in MOTOR_CONFIG.items()
        }
        self.dry_run = dry_run
        self.driver_error = ""
        self._kit = None
        self._motors = {}

        if not dry_run:
            self._initialize_driver()

    def _initialize_driver(self) -> None:
        try:
            from adafruit_motorkit import MotorKit

            self._kit = MotorKit()
            self._motors = {
                1: self._kit.motor1,
                2: self._kit.motor2,
                3: self._kit.motor3,
                4: self._kit.motor4,
            }
        except Exception as exc:
            self.dry_run = True
            self.driver_error = str(exc)

    def status(self) -> dict:
        with self._lock:
            return {
                "dry_run": self.dry_run,
                "driver_error": self.driver_error,
                "motors": [asdict(state) for state in self.states.values()],
            }

    def set_motor(self, channel: int, pwm: int, direction: str) -> MotorState:
        if channel not in self.states:
            raise ValueError(f"Unknown motor channel M{channel}")
        if direction not in {"forward", "reverse", "stop"}:
            raise ValueError("direction must be forward, reverse, or stop")
        if pwm < 0 or pwm > 100:
            raise ValueError("pwm must be between 0 and 100")

        with self._lock:
            state = self.states[channel]
            state.pwm = pwm
            state.direction = direction if pwm > 0 else "stop"
            self._apply_state(state)
            return state

    def stop_motor(self, channel: int) -> MotorState:
        return self.set_motor(channel, 0, "stop")

    def stop_all(self) -> None:
        with self._lock:
            for state in self.states.values():
                state.pwm = 0
                state.direction = "stop"
                self._apply_state(state)

    def _apply_state(self, state: MotorState) -> None:
        if self.dry_run:
            return
        self._motors[state.channel].throttle = state.throttle


class ColorSensorController:
    def __init__(self, disabled: bool = False) -> None:
        self._lock = threading.Lock()
        self._sensor = None
        self.state = ColorState(available=False)

        if disabled:
            self.state.error = "disabled with --no-color-sensor"
            return
        self._initialize_sensor()

    def _initialize_sensor(self) -> None:
        try:
            import board
            import adafruit_tcs34725

            i2c = board.I2C()
            self._sensor = adafruit_tcs34725.TCS34725(i2c)
            self._sensor.integration_time = 100
            self._sensor.gain = 4
            self.state = ColorState(available=True)
        except Exception as exc:
            self.state = ColorState(available=False, error=str(exc))

    def status(self) -> dict:
        with self._lock:
            if self._sensor is None:
                return asdict(self.state)

            try:
                red, green, blue, clear = self._sensor.color_raw
                self.state = ColorState(
                    available=True,
                    color_name=detect_color_name(red, green, blue, clear),
                    red=red,
                    green=green,
                    blue=blue,
                    clear=clear,
                    lux=float(self._sensor.lux),
                    color_temperature=float(self._sensor.color_temperature),
                    timestamp=time.time(),
                )
            except Exception as exc:
                self.state.available = False
                self.state.error = str(exc)
            return asdict(self.state)


def detect_color_name(red: int, green: int, blue: int, clear: int) -> str:
    max_channel = max(red, green, blue)
    min_channel = min(red, green, blue)

    if clear < 60 or max_channel < 20:
        return "Dark"

    saturation = (max_channel - min_channel) / max_channel if max_channel else 0.0
    if saturation < 0.16:
        if clear > 1200:
            return "White"
        return "Gray"

    hue = colorsys.rgb_to_hsv(red / max_channel, green / max_channel, blue / max_channel)[0] * 360

    if hue < 15 or hue >= 345:
        return "Red"
    if hue < 40:
        return "Orange"
    if hue < 70:
        return "Yellow"
    if hue < 165:
        return "Green"
    if hue < 200:
        return "Cyan"
    if hue < 260:
        return "Blue"
    if hue < 300:
        return "Purple"
    return "Pink"


HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Box Motor Control</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f7f8;
      --panel: #ffffff;
      --text: #172026;
      --muted: #5d6872;
      --line: #d6dde2;
      --accent: #096b72;
      --danger: #b42318;
      --ok: #147a43;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: var(--bg);
      color: var(--text);
    }

    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      padding: 18px 24px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }

    h1 {
      margin: 0;
      font-size: 22px;
      font-weight: 700;
      letter-spacing: 0;
    }

    main {
      width: min(1120px, 100%);
      margin: 0 auto;
      padding: 24px;
    }

    .status {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.4;
    }

    .status strong { color: var(--ok); }
    .status.dry strong { color: var(--danger); }

    .toolbar {
      display: flex;
      justify-content: flex-end;
      margin-bottom: 18px;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }

    .sensor {
      display: grid;
      grid-template-columns: minmax(160px, 220px) 1fr;
      gap: 18px;
      align-items: center;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      margin-bottom: 16px;
    }

    .swatch {
      display: grid;
      place-items: center;
      min-height: 132px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #808080;
      color: #ffffff;
      font-size: 26px;
      font-weight: 700;
      text-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
    }

    .sensor-title {
      margin: 0 0 10px;
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 0;
    }

    .sensor-data {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px 14px;
      color: var(--muted);
      font-size: 14px;
    }

    .sensor-data strong {
      color: var(--text);
    }

    .motor {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }

    .motor-head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
      margin-bottom: 18px;
    }

    .motor-title {
      margin: 0;
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 0;
    }

    .channel {
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }

    .control-row {
      display: grid;
      gap: 10px;
      margin-top: 14px;
    }

    label {
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }

    .pwm-line {
      display: grid;
      grid-template-columns: 1fr 72px;
      gap: 12px;
      align-items: center;
    }

    input[type="range"] {
      width: 100%;
      accent-color: var(--accent);
    }

    input[type="number"] {
      width: 72px;
      padding: 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      font-size: 15px;
      text-align: right;
    }

    .direction {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
    }

    button {
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      color: var(--text);
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
    }

    button.active {
      background: var(--accent);
      border-color: var(--accent);
      color: #ffffff;
    }

    button.stop.active,
    button.stop-all {
      background: var(--danger);
      border-color: var(--danger);
      color: #ffffff;
    }

    .readout {
      margin-top: 12px;
      color: var(--muted);
      font-size: 13px;
    }

    @media (max-width: 760px) {
      header {
        align-items: flex-start;
        flex-direction: column;
      }

      main { padding: 16px; }
      .sensor { grid-template-columns: 1fr; }
      .sensor-data { grid-template-columns: 1fr; }
      .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>AI Box Motor Control</h1>
      <div id="status" class="status">Connecting...</div>
    </div>
    <button class="stop-all" onclick="stopAll()">Stop All</button>
  </header>

  <main>
    <section class="sensor">
      <div id="color-swatch" class="swatch">...</div>
      <div>
        <h2 class="sensor-title">Color Sensor</h2>
        <div id="sensor-status" class="status">Reading TCS34725...</div>
        <div class="sensor-data">
          <div>Raw RGB: <strong id="raw-rgb">-</strong></div>
          <div>Clear: <strong id="clear-channel">-</strong></div>
          <div>Lux: <strong id="lux">-</strong></div>
          <div>Temperature: <strong id="temperature">-</strong></div>
        </div>
      </div>
    </section>
    <div class="grid" id="motors"></div>
  </main>

  <script>
    const state = { motors: [] };

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Request failed");
      return payload;
    }

    function motorCard(motor) {
      return `
        <section class="motor" data-channel="${motor.channel}">
          <div class="motor-head">
            <h2 class="motor-title">${motor.name}</h2>
            <span class="channel">M${motor.channel}</span>
          </div>

          <div class="control-row">
            <label for="pwm-${motor.channel}">PWM</label>
            <div class="pwm-line">
              <input id="pwm-${motor.channel}" type="range" min="0" max="100" value="${motor.pwm}"
                oninput="setPwm(${motor.channel}, this.value)">
              <input id="pwm-value-${motor.channel}" type="number" min="0" max="100" value="${motor.pwm}"
                onchange="setPwm(${motor.channel}, this.value)">
            </div>
          </div>

          <div class="control-row">
            <label>Direction</label>
            <div class="direction">
              <button onclick="setDirection(${motor.channel}, 'forward')"
                class="${motor.direction === "forward" ? "active" : ""}">Forward</button>
              <button onclick="setDirection(${motor.channel}, 'reverse')"
                class="${motor.direction === "reverse" ? "active" : ""}">Reverse</button>
              <button class="stop ${motor.direction === "stop" ? "active" : ""}"
                onclick="setDirection(${motor.channel}, 'stop')">Stop</button>
            </div>
          </div>

          <div class="readout">Current: ${motor.direction}, ${motor.pwm}% PWM</div>
        </section>
      `;
    }

    function colorToCss(sensor) {
      if (!sensor.available || sensor.clear <= 0) return "#808080";
      const scale = 255 / Math.max(sensor.red, sensor.green, sensor.blue, 1);
      const red = Math.round(sensor.red * scale);
      const green = Math.round(sensor.green * scale);
      const blue = Math.round(sensor.blue * scale);
      return `rgb(${red}, ${green}, ${blue})`;
    }

    function renderSensor(sensor) {
      const swatch = document.getElementById("color-swatch");
      const sensorStatus = document.getElementById("sensor-status");
      swatch.textContent = sensor.color_name;
      swatch.style.background = colorToCss(sensor);

      sensorStatus.className = sensor.available ? "status" : "status dry";
      sensorStatus.innerHTML = sensor.available
        ? "<strong>TCS34725 connected</strong>"
        : `<strong>Unavailable</strong>${sensor.error ? ": " + sensor.error : ""}`;

      document.getElementById("raw-rgb").textContent = `${sensor.red}, ${sensor.green}, ${sensor.blue}`;
      document.getElementById("clear-channel").textContent = sensor.clear;
      document.getElementById("lux").textContent = Number(sensor.lux || 0).toFixed(2);
      document.getElementById("temperature").textContent = `${Number(sensor.color_temperature || 0).toFixed(1)}K`;
    }

    function render(payload) {
      state.motors = payload.motors;
      const status = document.getElementById("status");
      status.className = payload.dry_run ? "status dry" : "status";
      status.innerHTML = payload.dry_run
        ? `<strong>Dry run</strong>${payload.driver_error ? ": " + payload.driver_error : ""}`
        : "<strong>Hardware connected</strong>";

      renderSensor(payload.color_sensor);
      document.getElementById("motors").innerHTML = payload.motors.map(motorCard).join("");
    }

    function getMotor(channel) {
      return state.motors.find((motor) => motor.channel === channel);
    }

    async function setPwm(channel, value) {
      const motor = getMotor(channel);
      const pwm = Math.max(0, Math.min(100, Number(value) || 0));
      const direction = motor && motor.direction !== "stop" ? motor.direction : "forward";
      await updateMotor(channel, pwm, direction);
    }

    async function setDirection(channel, direction) {
      const motor = getMotor(channel);
      const pwm = direction === "stop" ? 0 : Math.max(1, motor ? motor.pwm : 50);
      await updateMotor(channel, pwm, direction);
    }

    async function updateMotor(channel, pwm, direction) {
      try {
        const payload = await api(`/api/motors/${channel}`, {
          method: "POST",
          body: JSON.stringify({ pwm, direction }),
        });
        render(payload);
      } catch (error) {
        alert(error.message);
      }
    }

    async function stopAll() {
      try {
        render(await api("/api/stop-all", { method: "POST" }));
      } catch (error) {
        alert(error.message);
      }
    }

    async function refresh() {
      try {
        render(await api("/api/status"));
      } catch (error) {
        document.getElementById("status").textContent = error.message;
      }
    }

    refresh();
    setInterval(refresh, 1000);
  </script>
</body>
</html>
"""


def create_app(controller: MotorHatController, color_sensor: ColorSensorController) -> Flask:
    app = Flask(__name__)

    def full_status() -> dict:
        status = controller.status()
        status["color_sensor"] = color_sensor.status()
        return status

    @app.get("/")
    def index():
        return render_template_string(HTML)

    @app.get("/api/status")
    def api_status():
        return jsonify(full_status())

    @app.post("/api/motors/<int:channel>")
    def api_set_motor(channel: int):
        payload = request.get_json(silent=True) or {}
        try:
            pwm = int(payload.get("pwm", 0))
            direction = str(payload.get("direction", "stop")).lower()
            controller.set_motor(channel, pwm, direction)
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(full_status())

    @app.post("/api/stop-all")
    def api_stop_all():
        controller.stop_all()
        return jsonify(full_status())

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Web UI for Raspberry Pi Motor HAT control.")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Bind host. Default: {DEFAULT_HOST}")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Bind port. Default: {DEFAULT_PORT}")
    parser.add_argument("--dry-run", action="store_true", help="Start without writing to motor hardware.")
    parser.add_argument("--no-color-sensor", action="store_true", help="Start without reading the TCS34725.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    controller = MotorHatController(dry_run=args.dry_run)
    color_sensor = ColorSensorController(disabled=args.no_color_sensor)
    atexit.register(controller.stop_all)

    app = create_app(controller, color_sensor)
    print(f"Motor and color sensor UI running at http://{args.host}:{args.port}")
    if controller.dry_run:
        print(f"Dry-run mode active: {controller.driver_error or 'requested with --dry-run'}")
    if not color_sensor.state.available:
        print(f"Color sensor unavailable: {color_sensor.state.error}")
    app.run(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
