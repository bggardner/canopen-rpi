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

  async _blockDownloadSubBlocks() {
    let dataLength = this.transaction.data.length;
    while (dataLength > 0 && this.transaction.seqno <= this.transaction.blksize) {
      let c = 0;
      if (dataLength <= 7) { c = 1; }
      let data = this.transaction.data.slice((this.transaction.seqno - 1) * 7, this.transaction.seqno * 7);
      await new Promise(resolve => setTimeout(resolve, 0)); // Without this, things hang
      this._send(new CanOpenSdoBlockDownloadSubBlockRequest(this.transaction.nodeId, c, this.transaction.seqno, data));
      clearTimeout(this.transaction.timer);
      dataLength -= 7;
      this.transaction.seqno++;
    }
    this.transaction.timer = setTimeout(() => this.abort(CanOpenSdoAbortRequest.ABORT_TIMEOUT), this.timeout);
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
    if (this.transaction.scs == CanOpenSdoMessage.SCS_BLOCK_UPLOAD && this.transaction.seqno > 0) {
      clearTimeout(this.transaction.timer);
      let c = (msg.data[0] >> 7);
      let seqno = msg.data[0] & 0x7F;
      let ackseq = 0;
      if (this.transaction.seqno != seqno) {
        if (this.transaction.seqno > 1) {
          return this.abort(CanOpenSdoAbortRequest.ABORT_INVALID_SEQNO);
        }
      } else {
        ackseq = seqno;
        this.transaction.data = this.transaction.data.concat(Array.from(msg.data.slice(1, 8)));
        if (c == 1) {
          this.transaction.seqno = 0;
        } else if (this.transaction.seqno == this.transaction.blksize) {
          this.transaction.seqno = 1;
        } else {
          this.transaction.seqno++;
          this.transaction.timer = setTimeout(() => this.abort(CanOpenSdoAbortRequest.ABORT_TIMEOUT), this.timeout);
          return;
        }
      }
      let blksize = 127;
      this._send(new CanOpenSdoBlockUploadResponse(this.transaction.nodeId, ackseq, blksize));
      return;
    }
    let scs = msg.data[0] >> CanOpenSdoMessage.CS_BITNUM;
    if (scs == CanOpenSdoMessage.CS_ABORT) { return this._end(new CustomEvent("abort", {detail: new Uint32Array(msg.data.slice(4, 8).buffer)[0]})); }
    if (scs != this.transaction.scs) { return this.abort(CanOpenSdoAbortRequest.ABORT_INVALID_CS); }
    clearTimeout(this.transaction.timer);
    if (scs == CanOpenSdoMessage.SCS_DOWNLOAD_INITIATE) {
      let index = new Uint16Array(msg.data.slice(1,3).buffer)[0];
      let subIndex = msg.data[3];
      if (this.transaction.index != index || this.transaction.subIndex != subIndex) { return this.abort(); }
      if (this.transaction.hasOwnProperty("data")) {
        this.transaction.scs = CanOpenSdoMessage.SCS_DOWNLOAD_SEGMENT;
        this.transaction.toggle = 0;
        let n = 0;
        let c = 0;
        if (this.transaction.data.length <= 7) {
          n = 7 - this.transaction.data.length;
          c = 1;
        }
        let data = new Uint8Array(7);
        data = data.set(this.transaction.data.slice(this.transaction.dataOffset, this.transaction.dataOffset + 7));
        this._send(new CanOpenSdoDownloadSegmentRequest(this.transaction.nodeId, this.transaction.toggle, n, c, data));
      } else {
        this._end(new CustomEvent("done", {detail: 0}));
      }
    } else if (scs == CanOpenSdoMessage.SCS_DOWNLOAD_SEGMENT) {
      this.transaction.toggle ^= 1;
      this.transaction.dataOffset += 7;
      let n = 0;
      let c = 0;
      if (this.transaction.data.length <= this.transaction.dataOffset + 7) {
        n = 7 - this.transaction.data.length;
        c = 1;
      }
      let data = new Uint8Array(7);
      data = data.set(this.transaction.data.slice(this.transaction.dataOffset, this.transaction.dataOffset + 7));
      this._send(new CanOpenSdoDownloadSegmentRequest(this.transaction.nodeId, this.transaction.toggle, n, c, data));
    } else if (scs == CanOpenSdoMessage.SCS_UPLOAD_INITIATE) {
      let index = new Uint16Array(msg.data.slice(1,3).buffer)[0];
      let subIndex = msg.data[3];
      if (this.transaction.index != index || this.transaction.subIndex != subIndex) { return this.abort(); }
      let s = (msg.data[0] >> CanOpenSdoUploadInitiateResponse.S_BITNUM) & 0x1;
      let n = 0;
      if (s) { n = (msg.data[0] >> CanOpenSdoUploadInitiateResponse.N_BITNUM) & 0x3; }
      let e = (msg.data[0] >> CanOpenSdoUploadInitiateResponse.E_BITNUM) & 0x1;
      let data = new Uint8Array(4);
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
      let t = (msg.data[0] >> CanOpenSdoUploadSegmentResponse.T_BITNUM) & 0x1;
      if (t != this.transaction.toggle) { return this.abort(CanOpenSdoAbortRequest.ABORT_TOGGLE); }
      let n = (msg.data[0] >> CanOpenSdoUploadSegmentResponse.N_BITNUM) & 0x7;
      this.transaction.data.set(msg.data.slice(1, 8 - n), this.transaction.dataOffset);
      let c = (msg.data[0] >> CanOpenSdoUploadSegmentResponse.C_BITNUM) & 0x1;
      if (c) {
        this._end(new CustomEvent("done", {detail: this.transaction.data}));
      } else {
        this.transaction.dataOffset += 7 - n;
        this.transaction.toggle ^= 1;
        this._send(new CanOpenSdoUploadSegmentRequest(this.transaction.nodeId, this.transaction.toggle));
      }
    } else if (scs == CanOpenSdoMessage.SCS_BLOCK_DOWNLOAD) {
      let dataLength, c, data;
      let ss = msg.data[0] & 0x3;
      if (ss == CanOpenSdoBlockMessage.SUBCOMMAND_INITIATE) {
        let sc = (msg.data[0] >> 2) & 0x1;
        let index = new Uint16Array(msg.data.slice(1,3).buffer)[0];
        let subIndex = msg.data[3];
        if (this.transaction.index != index || this.transaction.subIndex != subIndex) { return this.abort(); }
        let blksize = msg.data[4];
        this.transaction.blksize = blksize;
        this.transaction.seqno = 1;
        this._blockDownloadSubBlocks();
      } else if (ss == CanOpenSdoBlockMessage.SUBCOMMAND_RESPONSE) {
        let ackseq = msg.data[1];
        let blksize = msg.data[2];
        let n = 0;
        if (ackseq != 0) {
          let dataLength = this.transaction.data.length;
          let bytesTransferred = 7 * ackseq;
          let bytesLeft = dataLength - bytesTransferred;
          if (bytesLeft < 0) {
            n = -bytesLeft;
          }
          this.transaction.data.splice(0, ackseq * 7);
        }
        if (this.transaction.data.length == 0) {
          this._send(new CanOpenSdoBlockDownloadEndRequest(this.transaction.nodeId, n, this.transaction.crc));
        } else {
          this.transaction.seqno = 1;
          this.transaction.blksize = blksize;
          this._blockDownloadSubBlocks();
        }
      } else if (ss == CanOpenSdoBlockMessage.SUBCOMMAND_END) {
        this._end(new CustomEvent("done", {detail: 0}));
      } else {
        this.abort(CanOpenSdoAbortRequest.ABORT_INVALID_CS);
      }
    } else if (scs == CanOpenSdoMessage.SCS_BLOCK_UPLOAD) {
      let ss = msg.data[0] & 0x1;
      if (ss == CanOpenSdoBlockMessage.SUBCOMMAND_INITIATE) {
        let sc = (msg.data[0] >> 2) & 0x1;
        if (sc == 0) {
          delete this.transaction.crc;
        }
        let s = (msg.data[0] >> 1) & 0x1;
        let index = new Uint16Array(msg.data.slice(1,3).buffer)[0];
        let subIndex = msg.data[3];
        if (this.transaction.index != index || this.transaction.subIndex != subIndex) { return this.abort(); }
        let size = new Uint32Array(msg.data.slice(4, 8).buffer)[0];
        this.transaction.size = size;
        this.transaction.data = [];
        this.transaction.seqno = 1;
        this._send(new CanOpenSdoBlockUploadStartRequest(this.transaction.nodeId));
      } else { // ss == CanOpenSdoBlockMessage.SUBCOMMAND_END
        let n = (msg.data[0] >> 2) & 0x7;
        this.transaction.data.splice(-n);
        let crc = new Uint16Array(msg.data.slice(1,3).buffer)[0];
        if (this.transaction.hasOwnProperty("crc") && this.transaction.crc != crc) { return this.abort(CanOpenSdoAbortRequest.ABORT_CRC_ERROR); }
        this._send(new CanOpenSdoBlockUploadEndResponse(this.transaction.nodeId));
        this._end(new CustomEvent("done", {detail: new Uint8Array(this.transaction.data)}));
      }
    } else {
      this.abort(CanOpenSdoAbortRequest.ABORT_INVALID_CS);
    }
  }

  _send(msg) {
    if (this.ws.readyState == WebSocket.OPEN) {
      this.ws.send(msg);
      this.transaction.timer = setTimeout(() => this.abort(CanOpenSdoAbortRequest.ABORT_TIMEOUT), this.timeout);
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

  blockDownload(nodeId, index, subIndex, data) {
    let cc = 1; // CRC support
    let s = 1;
    this.transaction = {
      nodeId: nodeId,
      scs: CanOpenSdoMessage.SCS_BLOCK_DOWNLOAD,
      cc: cc,
      index: index,
      subIndex: subIndex,
      data: Array.from(data),
      crc: CanOpenSdoBlockMessage.crc(data)
    }
    return this._start(new CanOpenSdoBlockDownloadInitiateRequest(nodeId, cc, s, index, subIndex, data.length));
  }

  blockUpload(nodeId, index, subIndex) {
    let cc = 1; // CRC Support
    let blksize = 127;
    let pst = 0;
    this.transaction = {
      nodeId: nodeId,
      scs: CanOpenSdoMessage.SCS_BLOCK_UPLOAD,
      cc: cc,
      index: index,
      subIndex: subIndex,
      blksize: blksize,
      pst: pst
    }
    return this._start(new CanOpenSdoBlockUploadInitiateRequest(nodeId, cc, index, subIndex, blksize, pst));
  }

  download(nodeId, n, e, s, index, subIndex, data) {
    this.transaction = {
      nodeId: nodeId,
      scs: CanOpenSdoMessage.SCS_DOWNLOAD_INITIATE,
      index: index,
      subIndex: subIndex,
      crc: CanOpenSdoBlockMessage.crc(data)
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
    let data = new Uint8Array(8);
    data[0] = sdoHeader;
    data.set(sdoData, 1);
    super(functionCode, nodeId, data);
  }

  // Bit positions and masks
  static get CS_BITNUM() { return 5; }

  // Command specifiers
  static get CCS_DOWNLOAD_SEGMENT() { return 0; }
  static get CCS_DOWNLOAD_INITIATE() { return 1; }
  static get CCS_UPLOAD_INITIATE() { return 2; }
  static get CCS_UPLOAD_SEGMENT() { return 3; }
  static get CCS_BLOCK_UPLOAD() { return 5; }
  static get CCS_BLOCK_DOWNLOAD() { return 6; }
  static get CS_ABORT() { return 4; }
  static get SCS_UPLOAD_SEGMENT() { return 0; }
  static get SCS_DOWNLOAD_SEGMENT() { return 1; }
  static get SCS_UPLOAD_INITIATE() { return 2; }
  static get SCS_DOWNLOAD_INITIATE() { return 3; }
  static get SCS_BLOCK_DOWNLOAD() { return 5; }
  static get SCS_BLOCK_UPLOAD() { return 6; }

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

class CanOpenSdoBlockMessage extends CanOpenSdoMessage {
  static get SUBCOMMAND_INITIATE() { return 0; }
  static get SUBCOMMAND_END() { return 1; }
  static get SUBCOMMAND_RESPONSE() { return 2; }
  static get SUBCOMMAND_START() { return 3; }
  static get CRC_TABLE() { return [
    0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50a5,
    0x60c6, 0x70e7, 0x8108, 0x9129, 0xa14a, 0xb16b,
    0xc18c, 0xd1ad, 0xe1ce, 0xf1ef, 0x1231, 0x0210,
    0x3273, 0x2252, 0x52b5, 0x4294, 0x72f7, 0x62d6,
    0x9339, 0x8318, 0xb37b, 0xa35a, 0xd3bd, 0xc39c,
    0xf3ff, 0xe3de, 0x2462, 0x3443, 0x0420, 0x1401,
    0x64e6, 0x74c7, 0x44a4, 0x5485, 0xa56a, 0xb54b,
    0x8528, 0x9509, 0xe5ee, 0xf5cf, 0xc5ac, 0xd58d,
    0x3653, 0x2672, 0x1611, 0x0630, 0x76d7, 0x66f6,
    0x5695, 0x46b4, 0xb75b, 0xa77a, 0x9719, 0x8738,
    0xf7df, 0xe7fe, 0xd79d, 0xc7bc, 0x48c4, 0x58e5,
    0x6886, 0x78a7, 0x0840, 0x1861, 0x2802, 0x3823,
    0xc9cc, 0xd9ed, 0xe98e, 0xf9af, 0x8948, 0x9969,
    0xa90a, 0xb92b, 0x5af5, 0x4ad4, 0x7ab7, 0x6a96,
    0x1a71, 0x0a50, 0x3a33, 0x2a12, 0xdbfd, 0xcbdc,
    0xfbbf, 0xeb9e, 0x9b79, 0x8b58, 0xbb3b, 0xab1a,
    0x6ca6, 0x7c87, 0x4ce4, 0x5cc5, 0x2c22, 0x3c03,
    0x0c60, 0x1c41, 0xedae, 0xfd8f, 0xcdec, 0xddcd,
    0xad2a, 0xbd0b, 0x8d68, 0x9d49, 0x7e97, 0x6eb6,
    0x5ed5, 0x4ef4, 0x3e13, 0x2e32, 0x1e51, 0x0e70,
    0xff9f, 0xefbe, 0xdfdd, 0xcffc, 0xbf1b, 0xaf3a,
    0x9f59, 0x8f78, 0x9188, 0x81a9, 0xb1ca, 0xa1eb,
    0xd10c, 0xc12d, 0xf14e, 0xe16f, 0x1080, 0x00a1,
    0x30c2, 0x20e3, 0x5004, 0x4025, 0x7046, 0x6067,
    0x83b9, 0x9398, 0xa3fb, 0xb3da, 0xc33d, 0xd31c,
    0xe37f, 0xf35e, 0x02b1, 0x1290, 0x22f3, 0x32d2,
    0x4235, 0x5214, 0x6277, 0x7256, 0xb5ea, 0xa5cb,
    0x95a8, 0x8589, 0xf56e, 0xe54f, 0xd52c, 0xc50d,
    0x34e2, 0x24c3, 0x14a0, 0x0481, 0x7466, 0x6447,
    0x5424, 0x4405, 0xa7db, 0xb7fa, 0x8799, 0x97b8,
    0xe75f, 0xf77e, 0xc71d, 0xd73c, 0x26d3, 0x36f2,
    0x0691, 0x16b0, 0x6657, 0x7676, 0x4615, 0x5634,
    0xd94c, 0xc96d, 0xf90e, 0xe92f, 0x99c8, 0x89e9,
    0xb98a, 0xa9ab, 0x5844, 0x4865, 0x7806, 0x6827,
    0x18c0, 0x08e1, 0x3882, 0x28a3, 0xcb7d, 0xdb5c,
    0xeb3f, 0xfb1e, 0x8bf9, 0x9bd8, 0xabbb, 0xbb9a,
    0x4a75, 0x5a54, 0x6a37, 0x7a16, 0x0af1, 0x1ad0,
    0x2ab3, 0x3a92, 0xfd2e, 0xed0f, 0xdd6c, 0xcd4d,
    0xbdaa, 0xad8b, 0x9de8, 0x8dc9, 0x7c26, 0x6c07,
    0x5c64, 0x4c45, 0x3ca2, 0x2c83, 0x1ce0, 0x0cc1,
    0xef1f, 0xff3e, 0xcf5d, 0xdf7c, 0xaf9b, 0xbfba,
    0x8fd9, 0x9ff8, 0x6e17, 0x7e36, 0x4e55, 0x5e74,
    0x2e93, 0x3eb2, 0x0ed1, 0x1ef0
  ]};

  static crc(data) {
    let crc = 0x0000;
    for (let i = 0; i < data.length; i++) {
      crc = ((crc << 8) & 0xFF00) ^ this.CRC_TABLE[(crc >> 8) ^ data[i]];
    }
    return crc & 0xFFFF;
  }
}

class CanOpenSdoBlockDownloadInitiateRequest extends CanOpenSdoBlockMessage {
  constructor(nodeId, cc, s, index, subIndex, size=0) {
    let functionCode = CanOpenMessage.FUNCTION_CODE_SDO_RX;
    let sdoHeader = CanOpenSdoMessage.CCS_BLOCK_DOWNLOAD << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += cc << 2;
    sdoHeader += s << 1;
    sdoHeader += CanOpenSdoBlockMessage.SUBCOMMAND_INITIATE;
    let sdoData = [index & 0xFF, index >> 8, subIndex].concat(Array.from(new Uint8Array(new Uint32Array([size]).buffer)));
    super(functionCode, nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoBlockDownloadInitiateResponse extends CanOpenSdoBlockMessage {
  constructor(nodeId, sc, index, subIndex, blksize) {
    let functionCode = CanOpenMessage.FUNCTION_CODE_SDO_TX;
    let sdoHeader = CanOpenSdoMessage.SCS_BLOCK_DOWNLOAD << CanOpenMessage.CS_BITNUM;
    sdoHeader += sc << 2;
    sdoHeader += CanOpenSdoBlockMessage.SUBCOMMAND_INITIATE;
    let sdoData = [index & 0xFF, index >> 8, subIndex, blksize, 0, 0, 0];
    super(functionCode, nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoBlockDownloadSubBlockRequest extends CanOpenSdoBlockMessage {
  constructor(nodeId, c, seqno, data) {
    let functionCode = CanOpenMessage.FUNCTION_CODE_SDO_RX;
    let sdoHeader = (c << 7) + seqno;
    super(functionCode, nodeId, sdoHeader, data);
  }
}

class CanOpenSdoBlockDownloadResponse extends CanOpenSdoBlockMessage {
  constructor(nodeId, ackseq, blksize) {
    let functionCode = CanOpenMessage.FUNCTION_CODE_SDO_TX;
    let sdoHeader = CanOpenSdoMessage.SCS_BLOCK_DOWNLOAD << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += CanOpenSdoBlockMessage.SUBCOMMAND_RESPONSE;
    let sdoData = [ackseq, blksize, 0, 0, 0, 0, 0];
    super(functionCode, nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoBlockDownloadEndRequest extends CanOpenSdoBlockMessage {
  constructor(nodeId, n, crc) {
    let functionCode = CanOpenMessage.FUNCTION_CODE_SDO_RX;
    let sdoHeader = CanOpenSdoMessage.CCS_BLOCK_DOWNLOAD << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += n << 2;
    sdoHeader += CanOpenSdoBlockMessage.SUBCOMMAND_END;
    let sdoData = [crc & 0xFF, crc >> 8, 0, 0, 0, 0, 0];
    super(functionCode, nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoBlockDownloadEndResponse extends CanOpenSdoBlockMessage {
  constructor(nodeId) {
    let functionCode = CanOpenMessage.FUNCTION_CODE_SDO_TX;
    let sdoHeader = CanOpenSdoMessage.SCS_BLOCK_DOWNLOAD << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += CanOpenSdoBlockMessage.SUBCOMMAND_END;
    let sdoData = new Uint8Array(7);
    super(functionCode, nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoBlockUploadInitiateRequest extends CanOpenSdoBlockMessage {
  constructor(nodeId, cc, index, subIndex, blksize, pst) {
    let functionCode = CanOpenMessage.FUNCTION_CODE_SDO_RX;
    let sdoHeader = CanOpenSdoMessage.CCS_BLOCK_UPLOAD << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += cc << 2;
    sdoHeader += CanOpenSdoBlockMessage.SUBCOMMAND_INITIATE;
    let sdoData = [index & 0xFF, index >> 8, subIndex, blksize, pst, 0, 0];
    super(functionCode, nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoBlockUploadInitiateResponse extends CanOpenSdoBlockMessage {
  constructor(nodeId, sc, s, index, subIndex, size=0) {
    let functionCode = CanOpenMessage.FUNCTION_CODE_SDO_TX;
    let sdoHeader = CanOpenSdoMessage.SCS_BLOCK_UPLOAD << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += cc << 2;
    sdoHeader += CanOpenSdoBlockMessage.SUBCOMMAND_INITIATE;
    let sdoData = [index & 0xFF, index >> 8, subIndex].concat(Array.from(new Uint8Array(new Uint32Array([size]).buffer)));
    super(functionCode, nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoBlockUploadStartRequest extends CanOpenSdoBlockMessage {
  constructor(nodeId) {
    let functionCode = CanOpenMessage.FUNCTION_CODE_SDO_RX;
    let sdoHeader = CanOpenSdoMessage.CCS_BLOCK_UPLOAD << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += CanOpenSdoBlockMessage.SUBCOMMAND_START;
    let sdoData = new Uint8Array(7);
    super(functionCode, nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoBlockUploadSubBlockRequest extends CanOpenSdoBlockMessage {
  constructor(nodeId, c, seqno, data) {
    let functionCode = CanOpenMessage.FUNCTION_CODE_SDO_TX;
    let sdoHeader = (c << 7) + seqno;
    super(functionCode, nodeId, sdoHeader, data);
  }
}

class CanOpenSdoBlockUploadResponse extends CanOpenSdoBlockMessage {
  constructor(nodeId, ackseq, blksize) {
    let functionCode = CanOpenMessage.FUNCTION_CODE_SDO_RX;
    let sdoHeader = CanOpenSdoMessage.CCS_BLOCK_UPLOAD << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += CanOpenSdoBlockMessage.SUBCOMMAND_RESPONSE;
    let sdoData = [ackseq, blksize, 0, 0, 0, 0, 0];
    super(functionCode, nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoBlockUploadEndRequest extends CanOpenSdoBlockMessage {
  constructor(nodeId, n, crc) {
    let functionCode = CanOpenMessage.FUNCTION_CODE_SDO_TX;
    let sdoHeader = CanOpenSdoMessage.SCS_BLOCK_UPLOAD << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += n << 2;
    sdoHeader += CanOpenSdoBlockMessage.SUBCOMMAND_END;
    let sdoData = [crc & 0xFF, crc >> 8, 0, 0, 0, 0, 0];
    super (functionCode, nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoBlockUploadEndResponse extends CanOpenSdoBlockMessage {
  constructor(nodeId) {
    let functionCode = CanOpenMessage.FUNCTION_CODE_SDO_RX;
    let sdoHeader = CanOpenSdoMessage.CCS_BLOCK_UPLOAD << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += CanOpenSdoBlockMessage.SUBCOMMAND_END;
    let sdoData = new Uint8Array(7);
    super(functionCode, nodeId, sdoHeader, sdoData);
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
            this.send(new CanOpenSdoAbortResponse(this.id, msg.index, msg.subIndex, CanOpenSdoMessage.ABORT_INVALID_CS));
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


