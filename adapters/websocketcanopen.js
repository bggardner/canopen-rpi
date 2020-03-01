class WebSocketCanOpen extends WebSocketCan {
  _messageHandler(event) {
    let init = Object.assign({}, event);
    init.data = CanOpenMessage.from(new Uint8Array(event.data));
    event = new MessageEvent(event.type, init);
    this._handleMessageEvent(event);
  }
}

class CanOpenSdoClient extends EventTarget {
  constructor(ws, timeout=2000) {
    super();
    if (!(ws instanceof WebSocket)) { throw "Websocket is required"; }
    if (ws.readyState != WebSocket.OPEN) { throw "Websocket is not open"; }
    this.ws = ws;
    this.timeout = timeout;
    this.ws.addEventListener("error", event => { this.abort(CanOpenSdoAbortRequest.ABORT_CONNECTION); }, {once: true});
    this.ws.addEventListener("close", event => { this.abort(CanOpenSdoAbortRequest.ABORT_CONNECTION); }, {once: true});
    this._listener = this._recv.bind(this);
  }

  _end(event) {
    delete this.transaction;
    if (this.ws.readyState == WebSocket.OPEN) {
      this.ws.removeEventListener("message", this._listener);
    }
    this.dispatchEvent(event);
  }

  _recv(event) {
    let msg = event.data;
    if (!(this.hasOwnProperty("transaction")) || msg.functionCode != CanOpenMessage.FUNCTION_CODE_SDO_TX || this.transaction.nodeId != msg.nodeId) { return; }
    let scs = msg.data[0] >> CanOpenSdoMessage.CS_BITNUM;
    if (scs == CanOpenSdoMessage.CS_ABORT) { return this._end(new CustomEvent("abort", {detail: new Uint32Array(msg.data.slice(4, 8).buffer)[0]})); }
    // TODO: Repeated normal transactions result in duplicate CanOpenSdoMessage.SCS_*_INITIATE receptions causing the abort in the line below
    // Suspected this.ws.removeEventListener("message", this._listener) is not working, however only two receptions are triggered instead of incrementing after each repeated transaction
    if (scs != this.transaction.scs) { return this.abort(CanOpenSdoAbortRequest.ABORT_INVALID_CS); }
    clearTimeout(this.transaction.timer);
    let index, subIndex, n, e, s, data, t, c;
    if (scs == CanOpenSdoMessage.SCS_DOWNLOAD_INITIATE) {
      index = new Uint16Array(msg.data.slice(1,3).buffer)[0];
      subIndex = msg.data[3];
      if (this.transaction.index != index || this.transaction.subIndex != subIndex) { return this.abort(); }
      if (this.transaction.hasOwnProperty("data")) {
        this.transaction.scs = CanOpenSdoMessage.SCS_DOWNLOAD_SEGMENT;
        this.transaction.toggle = 0;
        if (this.transaction.data.length > 7) {
          n = 0;
          c = 0;
        } else {
          n = 7 - this.transaction.data.length;
          c = 1;
        }
        data = new Uint8Array(7);
        data = data.set(this.transaction.data.slice(this.transaction.dataOffset, this.transaction.dataOffset + 7));
        this._send(new CanOpenSdoDownloadSegmentRequest(this.transaction.nodeId, this.transaction.toggle, n, c, data));
      } else {
        this._end(new CustomEvent("done", {detail: 0}));
      }
    } else if (scs == CanOpenSdoMessage.SCS_DOWNLOAD_SEGMENT) {
      this.transaction.toggle ^= 1;
      this.transaction.dataOffset += 7;
      if (this.transaction.data.length > this.transaction.dataOffset + 7) {
        n = 0;
        c = 0;
      } else {
        n = 7 - this.transaction.data.length;
        c = 1;
      }
      data = new Uint8Array(7);
      data = data.set(this.transaction.data.slice(this.transaction.dataOffset, this.transaction.dataOffset + 7));
      this._send(new CanOpenSdoDownloadSegmentRequest(this.transaction.nodeId, this.transaction.toggle, n, c, data));
    } else if (scs == CanOpenSdoMessage.SCS_UPLOAD_INITIATE) {
      index = new Uint16Array(msg.data.slice(1,3).buffer)[0];
      subIndex = msg.data[3];
      if (this.transaction.index != index || this.transaction.subIndex != subIndex) { return this.abort(); }
      s = (msg.data[0] >> CanOpenSdoUploadInitiateResponse.S_BITNUM) & 0x1;
      n = 0;
      if (s) { n = (msg.data[0] >> CanOpenSdoUploadInitiateResponse.N_BITNUM) & 0x3; }
      e = (msg.data[0] >> CanOpenSdoUploadInitiateResponse.E_BITNUM) & 0x1;
      data = new Uint8Array(4);
      data.set(msg.data.slice(4, 8 - n));
      data = new Uint32Array(data.buffer)[0];
      if (e) {
        this._end(new CustomEvent("done", {detail: data}));
      } else {
        this.transaction.scs = CanOpenSdoMessage.SCS_UPLOAD_SEGMENT;
        this.transaction.toggle = 0;
        this.transaction.data = new Uint8Array(data);
        this.transaction.dataOffset = 0;
        this._send(new CanOpenSdoUploadSegmentRequest(this.transaction.nodeId, this.transaction.toggle));
      }
    } else if (scs == CanOpenSdoMessage.SCS_UPLOAD_SEGMENT) {
      t = (msg.data[0] >> CanOpenSdoUploadSegmentResponse.T_BITNUM) & 0x1;
      if (t != this.transaction.toggle) { return this.abort(CanOpenSdoAbortRequest.ABORT_TOGGLE); }
      n = (msg.data[0] >> CanOpenSdoUploadSegmentResponse.N_BITNUM) & 0x7;
      this.transaction.data.set(msg.data.slice(1, 8 - n), this.transaction.dataOffset);
      c = (msg.data[0] >> CanOpenSdoUploadSegmentResponse.C_BITNUM) & 0x1;
      if (c) {
        this._end(new CustomEvent("done", {detail: this.transaction.data}));
      } else {
        this.transaction.dataOffset += 7 - n;
        this.transaction.toggle ^= 1;
        this._send(new CanOpenSdoUploadSegmentRequest(this.transaction.nodeId, this.transaction.toggle));
      }
    }
  }

  _send(msg) {
    this.transaction.timer = setTimeout(() => this.abort(CanOpenSdoAbortRequest.ABORT_TIMEOUT), this.timeout);
    if (this.ws.readyState == WebSocket.OPEN) {
      this.ws.send(msg);
    } else {
      delete this.transaction;
      return this.abort(CanOpenSdoAbortRequest.ABORT_CONNECTION);
    }
  }

  _start(msg) {
    return new Promise((resolve, reject) => {
      this.addEventListener("done", event => { resolve(event.detail); }, {once: true});
      this.addEventListener("abort", event => { reject(event.detail); }, {once: true});
      this.ws.addEventListener("message", this._listener);
      this._send(msg);
    });
  }

  abort(code=CanOpenSdoAbortRequest.ABORT_GENERAL) {
    if (this.hasOwnProperty("transaction")) {
      clearTimeout(this.transaction.timer);
      if (this.ws.readyState == WebSocket.OPEN) {
        this.ws.send(new CanOpenSdoAbortRequest(this.transaction.nodeId, this.transaction.index, this.transaction.subIndex, code));
      } else {
        code = CanOpenSdoAbortRequest.ABORT_CONNECTION;
      }
    }
    this._end(new CustomEvent("abort", {detail: code}));
  }

  download(nodeId, n, e, s, index, subIndex, data) {
    this.transaction = {
      nodeId: nodeId,
      scs: CanOpenSdoMessage.SCS_DOWNLOAD_INITIATE,
      index: index,
      subIndex: subIndex
    }
    if (!e) {
      if (!(data instanceof Uint8Array)) { throw "Normal SDO data must be of type Uint8Array"; }
      this.transaction.data = data;
      this.transaction.dataOffset = 0;
    }
    return this._start(new CanOpenSdoDownloadInitiateRequest(nodeId, n, e, s, index, subIndex, data));
  }

  upload(nodeId, index, subIndex=0) {
    this.transaction = {
      nodeId: nodeId,
      scs: CanOpenSdoMessage.SCS_UPLOAD_INITIATE,
      index: index,
      subIndex: subIndex
    }
    return this._start(new CanOpenSdoUploadInitiateRequest(nodeId, index, subIndex));
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

const CanOpenSdoAbortMixIn = superclass => class extends superclass {
  // Abort codes
  static get ABORT_TOGGLE() { return 0x05030000; }
  static get ABORT_TIMEOUT() { return 0x05040000; }
  static get ABORT_INVALID_CS() { return 0x05040001; }
  static get ABORT_WO() { return 0x06010001; }
  static get ABORT_RO() { return 0x06010002; }
  static get ABORT_OBJECT_DNE() { return 0x06020000; }
  static get ABORT_SUBINDEX_DNE() { return 0x06090011; }
  static get ABORT_CONNECTION() { return 0x060A0023; }
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

class CanOpenSdoAbortRequest extends CanOpenSdoAbortMixIn(CanOpenSdoRequest) {}

class CanOpenSdoAbortResponse extends CanOpenSdoAbortMixIn(CanOpenSdoResponse) {}

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

class CanOpenSdoDownloadSegmentRequest extends CanOpenSdoSegmentMixIn(CanOpenSdoRequest) {
  constructor(nodeId, t, sdoData) {
    let sdoHeader = CanOpenSdoMessage.CCS_DOWNLOAD_SEGMENT << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += t << CanOpenSdoSegmentMixIn.T_BITNUM;
    sdoHeader += n << CanOpenSdoSegmentMixIn.N_BITNUM;
    sdoHeader += c << CanOpenSdoSegmentMixIn.C_BITNUM;
    super(nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoDownloadSegmentResponse extends CanOpenSdoSegmentMixIn(CanOpenSdoResponse) {
  constructor(nodeId, t) {
    let sdoHeader = CanOpenSdoMessage.SCS_DOWNLOAD_SEGMENT << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += t << CanOpenSdoDownloadSegmentResponse.T_BITNUM;
    let sdoData = Array(7).fill(0x00);
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

class CanOpenSdoUploadSegmentRequest extends CanOpenSdoSegmentMixIn(CanOpenSdoRequest) {
  constructor(nodeId, t) {
    let sdoHeader = CanOpenSdoMessage.CCS_UPLOAD_SEGMENT << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += t << CanOpenSdoUploadSegmentRequest.T_BITNUM;
    let sdoData = Array(7).fill(0x00);
    super(nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoUploadSegmentResponse extends CanOpenSdoSegmentMixIn(CanOpenSdoResponse) {
  constructor(nodeId, t, n, c, sdoData) {
    let sdoHeader = CanOpenSdoMessage.SCS_UPLOAD_SEGMENT << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += t << CanOpenSdoSegmentMixIn.T_BITNUM;
    sdoHeader += n << CanOpenSdoSegmentMixIn.N_BITNUM;
    sdoHeader += c << CanOpenSdoSegmentMixIn.C_BITNUM;
    super(nodeId, sdoHeader, sdoData);
  }
}

class CanOpenTimeOfDay {
  static get EPOCH() { return new Date("01 Jan 1984 00:00:00 GMT"); }

  constructor(days, milliseconds) {
     this.days = days;
     this.milliseconds = milliseconds;
  }

  [Symbol.iterator]() {
    let tod = this;
    return {
      next() {
        switch(this._cursor++) {
          case 0: return {value: tod.milliseconds && 0xFF, done: false};
          case 1: return {value: (tod.milliseconds >> 8) & 0xFF, done: false};
          case 2: return {value: (tod.milliseconds >> 16) & 0xFF,done: false};
          case 3: return {value: tod.milliseconds >> 24, done: false};
          case 4: return {value: tod.days & 0xFF, done: false};
          case 5: return {value: tod.days >> 8, done: false};
          case 6:
            this._cursor = 0;
            return {done: true};
          default:
        }
      },
      _cursor: 0
    }
  }

  toDate() {
    let d = CanOpenTimeOfDay.EPOCH;
    d.setDate(d.getDate() + this.days);
    d.setMilliseconds(this.milliseconds);
    return d;
  }

  static from(byteArray) {
    let milliseconds = byteArray[0];
    milliseconds += byteArray[1] << 8;
    milliseconds += byteArray[2] << 16;
    milliseconds += (byteArray[3] & 0x0F) << 24;
    let days = byteArray[4];
    days += byteArray[5] << 8;
    return new this(days, milliseconds);
  }

  static fromDate(d) {
    let milliseconds = (d - this.EPOCH);
    let days = Math.floor(milliseconds / 1000 / 3600 / 24);
    milliseconds -= days * 24 * 3600 * 1000;
    return new this(days, milliseconds);
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
