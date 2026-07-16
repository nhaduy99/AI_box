# Sequence Test

Integrated runner for the AI Box pump/motor hardware, TCS34725 color sensor, and
UTSPAM optical sensor.

## Setup

```bash
cd /home/pi/projects/AI_box/sequence_test
./setup_env.sh
```

The environment uses `--system-site-packages` so Raspberry Pi hardware packages
installed at system level remain visible. It also installs the local
`../uts-pamod` package in editable mode.

## Basic run

```bash
/home/pi/projects/AI_box/sequence_test/.venv/bin/python \
  /home/pi/projects/AI_box/sequence_test/sequence_runner.py
```

The script runs this fixed sequence:

1. Move the linear actuator backward until the color sensor sees Red.
2. Pump 1 forward for 5 seconds, then stop.
3. Read OD, OJIP, and PAM.
4. Move the linear actuator forward until the color sensor sees Blue.
5. Pump 2 forward for 5 seconds, then stop.
6. Read OD, OJIP, and PAM.
7. Move the linear actuator forward until the color sensor sees Green.
8. Pump 3 forward for 5 seconds, then stop.
9. Read OD, OJIP, and PAM.
10. Run pumps 1, 2, and 3 in reverse for 10 seconds, then stop.
11. Move the linear actuator backward until the color sensor sees Red.

Results are saved to `sequence_results.json`.

## Web control UI

Start the manual and sequence control interface with:

```bash
./.venv/bin/python sequence_ui.py
```

Then open `http://<raspberry-pi-address>:8081`. Each motor can be run forward or
reverse for a chosen duration at a fixed 100% speed. The automated sequence has
separate forward-run times for pumps 1, 2, and 3, plus an emergency Stop All
button. The UI sequence runs pumps in the order 3, 2, 1 and defaults each pump
to 8 seconds. Use `--dry-run` to test the interface without writing motor outputs.

Motor mapping from `function_testing`:

- `M1`: Pump 1
- `M2`: Pump 2
- `M3`: Pump 3
- `M4`: Linear actuator

## Useful options

- `--pam-port /dev/ttyAMA0`: UTSPAM serial port.
- `--dry-run-motors`: initialize software without writing motor outputs.
- `--skip-od`, `--skip-ojip`, `--skip-pam`: skip specific UTSPAM measurements.
- `--measuring-led`, `--saturation-led`, `--reference-led`: set LED DAC values
  from `0` to `4095`.
- `--pump-pwm 60`: pump speed for forward and reverse pump steps.
- `--actuator-pwm 60`: linear actuator speed for color-seeking moves.
- `--sequence-pump-seconds 5`: duration for each forward pump step.
- `--pump-1-seconds`, `--pump-2-seconds`, `--pump-3-seconds`: optional individual
  pump durations that override `--sequence-pump-seconds`.
- `--sequence-reverse-seconds 10`: duration for the final reverse pump step.
- `--run-to-color-timeout 20`: timeout for each actuator color-seeking move.
