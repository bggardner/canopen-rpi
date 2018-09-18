#!/usr/bin/python3
import CAN
import CANopen

CAN_INTERFACE = "vcan0"

can_bus = CAN.Bus(CAN_INTERFACE)

node_id = 0x02

canopen_od = CANopen.ObjectDictionary.from_eds('node.eds')

node = CANopen.Node(can_bus, node_id, canopen_od)

while True:
    pass # Run forever
