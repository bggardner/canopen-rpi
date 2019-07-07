#!/usr/bin/python3

import signal

import CAN
import CANopen

CAN_INTERFACE = "vcan0"

can_bus = CAN.Bus(CAN_INTERFACE)

node_id = 0x02

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
    CANopen.ODI_HEARTBEAT_PRODUCER_TIME: CANopen.Object(
        parameter_name="Producer heartbeat time",
        object_type=CANopen.ObjectType.VAR,
        access_type=CANopen.AccessType.RW,
        data_type=CANopen.ODI_DATA_TYPE_UNSIGNED16,
        default_value=1000 # 16-bit, in ms
    ),
    CANopen.ODI_IDENTITY: CANopen.Object(
        parameter_name="Identity object",
        object_type=CANopen.ObjectType.RECORD,
        data_type=CANopen.ODI_DATA_TYPE_IDENTITY,
        sub_number=1,
        subs={
            CANopen.ODSI_VALUE: CANopen.SubObject(
                parameter_name="number of supported entries",
                access_type=CANopen.AccessType.CONST,
                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED8,
                low_limit=0x01,
                high_limit=0x04,
                default_value=0x01
            ),
            CANopen.ODSI_IDENTITY_VENDOR: CANopen.SubObject(
                parameter_name="Vendor-ID",
                access_type=CANopen.AccessType.RO,
                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED32,
                low_limit=0x00000000,
                high_limit=0xFFFFFFFF,
                default_value=0x00000000
            )
        }
    ),
    CANopen.ODI_SDO_SERVER: CANopen.Object(
        parameter_name="SDO server parameter",
        object_type=CANopen.ObjectType.RECORD,
        data_type=CANopen.ODI_DATA_TYPE_SDO_PARAMETER,
        sub_number=2,
        subs={
            CANopen.ODSI_VALUE: CANopen.SubObject(
                parameter_name="number of supported entires",
                access_type=CANopen.AccessType.CONST,
                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED8,
                low_limit=0x02,
                high_limit=0x02,
                default_value=0x02
            ),
            CANopen.ODSI_SDO_SERVER_DEFAULT_CSID: CANopen.SubObject(
                parameter_name="COB-ID client -> server (rx)",
                access_type=CANopen.AccessType.RO,
                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED32,
                default_value=(CANopen.FUNCTION_CODE_SDO_RX << CANopen.FUNCTION_CODE_BITNUM) + node_id
            ),
            CANopen.ODSI_SDO_SERVER_DEFAULT_SCID: CANopen.SubObject(
                parameter_name="COB-ID client -> server (rx)",
                access_type=CANopen.AccessType.RO,
                data_type=CANopen.ODI_DATA_TYPE_UNSIGNED32,
                default_value=(CANopen.FUNCTION_CODE_SDO_TX << CANopen.FUNCTION_CODE_BITNUM) + node_id
            )
        }
    )
})

node = CANopen.Node(can_bus, node_id, canopen_od)

signal.pause() # Run forever
