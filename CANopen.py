#TODO: OSErrors are thrown if the CAN bus goes down, need to do threaded Exception handling
#      See http://stackoverflow.com/questions/2829329/catch-a-threads-exception-in-the-caller-thread-in-python
#TODO: Check for BUS-OFF before attempting to send

import CAN
from collections import Mapping, MutableMapping
import configparser
from enum import Enum, IntEnum, unique
from select import select
import struct
from threading import Event, Thread, Timer, enumerate
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
NMT_FLYING_MASTER_RESPONSE = 0x71
NMT_FLYING_MASTER_REQUEST = 0x72
NMT_ACTIVE_MASTER_REQUEST = 0x73
NMT_MASTER_RESPONSE = 0x74
NMT_MASTER_REQUEST = 0x75
NMT_FORCE_FLYING_MASTER = 0x76

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
ODI_DATA_TYPE_PDO_MAPPING_PARAMETER = 0x0021
ODI_DATA_TYPE_SDO_PARAMETER = 0x0022
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
ODI_NMT_INHIBIT_TIME = 0x102A
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
ODI_REDUNDANCY_CONFIGURATION = 0x1F60
ODSI_REDUNDANCY_CONFIG_MAX_TX_DELAY_TIME = 0x01
ODSI_REDUNDANCY_CONFIG_HB_EVAL_TIME_POWER_ON = 0x02
ODSI_REDUNDANCY_CONFIG_HB_EVAL_TIME_RESET_COMM = 0x03
ODSI_REDUNDANCY_CONFIG_CHAN_ERR_CNT_THRESHOLD = 0x04
ODSI_REDUNDANCY_CONFIG_CHAN_ERR_CNT = 0x05
ODI_NMT_STARTUP = 0x1F80
ODI_REQUEST_NMT = 0x1F82
ODI_BOOT_TIME = 0x1F89
ODI_NMT_FLYING_MASTER_TIMING_PARAMETERS = 0x1F90
ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_TIMEOUT = 0x01
ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_DELAY = 0x02
ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_PRIORITY = 0x03
ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_PRIORITY_TIME_SLOT = 0x04
ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_DEVICE_TIME_SLOT = 0x05
ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_DETECT_TIME = 0x06
ODI_SELF_STARTING_NODES_TIMING_PARAMETERS = 0x1F91
ODSI_SELF_STARTING_NODES_TIMING_PARAMS_TIMEOUT = 0x01
ODSI_SELF_STARTING_NODES_TIMING_PARAMS_DELAY = 0x02
ODSI_SELF_STARTING_NODES_TIMING_PARAMS_TIME_SLOT = 0x03

# SDO
SDO_N_BITNUM = 3
SDO_N_LENGTH = 2
SDO_E_BITNUM = 1
SDO_S_BITNUM = 0
SDO_CS_BITNUM = 5
SDO_CS_LENGTH = 3
SDO_CCS_DOWNLOAD = 1
SDO_CCS_UPLOAD = 2
SDO_SCS_DOWNLOAD = 3
SDO_SCS_UPLOAD = 2
SDO_CS_ABORT = 4
SDO_ABORT_INVALID_CS = 0x05040001
SDO_ABORT_WO = 0x06010001
SDO_ABORT_RO = 0x06010002
SDO_ABORT_OBJECT_DNE = 0x06020000
SDO_ABORT_SUBINDEX_DNE = 0x06090011
SDO_ABORT_GENERAL = 0x08000000

# PDO
TPDO_COMM_PARAM_ID_VALID_BITNUM = 31
TPDO_COMM_PARAM_ID_RTR_BITNUM = 30

class ObjectDictionary(MutableMapping):
    def __init__(self, other=None, **kwargs):
        self._store = { # Defaults
            ODI_DATA_TYPE_BOOLEAN: Object(
                parameter_name="BOOLEAN",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000001
            ),
            ODI_DATA_TYPE_INTEGER8: Object(
                parameter_name="INTEGER8",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000008
            ),
            ODI_DATA_TYPE_INTEGER16: Object(
                parameter_name="INTEGER16",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000010
            ),
            ODI_DATA_TYPE_INTEGER32: Object(
                parameter_name="INTEGER32",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000020
            ),
            ODI_DATA_TYPE_UNSIGNED8: Object(
                parameter_name="UNSIGNED8",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000008
            ),
            ODI_DATA_TYPE_UNSIGNED16: Object(
                parameter_name="INTEGER16",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000010
            ),
            ODI_DATA_TYPE_UNSIGNED32: Object(
                parameter_name="INTEGER32",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000020
            ),
            ODI_DATA_TYPE_REAL32: Object(
                parameter_name="REAL32",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000020
            ),
            ODI_DATA_TYPE_VISIBLE_STRING: Object(
                parameter_name="VISIBLE_STRING",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000000 # Implementation-specific
            ),
            ODI_DATA_TYPE_OCTET_STRING: Object(
                parameter_name="OCTET_STRING",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000000 # Implementation-specific
            ),
            ODI_DATA_TYPE_UNICODE_STRING: Object(
                parameter_name="UNICODE_STRING",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000000 # Implementation-specific
            ),
            ODI_DATA_TYPE_TIME_OF_DAY: Object(
                parameter_name="TIME_OF_DAY",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000030
            ),
            ODI_DATA_TYPE_DOMAIN: Object(
                parameter_name="DOMAIN",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000000
            ),
            ODI_DATA_TYPE_INTEGER24: Object(
                parameter_name="INTEGER24",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000018
            ),
            ODI_DATA_TYPE_REAL64: Object(
                parameter_name="REAL64",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000040
            ),
            ODI_DATA_TYPE_INTEGER40: Object(
                parameter_name="INTEGER40",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000028
            ),
            ODI_DATA_TYPE_INTEGER48: Object(
                parameter_name="INTEGER48",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000030
            ),
            ODI_DATA_TYPE_INTEGER56: Object(
                parameter_name="INTEGER56",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000038
            ),
            ODI_DATA_TYPE_INTEGER64: Object(
                parameter_name="INTEGER64",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000040
            ),
            ODI_DATA_TYPE_UNSIGNED24: Object(
                parameter_name="UNSIGNED24",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000018
            ),
            ODI_DATA_TYPE_UNSIGNED40: Object(
                parameter_name="UNSIGNED40",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000028
            ),
            ODI_DATA_TYPE_UNSIGNED48: Object(
                parameter_name="UNSIGNED48",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000030
            ),
            ODI_DATA_TYPE_UNSIGNED56: Object(
                parameter_name="UNSIGNED56",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000038
            ),
            ODI_DATA_TYPE_UNSIGNED64: Object(
                parameter_name="UNSIGNED64",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000040
            ),
            ODI_DATA_TYPE_PDO_COMMUNICATION_PARAMETER: Object(
                parameter_name="PDO Communication Parameter Record",
                object_type=ObjectType.DEFSTRUCT,
                data_type=ODI_DATA_TYPE_PDO_COMMUNICATION_PARAMETER,
                sub_number=6,
                subs={
                    ODSI_VALUE: SubObject(
                        parameter_name="number of supported entries in the record",
                        access_type=AccessType.RO,
                        data_type=ODI_DATA_TYPE_UNSIGNED8,
                        low_limit=6,
                        high_limit=6,
                        default_value=6
                    ),
                    ODSI_DATA_TYPE_PDO_COMM_PARAM_ID: SubObject(
                        parameter_name="COB-ID",
                        access_type=AccessType.RO,
                        data_type=ODI_DATA_TYPE_UNSIGNED32,
                        low_limit=ODI_DATA_TYPE_UNSIGNED32,
                        high_limit=ODI_DATA_TYPE_UNSIGNED32,
                        default_value=ODI_DATA_TYPE_UNSIGNED32
                    ),
                    ODSI_DATA_TYPE_PDO_COMM_PARAM_TYPE: SubObject(
                        parameter_name="transmission type",
                        access_type=AccessType.RO,
                        data_type=ODI_DATA_TYPE_UNSIGNED32,
                        low_limit=ODI_DATA_TYPE_UNSIGNED8,
                        high_limit=ODI_DATA_TYPE_UNSIGNED8,
                        default_value=ODI_DATA_TYPE_UNSIGNED8
                    ),
                    ODSI_DATA_TYPE_PDO_COMM_PARAM_INHIBIT_TIME: SubObject(
                        parameter_name="inhibit time",
                        access_type=AccessType.RO,
                        data_type=ODI_DATA_TYPE_UNSIGNED32,
                        low_limit=ODI_DATA_TYPE_UNSIGNED16,
                        high_limit=ODI_DATA_TYPE_UNSIGNED16,
                        default_value=ODI_DATA_TYPE_UNSIGNED16
                    ),
                    ODSI_DATA_TYPE_PDO_COMM_PARAM_EVENT_TIMER: SubObject(
                        parameter_name="event timer",
                        access_type=AccessType.RO,
                        data_type=ODI_DATA_TYPE_UNSIGNED32,
                        low_limit=ODI_DATA_TYPE_UNSIGNED16,
                        high_limit=ODI_DATA_TYPE_UNSIGNED16,
                        default_value=ODI_DATA_TYPE_UNSIGNED16
                    ),
                    ODSI_DATA_TYPE_PDO_COMM_PARAM_SYNC_START: SubObject(
                        parameter_name="sync start",
                        access_type=AccessType.RO,
                        data_type=ODI_DATA_TYPE_UNSIGNED32,
                        low_limit=ODI_DATA_TYPE_UNSIGNED8,
                        high_limit=ODI_DATA_TYPE_UNSIGNED8,
                        default_value=ODI_DATA_TYPE_UNSIGNED8
                    )
                }
            ),
            ODI_DATA_TYPE_PDO_MAPPING_PARAMETER: Object(
                parameter_name="PDO Mapping Parameter Record",
                object_type=ObjectType.RECORD,
                data_type=ODI_DATA_TYPE_PDO_MAPPING_PARAMETER,
                sub_number=0x40,
                subs=dict(list({
                    ODSI_VALUE: SubObject(
                        parameter_name="number of supported entries in the record",
                        access_type=AccessType.RO,
                        data_type=ODI_DATA_TYPE_UNSIGNED8,
                        low_limit=0x40,
                        high_limit=0x40,
                        default_value=0x40
                    )
                }.items()) + list({index: SubObject(
                        parameter_name="Object " + str(index) + " to be mapped",
                        access_type=AccessType.RO,
                        data_type=ODI_DATA_TYPE_UNSIGNED32,
                        low_limit=ODI_DATA_TYPE_UNSIGNED32,
                        high_limit=ODI_DATA_TYPE_UNSIGNED32,
                        default_value=ODI_DATA_TYPE_UNSIGNED32
                    ) for index in range(1, 0x41)}.items())
                )
            ),
            ODI_DATA_TYPE_SDO_PARAMETER: Object(
                parameter_name="SDO Parameter Record",
                object_type=ObjectType.RECORD,
                data_type=ODI_DATA_TYPE_SDO_PARAMETER,
                sub_number=3,
                subs={
                    ODSI_VALUE: SubObject(
                        parameter_name="number of supported entries",
                        access_type=AccessType.RO,
                        data_type=ODI_DATA_TYPE_UNSIGNED8,
                        low_limit=3,
                        high_limit=3,
                        default_value=3
                    ),
                    ODSI_DATA_TYPE_SDO_PARAM_CSID: SubObject(
                        parameter_name="COB-ID client -> server",
                        access_type=AccessType.RO,
                        data_type=ODI_DATA_TYPE_UNSIGNED32,
                        low_limit=ODI_DATA_TYPE_UNSIGNED32,
                        high_limit=ODI_DATA_TYPE_UNSIGNED32,
                        default_value=ODI_DATA_TYPE_UNSIGNED32
                    ),
                    ODSI_DATA_TYPE_SDO_PARAM_SCID: SubObject(
                        parameter_name="COB-ID server -> client",
                        access_type=AccessType.RO,
                        data_type=ODI_DATA_TYPE_UNSIGNED32,
                        low_limit=ODI_DATA_TYPE_UNSIGNED32,
                        high_limit=ODI_DATA_TYPE_UNSIGNED32,
                        default_value=ODI_DATA_TYPE_UNSIGNED32
                    ),
                    ODSI_DATA_TYPE_SDO_PARAM_NODE_ID: SubObject(
                        parameter_name="node ID of SDO's client resp. server",
                        access_type=AccessType.RO,
                        data_type=ODI_DATA_TYPE_UNSIGNED32,
                        low_limit=ODI_DATA_TYPE_UNSIGNED8,
                        high_limit=ODI_DATA_TYPE_UNSIGNED8,
                        default_value=ODI_DATA_TYPE_UNSIGNED8
                    )
                }
            ),
            ODI_DATA_TYPE_IDENTITY: Object(
                parameter_name="Identity Record",
                object_type=ObjectType.RECORD,
                data_type=ODI_DATA_TYPE_IDENTITY,
                sub_number=4,
                subs={
                    ODSI_VALUE: SubObject(
                        parameter_name="number of supported entries",
                        access_type=AccessType.RO,
                        data_type=ODI_DATA_TYPE_UNSIGNED8,
                        low_limit=3,
                        high_limit=3,
                        default_value=3
                    ),
                    ODSI_DATA_TYPE_IDENTITY_VENDOR: SubObject(
                        parameter_name="Vendor-ID",
                        access_type=AccessType.RO,
                        data_type=ODI_DATA_TYPE_UNSIGNED32,
                        low_limit=ODI_DATA_TYPE_UNSIGNED32,
                        high_limit=ODI_DATA_TYPE_UNSIGNED32,
                        default_value=ODI_DATA_TYPE_UNSIGNED32
                    ),
                    ODSI_DATA_TYPE_IDENTITY_PRODUCT: SubObject(
                        parameter_name="Product code",
                        access_type=AccessType.RO,
                        data_type=ODI_DATA_TYPE_UNSIGNED32,
                        low_limit=ODI_DATA_TYPE_UNSIGNED32,
                        high_limit=ODI_DATA_TYPE_UNSIGNED32,
                        default_value=ODI_DATA_TYPE_UNSIGNED32
                    ),
                    ODSI_DATA_TYPE_IDENTITY_REVISION: SubObject(
                        parameter_name="Revision number",
                        access_type=AccessType.RO,
                        data_type=ODI_DATA_TYPE_UNSIGNED32,
                        low_limit=ODI_DATA_TYPE_UNSIGNED32,
                        high_limit=ODI_DATA_TYPE_UNSIGNED32,
                        default_value=ODI_DATA_TYPE_UNSIGNED32
                    ),
                    ODSI_DATA_TYPE_IDENTITY_SERIAL: SubObject(
                        parameter_name="Serial number",
                        access_type=AccessType.RO,
                        data_type=ODI_DATA_TYPE_UNSIGNED32,
                        low_limit=ODI_DATA_TYPE_UNSIGNED32,
                        high_limit=ODI_DATA_TYPE_UNSIGNED32,
                        default_value=ODI_DATA_TYPE_UNSIGNED32
                    )
                }
            ),
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

    def from_eds(filename):
        eds = configparser.ConfigParser()
        eds.read(filename)
        indices = []
        for section in ['MandatoryObjects', 'OptionalObjects', 'ManufacturerObjects']:
            if section not in eds:
                continue
            n = int(eds[section]['SupportedObjects'])
            for i in range(1, n + 1):
                indices.append(int(eds[section][str(i)], 0))
        od = {}
        for i in indices:
            oc = eds["{:4X}".format(i)]
            sub_number = int(oc.get('SubNumber', '0'), 0)
            subs = {}
            si = 0
            while len(subs) < sub_number and si <= 0xFF:
                key = "{:4X}sub{:d}".format(i, si)
                if key in eds:
                    sub = SubObject.from_config(eds[key])
                    subs.update({si: sub})
                si += 1
            o = Object.from_config(oc, subs)
            od.update({i: o})
        return ObjectDictionary(od)

@unique
class ObjectType(IntEnum):
    NULL = OD_OBJECT_TYPE_NULL
    DOMAIN = OD_OBJECT_TYPE_DOMAIN
    DEFTYPE = OD_OBJECT_TYPE_DEFTYPE
    DEFSTRUCT = OD_OBJECT_TYPE_DEFSTRUCT
    VAR = OD_OBJECT_TYPE_VAR
    ARRAY = OD_OBJECT_TYPE_ARRAY
    RECORD = OD_OBJECT_TYPE_RECORD

@unique
class AccessType(Enum):
    RO = "ro"
    WO = "wo"
    RW = "rw"
    RWR = "rwr"
    RWW = "rww"
    CONST = "const"

class DataType(int):
    def __new__(cls, value):
        instance = int.__new__(cls, value)
        if not 0x0 <= instance <= 0x9F:
            raise ValueError("Invalid data type: 0x{:X}".format(value))
        return instance

class ProtoObject(MutableMapping):
    def __init__(self, **kwargs):
        # See Table 1 of CiA 306-1
        if kwargs["parameter_name"] is not None:
            if not isinstance(kwargs["parameter_name"], str):
                raise TypeError
            if len(kwargs["parameter_name"]) > 241:
                raise ValueError
        self.parameter_name = kwargs["parameter_name"]
        if "object_type" in kwargs and kwargs["object_type"] is not None:
            self.object_type = ObjectType(kwargs["object_type"])
        else:
            self.object_type = ObjectType.VAR
        if "data_type" not in kwargs:
            #if object_type in [ObjectType.DEFTYPE, ObjectType.VAR]:
                #raise ValueError # Removed so RECORD SubObjects don't have to redefine data type
            if self.object_type == ObjectType.DOMAIN:
                self.data_type = DataType(ODI_DATA_TYPE_DOMAIN)
            else:
                self.data_type = None
        elif kwargs["data_type"] is None:
                self.data_type = None
        else:
            self.data_type = DataType(kwargs["data_type"])
        if "access_type" not in kwargs:
            if self.object_type in [ObjectType.DEFTYPE, ObjectType.VAR]:
                raise ValueError
            elif self.object_type == ObjectType.DOMAIN:
                self.access_type = AccessType.RW
            else:
                self.access_type = None
        elif kwargs["access_type"] is None:
                self.access_type = None
        else:
            self.access_type = AccessType(kwargs["access_type"])
        if "default_value" in kwargs and self.object_type in [ObjectType.DEFTYPE, ObjectType.VAR, ObjectType.DOMAIN]:
            self.default_value = kwargs["default_value"]
        else:
            self.default_value = None
        if self.object_type in [ObjectType.DEFTYPE, ObjectType.VAR]:
            if "pdo_mapping" not in kwargs:
                self.pdo_mapping = False
            elif kwargs["pdo_mapping"] is None:
                self.pdo_mapping = False
            elif kwargs["pdo_mapping"] not in [True, False]:
                raise ValueError
            else:
                self.pdo_mapping = bool(kwargs["pdo_mapping"])
        else:
            self.pdo_mapping = None
        if self.object_type in [ObjectType.DEFTYPE, ObjectType.VAR] and "low_limit" in kwargs:
            self.low_limit = kwargs["low_limit"]
        else:
            self.low_limit = None
        if self.object_type in [ObjectType.DEFTYPE, ObjectType.VAR] and "high_limit" in kwargs:
            self.high_limit = kwargs["high_limit"]
        else:
            self.high_limit = None

    def __getitem__(self, subindex):
        if subindex == ODSI_VALUE and self.sub_number == 0:
            if self.access_type == AccessType.WO:
                raise AttributeError
        return self._store[subindex]

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

    def __setitem__(self, name, value):
        # TODO: Prevent writing of read-only indices
        super().__setitem__(name, value)

    def update(self, other=None, **kwargs):
        if other is not None:
            for subindex, value in other.items() if isinstance(other, Mapping) else other:
                self[subindex] = value
            for subindex, value in kwargs.items():
                self[subindex] = value

    @staticmethod
    def _from_config(cfg):
        parameter_name = cfg['ParameterName']
        if 'ObjectType' in cfg:
            object_type = ObjectType(int(cfg['ObjectType'], 0))
        else:
            object_type = None
        if 'DataType' in cfg:
            data_type = int(cfg['DataType'], 0)
        else:
            data_type = None
        if 'AccessType' in cfg:
            access_type = AccessType(cfg['AccessType'])
        else:
            access_type = None
        if 'DefaultValue' in cfg:
            try:
                default_value = int(cfg['DefaultValue'], 0)
            except ValueError:
                default_value = cfg['DefaultValue'] # TODO: Validate values
        else:
            default_value = None
        if 'PDOMapping' in cfg:
            pdo_mapping = bool(cfg['PDOMapping'])
        else:
            pdo_mapping = None
        return ProtoObject(
            parameter_name=parameter_name,
            object_type=object_type,
            data_type=data_type,
            access_type=access_type,
            default_value=default_value,
            pdo_mapping=pdo_mapping
        )


class SubObject(ProtoObject):
    def __init__(self, **kwargs):
        #kwargs["object_type"] = ObjectType.VAR
        super().__init__(**kwargs)
        self.value = self.default_value

    def __setitem__(self, name, value):
        if name == "value" and type(value) not in [bool, int, float, str]:
            raise TypeError("CANopen objects can only be set to one of bool, int, float, or str")
        super().__setattr__(name,  value)

    @classmethod
    def from_config(cls, cfg):
        po = super()._from_config(cfg)
        return cls(
            parameter_name=po.parameter_name,
            object_type=po.object_type,
            data_type=po.data_type,
            access_type=po.access_type,
            default_value=po.default_value,
            pdo_mapping=po.pdo_mapping
        )

class Object(ProtoObject):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.object_type in [ObjectType.DEFSTRUCT, ObjectType.ARRAY, ObjectType.RECORD]:
            if "sub_number" not in kwargs:
                raise ValueError
            if not isinstance(kwargs["sub_number"], int):
                raise TypeError
            if kwargs["sub_number"] not in range(0xFF):
                raise ValueError
            self.sub_number = kwargs["sub_number"]
        else:
            self.sub_number = None
        if "obj_flags" in kwargs:
            self.obj_flags = kwargs["obj_flags"]
        else:
            self.obj_flags = 0

        self._store = {ODSI_STRUCTURE: SubObject(
            parameter_name="structure",
            data_type=ODI_DATA_TYPE_UNSIGNED32,
            access_type=AccessType.CONST,
            default_value=(self.data_type << 16) + self.object_type
        )}
        if self.sub_number is None:
            self._store.update({
                ODSI_VALUE: SubObject(
                    parameter_name="value",
                    data_type=self.data_type,
                    access_type=self.access_type,
                    default_value=self.default_value
                )
            })
        else:
            if "subs" not in kwargs:
                raise ValueError
            if not isinstance(kwargs["subs"], dict):
                raise TypeError
            if not all(k in range(0, 0xFF) for k in kwargs["subs"].keys()):
                raise ValueError
            if not all(isinstance(v, SubObject) for v in kwargs["subs"].values()):
                raise TypeError
            self._store.update(kwargs["subs"])

    def __setitem__(self, subindex, sub_object: SubObject):
        if type(subindex) is not int:
            raise TypeError("CANopen object sub-index must be an integer")
        if subindex < 0 or subindex >= 2 ** 8:
            raise IndexError("CANopen object sub-index must be a positive 8-bit integer")
        if type(sub_object) is not SubObject:
            raise TypeError("Must be a SubObject")
        # TODO: Prevent writing of read-only indices
        self._store[subindex] = sub_object

    @classmethod
    def from_config(cls, cfg, subs):
        po = super()._from_config(cfg)
        return cls(
            parameter_name=po.parameter_name,
            object_type=po.object_type,
            data_type=po.data_type,
            access_type=po.access_type,
            default_value=po.default_value,
            pdo_mapping=po.pdo_mapping,
            sub_number=int(cfg.get('SubNumber', '0'), 0),
            subs=subs
        )

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

class Message(CAN.Message):
    def __init__(self, fc, node_id, data=[]):
        arbitration_id = (fc << FUNCTION_CODE_BITNUM) + node_id
        super().__init__(arbitration_id, data)

    @classmethod
    def factory(cls, msg: CAN.Message):
        fc = msg.arbitration_id >> FUNCTION_CODE_BITNUM
        node_id = msg.arbitration_id & 0x7F
        if fc == FUNCTION_CODE_NMT:
            return NmtMessage.factory(node_id, msg.data)
        if fc == FUNCTION_CODE_SYNC:
            if node_id == 0x00:
                return SyncMessage()
            else:
                return EmcyMessage.factory(node_id, msg.data)
        if fc == FUNCTION_CODE_TPDO1:
            return PdoMessage(fc, node_id, msg.data)
        if fc == FUNCTION_CODE_TPDO2:
            return PdoMessage(fc, node_id, msg.data)
        if fc == FUNCTION_CODE_TPDO3:
            return PdoMessage(fc, node_id, msg.data)
        if fc == FUNCTION_CODE_TPDO4:
            return PdoMessage(fc, node_id, msg.data)
        if fc == FUNCTION_CODE_SDO_TX:
            return SdoResponse.factory(node_id, msg.data)
        if fc == FUNCTION_CODE_SDO_RX:
            return SdoRequest.factory(node_id, msg.data)
        if fc == FUNCTION_CODE_NMT_ERROR_CONTROL:
            return NmtErrorControlMessage.factory(node_id, msg.data)
        raise NotImplementedError

class NmtMessage(Message):
    def __init__(self, command, data):
        super().__init__(FUNCTION_CODE_NMT, command, data)

    @classmethod
    def factory(cls, cmd, data):
        if cmd == NMT_NODE_CONTROL:
            return NmtNodeControlMessage.factory(data)
        if cmd == NMT_GFC:
            return NmtGfcMessage()
        if cmd == NMT_FLYING_MASTER_RESPONSE:
            return NmtFlyingMasterResponse.factory(data)
        if cmd == NMT_FLYING_MASTER_REQUEST:
            return NmtFlyingMasterRequest()
        if cmd == NMT_ACTIVE_MASTER_REQUEST:
            return NmtActiveMasterRequest()
        if cmd == NMT_MASTER_RESPONSE:
            return NmtMasterResponse()
        if cmd == NMT_MASTER_REQUEST:
            return NmtMasterRequest()
        if cmd == NMT_FORCE_FLYING_MASTER:
            return NmtForceFlyingMasterRequest()
        raise NotImplementedError

class NmtNodeControlMessage(NmtMessage):
    def __init__(self, cmd, target_id):
        data = struct.pack("<BB", cmd, target_id)
        super().__init__(NMT_NODE_CONTROL, data)

    @classmethod
    def factory(cls, data):
        cmd, target_id = struct.unpack("<BB", data)
        return cls(cmd, target_id)

class NmtGfcMessage(NmtMessage):
    def __init__(self):
        super().__init__(NMT_GFC, bytes())

class NmtFlyingMasterResponse(NmtMessage):
    def __init__(self, priority, node_id):
        super().__init__(NMT_FLYING_MASTER_RESPONSE, bytes([priority, node_id]))

    @classmethod
    def factory(cls, data):
        priority, node_id = struct.unpack("<BB", data)
        return cls(priority, node_id)

class NmtFlyingMasterRequest(NmtMessage):
    def __init__(self):
        super().__init__(NMT_FLYING_MASTER_REQUEST, bytes())

class NmtActiveMasterRequest(NmtMessage):
    def __init__(self):
        super().__init__(NMT_ACTIVE_MASTER_REQUEST, bytes())

class NmtMasterResponse(NmtMessage):
    def __init__(self):
        super().__init__(NMT_MASTER_RESPONSE, bytes())

class NmtMasterRequest(NmtMessage):
    def __init__(self):
        super().__init__(NMT_MASTER_REQUEST, bytes())

class NmtForceFlyingMasterRequest(NmtMessage):
    def __init__(self):
        super().__init__(NMT_FORCE_FLYING_MASTER, bytes())

class SyncMessage(Message):
    def __init__(self):
        super().__init__(FUNCTION_CODE_SYNC, 0x00)

class EmcyMessage(Message):
    def __init__(self, emcy_id, eec, er, msef=0):
        data = struct.pack("<HBBI", eec, er, msef & 0xFF, msef >> 8)
        super().__init__(emcy_id >> FUNCTION_CODE_BITNUM, emcy_id & 0x7F, data)

    @classmethod
    def factory(cls, id, data):
        eec, er, msef0, msef1 = struct.unpack("<HBBI", data)
        return cls(id, eec, er, (msef1 << 8) + msef0)

class PdoMessage(Message):
    def __init__(self, fc, node_id, data):
        super().__init__(fc, node_id, data)

class SdoMessage(Message):
    def __init__(self, fc, node_id, cs, n, e, s, index, subindex, data):
        data = struct.pack("<BHBI", (cs << SDO_CS_BITNUM) + (n << SDO_N_BITNUM) + (e << SDO_E_BITNUM) + (s << SDO_S_BITNUM), index, subindex, data)
        super().__init__(fc, node_id, data)

    @property
    def node_id(self):
        return self.arbitration_id & 0x7F

    @property
    def n(self):
        return (self.data[0] >> SDO_N_BITNUM) & (2 ** SDO_N_LENGTH - 1)

    @property
    def e(self):
        return bool(self.data[0] & SDO_E_BITNUM)

    @property
    def s(self):
        return bool(self.data[0] & SDO_S_BITNUM)

    @property
    def index(self):
        return struct.unpack("<H", self.data[1:3])[0]

    @property
    def subindex(self):
        return struct.unpack("<B", self.data[3:4])[0]

    @property
    def sdo_data(self):
        return struct.unpack("<I", self.data[4:])[0]

class SdoRequest(SdoMessage):
    def __init__(self, node_id, cs, n, e, s, index, subindex, data):
        super().__init__(FUNCTION_CODE_SDO_RX, node_id, cs, n, e, s, index, subindex, data)

    @classmethod
    def factory(cls, node_id, data):
        cmd, index, subindex, data = struct.unpack("<BHBI", data.ljust(8, b'\x00'))
        cs = (cmd >> SDO_CS_BITNUM) & (2 ** SDO_CS_LENGTH - 1)
        n = (cmd >> SDO_N_BITNUM) & (2 ** SDO_N_LENGTH - 1)
        e = (cmd >> SDO_E_BITNUM) & 1
        s = (cmd >> SDO_S_BITNUM) & 1
        if cs == SDO_CCS_DOWNLOAD:
            return SdoDownloadRequest(node_id, n, e, s, index, subindex, data)
        if cs == SDO_CCS_UPLOAD:
            return SdoUploadRequest(node_id, index, subindex)
        raise Exception

class SdoResponse(SdoMessage):
    def __init__(self, node_id, cs, n, e, s, index, subindex, data):
        super().__init__(FUNCTION_CODE_SDO_TX, node_id, cs, n, e, s, index, subindex, data)

    @classmethod
    def factory(cls, node_id, data):
        cmd, index, subindex, data = struct.unpack("<BHBI", data.ljust(8, b'\x00'))
        cs = (cmd >> SDO_CS_BITNUM) & (2 ** SDO_CS_LENGTH - 1)
        n = (cmd >> SDO_N_BITNUM) & (2 ** SDO_N_LENGTH - 1)
        e = (cmd >> SDO_E_BITNUM) & 1
        s = (cmd >> SDO_S_BITNUM) & 1
        if cs == SDO_CS_ABORT:
            return SdoAbortResponse(node_id, index, subindex, data)
        if cs == SDO_SCS_DOWNLOAD:
            return SdoDownloadResponse(node_id, index, subindex)
        if cs == SDO_SCS_UPLOAD:
            return SdoUploadResponse(node_id, n, e, s, index, subindex, data)
        raise Exception

class SdoAbortResponse(SdoResponse):
    def __init__(self, node_id, index, subindex, abort_code):
        super().__init__(node_id, SDO_CS_ABORT, 0, 0, 0, index, subindex, abort_code)

class SdoDownloadRequest(SdoRequest):
    def __init__(self, node_id, n, e, s, index, subindex, data):
        super().__init__(node_id, SDO_CCS_DOWNLOAD, n, e, s, index, subindex, data)

class SdoDownloadResponse(SdoResponse):
    def __init__(self, node_id, index, subindex):
        super().__init__(node_id, SDO_SCS_DOWNLOAD, 0, 0, 0, index, subindex, 0)

class SdoUploadRequest(SdoRequest):
    def __init__(self, node_id, index, subindex):
        super().__init__(node_id, SDO_CCS_UPLOAD, 0, 0, 0, index, subindex, 0)

class SdoUploadResponse(SdoResponse):
    def __init__(self, node_id, n, e, s, index, subindex, data):
        super().__init__(node_id, SDO_SCS_UPLOAD, n, e, s, index, subindex, data)

class NmtErrorControlMessage(Message):
    def __init__(self, node_id, data):
        super().__init__(FUNCTION_CODE_NMT_ERROR_CONTROL, node_id, data)

    @classmethod
    def factory(self, node_id, data):
        if data[0] == NMT_STATE_INITIALISATION:
            return BootupMessage(node_id)
        else:
            return HeartbeatMessage(node_id, data[0])

class BootupMessage(NmtErrorControlMessage):
    def __init__(self, node_id):
        super().__init__(node_id, bytearray([NMT_STATE_INITIALISATION]))

class HeartbeatMessage(NmtErrorControlMessage):
    def __init__(self, node_id, nmt_state):
        super().__init__(node_id, bytearray([nmt_state]))

class SdoAbort(Exception):
    def __init__(self, odi, odsi, code):
        self.odi = odi
        self.odsi = odsi
        self.code = code

class SdoTimeout(Exception):
    pass

class Node:
    def __init__(self, bus: CAN.Bus, id, od: ObjectDictionary, *args, **kwargs):
        self.bus = bus
        if id > 0x7F or id <= 0:
            raise ValueError("Invalid Node ID")
        self.id = id
        self._default_od = od

        if "err_indicator" in kwargs:
            if isinstance(kwargs["err_indicator"], ErrorIndicator):
                self._err_indicator = kwargs["err_indicator"]
                self._err_indicator_timer = IntervalTimer(self._err_indicator.interval , self._process_err_indicator)
                self._err_indicator_timer.start()
            else:
                raise TypeError
        else:
            self._err_indicator = None
            self._err_indicator_timer = None

        if "run_indicator" in kwargs:
            if isinstance(kwargs["run_indicator"], RunIndicator):
                self._run_indicator = kwargs["run_indicator"]
            else:
                raise TypeError
        else:
            self._run_indicator = None

        self.nmt_state = NMT_STATE_INITIALISATION
        self._first_boot = True
        self._heartbeat_consumer_timers = {}
        self._heartbeat_producer_timer = None
        self._listener = None
        self._nmt_active_master = False
        self._nmt_active_master_timer = None
        self._nmt_flying_master_timer = None
        self._nmt_multiple_master_timer = None
        self._sync_counter = 0
        self._sync_timer = None
        self._tpdo_triggers = [False, False, False, False]

        self.reset()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._reset_timers()

    def _heartbeat_consumer_timeout(self, id):
        if self.nmt_state != NMT_STATE_STOPPED:
            self._send_emcy(EMCY_HEARTBEAT_BY_NODE + id)

    def _process_err_indicator(self):
        err_state = self.bus.get_state()
        self._err_indicator.set_state(err_state)

    def _process_heartbeat_producer(self):
        heartbeat_producer_time_object = self.od.get(ODI_HEARTBEAT_PRODUCER_TIME)
        if heartbeat_producer_time_object is not None:
            heartbeat_producer_time_value = heartbeat_producer_time_object.get(ODSI_VALUE)
            if heartbeat_producer_time_value is not None and heartbeat_producer_time_value.value is not None:
                heartbeat_producer_time = heartbeat_producer_time_value.value / 1000
            else:
                heartbeat_producer_time = 0
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
            sync_object_value = sync_object.get(ODSI_VALUE)
            if sync_object_value is not None and sync_object_value.value is not None:
                is_sync_producer = (sync_object_value.value & 0x40000000) != 0
            else:
                is_sync_producer = False
        else:
            is_sync_producer = False
        sync_time_object = self.od.get(ODI_SYNC_TIME)
        if sync_time_object is not None:
            sync_time_value = sync_time_object.get(ODSI_VALUE)
            if sync_time_value is not None and sync_time_value.value is not None:
                sync_time = sync_time_value.value / 1000000
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
        if self._err_indicator_timer is not None and self._err_indicator_timer.is_alive():
            self._err_indicator_timer.cancel()
        if self._nmt_active_master_timer is not None and self._nmt_active_master_timer.is_alive():
            self._nmt_active_master_timer.cancel()
        if self._nmt_flying_master_timer is not None and self._nmt_flying_master_timer.is_alive():
            self._nmt_flying_master_timer.cancel()

    def _send(self, msg: CAN.Message):
        return self.bus.send(msg)

    def _send_emcy(self, eec, msef=0):
        emcy_id_obj = self.od.get(ODI_EMCY_ID)
        if emcy_id_obj is None:
            return
        emcy_id_value = emcy_id_obj.get(ODSI_VALUE)
        if emcy_id_value is None:
            return
        if emcy_id_value.value is None:
            return
        er_obj = self.od.get(ODI_ERROR)
        if er_obj is None:
            return
        er_value = er_obj.get(ODSI_VALUE)
        if er_value is None:
            return
        if er_value.value is None:
            return
        msg = EmcyMessage(emcy_id_value.value, eec, er_value.value, msef)
        self._send(msg)

    def _send_heartbeat(self):
        msg = HeartbeatMessage(self.id, self.nmt_state)
        return self._send(msg)

    def _send_pdo(self, i):
        i = i - 1
        data = bytes()
        tpdo_mp = self.od.get(ODI_TPDO1_MAPPING_PARAMETER + i)
        if tpdo_mp is not None:
            tpdo_mp_length = tpdo_mp.get(ODSI_VALUE)
            if tpdo_mp_length is not None and tpdo_mp_length.value is not None:
                for j in range(tpdo_mp_length.value):
                    mapping_param = tpdo_mp.get(j + 1)
                    if mapping_param is not None and mapping_param.value is not None:
                        mapped_object = self.od.get(mapping_param.value >> 16)
                        if mapped_object is not None:
                             mapped_value = mapped_object.get((mapping_param.value >> 8) & 0xFF)
                        else:
                            raise ValueError("Mapped PDO object does not exist")
                        if mapped_value is not None and mapped_value.value is not None:
                            data = data + mapped_value.value.to_bytes((mapping_param.value & 0xFF) // 8, byteorder='little')
                    else:
                        raise ValueError("Mapped PDO object does not exist")
                msg = PdoMessage(FUNCTION_CODE_TPDO1 + (2 * i), self.id, data)
                self._send(msg)
                self._tpdo_triggers[i] = False

    def _send_sync(self):
        sync_object = self.od.get(ODI_SYNC)
        if sync_object is not None:
            sync_value = sync_object.get(ODSI_VALUE)
            if sync_value is not None and sync_value.value is not None:
                sync_id = sync_value.value & 0x3FF
                msg = CAN.Message(sync_id)
                self._send(msg)

    @property
    def is_listening(self):
        return self._is_listening

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

    def _listen(self):
        self._is_listening = True
        while True:
            msg = self.recv()
            self._process_msg(msg)

    def _nmt_startup(self):
        nmt_startup_obj = self.od.get(ODI_NMT_STARTUP)
        if nmt_startup_obj is not None:
            nmt_startup = nmt_startup_obj.get(ODSI_VALUE).value
            if nmt_startup & 0x01: # NMT Master
                if nmt_startup & 0x20: # NMT Flying Master
                    self._nmt_flying_master_startup()
                else:
                    self._nmt_become_active_master()
            elif (nmt_startup & 0x04) == 0: # Self-starting
                    self.nmt_state = NMT_STATE_OPERATIONAL

    def _nmt_flying_master_negotiation_request(self):
        self._send(NmtFlyingMasterRequest())
        self._nmt_flying_master_negotiation()

    def _nmt_flying_master_negotiation_timeout(self):
        nmt_flying_master_timing_params = self.od.get(ODI_NMT_FLYING_MASTER_TIMING_PARAMETERS)
        priority = nmt_flying_master_timing_params.get(ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_PRIORITY).value
        self._send(NmtFlyingMasterResponse(priority, self.id))
        self._nmt_become_active_master()

    def _nmt_flying_master_negotiation(self):
        nmt_flying_master_timing_params = self.od.get(ODI_NMT_FLYING_MASTER_TIMING_PARAMETERS)
        priority = nmt_flying_master_timing_params.get(ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_PRIORITY).value
        priority_time_slot = nmt_flying_master_timing_params.get(ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_PRIORITY_TIME_SLOT).value
        device_time_slot = nmt_flying_master_timing_params.get(ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_DEVICE_TIME_SLOT).value
        flying_master_response_wait_time = priority * priority_time_slot + self.id * device_time_slot
        if self._nmt_flying_master_timer is not None and self._nmt_flying_master_timer.is_alive():
            self._nmt_flying_master_timer.cancel()
        self._nmt_flying_master_timer = Timer(flying_master_response_wait_time / 1000, self._nmt_flying_master_negotiation_timeout)
        self._nmt_flying_master_timer.start()

    def _nmt_compare_flying_master_priority(self, priority):
        nmt_flying_master_timing_params = self.od.get(ODI_NMT_FLYING_MASTER_TIMING_PARAMETERS)
        own_priority = nmt_flying_master_timing_params.get(ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_PRIORITY).value
        if priority <= own_priority:
            self._nmt_become_inactive_master()
        else:
            self._send(NmtForceFlyingMasterRequest())
            self._nmt_flying_master_startup()

    def _nmt_active_master_timeout(self):
        if self._first_boot:
            self._first_boot = False
            self._send(NmtNodeControlMessage(NMT_NODE_CONTROL_RESET_COMMUNICATION, 0))
            self._nmt_flying_master_startup()
        else:
            self._nmt_flying_master_negotiation_request()

    def _nmt_flying_master_startup(self):
        flying_master_params = self.od.get(ODI_NMT_FLYING_MASTER_TIMING_PARAMETERS)
        flying_master_delay = flying_master_params.get(ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_DELAY).value
        sleep(flying_master_delay / 1000)
        self._send(NmtActiveMasterRequest())
        active_nmt_master_timeout_time = flying_master_params.get(ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_TIMEOUT).value
        if self._nmt_active_master_timer is not None and self._nmt_active_master_timer.is_alive():
            self._nmt_active_master_timer.cancel()
        self._nmt_active_master_timer = Timer(active_nmt_master_timeout_time / 1000, self._nmt_active_master_timeout)
        self._nmt_active_master_timer.start()

    def _nmt_become_active_master(self):
        self._nmt_active_master = True
        self._send(NmtNodeControlMessage(NMT_NODE_CONTROL_RESET_COMMUNICATION, 0))
        nmt_startup = self.od.get(ODI_NMT_STARTUP).get(ODSI_VALUE).value
        if (nmt_startup & 0x04) == 0: # Self-starting
            self.nmt_state = NMT_STATE_OPERATIONAL
        if nmt_startup & 0xA:
            self._send(NmtNodeControlMessage(NMT_NODE_CONTROL_START, 0))
        nmt_flying_master_timing_params = self.od.get(ODI_NMT_FLYING_MASTER_TIMING_PARAMETERS)
        nmt_multiple_master_detect_time = nmt_flying_master_timing_params.get(ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_DETECT_TIME).value
        if self._nmt_multiple_master_timer is not None and self._nmt_multiple_master_timer.is_alive():
            self._nmt_multiple_master_timer.cancel()
        self._nmt_multiple_master_timer = IntervalTimer(nmt_multiple_master_detect_time / 1000, self._send, [NmtForceFlyingMasterRequest()])
        self._nmt_multiple_master_timer.start()

    def _nmt_become_inactive_master(self):
        self._nmt_active_master = False
        if self._nmt_multiple_master_timer is not None and self._nmt_multiple_master_timer.is_alive():
            self._nmt_multiple_master_timer.cancel()

    def _boot(self):
        self._send(BootupMessage(self.id))
        self.nmt_state = NMT_STATE_PREOPERATIONAL
        if self._listener is None:
            self._listener = Thread(target=self._listen, daemon=True)
            self._listener.start()
        else:
            self._is_listening = True
        self._process_timers()
        self._nmt_startup()

    def _process_msg(self, msg: Message):
        if not self.is_listening:
            return
        id = msg.arbitration_id
        data = msg.data
        rtr = msg.is_remote_frame
        fc = (id >> FUNCTION_CODE_BITNUM) & 0xF
        if rtr: # CiA recommendeds against using RTRs, but they are still supported
            target_node = id & 0x7F
            if target_node == self.id or target_node == BROADCAST_NODE_ID:
                if self.nmt_state == NMT_STATE_OPERATIONAL:
                    tpdo = None
                    if fc == FUNCTION_CODE_TPDO1:
                        tpdo = 1
                    elif fc == FUNCTION_CODE_TPDO2:
                        tpdo = 2
                    elif fc == FUNCTION_CODE_TPDO3:
                        tpdo = 3
                    elif fc == FUNCTION_CODE_TPDO4:
                        tpdo = 4
                    if tpdo is not None:
                        tpdo_cp = self.od.get(ODI_TPDO1_COMMUNICATION_PARAMETER + tpdo - 1)
                        if tpdo_cp is not None:
                            tpdo_cp_id = tpdo_cp.get(ODSI_TPDO_COMM_PARAM_ID)
                            if tpdo_cp_id is not None and (tpdo_cp_id >> TPDO_COMM_PARAM_ID_VALID_BITNUM) & 1 == 0 and (tpdo_cp_id >> TPDO_COMM_PARAM_ID_RTR_BITNUM) & 1 == 0:
                                tpdo_cp_type = tpdo_cp.get(ODSI_TPDO_COMM_PARAM_TYPE)
                                if tpdo_cp_type == 0xFC:
                                    self._tpdo_triggers[0] = True; # Defer until SYNC event
                                elif tpdo_cp_type == 0xFD:
                                    self._send_pdo(tpdo)
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
            elif command == NMT_FLYING_MASTER_RESPONSE: # Response from either an NmtActiveMasterRequest or NmtFlyingMasterRequest
                compare_priority = False
                if self._nmt_active_master_timer is not None and self._nmt_active_master_timer.is_alive():
                    self._nmt_active_master_timer.cancel()
                    self._first_boot = False
                    compare_priority = True
                if self._nmt_flying_master_timer is not None and self._nmt_flying_master_timer.is_alive():
                    self._nmt_flying_master_timer.cancel()
                    compare_priority = True
                if self._nmt_multiple_master_timer is not None and self._nmt_multiple_master_timer.is_alive():
                    self._nmt_multiple_master_timer.cancel()
                    compare_priority = True
                if compare_priority:
                    self._nmt_compare_flying_master_priority(data[0])
            elif command == NMT_ACTIVE_MASTER_REQUEST:
                if self._nmt_active_master:
                    nmt_flying_master_timing_params = self.od.get(ODI_NMT_FLYING_MASTER_TIMING_PARAMETERS)
                    priority = nmt_flying_master_timing_params.get(ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_PRIORITY).value
                    self._send(NmtFlyingMasterResponse(priority, self.id))
            elif command == NMT_FLYING_MASTER_REQUEST:
                nmt_startup_obj = self.od.get(ODI_NMT_STARTUP)
                if nmt_startup_obj is not None:
                    nmt_startup = nmt_startup_obj.get(ODSI_VALUE).value
                    if nmt_startup & 0x21: # Is NMT Flying Master
                        self._nmt_flying_master_negotiation()
            elif command == NMT_MASTER_REQUEST:
                nmt_startup_obj = self.od.get(ODI_NMT_STARTUP)
                if nmt_startup_obj is not None:
                    nmt_startup = nmt_startup_obj.get(ODSI_VALUE).value
                    if nmt_startup & 0x01: # Is NMT Master
                         self._send(NmtMasterResponse())
            elif command == NMT_FORCE_FLYING_MASTER:
                self._nmt_become_inactive_master()
                self._nmt_flying_master_startup()
        elif fc == FUNCTION_CODE_SYNC and self.nmt_state == NMT_STATE_OPERATIONAL:
            sync_obj = self.od.get(ODI_SYNC)
            if sync_obj is not None:
                sync_obj_value = sync_obj.get(ODSI_VALUE)
                if sync_obj_value is not None and (sync_obj_value.value & 0x3FF) == id:
                    self._sync_counter = (self._sync_counter + 1) % 241
                    for i in range(4):
                        tpdo_cp = self.od.get(ODI_TPDO1_COMMUNICATION_PARAMETER + i)
                        if tpdo_cp is not None:
                            tpdo_cp_id = tpdo_cp.get(ODSI_TPDO_COMM_PARAM_ID)
                            if tpdo_cp_id is not None and tpdo_cp_id.value is not None and (tpdo_cp_id.value >> TPDO_COMM_PARAM_ID_VALID_BITNUM) & 1 == 0:
                                tpdo_cp_type = tpdo_cp.get(ODSI_TPDO_COMM_PARAM_TYPE)
                                if tpdo_cp_type is not None and tpdo_cp_type.value is not None and (((tpdo_cp_type.value == 0 or tpdo_cp_type.value == 0xFC) and self._tpdo_triggers[i]) or (self._sync_counter % tpdo_cp_type.value) == 0):
                                    self._send_pdo(i + 1)
        elif fc == FUNCTION_CODE_SDO_RX and self.nmt_state != NMT_STATE_STOPPED:
            sdo_server_object = self.od.get(ODI_SDO_SERVER)
            if sdo_server_object is not None:
                sdo_server_csid = sdo_server_object.get(ODSI_SDO_SERVER_DEFAULT_CSID)
                if sdo_server_csid is not None and id == sdo_server_csid.value:
                    if len(data) == 8:
                        try:
                            ccs = (data[0] >> SDO_CS_BITNUM) & (2 ** SDO_CS_LENGTH - 1)
                            odi = (data[2] << 8) + data[1]
                            odsi = data[3]
                            if odi in self.od:
                                obj = self.od.get(odi)
                                if odsi in obj:
                                    subobj = obj.get(odsi)
                                    if ccs == SDO_CCS_UPLOAD:
                                        if subobj.access_type == AccessType.WO:
                                            raise SdoAbort(odi, odsi, SDO_ABORT_WO)
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
                                        sdo_data = subobj.value
                                    elif ccs == SDO_CCS_DOWNLOAD:
                                        if subobj.access_type in [AccessType.RO, AccessType.CONST]:
                                            raise SdoAbort(odi, odsi, SDO_ABORT_RO)
                                        scs = SDO_SCS_DOWNLOAD
                                        s = (data[0] >> SDO_S_BITNUM) & 1
                                        e = (data[0] >> SDO_E_BITNUM) & 1
                                        if e == 1 and s == 1:
                                            n = (data[0] >> SDO_N_BITNUM) & (2 ** SDO_N_LENGTH - 1)
                                            subobj.value = int.from_bytes(data[4:8-n], byteorder='little')
                                            obj.update({odsi: subobj})
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
                                            raise NotImplementedError # TODO: Stadard SDO
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
                        data = [(scs << SDO_CS_BITNUM) + (n << SDO_N_BITNUM) + (e << SDO_E_BITNUM), (odi & 0xFF), (odi >> 8), (odsi)] + list(sdo_data)
                        sdo_server_scid = sdo_server_object.get(ODSI_SDO_SERVER_DEFAULT_SCID)
                        if sdo_server_scid is None:
                            raise ValueError("SDO Server SCID not specified")
                        msg = CAN.Message(sdo_server_scid.value, data)
                        self._send(msg)
                        self._process_timers()
        elif fc == FUNCTION_CODE_NMT_ERROR_CONTROL:
            producer_id = id & 0x7F
            if producer_id in self._heartbeat_consumer_timers:
                self._heartbeat_consumer_timers.get(producer_id).cancel()
            heartbeat_consumer_time = 0
            heartbeat_consumer_time_object = self.od.get(ODI_HEARTBEAT_CONSUMER_TIME)
            if heartbeat_consumer_time_object is not None:
                heartbeat_consumer_time_length = heartbeat_consumer_time_object.get(ODSI_VALUE)
                if heartbeat_consumer_time_length is not None and heartbeat_consumer_time_length is not None:
                    for i in range(1, heartbeat_consumer_time_length.value + 1):
                        heartbeat_consumer_time_value = heartbeat_consumer_time_object.get(i)
                        if heartbeat_consumer_time_value is not None and heartbeat_consumer_time_value.value is not None and ((heartbeat_consumer_time_value.value >> 16) & 0x7F) == producer_id:
                            heartbeat_consumer_time = (heartbeat_consumer_time_value.value & 0xFFFF) / 1000
                            break;
            if heartbeat_consumer_time != 0:
                heartbeat_consumer_timer = Timer(heartbeat_consumer_time, self._heartbeat_consumer_timeout, [producer_id])
                heartbeat_consumer_timer.start()
                self._heartbeat_consumer_timers.update({producer_id: heartbeat_consumer_timer})

    def recv(self):
        while True:
            rlist, _, _, = select([self.bus], [], [])
            if len(rlist) > 0:
                return Message.factory(self.bus.recv())

    def reset(self):
        self._is_listening = False
        self.od = self._default_od
        self.reset_communication()

    def reset_communication(self):
        self._reset_timers()
        for odi, object in self._default_od.items():
            if odi >= 0x1000 or odi <= 0x1FFF:
                self.od.update({odi: object})
        self._boot()

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
