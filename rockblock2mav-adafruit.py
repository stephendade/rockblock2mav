#!/usr/bin/env python3
'''
A MAVLink gateway for the RockBlock SBD satellite modems.

It will allow limited communications between a MAVLink GCS and
SBD modem fitted to an ArduPilot vehicle.

Requires:
-RockBlock modem
-Active Rockblock account
-Adafruit.io account for data reception (see https://learn.adafruit.com/using-the-rockblock-iridium-modem/forwarding-messages)

Written by Stephen Dade (stephen_dade@hotmail.com)

MAVProxy cmd to use to connect:
mavproxy.py --master=udpout:127.0.0.1:16000 --streamrate=1 --console --mav10 --map

'''
from argparse import ArgumentParser
from datetime import datetime, timedelta
import json
import socket
import sys
import time
import requests
import errno
from urllib.parse import quote

from Adafruit_IO import Client, errors
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

if __name__ == '__main__':
    parser = ArgumentParser(description='RockBlock SBD to MAVLink gateway')
    parser.add_argument("-adafruitusername", help="Adafruit.io username")
    parser.add_argument("-adafruitfeed", help="Adafruit.io feed name")
    parser.add_argument("-adafruitkey", help="Adafruit.io key")
    parser.add_argument("-imei", help="Iridium Modem IMEI")
    parser.add_argument("-out", default="udpin:127.0.0.1:16000", help="MAVLink udpin:IP:Port or udpout:IP:Port to output packets to")
    parser.add_argument("-rock7username", help="Rock7 username")
    parser.add_argument("-rock7password", help="Rock7 password")

    args = parser.parse_args()

    aio = Client(args.adafruitusername, args.adafruitkey)
    lastpacket = None

    mavUAV = mavlink1.MAVLink(255, 0, use_native=False)
    mavGCS = mavlink1.MAVLink(255, 0, use_native=False)

    udp_dir = args.out.split(':')[0]
    out_ip = args.out.split(':')[1]
    out_port = int(args.out.split(':')[2])

    clientIPPort = None

    UDPClientSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
    UDPClientSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if udp_dir == 'udpin':
        UDPClientSocket.bind((out_ip, out_port))
    UDPClientSocket.settimeout(1.0)
    UDPClientSocket.setblocking(0)

    while True:
        raw_data = None
        # get the raw data from AdafruitIO
        try:
            raw_feed = aio.feeds(args.adafruitfeed)
        except:
            print("Error accessing Adafruit.io feed. Check the username, feed name and key are correct")
            sys.exit(0)

        print("Checking for new packet at {0}".format(datetime.utcnow().strftime("%Y-%m-%d, %H:%M:%S")))

        try:
            raw_data = aio.receive(raw_feed.key).value
        except errors.RequestError:
            print("No data in feed")
            continue

        data = json.loads(raw_data)
        datetime_object = datetime.strptime(data['transmit_time'] + " UTC", '%y-%m-%d %H:%M:%S %Z')


        # print(data)

        # Only accept if packet less than 60 seconds old and we've not already seen it
        if datetime.utcnow()-datetime_object < timedelta(minutes=10) and lastpacket != data:
            # Start parsing the data
            print("Got new packet, coords {0},{1}. Received at {2} UTC".format(data['iridium_latitude'],
                                                                               data['iridium_longitude'],
                                                                               datetime_object))
            lastpacket = data

            # Parse incoming bytes - debugging
            msgList = mavUAV.parse_buffer(bytes.fromhex(data['data']))
            if msgList:
                for msg in msgList:
                    print(msg)

            # send on to GCS (raw bytes)
            if clientIPPort and udp_dir == 'udpin':
                UDPClientSocket.sendto(bytes.fromhex(data['data']), clientIPPort)
            elif udp_dir == 'udpout':
                UDPClientSocket.sendto(bytes.fromhex(data['data']), (out_ip, out_port))
        elif lastpacket != data:
            print("Adafruit.io packet too old. Packet time = {0}, Current time = {1}".format(datetime_object, datetime.utcnow()))

        # get incoming bytes from GCS
        data = None
        addr = None
        do_check = True
        while do_check:
            print("Checking for GCS packets")
            try:
                data, addr = UDPClientSocket.recvfrom(UDP_MAX_PACKET_LEN)
            except socket.error as e:
                if e.errno in [errno.EAGAIN, errno.EWOULDBLOCK, errno.ECONNREFUSED]:
                    do_check = False
                else:
                    raise
            if data:
                clientIPPort = addr
                try:
                    msgList = mavGCS.parse_buffer(data)
                except mavlink1.MAVError:
                    pass
                if msgList:
                    # queue up the messages (up to 50 bytes. Note format is 00 for each byte, so doubled) for sending 
                    # to the RockBlock
                    all_msgbuf = ''
                    for msg in msgList:
                        # Filter by acceptable messages and commands
                        if msg.get_type() in ['COMMAND_LONG', 'COMMAND_INT'] and int(msg.command) in ALLOWABLE_CMDS and len(all_msgbuf) <= 50:
                            print("Adding to send queue: " + str(msg))
                            all_msgbuf += "".join("%02x" % b for b in msg.get_msgbuf())
                            print("Message buffer length: {0}/50".format(len(all_msgbuf)/2))
                        elif msg.get_type() in ALLOWABLE_MESSAGES and len(all_msgbuf) <= 50:
                            all_msgbuf += "".join("%02x" % b for b in msg.get_msgbuf())
                            print("Adding to send queue: " + str(msg))
                            print("Message buffer length: {0}/50".format(len(all_msgbuf)/2))
                        elif len(all_msgbuf) > 50:
                            print("Message buffer full, not adding {0}".format(msg.get_type()))
                    if all_msgbuf:
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
                            print("Sent {0} bytes OK".format(len(msg.get_msgbuf())))
            else:
                # We've gotten all bytes from the GCS
                do_check = False
        print("Sleeping 2")
        time.sleep(2)
