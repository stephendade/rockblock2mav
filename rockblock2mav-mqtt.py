#!/usr/bin/env python3
import argparse
import binascii
import json
import time
import zipfile
import os
import base64
import paho.mqtt.client as mqtt
import pymavlink.mavutil as mavutil


# Allowable MAVLink messages to be sent via MQTT
ALLOWABLE_MESSAGES = ["MISSION_ITEM_INT",
                      "MISSION_SET_CURRENT",
                      "SET_MODE"]

# Only send these MAVLink commands, to save bandwidth
ALLOWABLE_CMDS = [20,    # MAV_CMD_NAV_RETURN_TO_LAUNCH
                  21,    # MAV_CMD_NAV_LAND
                  22,    # MAV_CMD_NAV_TAKEOFF
                  84,    # MAV_CMD_NAV_VTOL_TAKEOFF
                  85,    # MAV_CMD_NAV_VTOL_LAND
                  176,   # MAV_CMD_DO_SET_MODE
                  178,   # MAV_CMD_DO_CHANGE_SPEED
                  183,   # MAV_CMD_DO_SET_SERVO
                  208,   # MAV_CMD_DO_PARACHUTE
                  300,   # MAV_CMD_MISSION_START
                  400,   # MAV_CMD_COMPONENT_ARM_DISARM
                  192,   # MAV_CMD_DO_REPOSITION
                  2600]  # MAV_CMD_CONTROL_HIGH_LATENCY

GCS_MAVLINK = None


class CloudloopMQTTClient:
    def __init__(self, cert_zip, host="mqtt.cloudloop.com", port=8883, account_id=None, thing_id=None):
        """
        Initialize the MQTT client with TLS support.
        :param cert_zip: Path to the zip file containing CA, cert, and key files.
        :param
        host: MQTT broker host.
        :param port: MQTT broker port.
        """
        # Extract the zip file
        if not os.path.exists(cert_zip):
            raise FileNotFoundError(f"Certificate zip file {cert_zip} does not exist.")
        with zipfile.ZipFile(cert_zip, 'r') as zip_ref:
            zip_ref.extractall("MqttDelegateCert")
        # Define paths to the extracted certificate files
        ca_path = os.path.join("MqttDelegateCert", "CloudloopMQTT.pem")
        # Search for the certificate file in the certs directory
        cert_files = [f for f in os.listdir("MqttDelegateCert") if f.endswith("-certificate.pem.crt")]
        if not cert_files:
            raise FileNotFoundError("No certificate file found matching *-certificate.pem.crt pattern")
        cert_path = os.path.join("MqttDelegateCert", cert_files[0])
        # Search for the certificate file in the certs directory
        key_paths = [f for f in os.listdir("MqttDelegateCert") if f.endswith("-private.pem.crt")]
        if not key_paths:
            raise FileNotFoundError("No certificate file found matching *-private.pem.crt pattern")
        key_path = os.path.join("MqttDelegateCert", key_paths[0])
        if not (os.path.exists(ca_path) and os.path.exists(cert_path) and os.path.exists(key_path)):
            raise FileNotFoundError("One or more certificate files are missing in the extracted directory.")

        # Initialize the MQTT client
        self.account_id = account_id
        self.thing_id = thing_id
        self.client = mqtt.Client()
        self.client.tls_set(ca_certs=ca_path,
                            certfile=cert_path,
                            keyfile=key_path)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.host = host
        self.port = port

    def on_connect(self, client, userdata, flags, rc):
        print(f"Connected with result code {rc}")
        # Add your subscription topics here
        self.client.subscribe(f"lingo/{self.account_id}/{self.thing_id}/MO")

    def on_message(self, client, userdata, msg):
        # Decode the JSON payload
        payload = None
        try:
            payload = json.loads(msg.payload.decode())
            #print(f"Decoded payload: {payload}")
        except json.JSONDecodeError as e:
            print(f"Failed to decode JSON: {e}")
            return

        # Print out location of modem
        if payload.get('imt').get('location', False):
            lat = payload.get('imt').get('latitude')
            lon = payload.get('imt').get('longitude')
            alt = payload.get('imt').get('altitude', 'N/A')
            print(f"  Location Latitude: {lat}, Longitude: {lon}, Altitude: {alt} meters")
        # get the payload and process it
        # note payload is base64 encoded, decode it
        if payload.get('message'):
            try:
                str_payload = payload.get('message', '')
                # Add padding if necessary
                str_payload += '=' * (-len(str_payload) % 4)
                decoded_payload = base64.b64decode(str_payload)
                print(f"  Payload: {' '.join([f'{b:02x}' for b in decoded_payload])}")
                GCS_MAVLINK.write(decoded_payload)
            except (UnicodeDecodeError, binascii.Error) as e:
                print(f"Failed to decode payload: {e}")
                return
        else:
            print("Received empty payload.")

    def connect(self):
        try:
            self.client.connect(self.host, self.port, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"Connection failed: {e}")

    def publish(self, topic, payload):
        try:
            self.client.publish(topic, json.dumps(payload))
            return True
        except Exception as e:
            print(f"Publish failed: {e}")
            return False

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
        # clean up extracted files
        if os.path.exists("MqttDelegateCert"):
            for file in os.listdir("MqttDelegateCert"):
                os.remove(os.path.join("MqttDelegateCert", file))
            os.rmdir("MqttDelegateCert")

    def send_message(self, message: bytes):
        """
        Send a message to the MQTT broker.
        :param message: The message to send.
        """
        topic = f"lingo/{self.account_id}/{self.thing_id}/MT"
        payload = {
            "message": base64.b64encode(message).decode('ascii'),
        }
        return self.publish(topic, payload)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MQTT Client with TLS support.")
    parser.add_argument("cert_zip", help="Path to the zip file containing CA, cert, and key files.")
    parser.add_argument("--host", default="mqtt.cloudloop.com", help="MQTT broker host.")
    parser.add_argument("--port", type=int, default=8883, help="MQTT broker port.")
    parser.add_argument("-account_id", help="Cloudloop Account ID.",  type=str, required=True)
    parser.add_argument("-thing_id", help="Cloudloop Thing ID for modem.", type=str, required=True)
    parser.add_argument("-out", default="udpin:127.0.0.1:16000", help="MAVLink connection to GCS")
    args = parser.parse_args()

    client = CloudloopMQTTClient(cert_zip=args.cert_zip, host=args.host,
                                 port=args.port, account_id=args.account_id, 
                                 thing_id=args.thing_id)
    client.connect()

    GCS_MAVLINK = mavutil.mavlink_connection(args.out)  # Sends packets vehicle -> GCS
    all_msgbuf = bytes()

    ALL_ALLOWABLE_MESSAGES = ALLOWABLE_MESSAGES + ["COMMAND_LONG", "COMMAND_INT"]

    try:
        while True:
            # Check for incoming messages from GCS
            msgGCS = GCS_MAVLINK.recv_match(type=ALL_ALLOWABLE_MESSAGES, blocking=False)
            if msgGCS:
                if msgGCS.get_type() in ALLOWABLE_MESSAGES and len(all_msgbuf) <= 50:
                    msgbuf = msgGCS.get_msgbuf()
                    all_msgbuf += msgbuf
                    print("Adding to send queue: " + str(msgGCS))
                    print("Message buffer length: {0}/50".format(len(all_msgbuf)))
                elif msgGCS.get_type() in ["COMMAND_LONG", "COMMAND_INT"] and msgGCS.command in ALLOWABLE_CMDS and len(all_msgbuf) <= 50:
                    msgbuf = msgGCS.get_msgbuf()
                    all_msgbuf += msgbuf
                    print("Adding to send queue: " + str(msgGCS))
                    print("Message buffer length: {0}/50".format(len(all_msgbuf)))

            # Send messages if buffer has data
            if len(all_msgbuf) > 0:
                if client.send_message(all_msgbuf):
                    print(f"Message sent, length {len(all_msgbuf)} bytes")
                else:
                    print("Failed to send message.")
                all_msgbuf = bytes()

            # Small sleep to prevent busy waiting
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Disconnecting...")
        client.disconnect()
