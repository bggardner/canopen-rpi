import errno
try:
    from fcntl import ioctl
except:
    import time
import re
import socket
import struct
from subprocess import CalledProcessError, check_output

class Message:

    FORMAT = "=IB3x8s"
    SIZE = struct.calcsize(FORMAT)

    ERR_BITNUM = 29
    RTR_BITNUM = 30
    IDE_BITNUM = 31

    ID_TYPE_STANDARD = False
    ID_TYPE_EXTENDED = True

    def __init__(self, arbitration_id, data=[], *args, **kwargs):

        if 'dlc' in kwargs:
            self.dlc = kwargs['dlc']
        else:
            self.dlc = len(data)

        if 'id_type' in kwargs:
            self.id_type = kwargs['id_type']
        else:
            self.id_type = bool((1 << self.IDE_BITNUM) & arbitration_id)

        if 'is_remote_frame' in kwargs:
            self.is_remote_frame = kwargs['is_remote_frame']
        else:
            self.is_remote_frame = bool((1 << self.RTR_BITNUM) & arbitration_id)

        if 'is_error_frame' in kwargs:
            self.is_error_frame = kwargs['is_error_frame']
        else:
            self.is_error_frame = bool((1 << self.ERR_BITNUM) & arbitration_id)

        if 'timestamp' in kwargs:
            self.timestamp = kwargs['timestamp']
        else:
            self.timestamp = None

        self.arbitration_id = arbitration_id & 0x1FFFFFFF
        self.data = bytearray(data[:8])

    def __bytes__(self):
        arbitration_id = self.arbitration_id
        if self.id_type:
            arbitration_id |= 1 << self.IDE_BITNUM
        if self.is_remote_frame:
            arbitration_id |= 1 << self.RTR_BITNUM
        if self.is_error_frame:
            arbitration_id |= 1 << self.ERR_BITNUM
        data = self.data.ljust(8, b'\x00')
        return struct.pack(self.FORMAT, arbitration_id, self.dlc, self.data)

    def from_bytes(b):
        arbitration_id, dlc, data = struct.unpack(Message.FORMAT, b)
        return Message(arbitration_id, data[:dlc])


class Bus(socket.socket):

    STATE_UNKNOWN = "UKNOWN"
    STATE_ERROR_ACTIVE = "ERROR-ACTIVE"
    STATE_ERROR_PASSIVE = "ERROR-PASSIVE"
    STATE_BUS_OFF = "BUS-OFF"

    def __init__(self, interface, name=None):
        if name is None:
            name = interface
        self.name = name
        super().__init__(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        self.bind((interface,)) # Throws OSError if interface doesn't exist

    def get_state(self):
        addr = self.getsockname() # Data type check required because of https://bugs.python.org/issue37405
        if isinstance(addr, tuple):
            interface, *_ = self.getsockname()
        else:
            interface = self.getsockname()
        try:
            details = check_output(["ip", "-d", "link", "show", interface])
        except CalledProcessError: # ip returned non-zero
            return self.STATE_UNKNOWN
        m = re.search('state ([^\s]+) restart-ms', str(details))
        if m == None: # Not a valid can interface (could be vcan)
            return self.STATE_UNKNOWN
        return m.group(1)

    def recv(self):
        try:
            data = super().recv(Message.SIZE)
        except OSError as e:
            if e.errno == errno.ENETDOWN:
                raise BusDown
            raise
        try:
            res = ioctl(self, 0x8906, struct.pack("@LL", 0, 0))
            seconds, microseconds = struct.unpack("@LL", res)
            timestamp = seconds + microseconds / 1000000
        except:
            timestamp = time.time()
        msg = Message.from_bytes(data)
        msg.timestamp = timestamp
        return msg

    def send(self, msg: Message):
        try:
            return super().send(bytes(msg))
        except OSError as e:
            if e.errno == errno.ENETDOWN:
                raise BusDown
            raise

    def sendall(self, msg: Message):
        return super().sendall(bytes(msg))


class BusDown(Exception):
    pass
