import argparse
import struct
import sys
import time
import zlib

VENDOR_ID = 0x3434
DEFAULT_PID = 0x0C10
USAGE_PAGE = 0x008C
REPORT_ID_IN = 0xB1
REPORT_ID_OUT = 0xB2
DEFAULT_REPORT_LEN = 32

FRAME_START = 0xAA
FRAME_PLAIN = 0x55
FRAME_ACK = 0x56

OP_MODEL_INFO = 0x60
OP_DFU_VERSION = 0x61
OP_SECURITY = 0x62
OP_START = 0x63
OP_SEND_BIN = 0x64
OP_VERIFY = 0x65
OP_SWITCH = 0x66
OP_PATCH_VERSION = 0x6E
OP_BUILD_INFO = 0x6F

IMAGE_NAME_OFFSET = 0x208
IMAGE_NAME_LEN = 8
OTA_TMP_SIZE = 0x59000
MAX_PACKETS = OTA_TMP_SIZE >> 4
MAX_CHUNK = 48
MIN_CHUNK = 16
FRAME_OVERHEAD = 8


class DfuError(Exception):
    pass


def checksum16(data):
    return sum(data) & 0xFFFF


def build_frame(op, payload, sn, ack_header=False):
    body = bytes([op]) + bytes(payload)
    length = len(body) + 2
    head = bytes([FRAME_START, FRAME_ACK if ack_header else FRAME_PLAIN, length, (~length) & 0xFF, sn])
    return head + body + struct.pack("<H", checksum16(body))


def parse_frame(frame):
    if len(frame) < 9:
        raise ValueError("short frame")
    if frame[0] != FRAME_START or frame[1] not in (FRAME_PLAIN, FRAME_ACK):
        raise ValueError("bad frame start")
    length = frame[2]
    if frame[3] != (~length) & 0xFF or length < 6:
        raise ValueError("bad frame length")
    total = 5 + length
    if len(frame) < total:
        raise ValueError("truncated frame")
    body = frame[5 : total - 2]
    (got,) = struct.unpack("<H", frame[total - 2 : total])
    if got != checksum16(body):
        raise ValueError("bad frame checksum")
    return {
        "sn": frame[4],
        "kind": body[0],
        "ack_sn": body[1],
        "ack_cmd": body[2],
        "status": body[3],
        "payload": bytes(body[4:]),
    }


def raw_crc(zlib_value):
    return (zlib_value ^ 0xFFFFFFFF) & 0xFFFFFFFF


def text(raw):
    return bytes(raw).split(b"\x00", 1)[0].decode("ascii", "replace")


def parse_model(payload):
    if len(payload) < 34:
        raise DfuError("model info payload too short: %d" % len(payload))
    info = {
        "model": text(payload[0:10]),
        "le_mode": payload[10],
        "bt_version": payload[11],
        "fw_version": text(payload[12:22]),
        "hw_version": text(payload[22:32]),
        "command_version": payload[32] | (payload[33] << 8),
        "chip_id": payload[37] if len(payload) >= 38 else None,
    }
    return info


def parse_patch_versions(payload):
    entries = []
    for i in range(0, len(payload) - 5, 6):
        image_id = payload[i] | (payload[i + 1] << 8)
        version = struct.unpack("<I", payload[i + 2 : i + 6])[0]
        entries.append((image_id, version))
    return entries


class HidTransport:
    def __init__(self, path, report_len):
        try:
            import hid
        except ImportError:
            raise DfuError("python module 'hid' is missing, install it with: pip install hidapi")
        self.device = hid.device()
        self.device.open_path(path)
        self.report_len = report_len

    def write(self, report):
        written = self.device.write(report)
        if written is None or written < 0:
            raise DfuError("hid write failed: %s" % self.device.error())

    def read(self, timeout_ms):
        return bytes(self.device.read(self.report_len + 33, max(1, int(timeout_ms))))

    def close(self):
        self.device.close()


def filter_devices(entries, pid=None):
    found = []
    for entry in entries:
        if entry.get("usage_page") != USAGE_PAGE:
            continue
        if pid is not None and entry.get("product_id") != pid:
            continue
        found.append(entry)
    return found


def find_devices(pid=None):
    try:
        import hid
    except ImportError:
        raise DfuError("python module 'hid' is missing, install it with: pip install hidapi")
    return filter_devices(hid.enumerate(VENDOR_ID, 0), pid)


class Session:
    def __init__(self, transport, report_len=DEFAULT_REPORT_LEN, timeout=3.0, retries=5, log=None):
        self.transport = transport
        self.report_len = report_len
        self.timeout = timeout
        self.retries = retries
        self.log = log or (lambda message: None)
        self.sn = 1

    def next_sn(self):
        value = self.sn
        self.sn = self.sn % 255 + 1
        return value

    def make_report(self, frame):
        if len(frame) > self.report_len:
            raise DfuError("frame of %d bytes does not fit a %d byte report" % (len(frame), self.report_len))
        return bytes([REPORT_ID_OUT]) + frame.ljust(self.report_len, b"\x00")

    def flush(self):
        while self.transport.read(0):
            pass

    def read_response(self, wait):
        deadline = time.monotonic() + wait
        buf = b""
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            report = self.transport.read(max(1, int(remaining * 1000)))
            if not report:
                continue
            if report[0] != REPORT_ID_IN:
                continue
            chunk = report[1:]
            if not buf:
                if not chunk or chunk[0] != FRAME_START:
                    continue
                buf = chunk
            else:
                buf += chunk
            if len(buf) >= 3:
                total = 5 + buf[2]
                if len(buf) >= total:
                    try:
                        return parse_frame(buf[:total])
                    except ValueError as exc:
                        self.log("dropped malformed response: %s" % exc)
                        buf = b""

    def transact(self, op, payload=b"", ack_header=False, timeout=None, retries=None, sn=None):
        timeout = self.timeout if timeout is None else timeout
        retries = self.retries if retries is None else retries
        sn = self.next_sn() if sn is None else sn
        report = self.make_report(build_frame(op, payload, sn, ack_header))
        for attempt in range(retries + 1):
            self.flush()
            self.transport.write(report)
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                response = self.read_response(remaining)
                if response is None:
                    break
                if response["ack_cmd"] == op and response["ack_sn"] == sn:
                    return response
            self.log("no response to opcode 0x%02x sn %d, attempt %d" % (op, sn, attempt + 1))
        raise DfuError("no response to opcode 0x%02x after %d attempts" % (op, retries + 1))

    def model_info(self):
        response = self.transact(OP_MODEL_INFO)
        if response["status"] != 0:
            raise DfuError("model info rejected, status %d" % response["status"])
        return parse_model(response["payload"])

    def dfu_version(self):
        response = self.transact(OP_DFU_VERSION)
        payload = response["payload"]
        if len(payload) < 3:
            raise DfuError("dfu version payload too short")
        return payload[0] | (payload[1] << 8), payload[2]

    def patch_versions(self):
        response = self.transact(OP_PATCH_VERSION)
        return parse_patch_versions(response["payload"])

    def build_info(self):
        response = self.transact(OP_BUILD_INFO)
        return text(response["payload"])


def check_image(data, model):
    if not data:
        raise DfuError("image is empty")
    if len(data) > OTA_TMP_SIZE:
        raise DfuError("image is %d bytes, the device staging area holds %d" % (len(data), OTA_TMP_SIZE))
    if len(data) < IMAGE_NAME_OFFSET + IMAGE_NAME_LEN:
        raise DfuError("image is too small to contain a header")
    name = bytes(data[IMAGE_NAME_OFFSET : IMAGE_NAME_OFFSET + IMAGE_NAME_LEN])
    expected = model.encode("ascii")[:IMAGE_NAME_LEN]
    if name != expected:
        raise DfuError(
            "image model name %r does not match device model %r" % (name.decode("ascii", "replace"), model)
        )


def choose_chunk(requested, report_len, size):
    limit = min(MAX_CHUNK, report_len - FRAME_OVERHEAD)
    chunk = limit if requested is None else requested
    if chunk > limit:
        raise DfuError("chunk %d exceeds the maximum %d for a %d byte report" % (chunk, limit, report_len))
    if chunk < MIN_CHUNK:
        raise DfuError("chunk %d is below the minimum %d" % (chunk, MIN_CHUNK))
    if -(-size // chunk) >= MAX_PACKETS:
        raise DfuError("image needs too many packets with chunk %d" % chunk)
    return chunk


def upload(session, data, chunk, progress=None):
    z = 0
    total = len(data)
    sent = 0
    for offset in range(0, total, chunk):
        piece = data[offset : offset + chunk]
        sn = session.next_sn()
        response = session.transact(OP_SEND_BIN, piece, sn=sn, timeout=session.timeout * 2)
        if response["status"] != 0:
            raise DfuError("device refused data at offset %d, status %d" % (offset, response["status"]))
        z = zlib.crc32(piece, z)
        payload = response["payload"]
        if len(payload) < 5:
            raise DfuError("short data acknowledgement at offset %d" % offset)
        device_crc = struct.unpack("<I", payload[1:5])[0]
        if device_crc != raw_crc(z):
            raise DfuError(
                "crc mismatch at offset %d: device 0x%08x host 0x%08x" % (offset, device_crc, raw_crc(z))
            )
        sent += len(piece)
        if progress:
            progress(sent, total)
    return raw_crc(z)


def run_flash(session, data, activate, chunk_request, progress, say):
    info = session.model_info()
    check_image(data, info["model"])
    chunk = choose_chunk(chunk_request, session.report_len, len(data))
    say("device model %s firmware %s, image %d bytes, %d byte packets" % (info["model"], info["fw_version"], len(data), chunk))
    response = session.transact(OP_SECURITY, b"\x00")
    if response["status"] != 0:
        raise DfuError("device refused plain transfer mode, status %d" % response["status"])
    response = session.transact(OP_START, b"", ack_header=True, timeout=session.timeout * 3)
    if response["status"] != 0:
        raise DfuError("device refused to start the update, status %d" % response["status"])
    say("update session started")
    crc = upload(session, data, chunk, progress)
    say("upload finished, image crc 0x%08x" % crc)
    response = session.transact(OP_VERIFY, struct.pack("<II", crc, crc), timeout=30.0, retries=1)
    payload = response["payload"]
    code = payload[0] if payload else 0xFF
    if response["status"] != 0 or code != 0:
        raise DfuError("device verification failed, code %d (1 = crc, 2 = image check), nothing was activated" % code)
    say("device verified the image")
    if not activate:
        say("activation skipped, power cycle the keyboard to leave update mode")
        return
    session.flush()
    session.transport.write(session.make_report(build_frame(OP_SWITCH, b"", session.next_sn())))
    say("activation requested, the keyboard reboots and installs the image, do not unplug it")


def print_info(session, say):
    info = session.model_info()
    say("model          %s" % info["model"])
    say("firmware       %s" % info["fw_version"])
    say("hardware       %s" % info["hw_version"])
    say("command ver    %d" % info["command_version"])
    say("chip id        %s" % info["chip_id"])
    version, encryption = session.dfu_version()
    say("dfu version    %d, encryption mode %d" % (version, encryption))
    try:
        say("build          %s" % session.build_info())
    except DfuError as exc:
        say("build          unavailable (%s)" % exc)
    try:
        for image_id, value in session.patch_versions():
            say("image 0x%04x    version 0x%08x" % (image_id, value))
    except DfuError as exc:
        say("patch versions unavailable (%s)" % exc)


def open_session(args):
    path = args.path
    if path is None:
        devices = find_devices(args.pid)
        if not devices:
            raise DfuError(
                "no device with vendor 0x%04x, product 0x%04x and usage page 0x%04x found, see the list command"
                % (VENDOR_ID, args.pid, USAGE_PAGE)
            )
        if len(devices) > 1:
            raise DfuError("several matching interfaces found, pick one with --path (see the list command)")
        path = devices[0]["path"]
    transport = HidTransport(path, args.report_len)
    log = print if args.verbose else None
    return Session(transport, args.report_len, args.timeout, args.retries, log)


def progress_printer():
    state = {"last": -1}

    def show(sent, total):
        percent = sent * 100 // total
        if percent != state["last"]:
            state["last"] = percent
            sys.stdout.write("\r%3d%% %d/%d bytes" % (percent, sent, total))
            sys.stdout.flush()
            if sent == total:
                sys.stdout.write("\n")

    return show


def main(argv=None):
    parser = argparse.ArgumentParser(description="Keychron ZMK USB firmware updater")
    parser.add_argument("--path", help="hid device path, see the list command")
    parser.add_argument("--pid", type=lambda value: int(value, 0), default=DEFAULT_PID, help="usb product id, default 0x0c10")
    parser.add_argument("--report-len", type=int, default=DEFAULT_REPORT_LEN)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("info")
    flash = sub.add_parser("flash")
    flash.add_argument("image")
    flash.add_argument("--yes", action="store_true")
    flash.add_argument("--no-switch", action="store_true")
    flash.add_argument("--chunk", type=int)
    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            for entry in find_devices():
                print(
                    "%s  vid=0x%04x pid=0x%04x usage_page=0x%04x product=%s"
                    % (
                        entry["path"].decode("ascii", "replace") if isinstance(entry["path"], bytes) else entry["path"],
                        entry["vendor_id"],
                        entry["product_id"],
                        entry["usage_page"],
                        entry.get("product_string"),
                    )
                )
            return 0
        session = open_session(args)
        try:
            if args.command == "info":
                print_info(session, print)
                return 0
            with open(args.image, "rb") as handle:
                data = handle.read()
            info = session.model_info()
            check_image(data, info["model"])
            print("device   %s firmware %s" % (info["model"], info["fw_version"]))
            print("image    %s, %d bytes, crc32 0x%08x" % (args.image, len(data), zlib.crc32(data)))
            if not args.yes:
                print("checks passed, nothing was sent, run again with --yes to flash")
                return 2
            run_flash(session, data, not args.no_switch, args.chunk, progress_printer(), print)
            return 0
        finally:
            session.transport.close()
    except DfuError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
