#!/usr/bin/python3
import CAN
import CANopen
from functools import reduce
from operator import xor
import RPi.GPIO as GPIO
import signal
from time import sleep
from sys import exit

DEFAULT_CAN_INTERFACE = "can0"
REDUNDANT_CAN_INTERFACE = "can1"

PIN_ENABLE_N = 42
PIN_ADDRESS_N = list(range(34, 41))
PIN_ADDRESS_PARITY_N = 41
PIN_RUNLED0 = 2
PIN_ERRLED0 = 3
PIN_RUNLED1 = 4
PIN_ERRLED1 = 5

def sigterm_handler(signum, frame):
    GPIO.cleanup()
    exit()

signal.signal(signal.SIGTERM, sigterm_handler)

GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN_ENABLE_N, GPIO.IN)
GPIO.setup(PIN_ADDRESS_N, GPIO.IN)
GPIO.setup(PIN_ADDRESS_PARITY_N, GPIO.IN)

runled0 = CANopen.RunIndicator(PIN_RUNLED0)
errled0 = CANopen.ErrorIndicator(PIN_ERRLED0)
runled1 = CANopen.Indicator(PIN_RUNLED1, CANopen.Indicator.OFF)
errled1 = CANopen.Indicator(PIN_ERRLED1, CANopen.Indicator.ON)

default_bus = CAN.Bus(DEFAULT_CAN_INTERFACE)
redundant_bus = CAN.Bus(REDUNDANT_CAN_INTERFACE)
active_bus = default_bus

class ResetNode(Exception):
    pass

class ResetCommunication(Exception):
    pass

while True:
    try:
        if GPIO.input(PIN_ENABLE_N) == GPIO.HIGH:
            print("Enable_n is high")
            sleep(1)
            raise ResetNode
        while True:
            try:
                address_n = [
                    GPIO.input(PIN_ADDRESS_N[6]),
                    GPIO.input(PIN_ADDRESS_N[5]),
                    GPIO.input(PIN_ADDRESS_N[4]),
                    GPIO.input(PIN_ADDRESS_N[3]),
                    GPIO.input(PIN_ADDRESS_N[2]),
                    GPIO.input(PIN_ADDRESS_N[1]),
                    GPIO.input(PIN_ADDRESS_N[0])]
                address_parity_n = reduce(xor, address_n)
                if address_parity_n != GPIO.input(PIN_ADDRESS_PARITY_N):
                    print("Address parity mismatch")
                    sleep(1)
                    raise ResetCommunication

                node_id = 0
                for bit in address_n:
                    node_id = (node_id << 1) | (not bit)

                canopen_od = CANopen.ObjectDictionary({ # TODO: Include data types so there is a way to determine the length of values for SDO responses (currently always 4 bytes)
                    CANopen.ODI_DEVICE_TYPE: 0x00000000,
                    CANopen.ODI_ERROR: 0x00,
                    CANopen.ODI_SYNC: 0x40000000 + (CANopen.FUNCTION_CODE_SYNC << CANopen.FUNCTION_CODE_BITNUM),
                    CANopen.ODI_SYNC_TIME: 0, # 32-bit, in us
                    CANopen.ODI_EMCY_ID: (CANopen.FUNCTION_CODE_EMCY << CANopen.FUNCTION_CODE_BITNUM) + node_id,
                    CANopen.ODI_HEARTBEAT_CONSUMER_TIME: CANopen.Object(
                        parameter_name="Consumer Heartbeat Time",
                        object_type=CANopen.ObjectType.ARRAY,
                        sub_number=1,
                        subs={
                            CANopen.ODSI_VALUE: CANopen.SubObject(
                                parameter_name="Number of Entries",
                                access_type=CANopen.AccessType.RO,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED8,
                                low_limit=1,
                                high_limit=127,
                                default_value=1,
                            ),
                            CANopen.ODSI_HEARTBEAT_CONSUMER_TIME: CANopen.SubObject(
                                parameter_name="Consumer Heartbeat Time",
                                access_type=CANopen.AccessType.RO,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=2000 # all nodes, 16-bit, in ms
                            ),
                        }
                    ),
                    CANopen.ODI_HEARTBEAT_PRODUCER_TIME: 1000, # 16-bit, in ms
                    CANopen.ODI_IDENTITY: CANopen.Object(
                        parameter_name="Identity Object",
                        object_type=CANopen.ObjectType.ARRAY,
                        sub_number=4,
                        subs={
                            CANopen.ODSI_VALUE: CANopen.SubObject(
                                parameter_name="number of entries",
                                access_type=CANopen.AccessType.RO,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED8,
                                low_limit=1,
                                high_limit=4,
                                default_value=4
                            ),
                            CANopen.ODSI_IDENTITY_VENDOR: CANopen.SubObject(
                                parameter_name="Vendor ID",
                                access_type=CANopen.AccessType.RO,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=0x00000000
                            ),
                            CANopen.ODSI_IDENTITY_PRODUCT: CANopen.SubObject(
                                parameter_name="Product code",
                                access_type=CANopen.AccessType.RO,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=0x00000001
                            ),
                            CANopen.ODSI_IDENTITY_REVISION: CANopen.SubObject(
                                parameter_name="Revision number",
                                access_type=CANopen.AccessType.RO,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=0x00000000
                            ),
                            CANopen.ODSI_IDENTITY_SERIAL: CANopen.SubObject(
                                parameter_name="Serial number",
                                access_type=CANopen.AccessType.RO,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=0x00000001
                            )
                        }
                    ),
                    CANopen.ODI_SDO_SERVER: CANopen.Object(
                        parameter_name="Server SDO parameter",
                        object_type=CANopen.ObjectType.RECORD,
                        sub_number=2,
                        subs={
                            CANopen.ODSI_VALUE: CANopen.SubObject(
                                parameter_name="number of entries",
                                access_type=CANopen.AccessType.RO,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED8,
                                low_limit=2,
                                high_limit=2,
                                default_value=2
                                ),
                            CANopen.ODSI_SDO_SERVER_DEFAULT_CSID: CANopen.SubObject(
                                parameter_name="COB-ID Client->Server (rx)",
                                access_type=CANopen.AccessType.RO,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=(CANopen.FUNCTION_CODE_SDO_RX << CANopen.FUNCTION_CODE_BITNUM) + node_id
                            ),
                            CANopen.ODSI_SDO_SERVER_DEFAULT_SCID: CANopen.SubObject(
                                parameter_name="COB-ID Server->Client (tx)",
                                access_type=CANopen.AccessType.RO,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=(CANopen.FUNCTION_CODE_SDO_TX << CANopen.FUNCTION_CODE_BITNUM) + node_id
                            ),
                        }
                    ), #TODO: add Client SDO parameter Object(s)
                    CANopen.ODI_TPDO1_COMMUNICATION_PARAMETER: CANopen.Object(
                        parameter_name="transmit PDO parameter",
                        object_type=CANopen.ObjectType.RECORD,
                        sub_number=2,
                        subs={
                            CANopen.ODSI_VALUE: CANopen.SubObject(
                                parameter_name="largest sub-index supported",
                                access_type=CANopen.AccessType.RO,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED8,
                                low_limt=2,
                                high_limit=5,
                                default_value=2
                            ),
                            CANopen.ODSI_TPDO_COMM_PARAM_ID: CANopen.SubObject(
                                parameter_name="COB-ID used by PDO",
                                access_type=CANopen.AccessType.RO,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=node_id
                            ),
                            CANopen.ODSI_TPDO_COMM_PARAM_TYPE: CANopen.SubObject(
                                parameter_name="transmission type",
                                access_type=CANopen.AccessType.RO,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED8,
                                low_limit=0x00,
                                high_limit=0xFF,
                                default_value=1 # synchronous
                            )
                        }
                    ),
                    CANopen.ODI_TPDO1_MAPPING_PARAMETER: CANopen.Object(
                        parameter_name="transmit PDO mapping",
                        object_type=CANopen.ObjectType.RECORD,
                        sub_number=2,
                        subs={
                            CANopen.ODSI_VALUE: CANopen.SubObject(
                                parameter_name="number of mapped application objects in PDO",
                                access_type=CANopen.AccessType.RO,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED8,
                                low_limit=0x00,
                                high_limit=0x40,
                                default_value=2
                            ),
                            0x01: CANopen.SubObject(
                                parameter_name="PDO mapping for the 1st application object to be mapped",
                                access_type=CANopen.AccessType.RO,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=(CANopen.ODI_SYNC << 16) + (CANopen.ODSI_VALUE << 8) + 32
                            ),
                            0x02: CANopen.SubObject(
                                parameter_name="PDO mapping for the 2nd application object to be mapped",
                                access_type=CANopen.AccessType.RO,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=(CANopen.ODI_SYNC_TIME << 16) + (CANopen.ODSI_VALUE << 8) + 32
                            ),
                        }
                    ),
                })

                try:
                    node.boot()
                except NameError:
                    node = CANopen.Node(active_bus, node_id, canopen_od, run_indicator=runled0, err_indicator=errled0)
                    node.boot()

                try:
                    node.listen()
                    while True:
                        sync_time_object = node.od.get(CANopen.ODI_SYNC_TIME);
                        sync_time_object.update({CANopen.ODSI_VALUE: sync_time_object.get(CANopen.ODSI_VALUE) + 1})
                        node.od.update({CANopen.ODI_SYNC_TIME: sync_time_object})
                        sleep(1)
                except CAN.BusDown:
                    sleep(1)
                    continue
            except ResetCommunication:
                try:
                    node.reset_communication()
                except NameError:
                    pass
    except ResetNode:
        try:
            node.reset()
        except NameError:
            pass
