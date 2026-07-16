# Sequence Test Progress

Updated: 2026-07-02 15:53:43 AEST

## Current Sequence

The active sequence in `sequence_runner.py` is:

1. Move actuator backward until Red.
2. Pump 1 forward for 5 seconds, then stop.
3. Read OD, OJIP, and PAM.
4. Move actuator forward until Blue.
5. Pump 2 forward for 5 seconds, then stop.
6. Read OD, OJIP, and PAM.
7. Move actuator forward until Green.
8. Pump 3 forward for 5 seconds, then stop.
9. Read OD, OJIP, and PAM.
10. Run pumps 1, 2, and 3 in reverse for 10 seconds, then stop.
11. Move actuator backward until Red.

Default command:

```bash
cd /home/pi/projects/AI_box/sequence_test
.venv/bin/python sequence_runner.py --pam-port /dev/ttyAMA0
```

## Code Changes Made

- Added an initial actuator homing step: backward to Red before pump 1.
- Changed the second color target from Yellow to Green.
- Added direct color-move logic that supports Red, Blue, and Green targets.
- Results are stored in `sequence_results.json` under `sequence_steps`.
- README was updated to match the current sequence.

## Position Tests

The actuator color-position tests completed successfully:

```text
reverse_to_red False Red
forward_to_blue False Blue
forward_to_green False Green
reverse_to_blue False Blue
reverse_to_red False Red
```

`False` means the move did not time out.

## Latest Full Sequence Run

The latest full sequence completed and saved:

```bash
/home/pi/projects/AI_box/sequence_test/sequence_results.json
```

Output:

```text
Saved sequence results to sequence_results.json
actuator_initial_reverse_to_red: timed_out=True final_color=Orange
measure_after_pump_1: OD=11 OJIP=4096 PAM=1024
actuator_forward_to_blue: timed_out=False final_color=Blue
measure_after_pump_2: OD=11 OJIP=4096 PAM=1024
actuator_forward_to_green: timed_out=False final_color=Green
measure_after_pump_3: OD=11 OJIP=4096 PAM=1024
actuator_reverse_to_red: timed_out=False final_color=Red
```

Note: the initial backward-to-Red step timed out and ended at Orange during the
latest full run. The final return to Red succeeded.

## Verification

The sequence runner compiled successfully:

```bash
.venv/bin/python -m py_compile sequence_runner.py
```
