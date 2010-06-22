# Lagos

Automatically posting of SMSs received on a Psitek Fusion 220 device to a URL. A long running daemon in Twisted.

## Usage

Implemented as a `twistd` plugin

    $ virtualenv --no-site-packages ve
    $ source ve/bin/activate
    (ve)$ pip install -r requirements.pip
    (ve)$ twistd -n lagos \
            --port=/dev/tty.usbmodem3d11 \
            --uri=http://user:passwd@127.0.0.1:8000/debug/

Remove the `-n` to have it run in the background.

## Notes:

* Serializes messages that haven't been posted yet to 'queue.pickle', will be posted when restarted.
* Supports SSL
* Supports HTTP Basic Auth