from base64 import b64encode
from enum import Enum
from hashlib import sha1
from http.server import BaseHTTPRequestHandler
from random import randrange
from select import select
import struct


GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class Frame: # Called a Frame since a "message" is comprised of (or fragmented into) Frames

    class Opcode(Enum):
        CONTINUATION     = 0x0
        TEXT             = 0x1
        BINARY           = 0x2
        CONNECTION_CLOSE = 0x8
        PING             = 0x9
        PONG             = 0xA

    class CloseCode(Enum):
        NORMAL_CLOSURE             = 1000
        GOING_AWAY                 = 1001
        PROTOCOL_ERROR             = 1002
        UNSUPPORTED_DATA           = 1003
        NO_STATUS_RCVD             = 1005
        ABNORMAL_CLOSURE           = 1006
        INVALID_FRAME_PAYLOAD_DATA = 1007
        POLICY_VIOLATION           = 1008
        MESSAGE_TOO_BIG            = 1009
        MANDATORY_EXT              = 1010
        INTERNAL_SERVER_ERROR      = 1011
        TLS_HANDSHAKE              = 1015

    def __init__(self, final: bool, opcode: "Frame.Opcode", masked: bool, payload=[], **kwargs):
        self.final = final
        if "rsv1" in kwargs:
            self.rsv1 = kwargs["rsv1"]
        else:
            self.rsv1 = False
        if "rsv2" in kwargs:
            self.rsv2 = kwargs["rsv2"]
        else:
            self.rsv2 = False
        if "rsv3" in kwargs:
            self.rsv3 = kwargs["rsv3"]
        else:
            self.rsv3 = False
        self.opcode = opcode
        self.masked = masked
        self.payload = payload

    def __bytes__(self):
        header = int(self.final) << 15
        header += int(self.rsv1) << 14
        header += int(self.rsv2) << 13
        header += int(self.rsv3) << 12
        header += self.opcode.value << 8
        header += int(self.masked) << 7
        payload_len = len(self.payload)
        if payload_len > 0xFFFFFFFFFFFFFFFF:
            raise ValueError("Payload is too long, use fragmentation")
        elif payload_len > 0xFFFF:
            payload_len = 127
        elif payload_len > 125:
            payload_len = 126
        header += payload_len
        b = struct.pack(">H", header)
        if payload_len == 126:
            b += struct.pack(">H", len(self.payload))
        elif payload_len == 127:
            b += struct.pack(">Q", len(self.payload))
        if self.masked:
            b += struct.pack(">I", randrange(0xFFFFFFFF)) # Masking key
        b += bytes(self.payload)
        return b

    @classmethod
    def from_bytes(cls, b) -> "Frame":
        dummy_frame = cls.from_header_bytes(b[0:2])
        offset = 2
        if dummy_frame.masked:
            masking_key = b[offset:offset+4]
            offset += 4
        payload_len = len(dummy_frame.payload)
        if payload_len > 0xFFFF:
            payload_len = struct.unpack(">Q", b[offset:offset + 8])
            offset += 8
        elif payload_len > 125:
            payload_len = struct.unpack(">H", b[offset:offset + 2])
            offset += 2
        payload = b[offset:offset + payload_len]
        if dummy_frame.masked:
            unmasked_payload = bytes()
            for c in payload:
                unmasked_payload += bytes([c ^ masking_key[len(unmasked_payload) % 4]])
            payload = unmasked_payload
        dummy_frame.payload = payload
        return dummy_frame

    @classmethod
    def from_header_bytes(cls, b) -> "Frame": # Only returns valid header and dummy payload with the proper size
        final = bool(b[0] & 0x80)
        rsv1 = bool(b[0] & 0x40)
        rsv2 = bool(b[0] & 0x20)
        rsv3 = bool(b[0] & 0x10)
        opcode = cls.Opcode(b[0] & 0xF)
        masked = bool(b[1] & 0x80)
        payload_len = b[1] & 0x7F
        dummy_payload = [0] * payload_len
        return cls(final, opcode, masked, dummy_payload, rsv1=rsv1, rsv2=rsv2, rsv3=rsv3)


class WebSocket:
    def __init__(self, rfile, wfile, is_server=False):
        self.rfile = rfile
        self.wfile = wfile
        self.is_server = is_server
        self.is_closing = False
        self.message_buffer = None
        self.message_opcode = None

    def fileno(self):
        return self.rfile.fileno()

    def close(self, code=None):
        if code != None:
            code = struct.pack(">H", code.value)
        else:
            code = []
        self.is_closing = True
        self.send_frame(Frame(True, Frame.Opcode.CONNECTION_CLOSE, not self.is_server, code))

    def detach(self):
        self.rfile = None
        self.wfile = None

    def ping(self):
        self.send_frame(Frame(True, Frame.Opcode.PING, not self.is_server))

    def pong(self):
        self.send_frame(Frame(True, Frame.Opcode.PONG, not self.is_server))

    def recv(self):
        while True:
            try:
                frame = self.recv_frame()
            except: # Investigae exceptions
                self.detach()
                return
            if frame.masked != self.is_server:
                self.close(Frame.CloseCode.PROTOCOL_ERROR)
            if frame.final:
                if frame.opcode == Frame.Opcode.CONTINUATION:
                    if self.message_opcode == None:
                        self.close(Frame.CloseCode.PROTOCOL_ERROR) # Did not receive initial frame
                    elif self.message_opcode == Frame.Opcode.TEXT:
                        self.message_buffer += frame.payload
                        try:
                            return self.message_buffer.decode("utf-8")
                        except:
                            self.message_buffer = None
                            self.message_type = None
                            self.close(Frame.CloseCode.INVALID_FRAME_PAYLOAD_DATA)
                    elif self.message_opcode == Frame.Opcode.BINARY:
                        self.message_buffer += frame.payload
                        return self.message_buffer
                    else:
                        raise NotImplementedError # Continuation of other Frame.Opcode
                elif frame.opcode == Frame.Opcode.TEXT:
                    try:
                        return frame.payload.decode("utf-8")
                    except:
                        self.close(Frame.CloseCode.INVALID_FRAME_PAYLOAD_DATA)
                elif frame.opcode == Frame.Opcode.BINARY:
                    return frame.payload
                elif frame.opcode == Frame.Opcode.CONNECTION_CLOSE:
                    if self.is_closing:
                        self.detach()
                        return
                    self.close()
                elif frame.opcode == Frame.Opcode.PING:
                    self.pong()
                elif frame.opcode == Frame.Opcode.PONG:
                    pass
                else:
                    self.close(Frame.CloseCode.PROTOCOL_ERROR)
            else:
                if frame.opcode == Frame.Opcode.CONTINUATION:
                    if self.message_opcode == None:
                        self.close(Frame.CloseCode.PROTOCOL_ERROR) # Did not receive initial frame
                    elif self.message_opcode == Frame.Opcode.TEXT:
                        self.message_buffer += frame.payload
                    elif self.message_opcode == Frame.Opcode.BINARY:
                        self.message_buffer += frame.payload
                    else:
                        raise NotImplementedError # Continuation of other Frame.Opcode
                elif frame.opcode == Frame.Opcode.TEXT:
                    self.message_opcode = Frame.Opcode.TEXT
                    self.message_buffer += frame.payload
                elif frame.opcode == Frame.Opcode.BINARY:
                    self.message_opcode = Frame.Opcode.TEXT
                    self.message_buffer += frame.payload
                else:
                    raise NotImplementedError # Start of other Frame.Opcode

    def recv_frame(self) -> Frame:
        header = self.rfile.read(2)
        dummy_frame = Frame.from_header_bytes(header)
        read_length = 0
        if dummy_frame.masked:
            read_length += 4
        payload_len = len(dummy_frame.payload)
        if payload_len > 0xFFFF:
            read_length += 8
        elif payload_len > 125:
            read_length += 2
        read_length += payload_len
        body = self.rfile.read(read_length)
        return Frame.from_bytes(header + body)

    def send(self, data):
        if isinstance(data, str):
            frame = Frame(True, Frame.Opcode.TEXT, not self.is_server, data.encode("utf-8"))
        elif isinstance(data, bytes):
            frame = Frame(True, Frame.Opcode.BINARY, not self.is_server, data)
        else:
            raise NotImplementedError
        self.send_frame(frame)

    def send_frame(self, frame: Frame):
        self.wfile.write(bytes(frame))


class HTTPRequestHandler(BaseHTTPRequestHandler):
    class BadRequest(Exception):
        pass

    def do_GET(self):
        try:
            self.opening_handshake()
        except HTTPRequestHandler.BadRequest:
            return

        self.onopen()
        self.listen()
        self.onclose()

    def listen(self):
        while True:
            message = self.websocket.recv()
            if message is None:
                return
            else:
                self.onmessage(message)

    def onclose(self):
        pass # To be overridden

    def onmessage(self, data):
        pass # To be overridden

    def onopen(self):
        pass # To be overridden

    def opening_handshake(self):
        try:
            if self.request_version != "HTTP/1.1":
                raise HTTPRequestHandler.BadRequest
            self.protocol_version = "HTTP/1.1"
            if self.headers.get("Connection") != "Upgrade":
                raise HTTPRequestHandler.BadRequest
            if self.headers.get("Upgrade") != "websocket":
                raise HTTPRequestHandler.BadRequest
            if self.headers.get("Sec-WebSocket-Version") != "13":
                raise HTTPRequestHandler.BadRequest
            key = self.headers.get("Sec-WebSocket-Key")
            if key == None:
                raise HTTPRequestHandler.BadRequest
        except HTTPRequestHandler.BadRequest:
            self.send_response(400)
            raise

        accept = b64encode(sha1((key + GUID).encode()).digest()).decode()
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()

        self.websocket = WebSocket(self.rfile, self.wfile, True)

    def send(self, data):
        self.websocket.send(data)
