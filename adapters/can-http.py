#!/usr/bin/python3
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from os import path
from select import select
import signal
from socketserver import ThreadingMixIn
import sys
from time import sleep
import traceback
from urllib.parse import parse_qs, urlparse

import socketcan


CAN_SEND_INTERFACE = "vcan0" # When no bus/interface is specified
CAN_LISTEN_INTERFACES = ["vcan0", "vcan1"] # Must be a list
HTTP_SERVER_IP_ADDRESS = "" # Empty string for any address
HTTP_SERVER_PORT = 8000
WWW_DIR = path.dirname(path.realpath(__file__))


def sigterm_handler(signum, frame):
    sys.exit()


def parse_request(request):
    interface = request.get('bus')
    if interface == None:
        interface = CAN_SEND_INTERFACE
    else:
        interface = interface[0]
    try:
        bus = socketcan.Bus(interface)
    except OSError:
        raise BadRequest("bus '" + interface + "' does not exist")
    id = request.get('id')
    if id == None:
      raise BadRequest("id not specified")
    id = int(id[0])
    data = request.get('data[]') # POST
    if data == None:
        data = request.get('data') # GET
        if data == None:
            data = [] # parse_url removes data field if empty array
        else:
            data = data[0].strip('[]').split(',')
    if len(data) == 1:
      if data[0] == '':
        data = []
    data = list(map(int, data))
    msg = socketcan.Message(id, data)
    return (bus, msg)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    pass


class BadRequest(BaseException):
    def __init__(self, arg):
        self.args = arg


class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)

        try:
            # Command
            if parsed_path.query != '':
                bus, msg = parse_request(parse_qs(parsed_path.query))
                bus.send(msg)
                self.send_response(204);
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers();
                return

            # Telemetry
            if parsed_path.path == '/':
                self.send_response(200)
                self.send_header('Content-type', 'text/event-stream')
                self.send_header('Cache-control', 'no-cache')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()

                busses = []
                for interface in CAN_LISTEN_INTERFACES:
                    bus = socketcan.Bus(interface)
                    busses.append(bus)

                while True:
                    try:
                        rlist, _, _ = select(busses, [], [])
                        for bus in rlist:
                            msg = bus.recv()
                            id = msg.arbitration_id
                            data = msg.data
                            data = ",".join(map(str, data))
                            self.wfile.write(bytes('data: {"bus":"' + bus.name + '","id":' + str(id) + ',"data":[' + data + '],"ts":"' + datetime.fromtimestamp(msg.timestamp).isoformat() + '"}' + "\n\n", 'utf8'))
                    except socketcan.BusDown:
                        self.wfile.write(bytes('event: error' + "\n" + 'data: ' + bus.name + ' is down.' + "\n\n", 'utf-8'))
                        sleep(1)
                        continue
                    except SystemExit:
                        # This doesn't get called. Find a way if possible
                        self.wfile.write(bytes('event: error' + "\n" + 'data: System is shutting down.' + "\n\n", 'utf-8'))
                        raise

            # File
            filepath = WWW_DIR + self.path
            if path.isfile(filepath):
                f = open(filepath)
                self.send_response(200)
                if self.path.endswith(".html"):
                    self.send_header('Content-type', 'text/html')
                elif self.path.endswith(".js"):
                    self.send_header('Content-type', 'text/javascript')
                elif self.path.endswith(".css"):
                  self.send_header('Content-type', 'text/css')
                self.end_headers()
                self.wfile.write(bytes(f.read(), 'UTF-8'))
                f.close()
                return

            self.send_response(404)
            self.end_headers()

        except BadRequest as e:
            self.send_response(400)
            self.send_error(400, 'Bad Request: %s' % str(e.args))
        except BrokenPipeError:
            print('Connection closed.')
        except IOError:
            self.send_response(500)
            print("\n*** do_GET except ***")
            print("Unexpected error:", sys.exc_info()[0])
            traceback.print_exc()

    def do_POST(self):
        try:
            content_len = int(self.headers.get('content-length', 0)) # access POST body
            post_body = self.rfile.read(content_len) # read POST body
            post_body = post_body.decode('utf8')
            bus, frame = parse_request(parse_qs(post_body))
            bus.send(frame)
            self.send_response(204)
            self.end_headers()

        # do_POST try except clause
        except BadRequest as e:
            self.send_response(400)
            self.send_error(400, 'Bad Request: %s' % str(e.args))
        except:
            print("Unexpected error:", sys.exc_info()[0])
            traceback.print_exc()

    def log_message(self, format, *args):
        return # Suppress logging


signal.signal(signal.SIGTERM, sigterm_handler)
srvr = ThreadedHTTPServer((HTTP_SERVER_IP_ADDRESS, HTTP_SERVER_PORT), RequestHandler)
srvr.serve_forever()
