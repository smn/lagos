# Lagos

Automatically posting of SMSs received on a Psitek Fusion 220 device to a URL. 
Should work w/ modems that work with [pygsm][pygsm]
A long running daemon in Twisted.

## Installation

Implemented as a `twistd` plugin

    $ virtualenv --no-site-packages ve
    $ source ve/bin/activate
    (ve)$ pip install -r requirements.pip
    ... snip ...

## Usage

    (ve)$ twistd lagos --help
    Usage: twistd [options] lagos [options]
    Options:
      -d, --debug              Turn on debug output
      -p, --port=              The port where the GSM is connected [default:
                               /dev/ttyACM0]
          --backup_ports=      Other ports to try in case the primary isn't working
                               [default:
                               /dev/ttyACM1,/dev/ttyACM2,/dev/tty.usbmodem1d11]
      -m, --msisdn=            The SIM's MSISDN, used as MO [default: unknown]
      -u, --uri=               Where to POST the SMS, http://user:pw@host/resource
      -q, --queue_file=        A file queue, saves messages between restarts
                               [default: queue.pickle]
      -i, --interval=          Poll for new messages every so many seconds [default:
                               2]
          --connect_interval=  Check the ports for the modem every so many seconds
                               [default: 2]
          --poll_uri=          Poll the URI for SMS messages to be sent
          --poll_interval=     Poll interval [default: 2]
          --version            
          --help               Display this help and exit.

    

## Run

POST incoming SMSs to a URL, the Psitek modem doesn't give us the MSISDN with which the SIM is registered on the network. Specify if manually on the command line.

    (ve)$ twistd -n lagos \
            --port=/dev/tty.usbmodem3d11 \
            --uri=http://user:passwd@your.domain.com/api/sms/handler \
            --misisdn=+27*********
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
    2010-06-22 10:49:30+0200 [-] Posting <pygsm.IncomingMessage from +27********'> to http://user:passwd@your.domain.com/api/sms/handler
    2010-06-22 10:49:30+0200 [-] Starting factory <HTTPClientFactory: http://your.domain.com/api/sms/handler>
    2010-06-22 10:49:30+0200 [HTTPPageGetter,client] SMS Registered
    2010-06-22 10:49:30+0200 [HTTPPageGetter,client] Stopping factory <HTTPClientFactory: http://your.domain.com/api/sms/handler>

Poll a URL for SMSs to be sent out with the `--poll_uri` option:

    (ve)$ twistd -n lagos \
            --port=/dev/tty.usbmodem3d11 \
            --uri=http://user:passwd@your.domain.com/api/sms/handler \
            --misisdn=+27********* \
            --poll_uri=http://user:passwd@your.domain.com/api/sms/outbox.json

The poll URI should return a JSON formatted list with hashes:

    [
        {
            "uri": "http://user:passwd@your.domain.com/api/sms/outbox/1.json",
            "recipient": "+27123456789",
            "text": "hello world"
        },
        {
            "uri": "http://user:passwd@your.domain.com/api/sms/outbox/2.json",
            "recipient": "+27123456789",
            "text": "hello world"
        }
    ]

When the SMS has successfully been sent, the `uri` specified in the hash will be called with an `HTTP Delete` request. **The service polled is responsible for removing the entry from the outbound SMS list.**

Both `--poll_uri` and `--uri` can be used together to both POST inbound SMSs to a URI as well as polling an external JSON URI for outbound SMSs.

Remove the `-n` to have it run in the background.

## Notes:

* Serializes messages that haven't been posted yet to 'queue.pickle', will be posted when restarted.
* Allows specifying of multiple comma separated backup ports with `--backup_ports` in case the modem switches ports for some reason.
* Supports SSL (pyopenssl requires that you have have openssl installed to compile)
* Supports HTTP Basic Auth
* POST parameters currently not yet configurable, you'll have to change the code to do so.

[pygsm]: http://github.com/rapidsms/pygsm