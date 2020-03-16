/**
 * Wrapper class that translates WebSocket message data to/from a CanMesssage instance
 * @extends WebSocket
 */
class WebSocketCan extends WebSocket {
  /**
   * Create WebSocketCan instance.
   * @ param {string} url - The URL to which to connect; this should be the URL to which the WebSocketCan server will respond.
   */
  constructor(url) {
    super(url); // TODO: Investigate passing a custom protocol to the superclass
    this.binaryType = "arraybuffer";
    /**
     * @private
     * @type {Array}
    */
    this.messageListeners_ = [];
  }

  /**
  * Wraps message listeners in a function that casts the message as a CanMessage
  * @param {string} type - A case-sensitive string representing the event type to listen for.
  * @param {object} listener - The object which receives a notification when an event of the specified type occurs.
  */
  addEventListener(type, listener) {
    if (type == "message") {
      if (!this.messageListeners_.includes(listener)) {
        this.messageListeners_.push(listener);
      }
      listener = this.messageEventHandler;
    }
    super.addEventListener(type, listener);
  }

  /**
  * Removes an event listener previously registered with addEventListener().
  * @param {string} type - A string which specifies the type of event for which to remove an event listener.
  * @param {object} listener - The EventListener function of the event handler to remove from the event target.
  */
  removeEventListener(type, listener) {
    if (type == "message") {
      this.messageListeners_.splice(this.messageListeners_.indexOf(listener), 1);
      listener = this.messageHandler_;
      if (this.messageListeners_.length) { return; }
    }
    super.removeEventListener(type, listener);
  }

  /**
   * @type {EventListener}
   */
  set onmessage(handler) {
    super.onmessage = this.messageEventHandler(handler);
  }

  /**
   * Re-casts a MessageEvent with CanMessage data and passes it to handleMessageEvent()
   * @protected
   * @param {MessageEvent} event
   */
  messageEventHandler(event) {
    // MessageEvent.data is read-only, must re-cast
    let init = Object.assign({}, event);
    init.data = CanMessage.from(event.data);
    event = new MessageEvent(event.type, init);
    this.handleMessageEvent(event);
  }

  /**
   * Calls message event listeners
   * @protected
   * @param {MessageEvent} event - Event constructed in messageHandler()
   */
  handleMessageEvent(event) {
    for (let i = 0; i < this.messageListeners_.length; i++) {
      let listener = this.messageListeners_[i];
      if (typeof listener.handleEvent != 'undefined') {
        listener.handleEvent(event);
      } else {
        listener.call(this, event);
      }
    }
  }
}

/**
   * Class for sending data on a WebSocketCan.  Must extend data type passed to Websocket.send().
   * @extends Uint8Array
   */
class CanMessage extends Uint8Array {
  /**
   * Create a new CanMessage.
   * @param {number} arbitrationId - CAN frame abritration ID
   * @param {iterable.<number>} [data=new ArrayBuffer()] - CAN frame data bytes
   * @param {boolean} eff - CAN frame Extended Frame Format flag
   * @param {boolean} rtr - CAN frame Remote Transmission Request flag
   * @param {boolean} err - CAN error frame flag
   */
  constructor(arbitrationId, data=new ArrayBuffer(), eff=false, rtr=false, err=false) {
    let dataView = new DataView(new ArrayBuffer(16));
    dataView.setUint32(0, arbitrationId + (err << 29) + (rtr << 30) + (eff << 31), true);
    data = new Uint8Array(data);
    dataView.setUint32(4, data.byteLength, true);
    super(dataView.buffer)
    this.set(data, 8);
  }

  get arbitrationId() { return new Uint32Array(this.buffer.slice(0, 4))[0] & 0x1FFFFFFF; }
  get data() { return new Uint8Array(this.buffer.slice(8, 8 + this.dlc)); }
  get dlc() { return this[4]; }
  get eff() { return Boolean(this[3] & 0x80); }
  get err() { return Boolean(this[3] & 0x20); }
  get rtr() { return Boolean(this[3] & 0x40); }

  /**
   * Factory function for converting raw bytes to a CanMessage instance.
   * @param {ArrayBuffer} buffer - Byte array from the raw WebSocket message data
   * @returns {CanMessage}
   */
  static from(buffer) { // Factory from SocketCAN-formatted byte array
      if (!(buffer instanceof ArrayBuffer) || buffer.byteLength != 16) { throw "Argument must be an ArrayBuffer of length 16"; }
      let byteArray = new Uint8Array(buffer);
      if ((byteArray[4] & 0xF0) != 0 || byteArray[5] != 0 || byteArray[6] != 0 || byteArray[7] != 0) { throw "Malformed SocketCAN message"; }
      let arbitrationId = byteArray[0];
      arbitrationId += byteArray[1] << 8;
      arbitrationId += byteArray[2] << 16;
      arbitrationId += (byteArray[3] & 0x1F) << 24;
      let eff = Boolean(byteArray[3] & 0x80);
      let rtr = Boolean(byteArray[3] & 0x40);
      let err = Boolean(byteArray[3] & 0x20);
      let dlc = byteArray[4];
      let data = byteArray.slice(8, 8 + dlc);
      return new this(arbitrationId, data, eff, rtr, err);
  }
}
