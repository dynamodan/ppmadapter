PPM Adapter
===========

This is a userspace application that reads the PPM audio stream produced by
many RC controllers, and produces a virtual joystick using the uinput system.

This was forked from https://github.com/nigelsim/ppmadapter where development
seems to have fallen behind. This fork attempts to update and modify so as to
have a working copy, aiming for python3 support.

Installation
------------

This application requires two libraries, pyaudio and python-evdev. They are
declared in the setup.cfg file, so will be installed if you ``pip install``,
but you can also install them using your system package manager, looking for
packages similar in name to:

>      python-pyaudio python-evdev


Notes
-----

Ignore any input like the following, it is a consequence of using the Port Audio library:

```
        ALSA lib pcm.c:2267:(snd_pcm_open_noupdate) Unknown PCM cards.pcm.rear
        ALSA lib pcm.c:2267:(snd_pcm_open_noupdate) Unknown PCM cards.pcm.center_lfe
        ALSA lib pcm.c:2267:(snd_pcm_open_noupdate) Unknown PCM cards.pcm.side
        ALSA lib pcm_route.c:867:(find_matching_chmap) Found no matching channel map
        Cannot connect to server socket err = No such file or directory
        Cannot connect to server request channel
        jack server is not running or cannot be started
```


Usage
-----

You may have to give your user access to the /dev/uinput device. This is beyond the scope of this document, but there are options using udev rules, or just chmod.

You can use the built in microphone port, or the USB one provided with some (cheap?) adapters. To see a list of candidate input devices type:

>        python -m ppmadapter inputs


You will get a list like this:

``
    HDA Intel PCH: ALC892 Analog (hw:0,0): 	 Max Channels: in[2] out[0]
    HDA Intel PCH: ALC892 Digital (hw:0,1): 	 Max Channels: in[0] out[2]
    HDA Intel PCH: ALC892 Alt Analog (hw:0,2): 	 Max Channels: in[2] out[0]
    HDA NVidia: HDMI 0 (hw:1,3): 	 Max Channels: in[0] out[2]
    HDA NVidia: HDMI 1 (hw:1,7): 	 Max Channels: in[0] out[2]
    HDA NVidia: HDMI 2 (hw:1,8): 	 Max Channels: in[0] out[8]
    HDA NVidia: HDMI 3 (hw:1,9): 	 Max Channels: in[0] out[2]
    sysdefault: 	 Max Channels: in[128] out[128]
    iec958: 	 Max Channels: in[0] out[2]
    spdif: 	 Max Channels: in[0] out[2]
    default: 	 Max Channels: in[128] out[128]
    dmix: 	 Max Channels: in[0] out[2]
``


Then, to start the application with a specific card:

>        python -m ppmadapter -i hw:0 run
>        python -m ppmadapter -i hw:1,7 run

A match will be done on the name to find the right adapter. At this point if you run ``dmesg`` you should see something like the following, indicating that the device has been created:
>        input: ppmadapter as /devices/virtual/input/input62

Controller setup
''''''''''''''''
Original project:
>I use a Turnigy 9XR PRO running OpenTX. I've got a model setup to use PPM 1-4 channels using ``22.5ms`` and ``350us`` spacing, with ``-`` polarity. When you plug your controller in you should see the words **Got sync** written.

This project:
>I use a Flysky FS-i6 with the adapter cable for direct microphone input. PPM 1-6 channels.

License
-------
GPL v3
