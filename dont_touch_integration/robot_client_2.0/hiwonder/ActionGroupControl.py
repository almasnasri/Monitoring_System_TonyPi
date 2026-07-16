#!/usr/bin/env python3
# encoding: utf-8
"""
Action Group Control for TonyPi Robot.
Executes pre-recorded motion sequences stored as .d6a files (SQLite databases).

Available actions (typical TonyPi configuration):
- go_forward, go_forward_fast, back, back_fast: Walking
- turn_left, turn_right: Turning
- stand: Standing position
- squat_down: Squatting
- wave: Waving hand
- left_kick, right_kick: Kicking
- bow: Bowing
"""

import os
import sys
import time
import threading

# Try to import required modules
try:
    import sqlite3 as sql
    SQLITE_AVAILABLE = True
except ImportError:
    SQLITE_AVAILABLE = False

# Import controller
try:
    from . import ros_robot_controller_sdk as rrc
    from .Controller import Controller
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False

# Global state
runningAction = False
stop_action = False
stop_action_group = False

# Initialize board and controller if available
board = None
ctl = None

if HARDWARE_AVAILABLE:
    try:
        board = rrc.Board()
        ctl = Controller(board)
    except Exception as e:
        print(f"Warning: Could not initialize hardware: {e}")
        HARDWARE_AVAILABLE = False


def stopAction():
    """Stop the currently running action."""
    global stop_action
    stop_action = True


def stopActionGroup():
    """Stop the currently running action group."""
    global stop_action_group
    stop_action_group = True 


# State tracking for walking actions
__end = False
__start = True
current_status = ''


def runActionGroup(actName, times=1, with_stand=False, lock_servos='', path=None):
    """
    Run an action group (sequence of motions).
    
    Args:
        actName: Name of the action (without .d6a extension)
        times: Number of times to repeat (0 = infinite)
        with_stand: Whether to return to standing position after walking
        lock_servos: Dict of servo_id: position to lock during action
        path: Path to ActionGroups folder (default: /home/pi/TonyPi/ActionGroups/)
    """
    global __end
    global __start
    global current_status
    global stop_action_group
    
    if path is None:
        # Default path on TonyPi
        path = "/home/pi/TonyPi/ActionGroups/"
        # Also check local path for development
        local_path = os.path.join(os.path.dirname(__file__), '..', 'ActionGroups')
        if os.path.exists(local_path):
            path = local_path + "/"
    
    temp = times
    walking_actions = ['go_forward', 'go_forward_fast', 'go_forward_slow', 'back', 'back_fast']
    
    while True:
        if temp != 0:
            times -= 1
        try:
            if actName not in walking_actions or stop_action_group:
                if __end:
                    __end = False
                    if current_status == 'go':
                        runAction('go_forward_end', lock_servos, path=path)
                    else:
                        runAction('back_end', lock_servos, path=path)
                    
                if stop_action_group:
                    __end = False
                    __start = True
                    stop_action_group = False                        
                   
                    break
                __start = True
                if times < 0:
                    __end = False
                    __start = True
                    stop_action_group = False 
                    break
                runAction(actName, lock_servos, path=path)
            else:
                if times < 0:
                    if with_stand:
                        if actName in ['go_forward', 'go_forward_fast', 'go_forward_slow']:
                            runAction('go_forward_end', lock_servos, path=path)
                        else:
                            runAction('back_end', lock_servos, path=path)
                    break
                if __start:
                    __start = False
                    __end = True
                    
                    if actName in ['go_forward', 'go_forward_slow']:                       
                        runAction('go_forward_start', lock_servos, path=path)
                        current_status = 'go'
                    elif actName == 'go_forward_fast':
                        runAction('go_forward_start_fast', lock_servos, path=path)
                        current_status = 'go'
                    elif actName == 'back':
                        runAction('back_start', lock_servos, path=path)
                        runAction('back', lock_servos, path=path)
                        current_status = 'back'                    
                    elif actName == 'back_fast':
                        runAction('back_start', lock_servos, path=path)
                        runAction('back_fast', lock_servos, path=path)
                        current_status = 'back'
                else:
                    runAction(actName, lock_servos, path=path)
        except Exception as e:
            print(f"Action group error: {e}")
            break


def runAction(actNum, lock_servos='', path=None):
    """
    Run a single action (motion sequence from .d6a file).
    
    Args:
        actNum: Name of the action (without .d6a extension)
        lock_servos: Dict of servo_id: position to lock during action
        path: Path to ActionGroups folder
    """
    global runningAction
    global stop_action
    
    if not HARDWARE_AVAILABLE or ctl is None:
        print(f"Simulating action: {actNum}")
        time.sleep(0.5)  # Simulate action duration
        return
    
    if not SQLITE_AVAILABLE:
        print(f"SQLite not available, cannot run action: {actNum}")
        return
    
    if actNum is None:
        return
    
    if path is None:
        path = "/home/pi/TonyPi/ActionGroups/"

    actNum = path + actNum + ".d6a"

    if os.path.exists(actNum):
        if runningAction is False:
            runningAction = True
            try:
                ag = sql.connect(actNum)
                cu = ag.cursor()
                cu.execute("select * from ActionGroup")
                while True:
                    act = cu.fetchone()
                    if stop_action is True:
                        stop_action = False
                        print('Action stopped')                    
                        break
                    if act is not None:
                        for i in range(0, len(act) - 2, 1):
                            if str(i + 1) in lock_servos:
                                ctl.set_bus_servo_pulse(i + 1, lock_servos[str(i + 1)], act[1])
                            else:
                                ctl.set_bus_servo_pulse(i + 1, act[2 + i], act[1])
                        time.sleep(float(act[1]) / 1000.0)
                    else:
                        # Action complete
                        break
                cu.close()
                ag.close()
            except Exception as e:
                print(f"Error running action: {e}")
            finally:
                runningAction = False
    else:
        runningAction = False
        print(f"Action file not found: {actNum}")
        print(f"Please ensure action files are in: {path}")


# Action name mappings for convenience
ACTION_MAPPING = {
    "forward": "go_forward",
    "backward": "back",
    "left": "turn_left",
    "right": "turn_right",
    "stop": None,
    "stand": "stand",
    "squat": "squat_down",
    "wave": "wave",
    "kick_left": "left_kick",
    "kick_right": "right_kick",
    "bow": "bow",
}


def executeMovement(direction, times=1, with_stand=True):
    """
    Execute a movement command by direction name.
    
    Args:
        direction: Movement direction (forward, backward, left, right, stop, stand, etc.)
        times: Number of times to repeat
        with_stand: Whether to return to standing after walking
        
    Returns:
        dict: Result with success status and message
    """
    if direction == "stop":
        stopActionGroup()
        return {"success": True, "message": "Stopped"}
    
    action = ACTION_MAPPING.get(direction.lower())
    if action:
        runActionGroup(action, times=times, with_stand=with_stand)
        return {"success": True, "message": f"Executed {action}"}
    
    return {"success": False, "message": f"Unknown direction: {direction}"}


if __name__ == "__main__":
    print("Action Group Control Test")
    print(f"Hardware available: {HARDWARE_AVAILABLE}")
    print(f"SQLite available: {SQLITE_AVAILABLE}")
    
    # Test with a simple action
    print("\nTesting stand action...")
    executeMovement("stand")
    
    print("\nTest complete")
