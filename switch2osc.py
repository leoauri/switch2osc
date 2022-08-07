from pyjoycon import JoyCon, get_L_id, get_R_id

from pythonosc import udp_client

from ischedule import run_loop, schedule

import time 
import pprint
import argparse
from collections import Counter


parser = argparse.ArgumentParser(
        description='Bridge Nintendo switch controllers to OSC signals.')
parser.add_argument('--scalers', action='store_true', 
        help='Add scaled and accumulated sends')
parser.add_argument('--stats_every', type=float, 
        help='Show stats every STATS_EVERY seconds')

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
                m = max([b-a for a,b in 
                        zip(self.sent[addr], self.sent[addr][1:])])
            except ValueError:
                m = None

            print(f'{addr} at {count/(now-self.stamp)} Hz, range {r}',
                    end='')
            print('' if m is None else f', max epsilon {m}')
        self.counter.clear()
        self.sent = {}
        self.stamp = time.perf_counter()


if args.stats_every is not None:
    stats = Stats()

sent = {}
if args.scalers:
    scalers = {}
    accums = {}
    accum_scalers = {}


def send_to(addr, input, eps=1e-3):
    if addr not in sent or abs(sent[addr] - input) > eps:
        osc.send_message(addr, input)
        if addr not in sent:
            print(f'Sent on {addr}')
        if args.stats_every is not None:
            stats.record(addr, input)
        sent[addr] = input


def send_dict(addr, input):
    if isinstance(input, dict):
        for key, value in input.items():
            send_dict(addr + '/' + key, value)
    else:
        if args.scalers and addr not in scalers:
            scalers[addr] = Scaler()
            accums[addr] = Accumulator()
            accum_scalers[addr] = Scaler()

        send_to(addr, input)
        if args.scalers:
            send_to(addr + '/scaled', scalers[addr](input))
            send_to(addr + '/accum', accum_scalers[addr](accums[addr](input)))



joycon_id_l = get_L_id()
joycon_id_r = get_R_id()

try:
    joycon_l = JoyCon(*joycon_id_l)
except ValueError:
    print('Could not connect left joycon')
    joycon_l = None

try:
    joycon_r = JoyCon(*joycon_id_r)
except ValueError:
    print('Could not connect right joycon')
    joycon_r = None

osc = udp_client.SimpleUDPClient("127.0.0.1", 7331)

wait_time = 0.02
if wait_time != 0:
    print(f'Running at {1/wait_time} Hz, refresh {wait_time*1000} ms')

pp = pprint.PrettyPrinter(indent=4)

if joycon_l is not None:
    print('Left joycon connected')
    pp.pprint(joycon_l.get_status())

if joycon_r is not None:
    print('Right joycon connected')
    pp.pprint(joycon_r.get_status())

@schedule(interval=wait_time)
def update_joycons():
    if joycon_l is not None:
        jc_l = joycon_l.get_status()
        send_dict('/joycon_l', jc_l)
    if joycon_r is not None:
        jc_r = joycon_r.get_status()
        send_dict('/joycon_r', jc_r)

if args.stats_every is not None:
    schedule(stats.print_stats, interval=args.stats_every)

run_loop()
