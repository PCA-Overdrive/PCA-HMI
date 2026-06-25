"""CAN interface frame helpers used by the display dummy source.

The real CAN receive loop will eventually hand the same frame shape to
``decode_can_frame``. For now, ``build_dummy_*`` creates deterministic frames
that match the interface payload fields.
"""

DISTANCE_LEVEL_CAN_ID = 0x400
EXIT_COMPLETE_CAN_ID = 0x401

DISTANCE_LEVEL_MESSAGE = "DistanceLevelCmd"
EXIT_COMPLETE_MESSAGE = "ExitCompleteCmd"

DISTANCE_LEVEL_FIELDS = (
    "FrontLevelCmd",
    "FrontRightLevelCmd",
    "RightFrontLevelCmd",
    "RightBehindLevelCmd",
    "BehindRightLevelCmd",
    "BehindLevelCmd",
    "BehindLeftLevelCmd",
    "LeftBehindLevelCmd",
    "LeftFrontLevelCmd",
    "FrontLeftLevelCmd",
)

GEAR_STATUS = {
    0x00: "P",
    0x01: "D",
    0x02: "R",
}


def normalize_payload(payload):
    """Return a mutable list of uint8 values from common payload shapes."""
    if isinstance(payload, (bytes, bytearray)):
        return list(payload)
    return [int(value) & 0xFF for value in payload]


def parse_distance_level_payload(payload):
    """Parse CAN ID 0x400 DistanceLevelCmd.

    The supplied interface table says DLC 10, but the payload definition uses
    B0 through B13. The parser follows the field table because the display
    needs speed, gear, and collision-alarm state from B11 through B13.
    """
    data = normalize_payload(payload)
    if len(data) < 14:
        raise ValueError("DistanceLevelCmd requires at least 14 payload bytes")

    levels = {
        field_name: min(data[index], 4)
        for index, field_name in enumerate(DISTANCE_LEVEL_FIELDS)
    }

    return {
        "can_id": DISTANCE_LEVEL_CAN_ID,
        "message_name": DISTANCE_LEVEL_MESSAGE,
        "levels": levels,
        "emergency_stop_activated": data[10] == 0x01,
        "vehicle_speed_cmd": data[11],
        "speed": round(data[11] / 10, 1),
        "gear_status_cmd": data[12],
        "gear": GEAR_STATUS.get(data[12], "P"),
        "collision_alarm_tf": data[13],
        "collision_avoidance": data[13] == 0x01,
        "raw_payload": data[:14],
    }


def parse_exit_complete_payload(payload):
    """Parse CAN ID 0x401 ExitCompleteCmd."""
    data = normalize_payload(payload)
    if len(data) < 1:
        raise ValueError("ExitCompleteCmd requires at least 1 payload byte")

    return {
        "can_id": EXIT_COMPLETE_CAN_ID,
        "message_name": EXIT_COMPLETE_MESSAGE,
        "exit_complete": data[0] == 0x01,
        "exit_complete_cmd": data[0],
        "raw_payload": data[:1],
    }


def decode_can_frame(frame):
    """Decode a received CAN frame dictionary.

    Expected shape:
        {"can_id": 0x400, "data": [0x01, ...]}
    ``payload`` is accepted as an alias for ``data`` to make tests and future
    adapters easy to wire.
    """
    can_id = int(frame["can_id"])
    payload = frame.get("data", frame.get("payload", []))

    if can_id == DISTANCE_LEVEL_CAN_ID:
        return parse_distance_level_payload(payload)
    if can_id == EXIT_COMPLETE_CAN_ID:
        return parse_exit_complete_payload(payload)

    raise ValueError(f"Unsupported CAN ID: 0x{can_id:X}")


def build_dummy_distance_level_frame(cycle):
    """Build a deterministic dummy 0x400 frame."""
    levels = [0x01] * len(DISTANCE_LEVEL_FIELDS)
    focus = (cycle // 8) % len(levels)
    levels[focus] = 0x04
    levels[(focus - 1) % len(levels)] = 0x03
    levels[(focus + 1) % len(levels)] = 0x02

    speed_cmds = (0, 35, 60, 25)
    gear_cmds = (0x00, 0x02, 0x01, 0x01)
    speed_cmd = speed_cmds[(cycle // 20) % len(speed_cmds)]
    gear_cmd = gear_cmds[(cycle // 20) % len(gear_cmds)]
    emergency_stop = 0x01 if max(levels) >= 0x04 else 0x00
    collision_alarm = 0x01

    return {
        "can_id": DISTANCE_LEVEL_CAN_ID,
        "message_name": DISTANCE_LEVEL_MESSAGE,
        "data": levels + [emergency_stop, speed_cmd, gear_cmd, collision_alarm],
    }


def build_dummy_exit_complete_frame(cycle):
    """Build a deterministic dummy 0x401 frame."""
    return {
        "can_id": EXIT_COMPLETE_CAN_ID,
        "message_name": EXIT_COMPLETE_MESSAGE,
        "data": [0x01 if (cycle // 60) % 2 else 0x00],
    }
