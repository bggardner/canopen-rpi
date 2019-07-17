#!/usr/bin/python3
import signal

import socketcan
import socketcanopen

CAN_INTERFACE = "vcan0"

can_bus = socketcan.Bus(CAN_INTERFACE)

node_id = 0x02

canopen_od = socketcanopen.ObjectDictionary.from_eds('node.eds')

node = socketcanopen.Node(can_bus, node_id, canopen_od)

signal.pause() # Run forever
