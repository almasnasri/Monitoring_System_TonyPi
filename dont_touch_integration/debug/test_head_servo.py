from hiwonder import ros_robot_controller_sdk as rrc
import time

board = rrc.Board()

PAN = 2
TILT = 1

def move(pan, tilt):
    board.pwm_servo_set_position(
        0.3,
        [
            [PAN, pan],
            [TILT, tilt]
        ]
    )
    time.sleep(1)

print("CENTER")
move(800, 800)

print("LEFT")
move(1200, 800)

print("RIGHT")
move(400, 800)

print("UP")
move(800, 500)

print("DOWN")
move(800, 1100)

print("CUSTOM TEST")

while True:
    pan = int(input("Pan (300-1300): "))
    tilt = int(input("Tilt (300-1300): "))
    move(pan, tilt)
