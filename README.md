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
    2010-06-22 15:49:27+0200 [-] Log opened.
    2010-06-22 15:49:27+0200 [-] twistd 10.0.0 (/Users/sdehaan/Documents/Repositories/lagos/ve/bin/python 2.6.5) starting up.
    2010-06-22 15:49:27+0200 [-] reactor class: twisted.internet.selectreactor.SelectReactor.
    2010-06-22 15:49:27+0200 [-] Starting Lagos
    2010-06-22 15:49:27+0200 [-] Connecting modem
    2010-06-22 15:49:27+0200 [-] Loading queue from queue.pickle
    2010-06-22 15:49:27+0200 [-] Waiting for network connection
    2010-06-22 15:49:28+0200 [-] Got network connection, signal strength: 21
    2010-06-22 15:49:28+0200 [-] Polling for messages
    2010-06-22 15:49:28+0200 [-] No messages available, checking again after 2 seconds
    2010-06-22 15:49:30+0200 [-] Polling for messages
    2010-06-22 15:49:30+0200 [-] No messages available, checking again after 2 seconds
    2010-06-22 15:49:32+0200 [-] Polling for messages
    2010-06-22 15:49:32+0200 [-] No messages available, checking again after 2 seconds
    2010-06-22 15:49:34+0200 [-] Polling for messages
    2010-06-22 15:49:34+0200 [-] No messages available, checking again after 2 seconds


Remove the `-n` to have it run in the background.

## Notes:

* Serializes messages that haven't been posted yet to 'queue.pickle', will be posted when restarted.
* Supports SSL
* Supports HTTP Basic Auth