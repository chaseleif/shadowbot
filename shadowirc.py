#! /usr/bin/env python3

###
#  shadowirc.py
#  This is a (mostly) generic irc handler class
##
#  Author: Chase LP
###

from time import sleep
import re, socket, selectors

''' class IRCHandler
    Attributes
    irc           - Reference to the irc connection, a socket
    remainder     - String, used to gather only partially received lines
    poller        - A DefaultSelector, used to make reads non-blocking
    username      - The username of the irc connection
    printinmsg    - Boolean, indicates whether to print irc messages

    Internal Methods
    send          - Sends a string as bytes to the irc connection
    connect       - Connects to an irc connection and sends an identify message
    privmsg       - Sends a PRIVMSG to a recipient
    get_response  - Receives from the irc socket, with an optional timeout
    joinchan      - Sends a join channel message
'''
class IRCHandler():
  irc        = None # The tcp socket for the irc connection
  remainder  = ''   # Remainder string, used to return only complete lines
  poller     = None # Polling object for reading the tcp socket
  username   = ''   # Username of the irc connection
  printinmsg = True # Whether to print incoming irc text

  ''' init
      Initialize the irc socket and poller
      Connect to the irc server
      Returns after completion of identify to nickserv
  '''
  def __init__(self, server, port, botnick, botpass):
    # Get our tcp socket
    self.irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Make the socket non-blocking
    #  don't think this is necessary since we are using selector (?)
    #self.irc.setblocking(False)
    # Connect the socket
    self.connect(server, port, botnick, botpass)
    # Initialize the polling object
    self.poller = selectors.DefaultSelector()
    self.poller.register(self.irc, selectors.EVENT_READ)
    # Wait to receive message indicating we are identified with NickServ
    print('  Waiting for identify for ' + botnick)
    while True:
      resp = self.get_response()
      if 'Last login from: ' in resp:
        break
    print('  Identified as ' + botnick)
    self.username = botnick

  ''' del
      Closes the poller and shuts down the irc socket
  '''
  def __del__(self):
    try:
      self.poller.close()
    except Exception as e:
      print('  IRCHandler exception closing selector: ' + str(e))
    try:
      self.irc.shutdown(socket.SHUT_RDWR)
      self.irc.close()
    except Exception as e:
      print('  IRCHandler exception closing socket: ' + str(e))

  ''' send
      Utility function to shorten irc sendall messages

      Parameters
      msg         - string to send, should not end with a newline
  '''
  def send(self, msg):
    print('  IRC, sending: \"'+msg+'\"')
    self.irc.sendall(bytes(msg + '\n', 'UTF-8'))

  ''' connect
      Connects to an irc server:port and sends an identify msg to nickserv
  '''
  def connect(self, server, port, botnick, botpass):
    print('  Connecting to ' + server + ':' + str(port))
    self.irc.connect((server, port))
    self.send('USER ' + botnick + ' ' + botnick + ' ' + botnick + ' :ShadowBot')
    self.send('NICK ' + botnick)
    self.send('NICKSERV IDENTIFY ' + botnick + ' ' + botpass)

  ''' privmsg
      Utility function to shorten sending a PRIVMSG to a user/chan
  '''
  def privmsg(self,recipient,msg):
    self.send('PRIVMSG ' + recipient + ' :' + msg)

  ''' get_response
      Method to get text from the irc socket, handles PING PONG messages

      Parameters
      timeout     - integer, optional, the time to wait before returning

      Returns completely received strings
       strings only partially received saved in self.remainder
  '''
  def get_response(self,timeout=30):
    # See if we have a read event on the irc socket
    event = self.poller.select(timeout=timeout)
    # There are no read events, return
    if len(event) == 0:
      return ''
    # Read from the socket
    resp = self.irc.recv(2048).decode('UTF-8')
    # Put any remainder from previous messages at the front
    resp = self.remainder + resp
    # Clear the remainder
    self.remainder = ''
    # If the final character is not a newline we will have a remainder
    if resp[-1] != '\n':
      # Set a flag to indicate that the last line is incomplete
      self.remainder = '1'
    # Split the lines into a list for enumeration
    resp = resp.split('\n')
    for i, line in enumerate(resp):
      # Delete empty lines
      if len(line) == 0:
        del(resp[i])
      # Immediately response to complete PING messages
      # If this is the final line and we have a remainder the line is incomplete
      elif line[0:4] == 'PING' and (self.remainder != '1' or i+1 < len(resp)):
        self.send('PONG' + line[4:])
        # Delete the PING message from our response
        del(resp[i])
    # We have a remainder and at least one line in the list
    if self.remainder == '1' and len(resp) > 0:
      # Take the last line as the remainder
      self.remainder = resp[-1]
      # Delete the line from the list
      del(resp[-1])
    # We have a remainder but no lines in the list, clear the remainder
    elif self.remainder == '1':
      self.remainder = ''
    # The flag for printing incoming irc messages is set, print the message
    if self.printinmsg:
      print('\n'+'\n'.join(resp))
    # remove special garbage characters
    # \002: 02: START OF TEXT
    # \003: 03: END OF TEXT
    # \012: 10: LINE FEED
    # \015: 13: CARRIAGE RETURN
    ret = re.sub('[\002\003\012\015]','','\n'.join(resp))
    # \245: 165: upper Spanish enya (N with tilda), replace with N
    ret = re.sub('[\245]','N',ret)
    # \260: 176: a colored block, replace with space
    ret = re.sub('[\260]',' ',ret)
    # Check for other extra chars not yet caught
    extras = {}
    for c in ret:
      if ord(c) < 32 or ord(c) > 126:
        extras[ord(c)] = 1
    # I think I may have gotten them all though
    if len(extras) > 0:
      print('   ************************')
      print('         extras -> '+str(list(extras.keys())))
      print('   ************************')
    # Return the message (may be an empty string)
    return ret

  ''' joinchan
      Sends a message to join a channel
  '''
  def joinchan(self,chan):
    self.send('JOIN ' + chan)

