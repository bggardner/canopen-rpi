/**
 * Wrapper class that translates WebSocket message data to/from a CanOpenMesssage instance
 * @extends WebSocketCan
 */
class WebSocketCanOpen extends WebSocketCan {
  /**
   * Casts a CanMessage from MessageEvent data and passes it to handleMessageEvent()
   * @override
   * @protected
   * @param {MessageEvent} event
   */
  messageEventHandler(event) {
    let init = Object.assign({}, event);
    init.data = CanOpenMessage.from(event.data);
    event = new MessageEvent(event.type, init);
    this.handleMessageEvent(event);
  }
}

/**
 * Helper class that provides SDO Client functionality through Promises
 * @extends EventTarget
 */
class CanOpenSdoClient extends EventTarget {
  /**
   * Create a new CanOpenSdoClient instance.
   * @param {WebSocketCanOpen} ws - An open WebSocketCanOpen instance.
   * @param {number} timeout - SDO timeout (in ms)
   * @throws {string} - Exception description
   */
  constructor(ws, timeout=2000) {
    super();
    if (!(ws instanceof WebSocketCanOpen)) { throw "WebSocketCanOpen is required"; }
    if (ws.readyState != WebSocket.OPEN) { throw "Websocket is not open"; }
    /**
      @protected
      @const
     */
    this.ws = ws;
    /** @const */
    this.timeout = timeout;
    /**
      @private
      @const
     */
    this.listener_ = this.recv_.bind(this);
    this.ws.addEventListener("error", event => { this.abort(CanOpenSdoAbortRequest.ABORT_CONNECTION); }, {once: true});
    this.ws.addEventListener("close", event => { this.abort(CanOpenSdoAbortRequest.ABORT_CONNECTION); }, {once: true});
  }

  /**
   * Subroutine for sending unconfirmed SDO download sub-blocks.
   * @private
   */
  async blockDownloadSubBlocks_() {
    let dataLength = this.transaction.data.length;
    while (dataLength > 0 && this.transaction.seqno <= this.transaction.blksize) {
      let c = 0;
      if (dataLength <= 7) { c = 1; }
      let data = this.transaction.data.slice((this.transaction.seqno - 1) * 7, this.transaction.seqno * 7);
      await new Promise(resolve => setTimeout(resolve, 0)); // Without this, things hang
      this.send_(new CanOpenSdoBlockDownloadSubBlockRequest(this.transaction.nodeId, c, this.transaction.seqno, data));
      clearTimeout(this.transaction.timer);
      dataLength -= 7;
      this.transaction.seqno++;
    }
    this.transaction.timer = setTimeout(() => this.abort(CanOpenSdoAbortRequest.ABORT_TIMEOUT), this.timeout);
  }

  /**
   * Ends a a transaction.
   * @private
   * @param {CustomEvent} event
   */
  end_(event) {
    delete this.transaction;
    if (this.ws.readyState == WebSocket.OPEN) {
      this.ws.removeEventListener("message", this.listener_);
    }
    this.dispatchEvent(event);
  }

  /**
   * Processes a received a MessageEvent.
   * @private
   * @param {MessageEvent} event
   */
  recv_(event) {
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
      this.send_(new CanOpenSdoBlockUploadResponse(this.transaction.nodeId, ackseq, blksize));
      return;
    }
    let scs = msg.data[0] >> CanOpenSdoMessage.CS_BITNUM;
    if (scs == CanOpenSdoMessage.CS_ABORT) { return this.end_(new CustomEvent("abort", {detail: new Uint32Array(msg.data.slice(4, 8).buffer)[0]})); }
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
        data.set(this.transaction.data.slice(0, 7));
        this.send_(new CanOpenSdoDownloadSegmentRequest(this.transaction.nodeId, this.transaction.toggle, n, c, data));
      } else {
        this.end_(new CustomEvent("done", {detail: true}));
      }
    } else if (scs == CanOpenSdoMessage.SCS_DOWNLOAD_SEGMENT) {
      let t = (msg.data[0] >> CanOpenSdoDownloadSegmentResponse.T_BITNUM) & 0x1;
      if (t != this.transaction.toggle) { return this.abort(CanOpenSdoAbortRequest.ABORT_TOGGLE); }
      this.transaction.dataOffset += 7;
      if (this.transaction.dataOffset >= this.transaction.data.length) { return this.end_(new CustomEvent("done", {detail: true})); }
      this.transaction.toggle ^= 1;
      let n = 0;
      let c = 0;
      if (this.transaction.data.length - this.transaction.dataOffset <= 7) {
        n = 7 - (this.transaction.data.length - this.transaction.dataOffset);
        c = 1;
      }
      let data = new Uint8Array(7);
      data.set(this.transaction.data.slice(this.transaction.dataOffset, this.transaction.dataOffset + 7));
      this.send_(new CanOpenSdoDownloadSegmentRequest(this.transaction.nodeId, this.transaction.toggle, n, c, data));
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
      if (e) {
        this.end_(new CustomEvent("done", {detail: data.buffer}));
      } else {
        this.transaction.scs = CanOpenSdoMessage.SCS_UPLOAD_SEGMENT;
        this.transaction.toggle = 0;
        this.transaction.data = new Uint8Array(new Uint32Array(data.buffer)[0]);
        this.transaction.dataOffset = 0;
        this.send_(new CanOpenSdoUploadSegmentRequest(this.transaction.nodeId, this.transaction.toggle));
      }
    } else if (scs == CanOpenSdoMessage.SCS_UPLOAD_SEGMENT) {
      let t = (msg.data[0] >> CanOpenSdoUploadSegmentResponse.T_BITNUM) & 0x1;
      if (t != this.transaction.toggle) { return this.abort(CanOpenSdoAbortRequest.ABORT_TOGGLE); }
      let n = (msg.data[0] >> CanOpenSdoUploadSegmentResponse.N_BITNUM) & 0x7;
      this.transaction.data.set(msg.data.slice(1, 8 - n), this.transaction.dataOffset);
      let c = (msg.data[0] >> CanOpenSdoUploadSegmentResponse.C_BITNUM) & 0x1;
      if (c) {
        this.end_(new CustomEvent("done", {detail: this.transaction.data.buffer}));
      } else {
        this.transaction.dataOffset += 7 - n;
        this.transaction.toggle ^= 1;
        this.send_(new CanOpenSdoUploadSegmentRequest(this.transaction.nodeId, this.transaction.toggle));
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
        this.blockDownloadSubBlocks_();
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
          this.send_(new CanOpenSdoBlockDownloadEndRequest(this.transaction.nodeId, n, this.transaction.crc));
        } else {
          this.transaction.seqno = 1;
          this.transaction.blksize = blksize;
          this.blockDownloadSubBlocks_();
        }
      } else if (ss == CanOpenSdoBlockMessage.SUBCOMMAND_END) {
        this.end_(new CustomEvent("done", {detail: true}));
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
        if (s) {
            let size = new Uint32Array(msg.data.slice(4, 8).buffer)[0];
            this.transaction.size = size;
        }
        this.transaction.data = [];
        this.transaction.seqno = 1;
        this.send_(new CanOpenSdoBlockUploadStartRequest(this.transaction.nodeId));
      } else { // ss == CanOpenSdoBlockMessage.SUBCOMMAND_END
        let n = (msg.data[0] >> 2) & 0x7;
        this.transaction.data.splice(-n);
        let crc = new Uint16Array(msg.data.slice(1,3).buffer)[0];
        if (this.transaction.hasOwnProperty("crc") && this.transaction.crc != crc) { return this.abort(CanOpenSdoAbortRequest.ABORT_CRC_ERROR); }
        this.send_(new CanOpenSdoBlockUploadEndResponse(this.transaction.nodeId));
        this.end_(new CustomEvent("done", {detail: new Uint8Array(this.transaction.data).buffer}));
      }
    } else {
      this.abort(CanOpenSdoAbortRequest.ABORT_INVALID_CS);
    }
  }

  /**
   * Sends a CanOpenSdoMessage to the WebSocketCanOpen and starts the watchdog timer.
   * @private
   * @param {CanOpenSdoMessage} msg
   */
  send_(msg) {
    if (this.ws.readyState == WebSocket.OPEN) {
      this.ws.send(msg);
      this.transaction.timer = setTimeout(() => this.abort(CanOpenSdoAbortRequest.ABORT_TIMEOUT), this.timeout);
    } else {
      delete this.transaction;
      return this.abort(CanOpenSdoAbortRequest.ABORT_CONNECTION);
    }
  }

  /**
   * Starts an SDO transaction
   * @private
   * @param {CanOpenSdoMessage} msg
   */
  start_(msg) {
    return new Promise((resolve, reject) => {
      this.addEventListener("done", event => { resolve(event.detail); }, {once: true});
      this.addEventListener("abort", event => { reject(event.detail); }, {once: true});
      this.ws.addEventListener("message", this.listener_);
      this.send_(msg);
    });
  }

  /**
   * Aborts an SDO transaction, if in process
   * @param {number} [code=CanOpenSdoAbortRequest.ABORT_GENERAL] - SDO abort code
   */
  abort(code=CanOpenSdoAbortRequest.ABORT_GENERAL) {
    if (this.hasOwnProperty("transaction")) {
      clearTimeout(this.transaction.timer);
      if (this.ws.readyState == WebSocket.OPEN) {
        this.ws.send(new CanOpenSdoAbortRequest(this.transaction.nodeId, this.transaction.index, this.transaction.subIndex, code));
      } else {
        code = CanOpenSdoAbortRequest.ABORT_CONNECTION;
      }
    }
    this.end_(new CustomEvent("abort", {detail: code}));
  }

  /**
   * Starts an SDO block download transaction.
   * @param {number} nodeId - CANopen Node-ID
   * @param {number} index - CANopen object dictionary index
   * @param {number} subIndex - CANopen object dictionary sub-index
   * @param {iterable.<number>} data - Data to be downloaded to the object
   * @returns {Promise} - Resolves true or rejects an SDO abort code
   */
  blockDownload(nodeId, index, subIndex, data) {
    let cc = 1; // CRC support
    let s = 1;
    data = new Uint8Array(data);
    this.transaction = {
      nodeId: nodeId,
      scs: CanOpenSdoMessage.SCS_BLOCK_DOWNLOAD,
      cc: cc,
      index: index,
      subIndex: subIndex,
      data: Array.from(data),
      crc: CanOpenSdoBlockMessage.crc(data)
    }
    return this.start_(new CanOpenSdoBlockDownloadInitiateRequest(nodeId, cc, s, index, subIndex, data.length));
  }

  /**
   * Starts an SDO block upload transaction.
   * @param {number} nodeId - CANopen Node-ID
   * @param {number} index - CANopen object dictionary index
   * @param {number} subIndex - CANopen object dictionary sub-index
   * @returns {Promise} - Resolves an ArrayBuffer or rejects an SDO abort code
   */
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
    return this.start_(new CanOpenSdoBlockUploadInitiateRequest(nodeId, cc, index, subIndex, blksize, pst));
  }

  /**
   * Starts an SDO download transaction.
   * @param {number} nodeId - CANopen Node-ID
   * @param {number} index - CANopen object dictionary index
   * @param {number} subIndex - CANopen object dictionary sub-index
   * @param {iterable.<number>} data - Data to be downloaded to the object
   * @returns {Promise} - Resolves true or rejects an SDO abort code
   */
  download(nodeId, index, subIndex, data) {
    data = new Uint8Array(data);
    let n = 0;
    if (data.length < 4) {
      n = 4 - data.length;
    }
    let e = 0;
    if (data.length <= 4) {
      e = 1;
    }
    let s = 1;
    this.transaction = {
      nodeId: nodeId,
      scs: CanOpenSdoMessage.SCS_DOWNLOAD_INITIATE,
      index: index,
      subIndex: subIndex
    }
    if (!e) {
      this.transaction.data = data;
      this.transaction.dataOffset = 0;
      data = new Uint8Array(new Uint32Array([data.length]).buffer);
    }
    return this.start_(new CanOpenSdoDownloadInitiateRequest(nodeId, n, e, s, index, subIndex, data));
  }

  /**
   * Starts an SDO upload transaction.
   * @param {number} nodeId - CANopen Node-ID
   * @param {number} index - CANopen object dictionary index
   * @param {number} subIndex - CANopen object dictionary sub-index
   * @returns {Promise} - Resolves an ArrayBuffer or rejects an SDO abort code
   */
  upload(nodeId, index, subIndex=0) {
    this.transaction = {
      nodeId: nodeId,
      scs: CanOpenSdoMessage.SCS_UPLOAD_INITIATE,
      index: index,
      subIndex: subIndex
    }
    return this.start_(new CanOpenSdoUploadInitiateRequest(nodeId, index, subIndex));
  }
}

/** Class for sending data on a WebSocketCanOpen. */
class CanOpenMessage extends CanMessage {
  /**
   * Create a new CanOpenMessage.
   * @param {number} functionCode - CANopen function code (4 bits)
   * @param {number} nodeId - CANopen Node-ID or command
   * @param {iterable.<number>} [data=new ArrayBuffer()] - CAN frame data bytes
  */
  constructor(functionCode, nodeId, data=new ArrayBuffer()) {
    data = new Uint8Array(data);
    super((functionCode << 7) + nodeId, data, false, false, false);
  }

  static get FUNCTION_CODE_NMT() { return 0x0; }
  static get FUNCTION_CODE_SYNC() { return 0x1; }
  static get FUNCTION_CODE_EMCY() { return 0x1; }
  static get FUNCTION_CODE_TIME() { return 0x2; }
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

  /**
   * @type {number}
  */
  get functionCode() {
    return this.arbitrationId >> 7;
  }

  set functionCode(fc) {
    this.arbitrationId = ((fc & 0xF) << 7) + this.nodeId;
  }

  /**
   * @type {number}
   */
  get nodeId() {
    return this.arbitrationId & 0x7F;
  }

  set nodeId(id) {
    this.arbitrationId = (this.functionCode << 7) + (id & 0x7F);
  }

  /**
   * Factory function for converting raw bytes to a CanOpenMessage instance.
   * @param {ArrayBuffer} buffer - Byte array from the raw WebSocket message data
   * @returns {CanOpenMessage}
   */
  static from(buffer) { // Factory from SocketCAN-formatted byte array
      let byteArray = new Uint8Array(buffer);
      let nodeId = byteArray[0] & 0x7F;
      let functionCode = byteArray[0] >> 7;
      functionCode += (byteArray[1] & 0x7) << 1;
      let dlc = byteArray[4];
      let data = byteArray.slice(8, 8 + dlc);
      return new this(functionCode, nodeId, data);
  }
}

/**
 * Base class for NMT messages.
 * @extends CanOpenMessage
 */
class CanOpenNmtMessage extends CanOpenMessage {
  /**
   * @param {number} command - CANopen NMT command
   * @param {Uint8Array} [data=new Uint8Array()] - CANopen NMT command arguments
   */
  constructor(command, data=new Uint8Array()) {
    super(CanOpenMessage.FUNCTION_CODE_NMT, command, data);
  }
}

/**
 * Class for NMT node control messages.
 * @extends CanOpenNmtMessage
 */
class CanOpenNmtNodeControlMessage extends CanOpenNmtMessage {
  /**
   * @param {number} cs - CANopen NMT state
   * @param {number} nodeID - Target CANopen Node-ID (0 for all nodes)
   */
  constructor(cs, nodeId=0) {
    let data = new Uint8Array([cs, nodeId]);
    super(0, data);
  }

  static get CS_START() { return 1; }
  static get CS_STOP() { return 2; }
  static get CS_ENTER_PREOPERATIONAL() { return 128; }
  static get CS_RESET_NODE() { return 129; }
  static get CS_RESET_COMMUNICATION() { return 130; }
}

/**
 * CANopen SYNC message.
 * @extends CanOpenMessage
 */
class CanOpenSyncMessage extends CanOpenMessage {
  /**
   * @param {number} counter - CANopen SYNC counter
   */
  constructor(counter) {
    let data;
    if (counter == undefined) {
      data = new Uint8Array();
    } else {
      data = new Uint8Array([counter]);
    }
    super(CanOpenMessage.FUNCTION_CODE_SYNC, 0, data);
  }
}

/**
 * CANopen TIME message.
 * @extends CanOpenMessage
 */
class CanOpenTimeMessage extends CanOpenMessage {
  /**
   * @param {CanOpenTimeOfDay} timeOfDay - CANopen TIME_OF_DAY instance
   */
  constructor(timeOfDay) {
    let data = new Uint8Array(timeOfDay);
    super(CanOpenMessage.FUNCTION_CODE_TIME, 0, data);
  }
}

/**
 * Class for the CANopen NMT error control message.
 * @extends CanOpenMessage
 */
class CanOpenNmtErrorControlMessage extends CanOpenMessage {
  /**
   * @param {number} nodeId - CANopen Node-ID
   * @param {number} s - CANopen operational state
   */
  constructor(nodeId, s) {
    let data = new Uint8Array([s]);
    super(CanOpenMessage.FUNCTION_CODE_NMT_ERROR_CONTROL, nodeId, data);
  }
}

/**
 * Class for the CANopen boot-up message.
 * @extends CanOpenNmtErrorControlMessage
 */
class CanOpenBootupMessage extends CanOpenNmtErrorControlMessage {
  /**
   * @param {number} nodeId - CANopen Node-ID
   */
  constructor(nodeId) {
    super(nodeId, CanOpenNmtState.INITIALISATION);
  }
}

/**
 * Class for the CANopen heartbeat message.
 * @extends CanOpenNmtErrorControlMessage
 */
class CanOpenHeartbeatMessage extends CanOpenNmtErrorControlMessage {
  /**
   * @param {number} nodeId - CANopen Node-ID
   * @param {number} s - CANopen NMT state, one of the {@link CanOpenNmtState} properties
   */
  constructor(nodeId, s) {
    super(nodeId, [s]);
  }
}

/**
 * Base class for CANopen SDO messages.
 * @extends CanOpenMessage
 */
class CanOpenSdoMessage extends CanOpenMessage {
  /**
   * @param {number} functionCode - CANopen function code
   * @param {number} nodeId - CANopen Node-ID
   * @param {number} sdoHeader - SDO header byte
   * @param {Uint8Array} sdoData - SDO data bytes
   */
  constructor(functionCode, nodeId, sdoHeader, sdoData) {
    let data = new Uint8Array(8);
    data.set(new Uint8Array([sdoHeader]));
    data.set(sdoData, 1);
    super(functionCode, nodeId, data);
  }

  /**
   * Command specifier bit position
   * @constant
   * @type {number}
   * @default 5
   */
  static get CS_BITNUM() { return 5; }

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

  /**
   * Command specifier
   * @readonly
   * @type {number}
   */
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
    let sdoData = new Uint8Array(7);
    sdoData.set(new Uint8Array(new Uint16Array([index]).buffer));
    sdoData.set([subIndex], 2);
    sdoData.set(new Uint8Array(new Uint32Array([abortCode]).buffer), 3);
    super(nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoAbortRequest extends CanOpenSdoAbortMixIn(CanOpenSdoRequest) {}

class CanOpenSdoAbortResponse extends CanOpenSdoAbortMixIn(CanOpenSdoResponse) {}

class CanOpenSdoDownloadInitiateRequest extends CanOpenSdoInitiateMixIn(CanOpenSdoRequest) {
  constructor(nodeId, n, e, s, index, subIndex, data) {
    let sdoHeader = CanOpenSdoMessage.CCS_DOWNLOAD_INITIATE << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += n << CanOpenSdoDownloadInitiateRequest.N_BITNUM;
    sdoHeader += e << CanOpenSdoDownloadInitiateRequest.E_BITNUM;
    sdoHeader += s << CanOpenSdoDownloadInitiateRequest.S_BITNUM;
    let sdoData = new Uint8Array(7);
    sdoData.set(new Uint8Array(new Uint16Array([index]).buffer));
    sdoData.set(new Uint8Array([subIndex]), 2);
    sdoData.set(new Uint8Array(data.buffer), 3);
    super(nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoDownloadSegmentRequest extends CanOpenSdoSegmentMixIn(CanOpenSdoRequest) {
  constructor(nodeId, t, n, c, sdoData) {
    let sdoHeader = CanOpenSdoMessage.CCS_DOWNLOAD_SEGMENT << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += t << CanOpenSdoDownloadSegmentRequest.T_BITNUM;
    sdoHeader += n << CanOpenSdoDownloadSegmentRequest.N_BITNUM;
    sdoHeader += c << CanOpenSdoDownloadSegmentRequest.C_BITNUM;
    super(nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoDownloadSegmentResponse extends CanOpenSdoSegmentMixIn(CanOpenSdoResponse) {
  constructor(nodeId, t) {
    let sdoHeader = CanOpenSdoMessage.SCS_DOWNLOAD_SEGMENT << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += t << CanOpenSdoDownloadSegmentResponse.T_BITNUM;
    let sdoData = new Uint8Array(7);
    super(nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoDownloadInitiateResponse extends CanOpenSdoInitiateMixIn(CanOpenSdoResponse) {
  constructor(nodeId, index, subIndex) {
    let sdoHeader = CanOpenSdoMessage.SCS_DOWNLOAD_INITIATE << CanOpenSdoMessage.CS_BITNUM;
    let sdoData = new Uint8Array(7);
    sdoData.set(new Uint8Array(new Uint16Array([index]).buffer));
    sdoData.set(new Uint8Array([subIndex]), 2);
    super(nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoUploadInitiateRequest extends CanOpenSdoInitiateMixIn(CanOpenSdoRequest) {
  constructor(nodeId, index, subIndex) {
    let sdoHeader = CanOpenSdoMessage.CCS_UPLOAD_INITIATE << CanOpenSdoMessage.CS_BITNUM;
    let sdoData = new Uint8Array(7);
    sdoData.set(new Uint8Array(new Uint16Array([index]).buffer));
    sdoData.set(new Uint8Array([subIndex]), 2);
    super(nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoUploadInitiateResponse extends CanOpenSdoInitiateMixIn(CanOpenSdoResponse) {
  constructor(nodeId, n, e, s, index, subIndex, data) {
    let sdoHeader = CanOpenSdoMessage.SCS_UPLOAD_INITIATE << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += n << CanOpenSdoInitiateMixIn(CanOpenSdoRequest).N_BITNUM;
    sdoHeader += e << CanOpenSdoInitiateMixIn(CanOpenSdoRequest).E_BITNUM;
    sdoHeader += s << CanOpenSdoInitiateMixIn(CanOpenSdoRequest).S_BITNUM;
    let sdoData = new Uint8Array(7);
    sdoData.set(new Uint8Array(new Uint16Array([index]).buffer));
    sdoData.set(new Uint8Array([subIndex]), 2);
    sdoData.set(new Uint8Array(new Uint32Array([data]).buffer), 3);
    super(nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoUploadSegmentRequest extends CanOpenSdoSegmentMixIn(CanOpenSdoRequest) {
  constructor(nodeId, t) {
    let sdoHeader = CanOpenSdoMessage.CCS_UPLOAD_SEGMENT << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += t << CanOpenSdoUploadSegmentRequest.T_BITNUM;
    let sdoData = new Uint8Array(7);
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
    let sdoData = new Uint8Array(7);
    sdoData.set(new Uint8Array(new Uint16Array([index]).buffer));
    sdoData.set(new Uint8Array([subIndex]), 2);
    sdoData.set(new Uint8Array(new Uint32Array([size]).buffer), 3);
    super(functionCode, nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoBlockDownloadInitiateResponse extends CanOpenSdoBlockMessage {
  constructor(nodeId, sc, index, subIndex, blksize) {
    let functionCode = CanOpenMessage.FUNCTION_CODE_SDO_TX;
    let sdoHeader = CanOpenSdoMessage.SCS_BLOCK_DOWNLOAD << CanOpenMessage.CS_BITNUM;
    sdoHeader += sc << 2;
    sdoHeader += CanOpenSdoBlockMessage.SUBCOMMAND_INITIATE;
    let sdoData = new Uint8Array(7);
    sdoData.set(new Uint8Array(new Uint16Array([index]).buffer));
    sdoData.set(new Uint8Array([subIndex, blksize]), 2);
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
    let sdoData = new Uint8Array([ackseq, blksize, 0, 0, 0, 0, 0]);
    super(functionCode, nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoBlockDownloadEndRequest extends CanOpenSdoBlockMessage {
  constructor(nodeId, n, crc) {
    let functionCode = CanOpenMessage.FUNCTION_CODE_SDO_RX;
    let sdoHeader = CanOpenSdoMessage.CCS_BLOCK_DOWNLOAD << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += n << 2;
    sdoHeader += CanOpenSdoBlockMessage.SUBCOMMAND_END;
    let sdoData = new Uint8Array(7);
    sdoData.set(new Uint8Array(new Uint16Array([crc]).buffer));
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
    let sdoData = new Uint8Array(7);
    sdoData.set(new Uint8Array(new Uint16Array([index]).buffer));
    sdoData.set(new Uint8Array([subIndex, blksize, pst]), 2);
    super(functionCode, nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoBlockUploadInitiateResponse extends CanOpenSdoBlockMessage {
  constructor(nodeId, sc, s, index, subIndex, size=0) {
    let functionCode = CanOpenMessage.FUNCTION_CODE_SDO_TX;
    let sdoHeader = CanOpenSdoMessage.SCS_BLOCK_UPLOAD << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += cc << 2;
    sdoHeader += CanOpenSdoBlockMessage.SUBCOMMAND_INITIATE;
    let sdoData = new Uint8Array(7);
    sdoData.set(new Uint8Array(new Uint16Array([index]).buffer));
    sdoData.set(new Uint8Array([subIndex]), 2);
    sdoData.set(new Uint8Array(new Uint32Array([size]).buffer), 3);
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
    let sdoData = new Uint8Array([ackseq, blksize, 0, 0, 0, 0, 0]);
    super(functionCode, nodeId, sdoHeader, sdoData);
  }
}

class CanOpenSdoBlockUploadEndRequest extends CanOpenSdoBlockMessage {
  constructor(nodeId, n, crc) {
    let functionCode = CanOpenMessage.FUNCTION_CODE_SDO_TX;
    let sdoHeader = CanOpenSdoMessage.SCS_BLOCK_UPLOAD << CanOpenSdoMessage.CS_BITNUM;
    sdoHeader += n << 2;
    sdoHeader += CanOpenSdoBlockMessage.SUBCOMMAND_END;
    let sdoData = new Uint8Array(7);
    sdoData.set(new Uint8Array(new Uint16Array([crc]).buffer));
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

/**
 * Abstract CANopen time data type
 */
class CanOpenTimeDataType {
  /**
   * Create a new CanOpenTimeofDay.
   * @param {number} days - Number of days since the epoch
   * @param {number} milliseconds - Milliseconds since the beginning of the day
   */
  constructor(days, milliseconds) {
     this.days = days;
     this.milliseconds = milliseconds;
  }

  [Symbol.iterator]() {
    let tod = this;
    return {
      next() {
        switch(this.cursor_++) {
          case 0: return {value: tod.milliseconds && 0xFF, done: false};
          case 1: return {value: (tod.milliseconds >> 8) & 0xFF, done: false};
          case 2: return {value: (tod.milliseconds >> 16) & 0xFF,done: false};
          case 3: return {value: tod.milliseconds >> 24, done: false};
          case 4: return {value: tod.days & 0xFF, done: false};
          case 5: return {value: tod.days >> 8, done: false};
          case 6:
            this.cursor_ = 0;
            return {done: true};
          default:
        }
      },
      cursor_: 0
    }
  }

  /**
   * Factory function from a 6-byte array
   * @param {ArrayBuffer} buffer - 6-byte array defined in CiA 301
   * @returns {CanOpenTimeDataType}
   */
  static from(buffer) {
    let byteArray = new Uint8Array(buffer);
    let milliseconds = byteArray[0];
    milliseconds += byteArray[1] << 8;
    milliseconds += byteArray[2] << 16;
    milliseconds += (byteArray[3] & 0x0F) << 24;
    let days = byteArray[4];
    days += byteArray[5] << 8;
    return new this(days, milliseconds);
  }
}

/**
 * CANopen time of day ata type
 */
class CanOpenTimeOfDay extends CanOpenTimeDataType {
  /**
   * Returns the epoch
   * @constant
   * @type {Date}
   * @default new Date("01 Jan 1984 00:00:00 GMT")
   */
  static get EPOCH() { return new Date("01 Jan 1984 00:00:00 GMT"); }

  /**
   * Factory function from a Date
   * @param {Date} date
   * @returns {CanOpenTimeOfDay}
   */
  static fromDate(date) {
    let milliseconds = (date - this.EPOCH);
    let days = Math.floor(milliseconds / 1000 / 3600 / 24);
    milliseconds -= days * 24 * 3600 * 1000;
    return new this(days, milliseconds);
  }

  /**
   * Converts object to a Date
   * @returns {Date}
   */
  toDate() {
    let d = CanOpenTimeOfDay.EPOCH;
    d.setDate(d.getDate() + this.days);
    d.setMilliseconds(this.milliseconds);
    return d;
  }
}

/**
 * CANopen time difference data type
 */
class CanOpenTimeDifference extends CanOpenTimeDataType {}

/**
 * Class of constants for CANopen NMT states
 */
class CanOpenNmtState {
  /**
   * @constant
   * @type {number}
   * @default 0
   */
  static get INITIALISATION() { return 0x00; }
  /**
   * @constant
   * @type {number}
   * @default 127
   */
  static get PREOPERATIONAL() { return 0x7F; }
  /**
   * @constant
   * @type {number}
   * @default 5
   */
  static get OPERATIONAL() { return 0x05; }
  /**
   * @constant
   * @type {number}
   * @default 4
   */
  static get STOPPED() { return 0x04; }
}

// Code below is under development

// Polyfill from https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/ArrayBuffer/transfer
if (!ArrayBuffer.transfer) {
    ArrayBuffer.transfer = function(source, length) {
        if (!(source instanceof ArrayBuffer))
            throw new TypeError('Source must be an instance of ArrayBuffer');
        if (length <= source.byteLength)
            return source.slice(0, length);
        var sourceView = new Uint8Array(source),
            destView = new Uint8Array(new ArrayBuffer(length));
        destView.set(sourceView);
        return destView.buffer;
    };
}

class CanOpenObjectDictionary {
  static get INDEX_DATA_TYPE_BOOLEAN() { return 0x0001; }
  static get INDEX_DATA_TYPE_INTEGER8() { return 0x0002; }
  static get INDEX_DATA_TYPE_INTEGER16() { return 0x0003; }
  static get INDEX_DATA_TYPE_INTEGER32() { return 0x0004; }
  static get INDEX_DATA_TYPE_UNSIGNED8() { return 0x0005; }
  static get INDEX_DATA_TYPE_UNSIGNED16() { return 0x0006; }
  static get INDEX_DATA_TYPE_UNSIGNED32() { return 0x0007; }
  static get INDEX_DATA_TYPE_REAL32() { return 0x0008; }
  static get INDEX_DATA_TYPE_VISIBLE_STRING() { return 0x0009; }
  static get INDEX_DATA_TYPE_OCTET_STRING() { return 0x000A; }
  static get INDEX_DATA_TYPE_UNICODE_STRING() { return 0x000B; }
  static get INDEX_DATA_TYPE_TIME_OF_DAY() { return 0x000C; }
  static get INDEX_DATA_TYPE_TIME_DIFFERENCE() { return 0x000D; }
  static get INDEX_DATA_TYPE_DOMAIN() { return 0x000E; }
  static get INDEX_DATA_TYPE_INTEGER24() { return 0x0010; }
  static get INDEX_DATA_TYPE_REAL64() { return 0x0011; }
  static get INDEX_DATA_TYPE_INTEGER40() { return 0x0012; }
  static get INDEX_DATA_TYPE_INTEGER48() { return 0x0013; }
  static get INDEX_DATA_TYPE_INTEGER56() { return 0x0014; }
  static get INDEX_DATA_TYPE_INTEGER64() { return 0x0015; }
  static get INDEX_DATA_TYPE_UNSIGNED24() { return 0x0016; }
  static get INDEX_DATA_TYPE_UNSIGNED40() { return 0x0017; }
  static get INDEX_DATA_TYPE_UNSIGNED48() { return 0x0018; }
  static get INDEX_DATA_TYPE_UNSIGNED56() { return 0x0019; }
  static get INDEX_DATA_TYPE_UNSIGNED64() { return 0x001A; }

  constructor(init={}) {
    this[CanOpenObjectDictionary.INDEX_DATA_TYPE_BOOLEAN] = new CanOpenObject({
      0x00: new CanOpenSubObject({
        parameterName: "BOOLEAN",
        accessType: CanOpenObjectAccessType.CONST,
        objectType: CanOpenObjectType.DEFTYPE,
        dataType: CanOpenObjectDictionary.INDEX_DATA_TYPE_UNSIGNED32,
        defaultValue: 0x00000001
      })
    });
    Object.assign(this, init);
  }
}

class CanOpenObjectAccessType {
  static get RO() { return "ro"; }
  static get WO() { return "wo"; }
  static get RW() { return "rw"; }
  static get RWR() { return "rwr"; }
  static get RWW() { return "rww"; }
  static get CONST() { return "const"; }
}

class CanOpenObjectType {
  static get NULL() { return 0; }
  static get DOMAIN() { return 2; }
  static get DEFTYPE() { return 5; }
  static get DEFSTRUCT() { return 6; }
  static get VAR() { return 7; }
  static get ARRAY() { return 8; }
  static get RECORD() { return 9; }
}

class CanOpenProtoObject {

}

class CanOpenObject extends CanOpenProtoObject {

}

class CanOpenSubObject extends CanOpenObject {
  constructor(...args) {
    super(...args)
    this.value = this.default_value
  }

  get buffer() {
    switch (this.dataType) {
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_BOOLEAN:
        return new Uint8Array([this.value & 1]).buffer;
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_INTEGER8:
        return new Int8Array([this.value]).buffer;
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_INTEGER16:
        return new Int16Array([this.value]).buffer;
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_INTEGER24:
        return ArrayBuffer.transfer(new Int32Array([this.value]).buffer, 3);
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_INTEGER32:
        return new Int32Array([this.value]).buffer;
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_INTEGER40:
        return ArrayBuffer.transfer(new BigInt64Array([this.value]).buffer, 5);
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_INTEGER48:
        return ArrayBuffer.transfer(new BigInt64Array([this.value]).buffer, 6);
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_INTEGER56:
        return ArrayBuffer.transfer(new BigInt64Array([this.value]).buffer, 7);
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_INTEGER64:
        return new BigInt64Array([this.value]).buffer;
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_UNSIGNED8:
        return new Uint8Array([this.value]).buffer;
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_UNSIGNED16:
        return new Uint16Array([this.value]).buffer;
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_UNSIGNED24:
        return ArrayBuffer.transfer(new Uint32Array([this.value]).buffer, 3);
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_UNSIGNED32:
        return new Uint32Array([this.value]).buffer;
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_UNSIGNED40:
        return ArrayBuffer.transfer(new BigUint64Array([this.value]).buffer, 5);
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_UNSIGNED48:
        return ArrayBuffer.transfer(new BigUint64Array([this.value]).buffer, 6);
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_UNSIGNED56:
        return ArrayBuffer.transfer(new BigUint64Array([this.value]).buffer, 7);
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_UNSIGNED64:
        return new BigUint64Array([this.value]).buffer;
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_REAL32:
        return new Float32Array([this.value]).buffer;
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_REAL64:
        return new Float64Array([this.value]).buffer;
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_VISIBLE_STRING:
        return new Uint8Array(this.value.split("").map(c => c.charCodeAt(0))).buffer;
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_UNICODE_STRING:
        return new Uint16Array(this.value.split("").map(c => c.charCodeAt(0))).buffer;
      default:
        return new Uint8Array(this.value).buffer;
    }
  }

  from(buffer) {
    switch (this.dataType) {
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_BOOLEAN:
        return new Uint8Array(buffer)[0] && true;
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_INTEGER8:
        return new Int8Array(buffer)[0];
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_INTEGER16:
        return new Int16Array(buffer)[0];
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_INTEGER24:
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_INTEGER32:
        return new Int32Array(buffer)[0];
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_INTEGER40:
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_INTEGER48:
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_INTEGER56:
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_INTEGER64:
        return new BigInt64Array(buffer)[0];
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_UNSIGNED8:
        return new Uint8Array(buffer)[0];
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_UNSIGNED16:
        return new Uint16Array(buffer)[0];
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_UNSIGNED24:
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_UNSIGNED32:
        return new Uint32Array(buffer)[0];
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_UNSIGNED40:
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_UNSIGNED48:
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_UNSIGNED56:
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_UNSIGNED64:
        return new BigUint64Array(buffer)[0];
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_REAL32:
        return new Float32Array(buffer)[0];
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_REAL64:
        return new Float64Array(buffer)[0];
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_VISIBLE_STRING:
        return new TextDecoder("ascii").decode(buffer);
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_UNICODE_STRING:
        return new TextDecoder("utf-16").decode(buffer);
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_TIME_OF_DAY:
        return CanOpenTimeOfDay.from(buffer);
      case CanOpenObjectDictionary.INDEX_DATA_TYPE_TIME_DIFFERENCE:
        return CanOpenTimeDifference.from(buffer);
      default:
        return buffer;
    }
  }
}

class CanOpenNode {
  constructor(id, od, ws) {
    this.id = id;
    this.default_od = od;
    this.ws = ws;
    this.nmtState = CanOpenNmtState.INITIALISATION;
    this.listener = this.recv.bind(this);
    this.ws.addEventListener("message", this.listener);
    this.reset()
  }

  boot() {
    this.ws.send(new CanOpenBootupMessage(this.id));
    this.nmtState = CanOpenNmtState.PREOPERATIONAL;
    let node = this;
    this.heartbeatTimer = setInterval(function() { node.sendHeartbeat(); }, 1000); // TODO: Lookup period
  }

  recv(event) {
    let msg = event.data;
    switch (msg.functionCode) {
      case CanOpenMessage.FUNCTION_CODE_NMT:
        if (msg.data[1] == 0 || msg.data[1] == this.id) {
          switch (msg.data[0]) {
            case CanOpenNmtNodeControlMessage.CS_START:
              this.nmtState = CanOpenNmtState.OPERATIONAL;
              break;
            case CanOpenNmtNodeControlMessage.CS_STOP:
              this.nmtState = CanOpenNmtState.STOPPED;
              break;
            case CanOpenNmtNodeControlMessage.CS_ENTER_PREOPERATIONAL:
              this.nmtState = CanOpenNmtState.PREOPERATIONAL;
              break;
            case CanOpenNmtNodeControlMessage.CS_RESET_NODE:
              this.reset();
              break;
            case CanOpenNmtNodeControlMessage.CS_RESET_COMMUNICATION:
              this.resetCommunication();
              break;
            default:
          }
        }
        break;
      case CanOpenMessage.FUNCTION_CODE_SDO_RX:
        if (msg.nodeId != this.id) { return; }
        let cs = msg.data[0] >> CanOpenSdoMessage.CS_BITNUM;
        let index = new Uint16Array(msg.data.slice(1, 3).buffer)[0]
        let subIndex = msg.data[3];
        switch (cs) {
          case CanOpenSdoMessage.CCS_DOWNLOAD_INITIATE:
            if (index in this.od) {
              let obj = this.od[msg.index];
              if ((obj instanceof Object) && (subIndex in obj)) {
                let subObj = obj[subIndex];
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
        case CanOpenSdoMessage.CCS_UPLOAD_INITIATE:
          if (index in this.od) {}
          break;
      case CanOpenMessage.FUNCTION_CODE_SDO_TX:
        break;
      }
    }
  }

  reset() {
    this.od = this.default_od;
    this.nmtState = CanOpenNmtState.INITIALISATION;
    this.resetCommunication();
  }

  resetCommunication() {
    this.resetTimers();
    this.nmtState = CanOpenNmtState.INITIALISATION;
    this.boot()
  }

  resetTimers() {
    if (this.hasOwnProperty("heartbeatTimer")) {
      clearInterval(this.heartbeatTimer);
    }
  }

  send(msg) {
    this.ws.send(msg);
  }

  sendHeartbeat() {
    this.send(new CanOpenHeartbeatMessage(this.id, this.nmtState));
  }
}
