#! /usr/bin/env python3

from time import sleep
import socket, selectors

class IRCHandler():
  irc        = None
  remainder  = ''
  poller     = None
  username   = ''
  printinmsg = True

  def __init__(self, server, port, botnick, botpass):
    self.irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.irc.setblocking(True)
    self.connect(server, port, botnick, botpass)
    self.poller = selectors.DefaultSelector()
    self.poller.register(self.irc, selectors.EVENT_READ)
    print('  Waiting for identify for ' + botnick)
    while True:
      resp = self.get_response()
      if 'Last login from: ' in resp:
        break
    print('  Identified as ' + botnick)
    self.username = botnick

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

  def send(self, msg):
    print('  IRC, sending: \"'+msg+'\"')
    self.irc.sendall(bytes(msg + '\n', 'UTF-8'))

  def connect(self, server, port, botnick, botpass):
    print('  Connecting to ' + server + ':' + str(port))
    self.irc.connect((server, port))
    self.send('USER ' + botnick + ' ' + botnick + ' ' + botnick + ' :ShadowBot')
    self.send('NICK ' + botnick)
    self.send('NICKSERV IDENTIFY ' + botnick + ' ' + botpass)

  def privmsg(self,recipient,msg):
    self.send('PRIVMSG ' + recipient + ' :' + msg)

  def get_response(self,timeout=30):
    try:
      event = self.poller.select(timeout=timeout)
    except KeyboardInterrupt:
      return ''
    if len(event) == 0:
      return ''
    resp = self.irc.recv(2048).decode('UTF-8')
    resp = self.remainder + resp
    self.remainder = ''
    if resp[-1] != '\n':
      self.remainder = '1'
    resp = resp.split('\n')
    for i, line in enumerate(resp):
      if len(line) == 0:
        del(resp[i])
      elif line[0:4] == 'PING' and (self.remainder != '1' or i+1 < len(resp)):
        self.send('PONG' + line[4:])
        del(resp[i])
    if self.remainder == '1' and len(resp) > 0:
      self.remainder = resp[-1]
      del(resp[-1])
    elif self.remainder == '1':
      self.remainder = ''
    if self.printinmsg:
      print('\n'+'\n'.join(resp))
    return '\n'.join(resp)

  def joinchan(self,chan):
    self.send('JOIN ' + chan)

