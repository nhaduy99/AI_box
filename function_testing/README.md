# Function Testing

## Motor HAT and color sensor UI

Motor mapping:
- `M1`: Pump 1
- `M2`: Pump 2
- `M3`: Pump 3
- `M4`: Linear actuator

Install the motor HAT dependency:

```bash
/home/pi/projects/AI_box/function_testing/.venv_system/bin/python -m pip install adafruit-circuitpython-motorkit
```

Start the UI:

```bash
/home/pi/projects/AI_box/function_testing/.venv_system/bin/python /home/pi/projects/AI_box/function_testing/motor_hat_ui.py
```

Open this address from the Pi or another device on the same network:

```text
http://<raspberry-pi-ip>:8080
```

UI controls:
- Each motor has independent PWM control from `0` to `100`.
- Each motor has independent `Forward`, `Reverse`, and `Stop` controls.
- `Stop All` sets all four HAT channels to `0` throttle.
- The top panel shows the live TCS34725 color name, raw RGB values, clear channel, lux, and color temperature.
- If the MotorKit driver is unavailable, the page starts in dry-run mode and does not write to hardware.
- If the TCS34725 is unavailable, the motor controls still run and the color panel shows the sensor error.

## TCS34725 RGB color sensor test plan

Hardware setup:
- Connect TCS34725 `VIN` or `3V3` to Raspberry Pi `3.3V`.
- Connect `GND` to Raspberry Pi `GND`.
- Connect `SDA` to Raspberry Pi `SDA`.
- Connect `SCL` to Raspberry Pi `SCL`.
- Enable I2C on the Raspberry Pi before running the test.

Dependency setup:

```bash
python3 -m venv --system-site-packages /home/pi/projects/AI_box/function_testing/.venv_system
/home/pi/projects/AI_box/function_testing/.venv_system/bin/python -m pip install adafruit-circuitpython-tcs34725
```

Continuous color detection:

```bash
/home/pi/projects/AI_box/function_testing/.venv_system/bin/python /home/pi/projects/AI_box/function_testing/test_tcs34725.py
```

Press `Ctrl+C` to stop.

Run a fixed number of samples and save CSV output:

```bash
/home/pi/projects/AI_box/function_testing/.venv_system/bin/python /home/pi/projects/AI_box/function_testing/test_tcs34725.py --samples 20 --delay 0.5 --csv /home/pi/projects/AI_box/function_testing/tcs34725_samples.csv
```

Check whether the sensor is visible on I2C bus 1:

```bash
i2cdetect -y 1
```

Checks performed:
- Verifies Python can load the sensor library.
- Verifies the TCS34725 can initialize over I2C.
- Captures raw red, green, blue, and clear channel readings.
- Captures calculated color temperature and lux values.
- Prints a detected color name: `Dark`, `White`, `Gray`, `Red`, `Orange`, `Yellow`, `Green`, `Cyan`, `Blue`, `Purple`, or `Pink`.
- Fails the run if readings are negative or the clear channel is zero.

Expected result:
- The script prints `TCS34725 initialized`.
- In continuous mode, each reading prints a `Color:` line until stopped.
- In fixed sample mode, each sample prints `PASS` and the run ends with `All readings passed basic checks`.

Troubleshooting:
- If dependency import fails, install the package listed above.
- If initialization fails, check wiring, power, and I2C enablement.
- A TCS34725 should normally appear at I2C address `0x29`.
- If the clear channel is zero, check that the sensor is exposed to light and not covered.
