# PPMAdapter - An RC PPM decoder and joystick emulator
# Copyright 2016 Nigel Sim <nigel.sim@gmail.com>
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
import datetime
import collections

from evdev import UInput, ecodes
from ctypes import CFUNCTYPE, c_char_p, c_int, cdll
from contextlib import contextmanager

try:
    import numpy as np
    import matplotlib.pyplot as plt
    #from matplotlib.animation import FuncAnimation
    #from mpl_toolkits.axes_grid1 import make_axes_locatable
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
    def __init__(self, rate):
        """
        Parameters
        ----------
        rate : int
            sample rate
        """
        self._rate = float(rate)
        self._last_fall = None
        self._last_rise = None
        self._threshold = 12000
        self._last_edge = None
        self._ch = None

        # To get of weird jittering, average past values. Note this does
        # increase latency
        self._average_length = 15

        # Size in sampling intervals, of the frame space marker
        # Note: probably should be 2, but sometimes it's not quite
        self._marker = int(1.75 * 0.0025 * self._rate)

        # Mapping of channels to events
        self._mapping = {0: ecodes.ABS_X,
                         1: ecodes.ABS_Y,
                         2: ecodes.ABS_Z,
                         3: ecodes.ABS_THROTTLE}

        # History of values (for averaging)
        self._history = {i: collections.deque(maxlen=self._average_length) \
                for i in self._mapping.keys()}

        events = [(v, (0, 5, 255, 0)) for v in self._mapping.values()]

        self._ev = UInput(name='ppmadapter',
                          events={
                               ecodes.EV_ABS: events,
                               ecodes.EV_KEY: {288: 'BTN_JOYSTICK'}
                          })

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        self._ev.close()

    def feed(self, data, plot=False, measure_high=True):
        """Feeds the decoder with a block of sample data.

        The data should be integer values, and should only be a single channel.

        Parameters
        ----------
        data : list
            Sample data
        plot : bool
            Whether to display data in a matplotlib plot or not
        measure_high : bool
            Whether to compute the duration of each channel based on the time
            it's high or low. Code originally was False case but on my controller
            the high time seems to be what's modulated. I can't find docs on
            PPM yet... just doing what works for me here...
        """
        if plot:
            rising = np.zeros((len(data),))
            falling = np.zeros((len(data),))

        sync_req = False
        for i in range(len(data)):
            this_edge = data[i] > self._threshold
            if self._last_edge is None:
                self._last_edge = this_edge
                continue

            if this_edge and not self._last_edge:
                # rising
                self._last_rise = i

                if self._last_fall is not None:
                    if not measure_high:
                        sync_req |= self.signal(i - self._last_fall)

                    if plot:
                        rising[i] = self._threshold
            elif not this_edge and self._last_edge:
                # falling
                self._last_fall = i

                if self._last_rise is not None:
                    if measure_high:
                        sync_req |= self.signal(i - self._last_rise)

                    if plot:
                        falling[i] = self._threshold

            self._last_edge = this_edge

        if sync_req:
            # For averaging, now average compute values here, set them, then sync
            for channel, values in self._history.items():
                if len(values) > 0:
                    avg = int(sum(values)/len(values))
                    self._ev.write(ecodes.EV_ABS, self._mapping[channel], avg)
                    #print("ch"+str(channel), "=", avg)

            self._ev.syn()
            #print("sync", datetime.datetime.now())

        # Handle wrapping around data window
        if self._last_fall is not None:
            self._last_fall = self._last_fall - len(data)

            if self._last_fall < (-self._rate):
                print("Lost sync")
                self._ch = None
                self._last_fall = None
                self._last_rise = None

        if self._last_rise is not None:
            self._last_rise = self._last_rise - len(data)

        if plot:
            y = list(data)
            x = np.arange(0, len(y), 1)
            plt.plot(x, y, label="signal")
            plt.plot(x, rising, label="rising")
            plt.plot(x, falling, label="falling")
            plt.legend()
            plt.show()

    def signal(self, w):
        """Process the detected signal.

        The signal is the number of sampling intervals between the falling
        edge and the rising edge.

        Parameters
        ----------
        w : int
            signal width

        Returns
        -------
        bool
            does uinput require sync
        """
        if w > self._marker:
            if self._ch is None:
                print("Got sync")
            self._ch = 0
            #print("reset at", w, "vs. desired length", self._marker)
            return False

        if self._ch is None or self._ch not in self._mapping:
            return False

        duration = float(w) / self._rate
        value = int((duration - 0.0007) * 1000 * 255)

        # To enable averaging, add current value to queue but don't set it yet
        assert self._ch in self._history, str(self._ch)+" not in _history"
        self._history[self._ch].append(value)
        #self._ev.write(ecodes.EV_ABS, self._mapping[self._ch], value)

        self._ch += 1

        return True


def print_inputs():
    with noalsaerr():
        print("Input audio devices")
        print("-------------------")
        a = pyaudio.PyAudio()
        for i in range(a.get_device_count()):
            d = a.get_device_info_by_index(i)
            print( "%s: \t Max Channels: in[%s] out[%s]" % (d['name'], d['maxInputChannels'], d['maxOutputChannels']) )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', help="input audio device name", default='default')
    parser.add_argument('action', default='run', choices=['run', 'inputs'])
    parser.add_argument('--plot', help="display plot of PPM data", dest='plot', action='store_true')
    parser.set_defaults(plot=False)
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

    print("Using input: %s" % in_name)

    # Smaller = lower latency
    chunk = 512

    stream = a.open(format=pyaudio.paInt16,
                    channels=1,
                    rate=rate,
                    input=True,
                    frames_per_buffer=chunk*2,
                    input_device_index=in_ix)

    try:
        with PPMDecoder(rate) as ppm:
            while True:
                sample = stream.read(chunk)
                sample = array.array('h', sample)
                ppm.feed(sample, args.plot)
    finally:
        stream.close()

if __name__ == '__main__':
    sys.exit(main())
