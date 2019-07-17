#!/usr/bin/python3
from http.server import HTTPServer
from select import select
import signal
from socketserver import ThreadingMixIn
import sys

import socketcan
from websocket import WebSocket, HTTPRequestHandler


# Server constants
DEFAULT_CAN_INTERFACE = "vcan0"
HTTP_SERVER_IP_ADDRESS = "" # Empty string for any address
HTTP_SERVER_PORT = 8003


def sigterm_handler(signum, frame):
    sys.exit()


class WebSocketCanHandler(HTTPRequestHandler):

    def listen(self):
        bus = socketcan.Bus(DEFAULT_CAN_INTERFACE)
        while True:
            rlist, _, _ = select([self.websocket, bus], [], [])
            for s in rlist:
                if isinstance(s, socketcan.Bus):
                    msg = s.recv()
                    self.send(bytes(msg))
                elif isinstance(s, WebSocket):
                    msg = s.recv()
                    if msg is None:
                        return
                    bus.send(socketcan.Message.from_bytes(msg))


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    pass


signal.signal(signal.SIGTERM, sigterm_handler)
server = ThreadedHTTPServer((HTTP_SERVER_IP_ADDRESS, HTTP_SERVER_PORT), WebSocketCanHandler)
server.serve_forever()
