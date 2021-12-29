#! /usr/bin/env python3

import time
from shadowirc import IRCHandler
from bot import ShadowThread

irc = None

with open('pass') as infile:
  lines = infile.readlines()
  username = lines[0].strip()
  userpass = lines[1].strip()
  print('Connecting as user ' + username)
  irc = IRCHandler( server='irc.libera.chat',
                    port=6667,
                    botnick=username,
                    botpass=userpass)

thread = ShadowThread(irc)

availfuncs = []
for func in dir(thread):
  if func.startswith('_'):
    pass
  elif not callable(getattr(thread,func)):
    pass
  # 'private' functions
  elif func == 'awaitresponse' or func == 'cityrank' \
      or func == 'walkpath' or func == 'gotoloc' or func == 'printloop':
    pass
  else:
    availfuncs.append(func)

while True:
  print('Lamb bot nick = \'' + thread.lambbot + '\'')
  print('Current function = \'' + str(thread.doloop) + '\'',end='\n\n')
  print('Menu:')
  print('0) Join a channel')
  print('1) Set Lamb bot nick')
  print('2) Set Lamb bot function')
  print('3) List available functions')
  print('4) Send a message from the bot')
  print('5) Immediately abort thread and quit')
  print('6) Allow thread to normally exit and quit')
  resp = input('Enter your selection: ')
  print('')
  if resp == '0':
    chan = input('Enter the channel name to join: ')
    thread.irc.joinchan(chan)
  elif resp == '1':
    newnick = input('Enter the lamb bot nick: ')
    thread.lambbot = newnick
  elif resp == '2':
    newfunc = input('Enter the function to do: ')
    if newfunc in availfuncs:
      thread.doloop = newfunc
    else:
      print('Invalid function')
      print('Available functions are: ' + ', '.join(availfuncs))
  elif resp == '3':
    print('Available functions are: ' + ', '.join(availfuncs))
  elif resp == '4':
    recipient = input('Enter the recipient of the message: ')
    msg = input('Enter the message: ')
    irc.privmsg(recipient,msg)
  elif resp == '5':
    thread.doloop = None
    thread.doquit = True
    print('Sending quit, joining thread . . .')
    thread.th.join()
    print('Goodbye')
    break
  elif resp == '6':
    print('This function is not implemented yet, try ctrl-c')
  else:
    time.sleep(1)
  print('')

