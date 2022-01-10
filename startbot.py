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
#  startbot.py
#  This is a driver script for shadowirc.py and bot.py
##
#  Author: Chase LP
###

import time
from irchandler import IRCHandler
from bot import ShadowThread

# The ShadowThread object we will interact with
thread = None

# Read the user/pass, connect to irc, instantiate the thread object
with open('pass') as infile:
  lines = infile.readlines()
  # The username is by itself on the first line
  username = lines[0].strip()
  # The password is by itself on the second line
  userpass = lines[1].strip()
  # Connect to irc with the IRCHandler
  # The IRCHandler object is given to the ShadowThread constructor
  print('| Connecting as user ' + username)
  thread = ShadowThread(IRCHandler( server='irc.libera.chat',
                                    port=6667,
                                    botnick=username,
                                    botpass=userpass
                                  )
                       )

# These are methods of the ShadowThread object that are for internal use only
# These methods should not be called in the printloop method
unavailfuncs = ['islambmsg',
                'getlambmsg',
                'sleepreceive',
                'awaitresponse',
                'cityrank',
                'walkpath',
                'gotoloc',
                'printloop',
                'handlecombat',
                'invflush',
               ]

# Get a list of available functions
# This is used for printing available functions
#  and confirming that a valid function is selected (when changed)
availfuncs = []
# Go through the dir() of the ShadowThread object
for func in dir(thread):
  # Don't take any attribute or method that begins with an underscore
  if func.startswith('_'):
    pass
  # Only take methods that can be called
  elif not callable(getattr(thread,func)):
    pass
  # These methods are for internal use only
  elif func in unavailfuncs:
    pass
  # This is a user-defined method for the printloop method
  else:
    availfuncs.append(func)

# The previous recipient of a private message from this bot
# Used to ease sending repeated manual messages to some nick
lastrecipient = ''

def botcmdmenu():
  while True:
    print(' ___')
    print('| These commands will be ran before the function loop starts')
    print('| Ensure these are valid commands, e.g., \"#cast berzerk\"')
    print('| Current commands: ' +str(thread.precmds))
    print('| 1) Add a command')
    if len(thread.precmds) > 0:
      print('| 2) Remove a command')
      print('| 3) Clear commands')
    print('| 0) Return to bot menu')
    response = input('| Enter your selection: ')
    if response == '1':
      newcmd = input('| Enter a new command: ')
      if newcmd != '':
        thread.precmds.append(newcmd)
    elif len(thread.precmds) > 0 and response == '2':
      delcmd = input('| Enter the command to remove: ')
      try:
        thread.precmds.remove(delcmd)
      except Exception as e:
        print('| Exception: ' + str(e))
    elif len(thread.precmds) > 0 and response == '3':
      thread.precmds = []
    elif response == '0':
      break
    else:
      time.sleep(1)

def botmenu():
  while True:
    print(' ___')
    print('| Bot (' + thread.irc.username + ') Configuration:')
    print('| 1) Set the Lamb bot nick (' + thread.lambbot + ')')
    print('| 2) Set word to say on \'Meet\' events (' + str(thread.meetsay) + ')')
    print('| 3) Set the stop value for selling / pushing items to bank (' + str(thread.invstop) +')')
    print('| 4) Set number of bums needed to kill (' + str(thread.bumsleft) +')')
    print('| 5) Change the function loop (' + str(thread.doloop) + ')')
    print('| 6) Set command list to run before function loop')
    if thread.doloop is not None:
      print('| 9) Clear current function loop')
    print('| 0) Return to the main menu')
    response = input('| Enter your selection: ')
    if response == '1':
      newnick = input('| Enter the Lamb bot\'s nick: ')
      thread.lambbot = newnick
    elif response == '2':
      newword = input('| Enter what the bot says on meet: ')
      thread.meetsay = newword
    elif response == '3':
      print('| Currently the stop value is ' + str(thread.invstop))
      print('| Less than 1 indicates to not shed inventory')
      print('| A positive value indicates the highest number of inventory to sell')
      newval = input('| Enter the inventory stop position: ')
      try:
        newval = int(newval)
        if newval < 0:
          newval = 0
        thread.invstop = newval
      except Exception as e:
        print('| Exception: ' + str(e))
    elif response == '4':
      print(' ___')
      print('| Currently need to kill ' + str(thread.bumsleft) + ' more bum',end='')
      if thread.bumsleft != 1: print('s',end='')
      newval = input('\n| Enter the number of bums to kill: ')
      try:
        newval = int(newval)
        if newval < 0:
          newval = 0
        thread.bumsleft = newval
      except Exception as e:
        print('| Exception: ' + str(e))
    elif response == '5':
      print(' ___')
      print('| Bot function is ' + str(thread.doloop))
      print('| Available functions are ' + ', '.join(availfuncs))
      newfunc = input('| Enter a function name: ')
      if newfunc in availfuncs:
        thread.doloop = newfunc
      else:
        print('| Invalid function name')
    elif response == '6':
      botcmdmenu()
    elif response == '9' and thread.doloop is not None:
      thread.doloop = None
    elif response == '0':
      break
    else:
      time.sleep(1)

def ircmenu():
  global lastrecipient
  while True:
    print(' ___')
    print('| IRC Commands:')
    print('| 1) Join a channel')
    print('| 2) Send a message to a nick or channel')
    print('| 3) Send a message to ' + thread.lambbot)
    if lastrecipient != '':
      print('| 4) Send a message to ' + lastrecipient)
    print('| 0) Return to the main menu')
    response = input('| Enter your selection: ')
    if response == '1':
      chan = input('| Enter the channel name to join: ')
      thread.irc.joinchan(chan)
    elif response == '2':
      recipient = input('| Enter the recipient: ')
      if recipient != thread.lambbot:
        lastrecipient = recipient
      msg = input('| Enter the message: ')
      thread.irc.privmsg(recipient, msg, delay=0)
    elif response == '3':
      msg = input('| Enter the message: ')
      thread.irc.privmsg(thread.lambbot, msg, delay=0)
    elif response == '4' and lastrecipient != '':
      msg = input('| Enter the message: ')
      thread.irc.privmsg(lastrecipient, msg, delay=0)
    elif response == '0':
      break
    else:
      time.sleep(1)

def mainmenu():
  while True:
    print(' ___')
    print('| Main Menu:')
    print('| 1) Bot configuration')
    print('| 2) IRC commands')
    print('| 3) Quit')
    print('| 4) Hide menu')
    response = input('| Enter your selection: ')
    if response == '1':
      botmenu()
    elif response == '2':
      ircmenu()
    elif response == '3':
      print(' ___')
      print('| Quit')
      print('| 1) Allow thread to finish its current activity before exit')
      print('| 2) More immediately abort thread and quit')
      print('| (anything else to cancel)')
      response = input('| Enter your selection: ')
      if response == '1':
        thread.doloop = None
        thread.softquit = True
        print('| Finishing current activity, joining thread . . .')
        thread.th.join()
        print('| Goodbye')
        break
      if response == '2':
        print('| Aborting current activity, joining thread . . .')
        thread.doloop = None
        thread.doquit = True
        #time.sleep(2)
        thread.th.join()
        print('| Goodbye')
        break
    elif response == '4':
      print(' ___')
      input('| Hiding menu until the enter key is pressed . . .\n')
    else:
      time.sleep(1)

print('\n _____\n| shadowbot  Copyright (C) 2022  Chase Phelps\n' + \
      '| This program comes with ABSOLUTELY NO WARRANTY.\n' + \
      '| This is free software, and you are welcome to redistribute it under certain conditions\n _____')

# Begin the driver loop
mainmenu()

