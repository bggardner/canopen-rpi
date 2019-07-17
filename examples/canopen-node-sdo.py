#!/usr/bin/python3

import signal

import socketcan
import socketcanopen

CAN_INTERFACE = "vcan0"

can_bus = socketcan.Bus(CAN_INTERFACE)

node_id = 0x02

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
    )
})

node = socketcanopen.Node(can_bus, node_id, canopen_od)

signal.pause() # Run forever
