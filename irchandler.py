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
  remainder  = ''   # Remainder string, used to return only complete lines
  readybuff  = []   # A list of full lines that have been received
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
    self.connect(server, port, botnick)
    # Make the socket non-blocking
    self.irc.setblocking(False)
    # Initialize the polling object
    self.poller = selectors.DefaultSelector()
    self.poller.register(self.irc, selectors.EVENT_READ)
    # Wait to receive message indicating we are identified with NickServ
    print('    Waiting for identify for ' + botnick)
    while 'NickServ IDENTIFY' not in self.get_response():
      continue
    self.identify(server, botnick, botpass)
    del botpass
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

  ''' toggle_prints
      Set printinmsg to enable/disable printing of all incoming IRC messages
  '''
  def toggle_prints(self):
    self.printinmsg = not self.printinmsg

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
      Connects to an irc server:port
  '''
  def connect(self, server, port, botnick):
    print('    Connecting to ' + server + ':' + str(port))
    self.irc.connect((server, port))
    self.send('USER ' + botnick + ' ' + botnick + ' ' + botnick + ' :ShadowBot')
    self.send('NICK ' + botnick)

  ''' identify
      Identifies with nickserv
  '''
  def identify(self, server, botnick, botpass):
    msg = 'NICKSERV IDENTIFY '
    if 'libera' in server:
      msg += botnick + ' '
    msg += botpass
    # Don't use self.send so we don't echo the pass to console
    self.irc.sendall(bytes(msg + '\n', 'UTF-8'))
    del msg

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
      # The flag for printing incoming irc messages is set, print the message
      if self.printinmsg:
        print(ret)
      return ret
    # See if we have a read event on the irc socket
    event = self.poller.select(timeout=timeout)
    # There are no read events, return
    if len(event) == 0:
      return ''
    # Read from the socket
    resp = self.irc.recv(2048).decode('UTF-8')

    # remove garbage special characters
    # \002: 02: START OF TEXT
    # \003: 03: END OF TEXT
    resp = re.sub('[\002\003]','',resp)
    # turn any tabs into spaces
    resp = re.sub('\t',' ',resp)
    # combine any span of spaces into a single
    resp = re.sub(' [ ]+',' ',resp)
    # \245: Replace the yen symbol with '$'
    resp = re.sub('[\245]','$',resp)
    # \260: the degree symbol
    resp = re.sub('[\260]','*',resp)
    # \264: meant to be an apostrophe
    resp = re.sub('[\264]','\'',resp)
    # 96: also an apostrophe
    resp = re.sub(chr(96),'\'',resp)
    # \366: o umlaut, make an oe
    resp = re.sub('[\366]','oe',resp)
    # turn carriage returns into newlines
    resp = re.sub('\r','\n',resp)
    # condense any span of newlines into a single
    resp = re.sub('\n[\n]+','\n',resp)

    # Put any remainder from previous messages at the front
    resp = self.remainder + resp
    if len(resp) == 0:
      return ''
    # Clear the remainder
    self.remainder = False
    # If the final character is not a newline we will have a remainder
    if resp[-1] != '\n':
      # Set a flag to indicate that the last line is incomplete
      self.remainder = True
    # Split the lines into a list for enumeration
    resp = resp.split('\n')
    for i, line in enumerate(resp):
      # Delete empty lines
      if len(line) == 0:
        del(resp[i])
      # Immediately respond to complete PING messages
      elif line.startswith('PING'):
        # (If this is the final line with no remainder the line is incomplete)
        if not self.remainder or i+1 < len(resp):
          self.send('PONG' + line[4:])
          # Delete the PING message from our response
          del(resp[i])
    # We have a remainder and at least one line in the list
    if self.remainder and len(resp) > 0:
      # Take the last line as the remainder
      self.remainder = resp[-1]
      # Delete the line from the list
      del(resp[-1])
    # Otherwise there is no remainder
    else:
      self.remainder = ''
    # Convert the list into a single string again
    resp = '\n'.join(resp)
    # If the string is empty just return
    if len(resp) == 0:
      return ''

    # Add any new lines to the ready buffer
    self.readybuff = [s for s in resp.split('\n') if s != '']
    # Return what we have
    ret = ''
    if len(self.readybuff) > 0:
      ret = self.readybuff[0]
      del(self.readybuff[0])
      # The flag for printing incoming irc messages is set, print the message
      if self.printinmsg:
        print(ret)

    return ret

  ''' joinchan
      Sends a message to join a channel
  '''
  def joinchan(self,chan):
    self.send('JOIN ' + chan)

