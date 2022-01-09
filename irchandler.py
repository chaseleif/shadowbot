#! /usr/bin/env python3

'''
    shadowbot - an IRC bot to talk to another IRC bot
    Copyright (C) 2022  Chase Phelps

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
'''

###
#  shadowirc.py
#  This is a pretty generic irc handler class
##
#  Author: Chase LP
###

import time
import re, socket, selectors

''' class IRCHandler
    Attributes
    irc           - Reference to the irc connection, a socket
    remainder     - String, used to gather only partially received lines
    readybuff     - List of full lines that have been received
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
  readybuff  = []   # A list of full lines that have been received
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
    # Connect the socket
    self.connect(server, port, botnick, botpass)
    # Make the socket non-blocking
    self.irc.setblocking(False)
    # Initialize the polling object
    self.poller = selectors.DefaultSelector()
    self.poller.register(self.irc, selectors.EVENT_READ)
    # Wait to receive message indicating we are identified with NickServ
    print('    Waiting for identify for ' + botnick)
    while True:
      resp = self.get_response()
      if 'Last login from' in resp:
        break
    print('    Identified as ' + botnick)
    self.username = botnick

  ''' del
      Closes the poller and shuts down the irc socket
  '''
  def __del__(self):
    try:
      self.poller.close()
    except Exception as e:
      print('    IRCHandler exception closing selector: ' + str(e))
    try:
      self.irc.shutdown(socket.SHUT_RDWR)
      self.irc.close()
    except Exception as e:
      print('    IRCHandler exception closing socket: ' + str(e))

  ''' send
      Utility function to shorten irc sendall messages

      Parameters
      msg         - string to send, should not end with a newline
  '''
  def send(self, msg):
    if msg == '': return
    if msg.startswith('PONG'):
      print('    IRC -> PING PONG PING PONG ! ! !')
    else:
      print('    IRC -> \"'+msg+'\"')
    self.irc.sendall(bytes(msg + '\n', 'UTF-8'))

  ''' connect
      Connects to an irc server:port and sends an identify msg to nickserv
  '''
  def connect(self, server, port, botnick, botpass):
    print('    Connecting to ' + server + ':' + str(port))
    self.irc.connect((server, port))
    self.send('USER ' + botnick + ' ' + botnick + ' ' + botnick + ' :ShadowBot')
    self.send('NICK ' + botnick)
    # Do the identify message here so we don't echo the pass to console
    msg = 'NICKSERV IDENTIFY ' + botnick + ' ' + botpass + '\n'
    self.irc.sendall(bytes(msg, 'UTF-8'))

  ''' privmsg
      Utility function to shorten sending a PRIVMSG to a user/chan
  '''
  def privmsg(self, recipient, msg, delay=2):
    if msg == '': return
    # Give small delay for the automated texts
    if delay > 0:
      time.sleep(delay)
    self.send('PRIVMSG ' + recipient + ' :' + msg)

  ''' get_response
      Method to get text from the irc socket, handles PING PONG messages

      Parameters
      timeout     - integer, optional, the time to wait before returning

      Returns a completely received string
       strings only partially received saved in self.remainder
       extra strings saved in self.readybuff
  '''
  def get_response(self,timeout=30):
    if len(self.readybuff) > 0:
      ret = self.readybuff[0]
      self.readybuff = self.readybuff[1:]
      return ret
    # See if we have a read event on the irc socket
    event = self.poller.select(timeout=timeout)
    # There are no read events, return
    if len(event) == 0:
      ret = ''
      if len(self.readybuff) > 0:
        ret = self.readybuff[0]
        self.readybuff = self.readybuff[1:]
      return ret
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
    # convert the list into a single string
    resp = '\n'.join(resp)
    # if the return string is empty just return it
    if len(resp)==0:
      if len(self.readybuff) > 0:
        resp = self.readybuff[0]
        self.readybuff = self.readybuff[1:]
      return resp

    # remove garbage special characters which mess with message parsing

    # \002: 02: START OF TEXT
    # \003: 03: END OF TEXT
    ret = re.sub('[\002\003]','',resp)
    # turn any tabs into spaces
    ret = re.sub('\t',' ',ret)
    # combine any span of spaces into a single
    ret = re.sub(' [ ]+',' ',ret)

    # \260: 176: the degree symbol, seen in Libera Chat's MOTD
    ret = re.sub('[\260]','*',ret)

    # \264: 180: meant to be an apostrophe
    ret = re.sub('[\264]','\'',ret)

    # \245: 165: The yen symbol, replacing with '$'
    ret = re.sub('[\245]','$',ret)

    # \012: 10: '\n'
    # \015: 13: '\r'
    # turn carriage returns into newlines
    ret = re.sub('\r','\n',ret)
    # condense any span of newlines into a single
    ret = re.sub('\n[\n]+','\n',ret)

    # Check for other extra chars not yet caught
    extras = {}
    for c in ret:
      if c == '\n': continue
      if ord(c) < 32 or ord(c) > 126:
        extras[ord(c)] = 1
    # I think I may have gotten them all though
    if len(extras) > 0:
      print('     ************************')
      print('           extras -> '+str(list(extras.keys())))
      print('     ************************')
    # Append any new lines to the ready buffer
    self.readybuff += ret.split('\n')
    # Return whatever we have
    ret = ''
    if len(self.readybuff) > 0:
      ret = self.readybuff[0]
      self.readybuff = self.readybuff[1:]

    # The flag for printing incoming irc messages is set, print the message
    if self.printinmsg:
      print(ret)

    return ret

  ''' joinchan
      Sends a message to join a channel
  '''
  def joinchan(self,chan):
    self.send('JOIN ' + chan)

