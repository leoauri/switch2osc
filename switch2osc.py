from pyjoycon import JoyCon, get_L_id, get_R_id

from pythonosc import udp_client

import time 

import pprint

sent = {}


def send_dict(addr, input):
    if isinstance(input, dict):
        for key, value in input.items():
            send_dict(addr + '/' + key, value)
    else:
        if addr not in sent:
            osc.send_message(addr, input)
            print(f'Sent on {addr}')
            sent[addr] = input
        elif abs(sent[addr] - input) > 1e-2:
            osc.send_message(addr, input)
            sent[addr] = input


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

wait_time = 0.005
if wait_time != 0:
    print(f'Running at {1/wait_time} Hz, refresh {wait_time*1000} ms')

pp = pprint.PrettyPrinter(indent=4)

if joycon_l is not None:
    print('Left joycon connected')
    pp.pprint(joycon_l.get_status())

if joycon_r is not None:
    print('Right joycon connected')
    pp.pprint(joycon_r.get_status())

sclr = Scaler()
accum_twist = Accumulator()
sclr_twist = Scaler()
sclr_l_y = Scaler()
accum_l_y = Accumulator()

while True:
    if joycon_l is not None:
        jc_l = joycon_l.get_status()
        send_dict('/joycon_l', jc_l)
        send_dict('/twist_l', sclr_twist(accum_twist(jc_l['gyro']['x'])))
    if joycon_r is not None:
        jc_r = joycon_r.get_status()
        send_dict('/joycon_r', jc_r)
        send_dict('/stick_r_h', sclr(jc_r['analog-sticks']['right']['horizontal']))
        # send_dict('/l_y', sclr_l_y(jc_l['accel']['y']))
        send_dict('/l_y', sclr_l_y(accum_l_y(jc_l['gyro']['y'])))

    time.sleep(wait_time)
