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
mavproxy.py --master=udpout:127.0.0.1:16000 --streamrate=1 --console

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

from Adafruit_IO import Client
from pymavlink.dialects.v20 import ardupilotmega as mavlink2

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
                   
# Only send these MAVLink commands, to save bandwidth
ALLOWABLE_CMDS = [16, #MAV_CMD_NAV_WAYPOINT
                 20, #MAV_CMD_NAV_RETURN_TO_LAUNCH
                 21, #MAV_CMD_NAV_LAND
                 22, #MAV_CMD_NAV_TAKEOFF
                 84, #MAV_CMD_NAV_VTOL_TAKEOFF
                 85, #MAV_CMD_NAV_VTOL_LAND
                 176, #MAV_CMD_DO_SET_MODE
                 185, #MAV_CMD_DO_FLIGHTTERMINATION
                 246, #MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN
                 300, #MAV_CMD_MISSION_START
                 400, #MAV_CMD_COMPONENT_ARM_DISARM
                 2600, #MAV_CMD_CONTROL_HIGH_LATENCY
                 ]

UDP_MAX_PACKET_LEN = 65535

if __name__ == '__main__':
    parser = ArgumentParser(description='RockBlock SBD to MAVLink gateway')
    parser.add_argument("-adafruitusername", help="Adafruit.io username")
    parser.add_argument("-adafruitfeed", help="Adafruit.io feed name")
    parser.add_argument("-adafruitkey", help="Adafruit.io key")
    parser.add_argument("-imei", help="Iridium Modem IMEI")
    parser.add_argument("-out", default="127.0.0.1:16000", help="MAVLink UDPIn IP:Port to output packets to")
    parser.add_argument("-rock7username", help="Rock7 username")
    parser.add_argument("-rock7password", help="Rock7 password")

    args = parser.parse_args()
    
    aio = Client(args.adafruitusername, args.adafruitkey)
    lastpacket = None
    
    mavUAV = mavlink2.MAVLink(255, 0, use_native=False)
    mavGCS = mavlink2.MAVLink(255, 0, use_native=False)
    
    out_ip = args.out.split(':')[0]
    out_port = int(args.out.split(':')[1])
    
    clientIPPort = None
    
    UDPClientSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
    UDPClientSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    UDPClientSocket.bind((out_ip, out_port))
    UDPClientSocket.settimeout(1.0)
    UDPClientSocket.setblocking(0)
    
    # When was the last command sent? Need to avoid spamming
    lastSendCmd = time.time()
    
    while True:
        # get the raw data from AdafruitIO
        try:
            raw_feed = aio.feeds(args.adafruitfeed)
        except:
            print("Error accessing Adafruit.io feed. Check the username, feed name and key are correct")
            sys.exit(0)
        
        raw_data = aio.receive(raw_feed.key).value
        data = json.loads(raw_data)
        datetime_object = datetime.strptime(data['transmit_time'] + " UTC", '%y-%m-%d %H:%M:%S %Z')
        print("Checking for new packet at {0}".format(datetime.utcnow().strftime("%Y-%m-%d, %H:%M:%S")))
        
        #print(data)
        
        # Only accept if packet less than 60 seconds old and we've not already seen it
        if datetime.utcnow()-datetime_object < timedelta(minutes=10) and lastpacket != data:
            # Start parsing the data
            print("Got new packet, coords {0},{1}. Received at {2} UTC".format(data['iridium_latitude'],
                                                                               data['iridium_longitude'],
                                                                               datetime_object))
            lastpacket = data
            
            #re-add missing parts of message that we had to trim (mavlink header and compat flag)
            fullpkt = "fd" + data['data'][0:2] + "00" + data['data'][2:]
            print(fullpkt)
            
            # Parse incoming bytes - debugging
            msgList = mavUAV.parse_buffer(bytes.fromhex(fullpkt))
            if msgList:
                for msg in msgList:
                    print(msg)
                   
            # send on to GCS (raw bytes)
            if clientIPPort:
                UDPClientSocket.sendto(bytes.fromhex(fullpkt), clientIPPort)
            
        # get incoming bytes from GCS
        data = None
        addr = None
        do_check = True
        while do_check:
            print("Checking for GCS packets")
            try:
                data, addr = UDPClientSocket.recvfrom(UDP_MAX_PACKET_LEN)
            except socket.error as e:
                if e.errno in [ errno.EAGAIN, errno.EWOULDBLOCK, errno.ECONNREFUSED ]:
                    do_check = False
                else:
                    raise
            if data:
                clientIPPort = addr
                try:
                    msgList = mavGCS.parse_buffer(data)
                except mavlink2.MAVError:
                    pass
                if msgList:
                    for msg in msgList:
                        #print(msg)
                        if msg.get_type() in ['COMMAND_LONG', 'COMMAND_INT'] and (time.time() - lastSendCmd) > 20 and int(msg.command) in ALLOWABLE_CMDS:
                            # Only want to send CMD_LONG and CMD_INT messages once per 20sec, to save bandwidth
                            url = "{0}?imei={1}&username={2}&password={3}&data={4}&flush=yes".format(ROCK7_URL,
                                                                                           args.imei,
                                                                                           quote(args.rock7username),
                                                                                           quote(args.rock7password),
                                                                                           "".join("%02x" % b for b in msg.get_msgbuf()))
                            print("Sending: " + str(msg))
                            response = requests.post(url, headers={"Accept": "text/plain"})
                            responseSplit = response.text.split(',')
                            if responseSplit[0] != 'OK':
                                if responseSplit[1] in ROCK7_TX_ERRORS.keys():
                                    print("Error sending command: " + ROCK7_TX_ERRORS[responseSplit[1]])
                                else:
                                    print("Unknown error: " + response)
                            else:
                                if len(msg.get_msgbuf()) > 50:
                                    print("Warning, message greater than 50 bytes")
                                print("Sent {0} bytes OK".format(len(msg.get_msgbuf())))
                            lastSendCmd = time.time()
                        elif msg.get_type() in ['COMMAND_LONG', 'COMMAND_INT'] and int(msg.command) in ALLOWABLE_CMDS:
                            print("Too soon to send command: " + str(msg.command))
            else:
                # We've gotten all bytes from the GCS
                do_check = False
        print("Sleeping 2")
        time.sleep(2)
