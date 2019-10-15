class WebSocketCanOpen extends WebSocketCan {
  messageHandler(handler) {
    return function(event) {
      let init = Object.assign({}, event);
      init.data = CanOpenMessage.from(new Uint8Array(event.data));
      handler(new MessageEvent(event.type, init));
    }
  }
}

class CanOpenMessage extends CanMessage {
  constructor(functionCode, nodeId, data=[]) {
    super((functionCode << 7) + nodeId, data, false, false, false);
  }

  static get FUNCTION_CODE_NMT() { return 0x0; }
  static get FUNCTION_CODE_SYNC() { return 0x1; }
  static get FUNCTION_CODE_EMCY() { return 0x1; }
  static get FUNCTION_CODE_TIME_STAMP() { return 0x2; }
  static get FUNCTION_CODE_TPDO1() { return 0x3; }
  static get FUNCTION_CODE_RPDO1() { return 0x4; }
  static get FUNCTION_CODE_TPDO2() { return 0x5; }
  static get FUNCTION_CODE_RPDO2() { return 0x6; }
  static get FUNCTION_CODE_TPDO3() { return 0x7; }
  static get FUNCTION_CODE_RPDO3() { return 0x8; }
  static get FUNCTION_CODE_TPDO4() { return 0x9; }
  static get FUNCTION_CODE_RPDO4() { return 0xA; }
  static get FUNCTION_CODE_SDO_TX() { return 0xB; }
  static get FUNCTION_CODE_SDO_RX() { return 0xC; }
  static get FUNCTION_CODE_NMT_ERROR_CONTROL() { return 0xE; }

  get functionCode() {
    return this.arbitrationId >> 7;
  }

  set functionCode(fc) {
    this.arbitrationId = ((fc & 0xF) << 7) + this.nodeId;
  }

  get nodeId() {
    return this.arbitrationId & 0x7F;
  }

  set nodeId(id) {
    this.arbitrationId = (this.functionCode << 7) + (id & 0x7F);
  }

  static from(byteArray) { // Factory from SocketCAN-formatted byte array
      let nodeId = byteArray[0] & 0x7F;
      let functionCode = byteArray[0] >> 7;
      functionCode += (byteArray[1] & 0x7) << 1;
      let dlc = byteArray[4];
      let data = byteArray.slice(8, 8 + dlc);
      return new this(functionCode, nodeId, data);
  }
}

class CanOpenNmtErrorControlMessage extends CanOpenMessage {
  constructor(nodeId, data) {
    super(CanOpenMessage.FUNCTION_CODE_NMT_ERROR_CONTROL, nodeId, data);
  }
}

class CanOpenBootupMessage extends CanOpenNmtErrorControlMessage {
  constructor(nodeId) {
    super(nodeId, [0]);
  }
}

class CanOpenHeartbeatMessage extends CanOpenNmtErrorControlMessage {
  constructor(nodeId, nmtState) {
    super(nodeId, [nmtState]);
  }
}

class CanOpenSdoMessage extends CanOpenMessage {
  constructor(functionCode, nodeId, sdoHeader, sdoData) {
    sdoData.unshift(sdoHeader);
    super(functionCode, nodeId, new Uint8Array(sdoData));
  }

  // Bit positions and masks
  static get CS_BITNUM() { return 5; }

  // Command specifiers
  static get CCS_DOWNLOAD_SEGMENT() { return 0; }
  static get CCS_DOWNLOAD_INITIATE() { return 1; }
  static get CCS_UPLOAD_INITIATE() { return 2; }
  static get CCS_UPLOAD_SEGMENT() { return 3; }
  static get CS_ABORT() { return 4; }
  static get SCS_UPLOAD_SEGMENT() { return 0; }
  static get SCS_DOWNLOAD_SEGMENT() { return 1; }
  static get SCS_UPLOAD_INITIATE() { return 2; }
  static get SCS_DOWNLOAD_INITIATE() { return 3; }

  // Derived properties
  get cs() { return (this.data[0] >> CanOpenSdoMessage.CS_BITNUM) & 0x7; }
}

const CanOpenSdoInitiateMixIn = superclass => class extends superclass {
  static get S_BITNUM() { return 0; }
  static get E_BITNUM() { return 1; }
  static get N_BITNUM() { return 2; }
  static get N_MASK() { return 0xC; }
  get s() { return (this.data[0] >> this.S_BITNUM) & 0x1; }
  get e() { return (this.data[0] >> this.E_BITNUM) & 0x1; }
  get n() { return (this.data[0] >> this.N_BITNUM) & 0x3; }
  get index() { return (this.data[2] << 8) + this.data[1]; }
  get subIndex() { return this.data[3]; }
};

const CanOpenSdoSegmentMixIn = superclass => class extends superclass {
  static get T_BITNUM() { return 4; }
  static get N_BITNUM() { return 1; }
  static get N_MASK() { return 0xE; }
  static get C_BITNUM() { return 0; }
  get t() { return (this.data[0] >> this.T_BITNUM) & 0x1; }
  get n() { return (this.data[0] >> this.N_BITNUM) & 0x7; }
  get c() { return (this.data[0] >> this.C_BITNUM) & 0x1; }
};

class CanOpenSdoRequest extends CanOpenSdoMessage {
  constructor(nodeId, sdoHeader, sdoData) {
    super(CanOpenMessage.FUNCTION_CODE_SDO_RX, nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoResponse extends CanOpenSdoMessage {
  constructor(nodeId, sdoHeader, sdoData) {
    super(CanOpenMessage.FUNCTION_CODE_SDO_TX, nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoAbortResponse extends CanOpenSdoResponse {

  // Abort codes
  static get ABORT_INVALID_CS() { return 0x05040001; }
  static get ABORT_WO() { return 0x06010001; }
  static get ABORT_RO() { return 0x06010002; }
  static get ABORT_OBJECT_DNE() { return 0x06020000; }
  static get ABORT_SUBINDEX_DNE() { return 0x06090011; }
  static get ABORT_GENERAL() { return 0x08000000; }
  
  constructor(nodeId, index, subIndex, abortCode) {
    let sdoHeader = CanOpenSdoMessage.CS_ABORT << CanOpenSdoMessage.CS_BITNUM;
    let sdoData = [index & 0xFF, index >> 8, subIndex];
    sdoData.push((abortCode >> 0) & 0xFF);
    sdoData.push((abortCode >> 8) & 0xFF);
    sdoData.push((abortCode >> 16) & 0xFF);
    sdoData.push((abortCode >> 24) & 0xFF);
    super(nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoDownloadInitiateRequest extends CanOpenSdoInitiateMixIn(CanOpenSdoRequest) {
  constructor(nodeId, n, e, s, index, subIndex, data) {
    let sdoHeader = CanOpenSdoMessage.CCS_DOWNLOAD_INITIATE << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += n << CanOpenSdoInitiateMixIn(CanOpenSdoRequest).N_BITNUM;
    sdoHeader += e << CanOpenSdoInitiateMixIn(CanOpenSdoRequest).E_BITNUM;
    sdoHeader += s << CanOpenSdoInitiateMixIn(CanOpenSdoRequest).S_BITNUM;
    let sdoData = [index & 0xFF, index >> 8, subIndex];
    sdoData.push((data >> 0) & 0xFF);
    sdoData.push((data >> 8) & 0xFF);
    sdoData.push((data >> 16) & 0xFF);
    sdoData.push((data >> 24) & 0xFF);
    super(nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoDownloadInitiateResponse extends CanOpenSdoInitiateMixIn(CanOpenSdoResponse) {
  constructor(nodeId, index, subIndex) {
    let sdoHeader = CanOpenSdoMessage.SCS_DOWNLOAD_INITIATE << CanOpenSdoMessage.CS_BITNUM;
    let sdoData = [index & 0xFF, index >> 8, subIndex, 0, 0, 0, 0];
    super(nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoUploadInitiateRequest extends CanOpenSdoInitiateMixIn(CanOpenSdoRequest) {
  constructor(nodeId, index, subIndex) {
    let sdoHeader = CanOpenSdoMessage.CCS_UPLOAD_INITIATE << CanOpenSdoMessage.CS_BITNUM;
    let sdoData = [index & 0xFF, index >> 8, subIndex, 0 ,0 ,0 ,0];
    super(nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoUploadInitiateResponse extends CanOpenSdoInitiateMixIn(CanOpenSdoResponse) {
  constructor(nodeId, n, e, s, index, subIndex, data) {
    let sdoHeader = CanOpenSdoMessage.SCS_UPLOAD_INITIATE << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += n << CanOpenSdoInitiateMixIn(CanOpenSdoRequest).N_BITNUM;
    sdoHeader += e << CanOpenSdoInitiateMixIn(CanOpenSdoRequest).E_BITNUM;
    sdoHeader += s << CanOpenSdoInitiateMixIn(CanOpenSdoRequest).S_BITNUM;
    let sdoData = [index & 0xFF, index >> 8, subIndex];
    sdoData.push((data >> 0) & 0xFF);
    sdoData.push((data >> 8) & 0xFF);
    sdoData.push((data >> 16) & 0xFF);
    sdoData.push((data >> 24) & 0xFF);
    super(nodeId, sdoHeader, sdoData);
  }
}

class CanOpenObject extends Object {
  static get ACCESS_TYPE_RO() { return "ro"; }
  static get ACCESS_TYPE_WO() { return "wo"; }
  static get ACCESS_TYPE_RW() { return "rw"; }
  static get ACCESS_TYPE_RWR() { return "rwr"; }
  static get ACCESS_TYPE_RWW() { return "rww"; }
  static get ACCESS_TYPE_CONST() { return "const"; }
}

class CanOpenSubObject extends CanOpenObject {

}

class CanOpenNode {
  constructor(id, od, ws) {
    this.id = id;
    this.default_od = od;
    this.ws = ws;
    this.nmtState = CanOpenNode.NMT_STATE_INITIALISATION;
    let node = this;
    this.ws.addEventListener("message", function(e) { node.recv(e.data); });
    this.reset()
  }

  get NMT_STATE_INITIALISATION() { return 0x00; }
  get NMT_STATE_STOPPED() { return 0x04; }
  get NMT_STATE_OPERATIONAL() { return 0x05; }
  get NMT_STATE_PREOPERATIONAL() { return 0x7F; }

  boot() {
    this.ws.send(new CanOpenBootupMessage(this.id));
    this.nmtState = this.NMT_STATE_PREOPERATIONAL;
    let node = this;
    this.heartbeatTimer = setInterval(function() { node.send_heartbeat(); }, 1000); // TODO: Lookup period
  }

  recv(msg) {
    switch (msg.functionCode) {
      case CanOpenMessage.FUNCTION_CODE_SDO_RX:
        if (msg.nodeId != this.id) { return; }
        msg = CanOpenSdoMessage.from(new Uint8Array(msg));
        switch (msg.cs) {
          case CanOpenSdoMessage.CCS_DOWNLOAD:
            if ((this.od instanceof Object) && (msg.index in this.od)) {
              let obj = this.od[msg.index];
              if ((obj instanceof Object) && (msg.subIndex in obj)) {
                let subObj = obj[msg.subIndex];
                if (subObj instanceof CanOpenSubObject) {
                  if (subObject.accessType == CanOpenObject.ACCESS_TYPE_RO) {
                    this.send(new CanOpenAbortResponse(this.id, msg.index, msg.subIndex, CanOpenSdoMessage.ABORT_RO));
                  } else {
                    subObj.value = msg.data;
                    this.send(new CanOpenSdoDownloadResponse(this.id, msg.index, msg.subIndex));
                  }
                } else {
                  this.send(new CanOpenAbortResponse(this.id, msg.index, msg.subIndex, CanOpenSdoMessage.ABORT_SUBINDEX_DNE));
                }
              } else {
                this.send(new CanOpenAbortResponse(this.id, msg.index, msg.subIndex, CanOpenSdoMessage.ABORT_SUBINDEX_DNE));
              }
            } else {
              this.send(new CanOpenAbortResponse(this.id, msg.index, msg.subIndex, CanOpenSdoMessage.ABORT_OBJECT_DNE));
            }
            break;
      case CanOpenMessage.FUNCTION_CODE_SDO_RX:
        if (msg.nodeId != this.id) { return; }
        msg = CanOpenSdoMessage.from(new Uint8Array(msg));
        switch (msg.cs) {
          case CanOpenSdoMessage.CCS_DOWNLOAD:
            if ((this.od instanceof Object) && (msg.index in this.od)) {
              let obj = this.od[msg.index];
              if ((obj instanceof Object) && (msg.subIndex in obj)) {
                let subObj = obj[msg.subIndex];
                if (subObj instanceof CanOpenSubObject) {
                  if ((subObj.accessType == CanOpenObject.ACCESS_TYPE_CONST) || (subObj.accessType == CanOpenObject.ACCESS_TYPE_RO)) {
                    this.send(new CanOpenAbortResponse(this.id, msg.index, msg.subIndex, CanOpenSdoMessage.ABORT_RO));
                  } else {
                    subObj.value = msg.data;
                    this.send(new CanOpenSdoDownloadResponse(this.id, msg.index, msg.subIndex));
                  }
                } else {
                  this.send(new CanOpenAbortResponse(this.id, msg.index, msg.subIndex, CanOpenSdoMessage.ABORT_SUBINDEX_DNE));
                }
              } else {
                this.send(new CanOpenAbortResponse(this.id, msg.index, msg.subIndex, CanOpenSdoMessage.ABORT_SUBINDEX_DNE));
              }
            } else {
              this.send(new CanOpenAbortResponse(this.id, msg.index, msg.subIndex, CanOpenSdoMessage.ABORT_OBJECT_DNE));
            }
            break;
          case CanOpenSdoMessage.CCS_UPLOAD:
            if ((this.od instanceof Object) && (msg.index in this.od)) {
              let obj = this.od[msg.index];
              if ((obj instanceof Object) && (msg.subIndex in obj)) {
                let subObj = obj[msg.subIndex];
                if (subObj instanceof CanOpenSubObject) {
                  if (subObj.accessType == CanOpenObject.ACCESS_TYPE_WO) {
                    this.send(new CanOpenAbortResponse(this.id, msg.index, msg.subIndex, CanOpenSdoMessage.ABORT_WO));
                  } else {
                    this.send(new CanOpenSdoDownloadResponse(this.id, msg.index, msg.subIndex, subObj.value));
                  }
                } else {
                  this.send(new CanOpenAbortResponse(this.id, msg.index, msg.subIndex, CanOpenSdoMessage.ABORT_SUBINDEX_DNE));
                }
              } else {
                this.send(new CanOpenAbortResponse(this.id, msg.index, msg.subIndex, CanOpenSdoMessage.ABORT_SUBINDEX_DNE));
              }
            } else {
              this.send(new CanOpenAbortResponse(this.id, msg.index, msg.subIndex, CanOpenSdoMessage.ABORT_OBJECT_DNE));
            }
            break;
          default:
            self.send(new CanOpenSdoAbortResponse(this.id, msg.index, msg.subIndex, CanOpenSdoMessage.ABORT_INVALID_CS));
        }
      }
    }
  }

  reset() {
    this.od = this.default_od;
    this.reset_communication();
  }

  reset_communication() {
    this.reset_timers();
    this.nmtState = this.NMT_STATE_INITIALISATION;
    this.boot()
  }

  reset_timers() {
    if (this.hasOwnProperty("heartbeatTimer")) {
      clearInterval(this.heartbeatTimer);
    }
  }

  send(msg) {
    this.ws.send(msg);
  }

  send_heartbeat() {
    this.send(new CanOpenHeartbeatMessage(this.id, this.nmtState));
  }
}
