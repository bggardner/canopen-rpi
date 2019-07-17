#!/usr/bin/python3
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
from os import path
import re
from select import select
import signal
from socketserver import ThreadingMixIn
import struct
import sys
from time import sleep, time
import traceback
from urllib.parse import parse_qsl, urlparse

import socketcan
import socketcanopen

# Server constants
CAN_INTERFACES = ["vcan0", "vcan1"] # Must be a list
HTTP_SERVER_IP_ADDRESS = "" # Empty string for any address
HTTP_SERVER_PORT = 8002
WWW_DIR = path.dirname(path.realpath(__file__))

# Gateway variables (default value assignments)
default_net = "vcan0" # When 'default' net is specified
default_node_id = 0xFF # 0xFF = Invalid
command_timeout = 1 # Default, in seconds (value sent in ms)
sdo_timeout = 1 # Default, in seconds (value sent in ms)
rpdos = {}
tpdos = {}

def sigterm_handler(signum, frame):
    sys.exit()

def coerce(value, datatype):
    if value is None:
        return ValueError("Unable to coerce undefined value")
    if datatype == "b": # Boolean
        return bool(value)
    if datatype in ["u8", "u16", "u24", "u32", "u40", "u48", "u56", "u64", "i8", "i16", "i24", "i32", "i40", "i48", "i56", "i64"]:
        return int(value, 0)
    if datatype in ["r32", "r64"]:
        return float(value)
    if datatype in ["t", "td", "vs", "os", "us", "d"]:
        raise NotImplementedError
    raise ValueError("Unknown datatype: " + str(datatype))


def parse_request(request):
    match = re.match('/cia309-5/(\d+\.\d+)/(\d{1,10})/(0x[0-9a-f]{1,4}|\d{1,10}|default|none|all)/(0x[0-9a-f]{1,2}|\d{1,3}|default|none|all)/(.*)', request, re.IGNORECASE)
    if match is None:
        raise ValueError("invalid syntax")

    api_version = match.group(1)
    if api_version != '1.0':
        raise NotImplementedError

    sequence = match.group(2)
    sequence = int(sequence)
    if sequence > 4294967295:
        raise ValueError("invalid sequence: " + str(sequence))

    net = match.group(3)
    if net[0] == '0' and net[1] == 'x':
        net = int(net, 16)
    else:
        try:
            net = int(net)
        except ValueError:
            pass
    if type(net) == int and (net == 0 or net > 0xFFFF):
        raise ValueError("invalid net: " + str(net))

    node = match.group(4)
    if node[0] == '0' and node[1] == 'x':
        node = int(node, 16)
    else:
        try:
            node = int(node)
        except ValueError:
            pass
    if type(node) == int and (node == 0 or (node > 127 and node != 255)):
        raise ValueError("invalid node: " + str(node))

    command = match.group(5)
    #command = parse_command(command)
    return (sequence, net, node, command)

def parse_net(net):
    global default_net
    if net == 'default':
        net = default_net
    else:
        net = CAN_INTERFACES[int(net) - 1]
    return socketcan.Bus(net)

def parse_command(command):
    if command[0:2] == 'r/' or command[0:5] == 'read/':
        command_specifier = 'r'
    elif command[0:2] == 'w/' or command[0:6] == 'write/':
        command_specifier = 'w'
    elif command == 'start':
        command_specifier = 'start'
    elif command == 'stop':
        command_specifier = 'stop'
    elif command == 'preop' or command[0:11] == "preoperational":
        command_specifier = 'preop'
    elif command == 'reset/node':
        command_specifier = 'reset/node'
    elif command == 'reset/comm' or command[0:19] == 'reset/communication':
        command_specifier = 'reset/comm'
    elif command == 'set/sdo-timeout':
        command_specifier = 'set/sdo-timeout'
    elif command == 'set/rpdo':
        command_specifier = 'set/rpdo'
    elif command == 'set/tpdo':
        command_specifier = 'set/tpdo'
    elif command == 'set/tpdox':
        command_specifier = 'set/tpdox'
    elif command == 'set/heartbeat':
        command_specifier = 'set/heartbeat'
    elif command == 'set/id':
        command_specifier = 'set/id'
    elif command == 'set/command-timeout':
        command_specifier = 'set/command-timeout'
    elif command == 'set/network':
        command_specifier = 'set/network'
    elif command == 'set/node':
        command_specifier = 'set/node'
    elif command == 'set/command-size':
        command_specifier = 'set/command-size' 
    else:
        raise ValueError("invalid command: " + command)
    return command_specifier

def parse_int(value, max=sys.maxsize):
    int_value = int(value, 0)
    if int_value > max:
        raise ValueError("invalid integer value: " + str(value))
    return int_value

def exec_sdo(bus: socketcan.Bus, request: socketcanopen.SdoRequest, timeout) -> socketcanopen.SdoResponse:
    bus.send(request)
    timeout_time = time() + timeout
    dtimeout = timeout
    while dtimeout > 0:
        rlist, _, _ = select([bus], [], [], dtimeout)
        if len(rlist) > 0:
            bus = rlist[0]
            response = socketcanopen.Message.factory(bus.recv())
            if isinstance(response, socketcanopen.SdoResponse) and response.node_id == request.node_id and response.index == request.index and response.subindex == request.subindex:
                if isinstance(response, socketcanopen.SdoAbortResponse):
                    raise socketcanopen.SdoAbort(response.index, response.subindex, response.sdo_data)
                if isinstance(request, socketcanopen.SdoUploadRequest) and isinstance(response, socketcanopen.SdoUploadResponse):
                    return response
                if isinstance(request, socketcanopen.SdoDownloadRequest) and isinstance(response, socketcanopen.SdoDownloadResponse):
                    return response
                # Unsupported socketcanopen.SdoResponse, ignore and keep listening
            dtimeout = timeout_time - time()
        else:
            raise socketcanopen.SdoTimeout # Timeout from select
    raise socketcanopen.SdoTimeout

def read_pdo(bus: socketcan.Bus, nr, timeout):
    global rpdos
    rpdo = rpdos.get(nr)
    if rpdo is None:
        raise ValueError
    cob = rpdo.get('cob')
    if cob is None:
        raise ValueError
    datatypes = rpdo.get('datatypes')
    if datatypes is None:
        raise ValueError
    timeout_time = time() + timeout
    dtimeout = timeout
    while dtimeout > 0:
        rlist, _, _ = select([bus], [], [], dtimeout)
        if len(rlist) > 0:
            bus = rlist[0]
            msg = bus.recv()
            if msg.arbitration_id & 0x7FF == rpdos.get(nr).get('cob'):
                return list(msg.data) # TODO: Unpack data based on data types
            dtimeout = timeout_time - time()
        else:
            raise Exception # Timeout
    return list(range(len(datatypes)))

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    pass

class BadRequest(BaseException):
    def __init__(self, arg):
        self.args = arg

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global sdo_timeout, rpdos, tpdos
        request = urlparse(self.path).path

        if request == "/favicon.ico":
            self.send_response(204)
            return

        content_len = int(self.headers.get('content-length', 0)) # access POST/PUT body
        if content_len == 0:
            parameters = {}
        else:
            body = self.rfile.read(content_len) # read POST/PUT body
            body = body.decode('utf-8')
            parameters = dict(parse_qsl(body))

        try: # excepts bad stuff
            try: # excepts for HTTP 200
                try:
                    sequence, net, node, command = parse_request(request)
                except Exception as e:
                    raise BadRequest(str(e))

                command_response = {"sequence": str(sequence)}

                try:
                    bus = parse_net(net)
                except:
                    raise BadRequest("invalid net: " + str(net))

                if command in ['start', 'stop', 'preop', 'reset/node', 'reset/comm']:
                    if command == 'start':
                        cs = socketcanopen.NMT_NODE_CONTROL_START
                    elif command == 'stop':
                        cs = socketcanopen.NMT_NODE_CONTROL_STOP
                    elif command == 'preop' or command == 'preoperational':
                        cs = socketcanopen.NMT_NODE_CONTROL_PREOPERATIONAL
                    elif command == 'reset/node':
                        cs = socketcanopen.NMT_NODE_CONTROL_RESET_NODE
                    elif command == 'reset/comm' or command == 'reset/communication':
                        cs = socketcanopen.NMT_NODE_CONTROL_RESET_COMMUNICATION
                    else:
                        raise BadRequest("Invalid NMT Node Control command-specifier")

                    if node == 'all':
                        node_id = 0
                    elif node_id == 'default':
                        node_id = default_node_id
                    elif node_id == 'none':
                        node_id = None
                    else:
                        node_id = node

                    if node_id is not None:
                        msg = socketcanopen.NmtNodeControlMessage(cs, node_id)
                        bus.send(msg)
                    command_response["response"] = "OK"

                elif command == 'set/sdo-timeout':
                    if not 'value' in parameters:
                        raise BadRequest("value required")
                    value = parameters.get("value")
                    try:
                        value = int(value)
                    except:
                        raise BadRequest("invalid value: " + value)
                    if value >= (2 ** 16):
                        raise BadRequest("invalid value: " + value)
                    sdo_timeout = value / 1000
                    command_response["response"] = "OK"

                elif command == 'set/rpdo':
                    try:
                        nr = parse_int(parameters.get("nr"), 512)
                        cob = parse_int(parameters.get("COB"), 0xFFFFFFFF)
                        nr_of_data = parse_int(parameters.get("nr-of-data"), 0x40)
                        rpdo = rpdos.get(nr, {})
                        rpdo['cob'] = cob
                        mappings = []
                        datatypes = []
                        for i in range(nr_of_data):
                            map_obj = parameters.get("map-obj" + str(i + 1))
                            if map_obj is None:
                                raise BadRequest
                            if type(map_obj) is list:
                                index = parse_int(map_obj[0], 0xFFFF)
                                subindex = parse_int(map_obj[1], 0xFF)
                                mapping = {'index': index, 'subindex': subindex}
                                mappings.append(mapping)
                            else:
                                datatypes.append(map_obj)
                        if len(mappings) == 0:
                            rpdo['datatypes'] = datatypes
                        else:
                            rpdo['mappings'] = mappings
                        rpdos.update({nr: rpdo})
                    except ValueError as e:
                        raise BadRequest(e)
                    command_response["response"] = "OK"

                elif command == 'set/tpdo':
                    raise NotImplementedError

                elif command[0:2] == 'r/' or command[0:5] == 'read/' or command[0:2] == 'w/' or command[0:6] == 'write/':
                    match = re.match('(r|read|w|write)/(all|0x[0-9a-f]{1,4}|\d{1,5})/?(0x[0-9a-f]{1,2}|\d{1,3})?', command, re.IGNORECASE)
                    if match is None:
                        match = re.match('(r|read|w|write)/(p|pdo)/(0x[0-9a-f]{1,3}|\d{1,4})', command, re.IGNORECASE)

                    command_specifier = match.group(1)
                    index = match.group(2)

                    if index == 'p' or index == 'pdo':
                        nr = parse_int(match.group(3), 0x200)
                        rpdo = rpdos.get(nr)
                        if rpdo is None:
                            command_response["response"] = "ERROR:100"
                        else:
                            mappings = rpdo.get('mappings')
                            datatypes = rpdo.get('datatypes')
                            print("reading pdo")
                            values = read_pdo(bus, nr, 10)
                            print(str(len(mappings)) + "," + str(len(datatypes)) + "," + str(len(values)))
                            if mappings is None or datatypes is None or values is None or len(mappings) != len(datatypes) or len(mappings) != len(values):
                                command_response["response"] = "ERROR:100"
                            else:
                                command_response["net"] = net
                                command_response["nr"] = nr
                                command_response["nr-of-data"] = len(mappings)
                                command_response["value"] = values

                    else:

                        if index == 'all':
                            raise NotImplementedError
                        try:
                            index = parse_int(index, 0xFFFF)
                        except ValueError as e:
                            raise BadRequest(e)

                        subindex = match.group(3)
                        try:
                            subindex = parse_int(subindex, 0xFF)
                        except ValueError as e:
                            raise BadRequest(e)

                        if command_specifier == 'r' or command_specifier == 'read':
                            if node == 'all':
                                raise NotImplementedError # May not be a valid request
                            if node != 'none':
                                if node == 'default':
                                    node_id = default_node_id
                                else:
                                    node_id = node

                                if index == 'all':
                                    raise NotImplementedError # "Resource", should use EDS

                                req = socketcanopen.SdoUploadRequest(node_id, index, subindex)
                                res = exec_sdo(bus, req, sdo_timeout)
                                command_response["data"] = "0x{:08X}".format(res.sdo_data)
                                command_response["length"] = "u32" # Lookup data type in EDS?

                        elif command_specifier == 'w' or command_specifier == 'write':
                            if node == 'all':
                                raise NotImplementedError # May not be a valid request
                            if node != 'none':
                                if node == 'default':
                                    node_id = default_node_id
                                else:
                                    node_id = node

                                if index == 'all':
                                    raise BadRequest("invalid index: all")

                                if not 'datatype' in parameters:
                                    print(str(parameters))
                                    raise BadRequest("datatype is required")
                                datatype = parameters.get("datatype")
                                if not 'value' in parameters:
                                    raise BadRequest("value is required")

                                try:
                                    value = coerce(parameters.get("value"), parameters.get("datatype"))
                                except:
                                    raise BadRequest("invalid value/datatype")

                                # TODO: Look these up based on datatype and validate value
                                n = 0
                                e = 1
                                s = 1
                                req = socketcanopen.SdoDownloadRequest(node_id, n, e, s, index, subindex, value)
                                res = exec_sdo(bus, req, sdo_timeout)
                                command_response["response"] = "OK"

                else:
                    raise BadRequest("invalid command: " + command)

            except socketcanopen.SdoAbort as e:
                command_response["response"] = "ERROR:0x" + "{:08X}".format(e.code)
            except socketcanopen.SdoTimeout:
                command_response["response"] = "ERROR:103"

            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'X-Requested-With')
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(bytes(json.dumps(command_response) + "\n", 'utf-8'))

        except BadRequest as e:
            print("Bad Request: " + str(e))
            self.send_response(400)
            self.send_error(400, 'Bad Request: %s' % str(e.args))
        except BrokenPipeError:
            print('Connection closed.')
        except:
            print("Unexpected error:", sys.exc_info()[0])
            traceback.print_exc()
            self.send_response(500)
            self.send_error(500, 'Unexpected Error')

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'X-Requested-With')
        self.send_header('Access-Control-Allow-Headers', 'Content-type')
        self.end_headers()

    def do_POST(self):
        self.do_GET()

    def do_PUT(self):
        self.do_GET()

    def log_message(self, format, *args):
        return # Suppress logging

signal.signal(signal.SIGTERM, sigterm_handler)
srvr = ThreadedHTTPServer((HTTP_SERVER_IP_ADDRESS, HTTP_SERVER_PORT), RequestHandler)
srvr.serve_forever()
