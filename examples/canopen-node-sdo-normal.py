#!/usr/bin/python3
import can
from datetime import datetime, timedelta
import logging
import os
import signal

import socketcanopen

CAN_INTERFACE = "vcan0"

logging.basicConfig(level=logging.DEBUG)

can_bus = can.Bus(CAN_INTERFACE, bustype="socketcan")

node_id = 0x02

socketcanopen_od = socketcanopen.ObjectDictionary({
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
    socketcanopen.ODI_HEARTBEAT_PRODUCER_TIME: socketcanopen.Object(
        parameter_name="Producer heartbeat time",
        object_type=socketcanopen.ObjectType.VAR,
        access_type=socketcanopen.AccessType.RW,
        data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED16,
        default_value=1000 # 16-bit, in ms
    ),
    socketcanopen.ODI_IDENTITY: socketcanopen.Object(
        parameter_name="Identity object",
        object_type=socketcanopen.ObjectType.RECORD,
        data_type=socketcanopen.ODI_DATA_TYPE_IDENTITY,
        sub_number=1,
        subs={
            socketcanopen.ODSI_VALUE: socketcanopen.SubObject(
                parameter_name="number of supported entries",
                access_type=socketcanopen.AccessType.CONST,
                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED8,
                low_limit=0x01,
                high_limit=0x04,
                default_value=0x01
            ),
            socketcanopen.ODSI_IDENTITY_VENDOR: socketcanopen.SubObject(
                parameter_name="Vendor-ID",
                access_type=socketcanopen.AccessType.RO,
                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                low_limit=0x00000000,
                high_limit=0xFFFFFFFF,
                default_value=0x00000000
            )
        }
    ),
    0x1021: socketcanopen.Object(
        parameter_name="Store EDS",
        object_type=socketcanopen.ObjectType.VAR,
        access_type=socketcanopen.AccessType.RO,
        data_type=socketcanopen.ODI_DATA_TYPE_DOMAIN,
        default_value=bytes(open(os.path.dirname(os.path.abspath(__file__)) + "/node.eds", "r").read(), "ascii")
    ),
    0x1022: socketcanopen.Object(
        parameter_name="Store format",
        object_type=socketcanopen.ObjectType.VAR,
        access_type=socketcanopen.AccessType.RO,
        data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED8,
        default_value=0x00
    ),
    socketcanopen.ODI_SDO_SERVER: socketcanopen.Object(
        parameter_name="SDO server parameter",
        object_type=socketcanopen.ObjectType.RECORD,
        data_type=socketcanopen.ODI_DATA_TYPE_SDO_PARAMETER,
        sub_number=2,
        subs={
            socketcanopen.ODSI_VALUE: socketcanopen.SubObject(
                parameter_name="number of supported entires",
                access_type=socketcanopen.AccessType.CONST,
                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED8,
                low_limit=0x02,
                high_limit=0x02,
                default_value=0x02
            ),
            socketcanopen.ODSI_SDO_SERVER_DEFAULT_CSID: socketcanopen.SubObject(
                parameter_name="COB-ID client -> server (rx)",
                access_type=socketcanopen.AccessType.RO,
                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                default_value=(socketcanopen.FUNCTION_CODE_SDO_RX << socketcanopen.FUNCTION_CODE_BITNUM) + node_id
            ),
            socketcanopen.ODSI_SDO_SERVER_DEFAULT_SCID: socketcanopen.SubObject(
                parameter_name="COB-ID client -> server (rx)",
                access_type=socketcanopen.AccessType.RO,
                data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED32,
                default_value=(socketcanopen.FUNCTION_CODE_SDO_TX << socketcanopen.FUNCTION_CODE_BITNUM) + node_id
            )
        }
    ),
    0x2000: socketcanopen.Object(
        parameter_name="UNSIGNED64 RO test",
        object_type=socketcanopen.ObjectType.VAR,
        access_type=socketcanopen.AccessType.RO,
        data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED64,
        default_value=0x0123456780987654
    ),
    0x2001: socketcanopen.Object(
        parameter_name="UNSIGNED64 RW test",
        object_type=socketcanopen.ObjectType.VAR,
        access_type=socketcanopen.AccessType.RW,
        data_type=socketcanopen.ODI_DATA_TYPE_UNSIGNED64,
        default_value=0x4523018967452301
    ),
    0x2002: socketcanopen.Object(
        parameter_name="VISIBLE_STRING RO test",
        object_type=socketcanopen.ObjectType.VAR,
        access_type=socketcanopen.AccessType.RO,
        data_type=socketcanopen.ODI_DATA_TYPE_VISIBLE_STRING,
        default_value="Hello world (read only)"
    ),
    0x2003: socketcanopen.Object(
        parameter_name="VISIBLE_STRING RW test",
        object_type=socketcanopen.ObjectType.VAR,
        access_type=socketcanopen.AccessType.RW,
        data_type=socketcanopen.ODI_DATA_TYPE_VISIBLE_STRING,
        default_value="Hello world (read/write)"
    ),
    0x2004: socketcanopen.Object(
        parameter_name="UNICODE_STRING RO test",
        object_type=socketcanopen.ObjectType.VAR,
        access_type=socketcanopen.AccessType.RO,
        data_type=socketcanopen.ODI_DATA_TYPE_UNICODE_STRING,
        default_value="Hello world (read only)"
    ),
    0x2005: socketcanopen.Object(
        parameter_name="UNICODE_STRING RW test",
        object_type=socketcanopen.ObjectType.VAR,
        access_type=socketcanopen.AccessType.RW,
        data_type=socketcanopen.ODI_DATA_TYPE_UNICODE_STRING,
        default_value="Hello world (read/write)"
    ),
    0x2006: socketcanopen.Object(
        parameter_name="OCTET_STRING RO test",
        object_type=socketcanopen.ObjectType.VAR,
        access_type=socketcanopen.AccessType.RO,
        data_type=socketcanopen.ODI_DATA_TYPE_OCTET_STRING,
        default_value=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    ),
    0x2007: socketcanopen.Object(
        parameter_name="OCTET_STRING RW test",
        object_type=socketcanopen.ObjectType.VAR,
        access_type=socketcanopen.AccessType.RW,
        data_type=socketcanopen.ODI_DATA_TYPE_OCTET_STRING,
        default_value=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    ),
    0x2008: socketcanopen.Object(
        parameter_name="DOMAIN RO test",
        object_type=socketcanopen.ObjectType.VAR,
        access_type=socketcanopen.AccessType.RO,
        data_type=socketcanopen.ODI_DATA_TYPE_DOMAIN,
        default_value=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    ),
    0x2009: socketcanopen.Object(
        parameter_name="DOMAIN RW test",
        object_type=socketcanopen.ObjectType.VAR,
        access_type=socketcanopen.AccessType.RW,
        data_type=socketcanopen.ODI_DATA_TYPE_DOMAIN,
        default_value=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    ),
    0x200A: socketcanopen.Object(
        parameter_name="TIME_OF_DAY RO test",
        object_type=socketcanopen.ObjectType.VAR,
        access_type=socketcanopen.AccessType.RO,
        data_type=socketcanopen.ODI_DATA_TYPE_TIME_OF_DAY,
        default_value=datetime.today()
    ),
    0x200B: socketcanopen.Object(
        parameter_name="TIME_OF_DAY RW test",
        object_type=socketcanopen.ObjectType.VAR,
        access_type=socketcanopen.AccessType.RW,
        data_type=socketcanopen.ODI_DATA_TYPE_TIME_OF_DAY,
        default_value=datetime.today()
    ),
    0x200C: socketcanopen.Object(
        parameter_name="TIME_DIFFERENCE RO test",
        object_type=socketcanopen.ObjectType.VAR,
        access_type=socketcanopen.AccessType.RO,
        data_type=socketcanopen.ODI_DATA_TYPE_TIME_DIFFERENCE,
        default_value=timedelta(1, 2, 3, 4)
    ),
    0x200D: socketcanopen.Object(
        parameter_name="TIME_DIFFERENCE RW test",
        object_type=socketcanopen.ObjectType.VAR,
        access_type=socketcanopen.AccessType.RW,
        data_type=socketcanopen.ODI_DATA_TYPE_TIME_DIFFERENCE,
        default_value=timedelta(1, 2, 3, 4)
    ),
    0x200E: socketcanopen.Object(
        parameter_name="REAL64 RO test",
        object_type=socketcanopen.ObjectType.VAR,
        access_type=socketcanopen.AccessType.RO,
        data_type=socketcanopen.ODI_DATA_TYPE_REAL64,
        default_value=3.14159265359
    ),
    0x200F: socketcanopen.Object(
        parameter_name="REAL64 RW test",
        object_type=socketcanopen.ObjectType.VAR,
        access_type=socketcanopen.AccessType.RW,
        data_type=socketcanopen.ODI_DATA_TYPE_REAL64,
        default_value=3.14159265359
    )
})

node = socketcanopen.Node(can_bus, node_id, socketcanopen_od)

signal.pause() # Run forever
