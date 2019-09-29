PPM Adapter
===========
This is a userspace application that reads the PPM audio stream produced by
many RC controllers, and produces a virtual joystick using the uinput system.

This was forked from [amckee/ppmadapter](https://github.com/amckee/ppmadapter)
that provided a Python 3 compatible version of PPM Adapter. However, it seemed
not to work with my controller, so I modified it to use the PPM to TX logic
(but still being userspace not requiring a user-compiled kernel module) at
[nexx512/txppm/ppm.c](https://github.com/nexx512/txppm/blob/master/software/ppm.c).

Installation
------------
This application requires two libraries, pyaudio and python-evdev. They are
declared in the setup.cfg file, so will be installed if you ``pip install``,
but you can also install them using your system package manager, looking for
packages similar in name to:

    python-pyaudio python-evdev

Usage
-----
You need user access to */dev/uinput*. To create a udev rule giving access to
users in the "input" group, put in */etc/udev/rules.d/99-uinput.rules*

    KERNEL=="uinput", GROUP:="input", MODE:="0666"

Then reload the udev rules with (and make sure you're in the "input" group, if
not, add yourself and logout/login):

    sudo udevadm control --reload-rules && sudo udevadm trigger

To select which microphone input you wish to use, list them with:

    python3 -m ppmadapter inputs

Start PPM Adapter specifying one of the inputs (e.g. *hw:0*, *hw:1,7*, or *default*):

    python3 -m ppmadapter -i default run

Also see options *--plot* and/or *--debug* for debugging and *--average* and
*--buffer* for adjusting smoothness and latency. After running, ``dmesg`` should
show the input has been created:

    input: ppmadapter as /devices/virtual/input/inputXX

Tested controllers: Spektrum DX6i, RadioLink AT9S

Testing
-------
A few options for checking the joystick inputs are reasonable: ``jstest-gtk``
or ``crrcsim``. For a simulator, I've tried using ``crrcsim`` (either as audio
input directly or with the input from PPM Adapter),
[neXt](https://aur.archlinux.org/packages/next/), and FlightGear.

For neXt, you can create a config file *~/neXt/controllerconfigs.txt* something
like the following and then configure/calibrate the channels within the
simulator:

    03000000010000000100000001000000,ppmadapter,platform:Linux,leftx:a4,lefty:a1,rightx:a2,righty:a3

(Alternatively generate your own config using [controllermap](https://aur.archlinux.org/packages/controllermap/))

License
-------
GPL v3
