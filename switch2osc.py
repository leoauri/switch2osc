from pyjoycon import JoyCon, get_L_id, get_R_id

from pythonosc import udp_client

from ischedule import run_loop, schedule

import time
import pprint
import argparse
from collections import Counter
from math import floor
import logging
from pathlib import Path


parser = argparse.ArgumentParser(
    description="Bridge Nintendo switch controllers to OSC signals."
)
parser.add_argument(
    "--poll_interval", metavar="MS", type=float, help="Poll JoyCons every MS milliseconds."
)
parser.add_argument(
    "--port", type=int, help="Port to use for OSC server (Default 7331)."
)
parser.add_argument(
    "--scalers", action="store_true", help="Add scaled and accumulated sends"
)
parser.add_argument(
    "--stats_every",
    type=float,
    metavar="SECONDS",
    help="Show stats every SECONDS seconds",
)
parser.add_argument(
    "--show_addresses",
    action="store_true",
    help="Log addresses which have been sent to",
)
parser.add_argument(
    "--show_epsilons",
    action="store_true",
    help="Show calculated epsilons when calibrating",
)
parser.add_argument(
    "--show_zeroing", action="store_true", help="Show stats when zeroing controllers"
)
parser.add_argument(
    "--dump_example",
    action="store_true",
    help="Dump single example of captured controller data",
)
parser.add_argument(
    "--show_calib_data",
    nargs="+",
    type=str,
    metavar="ADDRESS_PART",
    help="Dump collected calibration data for addresses",
)
parser.add_argument("--logdir", type=str, help="Directory to log movement data to")

args = parser.parse_args()


class Scaler:
    def __init__(self, min=0, max=1):
        self.min_out = min
        self.max_out = max
        self.min_in = None
        self.max_in = None

    def scale(self, x):
        return x * (self.max_out - self.min_out) + self.min_out

    def __call__(self, x):
        if self.min_in is None or x < self.min_in:
            self.min_in = x
        if self.max_in is None or x > self.max_in:
            self.max_in = x

        if self.min_in == self.max_in:
            return self.scale(0.5)
        else:
            return self.scale((x - self.min_in) / (self.max_in - self.min_in))


class Accumulator:
    def __init__(self):
        self.total = 0

    def __call__(self, x):
        self.total += x
        return self.total


class Stats:
    def __init__(self):
        self.counter = Counter()
        self.stamp = time.perf_counter()
        self.sent = {}

    def record(self, addr, val):
        if addr not in self.sent:
            self.sent[addr] = []
        self.sent[addr].append(val)
        self.count(addr)

    def count(self, addr):
        self.counter.update([addr])

    def print_stats(self):
        print()
        now = time.perf_counter()
        for addr, count in sorted(self.counter.items()):
            r = max(self.sent[addr]) - min(self.sent[addr])
            try:
                m = max([b - a for a, b in zip(self.sent[addr], self.sent[addr][1:])])
            except ValueError:
                m = None

            print(f"{addr} at {count/(now-self.stamp)} Hz, range {r}", end="")
            print("" if m is None else f", max epsilon {m}")
        self.counter.clear()
        self.sent = {}
        self.stamp = time.perf_counter()


class Sender:
    def __init__(
        self,
        calibration_trigger=None,
        zero_triggers={},
        discard_samples=10,
        logger=None,
    ):
        self.eps = {}
        self.last_sent = {}
        self.calibrate_until = None
        self.calibrating = False
        self.calibration_trigger = calibration_trigger
        # for some reason, individual controllers produce bogus initial
        # values.  Throw away some of the initial calibration examples
        self.discard_samples = discard_samples
        self.logger = logger

        self.zero_triggers = zero_triggers
        self.zero_until = {}
        self.zero_data = {}
        self.modes = {}

    def start_calibrate(self, calibration_time=2):
        print(f"Calibrate for {calibration_time} seconds")
        self.calibrating = True
        self.calibrate_until = time.perf_counter() + calibration_time
        self.sent = {}
        self.eps = {}

    def finish_calibrate(self):
        self.calibrating = False
        if args.show_calib_data is not None:
            print("Collected calibration data:")
            for a in args.show_calib_data:
                pp.pprint({k: v for k, v in self.sent.items() if k.startswith(a)})
        # calculate epsilons
        for addr, vals in self.sent.items():
            vals = vals[self.discard_samples :]
            try:
                e = max([abs(b - a) for a, b in zip(vals, vals[1:])])
            except ValueError:
                e = None
            if e is not None:
                self.eps[addr] = e
        print("Finished calibration")
        if args.show_epsilons:
            print("Calculated epsilons:")
            pp.pprint(self.eps)

    @staticmethod
    def mode(vals, min_vals=10):
        if len(vals) == 0:
            return None
        mini = min(vals)
        maxi = max(vals)
        if mini == maxi:
            return mini
        if len(vals) < min_vals:
            return sum(vals) / len(vals)
        buckets = {}
        for val in vals:
            bucket = floor(10 * (val - mini) / (maxi - mini))
            if bucket not in buckets:
                buckets[bucket] = []
            buckets[bucket].append(val)
        biggest = max(buckets.values(), key=len)
        return Sender.mode(biggest)

    def maybe_zero(self, addr, val):
        if (addr, val) in self.zero_triggers:
            address_part = self.zero_triggers[(addr, val)]
            if address_part not in self.zero_until:
                print(f"Zeroing {address_part}")
            self.zero_until[address_part] = time.perf_counter() + 2
        for a, until in self.zero_until.copy().items():
            if time.perf_counter() > until:
                del self.zero_until[a]
                # get list of addresses which were covered by zeroing
                zaddrs = [addr for addr in self.zero_data.keys() if a in addr]
                for za in zaddrs:
                    # calculate mode of sampled data
                    self.modes[za] = Sender.mode(self.zero_data[za])
                    if args.show_zeroing:
                        print(f"Zeroed {za} to {self.modes[za]}")
                    # empty collected zero data
                    del self.zero_data[za]
                print(f"Finished zeroing {a}")
                if self.logger:
                    self.logger.warning(f"Finished zeroing {a}")
            else:
                if a in addr:
                    if addr not in self.zero_data:
                        self.zero_data[addr] = []
                    self.zero_data[addr].append(val)

    def send_to(self, addr, val):
        self.maybe_zero(addr, val)
        if not self.calibrating and (
            len(self.eps) == 0 or (addr, val) == self.calibration_trigger
        ):
            self.start_calibrate()
        if self.calibrating and time.perf_counter() > self.calibrate_until:
            self.finish_calibrate()
        if self.calibrating:
            if addr not in self.sent:
                self.sent[addr] = []
            self.sent[addr].append(val)
        else:
            if addr in self.modes and self.modes[addr] is not None:
                val -= self.modes[addr]
            if (
                addr not in self.last_sent
                or addr not in self.eps
                or abs(self.last_sent[addr] - val) > self.eps[addr]
            ):
                osc.send_message(addr, val)
                if self.logger:
                    # log message to logger
                    self.logger.info(f"{addr}\t{val}")
                if args.show_addresses and addr not in self.last_sent:
                    print(f"Sent on {addr}")
                self.last_sent[addr] = val
                if args.stats_every is not None:
                    stats.record(addr, val)

    def send_dict(self, addr, val):
        if isinstance(val, dict):
            for key, value in val.items():
                self.send_dict(addr + "/" + key, value)
        else:
            if args.scalers and addr not in scalers:
                scalers[addr] = Scaler()
                accums[addr] = Accumulator()
                accum_scalers[addr] = Scaler()

            self.send_to(addr, val)
            if args.scalers:
                self.send_to(addr + "/scaled", scalers[addr](val))
                self.send_to(addr + "/accum", accum_scalers[addr](accums[addr](val)))


if args.stats_every is not None:
    stats = Stats()

if args.scalers:
    scalers = {}
    accums = {}
    accum_scalers = {}

# start OSC client
osc = udp_client.SimpleUDPClient(
    "127.0.0.1", 7331 if args.port is None else args.port, allow_broadcast=True
)

wait_time = 0.02 if args.poll_interval is None else args.poll_interval / 1000
if wait_time != 0:
    print(f"Running at {1/wait_time:.3f} Hz, refresh {wait_time*1000} ms")

pp = pprint.PrettyPrinter(indent=4)

logger = None
if args.logdir:
    logdir = Path(args.logdir)
    logdir.mkdir(parents=True, exist_ok=True)
    logfn = logdir / (time.strftime("%Y%m%d%H%M%S") + ".tsv")
    logger = logging.getLogger("movement_logger")
    logging.basicConfig(
        filename=logfn, level=logging.INFO, style="{", format="{asctime}\t{message}"
    )

joycon_l = None
joycon_r = None

sender_l = Sender(
    zero_triggers={
        ("/joycon_l/buttons/shared/capture", 1): "/joycon_l",
    },
    logger=logger,
)

sender_r = Sender(
    zero_triggers={
        ("/joycon_r/buttons/shared/home", 1): "/joycon_r",
    },
    logger=logger,
)

def printlog(msg: str):
    print(msg)
    if logger:
        logger.warning(msg)

@schedule(interval=wait_time)
def update_joycons():
    global joycon_l, joycon_r

    if joycon_l is None:
        try:
            joycon_l = JoyCon(*get_L_id())
        except (ValueError, OSError, AssertionError):
            joycon_l = None
        if joycon_l is not None:
            printlog("Left joycon connected")
            if args.dump_example:
                pp.pprint(joycon_l.get_status())

    if joycon_r is None:
        try:
            joycon_r = JoyCon(*get_R_id())
        except (ValueError, OSError, AssertionError):
            joycon_r = None
        if joycon_r is not None:
            printlog("Right joycon connected")
            if args.dump_example:
                pp.pprint(joycon_r.get_status())

    if joycon_l is not None:
        if joycon_l.connected.is_set():
            jc_l = joycon_l.get_status()
            sender_l.send_dict("/joycon_l", jc_l)
        else:
            joycon_l = None
            printlog("Lost left joycon, waiting to reconnect...")

    if joycon_r is not None:
        if joycon_r.connected.is_set():
            jc_r = joycon_r.get_status()
            sender_r.send_dict("/joycon_r", jc_r)
        else:
            joycon_r = None
            printlog("Lost right joycon, waiting to reconnect...")


if args.stats_every is not None:
    schedule(stats.print_stats, interval=args.stats_every)

try:
    print("Waiting for joycons...")
    run_loop()
except KeyboardInterrupt:
    print()
    print("Bridge ended.")
