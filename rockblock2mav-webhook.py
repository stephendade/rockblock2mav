#!/usr/bin/env python3
'''
A MAVLink gateway for the RockBlock SBD satellite modems.

It will allow limited communications between a MAVLink GCS and
SBD modem fitted to an ArduPilot vehicle.

Requires:
-RockBlock modem
-Active Rockblock account
-Public static IP for data reception (see https://docs.groundcontrol.com/iot/rockblock/web-services/receiving-mo-message)

The rockblock webhook should be set to HTTP_POST to http://<public IP>:<port>/rock

Written by Stephen Dade (stephen_dade@hotmail.com)

MAVProxy cmd to use to connect:
mavproxy.py --master=udpout:127.0.0.1:16000 --streamrate=1 --console --mav10 --map

'''
from argparse import ArgumentParser
from datetime import datetime, timedelta, timezone
import queue
import time
import requests
import threading
from urllib.parse import quote
from flask import Flask, request

import pymavlink.mavutil as mavutil
from pymavlink.dialects.v10 import ardupilotmega as mavlink1


ROCK7_URL = 'https://rockblock.rock7.com/rockblock/MT'

# https://docs.rockblock.rock7.com/reference/testinput
ROCK7_TX_ERRORS = {'10': 'Invalid login credentials',
                   '11': 'No RockBLOCK with this IMEI found on your account',
                   '12': 'RockBLOCK has no line rental',
                   '13': 'Your account has insufficient credit',
                   '14': 'Could not decode hex data',
                   '15': 'Data too long',
                   '16': 'No Data',
                   '99': 'System Error'}

# Note command_long and command_int are allowed, but only certain commands
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

UDP_MAX_PACKET_LEN = 65535

ROCKBLOCK_RX_PACKETS = queue.Queue()


def rockBlockFlaskThread(imei, ip, port):
    mavUAV = mavlink1.MAVLink(255, 0, use_native=False)
    app = Flask(__name__)

    @app.route('/rock', methods=['POST'])
    def process_mo_packet():
        # print post parameters
        print(request.form)

        try:
            # check if the packet is for this IMEI
            if request.form['imei'] != imei:
                print("Bad IMEI. Expected {0}, got {1}".format(imei, request.form['imei']))
                return "Bad IMEI", 200

            datetime_object = datetime.strptime(request.form['transmit_time'], '%y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            print("Got new packet, coords {0},{1}. Received at {2} UTC".format(request.form['iridium_latitude'],
                                                                               request.form['iridium_longitude'],
                                                                               datetime_object))
            # if the packet time is too old, don't process it
            if datetime_object < datetime.now(timezone.utc) - timedelta(minutes=5):
                print("Packet too old")
                return "Old packet", 200
            # Parse incoming bytes
            msgList = mavUAV.parse_buffer(bytes.fromhex(request.form['data']))
            if msgList:
                for msg in msgList:
                    print(msg)
                    ROCKBLOCK_RX_PACKETS.put(msg)
            return "OK", 200
        except Exception as e:
            print("Error processing packet: {0}".format(e))
            return "Error processing packet", 400

    app.run(host=ip, port=port)


if __name__ == '__main__':
    parser = ArgumentParser(description='RockBlock SBD to MAVLink gateway')
    parser.add_argument("-imei", help="Iridium Modem IMEI")
    parser.add_argument("-out", default="udpin:127.0.0.1:16000", help="MAVLink connection to GCS")
    parser.add_argument("-debug", default="udpin:127.0.0.1:17000", help="Debugging port to view messages sent from GCS to vehicle")
    parser.add_argument("-rock7username", help="Rock7 username")
    parser.add_argument("-rock7password", help="Rock7 password")
    parser.add_argument("-tcpinput", default="", help="Use this public static IP to receive webhook data")
    parser.add_argument("-mav20", action='store_true', default=False, help="Use MAVLink 2.0 on -out")

    args = parser.parse_args()

    # Start flask in a background thread for receiving RockBlock packets
    flask_thread = threading.Thread(target=rockBlockFlaskThread, args=(args.imei,
                                                                       args.tcpinput.split(":")[0],
                                                                       int(args.tcpinput.split(":")[1])))
    flask_thread.start()

    mavGCS = mavutil.mavlink_connection(args.out)  # Sends packets vehicle -> GCS
    mavUAV = mavutil.mavlink_connection(args.debug)   # Repacks packets GCS -> vehicle
    mavUAV.WIRE_PROTOCOL_VERSION = "1.0"
    if args.mav20:
        mavGCS.WIRE_PROTOCOL_VERSION = "2.0"
    else:
        mavGCS.WIRE_PROTOCOL_VERSION = "1.0"

    while True:

        # if there is a packet in the queue, process it
        try:
            Rockblock_msg = ROCKBLOCK_RX_PACKETS.get_nowait()
        except queue.Empty:
            print("No packets in queue")
            Rockblock_msg = None

        # send on to GCS (convert to mavlink2 if needed)
        if Rockblock_msg:
            print("Sending to GCS")
            mavGCS.mav.srcSystem = Rockblock_msg.get_srcSystem()
            mavGCS.mav.srcComponent = Rockblock_msg.get_srcComponent()
            mavGCS.mav.seq = Rockblock_msg.get_seq()
            if args.mav20:
                mavGCS.mav.send(Rockblock_msg, force_mavlink1=False)
            else:
                mavGCS.mav.send(Rockblock_msg, force_mavlink1=True)

        # get incoming bytes from GCS to send to vehicle
        do_check = True
        all_msgbuf = ''
        while do_check:
            print("Checking for GCS packets")
            msgGCS = mavGCS.recv_msg()
            # filter according to msg properties and send buffer to Rock7
            if msgGCS:
                # convert to mavlink1 if needed. Get buffer of hex bytes too
                msgbuf = None
                if args.mav20:
                    mavUAV.mav.srcSystem = msgGCS.get_srcSystem()
                    mavUAV.mav.srcComponent = msgGCS.get_srcComponent()
                    mavUAV.mav.seq = msgGCS.get_seq()
                    # repack in MAVLink1 format
                    msgbuf = msgGCS.pack(mavUAV.mav, force_mavlink1=True)
                else:
                    msgbuf = msgGCS.get_msgbuf()
                # Filter by acceptable messages and commands
                if msgGCS.get_type() in ['COMMAND_LONG', 'COMMAND_INT'] and int(msgGCS.command) in ALLOWABLE_CMDS and len(all_msgbuf) <= 50:
                    print("Adding to send queue: " + str(msgGCS))
                    all_msgbuf += "".join("%02x" % b for b in msgbuf)
                    print("Message buffer length: {0}/50".format(len(all_msgbuf)/2))
                elif msgGCS.get_type() in ALLOWABLE_MESSAGES and len(all_msgbuf) <= 50:
                    all_msgbuf += "".join("%02x" % b for b in msgbuf)
                    print("Adding to send queue: " + str(msgGCS))
                    print("Message buffer length: {0}/50".format(len(all_msgbuf)/2))
            else:
                # We've gotten all bytes from the GCS
                do_check = False
        # send bytes to Rockblock, if any
        if all_msgbuf:
            print(all_msgbuf)
            url = "{0}?imei={1}&username={2}&password={3}&data={4}&flush=yes".format(ROCK7_URL,
                                                                                     args.imei,
                                                                                     quote(args.rock7username),
                                                                                     quote(args.rock7password),
                                                                                     all_msgbuf)
            response = requests.post(url, headers={"Accept": "text/plain"})
            responseSplit = response.text.split(',')
            if len(all_msgbuf)/2 > 50:
                print("Warning, messages greater than 50 bytes")
            if responseSplit[0] != 'OK' and len(responseSplit) > 1:
                if responseSplit[1] in ROCK7_TX_ERRORS.keys():
                    print("Error sending command: " + ROCK7_TX_ERRORS[responseSplit[1]])
                else:
                    print("Unknown error: " + response)
            else:
                print("Sent {0} bytes OK".format(len(all_msgbuf)/2))
            all_msgbuf = ''
        print("Sleeping 2")
        time.sleep(2)
