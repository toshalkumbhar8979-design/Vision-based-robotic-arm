/*
 * ============================================================================
 * SERVO CALIBRATION UTILITY
 * ============================================================================
 * 
 * Project:  Vision-Based Autonomous Robotic Arm
 * File:     servo_calibration.ino
 * Location: firmware/servo_calibration/
 * 
 * PURPOSE:
 *   Pre-assembly utility that sets ALL 6 servos to exactly 90 degrees and
 *   holds them there indefinitely. This allows the operator to physically
 *   attach the 3D printed arm parts onto the servo gears while the servos
 *   are locked in a known position.
 * 
 * WHEN TO USE:
 *   Flash this sketch BEFORE assembling the robot. Once all servos are
 *   locked at 90 degrees, push the plastic parts onto the metal gear shafts
 *   at the optimal mechanical midpoint of each joint's range.
 * 
 * ASSEMBLY STRATEGY (Decision #10 in decisions.md):
 *   Do NOT mount all joints "straight up" just because 90° is the midpoint.
 *   Instead:
 *     1. With the part detached, manually move it to find the collision
 *        limits (where plastic hits plastic on both ends).
 *     2. Find the exact midpoint of that mechanical range.
 *     3. With the servo locked at 90°, attach the part at that midpoint.
 *   This maximizes the usable range of motion. The software IK solver
 *   will handle the mathematical offsets.
 * 
 * HARDWARE REQUIRED:
 *   - Arduino Uno Rev3
 *   - PCA9685 16-Channel PWM Servo Driver (I2C address 0x40)
 *   - 6V battery connected to PCA9685 V+ and GND
 *   - Up to 6 servos connected to PCA9685 channels 0–5
 * 
 * DEPENDENCIES:
 *   - Wire.h (built-in Arduino I2C)
 *   - Adafruit_PWMServoDriver (install via Library Manager)
 * 
 * RELATED DECISIONS:
 *   - Decision #10: Home Position Assembly Strategy
 *   - Decision #9: Robot Arm Type (true 6-DOF serial manipulator)
 * ============================================================================
 */

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// Initialize PCA9685 at default I2C address (0x40)
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

// Pulse width limits for MG996R and MG90S servos
// These map the 0–180 degree range to PCA9685 pulse counts (out of 4096)
// SERVOMIN/SERVOMAX may need fine-tuning per servo — measure with oscilloscope if needed
#define SERVOMIN  150 // Pulse count for 0 degrees
#define SERVOMAX  600 // Pulse count for 180 degrees
#define SERVO_FREQ 50 // Standard analog servo frequency: 50 Hz (20ms period)

void setup() {
  Serial.begin(9600);
  Serial.println("=== Servo Calibration Utility ===");
  Serial.println("Setting all servos to 90 degrees for assembly...");

  pwm.begin();
  pwm.setOscillatorFrequency(27000000); // Standard PCA9685 oscillator frequency
  pwm.setPWMFreq(SERVO_FREQ);

  delay(100); // Allow PCA9685 to stabilize

  // Command ALL 6 servos to 90 degrees (center position)
  // Channel mapping (defined in architecture.md):
  //   0 = Base (MG996R)
  //   1 = Shoulder (MG996R)
  //   2 = Elbow (MG996R)
  //   3 = Wrist Pitch (MG90S)
  //   4 = Wrist Roll (MG90S)
  //   5 = Gripper (MG90S)
  for (uint8_t i = 0; i < 6; i++) {
    setServoAngle(i, 90);
    Serial.print("  Channel ");
    Serial.print(i);
    Serial.println(" -> 90 degrees (LOCKED)");
    delay(200); // Stagger commands to avoid simultaneous current spike from battery
  }
  
  Serial.println("");
  Serial.println("All servos at 90 degrees. They will HOLD this position.");
  Serial.println(">>> Assemble the robot arms now while servos are locked. <<<");
  Serial.println(">>> Do NOT cut power until assembly is complete.        <<<");
}

// Convert a 0–180 degree angle to PCA9685 pulse width count
int angleToPulse(int angle) {
  return map(angle, 0, 180, SERVOMIN, SERVOMAX);
}

// Set a specific servo channel to a specific angle
void setServoAngle(uint8_t servoNum, uint8_t angle) {
  pwm.setPWM(servoNum, 0, angleToPulse(angle));
}

void loop() {
  // Nothing to do — servos hold their position as long as PCA9685 is powered
  delay(1000);
}
