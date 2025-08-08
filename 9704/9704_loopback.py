#!/usr/bin/env python3
import time
import json
import base64
from enum import Enum
import serial

"""
Thsi script connects to a RockBLOCK 9704 modem, initializes it and
sends back (pings) any message received on the RAW topic.
It uses the serial port to communicate with the modem and handles
the modem state transitions based on the responses received.
"""

#enum  	responseCodes {
#  JSPR_RC_NO_ERROR = 200 , JSPR_RC_UNSOLICITED_MESSAGE = 299 , JSPR_RC_API_VERSION_NOT_SELECTED = 400 , JSPR_RC_UNSUPPORTED_REQUEST_TYPE = 401 ,
#  JSPR_RC_CONFIGURATION_ALREADY_SET = 402 , JSPR_RC_COMMAND_TOO_LONG = 403 , JSPR_RC_UNKNOWN_TARGET = 404 , JSPR_RC_COMMAND_MALFORMED = 405 ,
#  JSPR_RC_OPERATION_NOT_ALLOWED = 406 , JSPR_RC_BAD_JSON = 407 , JSPR_RC_REQUEST_FAILED = 408 , JSPR_RC_UNAUTHORIZED = 409 ,
#  JSPR_RC_SIM_NOT_CONFIGURED = 410 , JSPR_RC_WAKE_XCVR_IN_INVALID = 411 , JSPR_RC_INVALID_CHANNEL = 412 , JSPR_RC_INVALID_ACTION = 413 ,
#  JSPR_RC_HARDWARE_NOT_CONFIGURED = 414 , JSPR_RC_INVALID_RADIO_PATH = 415 , JSPR_RC_CRASH_DUMP_NOT_AVAILABLE = 416 , JSPR_RC_FEATURE_NOT_SUPPORTED_BY_HARDWARE = 417 ,
#  JSPR_RC_NOT_PROVISIONED = 418 , JSPR_RC_INVALID_TRANSMIT_POWER = 419 , JSPR_RC_INVALID_BURST_TYPE = 420 , JSPR_RC_SERIAL_PORT_ERROR = 500
#}


class ModemState(Enum):
    """Enum to represent the state of the modem"""
    BOOTED1 = "booted1"
    BOOTED2 = "booted2"
    BOOTED3 = "booted3"
    API_CONFIGURED = "api_configured"
    SIM_CONFIGURED = "sim_configured"
    OPERATIONAL_CONFIGURED = "operational_configured"
    CONSTELLATION_FIRST_VISIBLE = "constellation_first_visible"


class Modem9704:
    """Class to handle 9704 satellite modem operations"""

    CRC16_TABLE = [
        0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50a5, 0x60c6, 0x70e7,
        0x8108, 0x9129, 0xa14a, 0xb16b, 0xc18c, 0xd1ad, 0xe1ce, 0xf1ef,
        0x1231, 0x0210, 0x3273, 0x2252, 0x52b5, 0x4294, 0x72f7, 0x62d6,
        0x9339, 0x8318, 0xb37b, 0xa35a, 0xd3bd, 0xc39c, 0xf3ff, 0xe3de,
        0x2462, 0x3443, 0x0420, 0x1401, 0x64e6, 0x74c7, 0x44a4, 0x5485,
        0xa56a, 0xb54b, 0x8528, 0x9509, 0xe5ee, 0xf5cf, 0xc5ac, 0xd58d,
        0x3653, 0x2672, 0x1611, 0x0630, 0x76d7, 0x66f6, 0x5695, 0x46b4,
        0xb75b, 0xa77a, 0x9719, 0x8738, 0xf7df, 0xe7fe, 0xd79d, 0xc7bc,
        0x48c4, 0x58e5, 0x6886, 0x78a7, 0x0840, 0x1861, 0x2802, 0x3823,
        0xc9cc, 0xd9ed, 0xe98e, 0xf9af, 0x8948, 0x9969, 0xa90a, 0xb92b,
        0x5af5, 0x4ad4, 0x7ab7, 0x6a96, 0x1a71, 0x0a50, 0x3a33, 0x2a12,
        0xdbfd, 0xcbdc, 0xfbbf, 0xeb9e, 0x9b79, 0x8b58, 0xbb3b, 0xab1a,
        0x6ca6, 0x7c87, 0x4ce4, 0x5cc5, 0x2c22, 0x3c03, 0x0c60, 0x1c41,
        0xedae, 0xfd8f, 0xcdec, 0xddcd, 0xad2a, 0xbd0b, 0x8d68, 0x9d49,
        0x7e97, 0x6eb6, 0x5ed5, 0x4ef4, 0x3e13, 0x2e32, 0x1e51, 0x0e70,
        0xff9f, 0xefbe, 0xdfdd, 0xcffc, 0xbf1b, 0xaf3a, 0x9f59, 0x8f78,
        0x9188, 0x81a9, 0xb1ca, 0xa1eb, 0xd10c, 0xc12d, 0xf14e, 0xe16f,
        0x1080, 0x00a1, 0x30c2, 0x20e3, 0x5004, 0x4025, 0x7046, 0x6067,
        0x83b9, 0x9398, 0xa3fb, 0xb3da, 0xc33d, 0xd31c, 0xe37f, 0xf35e,
        0x02b1, 0x1290, 0x22f3, 0x32d2, 0x4235, 0x5214, 0x6277, 0x7256,
        0xb5ea, 0xa5cb, 0x95a8, 0x8589, 0xf56e, 0xe54f, 0xd52c, 0xc50d,
        0x34e2, 0x24c3, 0x14a0, 0x0481, 0x7466, 0x6447, 0x5424, 0x4405,
        0xa7db, 0xb7fa, 0x8799, 0x97b8, 0xe75f, 0xf77e, 0xc71d, 0xd73c,
        0x26d3, 0x36f2, 0x0691, 0x16b0, 0x6657, 0x7676, 0x4615, 0x5634,
        0xd94c, 0xc96d, 0xf90e, 0xe92f, 0x99c8, 0x89e9, 0xb98a, 0xa9ab,
        0x5844, 0x4865, 0x7806, 0x6827, 0x18c0, 0x08e1, 0x3882, 0x28a3,
        0xcb7d, 0xdb5c, 0xeb3f, 0xfb1e, 0x8bf9, 0x9bd8, 0xabbb, 0xbb9a,
        0x4a75, 0x5a54, 0x6a37, 0x7a16, 0x0af1, 0x1ad0, 0x2ab3, 0x3a92,
        0xfd2e, 0xed0f, 0xdd6c, 0xcd4d, 0xbdaa, 0xad8b, 0x9de8, 0x8dc9,
        0x7c26, 0x6c07, 0x5c64, 0x4c45, 0x3ca2, 0x2c83, 0x1ce0, 0x0cc1,
        0xef1f, 0xff3e, 0xcf5d, 0xdf7c, 0xaf9b, 0xbfba, 0x8fd9, 0x9ff8,
        0x6e17, 0x7e36, 0x4e55, 0x5e74, 0x2e93, 0x3eb2, 0x0ed1, 0x1ef0
    ]

    def __init__(self, port='/dev/ttyUSB0', baudrate=230400):
        """Initialize the modem connection"""
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.modem_state = ModemState.BOOTED1
        self.raw_topic_id = None
        self.const_visible = False
        self.message_id = 0
        self.request_reference = 0
        self.cur_message = None
        self.running = False
        self.rxbuffer = b''
        self.txbuffer = None
        self.bars = 0

    def connect(self):
        """Connect to the modem"""
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=0.1)
            print(f"[INFO] Opened serial port {self.port} at {self.baudrate} baud.")
            return True
        except serial.SerialException as e:
            print(f"[ERROR] Could not open serial port: {e}")
            return False

    def disconnect(self):
        """Disconnect from the modem"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("[INFO] Serial port closed.")

    def calculate_crc(self, buffer, initial_crc=0x0000):
        """
        Calculate CRC-16-CCITT using a lookup table.

        Args:
            buffer: Bytes or bytearray to calculate CRC for
            initial_crc: Initial CRC value

        Returns:
            The calculated CRC value (16-bit)
        """
        crc = initial_crc & 0xFFFF

        if buffer:
            for i in range(len(buffer)):
                data = buffer[i]
                table_index = ((crc >> 8) ^ data) & 0xFF
                crc = ((crc << 8) ^ self.CRC16_TABLE[table_index]) & 0xFFFF

        return crc

    def encode_message(self, message):
        """Encode a message to be sent over the modem."""
        # Calculate CRC using the specific initial value
        crc = self.calculate_crc(message)
        print(f"[INFO] CRC: 0x{crc:04X}")

        crc_hex = f"{crc:04x}"
        print(f"[INFO] CRC as hex string: '{crc_hex}'")

        # Convert hex string to bytes
        crc_bytes = bytes.fromhex(crc_hex)
        print(f"[INFO] CRC as bytes: {crc_bytes}")

        # Append CRC bytes to the message
        result = message + crc_bytes
        print(f"[INFO] Final encoded message: {result}")

        # Encode to base64
        encoded_message = base64.b64encode(result).decode('ascii')
        print(f"[INFO] Encoded message: {encoded_message}")
        return encoded_message

    def decode_message(self, encoded_message: str) -> tuple:
        """
        Decode a message received from the modem.

        Args:
            encoded_message: Base64-encoded message string

        Returns:
            tuple: (message_data, crc_received, crc_calculated)
                - message_data: The decoded message bytes without CRC
                - crc_received: The CRC bytes received with the message
                - crc_calculated: The CRC bytes calculated from the message
        """
        # Decode from base64
        decoded_bytes = base64.b64decode(encoded_message)

        # Extract CRC from the last 2 bytes
        crc_received = decoded_bytes[-2:]
        message_data = decoded_bytes[:-2]

        # Calculate CRC for the message data
        crc_calculated = self.calculate_crc(message_data)

        # Convert calculated CRC to bytes
        crc_calculated_bytes = crc_calculated.to_bytes(2, byteorder='big')

        return message_data, crc_received, crc_calculated_bytes

    def send_get_command(self, command):
        """Send GET command to the modem"""
        self.cur_message = command
        command_str = f"GET {command} {{}}\r"
        print(f"[TX] {command_str.strip()}")
        self.ser.write(command_str.encode())
        time.sleep(0.02)

    def send_put_command(self, command, options):
        """Send PUT command to the modem"""
        command_str = f"PUT {command} {{{options}}}\r"
        print(f"[TX] {command_str.strip()}")
        self.cur_message = command
        self.ser.write(command_str.encode())
        time.sleep(0.02)

    def read_serial(self):
        """Read and process data from the serial port"""
        self.rxbuffer += self.ser.read(self.ser.in_waiting)

        # now split the buffer into lines
        if b'\r' in self.rxbuffer:
            lines = self.rxbuffer.split(b'\r')
            self.rxbuffer = lines[-1]
            for line in lines[:-1]:
                line = line.decode('ascii', errors='replace').strip()
                if line:
                    self.process_line(line)

    def process_line(self, line):
        """Process a line (single response) received from the modem"""
        try:
            print(f"[RX] {line}")

            # Process the line if needed
            parts = []
            for part in line.split():
                if '{' in part:
                    parts.extend(line[line.index(part):].split())
                    break
                parts.append(part)

            if parts[0] == '\x00':
                return  # Ignore empty lines

            response_code = int(parts[0])
            target = parts[1]
            json_response = json.loads(parts[2])
            print(f"[RX] Code: {response_code}, Target: {target}, Response: {json_response}")

            if target == self.cur_message:
                print(f"[INFO] Command {self.cur_message.strip()} acknowledged by modem.")
                self.cur_message = None
            elif self.cur_message:
                print(f"[INFO] Command {self.cur_message.strip()} not acknowledged by modem, received {target} instead.")

            if response_code == 400:
                # apiversion not selected
                self.modem_state = ModemState.BOOTED2
                return

            if target == "apiVersion" and response_code in [200, 299, 402] and json_response.get("active_version", {}).get("major", 0) >= 1:
                self.modem_state = ModemState.BOOTED3
            elif target == "apiVersion" and response_code in [200, 299, 402]:
                self.modem_state = ModemState.BOOTED2
            elif target == "hwInfo" and response_code in [200, 299, 402]:
                self.modem_state = ModemState.API_CONFIGURED
            elif target == "simConfig" and response_code in [200, 299, 402]:
                self.modem_state = ModemState.SIM_CONFIGURED
            elif target == "operationalState" and response_code in [200, 299, 402, 406]:
                self.modem_state = ModemState.OPERATIONAL_CONFIGURED
                print("---Modem configured---")
            elif (target == "constellationState" and response_code in [200, 299] and
                    json_response.get("constellation_visible", False)):
                self.modem_state = ModemState.CONSTELLATION_FIRST_VISIBLE
                self.bars = json_response.get("signal_bars", 0)
            elif target == "constellationState" and response_code in [200, 299]:
                self.bars = json_response.get("signal_bars", 0)
            elif target == "messageProvisioning" and response_code in [200, 299]:
                if json_response.get("provisioning", []):
                    print(f"[INFO] Topics received: {json_response['provisioning']}")
                    # If there is a topic called RAW
                    if any(topic['topic_name'] == 'RAW' for topic in json_response['provisioning']):
                        self.raw_topic_id = next(topic['topic_id'] for topic in json_response['provisioning'] if topic['topic_name'] == 'RAW')
                        print(f"[INFO] RAW topic ID: {self.raw_topic_id}")
            elif target == "messageOriginate" and response_code in [200, 299]:
                request_reference_rx = json_response.get("request_reference", self.request_reference)
                if self.request_reference == request_reference_rx and json_response.get("message_response", "") == "message_accepted":
                    self.message_id = json_response.get("message_id", 0)
                    # send the segment
                    encoded_message = self.encode_message(self.txbuffer)
                    length = len(self.txbuffer) + 2  # +2 for CRC
                    self.send_put_command("messageOriginateSegment",
                                          f"\"topic_id\":{self.raw_topic_id}, \"message_id\":{self.message_id}, \"segment_length\":{length}, \"segment_start\":0, \"data\":\"{encoded_message}\"")
            elif target == "messageOriginateStatus" and response_code in [200, 299]:
                if json_response.get("final_mo_status", "") == "mo_ack_received" and json_response.get("message_id", 0) == self.message_id:
                    print(f"[INFO] Message {self.message_id} acknowledged by modem.")
                    print("---Message Sent---")
                elif json_response.get("message_id", 0) == self.message_id:
                    print(f"[INFO] Message {self.message_id} errored by modem.")
                    print("---Message NOT Sent---")
                self.txbuffer = None
            elif target == "messageTerminateSegment" and response_code == 299:
                message_id_rx = json_response.get("message_id", 0)
                message_data = json_response.get("data", '')
                message_data_decoded, crc_received, crc_calculated = self.decode_message(message_data)

                # check the CRC
                if crc_received != crc_calculated:
                    print(f"[ERROR] CRC mismatch! Received: {crc_received}, Calculated: {crc_calculated}")
                else:
                    print(f"[INFO] CRC match successful for message {message_id_rx}. Data: {message_data_decoded}")
                    if self.raw_topic_id:
                        print("Sending back message back")
                        decoded_str = message_data_decoded.decode('ascii', errors='replace')
                        self.send_message("Ping back " + decoded_str)
                    else:
                        print("[INFO] Not ready to send messages, waiting for topics or bars.")

        except serial.SerialException as e:
            print(f"[ERROR] Serial read failed: {e}")
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")

    def send_message(self, message):
        """Send a message through the modem"""
        if isinstance(message, str):
            message = message.encode('ascii')

        if not self.raw_topic_id:
            print("[ERROR] No RAW topic ID available. Cannot send message.")
            return False

        if self.bars == 0:
            print("[ERROR] No signal bars available. Cannot send message.")
            return False

        if self.txbuffer:
            print("[ERROR] Modem is already processing a message. Please wait.")
            return False

        # Send messageOriginate
        self.request_reference += 1
        length = len(message) + 2  # +2 for CRC
        self.txbuffer = message
        self.send_put_command("messageOriginate", 
                                f"\"topic_id\":{self.raw_topic_id}, \"message_length\":{length}, \"request_reference\":{self.request_reference}")
        return True

    def initialize(self):
        """Initialize the modem and prepare it for sending messages"""
        self.running = True
        while self.running:
            self.read_serial()  # Read serial input

            if not self.cur_message:
                if self.modem_state == ModemState.BOOTED1:
                    self.send_get_command("apiVersion")
                elif self.modem_state == ModemState.BOOTED2:
                    self.send_put_command("apiVersion", "\"active_version\": {\"major\": 1, \"minor\": 6, \"patch\": 1}")
                elif self.modem_state == ModemState.BOOTED3:
                    self.send_get_command("hwInfo")
                elif self.modem_state == ModemState.API_CONFIGURED:
                    self.send_put_command("simConfig", "\"interface\": \"internal\"")
                elif self.modem_state == ModemState.SIM_CONFIGURED:
                    self.send_put_command("operationalState", "\"state\": \"active\"")
                elif self.modem_state == ModemState.CONSTELLATION_FIRST_VISIBLE and not self.raw_topic_id:
                    self.send_get_command("messageProvisioning")

            time.sleep(0.02)  # Wait for responses to be processed

            # Return once we've got the constellation visible and raw topic ID
            if self.modem_state == ModemState.CONSTELLATION_FIRST_VISIBLE and self.raw_topic_id:
                return True

        return False

    def run(self):
        """Main loop for the modem"""
        if not self.connect():
            return False

        try:
            if not self.initialize():
                return False

            print("---Modem Ready to go---")
            while self.running:
                self.read_serial()
                time.sleep(0.02)  # Wait for responses to be processed

        except KeyboardInterrupt:
            print("\n[INFO] Ctrl+C detected. Exiting.")
            self.running = False
        finally:
            self.disconnect()

        return True

    def stop(self):
        """Stop the modem processing"""
        self.running = False


def main():
    modem = Modem9704()
    #if not modem.connect():
    #    print("[ERROR] Could not connect to the modem.")
    #    return
    #print("[INFO] Modem connected. Initializing...")
    #if not modem.initialize():
    #    print("[ERROR] Modem initialization failed.")
    #    return
    #print("[INFO] Modem initialized. Ready to send messages.")
    modem.run()
    #modem.decode_message("VHJ5IHRoaXMgb25lIUFJ")
    #modem.decode_message("R2V0IHJlYWR5IHRvIGdvId3E")
    #modem.decode_message("V2hhdCBhYm91dCB0aGlzIG9uZSEKzw==")


if __name__ == "__main__":
    main()
