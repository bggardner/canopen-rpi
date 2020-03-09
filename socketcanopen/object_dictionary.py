from collections import Mapping, MutableMapping
from configparser import ConfigParser
from datetime import datetime, timedelta
from enum import Enum, IntEnum, unique
import struct

from .constants import *


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
                parameter_name="UNSIGNED16",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000010
            ),
            ODI_DATA_TYPE_UNSIGNED32: Object(
                parameter_name="UNSIGNED32",
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
                default_value=0x00000000
            ),
            ODI_DATA_TYPE_OCTET_STRING: Object(
                parameter_name="OCTET_STRING",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000000
            ),
            ODI_DATA_TYPE_UNICODE_STRING: Object(
                parameter_name="UNICODE_STRING",
                object_type=ObjectType.DEFTYPE,
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                default_value=0x00000000
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
        return self._store[index]

    def __setitem__(self, index, obj):
        if type(index) is not int:
            raise TypeError("CANopen object dictionary index must be an integer")
        if index < 0 or index >= 2 ** 16:
            raise IndexError("CANopen object dictionary index must be a positive 16-bit integer")
        if not isinstance(obj, Object):
            raise TypeError("CANopen object dictionary can only consist of CANopen Objects")
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

    @classmethod
    def from_eds(cls, filename, node_id=None):
        # TODO: Support CompactSubObj directive
        eds = ConfigParser()
        eds.read(filename)
        if node_id is None:
            node_id = int(eds['DeviceCommissioning']['NodeID'], 0)
        indices = []
        for section in ['MandatoryObjects', 'OptionalObjects', 'ManufacturerObjects']:
            if not eds.has_section(section):
                continue
            n = ProtoObject._int_from_config_str(eds[section]['SupportedObjects'])
            for i in range(1, n + 1):
                indices.append(ProtoObject._int_from_config_str(eds[section][str(i)]))
        od = cls()
        for i in indices:
            oc = eds["{:4X}".format(i)]
            sub_number = ProtoObject._int_from_config_str(oc.get('SubNumber', '0'))
            subs = {}
            si = 0
            while len(subs) <= sub_number and si <= 0xFF:
                key = "{:4X}sub{:d}".format(i, si)
                if key in eds:
                    sub = SubObject.from_config(eds[key], node_id)
                    subs.update({si: sub})
                si += 1
            # TODO Check for mandatory properties based on Object.ObjectType
            # TODO: Assign proper data type to subs if Object.object_type in [ObjectType.DEFSTRUCT, ObjectType.ARRAY, ObjectType.RECORD]
            o = Object.from_config(oc, node_id, subs)
            od.update({i: o})
        return od


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
        super().__setitem__(name, value)

    def update(self, other=None, **kwargs):
        if other is not None:
            for subindex, value in other.items() if isinstance(other, Mapping) else other:
                self[subindex] = value
            for subindex, value in kwargs.items():
                self[subindex] = value

    @staticmethod
    def from_config(cfg, node_id):
        parameter_name = cfg['ParameterName']
        if 'ObjectType' in cfg:
            object_type = ObjectType(ProtoObject._int_from_config_str(cfg['ObjectType']))
        else:
            object_type = None
        if 'DataType' in cfg:
            data_type = ProtoObject._int_from_config_str(cfg['DataType'])
        else:
            data_type = None
        if 'AccessType' in cfg:
            access_type = AccessType(cfg['AccessType'])
        else:
            access_type = None
        if 'DefaultValue' in cfg:
            default_value = ProtoObject._value_from_config_str(cfg['DefaultValue'], data_type, node_id)
        else:
            default_value = None
        if 'PDOMapping' in cfg:
            pdo_mapping = bool(cfg['PDOMapping'])
        else:
            pdo_mapping = None
        if 'LowLimit' in cfg:
            low_limit = ProtoObject._value_from_config_str(cfg['LowLimit'], data_type, node_id)
        else:
            low_limit = None
        if 'HighLimit' in cfg:
            high_limit = ProtoObject._value_from_config_str(cfg['HighLimit'], data_type, node_id)
        else:
            high_limit = None
        return ProtoObject(
            parameter_name=parameter_name,
            object_type=object_type,
            data_type=data_type,
            access_type=access_type,
            default_value=default_value,
            pdo_mapping=pdo_mapping,
            low_limit=low_limit,
            high_limit=high_limit
        )

    @staticmethod
    def _int_from_config_str(s):
        try:
            return int(s, 0)
        except:
            pass
        if s[0] == '0' or s[0:2] == '-0':
            try:
                return int(s, 8) # Try octal
            except:
                pass
        raise ValueError('Invalid integer format')

    @staticmethod
    def _value_from_config_str(s, data_type=None, node_id=0):
        if data_type == ODI_DATA_TYPE_BOOLEAN:
            value = bool(ProtoObject._int_from_config_str(s))
        elif data_type in [
            ODI_DATA_TYPE_INTEGER8,
            ODI_DATA_TYPE_INTEGER16,
            ODI_DATA_TYPE_INTEGER24,
            ODI_DATA_TYPE_INTEGER32,
            ODI_DATA_TYPE_INTEGER40,
            ODI_DATA_TYPE_INTEGER48,
            ODI_DATA_TYPE_INTEGER56,
            ODI_DATA_TYPE_INTEGER64,
            ODI_DATA_TYPE_UNSIGNED8,
            ODI_DATA_TYPE_UNSIGNED16,
            ODI_DATA_TYPE_UNSIGNED24,
            ODI_DATA_TYPE_UNSIGNED32,
            ODI_DATA_TYPE_UNSIGNED40,
            ODI_DATA_TYPE_UNSIGNED48,
            ODI_DATA_TYPE_UNSIGNED56,
            ODI_DATA_TYPE_UNSIGNED64
            ]:
            value = 0
            if s[0:8].casefold() == '$NODEID+'.casefold():
                value = node_id
                s = s[8:]
            if s[0:8].casefold() == '$NODEID*'.casefold(): # Technically not allowed in EDS; hack for CiA302-2
                try:
                    multiplier = ProtoObject._int_from_config_str(s[8:])
                except:
                    multiplier, s = s[8:].split('+', 2)
                    multiplier = ProtoObject._int_from_config_str(multiplier)
                value = node_id * multiplier
            value += ProtoObject._int_from_config_str(s)
        elif data_type in [ODI_DATA_TYPE_REAL32, ODI_DATA_TYPE_REAL64]:
            value = float(s)
        elif data_type in [ODI_DATA_TYPE_VISIBLE_STRING, ODI_DATA_TYPE_UNICODE_STRING]:
            value = s
        elif data_type == ODI_DATA_TYPE_TIME_OF_DAY:
            raise NotImplementedError
        elif data_type == ODI_DATA_TYPE_TIME_DIFFERENCE:
            raise NotImplementedError
        elif data_type in [ODI_DATA_TYPE_OCTET_STRING, ODI_DATA_TYPE_DOMAIN]:
             value = bytes.fromhex(s)
        else:
            # Without explicit data type, probably is integer, float, otherwise default to string
            try:
                value = ProtoObject._int_from_config_str(s)
            except ValueError:
                try:
                    value = float(s)
                except ValueError:
                    value = s
        return value


class SubObject(ProtoObject):
    def __init__(self, **kwargs):
        #kwargs["object_type"] = ObjectType.VAR
        super().__init__(**kwargs)
        self.value = self.default_value

    def __bytes__(self):
        if self.data_type == ODI_DATA_TYPE_BOOLEAN:
            return bytes([bool(self.value)])
        if isinstance(self.value, int):
            if self.data_type == ODI_DATA_TYPE_INTEGER8:
                return self.value.to_bytes(1, byteorder='little', signed=True)
            if self.data_type == ODI_DATA_TYPE_INTEGER16:
                return self.value.to_bytes(2, byteorder='little', signed=True)
            if self.data_type == ODI_DATA_TYPE_INTEGER24:
                return self.value.to_bytes(3, byteorder='little', signed=True)
            if self.data_type == ODI_DATA_TYPE_INTEGER32:
                return self.value.to_bytes(4, byteorder='little', signed=True)
            if self.data_type == ODI_DATA_TYPE_INTEGER40:
                return self.value.to_bytes(5, byteorder='little', signed=True)
            if self.data_type == ODI_DATA_TYPE_INTEGER48:
                return self.value.to_bytes(6, byteorder='little', signed=True)
            if self.data_type == ODI_DATA_TYPE_INTEGER56:
                return self.value.to_bytes(7, byteorder='little', signed=True)
            if self.data_type == ODI_DATA_TYPE_INTEGER64:
                return self.value.to_bytes(8, byteorder='little', signed=True)
            if self.data_type == ODI_DATA_TYPE_UNSIGNED8:
                return self.value.to_bytes(1, byteorder='little')
            if self.data_type == ODI_DATA_TYPE_UNSIGNED16:
                return self.value.to_bytes(2, byteorder='little')
            if self.data_type == ODI_DATA_TYPE_UNSIGNED24:
                return self.value.to_bytes(3, byteorder='little')
            if self.data_type == ODI_DATA_TYPE_UNSIGNED32:
                return self.value.to_bytes(4, byteorder='little')
            if self.data_type == ODI_DATA_TYPE_UNSIGNED40:
                return self.value.to_bytes(5, byteorder='little')
            if self.data_type == ODI_DATA_TYPE_UNSIGNED48:
                return self.value.to_bytes(6, byteorder='little')
            if self.data_type == ODI_DATA_TYPE_UNSIGNED56:
                return self.value.to_bytes(7, byteorder='little')
            if self.data_type == ODI_DATA_TYPE_UNSIGNED64:
                return self.value.to_bytes(8, byteorder='little')
        if isinstance(self.value, float):
            if self.data_type == ODI_DATA_TYPE_REAL32:
              return struct.pack("<f", self.value)
            if self.data_type == ODI_DATA_TYPE_REAL64:
              return struct.pack("<d", self.value)
        if isinstance(self.value, str):
            if self.data_type == ODI_DATA_TYPE_VISIBLE_STRING:
                return bytes(self.value, 'ascii') # CANopen Visible String encoding is ISO 646-1974 (ASCII)
            if self.data_type == ODI_DATA_TYPE_UNICODE_STRING:
                return bytes(self.value, 'utf_16') # CANopen Unicode Strings are arrays of UNSIGNED16, assuming UTF-16
        if isinstance(self.value, datetime):
            td = self.value - datetime(1984, 1, 1)
            return struct.pack("<IH", int(td.seconds * 1000 + td.microseconds / 1000) << 4, td.days)
        if isinstance(self.value, timedelta):
            return struct.pack("<IH", int(self.value.seconds * 1000 + self.value.microseconds / 1000) << 4, self.value.days)
        return bytes(self.value) # Try casting if nothing else worked; custom data types should implement __bytes__()

    def from_bytes(self, b):
        if self.data_type == ODI_DATA_TYPE_BOOLEAN:
            return bool(b[0])
        if self.data_type in [
            ODI_DATA_TYPE_INTEGER8,
            ODI_DATA_TYPE_INTEGER16,
            ODI_DATA_TYPE_INTEGER24,
            ODI_DATA_TYPE_INTEGER32,
            ODI_DATA_TYPE_INTEGER40,
            ODI_DATA_TYPE_INTEGER48,
            ODI_DATA_TYPE_INTEGER56,
            ODI_DATA_TYPE_INTEGER64
            ]:
            return int.from_bytes(b, byteorder='little', signed=True)
        if self.data_type in [
            ODI_DATA_TYPE_UNSIGNED8,
            ODI_DATA_TYPE_UNSIGNED16,
            ODI_DATA_TYPE_UNSIGNED24,
            ODI_DATA_TYPE_UNSIGNED32,
            ODI_DATA_TYPE_UNSIGNED40,
            ODI_DATA_TYPE_UNSIGNED48,
            ODI_DATA_TYPE_UNSIGNED56,
            ODI_DATA_TYPE_UNSIGNED64
            ]:
            return int.from_bytes(b, byteorder='little')
        if self.data_type == ODI_DATA_TYPE_REAL32:
            return struct.unpack("<f", b)
        if self.data_type == ODI_DATA_TYPE_REAL64:
            return struct.unpack("<d", b)
        if self.data_type == ODI_DATA_TYPE_VISIBLE_STRING:
            return bytes(b).decode('ascii')
        if self.data_type == ODI_DATA_TYPE_UNICODE_STRING:
            return bytes(b).decode('utf_16')
        if self.data_type == ODI_DATA_TYPE_TIME_OF_DAY:
            ms, d = struct.unpack("<IH", bytes(b))
            ms = ms >> 4
            td = timedelta(days=d, milliseconds=ms)
            return datetime(1980, 1, 1) + td
        if self.data_type == ODI_DATA_TYPE_TIME_DIFFERENCE:
            ms, d = struct.unpack("<IH", bytes(b))
            ms = ms >> 4
            return timedelta(days=d, milliseconds=ms)
        return b # ODI_DATA_TYPE_OCTET_STRING or ODI_DATA_TYPE_DOMAIN

    def __setitem__(self, name, value):
        if name == "value" and type(value) not in [bool, int, float, str, bytes, bytearray, datetime, timedelta]: # TODO: Somehow support DOMAIN data type
            raise TypeError("CANopen objects can only be set to one of bool, int, float, str, bytes, bytearray, datetime, or timedelta")
        super().__setattr__(name,  value)

    @classmethod
    def from_config(cls, cfg, node_id):
        po = super().from_config(cfg, node_id)
        so = cls(
            parameter_name=po.parameter_name,
            object_type=po.object_type,
            data_type=po.data_type,
            access_type=po.access_type,
            default_value=po.default_value,
            pdo_mapping=po.pdo_mapping,
            low_limit=po.low_limit,
            high_limit=po.high_limit
        )
        if 'ParameterValue' in cfg:
            so.value = ProtoObject._value_from_config_str(cfg['ParameterValue'])
        else:
            so.value = po.default_value
        return so


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
            default_value=(self.data_type << OD_STRUCTURE_DATA_TYPE_BITNUM) + self.object_type
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
        if subindex == "value":
            subindex = ODSI_VALUE
            value = sub_object
            sub_object = self.get(subindex)
            sub_object.value = value
        if type(subindex) is not int:
            raise TypeError("CANopen object sub-index must be an integer")
        if subindex < 0 or subindex >= 2 ** 8:
            raise IndexError("CANopen object sub-index must be a positive 8-bit integer")
        if type(sub_object) is not SubObject:
            raise TypeError("Must be a SubObject")
        self._store[subindex] = sub_object

    @classmethod
    def from_config(cls, cfg, node_id, subs):
        po = super().from_config(cfg, node_id)
        o = cls(
            parameter_name=po.parameter_name,
            object_type=po.object_type,
            data_type=po.data_type,
            access_type=po.access_type,
            default_value=po.default_value,
            pdo_mapping=po.pdo_mapping,
            sub_number=cls._int_from_config_str(cfg.get('SubNumber', '0')),
            subs=subs
        )
        if 'ParameterValue' in cfg:
            o.value = ProtoObject._value_from_config_str(cfg['ParameterValue'])
        else:
            o.value = po.default_value
        return o
