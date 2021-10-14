from pyjoycon import JoyCon, get_L_id, get_R_id

from pythonosc import udp_client

import time 

import pprint

sent_on = []


def send_dict(addr, input):
    if isinstance(input, dict):
        for key, value in input.items():
            send_dict(addr + '/' + key, value)
    else:
        osc.send_message(addr, input)
        if addr not in sent_on:
            print(f'Sent on {addr}')
            sent_on.append(addr)



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

wait_time = 0.01
if wait_time != 0:
    print(f'Running at {1/wait_time} Hz, refresh {wait_time*1000} ms')

pp = pprint.PrettyPrinter(indent=4)

if joycon_l is not None:
    print('Left joycon connected')
    pp.pprint(joycon_l.get_status())

if joycon_r is not None:
    print('Right joycon connected')
    pp.pprint(joycon_r.get_status())

while True:
    if joycon_l is not None:
        jc_l = joycon_l.get_status()
        send_dict('/joycon_l', jc_l)
    if joycon_r is not None:
        jc_r = joycon_r.get_status()
        send_dict('/joycon_r', jc_r)

    time.sleep(wait_time)
