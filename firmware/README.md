# Firmware Directory

> **Location:** `firmware/`
> **Status:** Written, NOT yet flashed or tested.

This directory contains all Arduino C++ firmware that runs on the **Arduino Uno Rev3**.

## Contents

### `servo_calibration/servo_calibration.ino`
- **Purpose:** Pre-assembly calibration utility. Sets ALL 6 servos to exactly 90 degrees and holds them there.
- **When to use:** Flash this BEFORE physically assembling the robot arm. With servos locked at 90°, push the 3D printed parts onto the servo gears at the optimal mechanical midpoint.
- **Status:** ✅ Written, ❌ Not flashed yet.

### `robot_driver/robot_driver.ino`
- **Purpose:** Production firmware. Listens for 6-byte binary packets on Serial (115200 baud), commands the PCA9685 PWM driver, and includes a 500ms safety watchdog that auto-returns to Home if communication drops.
- **When to use:** Flash this AFTER the robot is assembled and calibrated. This is the firmware that stays on the Arduino during teleoperation, dataset collection, and autonomous execution.
- **Related Decisions:** Decision #6 (Serial Protocol), Decision #5 (Safety System) in `decisions.md`.
- **Status:** ✅ Written, ❌ Not tested yet.

## Hardware Connections

```
Arduino Uno Pin A4 (SDA) ──► PCA9685 SDA
Arduino Uno Pin A5 (SCL) ──► PCA9685 SCL
Arduino Uno GND           ──► PCA9685 GND
Arduino Uno 5V            ──► PCA9685 VCC

PCA9685 V+ (Servo Power)  ──► 6V Battery (+)
PCA9685 GND               ──► 6V Battery (-)

PCA9685 Channel 0 ──► Base Servo (MG996R)
PCA9685 Channel 1 ──► Shoulder Servo (MG996R)
PCA9685 Channel 2 ──► Elbow Servo (MG996R)
PCA9685 Channel 3 ──► Wrist Pitch Servo (MG90S)
PCA9685 Channel 4 ──► Wrist Roll Servo (MG90S)
PCA9685 Channel 5 ──► Gripper Servo (MG90S)
```

## Dependencies
- `Wire.h` (built-in Arduino I2C library)
- `Adafruit_PWMServoDriver` (install via Arduino IDE Library Manager or `arduino-cli lib install "Adafruit PWM Servo Driver Library"`)
