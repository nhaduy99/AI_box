#!/usr/bin/env python3
"""Integrated AI Box sequence runner.

Combines:
  - pump/linear actuator control from function_testing/motor_hat_ui.py
  - TCS34725 color sensor reads from function_testing
  - UTSPAM optical sensor reads from uts-pamod/main_test.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


AI_BOX_ROOT = Path("/home/pi/projects/AI_box")
FUNCTION_TESTING_ROOT = AI_BOX_ROOT / "function_testing"
UTS_PAMOD_ROOT = AI_BOX_ROOT / "uts-pamod"

for import_path in (
    FUNCTION_TESTING_ROOT,
    UTS_PAMOD_ROOT / "src",
):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from motor_hat_ui import ColorSensorController, MotorHatController
from uts_pamod import UTSSensor


MOTOR_NAMES = {
    1: "pump_1",
    2: "pump_2",
    3: "pump_3",
    4: "linear_actuator",
}


@dataclass(frozen=True)
class TimedMotorStep:
    channel: int
    direction: str
    pwm: int
    seconds: float


@dataclass(frozen=True)
class ColorMoveStep:
    channel: int
    direction: str
    pwm: int
    target_color: str
    timeout: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an integrated pump, motor, color sensor, and UTSPAM sequence."
    )
    parser.add_argument("--pam-port", default="/dev/ttyAMA0", help="UTSPAM serial port.")
    parser.add_argument("--dry-run-motors", action="store_true", help="Do not write motor outputs.")
    parser.add_argument("--output", type=Path, default=Path("sequence_results.json"))

    parser.add_argument("--pump-pwm", type=int, default=60, help="Default pump PWM, 1-100.")
    parser.add_argument("--actuator-pwm", type=int, default=60, help="Linear actuator PWM, 1-100.")
    parser.add_argument("--sequence-pump-seconds", type=float, default=5.0)
    parser.add_argument("--pump-1-seconds", type=float, default=None)
    parser.add_argument("--pump-2-seconds", type=float, default=None)
    parser.add_argument("--pump-3-seconds", type=float, default=None)
    parser.add_argument(
        "--reverse-pump-order",
        action="store_true",
        help="Run the three sequence pump stages in the order 3, 2, 1.",
    )
    parser.add_argument("--sequence-reverse-seconds", type=float, default=10.0)

    parser.add_argument("--measuring-led", type=int, default=100)
    parser.add_argument("--saturation-led", type=int, default=2800)
    parser.add_argument("--reference-led", type=int, default=2200)
    parser.add_argument("--skip-od", action="store_true")
    parser.add_argument("--skip-ojip", action="store_true")
    parser.add_argument("--skip-pam", action="store_true")

    parser.add_argument("--run-to-color-timeout", type=float, default=20.0)
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    for name in ("pump_pwm", "actuator_pwm"):
        value = getattr(args, name)
        if value < 1 or value > 100:
            raise ValueError(f"--{name.replace('_', '-')} must be between 1 and 100")

    for name in (
        "sequence_pump_seconds",
        "sequence_reverse_seconds",
        "run_to_color_timeout",
    ):
        value = getattr(args, name)
        if value < 0:
            raise ValueError(f"--{name.replace('_', '-')} cannot be negative")

    for name in ("pump_1_seconds", "pump_2_seconds", "pump_3_seconds"):
        value = getattr(args, name)
        if value is not None and value < 0:
            raise ValueError(f"--{name.replace('_', '-')} cannot be negative")

    for name in ("measuring_led", "saturation_led", "reference_led"):
        value = getattr(args, name)
        if value < 0 or value > 4095:
            raise ValueError(f"--{name.replace('_', '-')} must be between 0 and 4095")


async def run_timed_motor(
    motor_controller: MotorHatController,
    step: TimedMotorStep,
) -> dict[str, Any]:
    name = MOTOR_NAMES[step.channel]
    if step.seconds <= 0:
        return {
            "channel": step.channel,
            "name": name,
            "skipped": True,
            "reason": "duration is 0 seconds",
        }

    started_at = time.time()
    motor_controller.set_motor(step.channel, step.pwm, step.direction)
    try:
        await asyncio.sleep(step.seconds)
    finally:
        state = motor_controller.stop_motor(step.channel)

    return {
        "channel": step.channel,
        "name": name,
        "direction": step.direction,
        "pwm": step.pwm,
        "seconds": step.seconds,
        "started_at": started_at,
        "stopped_state": asdict(state),
    }


async def run_all_pumps(
    motor_controller: MotorHatController,
    direction: str,
    pwm: int,
    seconds: float,
) -> dict[str, Any]:
    started_at = time.time()
    channels = (1, 2, 3)
    for channel in channels:
        motor_controller.set_motor(channel, pwm, direction)
    try:
        await asyncio.sleep(seconds)
    finally:
        stopped_states = [asdict(motor_controller.stop_motor(channel)) for channel in channels]

    return {
        "channels": list(channels),
        "names": [MOTOR_NAMES[channel] for channel in channels],
        "direction": direction,
        "pwm": pwm,
        "seconds": seconds,
        "started_at": started_at,
        "stopped_states": stopped_states,
    }


async def move_until_color(
    motor_controller: MotorHatController,
    color_sensor: ColorSensorController,
    step: ColorMoveStep,
) -> dict[str, Any]:
    if step.timeout <= 0:
        raise ValueError("color move timeout must be greater than 0")

    started_at = time.time()
    initial_sensor_state = color_sensor.status()
    if not initial_sensor_state["available"]:
        raise ValueError(
            "Color sensor is unavailable"
            + (f": {initial_sensor_state['error']}" if initial_sensor_state.get("error") else "")
        )

    target = step.target_color.lower()
    initial_color = str(initial_sensor_state.get("color_name") or "")
    if initial_color.lower() == target:
        stopped_state = motor_controller.stop_motor(step.channel)
        return {
            "channel": step.channel,
            "name": MOTOR_NAMES[step.channel],
            "direction": step.direction,
            "pwm": step.pwm,
            "target_color": step.target_color,
            "timed_out": False,
            "already_at_target": True,
            "started_at": started_at,
            "initial_sensor_state": initial_sensor_state,
            "final_sensor_state": initial_sensor_state,
            "stopped_state": asdict(stopped_state),
        }

    motor_controller.set_motor(step.channel, step.pwm, step.direction)
    deadline = time.monotonic() + step.timeout
    final_sensor_state = initial_sensor_state
    timed_out = True

    try:
        while time.monotonic() < deadline:
            final_sensor_state = color_sensor.status()
            current_color = str(final_sensor_state.get("color_name") or "")
            if final_sensor_state.get("available") and current_color.lower() == target:
                timed_out = False
                break
            await asyncio.sleep(0.1)
    finally:
        stopped_state = motor_controller.stop_motor(step.channel)

    return {
        "channel": step.channel,
        "name": MOTOR_NAMES[step.channel],
        "direction": step.direction,
        "pwm": step.pwm,
        "target_color": step.target_color,
        "timeout_seconds": step.timeout,
        "timed_out": timed_out,
        "already_at_target": False,
        "started_at": started_at,
        "initial_sensor_state": initial_sensor_state,
        "final_sensor_state": final_sensor_state,
        "stopped_state": asdict(stopped_state),
    }


async def run_uts_measurements(args: argparse.Namespace) -> dict[str, Any]:
    results: dict[str, Any] = {}
    async with UTSSensor(port=args.pam_port) as sensor:
        results["id"] = await sensor.get_id()
        results["firmware"] = await sensor.get_version()

        await sensor.set_measuring_led(args.measuring_led)
        await sensor.set_saturation_led(args.saturation_led)
        await sensor.set_reference_led(args.reference_led)
        results["leds"] = {
            "measuring": args.measuring_led,
            "saturation": args.saturation_led,
            "reference": args.reference_led,
        }

        if not args.skip_od:
            results["od"] = await sensor.measure_od()
        if not args.skip_ojip:
            ojip = await sensor.measure_ojip()
            results["ojip"] = {"samples": len(ojip), "values": ojip}
        if not args.skip_pam:
            pam = await sensor.measure_pam()
            results["pam"] = {"samples": len(pam), "values": pam}

    return results


async def run_sequence(args: argparse.Namespace) -> dict[str, Any]:
    validate_args(args)

    motor_controller = MotorHatController(dry_run=args.dry_run_motors)
    color_sensor = ColorSensorController()

    results: dict[str, Any] = {
        "started_at": time.time(),
        "motor_status_initial": motor_controller.status(),
        "color_sensor_initial": color_sensor.status(read_sensor=True),
        "sequence_steps": [],
    }

    pump_seconds = {
        channel: (
            getattr(args, f"pump_{channel}_seconds")
            if getattr(args, f"pump_{channel}_seconds") is not None
            else args.sequence_pump_seconds
        )
        for channel in (1, 2, 3)
    }
    pump_order = (3, 2, 1) if args.reverse_pump_order else (1, 2, 3)

    try:
        results["sequence_steps"].append(
            {
                "name": "actuator_initial_reverse_to_red",
                "result": await move_until_color(
                    motor_controller,
                    color_sensor,
                    ColorMoveStep(
                        4,
                        "reverse",
                        args.actuator_pwm,
                        "Red",
                        args.run_to_color_timeout,
                    ),
                ),
            }
        )
        results["sequence_steps"].append(
            {
                "name": f"pump_{pump_order[0]}_forward",
                "result": await run_timed_motor(
                    motor_controller,
                    TimedMotorStep(
                        pump_order[0],
                        "forward",
                        args.pump_pwm,
                        pump_seconds[pump_order[0]],
                    ),
                ),
            }
        )
        results["sequence_steps"].append(
            {
                "name": f"measure_after_pump_{pump_order[0]}",
                "result": await run_uts_measurements(args),
            }
        )
        results["sequence_steps"].append(
            {
                "name": "actuator_forward_to_blue",
                "result": await move_until_color(
                    motor_controller,
                    color_sensor,
                    ColorMoveStep(
                        4,
                        "forward",
                        args.actuator_pwm,
                        "Blue",
                        args.run_to_color_timeout,
                    ),
                ),
            }
        )
        results["sequence_steps"].append(
            {
                "name": f"pump_{pump_order[1]}_forward",
                "result": await run_timed_motor(
                    motor_controller,
                    TimedMotorStep(
                        pump_order[1],
                        "forward",
                        args.pump_pwm,
                        pump_seconds[pump_order[1]],
                    ),
                ),
            }
        )
        results["sequence_steps"].append(
            {
                "name": f"measure_after_pump_{pump_order[1]}",
                "result": await run_uts_measurements(args),
            }
        )
        results["sequence_steps"].append(
            {
                "name": "actuator_forward_to_green",
                "result": await move_until_color(
                    motor_controller,
                    color_sensor,
                    ColorMoveStep(
                        4,
                        "forward",
                        args.actuator_pwm,
                        "Green",
                        args.run_to_color_timeout,
                    ),
                ),
            }
        )
        results["sequence_steps"].append(
            {
                "name": f"pump_{pump_order[2]}_forward",
                "result": await run_timed_motor(
                    motor_controller,
                    TimedMotorStep(
                        pump_order[2],
                        "forward",
                        args.pump_pwm,
                        pump_seconds[pump_order[2]],
                    ),
                ),
            }
        )
        results["sequence_steps"].append(
            {
                "name": f"measure_after_pump_{pump_order[2]}",
                "result": await run_uts_measurements(args),
            }
        )
        results["sequence_steps"].append(
            {
                "name": "all_pumps_reverse",
                "result": await run_all_pumps(
                    motor_controller,
                    "reverse",
                    args.pump_pwm,
                    args.sequence_reverse_seconds,
                ),
            }
        )
        results["sequence_steps"].append(
            {
                "name": "actuator_reverse_to_red",
                "result": await move_until_color(
                    motor_controller,
                    color_sensor,
                    ColorMoveStep(
                        4,
                        "reverse",
                        args.actuator_pwm,
                        "Red",
                        args.run_to_color_timeout,
                    ),
                ),
            }
        )
    finally:
        motor_controller.stop_all()
        results["motor_status_final"] = motor_controller.status()
        results["finished_at"] = time.time()

    return results


def write_results(path: Path, results: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    try:
        results = asyncio.run(run_sequence(args))
        write_results(args.output, results)
    except KeyboardInterrupt:
        print("Stopped by user", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Saved sequence results to {args.output}")
    for step in results.get("sequence_steps", []):
        name = step.get("name")
        result = step.get("result", {})
        if name and name.startswith("measure_"):
            print(
                f"{name}: "
                f"OD={len(result.get('od', []))} "
                f"OJIP={result.get('ojip', {}).get('samples', 0)} "
                f"PAM={result.get('pam', {}).get('samples', 0)}"
            )
        elif name and "to_" in name:
            print(
                f"{name}: "
                f"timed_out={result.get('timed_out')} "
                f"final_color={result.get('final_sensor_state', {}).get('color_name')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
