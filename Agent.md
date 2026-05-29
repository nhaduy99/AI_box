# Agent Progress

Last updated: 2026-05-29 12:16 AEST

## Current Status

The repository has the first functional AI_box hardware testing tools in place under `function_testing`.

## Completed

- Added a Flask-based Motor HAT web UI for controlling four HAT channels:
  - `M1`: Pump 1
  - `M2`: Pump 2
  - `M3`: Pump 3
  - `M4`: Linear actuator
- Added independent PWM, forward, reverse, stop, and stop-all controls.
- Added dry-run fallback when the Adafruit MotorKit driver is unavailable.
- Integrated live TCS34725 color sensor status into the motor UI.
- Added a standalone TCS34725 functional test script with:
  - continuous color detection
  - fixed sample mode
  - CSV export
  - basic sensor reading validation
- Added setup and usage documentation in `function_testing/README.md`.
- Pushed the initial project state to GitHub on branch `main`.

## Important Files

- `function_testing/motor_hat_ui.py`: Motor HAT control UI and live color sensor panel.
- `function_testing/test_tcs34725.py`: Standalone TCS34725 RGB color sensor test tool.
- `function_testing/README.md`: Hardware setup, dependency installation, run commands, and troubleshooting notes.

## Run Commands

Install Motor HAT dependency:

```bash
/home/pi/projects/AI_box/function_testing/.venv_system/bin/python -m pip install adafruit-circuitpython-motorkit
```

Install TCS34725 dependency:

```bash
/home/pi/projects/AI_box/function_testing/.venv_system/bin/python -m pip install adafruit-circuitpython-tcs34725
```

Start the Motor HAT and color sensor UI:

```bash
/home/pi/projects/AI_box/function_testing/.venv_system/bin/python /home/pi/projects/AI_box/function_testing/motor_hat_ui.py
```

Run continuous TCS34725 detection:

```bash
/home/pi/projects/AI_box/function_testing/.venv_system/bin/python /home/pi/projects/AI_box/function_testing/test_tcs34725.py
```

Run fixed TCS34725 samples with CSV output:

```bash
/home/pi/projects/AI_box/function_testing/.venv_system/bin/python /home/pi/projects/AI_box/function_testing/test_tcs34725.py --samples 20 --delay 0.5 --csv /home/pi/projects/AI_box/function_testing/tcs34725_samples.csv
```

## Next Steps

- Test Motor HAT output on the actual pump and actuator wiring.
- Confirm motor direction labels match the physical plumbing and actuator movement.
- Calibrate TCS34725 color thresholds using real samples under the final lighting setup.
- Decide whether to add logged hardware test results to the repo or keep generated CSV files local.
- Add higher-level AI_box workflows after the basic hardware checks are verified.
