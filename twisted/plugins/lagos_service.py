from __future__ import with_statement
from zope.interface import implements
from twisted.python import log, usage
from twisted.application.service import IServiceMaker, Service
from twisted.plugin import IPlugin
from twisted.internet.defer import Deferred
from twisted.internet import reactor, ssl
from twisted.web import client
import shutil
import pygsm
from pygsm.errors import GsmError
from serial.serialutil import SerialException
import sys
import urllib
import os.path
from base64 import b64encode
from urlparse import urlsplit
from datetime import datetime
try:
    import cPickle as pickle
except ImportError:
    import pickle

class Options(usage.Options):
    optParameters = [
        ["port", "p", "/dev/ttyACM0", "The port where the GSM is connected"],
        ["backup_ports", "bp", "/dev/ttyACM1,/dev/tty.usbmodem1d11", "Other ports to try in case the primary isn't working"],
        ["msisdn", "m", "unknown", "The SIM's MSISDN, used as MO"],
        ["uri", "u", None, "Where to POST the SMS, http://user:pw@host/resource"],
        ["queue_file", "q", "queue.pickle", "A file queue, saves messages between restarts"],
        ["interval", "i", 2, "Poll for new messages every so many seconds", int],
        ["connect_interval", "ci", 2, "Check the ports for the modem every so many seconds", int],
    ]
    
    optFlags = [
        ["debug", "d", "Turn on debug output"],
    ]

def load_queue_from_disk(filename):
    """
    Load the old queue from disk when started. Old messages that weren't
    posted yet are read from the queue and processed.
    """
    if os.path.exists(filename):
        log.msg("Loading queue from %s" % filename)
        try:
            fp = open(filename, 'r')
            data = pickle.load(fp)
            fp.close()
            return data
        except IOError, e:
            log.err()
            backup_filename = "%s.%s" % (
                filename, 
                datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            )
            shutil.copyfile(filename, backup_filename)
            log.err("Couldn't load queue from %s, backed it up to %s" % (
                filename, backup_filename
            ))
    
    # return an empty queue, start from scratch.
    return []

def save_queue_to_disk(filename, queue):
    """
    Save the queue to disk when shutting down, makes sure we don't
    lose any messages during shutdown & restart.
    """
    log.msg("Saving queue to %s" % filename)
    fp = open(filename, 'w+')
    pickle.dump(queue, fp)
    fp.close()


def callback(url, data={}):
    """
    Post the given dictionary to the URL.
    """
    url_info = urlsplit(url)
    
    # determine what port we're on
    if url_info.scheme == 'https':
        context_factory = ssl.ClientContextFactory()
        port = url_info.port or 443
    elif url_info.scheme == 'http':
        context_factory = None
        port = url_info.port or 80
    else:
        raise RuntimeError, 'unsupported callback scheme %s' % url_info.scheme
    
    # Twisted doesn't understand it when auth credentials are passed along
    # in the URI, remove those (ie scheme://user:password@host/path)
    url_without_auth = "%s://%s:%s%s" % (
        url_info.scheme, url_info.hostname, port, url_info.path
    )
    # Encode the credentials to send them as an HTTP Header
    b64_credentials = b64encode("%s:%s" % (url_info.username, url_info.password))
    return client.getPage(url_without_auth, context_factory, 
        postdata=urllib.urlencode(data),
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': 'Basic %s' % b64_credentials
        }, 
        agent='Lagos SMS - http://github.com/smn/lagos',
        method='POST',
    )

class LagosService(Service):
    def __init__(self, uri, queue_file, port, backup_ports, interval, 
                    connect_interval, debug, msisdn):
        self.uri = uri
        self.queue_file = queue_file
        self.port = port
        self.backup_ports = [bp.strip() for bp in backup_ports.split(",")]
        self.interval = interval
        self.connect_interval = connect_interval
        self.debug = debug
        self.msisdn = msisdn
    
    def reboot(self):
        log.msg("Rebooting Lagos")
        self.stopService()
        self.startService()
    
    def startService(self):
        log.msg("Starting Lagos")
        self.connect_modem()
    
    def logger(self, modem, msg, _type):
        if self.debug:
            log.msg("%8s %s" % (_type, msg))
    
    def connect_modem(self):
        ports = [self.port]
        ports.extend(self.backup_ports)
        for port in ports:
            try:
                self.connect_modem_on_port(port)
                log.msg("Connected to modem on port %s" % port)
                return
            except SerialException, e:
                if self.debug: log.err()
                log.msg("Port %s doesn't seem to be working, next!" % port)
        
        log.msg("None of the ports are responding, trying all " \
                "again after %s seconds" % self.connect_interval)
        reactor.callLater(self.connect_interval, self.reboot)
    
    def connect_modem_on_port(self, port):
        log.msg("Connecting modem")
        self.modem = pygsm.GsmModem(port=port, mode="text", 
                                        logger=self.logger)
        self.modem.boot()
        self.modem.incoming_queue = load_queue_from_disk(self.queue_file)
        self.wait_for_network()
    
    def wait_for_network(self):
        log.msg("Waiting for network connection")
        self.modem.wait_for_network()
        log.msg("Got network connection, signal strength: %s" % \
                    self.modem.signal_strength())
        deferred = self.poll_messages()

    def poll_messages(self):
        log.msg("Polling for messages")
        try:
            deferred = Deferred()
            deferred.addCallback(self.post_message)
            deferred.addErrback(log.err)
            deferred.callback(self.modem.next_message())
            return deferred
        except GsmError, e:
            log.err()
            self.reboot()
        except SerialException, e:
            log.err()
            self.reboot()
        except Exception, e:
            log.msg("### UNEXPECTED EXCEPTION ####")
            log.err()
            log.msg("Unexpected exception, waiting for a minute before trying again.")
            reactor.callLater(60, self.reboot)
    
    def post_message(self, message):
        if message:
            log.msg("Posting %s to %s" % (message, self.uri))
            deferred = callback(self.uri, {
                'sender_msisdn': message.sender,
                'recipient_msisdn': self.msisdn,
                'sms_id': 'unknown',
                'message': message.text,
            })
            deferred.addCallback(self.post_message_success)
            deferred.addErrback(self.post_message_failed, message)
        else:
            log.msg("No messages available, checking again after %s seconds" % self.interval)
        return reactor.callLater(self.interval, self.poll_messages)
    
    def post_message_success(self, result):
        log.msg(result)
    
    def post_message_failed(self, result, message):
        log.err(result)
        log.msg("Adding %s to the back of the queue " \
                "because posting failed" % message)
        self.modem.incoming_queue.append(message)
    
    def disconnect_modem(self):
        log.msg("Disconnecting modem")
        save_queue_to_disk(self.queue_file, self.modem.incoming_queue)
        self.modem.disconnect()

    def stopService(self):
        log.msg("Stopping Lagos")
        self.disconnect_modem()


class LagosServiceMaker(object):
    implements(IServiceMaker, IPlugin)
    tapname = "lagos"
    description = "POST incoming SMSs to a URL"
    options = Options
    
    def makeService(self, options):
        if not options['uri']:
            print "URI is required"
            print options
            sys.exit(1)
        return LagosService(**options)
    

serviceMaker = LagosServiceMaker()

