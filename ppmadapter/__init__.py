# PPMAdapter - An RC PPM decoder and joystick emulator
# Copyright 2016 Nigel Sim <nigel.sim@gmail.com>
#
# Also based on some code from PPM to TX
# Copyright (C) 2010 Tomas 'ZeXx86' Jedrzejek (zexx86@zexos.org)
# Copyright (C) 2011 Tomas 'ZeXx86' Jedrzejek (zexx86@zexos.org)
# Copyright (C) 2017 Jürgen Diez (jdiez@web.de)
# Copyright (C) 2018 Tomas 'ZeXx86' Jedrzejek (tomasj@spirit-system.com)
#
#
# PPMAdapter is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PPMAdapter is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PPMAdapter.  If not, see <http://www.gnu.org/licenses/>.

import array
import sys
import pyaudio
import argparse
import collections

from evdev import UInput, ecodes
from ctypes import CFUNCTYPE, c_char_p, c_int, cdll
from contextlib import contextmanager

try:
    import numpy as np
    import matplotlib.pyplot as plt
except ImportError:
    print("Warning: without numpy and matplotlib, --plot option will not work")


# Suppress ALSA errors
# http://stackoverflow.com/questions/7088672
ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)


def py_error_handler(filename, line, function, err, fmt):
    pass


c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)


@contextmanager
def noalsaerr():
    asound = cdll.LoadLibrary('libasound.so')
    asound.snd_lib_error_set_handler(c_error_handler)
    yield
    asound.snd_lib_error_set_handler(None)


class PPMDecoder(object):
    """Decodes the audio data into PPM pulse data, and then into uinput
    joystick events.
    """
    def __init__(self, rate, average_length):
        """
        Parameters
        ----------
        rate : int
            sample rate
        average_length : int
            average of past channel values for smoothing, set to 1 if undesired
        """
        self.rate = float(rate)

        # Values that persist between windows so we can handle small windows
        # where not all the channels have been seen in a single window
        self.min_value = float("+inf")
        self.max_value = float("-inf")
        self.channel = 0
        self.previous_value = None
        self.pulse_start_time = 0
        self.samples_since_pulse = 0

        # Should be 2ms, but sometimes not quite
        self.start_pulse_length = 2.0 / 1000

        # Mapping of channels to events
        self.mapping = {
            0: ecodes.ABS_X,
            1: ecodes.ABS_Y,
            2: ecodes.ABS_Z,
            3: ecodes.ABS_THROTTLE,
            4: ecodes.ABS_RUDDER,
            5: ecodes.ABS_MISC,
        }

        # History of values (for averaging)
        self.history = {i: collections.deque(maxlen=average_length)
                for i in self.mapping.keys()}

        # Min/max values we'll output
        events = [(v, (0, -512, 512, 0)) for v in self.mapping.values()]

        self.ev = UInput(name='ppmadapter', events={
            ecodes.EV_ABS: events,
            ecodes.EV_KEY: {288: 'BTN_JOYSTICK'}
        })

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        self.ev.close()

    def feed(self, data, plot=False, debug=False):
        """Feeds the decoder with a block of sample data.

        The data should be integer values, and should only be a single channel.

        Parameters
        ----------
        data : list
            Sample data
        plot : bool
            Whether to display data in a matplotlib plot or not
        """
        if plot:
            plot_start = np.zeros((len(data),))
            plot_channels = {i: np.zeros((len(data),)) for i in self.mapping.keys()}

        # Process all audio samples
        for i in range(len(data)):
            # Hmm... maybe the problem was just that it needed to be negated?
            # This is what txppm does.
            current_value = -data[i]

            # Update extrema and threshold as a weighted average. In my case,
            # average ends up being close to 0, which then results in noise
            # triggering this. Thus, weight toward max.
            self.min_value = min(self.min_value, current_value)
            self.max_value = max(self.max_value, current_value)
            threshold = 1/4*self.min_value + 3/4*self.max_value

            # Keep track of the previous value for determining if between the
            # last sample and the current sample there was a rise
            if self.previous_value is None:
                self.previous_value = current_value
                continue

            # Detect rising edge: if the previous value is low and now it's
            # high
            rising = self.previous_value < threshold and current_value > threshold

            if rising:
                # Time when hitting threshold (measured in seconds)
                # See: https://github.com/nexx512/txppm/blob/master/software/ppm.c
                trigger_offset = (threshold - self.previous_value) / \
                    (current_value - self.previous_value) / self.rate
                trigger_time = self.samples_since_pulse / self.rate + trigger_offset
                pulse_length = trigger_time - self.pulse_start_time
                self.pulse_start_time = trigger_time

                # Start pulse
                if pulse_length > self.start_pulse_length:
                    self.channel = 0
                    self.pulse_start_time = trigger_offset
                    self.samples_since_pulse = 0

                    if plot:
                        plot_start[i] = threshold

                # Channel measurement
                else:
                    # If a channel we care about, save it. Note: still need to
                    # increment the channel even if not in mapping since we
                    # might care about non-consecutive channels (e.g. 1, 3, and
                    # 5).
                    if self.channel in self.mapping:
                        # txppm says "According to the spec, the pulse length
                        # ranges from 1..2ms"
                        value = pulse_length*1000 - 1.5

                        # To enable averaging, add current value to queue but
                        # don't set it yet
                        self.history[self.channel].append(value)

                        if plot:
                            plot_channels[self.channel][i] = threshold

                    self.channel += 1

            self.samples_since_pulse += 1
            self.previous_value = current_value

        # Send joystick updates
        for ch, values in self.history.items():
            value = 0

            # Handle averaging
            if len(values) > 0:
                value = int(sum(values)/len(values) * 512)

            self.ev.write(ecodes.EV_ABS, self.mapping[ch], value)

            if debug:
                print("ch"+str(ch), "=", value)

        self.ev.syn()

        # Plot the audio data we received if desired
        if plot:
            # Plot negative since we negate when processing
            y = -np.array(list(data), dtype=np.float32)
            x = np.arange(0, len(y), 1)
            plt.plot(x, y, label="signal")
            plt.plot(x, plot_start, label="start")
            for ch, values in plot_channels.items():
                plt.plot(x, values, label="ch"+str(ch))
            plt.legend()
            plt.show()


def print_inputs():
    with noalsaerr():
        print("Input audio devices")
        print("-------------------")
        a = pyaudio.PyAudio()
        for i in range(a.get_device_count()):
            d = a.get_device_info_by_index(i)
            print("%s: \t Max Channels: in[%s] out[%s]" % (d['name'],
                d['maxInputChannels'], d['maxOutputChannels']))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', help="input audio device name", default='default')
    parser.add_argument('action', default='run', choices=['run', 'inputs'])
    parser.add_argument('--average', help="average channel values for smoothing (1 = no averaging)", type=int, default=1)
    parser.add_argument('--buffer', help="buffer size (smaller = lower latency)", type=int, default=64)
    parser.add_argument('--plot', help="display plot of PPM data", dest='plot', action='store_true')
    parser.add_argument('--debug', help="print debug information", dest='debug', action='store_true')
    parser.set_defaults(plot=False, debug=False)
    args = parser.parse_args()

    if args.action == 'inputs':
        print_inputs()
        return 0

    in_ix = None
    rate = None
    in_name = None

    with noalsaerr():
        a = pyaudio.PyAudio()

    for i in range(a.get_device_count()):
        d = a.get_device_info_by_index(i)
        if args.i == d['name']:
            in_ix = d['index']
            rate = int(d['defaultSampleRate'])
            in_name = d['name']
            break
        if args.i in d['name']:
            in_ix = d['index']
            rate = int(d['defaultSampleRate'])
            in_name = d['name']

    print("Using input: %s, buffer size %d, averaging %d" % (in_name,
        args.buffer, args.average))

    # Smaller = lower latency
    chunk = args.buffer

    stream = a.open(format=pyaudio.paInt16,
                    channels=1,
                    rate=rate,
                    input=True,
                    frames_per_buffer=chunk*2,
                    input_device_index=in_ix)

    try:
        with PPMDecoder(rate, args.average) as ppm:
            while True:
                sample = stream.read(chunk)
                sample = array.array('h', sample)
                ppm.feed(sample, args.plot, args.debug)
    finally:
        stream.close()


if __name__ == '__main__':
    sys.exit(main())
