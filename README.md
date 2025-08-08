# RockBlock to MAVLink gateway

Simple Python script for sending and receiving MAVLink messages using the RockBlock 9603/9704 SBD modems, allowing **worldwide** telemetry with an ArduPilot platform.

This gateway runs on the GCS, and will send/recieve MAVLink messages between the GCS and RockBlock servers.

**The 9603 and 9704 modems have seperate requirements and configuration. Ensure you are using the correct
section of the documentation below**

## Rockblock 9704

The Rockblock 9704 uses MAVLink2 messages.

There are two methods to run the gateway for recieving packets:
- Using Adafuit.io (https://io.adafruit.com/) to recieve the packets
- Using a public-facing webserver to recieve the packets

Required hardware, software and services:
- Rockblock Modem (such as https://www.groundcontrol.com/product/rockblock-9704/)
- Cables to connect modem with flight controller
- ArduPilot 4.7+ with a flight controller capable of running Lua scripts
- Active Cloudloop account (https://console.cloudloop.com/) with MQTT endpoint

### Modem setup

See ArduPilot documentation (TBC)

### Cloudloop Setup

Ensure the modem is activated.

In the Cloudloop "data" page, configure the Rockblock modem to have an MQTT destination.

Download the MQTT certificate zip file.

### rockblock2mav setup

On the GCS install the required Python libraries via ``pip3 install paho-mqtt pymavlink --user``

Run the MQTT gateway to establish the link between Cloudloop and your GCS:

```bash
./rockblock2mav-mqtt.py -account_id <ACCOUNT_ID> -thing_id <THING_ID> <CERT_ZIP_PATH>
```

Where:
- `<ACCOUNT_ID>`: Your Cloudloop account ID (found in the ``hello.txt`` file within the MQTT certificate zip file, as ``iot/<ACCOUNT_ID>/#``)
- `<THING_ID>`: Your modem's Thing ID (found in "Things" page)
- `<CERT_ZIP_PATH>`: Path to the downloaded MQTT certificate zip file

#### Command Line Options

- `-account_id`: Cloudloop account ID (required)
- `-thing_id`: Thing (modem) ID from Cloudloop console (required)
- `cert_zip`: Path to MQTT certificate zip file (required)
- `--host`: MQTT broker host (default: mqtt.cloudloop.com)
- `--port`: MQTT broker port (default: 8883)
- `-out`: MAVLink connection string (default: udpin:127.0.0.1:16000)


### GCS Connections

The gateway outputs MAVLink data on UDP port 16000 by default. Configure your GCS as follows:

**MAVProxy:**
```bash
mavproxy.py --master=udpout:127.0.0.1:16000 --console
```

**QGroundControl:**
- Add UDP connection
- Set to "UDP Server" mode
- Port: 16000

**Mission Planner:**
- Use UDP connection
- IP: 127.0.0.1, Port: 16000
- Note: Change output to `udpin:127.0.0.1:14550` for better Mission Planner compatibility


### Limitations

- **Message Types**: Only HIGH_LATENCY2 messages are sent from vehicle to GCS by default
- **Sky Visibility**: Modem requires clear view of sky - will not work indoors or under heavy tree cover
- **Allowed GCS→Vehicle Messages**: Limited to:
  - `COMMAND_LONG`, `COMMAND_INT`
  - `MISSION_ITEM_INT`, `MISSION_SET_CURRENT`
  - `SET_MODE`
- **Data Costs**: Iridium satellite communication incurs per-message costs
- **Latency**: Message delivery can take 10-60 seconds depending on satellite coverage
- **Reliability**: Message delivery is not guaranteed - implement retry logic for critical commands


## Rockblock 9602/9602

Due to bandwidth constraints (50 bytes per message) MAVLink 1 is used, as it uses slightly less bytes per message
compared to MAVLink2. An option is available (``-mav20``) to convert messages to/from MAVLink V2 on the GCS side. This allows the GCS to continue using MAVLink V2.

There are two methods to run the gateway for recieving packets:
- Using Adafuit.io (https://io.adafruit.com/) to recieve the packets
- Using a public-facing webserver to recieve the packets

Required hardware, software and services:
- Rockblock Modem (such as https://www.sparkfun.com/products/14498 and cable https://www.sparkfun.com/products/14720)
- ArduPilot 4.4+ with a flight controller capable of running Lua scripts
- Active RockBlock account (https://rockblock.rock7.com/Operations)

### Using adafruit.io
An Adafuit.io account (https://io.adafruit.com/) is required.

<img src="https://raw.githubusercontent.com/stephendade/rockblock2mav/main/diagram.jpg" width="400">

#### Setup:
1. Connect the Rockblock modem to a spare UART on the flight controller. Only the +5V, RX, TX and GND lines need to be connected
2. Ensure the modem is activated in the RockBlock account
3. Create a new feed on adafuit.io. Ensure the Feed History is OFF and a webhook is active. Connect this to your Rockblock account (https://learn.adafruit.com/using-the-rockblock-iridium-modem/forwarding-messages).
4. Copy the Ardupilot Rockblock Lua script to the flight controller, configuring as required.
5. On the GCS install the required Python libraries via ``pip3 install adafruit-io pymavlink --user``
6. On the GCS run rockblock2mav-adafruit.py to process the packets. By default it will send/receive telemetry on 127.0.0.1:16000

#### Commandline options
- ``-adafruitusername``       Adafruit.io username
- ``-adafruitfeed``           Adafruit.io feed name
- ``-adafruitkey``            Adafruit.io API key
- ``-imei``                   Iridium Modem IMEI number
- ``-out``                    MAVLink connection string (default: udpin:127.0.0.1:16000) to GCS
- ``-rock7username``          Rock7 account username
- ``-rock7password``          Rock7 account password
- ``-debug``             MAVLink connection string to view messages sent to the vehicle
- ``-mav20``             Use MAVLink V2 messages on ``-out``, instead of MAVLink V1

### Using a public webserver
A server (such as Amazon EC2) with a public URL is required.

#### Setup:
1. Connect the Rockblock modem to a spare UART on the flight controller. Only the +5V, RX, TX and GND lines need to be connected
2. Ensure the modem is activated in the RockBlock account
3. Copy the Ardupilot Rockblock Lua script to the flight controller, configuring as required.
4. On the server install the required Python libraries via ``pip3 install pymavlink flask --user``
5. Ensure the server has an open http port (5000 by default), with the Rockblock IP addresses whitelisted (https://docs.groundcontrol.com/iot/rockblock/web-services/integration)
6. In your rockblock account, add a HTTP_POST Delivery Address in the format ``http://<your url>:5000/rock``
7. On the Server run rockblock2mav-webhook.py to process the packets. By default it will send/receive telemetry on 127.0.0.1:16000

#### Commandline options
- ``-imei``              Iridium Modem IMEI number
- ``-out``               MAVLink connection string (default: udpin:127.0.0.1:16000) to GCS
- ``-rock7username``     Rock7 account username
- ``-rock7password``     Rock7 account password
- ``-tcpinput``          Public ip and port to bind to, for the Rock7 webhook. In format <IP>:<port>
- ``-debug``             MAVLink connection string to view messages sent to the vehicle
- ``-mav20``             Use MAVLink V2 messages on ``-out``, instead of MAVLink V1

### SystemD Service

For running unattended, a Systemd service is provided at ``rockblock2mav.service``. The file will need to be edited to have the correct user and folder specified (current default is user "pi"), along with the Rockblock account details

To install the service, run the following:
```
sudo cp rockblock2mav.service /etc/systemd/system
sudo systemctl daemon-reload
sudo systemctl enable rockblock2mav.service
sudo systemctl start rockblock2mav.service
```

### GCS Connections

Note for QGC users:
- Use the "udpin" output option, as the default "udpout" isn't compatible. For example ``rockblock2mav-adafruit.py -out:udpout:127.0.0.1:16000``

Note that Mission Planner has limited support at this time.

### Limitations:
- The flight controller will only send HIGH_LATENCY2 MAVlink messages. This will give basic position and status information. This message
is sent once per 60 seconds by default
- The Rockblock modem does require a full view of the sky to work reliably. It will not work indoors.
- Only the MAVLink messages ``COMMAND_LONG``, ``COMMAND_INT``, ``MISSION_ITEM_INT``, ``MISSION_SET_CURRENT`` and ``SET_MODE`` are sent from the GCS to the Rockblock.
- The only command messages sent from the GCS to the Rockblock modem are the following:
  - ``MAV_CMD_NAV_RETURN_TO_LAUNCH``
  - ``MAV_CMD_NAV_LAND``
  - ``MAV_CMD_NAV_TAKEOFF``
  - ``MAV_CMD_NAV_VTOL_TAKEOFF``
  - ``MAV_CMD_NAV_VTOL_LAND``
  - ``MAV_CMD_DO_SET_MODE``
  - ``MAV_CMD_DO_CHANGE_SPEED``
  - ``MAV_CMD_DO_SET_SERVO``
  - ``MAV_CMD_DO_PARACHUTE``
  - ``MAV_CMD_MISSION_START``
  - ``MAV_CMD_COMPONENT_ARM_DISARM``
  - ``MAV_CMD_DO_REPOSITION``
  - ``MAV_CMD_CONTROL_HIGH_LATENCY``
  