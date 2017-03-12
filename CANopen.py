#TODO: OSErrors are thrown if the CAN bus goes down, need to do threaded Exception handling
#      See http://stackoverflow.com/questions/2829329/catch-a-threads-exception-in-the-caller-thread-in-python
#TODO: Check for BUS-OFF before attempting to send

import CAN
from collections import Mapping, MutableMapping
from select import select
from threading import Event, Thread, Timer
from time import sleep

BROADCAST_NODE_ID = 0

# Function codes
FUNCTION_CODE_BITNUM = 7
FUNCTION_CODE_NMT = 0x0
FUNCTION_CODE_SYNC = 0x1
FUNCTION_CODE_EMCY = 0x1
FUNCTION_CODE_TIME_STAMP = 0x2
FUNCTION_CODE_TPDO1 = 0x3
FUNCTION_CODE_RPDO1 = 0x4
FUNCTION_CODE_TPDO2 = 0x5
FUNCTION_CODE_RPDO2 = 0x6
FUNCTION_CODE_TPDO3 = 0x7
FUNCTION_CODE_RPDO3 = 0x8
FUNCTION_CODE_TPDO4 = 0x9
FUNCTION_CODE_RPDO4 = 0xA
FUNCTION_CODE_SDO_TX = 0xB
FUNCTION_CODE_SDO_RX = 0xC
FUNCTION_CODE_NMT_ERROR_CONTROL = 0xE

# NMT commands
NMT_NODE_CONTROL = 0
NMT_NODE_CONTROL_START = 1
NMT_NODE_CONTROL_STOP = 2
NMT_NODE_CONTROL_PREOPERATIONAL = 128
NMT_NODE_CONTROL_RESET_NODE = 129
NMT_NODE_CONTROL_RESET_COMMUNICATION = 130
NMT_GFC = 1

# NMT states
NMT_STATE_INITIALISATION = 0
NMT_STATE_STOPPED = 4
NMT_STATE_OPERATIONAL = 5
NMT_STATE_PREOPERATIONAL = 127

# Emergency error codes
EMCY_RESET = 0x0000
EMCY_NONE = 0x0000
EMCY_GENERIC = 0x1000
EMCY_HEARTBEAT_BY_NODE = 0x8F00

# Object dictionary structure
OD_STRUCTURE_OBJECT_TYPE_BITNUM = 0
OD_STRUCTURE_DATA_TYPE_BITNUM = 8

# Object dictionary object type
OD_OBJECT_TYPE_NULL = 0
OD_OBJECT_TYPE_DOMAIN = 2
OD_OBJECT_TYPE_DEFTYPE = 5
OD_OBJECT_TYPE_DEFSTRUCT = 6
OD_OBJECT_TYPE_VAR = 7
OD_OBJECT_TYPE_ARRAY = 8
OD_OBJECT_TYPE_RECORD = 9

# Object dictionary indices and sub-indices
ODSI_VALUE = 0x00
ODSI_STRUCTURE = 0xFF
ODI_DATA_TYPE_BOOLEAN = 0x0001
ODI_DATA_TYPE_INTEGER8 = 0x0002
ODI_DATA_TYPE_INTEGER16 = 0x0003
ODI_DATA_TYPE_INTEGER32 = 0x0004
ODI_DATA_TYPE_UNSIGNED8 = 0x0005
ODI_DATA_TYPE_UNSIGNED16 = 0x0006
ODI_DATA_TYPE_UNSIGNED32 = 0x0007
ODI_DATA_TYPE_REAL32 = 0x0008
ODI_DATA_TYPE_VISIBLE_STRING = 0x0009
ODI_DATA_TYPE_OCTET_STRING = 0x000A
ODI_DATA_TYPE_UNICODE_STRING = 0x000B
ODI_DATA_TYPE_TIME_OF_DAY = 0x000C
ODI_DATA_TYPE_TIME_DIFFERENT = 0x000D
ODI_DATA_TYPE_DOMAIN = 0x000E
ODI_DATA_TYPE_INTEGER24 = 0x0010
ODI_DATA_TYPE_REAL64 = 0x0011
ODI_DATA_TYPE_INTEGER40 = 0x0012
ODI_DATA_TYPE_INTEGER48 = 0x0013
ODI_DATA_TYPE_INTEGER56 = 0x0014
ODI_DATA_TYPE_INTEGER64 = 0x0015
ODI_DATA_TYPE_UNSIGNED24 = 0x0016
ODI_DATA_TYPE_UNSIGNED40 = 0x0018
ODI_DATA_TYPE_UNSIGNED48 = 0x0019
ODI_DATA_TYPE_UNSIGNED56 = 0x001A
ODI_DATA_TYPE_UNSIGNED64 = 0x001B
ODI_DATA_TYPE_PDO_COMMUNICATION_PARAMETER = 0x0020
ODSI_DATA_TYPE_PDO_COMM_PARAM_ID = 0x01
ODSI_DATA_TYPE_PDO_COMM_PARAM_TYPE = 0x02
ODSI_DATA_TYPE_PDO_COMM_PARAM_INHIBIT_TIME = 0x03
ODSI_DATA_TYPE_PDO_COMM_PARAM_EVENT_TIMER = 0x05
ODSI_DATA_TYPE_PDO_COMM_PARAM_SYNC_START = 0x06
ODI_DATA_TYPE_PDO_MAPPING_PARAMETER = 0x002100
ODI_DATA_TYPE_SDO_PARAMETER = 0x002200
ODSI_DATA_TYPE_SDO_PARAM_CSID = 0x01
ODSI_DATA_TYPE_SDO_PARAM_SCID = 0x02
ODSI_DATA_TYPE_SDO_PARAM_NODE_ID = 0x03
ODI_DATA_TYPE_IDENTITY = 0x0023
ODSI_DATA_TYPE_IDENTITY_VENDOR = 0x01
ODSI_DATA_TYPE_IDENTITY_PRODUCT = 0x02
ODSI_DATA_TYPE_IDENTITY_REVISION = 0x03
ODSI_DATA_TYPE_IDENTITY_SERIAL = 0x04
ODI_DEVICE_TYPE = 0x1000
ODI_ERROR = 0x1001
ODI_SYNC = 0x1005
ODI_SYNC_TIME = 0x1006
ODI_EMCY_ID = 0x1014
ODI_HEARTBEAT_CONSUMER_TIME = 0x1016
ODSI_HEARTBEAT_CONSUMER_TIME = 0x01
ODI_HEARTBEAT_PRODUCER_TIME = 0x1017
ODI_IDENTITY = 0x1018
ODSI_IDENTITY_VENDOR = 0x01
ODSI_IDENTITY_PRODUCT = 0x02
ODSI_IDENTITY_REVISION = 0x03
ODSI_IDENTITY_SERIAL = 0x04
ODI_SDO_SERVER = 0x1200
ODSI_SDO_SERVER_DEFAULT_CSID = 0x01
ODSI_SDO_SERVER_DEFAULT_SCID = 0x02
ODI_SDO_CLIENT = 0x1280
ODSI_SDO_CLIENT_TX = 0x01
ODSI_SDO_CLIENT_RX = 0x02
ODSI_SDO_CLIENT_NODE_ID = 0x03
ODI_TPDO1_COMMUNICATION_PARAMETER = 0x1800
ODSI_TPDO_COMM_PARAM_ID = 0x01
ODSI_TPDO_COMM_PARAM_TYPE = 0x02
ODI_TPDO1_MAPPING_PARAMETER = 0x1A00

# SDO
SDO_N_BITNUM = 3
SDO_N_LENGTH = 2
SDO_E_BITNUM = 1
SDO_S_BITNUM = 0
SDO_CCS_BITNUM = 5
SDO_CCS_LENGTH = 3
SDO_CCS_DOWNLOAD = 1
SDO_CCS_UPLOAD = 2
SDO_SCS_BITNUM = 5
SDO_SCS_LENGTH = 3
SDO_SCS_DOWNLOAD = 3
SDO_SCS_UPLOAD = 2
SDO_CS_ABORT = 4
SDO_ABORT_INVALID_CS = 0x05040001
SDO_ABORT_OBJECT_DNE = 0x06020000
SDO_ABORT_SUBINDEX_DNE = 0x06090011
SDO_ABORT_GENERAL = 0x08000000

# PDO
TPDO_COMM_PARAM_ID_VALID_BITNUM = 31
TPDO_COMM_PARAM_ID_RTR_BITNUM = 30

class ObjectDictionary(MutableMapping):
    def __init__(self, other=None, **kwargs):
        self._store = { # Defaults
            ODI_DATA_TYPE_BOOLEAN: Object({
                ODSI_VALUE: 0x00000001,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_INTEGER8: Object({
                ODSI_VALUE: 0x00000008,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_INTEGER16: Object({
                ODSI_VALUE: 0x00000010,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_INTEGER32: Object({
                ODSI_VALUE: 0x00000020,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_UNSIGNED8: Object({
                ODSI_VALUE: 0x00000008,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_UNSIGNED16: Object({
                ODSI_VALUE: 0x00000010,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_UNSIGNED32: Object({
                ODSI_VALUE: 0x00000020,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_REAL32: Object({
                ODSI_VALUE: 0x00000020,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_VISIBLE_STRING: Object({
                ODSI_VALUE: 0x00000000, # Implementation-specific
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_OCTET_STRING: Object({
                ODSI_VALUE: 0x00000000, # Implementation-specific
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_UNICODE_STRING: Object({
                ODSI_VALUE: 0x00000000, # Implementation-specific
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_TIME_OF_DAY: Object({
                ODSI_VALUE: 0x00000030,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_DOMAIN: Object({
                ODSI_VALUE: 0x00000000,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_INTEGER24: Object({
                ODSI_VALUE: 0x00000018,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_REAL64: Object({
                ODSI_VALUE: 0x00000040,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_INTEGER40: Object({
                ODSI_VALUE: 0x00000028,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_INTEGER48: Object({
                ODSI_VALUE: 0x00000030,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_INTEGER56: Object({
                ODSI_VALUE: 0x00000038,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_INTEGER64: Object({
                ODSI_VALUE: 0x00000040,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_UNSIGNED24: Object({
                ODSI_VALUE: 0x00000018,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_UNSIGNED40: Object({
                ODSI_VALUE: 0x00000028,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_UNSIGNED48: Object({
                ODSI_VALUE: 0x00000030,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_UNSIGNED56: Object({
                ODSI_VALUE: 0x00000038,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_UNSIGNED64: Object({
                ODSI_VALUE: 0x00000040,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED32 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFTYPE << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_PDO_COMMUNICATION_PARAMETER: Object({
                ODSI_VALUE: 0x06, # Implementation-specific
                ODSI_DATA_TYPE_PDO_COMM_PARAM_ID: ODI_DATA_TYPE_UNSIGNED32,
                ODSI_DATA_TYPE_PDO_COMM_PARAM_TYPE: ODI_DATA_TYPE_UNSIGNED8,
                ODSI_DATA_TYPE_PDO_COMM_PARAM_INHIBIT_TIME: ODI_DATA_TYPE_UNSIGNED16,
                ODSI_DATA_TYPE_PDO_COMM_PARAM_EVENT_TIMER: ODI_DATA_TYPE_UNSIGNED16,
                ODSI_DATA_TYPE_PDO_COMM_PARAM_SYNC_START: ODI_DATA_TYPE_UNSIGNED8,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED16 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFSTRUCT << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_PDO_MAPPING_PARAMETER: Object({
                ODSI_VALUE: 0x00, # Implementation-specific
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED16 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFSTRUCT << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_SDO_PARAMETER: Object({
                ODSI_VALUE: 0x03, # Implementation-specific
                ODSI_DATA_TYPE_SDO_PARAM_CSID: ODI_DATA_TYPE_UNSIGNED32,
                ODSI_DATA_TYPE_SDO_PARAM_SCID: ODI_DATA_TYPE_UNSIGNED32,
                ODSI_DATA_TYPE_SDO_PARAM_SCID: ODI_DATA_TYPE_UNSIGNED32,
                ODSI_DATA_TYPE_SDO_PARAM_NODE_ID: ODI_DATA_TYPE_UNSIGNED8,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED16 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFSTRUCT << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DATA_TYPE_IDENTITY: Object({
                ODSI_VALUE: 0x04, # Implementation-specific
                ODSI_DATA_TYPE_IDENTITY_VENDOR: ODI_DATA_TYPE_UNSIGNED32,
                ODSI_DATA_TYPE_IDENTITY_PRODUCT: ODI_DATA_TYPE_UNSIGNED32,
                ODSI_DATA_TYPE_IDENTITY_REVISION: ODI_DATA_TYPE_UNSIGNED32,
                ODSI_DATA_TYPE_IDENTITY_SERIAL: ODI_DATA_TYPE_UNSIGNED32,
                ODSI_STRUCTURE: (ODI_DATA_TYPE_UNSIGNED16 << OD_STRUCTURE_DATA_TYPE_BITNUM) + (OD_OBJECT_TYPE_DEFSTRUCT << OD_STRUCTURE_OBJECT_TYPE_BITNUM)
            }),
            ODI_DEVICE_TYPE: None,
            ODI_ERROR: None,
            ODI_IDENTITY: None,
        }
        self.update(other, **kwargs)

    def __getitem__(self, index):
        # TODO: Prevent reading of write-only indices
        obj = self._store[index]
#        if len(obj) == 0:
#            return obj.get(ODSI_VALUE)
        return obj

    def __setitem__(self, index, obj):
        if type(index) is not int:
            raise TypeError("CANopen object dictionary index must be an integer")
        if index < 0 or index >= 2 ** 16:
            raise IndexError("CANopen object dictionary index must be a positive 16-bit integer")
        if not isinstance(obj, Object):
            if type(obj) not in [bool, int, float, str]:
                raise TypeError("CANopen object dictionary can only consist of CANopen objects or one of bool, int, float, or str")
            obj = Object({ODSI_VALUE: obj})
        # TODO: Prevent writing of read-only indices
        self._store[index] = obj

    def __delitem__(self, index):
        del self._store[index]

    def __iter__(self):
        return iter(self._store)

    def __len__(self):
        return len(self._store)

    def update(self, other=None, **kwargs):
        if other is not None:
            for index, obj in other.items() if isinstance(other, Mapping) else other:
                self[index] = obj
            for index, obj in kwargs.items():
                self[index] = obj

class Object(MutableMapping):
    def __init__(self, other=None, **kwargs):
        self._store = dict()
        self.update(dict(other, **kwargs))
        if ODSI_VALUE not in self:
            raise RuntimeError("CANopen object sub-index " + ODSI_VALUE + " is required")

    def __getitem__(self, subindex):
        # TODO: Prevent reading of write-only indices
        return self._store[subindex]

    def __setitem__(self, subindex, value):
        if type(subindex) is not int:
            raise TypeError("CANopen object sub-index must be an integer")
        if subindex < 0 or subindex >= 2 ** 8:
            raise IndexError("CANopen object sub-index must be a positive 8-bit integer")
        if type(value) not in [bool, int, float, str]:
            raise TypeError("CANopen objects can only be set to one of bool, int, float, or str")
        # TODO: Prevent writing of read-only indices
        self._store[subindex] = value

    def __delitem__(self, subindex):
        del self._store[subindex]

    def __iter__(self):
        return iter(self._store)

    def __len__(self):
        if ODSI_STRUCTURE in self._store:
            structure = self._store[ODSI_STRUCTURE]
            data_type = (structure >> 8) & 0xFF
            object_type = structure & 0xFF
            if object_type in [OD_OBJECT_TYPE_ARRAY, OD_OBJECT_TYPE_RECORD]:
                return len(self._store) - 2 # Don't count sub-indices 0x00 and 0xFF
        return len(self._store) - 1 # Don't count sub-index 0

    def __getattr__(self, name):
        if name == "data_type":
            if ODSI_STRUCTURE in self._store:
                structure = self._store[ODSI_STRUCTURE]
                data_type = (structure >> 8) & 0xFF
                return data_type
        if name == "object_type":
            if ODSI_STRUCTURE in self._store:
                structure = self._store[ODSI_STRUCTURE]
                object_type = structure & 0xFF
                return object_type
        raise AttributeError("CANopen object does not contain attribute [" + name + "]")

    def update(self, other=None, **kwargs):
        if other is not None:
            for subindex, value in other.items() if isinstance(other, Mapping) else other:
                self[subindex] = value
            for subindex, value in kwargs.items():
                self[subindex] = value

class IntervalTimer(Thread):
    def __init__(self, interval, function, args=None, kwargs=None):
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        super().__init__(args=args, kwargs=kwargs)
        self._stopped = Event()
        self._function = function
        self.interval = interval

    def cancel(self):
        self._stopped.set()
        while self.is_alive():
            pass

    def run(self):
        while not self._stopped.wait(self.interval):
            self._function(*self._args, **self._kwargs)

class Indicator:
    OFF = {'DutyCycle': 0, 'Frequency': 2.5}
    FLASH1 = {'DutyCycle': 16.67, 'Frequency': 0.833}
    #FLASH2 = {} Cannot accomplish with PWM
    #FLASH3 = {} Cannot accomplish with PWM
    BLINK = {'DutyCycle': 50, 'Frequency': 2.5}
    FLICKER = {'DutyCycle': 50, 'Frequency': 10}
    ON = {'DutyCycle': 100, 'Frequency': 2.5}

    def __init__(self, channel, init_state):
        import RPi.GPIO as GPIO
        GPIO.setup(channel, GPIO.OUT)
        self._pwm = GPIO.PWM(channel, init_state.get('Frequency'))
        self._pwm.start(init_state.get('DutyCycle'))

    def set_state(self, state):
        self._pwm.ChangeDutyCycle(state.get('DutyCycle'))
        self._pwm.ChangeFrequency(state.get('Frequency'))

class ErrorIndicator(Indicator):
    def __init__(self, channel, init_state=CAN.Bus.STATE_BUS_OFF, interval=1):
        init_state = self._get_state(init_state)
        self.interval = interval
        super().__init__(channel, init_state)

    def _get_state(self, err_state):
        if err_state == CAN.Bus.STATE_ERROR_ACTIVE:
            indicator_state = self.OFF
        elif err_state == CAN.Bus.STATE_ERROR_PASSIVE:
            indicator_state = self.FLASH1
        else: # BUS-OFF or UNKNOWN
            indicator_state = self.ON
        return indicator_state

    def set_state(self, err_state):
        indicator_state = self._get_state(err_state)
        super().set_state(indicator_state)

class RunIndicator(Indicator):
    def __init__(self, channel, init_state=NMT_STATE_INITIALISATION):
        init_state = self._get_state(init_state)
        super().__init__(channel, init_state)

    def _get_state(self, nmt_state):
        if nmt_state == NMT_STATE_PREOPERATIONAL:
            indicator_state = self.BLINK
        elif nmt_state == NMT_STATE_OPERATIONAL:
            indicator_state = self.ON
        elif nmt_state == NMT_STATE_STOPPED:
            indicator_state = self.FLASH1
        else:
            indicator_state = self.OFF
        return indicator_state

    def set_state(self, nmt_state):
        indicator_state = self._get_state(nmt_state)
        super().set_state(indicator_state)

class SdoAbort(Exception):
    def __init__(self, odi, odsi, code):
        self.odi = odi
        self.odsi = odsi
        self.code = code

class Node:
    def __init__(self, bus: CAN.Bus, id, od: ObjectDictionary, *args, **kwargs):
        self.bus = bus
        if id > 0x7F or id < 0:
            raise ValueError
        self.id = id
        self._default_od = od

        if "err_indicator" in kwargs:
            if isinstance(kwargs["err_indicator"], ErrorIndicator):
                self._err_indicator = kwargs["err_indicator"]
                self._err_indicator_timer = IntervalTimer(self._err_indicator.interval , self._process_err_indicator)
                self._err_indicator_timer.start()
            else:
                raise TypeError

        if "run_indicator" in kwargs:
            if isinstance(kwargs["run_indicator"], RunIndicator):
                self._run_indicator = kwargs["run_indicator"]
            else:
                raise TypeError

        self.od = self._default_od
        self.nmt_state = NMT_STATE_INITIALISATION
        self._heartbeat_consumer_timers = {}
        self._heartbeat_producer_timer = None
        self._tpdo_triggers = [False, False, False, False]
        self._sync_counter = 0
        self._sync_timer = None

    def __del__(self):
        self._reset_timers()

    def _heartbeat_consumer_timeout(self, id):
        if self.nmt_state != NMT_STATE_STOPPED:
            emcy_id = self.od.get(ODI_EMCY_ID)
            if emcy_id is not None:
                msg = CAN.Message(emcy_id, (EMCY_HEARTBEAT_BY_NODE + id).to_bytes(2, byteorder='little') + self.od.get(ODI_ERROR).get(ODSI_VALUE).to_bytes(1, byteorder='little') + b'\x00\x00\x00\x00\x00')
                self._send(msg)

    def _process_err_indicator(self):
        err_state = self.bus.get_state()
        self._err_indicator.set_state(err_state)

    def _process_heartbeat_producer(self):
        heartbeat_producer_time_object = self.od.get(ODI_HEARTBEAT_PRODUCER_TIME)
        if heartbeat_producer_time_object is not None:
            heartbeat_producer_time = heartbeat_producer_time_object.get(ODSI_VALUE, 0) / 1000
        else:
            heartbeat_producer_time = 0
        if self._heartbeat_producer_timer is not None and heartbeat_producer_time != self._heartbeat_producer_timer.interval:
            self._heartbeat_producer_timer.cancel()
        if heartbeat_producer_time != 0 and (self._heartbeat_producer_timer is None or not self._heartbeat_producer_timer.is_alive()):
            self._heartbeat_producer_timer = IntervalTimer(heartbeat_producer_time, self._send_heartbeat)
            self._heartbeat_producer_timer.start()

    def _process_sync(self):
        sync_object = self.od.get(ODI_SYNC)
        if sync_object is not None:
            is_sync_producer = (sync_object.get(ODSI_VALUE, 0) & 0x40000000) != 0
        else:
            is_sync_producer = False
        sync_time_object = self.od.get(ODI_SYNC_TIME)
        if sync_time_object is not None:
            sync_time = sync_time_object.get(ODSI_VALUE, 0) / 1000000
        else:
            sync_time = 0
        if self._sync_timer is not None and (sync_time != self._sync_timer.interval or self.nmt_state == NMT_STATE_STOPPED):
            self._sync_timer.cancel()
        if is_sync_producer and sync_time != 0 and self.nmt_state != NMT_STATE_STOPPED and (self._sync_timer is None or not self._sync_timer.is_alive()):
            self._sync_timer = IntervalTimer(sync_time, self._send_sync)
            self._sync_timer.start()

    def _process_timers(self):
        self._process_heartbeat_producer()
        self._process_sync()

    def _reset_timers(self):
        for i,t in self._heartbeat_consumer_timers.items():
            t.cancel()
        self._heartbeat_consumer_timers = {}
        if self._heartbeat_producer_timer is not None and self._heartbeat_producer_timer.is_alive():
            self._heartbeat_producer_timer.cancel()
        if self._sync_timer is not None and self._sync_timer.is_alive():
            self._sync_timer.cancel()

    def _send(self, msg: CAN.Message):
        self.bus.send(msg)

    def _send_bootup(self):
        msg = CAN.Message((FUNCTION_CODE_NMT_ERROR_CONTROL << FUNCTION_CODE_BITNUM) + self.id)
        self._send(msg)

    def _send_heartbeat(self):
        msg = CAN.Message((FUNCTION_CODE_NMT_ERROR_CONTROL << FUNCTION_CODE_BITNUM) + self.id, [self.nmt_state])
        self._send(msg)

    def _send_pdo(self, i):
        i = i - 1
        data = bytes()
        tpdo_mp = self.od.get(ODI_TPDO1_MAPPING_PARAMETER + i)
        if tpdo_mp is not None:
            for j in range(tpdo_mp.get(ODSI_VALUE, 0)):
                mapping_param = tpdo_mp.get(j + 1)
                if mapping_param is not None:
                    mapping_object = self.od.get(mapping_param >> 16)
                    if mapping_object is not None:
                        mapping_value = mapping_object.get((mapping_param >> 8) & 0xFF)
                    else:
                        mapping_value = 0 # This should really raise an exception, invalid PDO mapping ODSI
                    if mapping_value is not None:
                        data = data + mapping_value.to_bytes((mapping_param & 0xFF) // 8, byteorder='little')
                else:
                    pass # This should really raise an exception, invalid PDO mapping ODI
            msg = CAN.Message(((FUNCTION_CODE_TPDO1 + (2 * i)) << FUNCTION_CODE_BITNUM) + self.id, data)
            self._send(msg)

    def _send_sync(self):
        sync_object = self.od.get(ODI_SYNC)
        if sync_object is not None:
            sync_value = sync_object.get(ODSI_VALUE)
            if sync_value is not None:
                sync_id = sync_value & 0x3FF
                msg = CAN.Message(sync_id)
                self._send(msg)

    @property
    def nmt_state(self):
        return self._nmt_state

    @nmt_state.setter
    def nmt_state(self, nmt_state):
        self._nmt_state = nmt_state
        try:
            self._run_indicator.set_state(nmt_state)
        except AttributeError:
            pass

    def listen(self, blocking=False):
        if blocking:
            self._listen()
        else:
            self._listener = Thread(target=self._listen)
            self._listener.start()

    def _listen(self):
        while True:
            rlist, _, _, = select([self.bus], [], [])
            for bus in rlist:
                msg = bus.recv()
                self.recv(msg)

    def boot(self):
        self._send_bootup()
        self.nmt_state = NMT_STATE_PREOPERATIONAL
        self._process_timers()

    def recv(self, msg: CAN.Message):
        id = msg.arbitration_id
        data = msg.data
        rtr = msg.is_remote_frame
        fc = (id >> FUNCTION_CODE_BITNUM) & 0xF
        if rtr:
            target_node = id & 0x7F
            if target_node == self.id or target_node == BROADCAST_NODE_ID:
                if self.nmt_state == NMT_STATE_OPERATIONAL:
                    if fc == FUNCTION_CODE_TPDO1:
                        tpdo1_cp = self.od.get(ODI_TPDO1_COMMUNICATION_PARAMETER)
                        if tpdo1_cp is not None:
                            tpdo1_cp_id = tpdo1_cp.get(ODSI_TPDO_COMM_PARAM_ID)
                            if tpdo1_cp_id is not None and (tpdo1_cp_id >> TPDO_COMM_PARAM_ID_VALID_BITNUM) & 1 == 0 and (tpdo1_cp_id >> TPDO_COMM_PARAM_ID_RTR_BITNUM) & 1 == 0:
                                tpdo1_cp_type = tpdo1_cp.get(ODSI_TPDO_COMM_PARAM_TYPE)
                                if tpdo1_cp_type == 0xFC:
                                    self._tpdo_triggers[0] = True; # Defer until SYNC event
                                elif tpdo1_cp_type == 0xFD:
                                    self._send_pdo(1)
                elif fc == FUNCTION_CODE_NMT_ERROR_CONTROL:
                    self._send_heartbeat()
        elif fc == FUNCTION_CODE_NMT:
            command = id & 0x7F
            if command == NMT_NODE_CONTROL:
                target_node = data[1]
                if target_node == self.id or target_node == BROADCAST_NODE_ID:
                    cs = data[0]
                    if cs == NMT_NODE_CONTROL_START:
                        self.nmt_state = NMT_STATE_OPERATIONAL
                    elif cs == NMT_NODE_CONTROL_STOP:
                        self.nmt_state = NMT_STATE_STOPPED
                    elif cs == NMT_NODE_CONTROL_PREOPERATIONAL:
                        self.nmt_state = NMT_STATE_PREOPERATIONAL
                    elif cs == NMT_NODE_CONTROL_RESET_NODE:
                        self.reset()
                    elif cs == NMT_NODE_CONTROL_RESET_COMMUNICATION:
                        self.reset_communication()
        elif fc == FUNCTION_CODE_SYNC and self.nmt_state == NMT_STATE_OPERATIONAL:
            sync_obj = self.od.get(ODI_SYNC)
            if sync_obj is not None and (sync_obj.get(ODSI_VALUE) & 0x3FF) == id:
                self._sync_counter = (self._sync_counter + 1) % 241
                for i in range(4):
                    tpdo_cp = self.od.get(ODI_TPDO1_COMMUNICATION_PARAMETER + i)
                    if tpdo_cp is not None:
                        tpdo_cp_id = tpdo_cp.get(ODSI_TPDO_COMM_PARAM_ID)
                        if tpdo_cp_id is not None and (tpdo_cp_id >> TPDO_COMM_PARAM_ID_VALID_BITNUM) & 1 == 0:
                            tpdo_cp_type = tpdo_cp.get(ODSI_TPDO_COMM_PARAM_TYPE)
                            if tpdo_cp_type is not None and (((tpdo_cp_type == 0 or tpdo_cp_type == 0xFC) and self._tpdo_triggers[i]) or tpdo_cp_type == self._sync_counter):
                                self._send_pdo(i + 1)
                                self._tpdo_triggers[i] = False
        elif fc == FUNCTION_CODE_SDO_RX and self.nmt_state != NMT_STATE_STOPPED:
            sdo_server_object = self.od.get(ODI_SDO_SERVER)
            if sdo_server_object is not None:
                sdo_server_id = sdo_server_object.get(ODSI_SDO_SERVER_DEFAULT_CSID)
                if sdo_server_id is not None and id == sdo_server_id:
                    if len(data) == 8:
                        try:
                            ccs = (data[0] >> SDO_CCS_BITNUM) & (2 ** SDO_CCS_LENGTH - 1)
                            odi = (data[2] << 8) + data[1]
                            odsi = data[3]
                            if odi in self.od:
                                obj = self.od.get(odi)
                                if odsi in obj:
                                    if ccs == SDO_CCS_UPLOAD:
                                        scs = SDO_SCS_UPLOAD
                                        n = None # n = len(self.od.get(odi).get(odsi)) # TODO: Lookup length
                                        if n is None:
                                            n = 0
                                            s = 0
                                            e = 1
                                        elif n > 4:
                                            s = 1
                                            e = 0
                                        else:
                                            s = 1
                                            e = 1
                                        sdo_data = obj.get(odsi)
                                    elif ccs == SDO_CCS_DOWNLOAD:
                                        scs = SDO_SCS_DOWNLOAD
                                        s = (data[0] >> SDO_S_BITNUM) & 1
                                        e = (data[0] >> SDO_E_BITNUM) & 1
                                        if e == 1 and s == 1:
                                            n = (data[0] >> SDO_N_BITNUM) & (2 ** SDO_N_LENGTH - 1)
                                            obj.update({odsi: int.from_bytes(data[4:8-n], byteorder='little')})
                                            self.od.update({odi: obj})
                                        elif e == 1 and s == 0:
                                            if ODSI_STRUCTURE in obj:
                                                data_type_index = obj.get(ODSI_STRUCTURE) >> OD_STRUCTURE_DATA_TYPE_BITNUM
                                                if data_type_index in self.od:
                                                    data_type_object = self.od.get(data_type_index)
                                                    if ODSI_VALUE in data_type_object:
                                                        n = 4 - max(1, data_type_object.get(ODSI_VALUE) // 8)
                                                        obj.update({odsi: int.from_bytes(data[4:8-n], byteorder='little')})
                                                        self.od.update({odi: obj})
                                        elif e == 0 and s == 1:
                                            self._sdo_buffer = data[4:8]
                                        else:
                                            raise SdoAbort(odi, odsi, SDO_ABORT_GENERAL) # e == 0, s == 0 is reserved
                                        sdo_data = 0
                                    else:
                                        raise SdoAbort(odi, odsi, SDO_ABORT_INVALID_CS)
                                else:
                                    raise SdoAbort(odi, odsi, SDO_ABORT_SUBINDEX_DNE)
                            else:
                                raise SdoAbort(odi, odsi, SDO_ABORT_OBJECT_DNE)
                        except SdoAbort as a:
                            scs = SDO_CS_ABORT
                            n = 0
                            s = 0
                            e = 0
                            sdo_data = a.code
                        sdo_data = sdo_data.to_bytes(4, byteorder='little')
                        data = [(scs << SDO_SCS_BITNUM) + (n << SDO_N_BITNUM) + (e << SDO_E_BITNUM), (odi & 0xFF), (odi >> 8), (odsi)] + list(sdo_data)
                        msg = CAN.Message(sdo_server_object.get(ODSI_SDO_SERVER_DEFAULT_SCID), data)
                        self._send(msg)
                        self._process_timers()
                elif fc == FUNCTION_CODE_NMT_ERROR_CONTROL:
                    producer_id = id & 0x7F
                    if producer_id in self._heartbeat_consumer_timers:
                        self._heartbeat_consumer_timers.get(producer_id).cancel()
                    heartbeat_consumer_time_object = self.od.get(ODI_HEARTBEAT_CONSUMER_TIME)
                    if heartbeat_consumer_time_object is not None:
                        heartbeat_consumer_time = heartbeat_consumer_time_object.get(ODSI_HEARTBEAT_CONSUMER_TIME, 0) / 1000
                    else:
                        heartbeat_consumer_time = 0
                    if heartbeat_consumer_time != 0:
                        heartbeat_consumer_timer = Timer(heartbeat_consumer_time, self._heartbeat_consumer_timeout, [producer_id])
                        heartbeat_consumer_timer.start()
                        self._heartbeat_consumer_timers.update({producer_id: heartbeat_consumer_timer})

    def reset(self):
        self.od = self._default_od
        self.reset_communication()

    def reset_communication(self):
        self._reset_timers()
        for odi, object in self._default_od.items():
            if odi >= 0x1000 or odi <= 0x1FFF:
                self.od.update({odi: object})
        self.boot()

    def trigger_tpdo(self, tpdo): # Event-driven TPDO
        tpdo_cp = self.od.get(ODI_TPDO1_COMMUNICATION_PARAMETER + tpdo - 1)
        if tpdo_cp is not None:
            tpdo_cp_id = tpdo_cp.get(ODSI_TPDO_COMM_PARAM_ID)
            if tpdo_cp_id is not None and (tpdo_cp_id >> TPDO_COMM_PARAM_ID_VALID_BITNUM) & 1 == 0:
                tpdo_cp_type = tpdo_cp.get(ODSI_TPDO_COMM_PARAM_TYPE)
                if tpdo_cp_type is not None and (tpdo_cp_type == 0xFE or tpdo_cp_type == 0xFF):
                    self._send_pdo(tpdo)
                else:
                    self._tpdo_triggers[tpdo] = True # Defer until SYNC event
