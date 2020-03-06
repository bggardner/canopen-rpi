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
   * Dispatches an Event to the WebSocket, casting MessageEvent data (a CanMessage) to a byte array
   * @param {Event} event - The event to be dispatched
   * @returns {boolean}
   */
  dispatchEvent(event) {
    if (event.type == "message") {
      event.data = new Uint8Array(event.data).buffer;
    }
    return super.dispatchEvent(event);
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
   * Enqueues the specified CanMessage to be transmitted to the server over the WebSocket connection.
   * @param {CanMessage} msg - The CanMessage to send to the server.
   */
  send(msg) {
    super.send(new Uint8Array(msg).buffer);
  }

  /**
   * Casts a CanMessage from MessageEvent data and passes it to handleMessageEvent()
   * @protected
   * @param {MessageEvent} event
   */
  messageEventHandler(event) {
    let init = Object.assign({}, event);
    init.data = CanMessage.from(new Uint8Array(event.data));
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

/** Class for sending data on a WebSocketCan */
class CanMessage {
  /**
   * Create a new CanMessage.
   * @param {number} arbitrationId - CAN frame abritration ID
   * @param {TypedArray} data - CAN frame data bytes
   * @param {boolean} eff - CAN frame Extended Frame Format flag
   * @param {boolean} rtr - CAN frame Remote Transmission Request flag
   * @param {boolean} err - CAN error frame flag
   */
  constructor(arbitrationId, data=[], eff=false, rtr=false, err=false) {
    this.arbitrationId = parseInt(arbitrationId);
    this.data = data;
    this.eff = Boolean(eff);
    this.rtr = Boolean(rtr);
  }

  [Symbol.iterator]() { // For converting to a byte array in SocketCAN format
    let message = this;
    return {
      next() {
        switch(this.cursor_++) {
          case 0:
            return {value: (message.arbitrationId >> 0) & 0xFF, done: false};
          case 1:
            return {value: (message.arbitrationId >> 8) & 0xFF, done: false};
          case 2:
            return {value: (message.arbitrationId >> 16) & 0xFF, done: false};
          case 3:
            return {value: ((message.arbitrationId >> 24) & 0x1F) + (+message.eff << 7) + (+message.rtr << 6) + (+message.err << 5), done: false};
          case 4:
            return {value: message.data.length, done: false};
          case 5:
          case 6:
          case 7:
            return {value: 0, done: false};
          case 8:
          case 9:
          case 10:
          case 11:
          case 12:
          case 13:
          case 14:
          case 15:
            return {value: message.data[this.cursor_ - 9] == undefined ? 0 : message.data[this.cursor_ - 9], done: false};
          case 16:
            this.cursor_ = 0;
            return {done: true};
          default:
        }
      },
      cursor_: 0
    }
  }

  /**
   * Factory function for converting raw bytes to a CanMessage instance.
   * @param {Uint8Array} byteArray - Byte array from the raw WebSocket message data
   * @returns {CanMessage}
   */
  static from(byteArray) { // Factory from SocketCAN-formatted byte array
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
