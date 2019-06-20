About
==========

Modules
-------

This repository contains two Python modules used for instantiating CANopen nodes in Linux, especially for a Raspberry Pi.  The first module, `CAN.py`, abstracts the CAN interface by providing `Bus` and `Message` classes.  The `CAN.py` module can be used to create adaptors to translate CAN traffic to other protocols.  The second module, `CANopen.py`, contains classes to instantiate a CANopen node application.  Each node must be initialized with at least one `CAN.Bus`, a node ID (integer, 1 to 127), and an `CANopen.ObjectDictionary`.

Node Applications
-------------------------

Example node applications are provided:
* `canopen-node-sdo.py` is the simplest implentation of a node that supports SDO communication.
* `canopen-node-eds.py` imports the CANopen object dictionary from an EDS file (`node.eds`).
* `canopen-node-pdo.py` adds synchronous PDO support.
* `canopen-master.py` is a complex example of a CANopen Master that involves using GPIOs and how to interact with changes to the object dictionary.

`systemd` `.service` files and instructions for starting the node applications at boot are also provided.

Protocol Adaptors
-----------------

Example protocol adaptors are provided: Note that these are very crude and do not provide buffering.
* CAN-to-HTTP (`canhttp.py`, see below for API)
* CAN-to-UDP (`canudp.py`, uses [SocketCAN](https://www.kernel.org/doc/Documentation/networking/can.txt) message structure)
* CANopen-to-HTTP (`canopen-http.py`, implementation of CiA 309-5)

Raspberry Pi Setup
==================

Install and Configure Raspbian
------------------------------


1. Install the latest version of [Raspbian](https://www.raspberrypi.org/downloads/raspbian/).

2. (Optional) Because of a [driver issue](https://github.com/raspberrypi/linux/issues/1317), you may need to add `dtoverlay=mmc` to `/boot/config.txt` for the Raspberry Pi to boot.

2. (Optional) Run `sudo raspi-config` and adjust internationalization options.

3. (Optional) Prevent flash memory corruption:

    1. Change `/etc/fstab` to:

        ```
        proc            /proc     proc    defaults          0   0
        /dev/mmcblk0p1  /boot     vfat    ro,noatime        0   2
        /dev/mmcblk0p2  /         ext4    defaults,noatime  0   1
        none            /var/log  tmpfs   size=1M,noatime   0   0
        ```

    2. Disable swap memory:

        ```
        sudo dphys-swapfile swapoff
        sudo dphys-swapfile uninstall
        sudo update-rc.d dphys-swapfile remove
        ```

    3. Reboot: `sudo reboot`

Add CAN Support
-----------------------------

1. Connect MCP2515 circuit(s) to the Raspberry Pi `SPI0` bus.  Interrupt GPIOs are defined in step 4.

1. If necessary, enable writable boot partition: `sudo mount -o remount,rw /dev/mmcblk0p1 /boot`

1. Run `sudo raspi-config`
    * Interfacing Options
        * SPI: Enable/Disable automatic loading (Yes)

2. Configure SPI Module: Change `/boot/config.txt` to:

    ```
    dtoverlay=mcp2515-can1,oscillator=16000000,interrupt=24
    dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=25
    ```
    *Note: It appears the order of the mcp2515-can\* overlay determines which SPI CE is used (first listing gets spi0.1/CE1, second listing get spi0.0/CE0), even though the documentation says otherwise.  See https://github.com/raspberrypi/linux/issues/1490 for more info.*
    
    *Note: The `oscillator` and `interrupt` parameters may be different for your application.*

3. Setup CAN interfaces
    * Manual

    ```
    sudo ip link set can0 up type can bitrate 1000000
    sudo ip link set can1 up type can bitrate 1000000
    ```
    * Automatic (start at boot-up)
        1. Copy [can_if](https://github.com/linux-can/can-misc/blob/master/etc/can_if) to `/home/pi/` (or change location in `can_if.service`
        2. Modify `can_if` line `CAN_IF=""` to `CAN_IF="can0@1000000,2000 can1@1000000,2000"` *(may vary per application)*
        2. Set `can_if` to be globally executable (`chmod +x can_if`)
        3. Copy `can_if.service` to `/etc/systemd/system/`
        4. `sudo systemctl daemon-reload`
        5. `sudo systemctl enable can_if.service`
        6. `sudo reboot` or `sudo systemctl start can_if.service`

4. (Optional) Install `can-utils` for debugging

    ```
    sudo apt-get install can-utils
    ```

Library Usage
-------------

The simplest node is presented in the [canopen-node-sdo.py](/canopen-node-sdo.py) file.

Alternatively, `node.listen(True)` can be replaced with `node.process_msg(msg: CANopen.Message)` to manually send messages to the node, or `node.listen()` .  This is useful when there is a need to interface with the node's object dictionary (accessible from `node.od`) during operation, as `Node.listen(True)` is blocking and `Node.process_msg(msg: CAN.Message)` and `Node.listen()` are not. 

Example: Configure as CANopen Master with CAN-to-HTTP Adapter on Boot
---------------------------------------------------------------------

8. Setup CANopen Master
    1. Copy [canopen-master.py](/canopen-master.py) to `/home/pi/`
    2. Copy [canopen-master.service](/canopen-master.service) to `/etc/systemd/service/` and configure with `systemctl` like `can_if.service` above

8. Setup CAN-to-HTTP Adapter
    1. Copy [canhttp.py](/canhttp.py) to `/home/pi/`
    2. Copy [canhttp.service](/canhttp.service) to `/etc/systemd/service/` and configure with `systemctl` like `can_if.service` above
    

HTTP to CAN API
========================
* The HTTP to CAN API uses the HTTP/1.1 protocol's GET method.
* Telemetry responses use the [server-side event API](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)

Telemetry
---------
When the host URL is accessed without query string parameters, a `text/event-stream` is opened and CAN traffic is streamed as JSON-encoded data-only events.  The JSON objects shall have the following attribute-value pairs:
* `bus`: Which CAN bus message was received (if multiple; 0 or 1 e.g.)
* `id`: 11-bit CAN identifier, in base 10
* `data`: Array of CAN data bytes (0-8 bytes), in base 10
* `ts`: ISO 8601 time-stamp of when the CAN message was received

*Note: This assumes the events can be supplied faster than CAN frames are received.  It is suggested that CAN frames be buffered, and an `error` event sent if the buffer overflows (see Errors section).*

**Example**

Request: `GET / HTTP/1.1`

Response: (one data-only event per CAN frame)
```
HTTP/1.1 200 OK
Access-Control-Origin: *
Content-Type: text/event-stream
Cache-Control: no-cache

data:{"bus": 0, "id": 123, "data":[255,128,5], "ts":"2015-12-21T10:36:30.123Z"}

data:{"bus": 1, "id": 157, "data":[], "ts":"2015-12-21T10:36:56.789Z"}
```

Commands
--------
When the host URL is accessed with a valid set of query string arguments listed below, the command is translated to a CAN frame.
* `id`: (required) The 11-bit CAN identifier, in base 10
* `data`: (optional) A JSON-encoded array of CAN data bytes (in base 10), having a length of 0-8.

**Example**

Request: `GET /?id=123&data=[255,128,5] HTTP/1.1`

Response:
```
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: *

```

Errors
======

If no query string is present, and the state of the CAN bus (or busses) are abnormal, an `error` event is streamed (once) if "bus-off" or a `warning` event if "error warning" (error count exceeds a threshold).  A `notice` event is streamed if the bus (or busses) return to a normal state.

**Example**

Request: `GET / HTTP/1.1`

Response:
```
HTTP/1.1 200 OK
Access-Control-Allow-Origin: *
Content-Type: text/event-stream
Cache-Control: no-cache

event: error
data: Bus 0 is in the bus-off state

event: warning
data: Bus 1 is in the warning state

event: notice
data: Bus 1 is now in a normal state

event: error
data: CAN RX buffer overflow on bus 1

```

If a query string is present, but the required command parameters do not exist or are invalid, then an HTTP 400 code shall be returned.  All other errors shall be formatted per the [JSON API](http://jsonapi.org/format/#error-objects).


**Example**

Request:

`GET /?badargument=1 HTTP/1.1` or

`GET /?id=4096&data=[] HTTP/1.1` (invalid id) or

`GET /?id=123&data=[256] HTTP/1.1` (invalid data byte) or

`GET /?id=123&data=[0,0,0,0,0,0,0,0,0]` (too many data bytes)

Response:
```
HTTP/1.1 400 Bad Request
Access-Control-Allow-Origin: *

```

**Example**

Request `GET /?id=123&data[] HTTP/1.1`

Response:
```
HTTP/1.1 200 OK
Access-Control-Allow-Origin: *

{"errors":[{"detail":"Message sent on bus 0, but bus 1 is in the bus-off state"}]}

```

**Example**

Request `GET /?id=123&data=[] HTTP/1.1`

Response:
```
HTTP/1.1 200 OK
Access-Control-Allow-Origin: *

{"errors":[{"detail":"Application-specific error message"}]}
```
