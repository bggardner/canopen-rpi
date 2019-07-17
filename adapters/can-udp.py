#!/usr/bin/python3
from datetime import datetime
from select import select
import signal
import socket
import sys
from time import sleep

import socketcan

CAN_LISTEN_INTERFACES = ["vcan0", "vcan1"] # Must be a list
CAN_SEND_INTERFACE = "vcan0"
UDP_LISTEN_IP = "127.0.0.1"
UDP_LISTEN_PORT = 5005
UDP_SEND_IP = "127.0.0.1"
UDP_SEND_PORT = 5006

def sigterm_handler(signum, frame):
    sys.exit()

signal.signal(signal.SIGTERM, sigterm_handler)

sockets = []
for interface in CAN_LISTEN_INTERFACES:
    can_socket = socketcan.Bus(interface)
    sockets.append(can_socket)
for s in sockets:
    if s.getsockname()[0] == CAN_SEND_INTERFACE:
      can_socket = s
udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_socket.bind((UDP_LISTEN_IP, UDP_LISTEN_PORT))
sockets.append(udp_socket)

while True:
    try:
        rlist, _, _ = select(sockets, [], [])
        for s in rlist:
            socket_type = s.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)
            if isinstance(s, socketcan.Bus):
                msg = s.recv()
                for b in bytes(msg):
                    print(hex(b))
                print("-")
                udp_socket.sendto(bytes(msg), (UDP_SEND_IP, UDP_SEND_PORT))
            if socket_type == socket.SOCK_DGRAM:
                msg = s.recv(socketcan.Message.SIZE)
                can_socket.send(socketcan.Message.from_bytes(msg))
    except socketcan.BusDown:
        sleep(1)

