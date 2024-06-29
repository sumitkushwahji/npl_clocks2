from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import threading
import socket
import datetime
import struct
import time
import json
from myapp.models import LogEntry
from django.http import HttpResponse  
from django.shortcuts import render  

NTD_IP = [
    "172.16.26.3",
    "172.16.26.4",
    "172.16.26.9",
    "172.17.26.10",
    "172.16.26.12",
    "172.16.26.7",
    "172.16.26.15",
    "172.17.26.16",
]

global timestamp
bias = 0


def home(request):
    return HttpResponse("Welcome to the homepage!")

def index(request, path=None):
    return render(request, 'index.html')

class NTPException(Exception):
    pass


class NTP:
    _SYSTEM_EPOCH = datetime.date(*time.gmtime(0)[0:3])
    _NTP_EPOCH = datetime.date(1900, 1, 1)
    NTP_DELTA = (_SYSTEM_EPOCH - _NTP_EPOCH).days * 24 * 3600


class NTPPacket:
    _PACKET_FORMAT = "!B B B b 11I"

    def __init__(self, version=2, mode=3, tx_timestamp=0):
        self.leap = 0
        self.version = version
        self.mode = mode
        self.stratum = 0
        self.poll = 0
        self.precision = 0
        self.root_delay = 0
        self.root_dispersion = 0
        self.ref_id = 0
        self.ref_timestamp = 0
        self.orig_timestamp = 0
        self.recv_timestamp = 0
        self.tx_timestamp = tx_timestamp

    def to_data(self):
        try:
            packed = struct.pack(
                NTPPacket._PACKET_FORMAT,
                (self.leap << 6 | self.version << 3 | self.mode),
                self.stratum,
                self.poll,
                self.precision,
                _to_int(self.root_delay) << 16 | _to_frac(self.root_delay, 16),
                _to_int(self.root_dispersion) << 16
                | _to_frac(self.root_dispersion, 16),
                self.ref_id,
                _to_int(self.ref_timestamp),
                _to_frac(self.ref_timestamp),
                _to_int(self.orig_timestamp),
                _to_frac(self.orig_timestamp),
                _to_int(self.recv_timestamp),
                _to_frac(self.recv_timestamp),
                _to_int(self.tx_timestamp),
                _to_frac(self.tx_timestamp),
            )
        except struct.error:
            raise NTPException("Invalid NTP packet fields.")
        return packed

    def from_data(self, data):
        try:
            unpacked = struct.unpack(
                NTPPacket._PACKET_FORMAT,
                data[0 : struct.calcsize(NTPPacket._PACKET_FORMAT)],
            )
        except struct.error:
            raise NTPException("Invalid NTP packet.")
        self.leap = unpacked[0] >> 6 & 0x3
        self.version = unpacked[0] >> 3 & 0x7
        self.mode = unpacked[0] & 0x7
        self.stratum = unpacked[1]
        self.poll = unpacked[2]
        self.precision = unpacked[3]
        self.root_delay = float(unpacked[4]) / 2**16
        self.root_dispersion = float(unpacked[5]) / 2**16
        self.ref_id = unpacked[6]
        self.ref_timestamp = _to_time(unpacked[7], unpacked[8])
        self.orig_timestamp = _to_time(unpacked[9], unpacked[10])
        self.recv_timestamp = _to_time(unpacked[11], unpacked[12])
        self.tx_timestamp = _to_time(unpacked[13], unpacked[14])


class NTPStats(NTPPacket):
    def __init__(self):
        NTPPacket.__init__(self)
        self.dest_timestamp = 0

    @property
    def offset(self):
        return (
            (self.recv_timestamp - self.orig_timestamp)
            + (self.tx_timestamp - self.dest_timestamp)
        ) / 2

    @property
    def delay(self):
        return (self.dest_timestamp - self.orig_timestamp) - (
            self.tx_timestamp - self.recv_timestamp
        )

    @property
    def tx_time(self):
        return ntp_to_system_time(self.tx_timestamp)

    @property
    def recv_time(self):
        return ntp_to_system_time(self.recv_timestamp)

    @property
    def orig_time(self):
        return ntp_to_system_time(self.orig_timestamp)

    @property
    def ref_time(self):
        return ntp_to_system_time(self.ref_timestamp)

    @property
    def dest_time(self):
        return ntp_to_system_time(self.dest_timestamp)


class NTPClient:
    def __init__(self):
        pass

    def request(self, host, version=2, port=123, timeout=5):
        addrinfo = socket.getaddrinfo(host, port)[0]
        family, sockaddr = addrinfo[0], addrinfo[4]
        s = socket.socket(family, socket.SOCK_DGRAM)
        s.settimeout(timeout)

        try:
            packet = NTPPacket(version=version)
            data = packet.to_data()
            dest_timestamp = time.time() + NTP.NTP_DELTA
            s.sendto(data, sockaddr)

            response_packet, src_addr = s.recvfrom(1024)
            if src_addr is None:
                raise NTPException("No valid source address received.")
            while src_addr[0] != sockaddr[0]:
                response_packet, src_addr = s.recvfrom(1024)
        except socket.timeout:
            raise NTPException(f"No response received from {host}.")
        except socket.error as se:
            if isinstance(se.args, tuple) and se.args[0] == 10022:
                raise NTPException(f"WinError 10022: An invalid argument was supplied.")
            else:
                raise NTPException(f"Socket error: {se}")
        except TypeError as te:
            raise NTPException(f"Error processing source address: {te}")
        except Exception as e:
            raise NTPException(f"Unexpected error receiving NTP response: {e}")
        finally:
            s.close()

        stats = NTPStats()
        stats.from_data(response_packet)
        stats.dest_timestamp = dest_timestamp

        return stats


def _to_int(timestamp):
    return int(timestamp)


def _to_frac(timestamp, n=32):
    return int(abs(timestamp - _to_int(timestamp)) * 2**n)


def _to_time(integ, frac, n=32):
    return integ + float(frac) / 2**n


def ntp_to_system_time(timestamp):
    return timestamp - NTP.NTP_DELTA


def system_to_ntp_time(timestamp):
    return timestamp + NTP.NTP_DELTA


def send_time(ip, data, timestamp, bias):
    host_ip, server_port = ip, 10000
    tcp_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        tcp_client.connect((host_ip, server_port))
        tcp_client.sendall(data)
        received = tcp_client.recv(1024)
        log_entry = LogEntry(
            timestamp=datetime.datetime.now(),
            ip=ip,
            status="Synchronized",
            bias=bias,
        )
        log_entry.save()
    except Exception as e:
        log_entry = LogEntry(
            timestamp=datetime.datetime.now(),
            ip=ip,
            status="Not Connected",
            bias=bias,
        )
        log_entry.save()
    finally:
        tcp_client.close()


@csrf_exempt
def start_sync(request):
    if request.method == "POST":
        data = json.loads(request.body.decode("utf-8"))
        server = data.get("server")
        sync_time = int(data.get("sync_time")) * 60
        global bias
        bias = int(data.get("bias"))
        hosts = NTD_IP
        print

        def loop(server, hosts):
            while True:
                try:
                    sync_ntd(server, hosts)
                    time.sleep(sync_time)
                except Exception as e:
                    print(f"Error in sync_ntd: {e}")
                    time.sleep(sync_time)

        threading.Thread(target=loop, args=(server, hosts)).start()

        return JsonResponse({"status": "Synchronization started"})

    return JsonResponse({"error": "Invalid request method"}, status=400)


@csrf_exempt
def sync_ntd(server, hosts):
    global timestamp, bias
    print("server: ", server)
    print("hosts: ", hosts)
    if hosts is None:
        print("No hosts provided.")
        return
    print(f"Syncing NTDs with {server}...")
    client = NTPClient()
    try:
        response = client.request(server, version=3)
        print(f"Response: {response}")
    except NTPException as e:
        print(f"NTPException: {e}")
        return  # Exit function on exception

    timestamp = round(response.tx_time + bias)

    ntp_date = datetime.datetime.fromtimestamp(timestamp)

    header = b"\x55\xaa\x00\x00\x01\x01\x00\xc1\x00\x00\x00\x00\x00\x00\x0f\x00\x00\x00\x0f\x00\x10\x00\x00\x00\x00\x00\x00\x00"
    footer = b"\x00\x00\x0d\x0a"
    year1 = bytes([ntp_date.year // 256])
    year2 = bytes([ntp_date.year % 256])
    data = (
        header
        + year2
        + year1
        + bytes([ntp_date.month])
        + bytes([ntp_date.day])
        + bytes([ntp_date.hour])
        + bytes([ntp_date.minute])
        + bytes([ntp_date.second])
        + footer
    )

    for ip in hosts:
        try:
            threading.Thread(target=send_time, args=(ip, data, timestamp, bias)).start()
        except Exception as e:
            print(f"Error processing host {ip}: {e}")


def get_logs(request):
    logs = LogEntry.objects.all()
    log_list = [
        {
            "timestamp": log.timestamp,
            "ip": log.ip,
            "status": log.status,
            "bias": log.bias,
        }
        for log in logs
    ]
    return JsonResponse({"log_entries": log_list})
