import struct

from .constants import *
from . import socketcan


class Message(socketcan.Message):
    def __init__(self, fc, node_id, data=[]):
        arbitration_id = (fc << FUNCTION_CODE_BITNUM) + node_id
        super().__init__(arbitration_id, data)

    @property
    def function_code(self):
        return self.arbitration_id >> FUNCTION_CODE_BITNUM

    @property
    def node_id(self):
        return self.arbitration_id & 0x7F

    @classmethod
    def factory(cls, msg: socketcan.Message):
        fc = (msg.arbitration_id & FUNCTION_CODE_MASK) >> FUNCTION_CODE_BITNUM
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
        if cmd == NMT_MASTER_NODE_ID and len(data) == 2:
            return NmtMasterNodeIdMessage(data[0], data[1])
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


class NmtMasterNodeIdMessage(NmtMessage):
    def __init__(self, priority, node_id):
        super().__init__(NMT_MASTER_NODE_ID, bytes([priority, node_id]))


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
    def __init__(self, fc, node_id, header, sdo_data):
        data = [header] + list(sdo_data)
        super().__init__(fc, node_id, data)

    @property
    def node_id(self):
        return self.arbitration_id & 0x7F

    @property
    def header(self):
        return self.data[0]

    @property
    def sdo_data(self):
        return self.data[1:]


class SdoRequest(SdoMessage):

    def __init__(self, node_id, header, data):
        super().__init__(FUNCTION_CODE_SDO_RX, node_id, header, data)

    @classmethod
    def factory(cls, node_id, data):
        cmd, index, subindex, sdo_data = struct.unpack("<BHBI", data.ljust(8, b'\x00'))
        ccs = (cmd & SDO_CS_MASK) >> SDO_CS_BITNUM
        if ccs == SDO_CCS_DOWNLOAD_INITIATE:
            n = (cmd & SDO_INITIATE_N_MASK) >> SDO_INITIATE_N_BITNUM
            e = (cmd >> SDO_E_BITNUM) & 1
            s = (cmd >> SDO_S_BITNUM) & 1
            return SdoDownloadInitiateRequest(node_id, n, e, s, index, subindex, sdo_data)
        if ccs == SDO_CCS_DOWNLOAD_SEGMENT:
            t = (cmd >> SDO_T_BITNUM) & 1
            n = (cmd & SDO_SEGMENT_N_MASK) >> SDO_SEGMENT_N_BITNUM
            c = (cmd >> SDO_C_BITNUM) & 1
            data = data[1:8]
            return SdoDownloadSegmentRequest(node_id, t, n, c, data)
        if ccs == SDO_CCS_UPLOAD_INITIATE:
            n = (cmd & SDO_INITIATE_N_MASK) >> SDO_INITIATE_N_BITNUM
            e = (cmd >> SDO_E_BITNUM) & 1
            s = (cmd >> SDO_S_BITNUM) & 1
            return SdoUploadInitiateRequest(node_id, index, subindex)
        if ccs == SDO_CCS_UPLOAD_SEGMENT:
            t = (cmd >> SDO_T_BITNUM) & 1
            return SdoUploadSegmentRequest(node_id, t)
        raise Exception


class SdoResponse(SdoMessage):

    def __init__(self, node_id, header, data):
        super().__init__(FUNCTION_CODE_SDO_TX, node_id, header, data)

    @classmethod
    def factory(cls, node_id, data):
        cmd, index, subindex, data = struct.unpack("<BHBI", data.ljust(8, b'\x00'))
        cs = (cmd & SDO_CS_MASK) >> SDO_CS_BITNUM
        if cs == SDO_CS_ABORT:
            return SdoAbortResponse(node_id, index, subindex, data)
        if cs == SDO_SCS_DOWNLOAD_INITIATE:
            n = (cmd & SDO_INITIATE_N_MASK) >> SDO_INITIATE_N_BITNUM
            e = (cmd >> SDO_E_BITNUM) & 1
            s = (cmd >> SDO_S_BITNUM) & 1
            return SdoDownloadInitiateResponse(node_id, index, subindex)
        if cs == SDO_SCS_DOWNLOAD_SEGMENT:
            t = (cmd >> SDO_T_BITNUM) & 1
            return SdoDownloadSegmentResponse(node_id, t)
        if cs == SDO_SCS_UPLOAD_INITIATE:
            n = (cmd & SDO_INITIATE_N_MASK) >> SDO_INITIATE_N_BITNUM
            e = (cmd >> SDO_E_BITNUM) & 1
            s = (cmd >> SDO_S_BITNUM) & 1
            return SdoUploadInitiateResponse(node_id, n, e, s, index, subindex, data)
        if cs == SDO_SCS_UPLOAD_SEGMENT:
            t = (cmd >> SDO_T_BITNUM) & 1
            n = (cmd & SDO_SEGMENT_N_MASK) >> SDO_SEGMENT_N_BITNUM
            c = (cmd >> SDO_C_BITNUM) & 1
            data = data[1:8]
            return SdoUploadSegmentResponse(node_id, t, n, c, data)
        raise Exception


class SdoAbortResponse(SdoResponse):
    def __init__(self, node_id, index, subindex, abort_code):
        header = SDO_CS_ABORT << SDO_CS_BITNUM
        sdo_data = struct.pack("<HBI", index, subindex, abort_code)
        super().__init__(node_id, header, sdo_data)


class SdoDownloadInitiateRequest(SdoRequest):
    def __init__(self, node_id, n, e, s, index, subindex, data):
        header = (SDO_CCS_DOWNLOAD_INITIATE << SDO_CS_BITNUM) + (n << SDO_INITIATE_N_BITNUM) + (e << SDO_E_BITNUM) + (s << SDO_S_BITNUM)
        sdo_data = struct.pack("<HB", index, subindex) + data
        super().__init__(node_id, header, sdo_data)


class SdoDownloadSegmentRequest(SdoRequest):
    def __init__(self, node_id, t, n, c, data):
        header = (SDO_CCS_DOWNLOAD_SEGMENT << SDO_CS_BITNUM) + (t << SDO_T_BITNUM) + (n << SDO_SEGMENT_N_BITNUM) + (c << SDO_C_BITNUM)
        super().__init__(node_id, header, data)


class SdoDownloadInitiateResponse(SdoResponse):
    def __init__(self, node_id, index, subindex):
        header = SDO_SCS_DOWNLOAD_INITIATE << SDO_CS_BITNUM
        sdo_data = struct.pack("<HBI", index, subindex, 0)
        super().__init__(node_id, header, sdo_data)


class SdoDownloadSegmentResponse(SdoResponse):
    def __init__(self, node_id, t):
        header = (SDO_SCS_DOWNLOAD_SEGMENT << SDO_CS_BITNUM) + (t << SDO_T_BITNUM)
        super().__init__(node_id, header, bytes(7))


class SdoUploadInitiateRequest(SdoRequest):
    def __init__(self, node_id, index, subindex):
        header = SDO_CCS_UPLOAD_INITIATE << SDO_CS_BITNUM
        sdo_data = struct.pack("<HBI", index, subindex, 0)
        super().__init__(node_id, header, sdo_data)


class SdoUploadInitiateResponse(SdoResponse):
    def __init__(self, node_id, n, e, s, index, subindex, data):
        header = (SDO_SCS_UPLOAD_INITIATE << SDO_CS_BITNUM) + (n << SDO_INITIATE_N_BITNUM) + (e << SDO_E_BITNUM) + (s << SDO_S_BITNUM)
        sdo_data = struct.pack("<HB", index, subindex) + data
        super().__init__(node_id, SDO_SCS_UPLOAD_INITIATE, n, e, s, index, subindex, data)


class SdoUploadSegmentRequest(SdoRequest):
    def __init__(self, node_id, t):
        header = (SDO_CCS_UPLOAD_SEGMENT << SDO_CS_BITNUM) + (t << SDO_T_BITNUM)
        super().__init__(node_id, header, bytes(7))


class SdoUploadSegmentResponse(SdoResponse):
    def __init__(self, node_id, t, n, c, data):
        header = (SDO_SCS_UPLOAD_SEGMENT << SDO_CS_BITNUM) + (t << SDO_T_BITNUM) + (n << SDO_SEGMENT_N_BITNUM) + (c << SDO_C_BITNUM)
        super().__init__(node_id, header, data)


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
