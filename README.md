About
==========

Modules
-------

This repository contains a Python module used for instantiating CANopen nodes in Linux, especially for a Raspberry Pi.  The first module, `socketcan`, abstracts the CAN interface by providing `Bus` and `Message` classes.  The `socketcan` module can be used to create adaptors to translate CAN traffic to other protocols.  The second module, `socketcanopen`, contains classes to instantiate a CANopen node application.  Each node must be initialized with at least one `can.BusABC`, a node ID (integer, 1 to 127), and an `socketcanopen.ObjectDictionary`.

Node Applications
-------------------------

Example node applications are provided:
* `canopen-node-sdo.py` is the simplest implentation of a node that supports SDO communication.
* `canopen-node-sdo-normal.py` has object dictionary entries with values greater than 4 bytes to demonstrate normal (non-expedited) SDO.
* `canopen-node-eds.py` imports the CANopen object dictionary from an EDS file (`node.eds`).
* `canopen-node-pdo.py` adds synchronous PDO support.
* `canopen-master.py` is a complex example of a CANopen Master that involves using GPIOs and how to interact with changes to the object dictionary.

`systemd` `.service` unit files and instructions for starting the node applications at boot are also provided.

Protocol Adaptors
-----------------

Example protocol adaptors are provided: Note that these are very crude and do not provide buffering.
* CANopen-to-HTTP (`canopen-http.py`, implementation of CiA 309-5)
* CAN-to-WebSocket (`websocketcan-server.py`, uses SocketCAN message structure; `websocketcan.js` and `websocketcanopen.js` provide wrappers to JavaScript's WebSocket, which can be used to decode messages in client browser)

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

2. Reboot to enable the MCP2515 drivers.

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
    sudo apt install can-utils
    ```

Library Usage
=============

Installation
------------
1. `git clone https://github.com/bggardner/canopen-rpi.git`
1. `cd canopen-rpi`
1. `pip3 install -e .`

The simplest node is presented in the [canopen-node-sdo.py](/examples/canopen-node-sdo.py) file.

Alternatively, `node.listen(True)` can be replaced with `node.process_msg(msg: socketcanopen.Message)` to manually send messages to the node, or `node.listen()` .  This is useful when there is a need to interface with the node's object dictionary (accessible from `node.od`) during operation, as `Node.listen(True)` is blocking and `Node.process_msg(msg: can.Message)` and `Node.listen()` are not. 

Example: Configure as CANopen Master with CAN-to-HTTP Adapter on Boot
---------------------------------------------------------------------

8. Setup CANopen Master
    1. Copy [canopen-master.py](/examples/canopen-master.py) to `/home/pi/`
    2. Copy [canopen-master.service](/unit-files/canopen-master.service) to `/etc/systemd/service/` and configure with `systemctl` like `can_if.service` above

8. Setup CAN-to-WebSocket Adapter
    1. Copy [websocketcan-server.py](/examples/websocketcan-server.py) to `/home/pi/`
    2. Copy [websocketcan-server.service](/unit-files/websocketcan-server.service) to `/etc/systemd/service/` and configure with `systemctl` like `can_if.service` above

