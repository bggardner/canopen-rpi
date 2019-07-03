#!/usr/bin/python3
import CAN
import CANopen
from functools import reduce
from operator import xor
import RPi.GPIO as GPIO
import signal
from time import sleep
from sys import exit

DEFAULT_CAN_INTERFACE = "vcan0"
REDUNDANT_CAN_INTERFACE = "vcan1"

PIN_ENABLE_N = 16
PIN_ADDRESS_N = [12, 13, 14, 15, 17, 18, 19]
PIN_ADDRESS_PARITY_N = 20
PIN_RUNLED0 = 41
PIN_ERRLED0 = 40
PIN_RUNLED1 = 39
PIN_ERRLED1 = 38

def sigterm_handler(signum, frame):
    GPIO.cleanup()
    exit()

signal.signal(signal.SIGTERM, sigterm_handler)

GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN_ENABLE_N, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PIN_ADDRESS_N, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PIN_ADDRESS_PARITY_N, GPIO.IN, pull_up_down=GPIO.PUD_UP)

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

                if node_id == CANopen.BROADCAST_NODE_ID:
                    print("Invalid Node ID")
                    sleep(1)
                    raise ResetCommunication

                print("Booting with Node ID: {:d}".format(node_id))
                canopen_od = CANopen.ObjectDictionary({
                    CANopen.ODI_DEVICE_TYPE: CANopen.Object(
                        parameter_name="Device type",
                        object_type=CANopen.ObjectType.VAR,
                        access_type=CANopen.AccessType.RO,
                        data_type=CANopen.ODI_DATA_TYPE_UNSIGNED32,
                        default_value=0x00000000
                    ),
                    CANopen.ODI_ERROR: CANopen.Object(
                        parameter_name="Error register",
                        object_type=CANopen.ObjectType.VAR,
                        access_type=CANopen.AccessType.RO,
                        data_type=CANopen.ODI_DATA_TYPE_UNSIGNED8,
                        default_value=0x00
                    ),
                    CANopen.ODI_SYNC: CANopen.Object(
                        parameter_name="COB-ID SYNC",
                        object_type=CANopen.ObjectType.VAR,
                        access_type=CANopen.AccessType.CONST,
                        data_type=CANopen.ODI_DATA_TYPE_UNSIGNED32,
                        default_value=0x00000000 + (CANopen.FUNCTION_CODE_SYNC << CANopen.FUNCTION_CODE_BITNUM), # 0x40000000 + ... if SYNC producer
                    ),
                    CANopen.ODI_SYNC_TIME: CANopen.Object(
                        parameter_name="Communication cycle period",
                        object_type=CANopen.ObjectType.VAR,
                        access_type=CANopen.AccessType.RW,
                        data_type=CANopen.ODI_DATA_TYPE_UNSIGNED32,
                        default_value=1000000 # 1 second, 32-bit, in us
                    ),
                    CANopen.ODI_EMCY_ID: CANopen.Object(
                        parameter_name="COB-ID emergency message",
                        object_type=CANopen.ObjectType.VAR,
                        access_type=CANopen.AccessType.CONST,
                        data_type=CANopen.ODI_DATA_TYPE_UNSIGNED32,
                        default_value=(CANopen.FUNCTION_CODE_EMCY << CANopen.FUNCTION_CODE_BITNUM) + node_id
                    ),
                    CANopen.ODI_HEARTBEAT_CONSUMER_TIME: CANopen.Object(
                        parameter_name="Consumer Heartbeat Time",
                        object_type=CANopen.ObjectType.ARRAY,
                        data_type=CANopen.ODI_DATA_TYPE_UNSIGNED32,
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
                                default_value=(1 << 16) + 2000 # Node-ID 1, 16-bit, in ms
                            ),
                        }
                    ),
                    CANopen.ODI_HEARTBEAT_PRODUCER_TIME: CANopen.Object(
                        parameter_name="Producer heartbeat time",
                        object_type=CANopen.ObjectType.VAR,
                        access_type=CANopen.AccessType.RW,
                        data_type=CANopen.ODI_DATA_TYPE_UNSIGNED16,
                        default_value=1000 # 16-bit, in ms
                    ),
                    CANopen.ODI_IDENTITY: CANopen.Object(
                        parameter_name="Identity Object",
                        object_type=CANopen.ObjectType.RECORD,
                        data_type=CANopen.ODI_DATA_TYPE_IDENTITY,
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
                        data_type=CANopen.ODI_DATA_TYPE_SDO_PARAMETER,
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
                        data_type=CANopen.ODI_DATA_TYPE_PDO_COMMUNICATION_PARAMETER,
                        sub_number=2,
                        subs={
                            CANopen.ODSI_VALUE: CANopen.SubObject(
                                parameter_name="largest sub-index supported",
                                access_type=CANopen.AccessType.RO,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED8,
                                low_limt=2,
                                high_limit=6,
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
                        data_type=CANopen.ODI_DATA_TYPE_PDO_MAPPING_PARAMETER,
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
                    CANopen.ODI_NMT_STARTUP: CANopen.Object(
                        parameter_name="NMT Startup",
                        object_type=CANopen.ObjectType.VAR,
                        access_type=CANopen.AccessType.CONST,
                        data_type=CANopen.ODI_DATA_TYPE_UNSIGNED32,
                        default_value=0x00000023 # Flying master, NMT master start, NMT master
                    ),
                    CANopen.ODI_NMT_FLYING_MASTER_TIMING_PARAMETERS: CANopen.Object(
                        parameter_name="NMT flying master timing parameters",
                        object_type=CANopen.ObjectType.ARRAY,
                        data_type=CANopen.ODI_DATA_TYPE_UNSIGNED16,
                        sub_number=6,
                        subs={
                            CANopen.ODSI_VALUE: CANopen.SubObject(
                                parameter_name="Highest sub-index supported",
                                access_type=CANopen.AccessType.CONST,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED8,
                                low_limit=0x06,
                                high_limit=0x06,
                                default_value=0x06
                            ),
                            CANopen.ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_TIMEOUT: CANopen.SubObject(
                                parameter_name="NMT master timeout",
                                access_type=CANopen.AccessType.CONST,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED16,
                                low_limit=0x0000,
                                high_limit=0xFFFF,
                                default_value=100
                            ),
                            CANopen.ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_DELAY: CANopen.SubObject(
                                parameter_name="NMT master negotiation time delay",
                                access_type=CANopen.AccessType.CONST,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED16,
                                low_limit=0x0000,
                                high_limit=0xFFFF,
                                default_value=500
                            ),
                            CANopen.ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_PRIORITY: CANopen.SubObject(
                                parameter_name="NMT master priority",
                                access_type=CANopen.AccessType.CONST,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED16,
                                low_limit=0x0000,
                                high_limit=0xFFFF,
                                default_value=(node_id - 1) & 0x3
                            ),
                            CANopen.ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_PRIORITY_TIME_SLOT: CANopen.SubObject(
                                parameter_name="Priority time slot",
                                access_type=CANopen.AccessType.CONST,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED16,
                                low_limit=0x0000,
                                high_limit=0xFFFF,
                                default_value=1500
                            ),
                            CANopen.ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_DEVICE_TIME_SLOT: CANopen.SubObject(
                                parameter_name="CANopen device time slot",
                                access_type=CANopen.AccessType.CONST,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED16,
                                low_limit=0x0000,
                                high_limit=0xFFFF,
                                default_value=10
                            ),
                            CANopen.ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_DETECT_TIME: CANopen.SubObject(
                                parameter_name="Multiple NMT master detect cycle time",
                                access_type=CANopen.AccessType.CONST,
                                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED16,
                                low_limit=0x0000,
                                high_limit=0xFFFF,
                                default_value=4000 + 10 * node_id
                            ),
                        }
                    ),
                })

                with CANopen.Node(active_bus, node_id, canopen_od, run_indicator=runled0, err_indicator=errled0) as node:
                    while True:
                        signal.pause() # Replace with application code and interact with Object Dictionary (node.od)

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
