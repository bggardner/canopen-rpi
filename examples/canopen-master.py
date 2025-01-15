#!/usr/bin/env python3
import can
from functools import reduce
import logging
from operator import xor
import RPi.GPIO as GPIO
import signal
from time import sleep
from sys import exit

import socketcanopen

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

runled0 = socketcanopen.RunIndicator(PIN_RUNLED0)
errled0 = socketcanopen.ErrorIndicator(PIN_ERRLED0)
runled1 = socketcanopen.Indicator(PIN_RUNLED1, socketcanopen.Indicator.OFF)
errled1 = socketcanopen.Indicator(PIN_ERRLED1, socketcanopen.Indicator.ON)

default_bus = can.Bus(DEFAULT_CAN_INTERFACE, interface="socketcan")
redundant_bus = can.Bus(REDUNDANT_CAN_INTERFACE, interface="socketcan")
active_bus = default_bus


class ResetNode(Exception):
    pass


class ResetCommunication(Exception):
    pass


while True:
    try:
        if GPIO.input(PIN_ENABLE_N) == GPIO.HIGH:
            logger.warning("Enable_n is high")
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
                    logger.warning("Address parity mismatch")
                    sleep(1)
                    raise ResetCommunication

                node_id = 0
                for bit in address_n:
                    node_id = (node_id << 1) | (not bit)

                if node_id == socketcanopen.BROADCAST_NODE_ID:
                    logger.warning("Invalid Node ID")
                    sleep(1)
                    raise ResetCommunication

                canopen_od = socketcanopen.ObjectDictionary({
                    socketcanopen.ODI_DEVICE_TYPE: socketcanopen.Object(
                        parameter_name="Device type",
                        object_type=socketcanopen.ObjectType.VAR,
                        access_type=socketcanopen.AccessType.RO,
                        data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                        default_value=0x00000000
                    ),
                    socketcanopen.ODI_ERROR: socketcanopen.Object(
                        parameter_name="Error register",
                        object_type=socketcanopen.ObjectType.VAR,
                        access_type=socketcanopen.AccessType.RO,
                        data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED8,
                        default_value=0x00
                    ),
                    socketcanopen.ODI_SYNC: socketcanopen.Object(
                        parameter_name="COB-ID SYNC",
                        object_type=socketcanopen.ObjectType.VAR,
                        access_type=socketcanopen.AccessType.RW,
                        data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                        default_value=0x00000000 + (socketcanopen.FUNCTION_CODE_SYNC << socketcanopen.FUNCTION_CODE_BITNUM), # 0x40000000 + ... if SYNC producer
                    ),
                    socketcanopen.ODI_SYNC_TIME: socketcanopen.Object(
                        parameter_name="Communication cycle period",
                        object_type=socketcanopen.ObjectType.VAR,
                        access_type=socketcanopen.AccessType.RW,
                        data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                        default_value=1000000 # 1 second, 32-bit, in us
                    ),
                    socketcanopen.ODI_TIME_STAMP: socketcanopen.Object(
                        parameter_name="COB-ID time stamp object",
                        object_type=socketcanopen.ObjectType.VAR,
                        access_type=socketcanopen.AccessType.RW,
                        data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                        default_value=(socketcanopen.FUNCTION_CODE_TIME_STAMP << socketcanopen.FUNCTION_CODE_BITNUM) + node_id
                    ),
                    socketcanopen.ODI_EMCY_ID: socketcanopen.Object(
                        parameter_name="COB-ID emergency message",
                        object_type=socketcanopen.ObjectType.VAR,
                        access_type=socketcanopen.AccessType.CONST,
                        data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                        default_value=(socketcanopen.FUNCTION_CODE_EMCY << socketcanopen.FUNCTION_CODE_BITNUM) + node_id
                    ),
                    socketcanopen.ODI_HEARTBEAT_CONSUMER_TIME: socketcanopen.Object(
                        parameter_name="Consumer Heartbeat Time",
                        object_type=socketcanopen.ObjectType.ARRAY,
                        data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                        sub_number=1,
                        subs={
                            socketcanopen.ODSI_VALUE: socketcanopen.SubObject(
                                parameter_name="Number of Entries",
                                access_type=socketcanopen.AccessType.RO,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED8,
                                low_limit=1,
                                high_limit=127,
                                default_value=1,
                            ),
                            socketcanopen.ODSI_HEARTBEAT_CONSUMER_TIME: socketcanopen.SubObject(
                                parameter_name="Consumer Heartbeat Time",
                                access_type=socketcanopen.AccessType.RO,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=(1 << 16) + 2000 # Node-ID 1, 16-bit, in ms
                            ),
                        }
                    ),
                    socketcanopen.ODI_HEARTBEAT_PRODUCER_TIME: socketcanopen.Object(
                        parameter_name="Producer heartbeat time",
                        object_type=socketcanopen.ObjectType.VAR,
                        access_type=socketcanopen.AccessType.RW,
                        data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED16,
                        default_value=1000 # 16-bit, in ms
                    ),
                    socketcanopen.ODI_IDENTITY: socketcanopen.Object(
                        parameter_name="Identity Object",
                        object_type=socketcanopen.ObjectType.RECORD,
                        data_type=socketcanopen.ODI_DATA_TYPE_IDENTITY,
                        sub_number=4,
                        subs={
                            socketcanopen.ODSI_VALUE: socketcanopen.SubObject(
                                parameter_name="number of entries",
                                access_type=socketcanopen.AccessType.RO,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED8,
                                low_limit=1,
                                high_limit=4,
                                default_value=4
                            ),
                            socketcanopen.ODSI_IDENTITY_VENDOR: socketcanopen.SubObject(
                                parameter_name="Vendor ID",
                                access_type=socketcanopen.AccessType.RO,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=0x00000000
                            ),
                            socketcanopen.ODSI_IDENTITY_PRODUCT: socketcanopen.SubObject(
                                parameter_name="Product code",
                                access_type=socketcanopen.AccessType.RO,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=0x00000001
                            ),
                            socketcanopen.ODSI_IDENTITY_REVISION: socketcanopen.SubObject(
                                parameter_name="Revision number",
                                access_type=socketcanopen.AccessType.RO,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=0x00000000
                            ),
                            socketcanopen.ODSI_IDENTITY_SERIAL: socketcanopen.SubObject(
                                parameter_name="Serial number",
                                access_type=socketcanopen.AccessType.RO,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=0x00000001
                            )
                        }
                    ),
                    socketcanopen.ODI_NMT_INHIBIT_TIME: socketcanopen.Object(
                        parameter_name="NMT inhibit time",
                        object_type=socketcanopen.ObjectType.VAR,
                        access_type=socketcanopen.AccessType.RW,
                        data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED16,
                        default_value=0 # in ms
                    ),
                    socketcanopen.ODI_SDO_SERVER: socketcanopen.Object(
                        parameter_name="Server SDO parameter",
                        object_type=socketcanopen.ObjectType.RECORD,
                        data_type=socketcanopen.ODI_DATA_TYPE_SDO_PARAMETER,
                        sub_number=2,
                        subs={
                            socketcanopen.ODSI_VALUE: socketcanopen.SubObject(
                                parameter_name="number of entries",
                                access_type=socketcanopen.AccessType.RO,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED8,
                                low_limit=2,
                                high_limit=2,
                                default_value=2
                                ),
                            socketcanopen.ODSI_SDO_SERVER_DEFAULT_CSID: socketcanopen.SubObject(
                                parameter_name="COB-ID Client->Server (rx)",
                                access_type=socketcanopen.AccessType.RO,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=(socketcanopen.FUNCTION_CODE_SDO_RX << socketcanopen.FUNCTION_CODE_BITNUM) + node_id
                            ),
                            socketcanopen.ODSI_SDO_SERVER_DEFAULT_SCID: socketcanopen.SubObject(
                                parameter_name="COB-ID Server->Client (tx)",
                                access_type=socketcanopen.AccessType.RO,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=(socketcanopen.FUNCTION_CODE_SDO_TX << socketcanopen.FUNCTION_CODE_BITNUM) + node_id
                            ),
                        }
                    ), #TODO: add Client SDO parameter Object(s)
                    socketcanopen.ODI_TPDO1_COMMUNICATION_PARAMETER: socketcanopen.Object(
                        parameter_name="transmit PDO parameter",
                        object_type=socketcanopen.ObjectType.RECORD,
                        data_type=socketcanopen.ODI_DATA_TYPE_PDO_COMMUNICATION_PARAMETER,
                        sub_number=2,
                        subs={
                            socketcanopen.ODSI_VALUE: socketcanopen.SubObject(
                                parameter_name="largest sub-index supported",
                                access_type=socketcanopen.AccessType.RO,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED8,
                                low_limt=2,
                                high_limit=6,
                                default_value=2
                            ),
                            socketcanopen.ODSI_PDO_COMM_PARAM_ID: socketcanopen.SubObject(
                                parameter_name="COB-ID used by PDO",
                                access_type=socketcanopen.AccessType.RO,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=node_id
                            ),
                            socketcanopen.ODSI_PDO_COMM_PARAM_TYPE: socketcanopen.SubObject(
                                parameter_name="transmission type",
                                access_type=socketcanopen.AccessType.RO,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED8,
                                low_limit=0x00,
                                high_limit=0xFF,
                                default_value=1 # synchronous
                            )
                        }
                    ),
                    socketcanopen.ODI_TPDO1_MAPPING_PARAMETER: socketcanopen.Object(
                        parameter_name="transmit PDO mapping",
                        object_type=socketcanopen.ObjectType.RECORD,
                        data_type=socketcanopen.ODI_DATA_TYPE_PDO_MAPPING_PARAMETER,
                        sub_number=2,
                        subs={
                            socketcanopen.ODSI_VALUE: socketcanopen.SubObject(
                                parameter_name="number of mapped application objects in PDO",
                                access_type=socketcanopen.AccessType.RO,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED8,
                                low_limit=0x00,
                                high_limit=0x40,
                                default_value=2
                            ),
                            0x01: socketcanopen.SubObject(
                                parameter_name="PDO mapping for the 1st application object to be mapped",
                                access_type=socketcanopen.AccessType.RO,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=(socketcanopen.ODI_SYNC << 16) + (socketcanopen.ODSI_VALUE << 8) + 32
                            ),
                            0x02: socketcanopen.SubObject(
                                parameter_name="PDO mapping for the 2nd application object to be mapped",
                                access_type=socketcanopen.AccessType.RO,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=(socketcanopen.ODI_SYNC_TIME << 16) + (socketcanopen.ODSI_VALUE << 8) + 32
                            ),
                        }
                    ),
                    socketcanopen.ODI_NMT_STARTUP: socketcanopen.Object(
                        parameter_name="NMT Startup",
                        object_type=socketcanopen.ObjectType.VAR,
                        access_type=socketcanopen.AccessType.CONST,
                        data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                        default_value=0x00000023 # Flying master, NMT master start, NMT master
                    ),
                    socketcanopen.ODI_NMT_SLAVE_ASSIGNMENT: socketcanopen.Object(
                        parameter_name="NMT slave assignment",
                        object_type=socketcanopen.ObjectType.ARRAY,
                        data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                        sub_number=0x7F,
                        subs=dict(list({
                            socketcanopen.ODSI_VALUE: socketcanopen.SubObject(
                                parameter_name="Highest sub-index supported",
                                access_type=socketcanopen.AccessType.CONST,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED8,
                                low_limit=0x7F,
                                high_limit=0x7F,
                                default_value=0x7F
                            )
                            }.items()) + list({index: socketcanopen.SubObject(
                                parameter_name="Node-ID {}".format(index),
                                access_type=socketcanopen.AccessType.RO,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                                low_limit=0x00000000,
                                high_limit=0xFFFFFFFF,
                                default_value=0x00000000
                            ) for index in range(1, 0x80)}.items())
                        )
                    ),
                    socketcanopen.ODI_REQUEST_NMT: socketcanopen.Object(
                        parameter_name="NMT flying master timing parameters",
                        object_type=socketcanopen.ObjectType.ARRAY,
                        data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED8,
                        sub_number=0x80,
                        subs=dict(list({
                            socketcanopen.ODSI_VALUE: socketcanopen.SubObject(
                                parameter_name="Highest sub-index supported",
                                access_type=socketcanopen.AccessType.CONST,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED8,
                                low_limit=0x80,
                                high_limit=0x80,
                                default_value=0x80
                            )
                            }.items()) + list({index: socketcanopen.SubObject(
                                parameter_name="Node-ID {}".format(index),
                                access_type=socketcanopen.AccessType.RO,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED8,
                                low_limit=0x00,
                                high_limit=0xFF,
                                default_value=0x00
                            ) for index in range(1, 0x81)}.items())
                        )
                    ),
                    socketcanopen.ODI_BOOT_TIME: socketcanopen.Object(
                        parameter_name="Boot time",
                        object_type=socketcanopen.ObjectType.VAR,
                        access_type=socketcanopen.AccessType.RW,
                        data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                        default_value=0x00001388 # 5 sec
                    ),
                    socketcanopen.ODI_NMT_FLYING_MASTER_TIMING_PARAMETERS: socketcanopen.Object(
                        parameter_name="NMT flying master timing parameters",
                        object_type=socketcanopen.ObjectType.ARRAY,
                        data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED16,
                        sub_number=6,
                        subs={
                            socketcanopen.ODSI_VALUE: socketcanopen.SubObject(
                                parameter_name="Highest sub-index supported",
                                access_type=socketcanopen.AccessType.CONST,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED8,
                                low_limit=0x06,
                                high_limit=0x06,
                                default_value=0x06
                            ),
                            socketcanopen.ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_TIMEOUT: socketcanopen.SubObject(
                                parameter_name="NMT master timeout",
                                access_type=socketcanopen.AccessType.CONST,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED16,
                                low_limit=0x0000,
                                high_limit=0xFFFF,
                                default_value=100
                            ),
                            socketcanopen.ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_DELAY: socketcanopen.SubObject(
                                parameter_name="NMT master negotiation time delay",
                                access_type=socketcanopen.AccessType.CONST,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED16,
                                low_limit=0x0000,
                                high_limit=0xFFFF,
                                default_value=500
                            ),
                            socketcanopen.ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_PRIORITY: socketcanopen.SubObject(
                                parameter_name="NMT master priority",
                                access_type=socketcanopen.AccessType.CONST,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED16,
                                low_limit=0x0000,
                                high_limit=0xFFFF,
                                default_value=node_id % 3
                            ),
                            socketcanopen.ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_PRIORITY_TIME_SLOT: socketcanopen.SubObject(
                                parameter_name="Priority time slot",
                                access_type=socketcanopen.AccessType.CONST,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED16,
                                low_limit=0x0000,
                                high_limit=0xFFFF,
                                default_value=1500
                            ),
                            socketcanopen.ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_DEVICE_TIME_SLOT: socketcanopen.SubObject(
                                parameter_name="socketcanopen device time slot",
                                access_type=socketcanopen.AccessType.CONST,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED16,
                                low_limit=0x0000,
                                high_limit=0xFFFF,
                                default_value=10
                            ),
                            socketcanopen.ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_DETECT_TIME: socketcanopen.SubObject(
                                parameter_name="Multiple NMT master detect cycle time",
                                access_type=socketcanopen.AccessType.CONST,
                                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED16,
                                low_limit=0x0000,
                                high_limit=0xFFFF,
                                default_value=4000 + 10 * node_id
                            ),
                        }
                    ),
                })

                nmt_slave_assignments = canopen_od.get(socketcanopen.ODI_NMT_SLAVE_ASSIGNMENT)
                nmt_slave_assignment = nmt_slave_assignments.get(0x02)
                nmt_slave_assignment.value = 0x00000009 # Mandatory slave
                nmt_slave_assignments.update({0x02: nmt_slave_assignment})
                canopen_od.update({socketcanopen.ODI_NMT_SLAVE_ASSIGNMENT: nmt_slave_assignments})

                with socketcanopen.Node(active_bus, node_id, canopen_od, run_indicator=runled0, err_indicator=errled0) as node:
                    while node.nmt_state == socketcanopen.NMT_STATE_INITIALISATION:
                        sleep(1)
                    logger.info(bytes(node._sdo_upload_request(2, 0x1021, 0x00)).decode())
                    logger.info(bytes(node._sdo_block_upload_request(2, 0x1021, 0x00)).decode())
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
