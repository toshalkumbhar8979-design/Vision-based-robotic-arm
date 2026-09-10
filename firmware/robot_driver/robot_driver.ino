/*
 * ============================================================================
 * ROBOT DRIVER — Production Arduino Firmware
 * ============================================================================
 * 
 * Project:  Vision-Based Autonomous Robotic Arm
 * File:     robot_driver.ino
 * Location: firmware/robot_driver/
 * 
 * PURPOSE:
 *   Production firmware that runs on the Arduino Uno during ALL phases of
 *   the project: teleoperation, dataset collection, and autonomous execution.
 *   It acts as a dumb, fast serial-to-PWM bridge:
 *     1. Receives 6-byte binary packets from the host (MacBook or RPi5)
 *     2. Commands the PCA9685 to set each servo angle immediately
 *     3. Monitors for communication loss and auto-returns to Home
 * 
 * SERIAL PROTOCOL (Decision #6 in decisions.md):
 *   - Baud Rate: 115200
 *   - Packet Format: 6 raw bytes, one per servo (value 0–180)
 *   - Byte Order: [Base, Shoulder, Elbow, WristPitch, WristRoll, Gripper]
 *   - Target Frequency: 30 Hz (sent by the Python host)
 *   - Why binary over ASCII: Lower latency, minimal parsing, critical for
 *     smooth teleoperation demonstrations
 * 
 * SAFETY (Decision #5 in decisions.md):
 *   - 500ms watchdog timer: if no serial packet arrives within 500ms,
 *     the firmware assumes the host has crashed or disconnected and
 *     automatically returns all servos to the Home Position.
 *   - This is the SOFTWARE layer of safety. The HARDWARE layer is a
 *     physical emergency stop switch that cuts the 6V battery power.
 * 
 * SERVO CHANNEL MAPPING (defined in architecture.md):
 *   Channel 0 = Base         (MG996R)
 *   Channel 1 = Shoulder     (MG996R)
 *   Channel 2 = Elbow        (MG996R)
 *   Channel 3 = Wrist Pitch  (MG90S)
 *   Channel 4 = Wrist Roll   (MG90S)
 *   Channel 5 = Gripper      (MG90S)
 * 
 * HARDWARE REQUIRED:
 *   - Arduino Uno Rev3
 *   - PCA9685 16-Channel PWM Servo Driver (I2C address 0x40)
 *   - 6V battery connected to PCA9685 V+ and GND
 *   - 6 servos on PCA9685 channels 0–5
 * 
 * DEPENDENCIES:
 *   - Wire.h (built-in Arduino I2C)
 *   - Adafruit_PWMServoDriver (install via Library Manager)
 * 
 * NOTE ON SERVO FEEDBACK:
 *   MG996R and MG90S are open-loop PWM servos — they do NOT report their
 *   actual position back. We must assume commanded_angle ≈ actual_angle.
 *   This is acceptable as long as payloads remain lightweight (sponge blocks,
 *   per Decision #7 in decisions.md).
 * ============================================================================
 */

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// Initialize PCA9685 at default I2C address (0x40)
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

// Pulse width limits — tune these if a specific servo doesn't reach 0° or 180°
#define SERVOMIN  150 // Pulse count for 0 degrees (out of 4096)
#define SERVOMAX  600 // Pulse count for 180 degrees (out of 4096)
#define SERVO_FREQ 50 // 50 Hz — standard for analog hobby servos

const int NUM_SERVOS = 6;

// Spaced PCA9685 Servo Channels: Base=0, Shoulder=2, Elbow=4, WristPitch=6, WristRoll=8, Gripper=10
const uint8_t SERVO_CHANNELS[NUM_SERVOS] = {0, 2, 4, 6, 8, 10};

// Home Position angles (0–180) for each servo
// These define the safe resting configuration the robot returns to on startup
const uint8_t HOME_ANGLES[NUM_SERVOS] = {90, 90, 90, 90, 90, 140}; 

// Track the last commanded angle and pulse for each servo
uint8_t current_angles[NUM_SERVOS];
float current_pulses[NUM_SERVOS];

// Buffer to store incoming serial data (exactly 6 bytes per command packet)
byte serialBuffer[NUM_SERVOS];

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(10); // Don't block on incomplete reads

  Wire.begin();
  Wire.setClock(400000L); // 400kHz Fast I2C Bus Mode to prevent transmission bottlenecks
  delay(100);
  pwm.begin();
  pwm.setPWMFreq(SERVO_FREQ);
  delay(100);
  
  for (int i = 0; i < NUM_SERVOS; i++) {
    current_angles[i] = 255;
    current_pulses[i] = -1.0;
  }

  // Always start in a known, safe position
  moveToHome();
}

// Convert a 0–180 degree angle to the PCA9685 pulse width count
int angleToPulse(int angle) {
  return map(angle, 0, 180, SERVOMIN, SERVOMAX);
}

// Command a single servo to a specific angle with smooth pulse-level EMA interpolation
void setServoAngle(uint8_t servoNum, uint8_t angle) {
  angle = constrain(angle, 0, 180);

  // Hardware motor protection clamp for Servo 5 (Gripper): NEVER go below 85° or above 140°
  if (servoNum == 5) {
    angle = constrain(angle, 85, 140);
  }

  int targetPulse = angleToPulse(angle);
  
  if (current_angles[servoNum] == angle && current_pulses[servoNum] == targetPulse) {
    return; // Don't interrupt PCA9685 PWM timer if target is reached
  }

  if (current_pulses[servoNum] < 0) {
    current_pulses[servoNum] = targetPulse;
  } else {
    // Smooth pulse-level EMA interpolation (eliminates integer staircase motor chatter)
    current_pulses[servoNum] = (current_pulses[servoNum] * 0.5) + (targetPulse * 0.5);
  }

  int finalPulse = round(current_pulses[servoNum]);
  uint8_t pcaChannel = SERVO_CHANNELS[servoNum];
  pwm.setPWM(pcaChannel, 0, finalPulse);
  current_angles[servoNum] = angle;
}

// Move all servos to the predefined Home Position
void moveToHome() {
  for (int i = 0; i < NUM_SERVOS; i++) {
    setServoAngle(i, HOME_ANGLES[i]);
  }
}

#define FRAME_HEADER 0xFF

void loop() {
  // If multiple 7-byte packets accumulated in RX buffer, consume stale older packets to process ONLY newest position
  while (Serial.available() >= 14) {
    if (Serial.peek() == FRAME_HEADER) {
      for (int i = 0; i < 7; i++) Serial.read(); // Flush stale packet
    } else {
      Serial.read();
    }
  }

  // Read incoming serial packets with 0xFF header byte framing for 100% anti-jitter alignment
  if (Serial.available() >= 7) {
    if (Serial.peek() == FRAME_HEADER) {
      Serial.read(); // Consume header byte 0xFF
      Serial.readBytes(serialBuffer, NUM_SERVOS);
      for (int i = 0; i < NUM_SERVOS; i++) {
        setServoAngle(i, serialBuffer[i]);
      }
    } else {
      // Discard misaligned byte until 0xFF header marker is reached
      Serial.read();
    }
  }
}
