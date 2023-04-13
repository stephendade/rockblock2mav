# RockBlock to MAVLink gateway

Simple Python script for sending and receiving MAVLink messages using the RockBlock SBD modems, allowing **worldwide** telemetry with an ArduPilot platform.

This gateway runs on the GCS, and will send/recieve MAVLink messages between the GCS and RockBlock servers.

Due to bandwidth constraints (50 bytes per message) MAVLink 1 is used, as it uses slightly less bytes per message
compared to MAVLink2.

Required hardware, software and services:
- Rockblock Modem (such as https://www.sparkfun.com/products/14498 and cable https://www.sparkfun.com/products/14720)
- ArduPilot 4.4+ with a flight controller capable of running Lua scripts
- Active RockBlock account (https://rockblock.rock7.com/Operations)
- Adafuit.io account (https://io.adafruit.com/)

Due to limitations of the Rockblock web service, all received packets need to go via a public-facing web service. See https://docs.rockblock.rock7.com/docs/integration-with-application for details. For the purposes of this configuration, adafruit.io is used.

<img src="https://raw.githubusercontent.com/stephendade/rockblock2mav/main/diagram.jpg" width="400">

## Setup:
1. Connect the Rockblock modem to a spare UART on the flight controller. Only the +5V, RX, TX and GND lines need to be connected
2. Ensure the modem is activated in the RockBlock account
3. Create a new feed on adafuit.io. Ensure the Feed History is OFF and a webhook is active. Connect this to your Rockblock account (https://learn.adafruit.com/using-the-rockblock-iridium-modem/forwarding-messages).
4. Copy the Ardupilot Rockblock Lua script to the flight controller, configuring as required.
5. On the GCS install the required Python libraries via ``pip3 install adafruit-io pymavlink``
6. On the GCS run rockblock2mav.py to send/receive telemetry on 127.0.0.1:16000. Ensure the GCS is connected to this ip/port.

## Limitations:
- The flight controller will only send HIGH_LATENCY2 MAVlink messages. This will give basic position and status information. This message
is sent once per 20 seconds
- The Rockblock modem does require a full view of the sky to work reliably. It will not work indoors.
- The only command (``COMMAND_LONG``, ``COMMAND_INT``) messages sent from the GCS to the Rockblock modem are the following:
  - ``MAV_CMD_NAV_RETURN_TO_LAUNCH``
  - ``MAV_CMD_NAV_LAND``
  - ``MAV_CMD_NAV_TAKEOFF``
  - ``MAV_CMD_NAV_VTOL_TAKEOFF``
  - ``MAV_CMD_NAV_VTOL_LAND``
  - ``MAV_CMD_DO_SET_MODE``
  - ``MAV_CMD_MISSION_START``
  - ``MAV_CMD_COMPONENT_ARM_DISARM``
  - ``MAV_CMD_CONTROL_HIGH_LATENCY``
  
The ``MISSION_ITEM_INT`` message is also supported.



