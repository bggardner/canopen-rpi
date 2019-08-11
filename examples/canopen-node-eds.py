#!/usr/bin/python3
import logging
import os
import signal

import socketcan
import socketcanopen

logging.basicConfig(level=logging.DEBUG)

CAN_INTERFACE = "vcan0"

can_bus = socketcan.Bus(CAN_INTERFACE)

node_id = 0x02

canopen_od = socketcanopen.ObjectDictionary.from_eds(os.path.dirname(os.path.relpath(__file__)) + '/node.eds', node_id)

node = socketcanopen.Node(can_bus, node_id, canopen_od)

signal.pause() # Run forever
