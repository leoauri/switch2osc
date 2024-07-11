# switch2osc
A script to bridge Nintendo Switch controllers to [OSC signals](https://en.wikipedia.org/wiki/Open_Sound_Control).

Install into your environment:
```
pip install -r requirements.txt
```

To run the bridge and output OSC on port 7332:
```
python switch2osc.py --port 7332
```

To log movement data to directory `movelogs`:
```
python switch2osc.py --logdir movelogs
```

Show more options:
```
python switch2osc.py --help
```
```
usage: switch2osc.py [-h] [--port PORT] [--scalers] [--stats_every SECONDS]
                     [--show_addresses] [--show_epsilons] [--show_zeroing]
                     [--dump_example]
                     [--show_calib_data ADDRESS_PART [ADDRESS_PART ...]]
                     [--logdir LOGDIR]

Bridge Nintendo switch controllers to OSC signals.

options:
  -h, --help            show this help message and exit
  --port PORT           Port to use for OSC server (Default 7331).
  --scalers             Add scaled and accumulated sends
  --stats_every SECONDS
                        Show stats every SECONDS seconds
  --show_addresses      Log addresses which have been sent to
  --show_epsilons       Show calculated epsilons when calibrating
  --show_zeroing        Show stats when zeroing controllers
  --dump_example        Dump single example of captured controller data
  --show_calib_data ADDRESS_PART [ADDRESS_PART ...]
                        Dump collected calibration data for addresses
  --logdir LOGDIR       Directory to log movement data to
```
