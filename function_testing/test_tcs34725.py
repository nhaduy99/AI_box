#!/usr/bin/env python3
"""Functional test utility for the TCS34725 RGB color sensor.

Expected hardware:
  - Raspberry Pi with I2C enabled
  - TCS34725 connected to SDA/SCL, 3.3V, and GND

Install dependencies:
  python3 -m pip install adafruit-circuitpython-tcs34725

Run:
  python3 test_tcs34725.py
  python3 test_tcs34725.py --samples 20 --delay 0.5 --csv tcs34725_samples.csv
"""

from __future__ import annotations

import argparse
import colorsys
import csv
import sys
import time
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DELAY_SECONDS = 0.5


@dataclass(frozen=True)
class SensorReading:
    sample: int
    timestamp: float
    red: int
    green: int
    blue: int
    clear: int
    color_temperature: float
    lux: float
    color_name: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect colors continuously with a TCS34725 RGB color sensor."
    )
    parser.add_argument(
        "--samples",
        type=int,
        help="Optional number of readings to capture. Omit for continuous detection.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_SECONDS,
        help=f"Delay between readings in seconds. Default: {DEFAULT_DELAY_SECONDS}",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        help="Optional CSV path for saving readings.",
    )
    return parser.parse_args()


def load_sensor_modules():
    try:
        import board
        import adafruit_tcs34725
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency. Install with: "
            "python3 -m pip install adafruit-circuitpython-tcs34725. "
            f"Import error: {exc}"
        ) from exc

    return board, adafruit_tcs34725


def initialize_sensor():
    board, adafruit_tcs34725 = load_sensor_modules()

    try:
        i2c = board.I2C()
        sensor = adafruit_tcs34725.TCS34725(i2c)
    except Exception as exc:
        raise RuntimeError(
            "Could not initialize TCS34725. Check wiring, power, and that I2C is enabled. "
            f"Driver error: {exc}"
        ) from exc

    # Balanced defaults for stable functional testing in normal indoor light.
    sensor.integration_time = 100
    sensor.gain = 4
    return sensor


def validate_args(samples: int, delay: float) -> None:
    if samples is not None and samples < 1:
        raise ValueError("--samples must be at least 1")
    if delay < 0:
        raise ValueError("--delay cannot be negative")


def read_sensor(sensor, sample: int) -> SensorReading:
    red, green, blue, clear = sensor.color_raw
    color_name = detect_color_name(red, green, blue, clear)
    return SensorReading(
        sample=sample,
        timestamp=time.time(),
        red=red,
        green=green,
        blue=blue,
        clear=clear,
        color_temperature=float(sensor.color_temperature),
        lux=float(sensor.lux),
        color_name=color_name,
    )


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


def reading_passes_basic_checks(reading: SensorReading) -> bool:
    channels = (reading.red, reading.green, reading.blue, reading.clear)
    return (
        all(value >= 0 for value in channels)
        and reading.clear > 0
        and reading.lux >= 0
        and reading.color_temperature >= 0
    )


def print_reading(reading: SensorReading, passed: bool) -> None:
    status = "PASS" if passed else "CHECK"
    print(
        f"{status} sample={reading.sample} "
        f"color={reading.color_name} "
        f"raw=(R:{reading.red} G:{reading.green} B:{reading.blue} C:{reading.clear}) "
        f"temp={reading.color_temperature:.1f}K lux={reading.lux:.2f}"
    )


def save_csv(csv_path: Path, readings: list[SensorReading]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(SensorReading.__dataclass_fields__))
        writer.writeheader()
        for reading in readings:
            writer.writerow(reading.__dict__)


def print_color(reading: SensorReading) -> None:
    print(
        f"Color: {reading.color_name:<6} "
        f"raw=(R:{reading.red} G:{reading.green} B:{reading.blue} C:{reading.clear}) "
        f"lux={reading.lux:.2f}",
        flush=True,
    )


def run_test(samples: int | None, delay: float, csv_path: Path | None) -> int:
    sensor = initialize_sensor()
    readings: list[SensorReading] = []
    failed_checks = 0

    print("TCS34725 initialized")
    print(f"integration_time={sensor.integration_time}ms gain={sensor.gain}x")
    if samples is None:
        print("Printing detected color continuously. Press Ctrl+C to stop.")

    sample = 1
    while samples is None or sample <= samples:
        reading = read_sensor(sensor, sample)
        readings.append(reading)

        passed = reading_passes_basic_checks(reading)
        if not passed:
            failed_checks += 1

        if samples is None:
            print_color(reading)
        else:
            print_reading(reading, passed)

        if samples is None or sample != samples:
            time.sleep(delay)
        sample += 1

    if csv_path:
        save_csv(csv_path, readings)
        print(f"Saved readings to {csv_path}")

    if failed_checks:
        print(f"Completed with {failed_checks} reading(s) needing inspection")
        return 1

    print("All readings passed basic checks")
    return 0


def main() -> int:
    args = parse_args()
    try:
        validate_args(args.samples, args.delay)
        return run_test(args.samples, args.delay, args.csv)
    except KeyboardInterrupt:
        print("\nStopped color detection")
        return 0
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
