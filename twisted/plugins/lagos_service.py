from __future__ import with_statement
from zope.interface import implements

from twisted.python import log, usage
from twisted.application.service import IServiceMaker, Service
from twisted.plugin import IPlugin
from twisted.internet.defer import Deferred
from twisted.internet import reactor
from twisted.web import http

from pygsm.errors import GsmError
from serial.serialutil import SerialException
from contextlib import contextmanager
from lagos.utils import load_queue_from_disk, save_queue_to_disk, request

import uuid, sys, json, pygsm, glob

class Options(usage.Options):
    optParameters = [
        ["port", "p", None, "The port where the GSM is connected"],
        ["match_port", "mp", None, "Try the ports matching this pattern for glob"],
        ["backup_ports", "bp", "/dev/ttyACM1,/dev/ttyACM2,/dev/tty.usbmodem1d11", "Other ports to try in case the primary isn't working"],
        ["msisdn", "m", "unknown", "The SIM's MSISDN, used as MO"],
        ["uri", "u", None, "Where to POST the SMS, http://user:pw@host/resource"],
        ["queue_file", "q", "queue.pickle", "A file queue, saves messages between restarts"],
        ["interval", "i", 2, "Poll for new messages every so many seconds", int],
        ["connect_interval", "ci", 2, "Check the ports for the modem every so many seconds", int],
        ["poll_uri", None, None, "Poll the URI for SMS messages to be sent", str],
        ["poll_interval", None, 2, "Poll interval", int],
    ]
    
    optFlags = [
        ["debug", "d", "Turn on debug output"],
    ]


class LagosService(Service):
    def __init__(self, uri, queue_file, port, match_port, backup_ports, interval, 
                    connect_interval, debug, msisdn, poll_uri, poll_interval):
        self.uri = uri
        self.queue_file = queue_file
        self.ports = [port] if port else []
        if backup_ports:
            self.ports += [bp.strip() for bp in backup_ports.split(",")]
        self.match_port = match_port
        
        self.interval = interval
        self.connect_interval = connect_interval
        self.debug = debug
        self.msisdn = msisdn
        self.poll_uri = poll_uri
        self.poll_interval = poll_interval
    
    def reboot(self):
        with self.reboot_on_exception():
            log.msg("Rebooting Lagos")
            self.stopService()
            self.startService()
    
    def startService(self):
        log.msg("Starting Lagos")
        reactor.callLater(0, self.connect_modem)
        if self.poll_uri:
            reactor.callLater(0, self.poll_uri_for_messages)
    
    def logger(self, modem, msg, _type):
        if self.debug:
            log.msg("%8s %s" % (_type, msg))
    
    def connect_modem(self):
        ports = self.ports
        # allow for re-globbing while running, might change after booting
        if self.match_port:
            ports += glob.glob(self.match_port)
        
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
        log.msg("Attempting modem on port %s" % port)
        self.modem = pygsm.GsmModem(port=port, mode="text", 
                                        logger=self.logger)
        self.modem.boot()
        self.modem.incoming_queue = load_queue_from_disk(self.queue_file)
        self.wait_for_network()
    
    def modem_is_ready(self):
        try:
            return hasattr(self, 'modem') and self.modem.ping()
        except SerialException, e:
            log.err()
            return False
    
    def wait_for_network(self):
        with self.reboot_on_exception():
            log.msg("Waiting for network connection")
            self.modem.wait_for_network()
            log.msg("Got network connection, signal strength: %s" % \
                self.modem.signal_strength())
        self.poll_modem_for_messages()
        
    @contextmanager
    def reboot_on_exception(self):
        """Anything that fails in this contextmanager causes a reboot"""
        try:
            yield
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
    
    def poll_modem_for_messages(self):
        log.msg("Polling for messages")
        with self.reboot_on_exception():
            deferred = Deferred()
            deferred.addCallback(self.post_message)
            deferred.addErrback(log.err)
            deferred.callback(self.modem.next_message())
            return deferred
    
    def poll_uri_for_messages(self):
        with self.reboot_on_exception():
            log.msg("Polling %s for new messages to be sent out." % self.poll_uri)
            if self.modem_is_ready():
                deferred = request(self.poll_uri, method='GET')
                deferred.addCallback(self.poll_uri_for_messages_success)
                deferred.addErrback(self.poll_uri_for_messages_fail)
                return deferred
            else:
                log.err("Modem is not ready, no use polling.")
            # reschedule
            reactor.callLater(self.poll_interval, self.poll_uri_for_messages)
    
    def poll_uri_for_messages_fail(self, result):
        log.err(result)
        log.msg("Polling for new messages failed!")
    
    def poll_uri_for_messages_success(self, result):
        required_keys = ['recipient', 'text', 'uri']
        messages = json.loads(result)
        for message in messages:
            # check if the JSON makes any sense
            if all([k in message for k in required_keys]):
                # try and send the SMS
                if self.modem.send_sms(recipient=message['recipient'],
                                       text=message['text']):
                    # send an HTTP DELETE to the URI specified in the message
                    log.msg('Message sent, sending DELETE to %(uri)s' % message)
                    deferred = request(str(message['uri']), method='DELETE')
                    deferred.addCallback(self.delete_message_success)
                    deferred.addErrback(log.err)
                else:
                    log.err('Unable to send SMS, no clue why.')
            else:
                log.err("Invalid JSON message received, missing " \
                        "entries: %s" % (required_keys - message.keys(),))
    
    def delete_message_success(self, result):
        log.msg("Message deleted successfully: %s" % result)
    
    def post_message(self, message):
        if message:
            log.msg("Posting %s to %s" % (message, self.uri))
            deferred = request(self.uri, data={
                'sender_msisdn': message.sender,
                'recipient_msisdn': self.msisdn,
                'sms_id': uuid.uuid4(),
                'message': message.text,
            }, method='POST')
            deferred.addCallback(self.post_message_success)
            deferred.addErrback(self.post_message_failed, message)
        else:
            log.msg("No messages available, checking again after %s seconds" % self.interval)
        return reactor.callLater(self.interval, self.poll_modem_for_messages)
    
    def post_message_success(self, result):
        log.msg(result)
    
    def post_message_failed(self, result, message):
        log.err(result)
        exception = result.value
        if int(exception.status) == http.CONFLICT:
            log.msg("Duplicate submission, skipping.")
        else:
            log.msg("Adding %s to the back of the queue " \
                    "because posting failed" % message)
            self.modem.incoming_queue.append(message)
    
    def disconnect_modem(self):
        log.msg("Disconnecting modem")
        save_queue_to_disk(self.queue_file, self.modem.incoming_queue)
        self.modem.disconnect()
        del self.modem # hopefully garbage collect & disconnect all devices

    def stopService(self):
        log.msg("Stopping Lagos")
        if self.modem_is_ready():
            self.disconnect_modem()
        else:
            log.msg("Modem not connected, no need to disconnect.")


class LagosServiceMaker(object):
    implements(IServiceMaker, IPlugin)
    tapname = "lagos"
    description = "POST incoming SMSs to a URL, poll a URL for outgoing SMSs"
    options = Options
    
    def makeService(self, options):
        if not options['uri']:
            print "URI is required"
            print options
            sys.exit(1)
        return LagosService(**options)
    

serviceMaker = LagosServiceMaker()

