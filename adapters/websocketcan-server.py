#!/usr/bin/env python3
import asyncio
import can
import websockets
import websockets.speedups

# Server constants
CAN_INTERFACE = "vcan0"
WEBSOCKET_SERVER_IP_ADDRESS = "" # Empty string for any address
WEBSOCKET_SERVER_PORT = 8003

def ws_to_can(msg: bytes) -> can.message:
    # Convert from bytes to can.Message: from can.interfaces.socketcan.socketcan.capture_message()
    can_id, can_dlc, flags, data = can.interfaces.socketcan.socketcan.dissect_can_frame(msg)
    is_extended_frame_format = bool(can_id & can.interfaces.socketcan.constants.CAN_EFF_FLAG)
    is_remote_transmission_request = bool(can_id & can.interfaces.socketcan.constants.CAN_RTR_FLAG)
    is_error_frame = bool(can_id & can.interfaces.socketcan.constants.CAN_ERR_FLAG)
    is_fd = len(msg) == can.interfaces.socketcan.constants.CANFD_MTU
    bitrate_switch = bool(flags & can.interfaces.socketcan.constants.CANFD_BRS)
    error_state_indicator = bool(flags & can.interfaces.socketcan.constants.CANFD_ESI)
    msg = can.Message(
        arbitration_id=can_id,
        is_extended_id=is_extended_frame_format,
        is_remote_frame=is_remote_transmission_request,
        is_error_frame=is_error_frame,
        is_fd=is_fd,
        bitrate_switch=bitrate_switch,
        error_state_indicator=error_state_indicator,
        dlc=can_dlc,
        data=data
    )
    return msg

async def websocket_consumer_handler(websocket, path):
    try:
        async for msg in websocket:
            msg = ws_to_can(msg)
            try:
                can_bus.send(msg)
            except Exception as e:
                break
    except websockets.exceptions.ConnectionClosed:
        pass

async def websocket_producer_handler(websocket, path):
    socketcan_producer = can.AsyncBufferedReader()
    notifier.add_listener(socketcan_producer)
    while True:
        msg = await socketcan_producer.get_message()
        msg = can.interfaces.socketcan.socketcan.build_can_frame(msg) # Convert from can.Message to bytes
        try:
            await websocket.send(msg)
        except websockets.exceptions.ConnectionClosed:
            break
    notifier.remove_listener(socketcan_producer)

async def websocket_handler(websocket, path):
    consumer_task = asyncio.ensure_future(websocket_consumer_handler(websocket, path))
    producer_task = asyncio.ensure_future(websocket_producer_handler(websocket, path))
    done, pending = await asyncio.wait([consumer_task, producer_task], return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()

can_bus = can.ThreadSafeBus(CAN_INTERFACE, interface="socketcan")
notifier = can.Notifier(can_bus, [], loop=asyncio.get_event_loop())
websocket_server = websockets.serve(websocket_handler, WEBSOCKET_SERVER_IP_ADDRESS, WEBSOCKET_SERVER_PORT, compression=None)
asyncio.get_event_loop().run_until_complete(websocket_server)
asyncio.get_event_loop().run_forever()
