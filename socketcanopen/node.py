# TODO: OSErrors / can.CanErrors are thrown if the CAN bus goes down, need to do threaded Exception handling
#      See http://stackoverflow.com/questions/2829329/catch-a-threads-exception-in-the-caller-thread-in-python
# TODO: Check for BUS-OFF before attempting to send
# TODO: NMT error handler (CiA302-2)
from binascii import crc_hqx
import can
import copy
import datetime
import io
import logging
import math
import os
import struct
import threading
import time

from .constants import *
from .indicators import *
from .messages import *
from .object_dictionary import *

logger = logging.getLogger(__name__)

class IntervalTimer(threading.Thread):
    """Call a function every specified number of seconds:

            t = IntervalTimer(30.0, function, args=None, kwargs=None)
            t.start()
            t.cancel()    # stop the timer's action if it's still running
    """

    def __init__(self, interval, function, args=None, kwargs=None):
        super().__init__(args=args, kwargs=kwargs, daemon=True)
        self.interval = interval
        self.function = function
        self.args = args if args is not None else []
        self.kwargs = kwargs if kwargs is not None else {}
        self.finished = threading.Event()

    def cancel(self):
        self.finished.set()

    def run(self):
        next_run = time.time() + self.interval
        while not self.finished.wait(next_run - time.time()):
            if self.finished.is_set():
                break
            threading.Thread(target=self.function, args=self.args, kwargs=self.kwargs, daemon=True).start()
            next_run += self.interval


class NmtSlaveBootError(Exception):

    def __init__(self, status):
        self.status = status


class SdoAbort(Exception):

    def __init__(self, index, subindex, code):
        self.index = index
        self.subindex = subindex
        self.code = code


class SdoRequestEvent(threading.Event):

    def __init__(self, index, subindex):
        super().__init__()
        self.index = index
        self.subindex = subindex
        self._response = None

    def respond(self, data):
        self._response = data
        self.set()

    @property
    def response(self):
        return self._response


class SdoTimeout(SdoAbort):

    def __init__(self, index, subindex):
        super().__init__(index, subindex, SDO_ABORT_TIMEOUT)


class Listener(can.Listener):

    def __init__(self, msg_handler, err_handler, channel):
        self.msg_handler = msg_handler
        self.err_handler = err_handler
        self.channel = channel

    def on_message_received(self, msg: can.Message):
        self.msg_handler(msg)

    def on_error(self, exc: Exception):
        self.err_handler(self.channel)


class Node:

    SDO_TIMEOUT = 5 #0.3
    SDO_ROUND_TRIP_TIME = 222e-6

    def __init__(self, bus: can.BusABC, id, od: ObjectDictionary, *args, **kwargs):
        self.default_bus = bus
        self._notifier = can.Notifier(self.default_bus, [])
        self._listener = Listener(self._process_msg, self._on_can_error, self.default_bus.channel)

        if id > 0x7F or id <= 0:
            raise ValueError("Invalid Node ID")
        self.id = id
        self.od = od

        if "err_indicator" in kwargs:
            if not isinstance(kwargs["err_indicator"], ErrorIndicator):
                raise TypeError
            self._err_indicator = kwargs["err_indicator"]
            if "redundant_err_indicator" in kwargs:
                if not isinstance(kwargs["redundant_err_indicator"], ErrorIndicator):
                    raise TypeError
                self._redundant_err_indicator = kwargs["redundant_err_indicator"]
            # TODO: Move this to reset()
            self._process_err_indicator()
            self._err_indicator_timer = IntervalTimer(self._err_indicator.interval , self._process_err_indicator)
            self._err_indicator_timer.start()
        else:
            self._err_indicator = None
            self._err_indicator_timer = None
        self._err_indicator_timer_lock = threading.Lock()

        if "run_indicator" in kwargs:
            if not isinstance(kwargs["run_indicator"], RunIndicator):
                raise TypeError
            self._run_indicator = kwargs["run_indicator"]
            if "redundant_run_indicator" in kwargs:
                if not isinstance(kwargs["redundant_run_indicator"], RunIndicator):
                    raise TypeError
                self._redundant_run_indicator = kwargs["redundant_run_indicator"]
            else:
                self.redundant_run_indicator = None
        else:
            self._run_indicator = None
            self._redundant_run_indicator = None

        self._default_bus_heartbeat_disabled = False
        self._emcy_inhibit_time = 0
        self._first_boot = True
        self._heartbeat_consumer_timers = {}
        self._heartbeat_consumer_timers_lock = threading.Lock()
        self._heartbeat_evaluation_counters = {}
        self._heartbeat_evaluation_power_on_timer = None
        self._heartbeat_evaluation_power_on_timer_lock = threading.Lock()
        self._heartbeat_evaluation_reset_communication_timer = None
        self._heartbeat_evaluation_reset_communication_timer_lock = threading.Lock()
        self._heartbeat_producer_timer = None
        self._heartbeat_producer_timer_lock = threading.Lock()
        self._message_timers = []
        self._message_timers_lock = threading.Lock()
        self._nmt_active_master = False
        self._nmt_active_master_id = None
        self._nmt_active_master_timer = None
        self._nmt_active_master_timer_lock = threading.Lock()
        self._nmt_boot_timer = None
        self._nmt_boot_timer_lock = threading.Lock()
        self._nmt_boot_time_expired = True
        self._nmt_flying_master_timer = None
        self._nmt_flying_master_timer_lock = threading.Lock()
        self._nmt_inhibit_time = 0
        self._nmt_multiple_master_timer = None
        self._nmt_multiple_master_timer_lock = threading.Lock()
        self._nmt_slave_booters = {}
        self._nmt_slave_states = {}
        self._pending_emcy_msgs = []
        self._redundant_nmt_state = None
        self._redundant_reset_communication_thread = None
        self._sdo_cs = None
        self._sdo_data = None
        self._sdo_data_type = None
        self._sdo_len = None
        self._sdo_odi = None
        self._sdo_odsi = None
        self._sdo_requests = {}
        self._sdo_seqno = 0
        self._sdo_t = None
        self._sync_counter = 0
        self._sync_producer_counter = 1
        self._sync_timer = None
        self._sync_timer_lock = threading.Lock()
        self._timedelta = datetime.timedelta()
        self._tpdo_inhibit_times = {}
        self._tpdo_triggers = [False, False, False, False]

        if od.get(ODI_REDUNDANCY_CONFIGURATION) is not None and "redundant_bus" in kwargs:
            if not isinstance(kwargs["redundant_bus"], can.BusABC):
                raise TypeError
            self.redundant_bus = kwargs["redundant_bus"]
            self._redundant_notifier = can.Notifier(self.redundant_bus, [])
            self._redundant_listener = Listener(self._process_msg, self._on_can_error, self.redundant_bus.channel)
        else:
            self.redundant_bus = None
            self._redundant_notifer = None
            self._redundant_listener = None

        self.reset()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._cancel_timer(self._heartbeat_evaluation_power_on_timer)
        self._reset_timers()

    def _boot(self, channel):
        logger.info(f"Booting on {channel} with node-ID of {self.id}")
        self._send(BootupMessage(self.id), channel)
        self.nmt_state = (NMT_STATE_PREOPERATIONAL, channel)
        self._start_listening(channel)
        self._process_heartbeat_producer()
        self._process_sync()
        if self._redundant_reset_communication_thread is not None and channel == self.default_bus.channel:
            self._redundant_reset_communication_thread.join()
            self._redundant_reset_communication_thread = None
        if channel == self.active_bus.channel:
            threading.Thread(target=self._nmt_startup, daemon=True).start()

    @staticmethod
    def _cancel_timer(timer: threading.Timer):
        if timer is not None and timer.is_alive():
            timer.cancel()
            return True
        return False

    def _heartbeat_consumer_timeout(self, id):
        logger.warning(f"Heartbeat consumer timeout for node-ID {id}")
        self._heartbeat_evaluation_counters[id] = 0 # For start service error control during NMT slave boot
        self.emcy(EMCY_HEARTBEAT_BY_NODE + id)
        request_nmt_obj = self.od.get(ODI_REQUEST_NMT)
        if request_nmt_obj is not None:
            request_nmt_subobj = request_nmt_obj.get(id)
            request_nmt_subobj.value = 0x01 # CANopen device is missing
            request_nmt_obj.update({id: request_nmt_subobj})
            self.od.update({ODI_REQUEST_NMT: request_nmt_obj})

    def _heartbeat_evaluation_power_on_timeout(self):
        logger.info("Heartbeat evaluation timer (power-on) expired")
        if len(self._heartbeat_evaluation_counters.values()) == 0 or max(self._heartbeat_evaluation_counters.values()) < 3: # CiA 302-6, Figure 7, event (4)
            logger.warning(f"Heartbeat evaluation counter length = {len(self._heartbeat_evaluation_counters.values())}, max = {max(self._heartbeat_evaluation_counters.values()) if len(self._heartbeat_evaluation_counters.values()) > 0 else 'None'}")
            self.active_bus = self.redundant_bus
        # else: CiA 302-6, Figure 7, event (1)
        self._heartbeat_evaluation_counters = {}
        self.send_nmt(NmtIndicateActiveInterfaceMessage())

    def _heartbeat_evaluation_reset_communication_timeout(self):
        logger.info("Heartbeat evaluation timer (reset communication) expired")
        if self.active_bus == self.default_bus:
            if len(self._heartbeat_evaluation_counters.values()) > 0 and min(self._heartbeat_evaluation_counters.values()) == 0: # CiA 302-6, Figure 7, event (6)
                self.active_bus = self.redundant_bus
                self.send_nmt(NmtIndicateActiveInterfaceMessage())
        else:
            if len(self._heartbeat_evaluation_counters.values()) > 0 and max(self._heartbeat_evaluation_counters.values()) >= 3: # CiA 302-6, Figure 7, event (8)
                self.active_bus = self.default_bus
                self.send_nmt(NmtIndicateActiveInterfaceMessage())

    def _nmt_active_master_timeout(self, first_boot=None):
        if first_boot is None:
            first_boot = self._first_boot
        elif first_boot is True:
            logger.info("Active NMT master failure detected")
        if first_boot:
            logger.debug("Active NMT master timeout from power-on or failure, Reset Communication on all nodes")
            self._first_boot = False
            self.send_nmt(NmtNodeControlMessage(NMT_NODE_CONTROL_RESET_COMMUNICATION, 0))
            self._nmt_flying_master_startup()
        else:
            logger.debug("Active NMT master timeout after reboot")
            self._nmt_flying_master_negotiation_request()

    def _nmt_become_active_master(self):
        logger.info("Device is active NMT master")
        self._nmt_boot_time_expired = False
        self._nmt_active_master = True
        # See CiA 302-2 v4.1.0, section 5.5.3
        nmt_flying_master_timing_params = self.od.get(ODI_NMT_FLYING_MASTER_TIMING_PARAMETERS)
        nmt_multiple_master_detect_time = nmt_flying_master_timing_params.get(ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_DETECT_TIME).value / 1000
        with self._nmt_multiple_master_timer_lock:
            self._cancel_timer(self._nmt_multiple_master_timer)
            self._nmt_multiple_master_timer = IntervalTimer(nmt_multiple_master_detect_time, self._send, [NmtForceFlyingMasterRequest()])
            self._nmt_multiple_master_timer.start()
        threading.Thread(target=self.on_active_nmt_master_won, daemon=True).start()

        # CiA 302-2 section 3.1
        all_slaves = []
        mandatory_slaves = []
        reset_communication_slaves = []
        slave_assignment_obj = self.od.get(ODI_NMT_SLAVE_ASSIGNMENT)
        keep_alive_slave_count = 0
        if slave_assignment_obj is not None:
            slave_assignment_obj_length = slave_assignment_obj.get(ODSI_VALUE).value
            for slave_id in range(1, slave_assignment_obj_length + 1):
                slave_assignment = slave_assignment_obj.get(slave_id).value
                if slave_assignment & 0x01: # Bit 0: NMT Slave
                    all_slaves.append(slave_id)
                    if slave_assignment & 0x08: # Bit 3: Mandatory
                        mandatory_slaves.append(slave_id)
                    if slave_assignment & 0x10: # Bit 4: Reset Communication
                        keep_alive_slave_count += 1
                    else:
                        reset_communication_slaves.append(slave_id)
        if slave_assignment_obj is None or keep_alive_slave_count == 0:
            logger.info("No keep alive nodes, reset communication to all")
            self.send_nmt(NmtNodeControlMessage(NMT_NODE_CONTROL_RESET_COMMUNICATION, 0))
        else:
            for slave_id in reset_communication_slaves:
                logger.info(f"Resetting communication for slave with node-ID {slave_id}")
                self.send_nmt(NmtNodeControlMessage(NMT_NODE_CONTROL_RESET_COMMUNICATION, slave_id))

        # Start process boot NMT slave
        for slave_id in self._nmt_slave_booters:
            self._nmt_slave_booters[slave_id]["thread"].join() # Prefer to kill thread instead of wait for join
        boot_time_obj = self.od.get(ODI_BOOT_TIME)
        if boot_time_obj is not None:
            boot_time = boot_time_obj.get(ODSI_VALUE).value / 1000
            if boot_time > 0:
                with self._nmt_boot_timer_lock:
                    self._cancel_timer(self._nmt_boot_timer)
                    self._nmt_boot_timer = threading.Timer(boot_time, self._nmt_boot_timeout)
                    self._nmt_boot_timer.start()
        self._nmt_slave_booters = {}
        for slave_id in all_slaves:
            logger.info(f"Booting NMT slave with node-ID {slave_id}...")
            self._nmt_slave_booters[slave_id] = {"thread": threading.Thread(target=self._nmt_boot_slave, args=(slave_id,), daemon=True), "status": None, "read": False}
            self._nmt_slave_booters[slave_id]["thread"].start()
        mandatory_slaves_booted = 0
        while (len(mandatory_slaves) > mandatory_slaves_booted) and not self._nmt_boot_time_expired:
            mandatory_slaves_booted = 0
            for slave_id in mandatory_slaves:
                booter = self._nmt_slave_booters.get(slave_id)
                if booter.get("status") is not None and not booter.get("read"):
                    booter["read"] = True
                    if booter.get("status") == "OK":
                        mandatory_slaves_booted += 1
                        logger.info(f"Boot NMT slave succeeded for node-ID {slave_id}")
                    else:
                        logger.error(f"Boot NMT slave error for node-ID {slave_id} with code {booter.get('status')}")
            time.sleep(1)
        if self._nmt_boot_time_expired:
            logger.warning("NMT boot time expired before all mandatory slaves booted, halting NMT boot")
            self.on_error("nmt_boot_timeout", self._nmt_slave_booters)
            return
        with self._nmt_boot_timer_lock:
            self._cancel_timer(self._nmt_boot_timer)
        self._nmt_boot_time_expired = True
        logger.info(f"All mandatory slaves booted ({mandatory_slaves_booted})")
        # End process boot NMT slave

        nmt_startup = self.od.get(ODI_NMT_STARTUP).get(ODSI_VALUE).value
        if (nmt_startup & 0x04) == 0:
            logger.debug("Self-starting")
            self.nmt_state = NMT_STATE_OPERATIONAL

    def _nmt_become_inactive_master(self):
        logger.info("Device is not active NMT master, running in NMT slave mode")
        self._nmt_active_master = False
        with self._nmt_active_master_timer_lock:
            self._cancel_timer(self._nmt_active_master_timer)
            if self._nmt_active_master_id not in self._heartbeat_consumer_timers: # See CiA 302-2 v4.1.0, section 5.5.2
                logger.debug("Active NMT master not in heartbeat consumers; timeout will be twice heartbeat producer time")
                heartbeat_producer_time = self.od.get(ODI_HEARTBEAT_PRODUCER_TIME).get(ODSI_VALUE).value
                self._nmt_active_master_timer = threading.Timer(heartbeat_producer_time * 2 / 1000, self._nmt_active_master_timeout, [True])
                self._nmt_active_master_timer.start()
        threading.Thread(target=self.on_active_nmt_master_lost, daemon=True).start()

    def _nmt_boot_slave(self, slave_id):
        nmt_slave_assignment = self.od.get(ODI_NMT_SLAVE_ASSIGNMENT).get(slave_id).value
        logger.debug(f"Entering boot NMT slave process for node-ID {slave_id} with assignment 0x{nmt_slave_assignment:08X}")
        try:
            if (nmt_slave_assignment & 0x01) == 0: # Is NMT slave node-ID still in network list?
                raise NmtSlaveBootError(slave_id, "A")
            route_d = False
            route_e = True
            if nmt_slave_assignment & 0x03: # Boot NMT slave?
                route_e = False
                logger.info(f"Requesting device type during NMT slave boot for node-ID {slave_id}")
                while True:
                    try:
                        slave_device_type = self._sdo_upload_request(slave_id, ODI_DEVICE_TYPE, ODSI_VALUE)
                        break
                    except SdoAbort as e:
                        self._nmt_slave_booters[slave_id]["status"] = "B"
                        if nmt_slave_assignment & 0x08 and self._nmt_boot_time_expired: # Mandatory and boot time expired?
                            raise NmtSlaveBootError("B")
                        logger.error(f"Failed to get device type during NMT slave boot for node-ID {slave_id}, retrying...")
                        time.sleep(1)
                slave_device_type = int.from_bytes(slave_device_type, byteorder="little")
                logger.info(f"Received SDO response from slave ID {slave_id} with device type of 0x{slave_device_type:08X}")
                device_type_id_obj = self.od.get(ODI_DEVICE_TYPE_IDENTIFICATION)
                if device_type_id_obj is not None:
                    device_type_id_subobj = device_type_id_obj.get(slave_id)
                    if device_type_id_subobj is not None and device_type_id_subobj.value != 0 and device_type_id_subobj.value != slave_device_type:
                        raise NmtSlaveBootError("C")
                for index, error_status in {
                    ODI_VENDOR_IDENTIFICATION: "D",
                    ODI_PRODUCT_CODE: "M",
                    ODI_REVISION_NUMBER: "N",
                    ODI_SERIAL_NUMBER: "O"
                }.items():
                    obj = self.od.get(index)
                    if obj is None:
                        continue
                    subobj = obj.get(slave_id)
                    if subobj is not None and subobj.value != 0:
                        try:
                            response = self._sdo_upload_request(slave_id, ODI_IDENTITY, index - ODI_DEVICE_TYPE_IDENTIFICATION)
                        except:
                            raise NmtSlaveBootError(error_status)

                # Begin Route B
                if nmt_slave_assignment & 0x10: # Keep-alive?
                    # Check NMT state per CiA 302-6 section 3.6
                    heartbeat_consumer_time = 0
                    heartbeat_consumer_time_obj = self.od.get(ODI_HEARTBEAT_CONSUMER_TIME)
                    if heartbeat_consumer_time_obj is not None:
                        for subindex in range(1, heartbeat_consumer_time_obj.get(ODSI_VALUE).value + 1):
                            heartbeat_consumer_time_value = heartbeat_consumer_time_obj.get(subindex).value
                            if (heartbeat_consumer_time_value >> 16) & 0x7F == slave_id:
                                heartbeat_consumer_time = heartbeat_consumer_time_value & 0xFFFF
                                break
                    if heartbeat_consumer_time > 0:
                        del self._nmt_slave_states[slave_id]
                        with self._heartbeat_consumer_timers_lock:
                            self._cancel_timer(self._heartbeat_consumer_timers.get(slave_id))
                            # Set timer to be longer than timeout (arbitrarily choosing 1 second)
                            self._heartbeat_consumer_timers[slave_id] = threading.Timer(heartbeat_consumer_time + 1, lambda: None)
                            self._heartbeat_consumer_timers.get(slave_id).start() # If heartbeat is received, timer is cancelled in _process_msg()
                        self._heartbeat_consumer_timers[slave_id].join(heartbeat_consumer_time & 0xFFFF) # Wait for timeout
                        heartbeat_event = self._heartbeat_consumer_timers.get(slave_id).is_alive() # If timer is still alive, then no heartbeat was received
                        self._cancel_timer(self._heartbeat_consumer_timers.get(slave_id))
                        if heartbeat_event:
                            raise NmtSlaveBootError("E")
                    else:
                        node_guard_request = NmtErrorControlMessage(slave_id, [])
                        node_guard_request.is_remote_frame = True
                        self._send(node_guard_request)
                        with self._heartbeat_consumer_timers_lock:
                            self._cancel_timer(self._heartbeat_consumer_timers.get(slave_id))
                            self._heartbeat_consumer_timers[slave_id] = threading.Timer(0.1, lambda: None)
                            self._heartbeat_consumer_timers.get(slave_id).start() # If heartbeat is received, timer is cancelled in _process_msg()
                        heartbeat_event = self._heartbeat_consumer_timers.get(slave_id).is_alive() # If timer is still alive, then no heartbeat was received
                        self._cancel_timer(self._heartbeat_consumer_timers.get(slave_id))
                        if heartbeat_event:
                            raise NmtSlaveBootError("F")
                    if self._nmt_slave_states.get(slave_id) == NMT_STATE_OPERATIONAL:
                        route_d = True
                    else:
                        self.send_nmt(NmtNodeControlMessage(NMT_NODE_CONTROL_RESET_COMMUNICATION, slave_id))
                if not route_d:
                    if nmt_slave_assignment & 0x20: # Software version check?
                        pass

                    # Begin Route C
                    expected_cfg_date = 0
                    expected_cfg_date_obj = self.od.get(ODI_EXPECTED_CONFIGURATION_DATE)
                    if expected_cfg_date_obj is not None:
                        expected_cfg_date = expected_cfg_date_obj.get(slave_id).value
                    expected_cfg_time = 0
                    expected_cfg_time_obj = self.od.get(ODI_EXPECTED_CONFIGURATION_TIME)
                    if expected_cfg_time_obj is not None:
                        expected_cfg_time = expected_cfg_time_obj.get(slave_id).value
                    update_configuration = True
                    if expected_cfg_date != 0 and expected_cfg_time != 0:
                        try:
                            cfg_date = int.from_bytes(self._sdo_upload_request(slave_id, ODI_VERIFY_CONFIGURATION, ODSI_VERIFY_CONFIGURATION_DATE), byteorder="little")
                            cfg_time = int.from_bytes(self._sdo_upload_request(slave_id, ODI_VERIFY_CONFIGURATION, ODSI_VERIFY_CONFIGURATION_TIME), byteorder="little")
                            if cfg_date == expected_cfg_date and cfg_time == expected_cfg_time:
                                update_configuration = False
                        except:
                            pass
                    if update_configuration:
                        try:
                            self.update_configuration(slave_id)
                        except:
                            raise NmtSlaveBootError("J")

            # Enter Routes D/E
            # Start error control service per CiA 302-6 section 4.1
            heartbeat_consumer_time = 0
            heartbeat_consumer_time_obj = self.od.get(ODI_HEARTBEAT_CONSUMER_TIME)
            if heartbeat_consumer_time_obj is not None:
                for subindex in range(1, heartbeat_consumer_time_obj.get(ODSI_VALUE).value + 1):
                    heartbeat_consumer_time_value = heartbeat_consumer_time_obj.get(subindex).value
                    if (heartbeat_consumer_time_value >> 16) & 0x7F == slave_id:
                        heartbeat_consumer_time = heartbeat_consumer_time_value & 0xFFFF
                        break
            if heartbeat_consumer_time > 0:
                with self._heartbeat_consumer_timers_lock:
                    self._cancel_timer(self._heartbeat_consumer_timers.get(slave_id))
                    # Set timer to be longer than timeout (arbitrarily choosing 1 second)
                    self._heartbeat_consumer_timers[slave_id] = threading.Timer(heartbeat_consumer_time + 1, lambda: None)
                    self._heartbeat_consumer_timers.get(slave_id).start() # If heartbeat is received, timer is cancelled in _process_msg()
                self._heartbeat_consumer_timers.get(slave_id).join(heartbeat_consumer_time) # Wait for timeout
                heartbeat_event = self._heartbeat_consumer_timers.get(slave_id).is_alive() # If timer is still alive, then no heartbeat was received
                self._cancel_timer(self._heartbeat_consumer_timers.get(slave_id))
                if heartbeat_event:
                    raise NmtSlaveBootError("K")
                else:
                    # Heartbeat was received, so restart timer
                    with self._heartbeat_consumer_timers_lock:
                        self._heartbeat_consumer_timers[slave_id] = threading.Timer((heartbeat_consumer_time & 0xFFFF), self._heartbeat_consumer_timeout, args=[slave_id])
                        self._heartbeat_consumer_timers.get(slave_id).start()
            else:
                if not (nmt_slave_assignment & 0x01) and (nmt_slave_assignment >> 16) > 0:
                    raise NotImplementedError("Node guarding is not supported")
            if route_d:
                raise NmtSlaveBootError("L")
            if not route_e:
                nmt_startup_obj = self.od.get(ODI_NMT_STARTUP)
                if nmt_startup_obj is not None:
                    nmt_startup = nmt_startup_obj.get(ODSI_VALUE).value
                    if (nmt_startup & 0x80) == 0: # The NMT master shall start the NMT slaves
                        if (nmt_startup & 0x02) == 0 or self.nmt_state == NMT_STATE_OPERATIONAL:
                            self.send_nmt(NmtNodeControlMessage(NMT_NODE_CONTROL_START, slave_id))
            self._nmt_slave_booters[slave_id]["status"] = "OK"
        except NmtSlaveBootError as e:
            self._nmt_slave_booters[slave_id]["status"] = e.status
            self.on_error("nmt_boot_error", [slave_id, e.status])

    def _nmt_boot_timeout(self):
        self._nmt_boot_time_expired = True

    def _nmt_compare_flying_master_priority(self, priority):
        nmt_flying_master_timing_params = self.od.get(ODI_NMT_FLYING_MASTER_TIMING_PARAMETERS)
        own_priority = nmt_flying_master_timing_params.get(ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_PRIORITY).value
        if priority <= own_priority:
            logger.debug("Acive NMT Master priority level is the same or higher")
            self._nmt_become_inactive_master()
        else:
            logger.debug("Acive NMT Master priority level is lower")
            self.send_nmt(NmtForceFlyingMasterRequest())
            self._nmt_flying_master_startup()

    def _nmt_flying_master_negotiation(self):
        nmt_flying_master_timing_params = self.od.get(ODI_NMT_FLYING_MASTER_TIMING_PARAMETERS)
        priority = nmt_flying_master_timing_params.get(ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_PRIORITY).value
        priority_time_slot = nmt_flying_master_timing_params.get(ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_PRIORITY_TIME_SLOT).value
        device_time_slot = nmt_flying_master_timing_params.get(ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_DEVICE_TIME_SLOT).value
        flying_master_response_wait_time = (priority * priority_time_slot + self.id * device_time_slot) / 1000
        with self._nmt_flying_master_timer_lock:
            self._cancel_timer(self._nmt_flying_master_timer)
            self._nmt_flying_master_timer = threading.Timer(flying_master_response_wait_time, self._nmt_flying_master_negotiation_timeout)
            self._nmt_flying_master_timer.start()

    def _nmt_flying_master_negotiation_request(self):
        logger.debug("Requesting service NMT flying master negotiaion")
        self.send_nmt(NmtFlyingMasterRequest())
        self._nmt_flying_master_negotiation()

    def _nmt_flying_master_negotiation_timeout(self):
        logger.debug("NMT flying master negotiaion timeout")
        nmt_flying_master_timing_params = self.od.get(ODI_NMT_FLYING_MASTER_TIMING_PARAMETERS)
        priority = nmt_flying_master_timing_params.get(ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_PRIORITY).value
        self.send_nmt(NmtMasterNodeIdMessage(priority, self.id))
        self._nmt_become_active_master()

    def _nmt_flying_master_startup(self):
        logger.debug("Entering NMT flying master process")
        flying_master_params = self.od.get(ODI_NMT_FLYING_MASTER_TIMING_PARAMETERS)
        if flying_master_params is None:
            raise RuntimeException("Device is configured as NMT flying master, but object dictionary parameters do not exist")
        flying_master_negotiation_delay = flying_master_params.get(ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_DELAY).value
        time.sleep(flying_master_negotiation_delay / 1000)
        logger.debug("Service active NMT master detection")
        active_nmt_master_timeout_time = flying_master_params.get(ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_TIMEOUT).value / 1000
        with self._nmt_active_master_timer_lock:
            self._cancel_timer(self._nmt_active_master_timer)
            self._nmt_active_master_timer = threading.Timer(active_nmt_master_timeout_time, self._nmt_active_master_timeout)
            self._nmt_active_master_timer.start()
        self.send_nmt(NmtActiveMasterRequest())

    def _nmt_startup(self):
        logger.debug("Entering NMT startup process")
        nmt_startup_obj = self.od.get(ODI_NMT_STARTUP)
        if nmt_startup_obj is not None:
            nmt_startup = nmt_startup_obj.get(ODSI_VALUE).value
            if nmt_startup & 0x01: # NMT Master
                if nmt_startup & 0x20: # NMT Flying Master
                    self._nmt_flying_master_startup()
                else:
                    self._nmt_become_active_master()
            else:
                if (nmt_startup & 0x04) == 0:
                    logger.info("Self-starting")
                    self.nmt_state = NMT_STATE_OPERATIONAL
                logger.info("Entering NMT slave mode")
        else:
            logger.info("Entering NMT slave mode")

    def _on_can_error(self, channel):
        error_behavior_obj = self.od.get(ODI_ERROR_BEHAVIOR)
        if error_behavior_obj is not None:
            comm_error_behavior = error_behavior_obj.get(0x01).value
            if comm_error_behavior == 0:
                if ((channel == self.default_bus.channel and self._nmt_state == NMT_STATE_OPERATIONAL) or
                    (channel == self.redundant_bus.channel and self._redundant_nmt_state == NMT_STATE_OPERATIONAL)):
                    self.nmt_state = (NMT_STATE_PREOPERATIONAL, channel)
            elif comm_error_behavior == 2:
                self.nmt_state = (NMT_STATE_STOPPED, channel)

    def _on_sdo_download(self, odi, odsi, obj, sub_obj):
        obj.update({odsi: sub_obj})
        self.od.update({odi: obj})
        if odi in [ODI_SYNC, ODI_SYNC_TIME]:
            self._process_sync()
        elif odi == ODI_HEARTBEAT_PRODUCER_TIME:
            self._process_heartbeat_producer()
        threading.Thread(target=self.on_sdo_download, args=(odi, odsi, obj, sub_obj), daemon=True).start()

    def _on_sync(self):
        self._sync_counter = (self._sync_counter + 1) % 241
        for i in range(4):
            tpdo_cp = self.od.get(ODI_TPDO1_COMMUNICATION_PARAMETER + i)
            if tpdo_cp is not None:
                tpdo_cp_id = tpdo_cp.get(ODSI_TPDO_COMM_PARAM_ID)
                if tpdo_cp_id is not None and tpdo_cp_id.value is not None and (tpdo_cp_id.value >> TPDO_COMM_PARAM_ID_VALID_BITNUM) & 1 == 0:
                    tpdo_cp_type = tpdo_cp.get(ODSI_TPDO_COMM_PARAM_TYPE)
                    if tpdo_cp_type is not None and tpdo_cp_type.value is not None and (((tpdo_cp_type.value == 0 or tpdo_cp_type.value == 0xFC) and self._tpdo_triggers[i]) or (self._sync_counter % tpdo_cp_type.value) == 0):
                        self._send_pdo(i + 1)
        threading.Thread(target=self.on_sync, daemon=True).start()

    def _process_err_indicator(self):
        try:
            self._err_indicator.set_state(self.default_bus.state)
            self._redundant_err_indicator.set_state(self.redundant_bus.state)
        except AttributeError:
            pass

    def _process_heartbeat_producer(self):
        heartbeat_producer_time_object = self.od.get(ODI_HEARTBEAT_PRODUCER_TIME)
        if heartbeat_producer_time_object is not None:
            heartbeat_producer_time_value = heartbeat_producer_time_object.get(ODSI_VALUE)
            if heartbeat_producer_time_value is not None and heartbeat_producer_time_value.value is not None:
                heartbeat_producer_time = heartbeat_producer_time_value.value / 1000
            else:
                heartbeat_producer_time = 0
        else:
            heartbeat_producer_time = 0
        with self._heartbeat_producer_timer_lock:
            self._cancel_timer(self._heartbeat_producer_timer)
            if heartbeat_producer_time != 0:
                self._heartbeat_producer_timer = IntervalTimer(heartbeat_producer_time, self._send_heartbeat)
                self._heartbeat_producer_timer.start()

    def _process_msg(self, msg: can.Message):
        can_id = msg.arbitration_id
        data = msg.data
        fc = (can_id & FUNCTION_CODE_MASK) >> FUNCTION_CODE_BITNUM # Only look for restricted CAN-IDs using function code
        if msg.is_remote_frame: # CiA recommendeds against using RTRs, but they are still supported
            target_node = can_id & 0x7F
            if fc == FUNCTION_CODE_NMT_ERROR_CONTROL and (target_node == self.id or target_node == BROADCAST_NODE_ID):
                self._send_heartbeat()
            if self.nmt_state == NMT_STATE_OPERATIONAL:
                for tpdo in range(1, 5):
                    tpdo_cp = self.od.get(ODI_TPDO1_COMMUNICATION_PARAMETER + tpdo - 1)
                    if tpdo_cp is not None:
                        tpdo_cp_id = tpdo_cp.get(ODSI_TPDO_COMM_PARAM_ID)
                        if tpdo_cp_id is not None and (tpdo_cp_id >> TPDO_COMM_PARAM_ID_VALID_BITNUM) & 1 == 0 and (tpdo_cp_id >> TPDO_COMM_PARAM_ID_RTR_BITNUM) & 1 == 0:
                            tpdo_cp_type = tpdo_cp.get(ODSI_TPDO_COMM_PARAM_TYPE)
                            if tpdo_cp_type == 0xFC:
                                self._tpdo_triggers[tpdo - 1] = True; # Defer until SYNC event
                            elif tpdo_cp_type == 0xFD:
                                self._send_pdo(tpdo)
        elif fc == FUNCTION_CODE_NMT:
            command = can_id & 0x7F
            if command == NMT_NODE_CONTROL:
                target_node = data[1]
                if target_node == self.id or target_node == BROADCAST_NODE_ID:
                    cs = data[0]
                    if cs == NMT_NODE_CONTROL_START:
                        self.nmt_state = (NMT_STATE_OPERATIONAL, msg.channel)
                    elif cs == NMT_NODE_CONTROL_STOP:
                        self.nmt_state = (NMT_STATE_STOPPED, msg.channel)
                    elif cs == NMT_NODE_CONTROL_PREOPERATIONAL:
                        self.nmt_state = (NMT_STATE_PREOPERATIONAL, msg.channel)
                    elif cs == NMT_NODE_CONTROL_RESET_NODE:
                        self.reset()
                    elif cs == NMT_NODE_CONTROL_RESET_COMMUNICATION:
                        self.reset_communication(msg.channel)
            elif command == NMT_MASTER_NODE_ID: # Response from either an NmtActiveMasterRequest, NmtFlyingMasterRequest, or unsolicited from non-Flying Master after bootup was indicated
                if self.is_nmt_master_capable:
                    logger.debug(f"Active NMT flying master detected with node-ID {data[1]}")
                    compare_priority = False
                    self._nmt_active_master_id = data[1]
                    with self._nmt_active_master_timer_lock:
                        if self._cancel_timer(self._nmt_active_master_timer): # If from NmtActiveMasterRequest
                            self._first_boot = False
                            compare_priority = True
                    with self._nmt_flying_master_timer_lock:
                        if self._cancel_timer(self._nmt_flying_master_timer): # If from NmtFlyingMasterRequest
                            compare_priority = True
                    with self._nmt_multiple_master_timer_lock:
                        if self._cancel_timer(self._nmt_multiple_master_timer):
                            compare_priority = True
                    if compare_priority:
                        self._nmt_compare_flying_master_priority(data[0])
            elif command == NMT_ACTIVE_MASTER_REQUEST:
                if self.is_active_nmt_master:
                    nmt_flying_master_timing_params = self.od.get(ODI_NMT_FLYING_MASTER_TIMING_PARAMETERS)
                    priority = nmt_flying_master_timing_params.get(ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_PRIORITY).value
                    self.send_nmt(NmtMasterNodeIdMessage(priority, self.id))
            elif command == NMT_FLYING_MASTER_REQUEST:
                nmt_startup_obj = self.od.get(ODI_NMT_STARTUP)
                if nmt_startup_obj is not None:
                    nmt_startup = nmt_startup_obj.get(ODSI_VALUE).value
                    if nmt_startup & 0x21: # Is NMT Flying Master
                        self._nmt_flying_master_negotiation()
            elif command == NMT_MASTER_REQUEST:
                if self.is_nmt_master_capable:
                 self.send_nmt(NmtMasterResponse())
            elif command == NMT_FORCE_FLYING_MASTER:
                if self.is_nmt_master_capable:
                    logger.info("Force NMT flying master negotation service indicated")
                    self._nmt_become_inactive_master()
                    self._nmt_flying_master_startup()
            elif command == NMT_INDICATE_ACTIVE_INTERFACE: # CiA 302-6, Figure 7, event (2), (5), (7), or (9)
                self._cancel_timer(self._heartbeat_evaluation_power_on_timer)
                if msg.channel == self.default_bus.channel:
                    self.active_bus = self.default_bus
                else:
                    self.active_bus = self.redundant_bus
        elif fc == FUNCTION_CODE_NMT_ERROR_CONTROL:
            producer_id = can_id & 0x7F
            producer_nmt_state = data[0]

            if msg.channel == self.default_bus.channel and (
                    (self._heartbeat_evaluation_power_on_timer is not None and self._heartbeat_evaluation_power_on_timer.is_alive()) or
                    (self._heartbeat_evaluation_reset_communication_timer is not None and self._heartbeat_evaluation_reset_communication_timer.is_alive())
                ):
                if producer_id in self._heartbeat_evaluation_counters:
                    self._heartbeat_evaluation_counters[producer_id] += 1
                else:
                    self._heartbeat_evaluation_counters[producer_id] = 1
                logger.debug(f"Heartbeat evaluated for node-ID {producer_id} with count of {self._heartbeat_evaluation_counters[producer_id]}")

            if producer_id in self._heartbeat_consumer_timers:
                with self._heartbeat_consumer_timers_lock:
                    self._cancel_timer(self._heartbeat_consumer_timers.get(producer_id))
            elif self.is_nmt_master_capable and (producer_id == self._nmt_active_master_id):
                # CiA 302-2, section 5.5.2 Detection of an NMT master failure
                # If not in heartbeat consumers, timeout is not defined; use 1.5 of own heartbeat period
                with self._nmt_active_master_timer_lock:
                    self._cancel_timer(self._nmt_active_master_timer)
                    heartbeat_producer_object = self.od.get(ODI_HEARTBEAT_PRODUCER_TIME)
                    if heartbeat_producer_object is not None:
                        heartbeat_producer_value = heartbeat_producer_object.get(ODSI_VALUE)
                        if heartbeat_producer_value is not None and heartbeat_producer_value.value != 0:
                            self._nmt_active_master_timer = threading.Timer(heartbeat_producer_value.value * 1.5 / 1000, self._nmt_active_master_timeout, [True])
                            self._nmt_active_master_timer.start()

            heartbeat_consumer_time = 0
            heartbeat_consumer_time_object = self.od.get(ODI_HEARTBEAT_CONSUMER_TIME)
            if heartbeat_consumer_time_object is not None:
                heartbeat_consumer_time_length = heartbeat_consumer_time_object.get(ODSI_VALUE)
                if heartbeat_consumer_time_length is not None and heartbeat_consumer_time_length.value is not None:
                    for i in range(1, heartbeat_consumer_time_length.value + 1):
                        heartbeat_consumer_time_value = heartbeat_consumer_time_object.get(i)
                        if heartbeat_consumer_time_value is not None and heartbeat_consumer_time_value.value is not None and ((heartbeat_consumer_time_value.value >> 16) & 0x7F) == producer_id:
                            heartbeat_consumer_time = (heartbeat_consumer_time_value.value & 0xFFFF) / 1000
                            break

            # If active NMT master, initially start heartbeat consumer timers in _nmt_become_active_master(), otherwise start here:
            if (self.is_active_nmt_master and self._nmt_boot_time_expired) or not self.is_nmt_master_capable:
                if heartbeat_consumer_time != 0:
                    with self._heartbeat_consumer_timers_lock:
                        #self._cancel_timer(self._heartbeat_consumer_timers.get(producer_id)) # Already cancelled above
                        heartbeat_consumer_timer = threading.Timer(heartbeat_consumer_time, self._heartbeat_consumer_timeout, [producer_id])
                        heartbeat_consumer_timer.start()
                        self._heartbeat_consumer_timers.update({producer_id: heartbeat_consumer_timer})
                    if self.is_nmt_master_capable and (producer_id == self._nmt_active_master_id):
                        with self._nmt_active_master_timer_lock:
                            self._cancel_timer(self._nmt_active_master_timer)
                            self._nmt_active_master_timer = threading.Timer(heartbeat_consumer_time, self._nmt_active_master_timeout)
                            self._nmt_active_master_timer.start()

            # Need to save NMT state for NMT slave keep-alive checking
            if self.is_active_nmt_master and self._nmt_boot_time_expired:
                 self._nmt_slave_states.update({producer_id: producer_nmt_state})

            request_nmt_obj = self.od.get(ODI_REQUEST_NMT)
            if request_nmt_obj is not None:
                request_nmt_subobj = request_nmt_obj.get(producer_id)
                if request_nmt_subobj is not None:
                    request_nmt_subobj.value = producer_nmt_state
                    request_nmt_obj.update({producer_id: request_nmt_subobj})
                    self.od.update({ODI_REQUEST_NMT: request_nmt_obj})

            if self.is_active_nmt_master and producer_nmt_state == NMT_STATE_INITIALISATION:
                # Service NMT master node-ID, CiA 302-6, Section 4.6.3
                nmt_flying_master_timing_params = self.od.get(ODI_NMT_FLYING_MASTER_TIMING_PARAMETERS)
                if nmt_flying_master_timing_params is not None:
                    priority = nmt_flying_master_timing_params.get(ODSI_NMT_FLYING_MASTER_TIMING_PARAMS_PRIORITY).value
                else:
                    priority = 0
                self.send_nmt(NmtMasterNodeIdMessage(priority, self.id))

                if self._nmt_boot_time_expired:
                    # Bootup handler per CiA 302-2 section 4.3
                    in_network = False
                    nmt_slave_assignments = self.od.get(ODI_NMT_SLAVE_ASSIGNMENT)
                    if nmt_slave_assignments is not None:
                        nmt_slave_assignment = nmt_slave_assignments.get(producer_id)
                        if nmt_slave_assignment is not None:
                            if nmt_slave_assignment.value & 0x01:
                                in_network = True
                                threading.Thread(target=self._nmt_boot_slave, daemon=True, args=[producer_id]).start()
                    self.on_node_bootup(producer_id, in_network)

        else: # Check non-restricted CAN-IDs
            if self.nmt_state == NMT_STATE_OPERATIONAL and msg.channel == self.active_bus.channel: # CiA 302-6, Section 4.4.2.3
                sync_obj = self.od.get(ODI_SYNC)
                if sync_obj is not None:
                    sync_obj_value = sync_obj.get(ODSI_VALUE)
                    if sync_obj_value is not None and (sync_obj_value.value & 0x1FFFFFFF) == can_id:
                        self._on_sync()
            if self._nmt_state in [NMT_STATE_PREOPERATIONAL, NMT_STATE_OPERATIONAL]:
                emcy_consumer_object= self.od.get(ODI_EMERGENCY_CONSUMER_OBJECT)
                if emcy_consumer_object is not None:
                    subobjs = 0
                    for subindex, subobj in emcy_consumer_object.items():
                        if subindex == 0:
                            subobjs = subobj.value
                            continue
                        if subindex > subobjs:
                            break
                        if subobj.value == can_id:
                            eec, er = struct.unpack("<HB", data[0:3])
                            msef = int.from_bytes(data[3:], byteorder="little")
                            self.on_emcy(can_id, eec, er, msef)
                if msg.channel == self.active_bus.channel: # CiA 302-6, Section 4.3.2.3
                    time_obj = self.od.get(ODI_TIME_STAMP)
                    if time_obj is not None:
                        time_cob_id = time_obj.get(ODSI_VALUE).value
                        if time_cob_id & 0x80 and time_cob_id & 0x1FFFFFFF == can_id:
                            ms, d = struct.unpack("<IH", data[0:6])
                            self.timestamp = EPOCH + datetime.timedelta(days=d, milliseconds=ms)
            if (
                   (msg.channel == self.default_bus.channel and self._nmt_state in [NMT_STATE_PREOPERATIONAL, NMT_STATE_OPERATIONAL])
                   or
                   (self.redundant_bus is not None and msg.channel == self.redundant_bus.channel and self._redundant_nmt_state in [NMT_STATE_PREOPERATIONAL, NMT_STATE_OPERATIONAL])
               ) and len(data) == 8: # Ignore SDO if data is not 8 bytes
                sdo_server_object = self.od.get(ODI_SDO_SERVER)
                if sdo_server_object is not None:
                    sdo_server_csid = sdo_server_object.get(ODSI_SDO_SERVER_DEFAULT_CSID)
                    if sdo_server_csid is not None and (sdo_server_csid.value & 0x1FFFFFFF) == can_id:
                        try:
                            ccs = (data[0] & SDO_CS_MASK) >> SDO_CS_BITNUM
                            if self._sdo_cs == SDO_SCS_BLOCK_DOWNLOAD and self._sdo_seqno > 0:
                                logger.info(f"SDO block download sub-block for mux 0x{self._sdo_odi:02X}{solf_sdo_osdi:04X}")
                                c = data[0] >> 7
                                seqno = data[0] & 0x7F
                                if self._sdo_seqno != seqno:
                                    if self._sdo_seqno > 1:
                                        raise SdoAbort(self._sdo_odi, self._sdo_odsi, SDO_ABORT_INVALID_SEQNO)
                                    else:
                                        ackseq = 0
                                else:
                                    self._sdo_data += data[1:8]
                                    ackseq = seqno
                                    if c == 1:
                                        self._sdo_seqno = 0
                                    elif self._sdo_seqno == self._sdo_len:
                                        self._sdo_seqno = 1
                                    else:
                                        self._sdo_seqno += 1
                                        return
                                blksize = 127
                                data = struct.pack("<BBB5x", (SDO_SCS_BLOCK_DOWNLOAD << SDO_CS_BITNUM) + SDO_BLOCK_SUBCOMMAND_RESPONSE, ackseq, blksize)
                            else:
                                if ccs in [SDO_CS_ABORT, SDO_CCS_DOWNLOAD_INITIATE, SDO_CCS_UPLOAD_INITIATE] or (ccs == SDO_CCS_BLOCK_DOWNLOAD and (data[0] & 0x1) == SDO_BLOCK_SUBCOMMAND_INITIATE) or (ccs == SDO_CCS_BLOCK_UPLOAD and (data[0] & 0x03) == SDO_BLOCK_SUBCOMMAND_INITIATE):
                                    odi = (data[2] << 8) + data[1]
                                    odsi = data[3]
                                    if odi in self.od:
                                        obj = self.od.get(odi)
                                        if odsi in obj:
                                            subobj = obj.get(odsi)
                                        else:
                                            raise SdoAbort(odi, odsi, SDO_ABORT_SUBINDEX_DNE)
                                    else:
                                        raise SdoAbort(odi, odsi, SDO_ABORT_OBJECT_DNE)
                                if ccs == SDO_CS_ABORT:
                                    logger.info(f"SDO abort request for mux 0x{odi:04X}{odsi:02X}")
                                    self._sdo_cs = None
                                    self._sdo_data = None
                                    self._sdo_len = None
                                    self._sdo_odi = None
                                    self._sdo_odsi = None
                                    self._sdo_seqno = 0
                                    self._sdo_t = None
                                    return
                                elif ccs == SDO_CCS_DOWNLOAD_INITIATE:
                                    logger.info(f"SDO download initiate request for mux 0x{odi:04X}{odsi:02X}")
                                    if subobj.access_type in [AccessType.RO, AccessType.CONST]:
                                        raise SdoAbort(odi, odsi, SDO_ABORT_RO)
                                    scs = SDO_SCS_DOWNLOAD_INITIATE
                                    s = (data[0] >> SDO_S_BITNUM) & 1
                                    e = (data[0] >> SDO_E_BITNUM) & 1
                                    data_type_index = subobj.data_type
                                    if e == 1 and s == 1:
                                        n = (data[0] & SDO_INITIATE_N_MASK) >> SDO_INITIATE_N_BITNUM
                                        subobj.value = subobj.from_bytes(data[4:8-n])
                                        self._on_sdo_download(odi, odsi, obj, subobj)
                                    elif e == 1 and s == 0:
                                        n = 0 # Unspecified number of bytes, default to all
                                        if data_type_index in self.od:
                                            data_type_object = self.od.get(data_type_index)
                                            if ODSI_VALUE in data_type_object:
                                                n = 4 - max(1, data_type_object.get(ODSI_VALUE).value // 8)
                                        subobj.value = subobj.from_bytes(data[4:8-n])
                                        self._on_sdo_download(odi, odsi, obj, subobj)
                                    elif e == 0 and s == 1: # Normal (non-expedited) SDO
                                        self._sdo_odi = odi
                                        self._sdo_odsi = odsi
                                        self._sdo_t = 0
                                        self._sdo_len = int.from_bytes(data[4:8], byteorder="little")
                                        if self._sdo_len == 0:
                                            raise SdoAbort(odi, odsi, SDO_ABORT_PARAMETER_LENGTH)
                                        self._sdo_data = []
                                        self._sdo_data_type = data_type_index
                                    else: # e == 0, s == 0 is reserved
                                        logger.error("SDO Download Initiate Request with e=0 & s=0 aborted")
                                        raise SdoAbort(odi, odsi, SDO_ABORT_GENERAL)
                                    if e == 1: # Handle special cases
                                        if odi == ODI_PREDEFINED_ERROR_FIELD and subobj.value != 0:
                                            raise SdoAbort(odi, odsi, SDO_ABORT_INVALID_VALUE)
                                        if odi == ODI_REQUEST_NMT:
                                            if not self.is_active_nmt_master:
                                                logger.error("SDO Download to NMT Request aborted; device is not active NMT master")
                                                raise SdoAbort(odi, odsi, SDO_ABORT_GENERAL)
                                            target_node = odsi & 0x7F
                                            if (subobj.value & 0x7F) == 0x04: # Stop remote node
                                                self.send_nmt(NmtNodeControlMessage(NMT_NODE_CONTROL_STOP, target_node))
                                            elif (subobj.value & 0x7F) == 0x05: # Start remote node
                                                self.send_nmt(NmtNodeControlMessage(NMT_NODE_CONTROL_START, target_node))
                                            elif (subobj.value & 0x7F) == 0x06: # Reset node
                                                self.send_nmt(NmtNodeControlMessage(NMT_NODE_CONTROL_RESET_NODE, target_node))
                                            elif (subobj.value & 0x7F) == 0x06: # Reset communication
                                                self.send_nmt(NmtNodeControlMessage(NMT_NODE_CONTROL_RESET_COMMUNICATION, target_node))
                                            elif (subobj.value & 0x7F) == 0x06: # Enter preoperational
                                                self.send_nmt(NmtNodeControlMessage(NMT_NODE_CONTROL_PREOPERATIONAL, target_node))
                                            else:
                                                raise SdoAbort(odi, odsi, SDO_ABORT_INVALID_VALUE)
                                    data = struct.pack("<BHB4x", scs << SDO_CS_BITNUM, odi, odsi)
                                elif ccs == SDO_CCS_DOWNLOAD_SEGMENT:
                                    if self._sdo_data is None:
                                        logger.error("SDO Download Segment Request aborted, initate not received or aborted")
                                        raise SdoAbort(0, 0, SDO_ABORT_INVALID_CS) # Initiate not receieved or aborted
                                    logger.info(f"SDO download segment request for mux 0x{self._sdo_odi:04X}{self._sdo_odsi:02X}")
                                    scs = SDO_SCS_DOWNLOAD_SEGMENT
                                    t = (data[0] >> SDO_T_BITNUM) & 1
                                    if self._sdo_t != t:
                                        raise SdoAbort(self._sdo_odi, self._sdo_odsi, SDO_ABORT_TOGGLE)
                                    self._sdo_t = t ^ 1
                                    n = (data[0] & SDO_SEGMENT_N_MASK) >> SDO_SEGMENT_N_BITNUM
                                    self._sdo_data += data[1:8-n]
                                    c = (data[0] >> SDO_C_BITNUM) & 1
                                    if c == 1:
                                        obj = self.od.get(self._sdo_odi)
                                        subobj = obj.get(self._sdo_odsi)
                                        subobj.value = subobj.from_bytes(self._sdo_data)
                                        self._on_sdo_download(self._sdo_odi, self._sdo_odsi, obj, subobj)
                                        self._sdo_data = None
                                        self._sdo_data_type = None
                                        self._sdo_len = None
                                        self._sdo_odi = None
                                        self._sdo_odsi = None
                                        self._sdo_t = None
                                    data = struct.pack("<B7x", (scs << SDO_CS_BITNUM) + (t << SDO_T_BITNUM))
                                elif ccs == SDO_CCS_UPLOAD_INITIATE:
                                    logger.info(f"SDO upload initiate request for mux 0x{odi:04X}{odsi:02X}")
                                    if subobj.access_type == AccessType.WO:
                                        raise SdoAbort(odi, odsi, SDO_ABORT_WO)
                                    if odsi != ODSI_VALUE and obj.get(ODSI_VALUE).value < odsi:
                                        raise SdoAbort(odi, odsi, SDO_ABORT_NO_DATA)
                                    scs = SDO_SCS_UPLOAD_INITIATE
                                    data_type_index = subobj.data_type
                                    data_type_length = None
                                    if data_type_index in self.od:
                                        data_type_object = self.od.get(data_type_index)
                                        if ODSI_VALUE in data_type_object:
                                            data_type_length = data_type_object.get(ODSI_VALUE).value // 8
                                            if data_type_length == 0:
                                                data_type_length = None
                                    if data_type_length is None:
                                        if hasattr(subobj.value, "fileno"):
                                            data_type_length = os.fstat(subobj.value.fileno()).st_size
                                        else:
                                            data_type_length = len(bytes(subobj))
                                    if data_type_length > 4:
                                        if hasattr(subobj.value, "read"):
                                            self._sdo_data = subobj.value
                                            self._sdo_data.seek(0)
                                        else:
                                            self._sdo_data = bytes(subobj)
                                        self._sdo_len = data_type_length
                                        self._sdo_t = 0
                                        self._sdo_odi = odi
                                        self._sdo_odsi = odsi
                                        s = 1
                                        e = 0
                                        n = 0
                                        sdo_data = struct.pack("<I", data_type_length)
                                    else:
                                        n = 4 - data_type_length
                                        s = 1
                                        e = 1
                                        sdo_data = bytes(subobj)
                                    data = struct.pack("<BHB4s", (scs << SDO_CS_BITNUM) + (n << SDO_INITIATE_N_BITNUM) + (e << SDO_E_BITNUM), odi, odsi, sdo_data)
                                elif ccs == SDO_CCS_UPLOAD_SEGMENT:
                                    if self._sdo_data is None:
                                        logger.error("SDO upload initiate request aborted, initiate not received or aborted")
                                        raise SdoAbort(0, 0, SDO_ABORT_INVALID_CS) # Initiate not receieved or aborted
                                    logger.info(f"SDO upload segment request for mux 0x{self._sdo_odi:04X}{self._sdo_odsi:02X}")
                                    scs = SDO_SCS_UPLOAD_SEGMENT
                                    t = (data[0] >> SDO_T_BITNUM) & 1
                                    if self._sdo_t != t:
                                        raise SdoAbort(self._sdo_odi, self._sdo_odsi, SDO_ABORT_TOGGLE)
                                    self._sdo_t = t ^ 1
                                    if self._sdo_len > 7:
                                        l = 7
                                    else:
                                        l = self._sdo_len
                                    if hasattr(self._sdo_data, "read"):
                                        sdo_data = self._sdo_data.read(l)
                                    else:
                                        sdo_data = self._sdo_data[-self._sdo_len:(-self._sdo_len+l or None)]
                                    self._sdo_len -= l
                                    n = 7 - l
                                    if self._sdo_len > 0:
                                        c = 0
                                    else:
                                        self._sdo_data = None
                                        self._sdo_len = None
                                        self._sdo_t = None
                                        c = 1
                                    data = struct.pack(f"<B{len(sdo_data)}s{7 - len(sdo_data)}x", (scs << SDO_CS_BITNUM) + (t << SDO_T_BITNUM) + (n << SDO_SEGMENT_N_BITNUM) + (c << SDO_C_BITNUM), sdo_data)
                                elif ccs == SDO_CCS_BLOCK_DOWNLOAD:
                                    scs = SDO_SCS_BLOCK_DOWNLOAD
                                    cs = data[0] & 0x01
                                    if cs == SDO_BLOCK_SUBCOMMAND_INITIATE:
                                        logger.info(f"SDO block download initiate request for mux 0x{odi:04X}{odsi:02X}")
                                        if subobj.access_type in [AccessType.RO, AccessType.CONST]:
                                            raise SdoAbort(odi, odsi, SDO_ABORT_RO)
                                        if odsi != ODSI_VALUE and obj.get(ODSI_VALUE).value < odsi:
                                            raise SdoAbort(odi, odsi, SDO_ABORT_NO_DATA)
                                        cc = (data[0] >> 2) & 0x01
                                        s = (data[0] >> 1) & 0x01
                                        if s == 1:
                                            size = int.from_bytes(data[4:8], byteorder="little")
                                            if size == 0:
                                                raise SdoAbort(odi, odsi, SDO_ABORT_PARAMETER_LENGTH)
                                            if size > 127:
                                                blksize = 127
                                            else:
                                                blksize = size
                                        else:
                                            blksize = 127
                                        sc = cc
                                        self._sdo_cs = scs
                                        self._sdo_data = []
                                        self._sdo_len = blksize
                                        self._sdo_odi = odi
                                        self._sdo_odsi = odsi
                                        self._sdo_seqno = 1
                                        self._sdo_t = cc # CRC support
                                        data = struct.pack("<BHBB3x", (scs << SDO_CS_BITNUM) + (sc << 2) + SDO_BLOCK_SUBCOMMAND_INITIATE, odi, odsi, blksize)
                                    else: # SDO_BLOCK_SUBCOMMAND_END
                                        if self._sdo_cs != SDO_SCS_BLOCK_DOWNLOAD:
                                            raise SdoAbort(0, 0, SDO_ABORT_INVALID_CS)
                                        logger.info(f"SDO block download end request for mux 0x{self._sdo_odi:04X}{self._sdo_odsi:02X}")
                                        n = (data[0] >> 2) & 0x07
                                        self._sdo_data = self._sdo_data[0:-n]
                                        if self._sdo_t: # Check CRC
                                            crc, = struct.unpack("<H", data[1:3])
                                            if crc != crc_hqx(bytes(self._sdo_data), 0):
                                                raise SdoAbort(self._sdo_odi, self._sdo_odsi, SDO_ABORT_CRC_ERROR)
                                        obj = self.od.get(self._sdo_odi)
                                        subobj = obj.get(self._sdo_odsi)
                                        subobj.value = subobj.from_bytes(self._sdo_data)
                                        self._on_sdo_download(self._sdo_odi, self._sdo_odsi, obj, subobj)
                                        self._sdo_cs = None
                                        self._sdo_data = None
                                        self._sdo_len = None
                                        self._sdo_odi = None
                                        self._sdo_odsi = None
                                        self._sdo_seqno = 0
                                        self._sdo_t = None
                                        data = struct.pack("<B7x", (scs << SDO_CS_BITNUM) + SDO_BLOCK_SUBCOMMAND_END)
                                elif ccs == SDO_CCS_BLOCK_UPLOAD:
                                    cs = data[0] & 0x03
                                    if cs == SDO_BLOCK_SUBCOMMAND_INITIATE:
                                        cc = (data[0] >> 2) & 0x01
                                        blksize = data[4]
                                        if blksize == 0 or blksize >= 128:
                                            raise SdoAbort(odi, odsi, SDO_ABORT_INVALID_BLKSIZE)
                                        pst = data[5] # TODO: Support protocol switching
                                        sc = cc # CRC support
                                        data_type_index = subobj.data_type
                                        data_type_length = None # Maybe use len(bytes(subobj))?
                                        if data_type_index in self.od:
                                            data_type_object = self.od.get(data_type_index)
                                            if ODSI_VALUE in data_type_object:
                                                data_type_length = data_type_object.get(ODSI_VALUE).value // 8
                                        if data_type_length is None:
                                            s = 0
                                            size = 0
                                        else:
                                            s = 1
                                            size = data_type_length
                                        scs = SDO_SCS_BLOCK_UPLOAD
                                        self._sdo_cs = scs
                                        if hasattr(subobj.value, "read"):
                                            self._sdo_data = subobj.value
                                            self._sdo_data.seek(0)
                                        else:
                                            self._sdo_data = bytes(subobj)
                                        self._sdo_len = blksize
                                        self._sdo_odi = odi
                                        self._sdo_odsi = odsi
                                        logger.info(f"SDO block upload initiate request for mux 0x{self._sdo_odi:04X}{self._sdo_odsi:02X}")
                                        data = struct.pack("<BHBI", (scs << SDO_CS_BITNUM) + (sc << 2) + (s << 1) + SDO_BLOCK_SUBCOMMAND_INITIATE, self._sdo_odi, self._sdo_odsi, size)
                                    elif cs == SDO_BLOCK_SUBCOMMAND_START:
                                        if self._sdo_cs != SDO_SCS_BLOCK_UPLOAD:
                                            raise SdoAbort(0, 0, SDO_ABORT_INVALID_CS);
                                        logger.info(f"SDO block upload start request for mux 0x{self._sdo_odi:04X}{self._sdo_odsi:02X}")
                                        self._sdo_seqno = 1
                                        if hasattr(self._sdo_data, "fileno"):
                                            data_len = os.fstat(self._sdo_data.fileno()).st_size
                                        else:
                                            data_len = len(self._sdo_data)
                                        while data_len > 0 and self._sdo_seqno <= self._sdo_len:
                                            if data_len > 7:
                                                c = 0
                                            else:
                                                c = 1
                                            if hasattr(self._sdo_data, "read"):
                                                sdo_data = self._sdo_data.read(7)
                                            else:
                                                sdo_data = self._sdo_data[(self._sdo_seqno - 1) * 7:self._sdo_seqno * 7]
                                            sdo_data = sdo_data.ljust(7, b'\x00')
                                            data = struct.pack("<B7s", (c << 7) + self._sdo_seqno, sdo_data)
                                            sdo_server_scid = sdo_server_object.get(ODSI_SDO_SERVER_DEFAULT_SCID)
                                            if sdo_server_scid is None:
                                                raise ValueError("SDO Server SCID not specified")
                                            arbitration_id = sdo_server_scid.value & 0x1FFFFFFF
                                            is_extended_id = bool(sdo_server_scid.value & 0x20000000)
                                            msg = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=is_extended_id, channel=msg.channel)
                                            self._send(msg, msg.channel)
                                            data_len -= 7
                                            self._sdo_seqno += 1
                                        if hasattr(self._sdo_data, "seek"):
                                            self._sdo_data.seek((1 - self._sdo_seqno) * 7 - min(0, data_len), io.SEEK_CUR)
                                        return
                                    elif cs == SDO_BLOCK_SUBCOMMAND_RESPONSE:
                                        if self._sdo_cs != SDO_SCS_BLOCK_UPLOAD:
                                            raise SdoAbort(0, 0, SDO_ABORT_INVALID_CS);
                                        logger.info(f"SDO block upload response for mux 0x{self._sdo_odi:04X}{self._sdo_odsi:02X}")
                                        ackseq = data[1]
                                        blksize = data[2]
                                        if ackseq != 0:
                                            if hasattr(self._sdo_data, "fileno"):
                                                data_len = os.fstat(self._sdo_data.fileno()).st_size - self._sdo_data.tell()
                                            else:
                                                data_len = len(self._sdo_data)
                                            bytes_transferred = 7 * ackseq
                                            bytes_left = data_len - bytes_transferred
                                            if bytes_left < 0:
                                                n = -bytes_left
                                            else:
                                                n = 0
                                            if hasattr(self._sdo_data, "seek"):
                                                self._sdo_data.seek(bytes_transferred, io.SEEK_CUR)
                                            else:
                                                self._sdo_data = self._sdo_data[bytes_transferred:]
                                        if ackseq == self._sdo_len:
                                            self._sdo_seqno = 1
                                        else:
                                            self._sdo_seqno = ackseq + 1
                                        self._sdo_len = blksize
                                        if hasattr(self._sdo_data, "fileno"):
                                            data_len = os.fstat(self._sdo_data.fileno()).st_size - self._sdo_data.tell()
                                        else:
                                            data_len = len(self._sdo_data)
                                        logger.info(f"{data_len} bytes remaining in SDO block upload")
                                        if data_len <= 0:
                                            crc = crc_hqx(bytes(self.od.get(self._sdo_odi).get(self._sdo_odsi)), 0)
                                            data = struct.pack("<BH5x", (SDO_SCS_BLOCK_UPLOAD << SDO_CS_BITNUM) + (n << 2) + SDO_BLOCK_SUBCOMMAND_END, crc)
                                        else:
                                            while data_len > 0 and self._sdo_seqno <= self._sdo_len:
                                                if data_len > 7:
                                                    c = 0
                                                else:
                                                    c = 1
                                                if hasattr(self._sdo_data, "read"):
                                                    sdo_data = self._sdo_data.read(7)
                                                else:
                                                    sdo_data = self._sdo_data[(self._sdo_seqno - 1) * 7:self._sdo_seqno * 7]
                                                sdo_data = sdo_data.ljust(7, b'\x00')
                                                data = struct.pack("<B7s", (c << 7) + self._sdo_seqno, sdo_data)
                                                sdo_server_scid = sdo_server_object.get(ODSI_SDO_SERVER_DEFAULT_SCID)
                                                if sdo_server_scid is None:
                                                    raise ValueError("SDO Server SCID not specified")
                                                arbitration_id = sdo_server_scid.value & 0x1FFFFFFF
                                                is_extended_id = bool(sdo_server_scid.value & 0x20000000)
                                                msg = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=is_extended_id, channel=msg.channel)
                                                self._send(msg, msg.channel)
                                                data_len -= 7
                                                self._sdo_seqno += 1
                                            if hasattr(self._sdo_data, "seek"):
                                                self._sdo_data.seek((1 - self._sdo_seqno) * 7 - min(0, data_len), io.SEEK_CUR)
                                            return
                                    else: # SDO_BLOCK_SUBCOMMAND_END
                                        if self._sdo_cs != SDO_SCS_BLOCK_UPLOAD:
                                            logger.error(f"SDO Request aborted, invalid cs: {ccs:d}")
                                            raise SdoAbort(0, 0, SDO_ABORT_INVALID_CS);
                                        logger.info(f"SDO block upload end request for mux 0x{self._sdo_odi:04X}{self._sdo_odsi:02X}")
                                        self._sdo_cs = None
                                        self._sdo_data = None
                                        self._sdo_len = None
                                        self._sdo_odi = None
                                        self._sdo_odsi = None
                                        self._sdo_seqno = 0
                                        self._sdo_t = None
                                        return
                                else:
                                    raise SdoAbort(0, 0, SDO_ABORT_INVALID_CS)
                        except SdoAbort as a:
                            logger.error(f"SDO aborted for mux 0x{a.index:04X}{a.subindex:02X} with error code 0x{a.code:08X}")
                            self._sdo_seqno = 0
                            self._sdo_data = None
                            self._sdo_len = None
                            self._sdo_t = None
                            self._sdo_odi = None
                            self._sdo_odsi = None
                            scs = SDO_CS_ABORT
                            data = struct.pack("<BHBI", scs << SDO_CS_BITNUM, a.index, a.subindex, a.code)
                        sdo_server_scid = sdo_server_object.get(ODSI_SDO_SERVER_DEFAULT_SCID)
                        if sdo_server_scid is None:
                            raise ValueError("SDO Server SCID not specified")
                        arbitration_id = sdo_server_scid.value & 0x1FFFFFFF
                        is_extended_id = bool(sdo_server_scid.value & 0x20000000)
                        msg = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=is_extended_id, channel=msg.channel)
                        self._send(msg, msg.channel)

                # Store responses to SDO requests
                # Start with pre-defiined connection set
                if (can_id >> FUNCTION_CODE_BITNUM) == FUNCTION_CODE_SDO_TX:
                    sdo_client_rx_can_id = (FUNCTION_CODE_SDO_RX << FUNCTION_CODE_BITNUM) + (can_id & 0x7F)
                else:
                    sdo_client_rx_can_id = None
                # Check for client COB-IDs
                for index in range(ODI_SDO_CLIENT, ODI_SDO_CLIENT + 0x80):
                    if index in self.od:
                        sdo_client_parameters = True
                        sdo_client_tx_cob_id = self.od.get(index).get(ODSI_SDO_CLIENT_TX).value
                        sdo_client_rx_cob_id = self.od.get(index).get(ODSI_SDO_CLIENT_RX).value
                        if (sdo_client_rx_cob_id & 0x8000) == 0 and (sdo_client_rx_cob_id & 0x8000) == 0 and can_id == (sdo_client_tx_cob_id & 0x1FFFFFFF):
                            sdo_client_rx_can_id = sdo_client_rx_cob_id & 0x1FFFFFFF
                            break
                if sdo_client_rx_can_id is not None:
                    sdo_request = self._sdo_requests.get(sdo_client_rx_can_id)
                    if sdo_request is not None:
                        sdo_request.respond(msg.data)
                    else:
                        logger.warning(f"SDO message discarded with CAN ID {can_id:03X}, no match for {sdo_client_rx_can_id:03X}")

            threading.Thread(target=self.on_message, args=(msg,), daemon=True).start()

    def _process_sync(self):
        sync_object = self.od.get(ODI_SYNC)
        if sync_object is not None:
            sync_object_value = sync_object.get(ODSI_VALUE)
            if sync_object_value is not None and sync_object_value.value is not None:
                is_sync_producer = (sync_object_value.value & 0x40000000) != 0
            else:
                is_sync_producer = False
        else:
            is_sync_producer = False
        sync_time = 0
        sync_time_object = self.od.get(ODI_SYNC_TIME)
        if sync_time_object is not None:
            sync_time_value = sync_time_object.get(ODSI_VALUE)
            if sync_time_value is not None and sync_time_value.value is not None:
                sync_time = sync_time_value.value / 1000000
        logger.info(f"Node is now {'' if is_sync_producer else 'not '}the SYNC producer with a cycle time of {sync_time} seconds")
        with self._sync_timer_lock:
            self._cancel_timer(self._sync_timer)
            if is_sync_producer and sync_time != 0:
                self._sync_timer = IntervalTimer(sync_time, self._send_sync)
                self._sync_timer.start()

    def _reset_timers(self):
        with self._message_timers_lock:
            for t in self._message_timers:
                self._cancel_timer(t)
        with self._heartbeat_consumer_timers_lock:
            for i, t in self._heartbeat_consumer_timers.items():
                self._cancel_timer(t)
        with self._err_indicator_timer_lock:
            self._cancel_timer(self._err_indicator_timer)
        with self._heartbeat_evaluation_reset_communication_timer_lock:
            self._cancel_timer(self._heartbeat_evaluation_reset_communication_timer)
        with self._heartbeat_producer_timer_lock:
            self._cancel_timer(self._heartbeat_producer_timer)
        with self._sync_timer_lock:
            self._cancel_timer(self._sync_timer)
        with self._nmt_active_master_timer_lock:
            self._cancel_timer(self._nmt_active_master_timer)
        with self._nmt_flying_master_timer_lock:
            self._cancel_timer(self._nmt_flying_master_timer)
        with self._nmt_multiple_master_timer_lock:
            self._cancel_timer(self._nmt_multiple_master_timer)

    def _sdo_request(self, request):
        index, subindex = struct.unpack("<HB", request.sdo_data[0:3])
        # Check for client COB-IDs
        for odi in range(ODI_SDO_CLIENT, ODI_SDO_CLIENT + 0x80):
            if odi in self.od:
                sdo_client_obj = self.od.get(odi)
                if request.node_id == sdo_client_obj.get(ODSI_SDO_CLIENT_NODE_ID).value:
                    sdo_client_tx_cob_id = sdo_client_obj.get(ODSI_SDO_CLIENT_TX).value
                    sdo_client_rx_cob_id = sdo_client_obj.get(ODSI_SDO_CLIENT_RX).value
                    if sdo_client_tx_cob_id & 0x80000000 and sdo_client_rx_cob_id & 0x80000000:
                        raise SdoAbort(index, subindex, SDO_ABORT_CONNECTION) # SDO is not valid
                    request.arbitration_id = sdo_client_rx_cob_id & 0x1FFFFFFF
                    break
        if self._sdo_requests.get(request.arbitration_id) is not None:
            self._send(SdoAbortResponse(request.arbitration_id, index, subindex, SDO_ABORT_GENERAL))
        self._sdo_requests[request.arbitration_id] = SdoRequestEvent(index, subindex)
        logger.info(f"Sending SDO request with CAN ID {request.arbitration_id:03X}")
        self._send(request)
        response = None
        try:
            self._sdo_requests[request.arbitration_id].wait(self.SDO_TIMEOUT)
            response = self._sdo_requests[request.arbitration_id].response
            del self._sdo_requests[request.arbitration_id]
        except KeyError:
            pass
        if response is None:
            logger.error(f"SDO timeout for CAN ID {request.arbitration_id:03X}")
            raise SdoTimeout(index, subindex)
        logger.info(f"Received SDO response for CAN ID {request.arbitration_id:03X}")
        if (response[0] >> SDO_CS_BITNUM) == SDO_CS_ABORT:
            raise SdoAbort(index, subindex, int.from_bytes(response[4:8], byteorder="little"))
        return response

    def _sdo_download_request(self, node_id, index, subindex, sdo_data):
        sdo_data = sdo_data.ljust(4, b'\x00')
        response = self._sdo_request(SdoDownloadInitiateRequest(node_id, 0, 1, 0, index, subindex, sdo_data))
        if (response[0] >> SDO_CS_BITNUM) != SDO_SCS_DOWNLOAD_INITIATE:
            raise SdoAbort(index, subindex, SDO_ABORT_INVALID_CS)
        return response[4:8]

    def _sdo_upload_request(self, node_id, index, subindex):
        response = self._sdo_request(SdoUploadInitiateRequest(node_id, index, subindex))
        if (response[0] >> SDO_CS_BITNUM) != SDO_SCS_UPLOAD_INITIATE:
            raise SdoAbort(index, subindex, SDO_ABORT_INVALID_CS)
        return response[4:8]

    def _send(self, msg: can.Message, channel=None):
        if channel is None:
            bus = self.active_bus
        elif self.redundant_bus is not None and channel == self.redundant_bus.channel:
            bus = self.redundant_bus
        else:
            bus = self.default_bus
        max_tx_delay = None
        if ODI_REDUNDANCY_CONFIGURATION in self.od: # CiA 302-6, 4.1.2.2(b)
            redundancy_cfg = self.od.get(ODI_REDUNDANCY_CONFIGURATION)
            max_tx_delay = redundancy_cfg.get(0x01).value / 1000
        try:
            bus.send(msg, max_tx_delay)
        except can.CanError as e:
            self._on_can_error(bus.channel)
            if bus == self.default_bus and max_tx_delay is not None: # CiA 302-6, Section 7.1.2.2(d)
                err_threshold = redundancy_cfg.get(0x04)
                err_counter = redundancy_cfg.get(0x05)
                err_counter.value = min(err_threshold.value, err_counter.value + 4)
                redundancy_cfg.update({0x05: err_counter})
                self.od.update({ODI_REDUNDANCY_CONFIGURATION: redundancy_cfg})
                if self.active_bus == self.default_bus and err_counter.value == err_threshold.value:
                    self._default_bus_heartbeat_disabled = True
                    self.active_bus = self.redundant_bus
                    self.send_nmt(NmtIndicateActiveInterfaceMessage())
        else:
            if bus == self.default_bus and max_tx_delay is not None: # CiA 302-6, Section 7.1.2.2(e)
                err_counter = redundancy_cfg.get(0x05)
                err_counter.value = min(0, err_counter.value - 1)
                redundancy_cfg.update({0x05: err_counter})
                self.od.update({ODI_REDUNDANCY_CONFIGURATION: redundancy_cfg})
                if err_counter.value == 0:
                    self._default_bus_heartbeat_disabled = False

    def _send_emcy(self, eec, msef=0):
        emcy_id_obj = self.od.get(ODI_EMCY_ID)
        if emcy_id_obj is None:
            return
        emcy_id_value = emcy_id_obj.get(ODSI_VALUE)
        if emcy_id_value is None:
            return
        if emcy_id_value.value is None:
            return
        er_obj = self.od.get(ODI_ERROR)
        if er_obj is None:
            return
        er_value = er_obj.get(ODSI_VALUE)
        if er_value is None:
            return
        if er_value.value is None:
            return
        self.on_emcy(emcy_id_value, eec, er_value, msef)
        msg = EmcyMessage(emcy_id_value.value, eec, er_value.value, msef)
        if self._nmt_state == NMT_STATE_STOPPED and self._redundant_nmt_state == NMT_STATE_STOPPED:
            self._pending_emcy_msgs.append(msg)
            return
        emcy_inhibit_time_obj = self.od.get(ODI_INHIBIT_TIME_EMCY)
        if emcy_inhibit_time_obj is not None:
            emcy_inhibit_time_subobj = emcy_inhibit_time_obj.get(ODSI_VALUE)
            if emcy_inhibit_time_subobj.value != 0:
                emcy_inhibit_time = emcy_inhibit_time_subobj.value / 10000
                if self._emcy_inhibit_time + emcy_inhibit_time < time.time():
                    logger.info("EMCY inhibit time violation, delaying message")
                    self._emcy_inhibit_time += emcy_inhibit_time
                    if self._nmt_state == NMT_STATE_PREOPERATIONAL or self._nmt_state == NMT_STATE_OPERATIONAL:
                        with self._message_timers_lock:
                            t = threading.Timer(time.time() - self._emcy_inhibit_time, self._send, [msg, self.default_bus.channel])
                            t.start()
                            self._message_timers.append(t)
                    if self._redundant_nmt_state == NMT_STATE_PREOPERATIONAL or self._redundant_nmt_state == NMT_STATE_OPERATIONAL:
                        with self._message_timers_lock:
                            t = threading.Timer(time.time() - self._emcy_inhibit_time, self._send, [msg, self.redundant_bus.channel])
                            t.start()
                            self._message_timers.append(t)
                    return
        if self._nmt_state == NMT_STATE_PREOPERATIONAL or self._nmt_state == NMT_STATE_OPERATIONAL:
            self._send(msg, channel=self.default_bus.channel)
        if self._redundant_nmt_state == NMT_STATE_PREOPERATIONAL or self._redundant_nmt_state == NMT_STATE_OPERATIONAL:
            self._send(msg, channel=self.redundant_bus.channel)

    def _send_heartbeat(self):
        msg = HeartbeatMessage(self.id, self.nmt_state)
        if not self._default_bus_heartbeat_disabled:
            self._send(msg, self.default_bus.channel)
        if self.redundant_bus is not None:
            self._send(msg, self.redundant_bus.channel)

    def _send_pdo(self, i):
        i = i - 1
        data = bytes()
        tpdo_mp = self.od.get(ODI_TPDO1_MAPPING_PARAMETER + i)
        if tpdo_mp is not None:
            tpdo_mp_length = tpdo_mp.get(ODSI_VALUE)
            if tpdo_mp_length is not None and tpdo_mp_length.value is not None:
                for j in range(tpdo_mp_length.value):
                    mapping_param = tpdo_mp.get(j + 1)
                    if mapping_param is not None and mapping_param.value is not None:
                        mapped_obj = self.od.get(mapping_param.value >> 16)
                        if mapped_obj is not None:
                             mapped_subobj = mapped_obj.get((mapping_param.value >> 8) & 0xFF)
                        else:
                            raise ValueError("Mapped PDO object does not exist")
                        if mapped_subobj is not None:
                            mapped_bytes = bytes(mapped_subobj)
                            if len(mapped_bytes) != ((mapping_param.value & 0xFF) // 8):
                                raise ValueError("PDO Mapping length mismatch")
                            data = data + mapped_bytes
                    else:
                        raise ValueError("Mapped PDO object does not exist")
                tpdo_cp = self.od.get(ODI_TPDO1_COMMUNICATION_PARAMETER + i)
                if tpdo_cp is not None:
                    tpdo_cp_id = tpdo_cp.get(ODSI_TPDO_COMM_PARAM_ID)
                    if tpdo_cp_id is not None and tpdo_cp_id.value is not None:
                        arbitration_id = tpdo_cp_id.value & 0x1FFFFFFF
                        is_extended_id = bool(tpdo_cp_id.value & 0x20000000)
                        msg = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=is_extended_id)
                        self._tpdo_triggers[i] = False
                        if ODSI_TPDO_COMM_PARAM_INHIBIT_TIME in tpdo_cp:
                            tpdo_inhibit_time = tpdo_cp.get(ODSI_TPDO_COMM_PARAM_INHIBIT_TIME).value / 10000
                            if i not in self._tpdo_inibit_time:
                                self._tpdo_inhibit_times[i] = 0
                            if self._tpdo_inhibit_times[i] + tpdo_inhibit_time < time.time():
                                logger.info(f"TPDO{i} inhibit time violation, delaying message")
                                self._tpdo_inhibit_times[i] += tpdo_inhibit_time
                                # CiA 302-6, 4.1.2.2(a)
                                if self._nmt_state == NMT_STATE_OPERATIONAL:
                                    with self._message_timers_lock:
                                        t = threading.Timer(time.time() - self._tpdo_inhibit_times[i], self._send, [msg, self.default_bus.channel])
                                        t.start()
                                        self._message_timers.append(t)
                                if self._redundant_nmt_state == NMT_STATE_OPERATIONAL:
                                    with self._message_timers_lock:
                                        t = threading.Timer(time.time() - self._tpdo_inhibit_times[i], self._send, [msg, self.redundant_bus.channel])
                                        t.start()
                                        self._message_timers.append(t)
                        else:
                            if self._nmt_state == NMT_STATE_OPERATIONAL:
                                 self._send(msg, self.default_bus.channel)
                            if self._redundant_nmt_state == NMT_STATE_OPERATIONAL:
                                 self._send(msg, self.redundant_bus.channel)

    def _send_sync(self):
        sync_object = self.od.get(ODI_SYNC)
        if sync_object is not None:
            sync_value = sync_object.get(ODSI_VALUE)
            if sync_value is not None and sync_value.value is not None:
                arbitration_id = sync_value.value & 0x1FFFFFFF
                is_extended_id = bool(sync_value.value & 0x20000000)
                sync_overflow_object = self.od.get(ODI_SYNCHRONOUS_COUNTER_OVERFLOW_VALUE)
                data = []
                if sync_overflow_object is not None:
                    sync_overflow = sync_overflow_object.get(ODSI_VALUE)
                    if sync_overflow is not None and sync_overflow.value > 1 and sync_overflow.value < 241:
                        if self._sync_producer_counter >= sync_overflow.value:
                            self._sync_producer_counter = 1
                        else:
                            self._sync_producer_counter += 1
                        data = [self._sync_producer_counter]
                msg = can.Message(arbitration_id=arbitration_id, is_extended_id=is_extended_id, data=data)
                if self._nmt_state == NMT_STATE_PREOPERATIONAL or self._nmt_state == NMT_STATE_OPERATIONAL:
                    self._send(msg, self.default_bus.channel)
                if self._redundant_nmt_state is not None and self._redundant_nmt_state == NMT_STATE_PREOPERATIONAL or self._redundant_nmt_state == NMT_STATE_OPERATIONAL:
                    self._send(msg, self.redundant_bus.channel)
                self._on_sync()

    def _start_listening(self, channel):
        if channel == self.default_bus.channel:
            self._notifier.add_listener(self._listener)
        else:
            self._redundant_notifier.add_listener(self._redundant_listener)
        logger.debug(f"Listening on {'all channels' if channel is None else channel}")

    def _stop_listening(self, channel=None):
        if channel is None or channel == self.default_bus.channel:
            try:
                self._notifier.remove_listener(self._listener)
                logger.debug(f"Stopped listening on {self.default_bus.channel}")
            except ValueError:
                pass
        if channel is None or channel == self.redundant_bus.channel:
            try:
                self._redundant_notifier.remove_listener(self._redundant_listener)
                logger.debug(f"Stopped listening on {self.redundant_bus.channel}")
            except ValueError:
                pass

    @property
    def active_bus(self):
        return self._active_bus

    @active_bus.setter
    def active_bus(self, bus):
        logger.info(f"Active bus is now {bus.channel}")
        self._active_bus = bus

    def emcy(self, eec, msef=0):
        errors_obj = self.od.get(ODI_PREDEFINED_ERROR_FIELD)
        if errors_obj is not None:
            errors_length_subobj = errors_obj.get(ODSI_VALUE)
            errors_length_subobj.value = max(0xFF, errors_length_subobj.value + 1)
            errors_obj.update({ODSI_VALUE: errors_length_subobj})
            for si in range(1, errors_length_subobj.value):
                errors_obj.update({(si + 1): errors_obj.get(si)})
            errors_obj.update({0x01: SubObject(
                parameter_name="Standard error field",
                access_type=AccessType.RO,
                data_type=ODI_DATA_TYPE_UNSIGNED32,
                low_limit=0x00000000,
                high_limit=0xFFFFFFF,
                default_value=((msef & 0xFFFF) << 16) + eec
            )})
            self.od.update({ODI_PREDEFINED_ERROR_FIELD: errors_obj})
        self._send_emcy(eec, msef)

    @property
    def nmt_state(self):
        if self.active_bus.channel == self.default_bus.channel:
            return self._nmt_state
        else:
            return self._redundant_nmt_state

    @nmt_state.setter
    def nmt_state(self, nmt_state):
        channel = None
        if isinstance(nmt_state, tuple):
            nmt_state, channel = nmt_state
        if channel is None:
            channel = self.active_bus.channel
        logger.info(f"Entering NMT state on {channel} with value 0x{nmt_state:02X}")
        if channel == self.default_bus.channel:
            self._nmt_state = nmt_state
            try:
                self._run_indicator.set_state(nmt_state)
            except AttributeError:
                pass
        else:
            self._redundant_nmt_state = nmt_state
            try:
                self._redundant_run_indicator.set_state(nmt_state)
            except AttributeError:
                pass
        for msg in self._pending_emcy_msgs:
            self.send_emcy(msg)

        # End of NMT startup, part 2
        if self.is_active_nmt_master and nmt_state == NMT_STATE_OPERATIONAL and channel == self.active_bus.channel:
            nmt_startup = self.od.get(ODI_NMT_STARTUP).get(ODSI_VALUE).value
            if (nmt_startup & 0x08) == 0:
                if nmt_startup & 0x02:
                    logger.info("Starting all NMT slaves")
                    self.send_nmt(NmtNodeControlMessage(NMT_NODE_CONTROL_START, 0))
                elif slave_assignment_obj is not None:
                    for slave_id in range(1, slave_assignment_obj_length + 1):
                        slave_assignment = slave_assignment_obj.get(slave_id).value
                        if slave_assignment & 0x01:
                            logger.info(f"Starting NMT slave with node-ID {slave_id}")
                            self.send_nmt(NmtNodeControlMessage(NMT_NODE_CONTROL_START, slave_id))

    @property
    def is_active_nmt_master(self):
        return self._nmt_active_master

    @property
    def is_nmt_master_capable(self):
        nmt_startup_obj = self.od.get(ODI_NMT_STARTUP)
        if nmt_startup_obj is not None:
            nmt_startup = nmt_startup_obj.get(ODSI_VALUE).value
            if nmt_startup & 0x01:
                return True
        return False

    def on_active_nmt_master_lost(self):
        pass

    def on_active_nmt_master_won(self):
        pass

    def on_emcy(self, can_id, eec, er, msef):
        pass

    def on_error(self, msg, args):
        pass

    def on_message(self, msg):
        pass

    def on_node_bootup(self, id, in_network): # CiA 302-2 section 4.3
        pass

    def on_sdo_download(self, odi, odsi, obj, sub_obj):
        pass

    def on_sync(self):
        pass

    def recv(self):
        return self.active_bus.recv() # Returns can.Message

    def reset(self):
        logger.info("Device reset")
        self._stop_listening()
        self.active_bus = self.default_bus
        self.nmt_state = (NMT_STATE_INITIALISATION, self.default_bus.channel)
        if self.redundant_bus is not None:
            self.nmt_state = (NMT_STATE_INITIALISATION, self.redundant_bus.channel)
        for odi, obj in self.od.items():
            for odsi, subobj in obj.items():
                subobj.value = subobj.default_value
                obj.update({odsi: subobj})
            self.od.update({odi: obj})
        self._heartbeat_evaluation_counters = {}
        if ODI_REDUNDANCY_CONFIGURATION in self.od:
            logger.info("Node is configured for redundancy")
            redundancy_cfg = self.od.get(ODI_REDUNDANCY_CONFIGURATION)
            heartbeat_eval_time = redundancy_cfg.get(ODSI_REDUNDANCY_CONFIG_HB_EVAL_TIME_POWER_ON).value
            logger.info(f"Starting heartbeat evaluation timer (power-on) for {heartbeat_eval_time} seconds")
            with self._heartbeat_evaluation_power_on_timer_lock:
                self._cancel_timer(self._heartbeat_evaluation_power_on_timer)
                self._heartbeat_evaluation_power_on_timer = threading.Timer(heartbeat_eval_time, self._heartbeat_evaluation_power_on_timeout)
                self._heartbeat_evaluation_power_on_timer.start()
        if self.redundant_bus is not None:
            self._redundant_reset_communication_thread = threading.Thread(target=self.reset_communication, args=(self.redundant_bus.channel,), daemon=True)
            self._redundant_reset_communication_thread.start()
        self.reset_communication(self.default_bus.channel)

    def reset_communication(self, channel=None):
        if channel is None:
            channel = self.active_bus.channel
        logger.info(f"Device reset communication on {channel}")
        self._stop_listening(channel)
        self.nmt_state = (NMT_STATE_INITIALISATION, channel)
        for can_id, request in self._sdo_requests.items():
            request.set() # Resolve pending SDO requests
        self._reset_timers()
        if self._err_indicator is not None:
            with self._err_indicator_timer_lock:
                self._cancel_timer(self._err_indicator_timer)
                self._err_indicator_timer = IntervalTimer(self._err_indicator.interval, self._process_err_indicator)
                self._err_indicator_timer.start()
        for odi, obj in self.od.items():
            if odi < 0x1000 or odi > 0x1FFF:
                continue
            for odsi, subobj in obj.items():
                subobj.value = subobj.default_value
                obj.update({odsi: subobj})
            self.od.update({odi: obj})
        self._heartbeat_evaluation_counters = {}
        if ODI_REDUNDANCY_CONFIGURATION in self.od and channel == self.active_bus.channel:
            logger.info("Node is configured for redundancy")
            redundancy_cfg = self.od.get(ODI_REDUNDANCY_CONFIGURATION)
            timer_was_running = self._cancel_timer(self._heartbeat_evaluation_power_on_timer)
            if channel == self.default_bus.channel and timer_was_running: # CiA 302-6, Figure 7, event (3)
                heartbeat_eval_time = redundancy_cfg.get(ODSI_REDUNDANCY_CONFIG_HB_EVAL_TIME_POWER_ON).value
                logger.info(f"Restarting heartbeat evaluation timer (power-on) for {heartbeat_eval_time} seconds")
                with self._heartbeat_evaluation_power_on_timer_lock:
                    #self._cancel_timer(self._heartbeat_evaluation_power_on_timer) # Already cancelled above
                    self._heartbeat_evaluation_power_on_timer = threading.Timer(heartbeat_eval_time, self._heartbeat_evaluation_power_on_timeout)
                    self._heartbeat_evaluation_power_on_timer.start()
            else: # CiA 302-6, Figure 7, event (10) or (11)
                heartbeat_eval_time = redundancy_cfg.get(ODSI_REDUNDANCY_CONFIG_HB_EVAL_TIME_RESET_COMM).value
                logger.info(f"Restarting heartbeat evaluation timer (reset communication) for {heartbeat_eval_time} seconds")
                with self._heartbeat_evaluation_reset_communication_timer_lock:
                    self._cancel_timer(self._heartbeat_evaluation_reset_communication_timer)
                    self._heartbeat_evaluation_reset_communication_timer = threading.Timer(heartbeat_eval_time, self._heartbeat_evaluation_reset_communication_timeout)
                    self._heartbeat_evaluation_reset_communication_timer.start()
        self._pending_emcy_msgs = []
        self._boot(channel)

    def reset_emcy(self):
        self._send_emcy(0)

    def send_nmt(self, msg):
        nmt_inhibit_time_obj = self.od.get(ODI_NMT_INHIBIT_TIME)
        if nmt_inhibit_time_obj is not None:
            nmt_inhibit_time_subobj = nmt_inhibit_time_obj.get(ODSI_VALUE)
            if nmt_inhibit_time_subobj.value != 0:
                nmt_inhibit_time = nmt_inhibit_time_subobj.value / 1000
                if self._nmt_inhibit_time + nmt_inhibit_time < time.time():
                    logger.info("NMT inhibit time violation, delaying message")
                    self._nmt_inhibit_time += nmt_inhibit_time
                    with self._message_timers_lock:
                        t = threading.Timer(time.time() - self._nmt_inhibit_time, self._send, [msg])
                        t.start()
                        self._message_timers.append(t)
                    return
        return self._send(msg)

    def send_time(self, ts=None):
        if ts is None:
            ts = self.timestamp
        if not isinstance(ts, datetime.datetime):
            raise ValueError("Timestamp must be of type datetime")
        if ts < EPOCH:
            raise ValueError(f"Timestamp must be no earlier than {EPOCH}")
        time_obj = self.od.get(ODI_TIME_STAMP)
        if time_obj is None:
            return False
        time_cob_id = time_obj.get(ODSI_VALUE).value
        if time_cob_id & 0x40000000:
            td = ts - EPOCH
            arbitration_id = time_cob_id & 0x1FFFFFFF
            data = struct.pack("<IH", round(td.seconds * 1000 + td.microseconds / 1000), td.days)
            is_extended_id = bool(time_cob_id & 0x20000000)
            msg = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=is_extended_id)
            max_tx_delay = None
            if self._nmt_state == NMT_STATE_OPERATIONAL or self._nmt_state == NMT_STATE_PREOPERATIONAL:
                self._send(msg, channel=self.default_bus.channel)
            if self._redundant_nmt_state == NMT_STATE_OPERATIONAL or self._redundant_nmt_state == NMT_STATE_PREOPERATIONAL:
                self._send(msg, channel=self.redundant_bus.channel)
            logger.info(f"Sent TIME object with {ts}")

    @property
    def timestamp(self):
        return datetime.datetime.now(datetime.timezone.utc) + self._timedelta

    @timestamp.setter
    def timestamp(self, ts=None):
        if ts is None:
            self._timedelta = datetime.timedelta()
        elif isinstance(ts, datetime.datetime):
            if ts < EPOCH:
                raise ValueError(f"Timestamp must be no earlier than {EPOCH}")
            self._timedelta = ts - datetime.datetime.now(datetime.timezone.utc)

    def trigger_tpdo(self, tpdo): # Event-driven TPDO
        tpdo_cp = self.od.get(ODI_TPDO1_COMMUNICATION_PARAMETER + tpdo - 1)
        if tpdo_cp is not None:
            tpdo_cp_id = tpdo_cp.get(ODSI_TPDO_COMM_PARAM_ID)
            if tpdo_cp_id is not None and (tpdo_cp_id >> TPDO_COMM_PARAM_ID_VALID_BITNUM) & 1 == 0:
                tpdo_cp_type = tpdo_cp.get(ODSI_TPDO_COMM_PARAM_TYPE)
                if tpdo_cp_type is not None and (tpdo_cp_type == 0xFE or tpdo_cp_type == 0xFF):
                    self._send_pdo(tpdo)
                else:
                    self._tpdo_triggers[tpdo] = True # Defer until SYNC event

    def update_configuration(self, slave_id):
        # Per CiA 302-3
        raise NotImplementedError
