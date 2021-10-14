from pyjoycon import JoyCon, get_L_id, get_R_id

from pythonosc import udp_client

from time import monotonic as monotime

import pprint

joycon_id_l = get_L_id()
joycon_id_r = get_R_id()

try:
    joycon_l = JoyCon(*joycon_id_l)
except ValueError:
    print('Could not connect left joycon')
    joycon_l = None

# try:
#     joycon_r = JoyCon(*joycon_id_r)
# except ValueError:
#     print('Could not connect right joycon')

osc = udp_client.SimpleUDPClient("127.0.0.1", 7331)

done = None
wait_time = 0.01
if wait_time is not 0:
    print(f'Running at {1/wait_time} Hz, refresh {wait_time*1000} ms')

pp = pprint.PrettyPrinter(indent=4)

if joycon_l is not None:
    pp.pprint(joycon_l.get_status())

while True:
    if done is None or monotime() > done + wait_time:
        done = monotime()
        if joycon_l is not None:
            jc_l = joycon_l.get_status()
            gyro = jc_l['gyro']
            # print(gyro)
            osc.send_message("/gyro_x", gyro['x'])
            osc.send_message("/gyro_y", gyro['y'])
            osc.send_message("/gyro_z", gyro['z'])

            button_l_l = jc_l['buttons']['left']['l']
            osc.send_message('/button_l_l', button_l_l)
