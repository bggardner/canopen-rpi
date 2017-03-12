#!/usr/bin/python3
import CAN
import CANopen

CAN_INTERFACE = "vcan0"

can_bus = CAN.Bus(CAN_INTERFACE)

node_id = 0x02

canopen_od = CANopen.ObjectDictionary({
    CANopen.ODI_DEVICE_TYPE: 0x00000000,
    CANopen.ODI_ERROR: 0x00,
    CANopen.ODI_HEARTBEAT_PRODUCER_TIME: 1000, # 16-bit, in ms
    CANopen.ODI_IDENTITY: CANopen.Object({
        CANopen.ODSI_VALUE: 4,
        CANopen.ODSI_IDENTITY_VENDOR: 0x00000000,
        CANopen.ODSI_IDENTITY_PRODUCT: 0x00000001,
        CANopen.ODSI_IDENTITY_REVISION: 0x00000000,
        CANopen.ODSI_IDENTITY_SERIAL: 0x00000001,
    }),
    CANopen.ODI_SDO_SERVER: CANopen.Object({
        CANopen.ODSI_VALUE: 2,
        CANopen.ODSI_SDO_SERVER_DEFAULT_CSID: (CANopen.FUNCTION_CODE_SDO_RX << CANopen.FUNCTION_CODE_BITNUM) + node_id,
        CANopen.ODSI_SDO_SERVER_DEFAULT_SCID: (CANopen.FUNCTION_CODE_SDO_TX << CANopen.FUNCTION_CODE_BITNUM) + node_id,
    }),
    CANopen.ODI_TPDO1_COMMUNICATION_PARAMETER: CANopen.Object({
        CANopen.ODSI_VALUE: 2,
        CANopen.ODSI_TPDO_COMM_PARAM_ID: node_id,
        CANopen.ODSI_TPDO_COMM_PARAM_TYPE: 1,
    }),
    CANopen.ODI_TPDO1_MAPPING_PARAMETER: CANopen.Object({
        CANopen.ODSI_VALUE: 2,
        0x01: (CANopen.ODI_SYNC << 16) + (CANopen.ODSI_VALUE << 8) + 32,
        0x02: (CANopen.ODI_SYNC_TIME << 16) + (CANopen.ODSI_VALUE << 8) + 32,
    }),
    CANopen.ODI_SYNC: 0x80,
    CANopen.ODI_SYNC_TIME: 0x00000000,
})

node = CANopen.Node(can_bus, node_id, canopen_od)
node.boot()
node.listen(True) # Listen forever (blocking)
