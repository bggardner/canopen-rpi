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
  }

  addEventListener(type, listener, useCapture, wantsUntrusted) {
    let wrapper = listener;
    if (type == "message") {
      wrapper = this._messageHandler(listener);
    }
    super.addEventListener(type, wrapper, useCapture, wantsUntrusted);
  }

  set onmessage(handler) {
    super.onmessage = this._messageHandler(handler);
  }

  send(msg) {
    let byteArray = new Uint8Array(msg);
    super.send(byteArray.buffer);
  }

  _messageHandler(handler) {
    return function(event) {
      let init = Object.assign({}, event);
      init.data = CanMessage.from(new Uint8Array(event.data));
      handler(new MessageEvent(event.type, init));
    }
  }
}
