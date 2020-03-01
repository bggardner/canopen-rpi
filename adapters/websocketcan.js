class CanMessage {
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
        switch(this._cursor++) {
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
            return {value: message.data[this._cursor - 9] == undefined ? 0 : message.data[this._cursor - 9], done: false};
          case 16:
            this._cursor = 0;
            return {done: true};
          default:
        }
      },
      _cursor: 0
    }
  }

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

class WebSocketCan extends WebSocket {
  constructor(url) {
    super(url);
    this.binaryType = "arraybuffer";
    this._messageListeners = [];
  }

  addEventListener(type, listener, useCapture, wantsUntrusted) {
    if (type == "message") {
      if (!this._messageListeners.includes(listener)) {
        this._messageListeners.push(listener);
      }
      listener = this._messageHandler;
    }
    super.addEventListener(type, listener, useCapture, wantsUntrusted);
  }

  removeEventListener(type, listener, useCapture) {
    if (type == "message") {
      this._messageListeners.splice(this._messageListeners.indexOf(listener), 1);
      listener = this._messageHandler;
      if (this._messageListeners.length) { return; }
    }
    super.removeEventListener(type, listener, useCapture);
  }

  set onmessage(handler) {
    super.onmessage = this._messageHandler(handler);
  }

  send(msg) {
    let byteArray = new Uint8Array(msg);
    super.send(byteArray.buffer);
  }

  _messageHandler(event) {
    let init = Object.assign({}, event);
    init.data = CanMessage.from(new Uint8Array(event.data));
    event = new MessageEvent(event.type, init);
    this._handleMessageEvent(event);
  }

  _handleMessageEvent(event) {
    for (let i = 0; i < this._messageListeners.length; i++) {
      let listener = this._messageListeners[i];
      if (typeof listener.handleEvent != 'undefined') {
        listener.handleEvent(event);
      } else {
        listener.call(this, event);
      }
    }
  }
}
