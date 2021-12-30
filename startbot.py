#! /usr/bin/env python3

import time
from shadowirc import IRCHandler
from bot import ShadowThread

thread = None

with open('pass') as infile:
  lines = infile.readlines()
  username = lines[0].strip()
  userpass = lines[1].strip()
  print('Connecting as user ' + username)
  thread = ShadowThread(IRCHandler( server='irc.libera.chat',
                                    port=6667,
                                    botnick=username,
                                    botpass=userpass
                                  )
                       )


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

print('')
while True:
  print('This bot\'s nick = \'' + thread.irc.username + '\'')
  print('The Lamb bot\'s nick = \'' + thread.lambbot + '\'')
  print('Current function = \'' + str(thread.doloop) + '\'',end='\n\n')
  print('Menu:')
  print('1) Set Lamb bot nick')
  print('2) List available functions')
  print('3) Set Lamb bot function')
  print('4) Clear Lamb bot function')
  print('5) Join a channel')
  print('6) Send a message from the bot')
  print('7) Allow thread to finish its current task, normally exit and quit')
  print('8) Immediately abort thread and quit')
  print('9) Hide this menu')
  resp = input('Enter your selection: ')
  print('')
  if resp == '1':
    newnick = input('Enter the lamb bot nick: ')
    thread.lambbot = newnick
  elif resp == '2':
    print('Available functions are: ' + ', '.join(availfuncs))
  elif resp == '3':
    newfunc = input('Enter the function to do: ')
    if newfunc in availfuncs:
      thread.doloop = newfunc
    else:
      print('Invalid function')
      print('Available functions are: ' + ', '.join(availfuncs))
  elif resp == '4':
    thread.doloop = None
  elif resp == '5':
    chan = input('Enter the channel name to join: ')
    thread.irc.joinchan(chan)
  elif resp == '6':
    recipient = input('Enter the recipient of the message: ')
    msg = input('Enter the message: ')
    thread.irc.privmsg(recipient,msg)
  elif resp == '7':
    thread.doloop = None
    thread.doquit = True
    print('Sending quit, joining thread . . .')
    thread.th.join()
    print('Goodbye')
    break
  elif resp == '8':
    thread.doloop = None
    thread.doquit = True
    print('Waiting five seconds to see if the thread may terminate . . .')
    time.sleep(5)
    print('Goodbye')
    break
  elif resp == '9':
    input('Press the enter key to show menu . . .\n')
  else:
    time.sleep(1)
  print('')

