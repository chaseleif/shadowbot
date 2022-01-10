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
#  bot.py
#  This is a bot to automate interactions with the ShadowLamb bot
##
#  Author: Chase LP
###

import re, time, threading

# entermsg is a dict keyed on locations with entrance messages as values
entermsg = {'Redmond':'You arrive at Redmond',
            'Redmond_Hotel':'You enter the Redmond Hotel',
            ################ The OrkHQ, for getting bacon
            'Redmond_OrkHQ':'You enter the ork headquarters',
            'OrkHQ_StorageRoom':'You continue inside OrkHQ_StorageRoom',
            # Confirmed exit messages the same for:
            # Redmond_OrkHQ, Redmond_Hideout, Seattle_Renraku,
            # Seattle_Forest, Seattle_Harbor, Delaware_Nysoft,
            # Delaware_Prison
            'Exit':'You can return to this location',
            # '#travel 1' moves to the right, 2 to left, (unless in redmond)
            # Chicago <-> Delaware <-> Seattle <-> Redmond
            'Subway':'You enter the Subway',
           }

''' class ShadowThread
    Attributes
    th            - threading object, the thread which performs the printloop function
    doloop        - None or a string, indicating which method to do inside printloop
    doquit        - boolean, indicates whether the thread should exit
    irc           - reference to an IRCHandler class, wraps the irc connection
    lambbot       - string, the nick of the Shadow Lamb bot we will talk to
    meetsay       - None or a string, what we will say upon "You meet ..." messages
    invstop       - The stop position for considering items to sell / push to bank
    lambmsg       - An re object to test for and get messages from the Lamb bot
    bumsleft      - A counter of bums needed to kill for the 'Bummer' quest
    precmds       - A list of commands to run before entering a loop function

    Internal Methods
    getlambmsg    - Returns a string, the stripped message from the Lamb bot (or empty if not a Lamb msg)
    awaitresponse - Awaits a specific response from the Lamb bot, returns the string response
    handlecombat  - Called when in combat, returns when combat is over
    cityrank      - Returns an ordinal value for cities, used for subway travel
    walkpath      - Issues "goto" commands for all locations within a list to walk a path
    gotoloc       - Travels to a destination location
    printloop     - The thread function, calls method specified by doloop, loop is quit for exceptions
    invflush      - This method flushes inventory up to a point

    Doloop Methods
    getbacon      - Goes to the OrkHQ, then repeatedly kills FatOrk to get bacon
    explore       - Explores the current city on a loop
'''
class ShadowThread():
  th          = None    # A reference to the running thread
  doloop      = None    # None, or a string with the name of the loop function to do
  softquit    = False   # A flag to tell the thread to quit 'soon'
  doquit      = False   # A flag to tell the thread to quit
  irc         = None    # A reference to the IRC handler class with the current connection
  lambbot     = ''      # The nick of the Lamb bot we will be talking to
  meetsay     = None    # None, or a string we will say when we 'meet' civilians
  invstop     = 0       # Inventory stop position for selling and getting rid of inventory
  lambmsg     = None    # a compiled re to test for / retrieve lamb messages
  bumsleft    = 0       # Number of bums left to kill
  precmds     = []      # List of commands to run when beginning doloop()

  ''' init
      Assign the lambbot, the irc socket class, and start the thread
  '''
  def __init__(self, irc, lambbot='Lamb3'):
    self.irc = irc
    self.lambbot = lambbot
    self.lambmsg = re.compile('[:]?'+self.lambbot+'[\S]* PRIVMSG '+self.irc.username+' :')
    self.th = threading.Thread(target=self.printloop, daemon=True)
    self.th.start()

  ''' del
      Set quit flags and join the thread
  '''
  def __del__(self):
    self.doquit = True
    self.func = None
    self.th.join()

  ''' getlambmsg
      Returns the text content of the message from the Lamb bot
      Returns an empty string if the msg is not from the Lamb bot

      Parameters
      msg         - string, the full message line
                    * This should be a valid message from the Lamb bot
  '''
  def getlambmsg(self, msg):
    if self.lambmsg.match(msg) is None:
      return ''
    msg = msg[self.lambmsg.match(msg).span()[1]:].strip()
    if msg[-1] == '.':
      msg = msg[:-1]
    return msg

  ''' sleepreceive
      A receptive sleep, where we continue to accept PING messages
      Will likely 'sleep' for a slightly longer than requested

      Parameters
      duration    - integer, time to 'sleep' for
  '''
  def sleepreceive(self, duration=30):
    print(' ~ sleepreceive')
    while duration > 0:
      # The user wants to quit, get back to the loop function
      if self.doquit:
        raise Exception('Player quit')
      print(' ~ About ' + str(duration) + 's remaining')
      starttime = time.time()
      if duration < 30:
        self.irc.get_response()
      else:
        self.irc.get_response(timeout=duration)
      duration -= int(time.time() - starttime)

  ''' awaitresponse
      Returns the string with the line containing the quitmsg parameter

      Parameters
      quitmsg     - string, this is the string we are waiting to receive
      eta         - integer, this is an optional parameter used to print
                     periodic approximate time remaining messages
  '''
  def awaitresponse(self, quitmsg, eta=-1):
    print(' ~ Awaiting response: '+str(quitmsg))
    # Repeat until we see the quitmsg parameter
    while True:
      # If there is an ETA, print an approximate time remaining
      if eta > 0:
        print(' ~ ' + time.asctime())
        # ETA currently used only for subway travel
        # If the ETA becomes too negative then there may be some issue
        if eta-time.time() < -60:
          print(' ~ We are a minute past the ETA ... returning from awaitresponse ... !!!')
          return ''
        # print the ETA
        print(' ~ About '+str(int(eta-time.time()))+'s remaining')
      # Get text from irc, set the timeout to 2 minutes
      response = self.irc.get_response(timeout=120)
      # The user wants to quit, get back to the loop function
      if self.doquit:
        raise Exception('Player quit')
      line = self.getlambmsg(response)
      if line == '':
        continue
      # We have seen our quit msg, return the line
      if quitmsg in line:
        return response
      # We meet a citizen or another player
      # This will occur when we are walking within cities
      elif 'You meet ' in line:
        # We need to kill more bums
        # 'You meet 1-Bum[7852502](-7.5m)(L5(6))[H]'
        # 'You meet 1-Bum[7852511](-7.5m)(L5(6))[H], 2-Bum[7852512](-7.5m)(L5(6))[H]'
        # I have seen bums walking with other NPCs (Police Officers?)
        if self.bumsleft > 0 and 'Bum' in line:
          # Ensure there are only bums and get a count of them
          parts = line.split(', ')
          bumcount = 0
          for part in line.split(', '):
            if 'Bum' in part:
              bumcount += 1
            else:
              bumcount = self.bumsleft + 1
              break
          # Don't kill more bums than needed or other NPC types
          if bumcount <= self.bumsleft:
            self.irc.privmsg(self.lambbot, '#fight')
            response = self.awaitresponse('You ENCOUNTER')
            response = self.handlecombat(response)
            self.bumsleft -= bumcount
            continue
        # If we have a message set to say
        if self.meetsay is not None:
          # Say the message and get their reply
          self.irc.privmsg(self.lambbot, '#say ' + self.meetsay)
          # Give a moment of time for a response . . .
          self.sleepreceive()
        # Say bye to them, this will close an interation with a citizen
        self.irc.privmsg(self.lambbot, '#bye')
      # Starting combat
      elif 'You ENCOUNTER ' in line:
        # We get a new list from the handle combat function
        response = self.handlecombat(response)
      # You gained some MP
      elif 'You gained +' in line:
        pass
      # Yes, we are going somewhere . . .
      elif 'You are going to' in line:
        pass
      # Someone has cast a spell
      elif 'casts a level' in line:
        pass
      # This is the response from #status
      # male darkelve L59(101). HP :58.5/72.6, MP :135.38/135.38, Atk :132.2, Def :9.2, Dmg :15.6-37.2, Arm (M/F):2.5/1.9, XP :25.87, Karma :18, $ :17340.23, Weight :48.16kg/42.62kg
      elif 'male' in line and 'P ' in line and ' Karma ' in line and ' Weight ' in line:
        pass
      # This is an unhandled message type
      else:
        print(' ~ unhandled: \"'+line+'\"')

  ''' handlecombat
      Combat handler, returns when combat is complete
      * This currently requires the calm spell for healing *
      Any special combat actions go here

      Parameters
      msg         - string, the current message buffer
                    Must contain the line 'You ENCOUNTER' or 'are fighting'

      Returns
      msg         - string, the current message buffer
                    Will be the line 'You continue'
  '''
  def handlecombat(self, msg=''):
    class ShadowEnemy():
      name = ''
      distance = 0
      level = 0
      def __init__(self,nm,dist,lev):
        self.name = nm
        self.distance = dist
        self.level = lev

    line = self.getlambmsg(msg)
    if 'You ENCOUNTER' in line:
      line = line[14:]
    else: # 'You are fighting against' in line:
      line = '.'.join(line.split('.')[:-2])[25:]
    parts = line.split(', ')

    enemies = {}
    havetarget = None
    for part in parts:
      num = int(part.split('-')[0].strip())
      name = part.split('-')[1].split('[')[0]
      dist = float(part.split('(')[1][:-2])
      lvl = int(part.split('(')[2][1:].split(')')[0])
      enemies[num] = ShadowEnemy(name,dist,lvl)
      print(' ~ Enemy '+str(num)+') '+name+', L'+str(lvl)+', at '+str(dist)+'m')
      if 'Drone' in name:
        if havetarget is None or dist > enemies[havetarget].distance:
          # Save the current target as the index of enemies[]
          havetarget = num

    if havetarget is None:
      lowlevel = 9999
      for enemy in enemies:
        if enemies[enemy].level < lowlevel:
          lowlevel = enemies[enemy].level
          havetarget = enemy
        # More 'negative' distance enemies are farther away
        # *Could track our distance for future selections*
        elif enemies[enemy].level == lowlevel \
          and enemies[enemy].distance > enemies[havetarget].distance:
          havetarget = enemy

    # shouldn't be None
    if havetarget is not None and len(enemies) > 1:
      print(' ~ Target is '+str(havetarget))
      self.irc.privmsg(self.lambbot, '#attack ' + str(havetarget))

    calmcasttime = 0
    calmcastgap = 90

    enemyattack = re.compile('[\d]+-[a-zA-Z]+\[[\d]+\]')

    while True:
      msg = self.irc.get_response(timeout=45)
      line = self.getlambmsg(msg)
      if 'You continue' in line:
        break
      # ignoring msgs -> misses, loots, casts, moves, uses, loads, gain MP
      # ('caused damage' contains 'used')
      elif 'misses' in line or 'received' in line or 'gained' in line \
          or 'casts' in line or 'moves' in line or 'loads' in line \
          or ' used ' in line:
        pass
      # Combat
      elif 'attacks' in line:
        if line[re.search('[\d]+-',line).span()[1]:].startswith(self.irc.username):
          # We killed an enemy
          if 'killed them' in line:
            num = int(line.split('attacks ')[1].split('-')[0].strip())
            # If we didn't fill out the enemies dict
            if num not in enemies:
              continue
            del(enemies[num])
            # finished this combat, the top of the outer while will quit
            if len(enemies) == 0:
              continue
            if len(enemies) > 1:
              havetarget = None
              for enemy in enemies:
                if 'Drone' in enemies[enemy].name:
                  havetarget = enemy
                  break
              if havetarget is None:
                lowlevel = 9999
                for enemy in enemies:
                  if enemies[enemy].level < lowlevel:
                    lowlevel = enemies[enemy].level
                    havetarget = enemy
              if havetarget is not None:
                self.irc.privmsg(self.lambbot, '#attack ' + str(havetarget))
        # An enemy attacked
        elif enemyattack.match(line) is not None:
          # uh oh
          if 'killed' in line:
            raise Exception('Player died')
          player = line.split('-')[1].split(' ')[-1]
          # "68.7/72.6"
          health = line.split(', ')[1].split('HP')[0]
          numerator = health.split('/')[0]
          denominator = health.split('/')[1]
          doheal = False
          docalm = False
          health = float(numerator)/float(denominator)
          # Less than 30% health
          if health < 0.3:
            doheal = True
          # Less than 50% health
          elif health < 0.5:
            docalm = True
          # Less than 80% health
          elif health < 0.8 and (time.time() - calmcasttime) > calmcastgap:
            docalm = True
          if doheal:
            self.irc.privmsg(self.lambbot, '#cast heal ' + player)
          elif docalm:
            self.irc.privmsg(self.lambbot, '#cast calm ' + player)
            calmcasttime = time.time()
    # return line ending combat
    return msg

  ''' cityrank
      Returns an ordering, this is used to determine direction of subway travel

      Parameters
      city        - A string with a city name: Chicago, Delaware, Seattle, Redmond
  '''
  def cityrank(self,city):
    if city=='Chicago': return 4
    if city=='Delaware': return 3
    if city=='Seattle': return 2
    return 1

  ''' walkpath
      Returns upon arrival of last entry in the list

      Parameters
      path        - list, a list of strings, each a destination to "goto"
  '''
  def walkpath(self,path):
    print(' ~ Entering walkpath, path = '+str(path))
    # For each waypoint in the list of waypoints
    for point in path:
      print(' ~ Point = ' + point)
      # goto the waypoint
      self.irc.privmsg(self.lambbot, '#goto ' + point)
      # await the entrance message for this waypoint
      self.awaitresponse(entermsg[point])
      # The user wants to quit, get back to the loop function
      if self.doquit:
        raise Exception('Player quit')

  ''' gotoloc
      Handles getting to some starting point for a message loop.

      Parameters
      location    - string, the destination location, form of 'Redmond_Hotel'
                    * the destination location should not be within a dungeon
                    * the origin must be in the world (not in a dungeon)

      Returns       
                    When travel is complete, player is at the destination
  '''
  def gotoloc(self,location):
    # No current location
    currloc = ''
    # Limit repeated "#party" messages
    onsubway = False
    while currloc == '':
      # Find out where we are at
      self.irc.privmsg(self.lambbot, '#party')
      # You are {inside,outside,fighting,exploring,going}
      # leave whatever location we are in, or enter if it is right
      while True:
        resp = self.irc.get_response()
        line = self.getlambmsg(resp)
        # We are inside or outside of a location
        if line.startswith('You are inside') or line.startswith('You are outside'):
          if 'outside' in line:
            self.irc.privmsg(self.lambbot, '#enter')
            self.irc.get_response()
          # If this location is the destination then return
          if location in line:
            return
          # The location is the last word in the line
          currloc = line.split(' ')[-1]
          break
        # We are in combat
        elif line.startswith('You are fighting'):
          onsubway = False
          resp = handlecombat(resp)
        # We are exploring, or going to a location, try to stop
        elif line.startswith('You are'):
          # If onsubway then we *just* tried to stop, and didn't
          if onsubway:
            # This should be a subway journey, which we cannot stop
            # Find out the remaining time for this travel
            line = line.split('.')[1][1:]
            mins = 0
            secs = 0
            if line.split('m')[0].isdigit():
              mins = int(line.split('m')[0])
            if 's' in line:
              line = line.split('s')[0]
              if ' ' in line:
                line = line.split(' ')[1]
              secs = int(line)
            timeremaining = mins*60 + secs + 10
            print(' ~ It was detected that we are likely in a subway')
            print(' ~ (sleeping for >= ' + str(timeremaining) + 's)')
            self.sleepreceive(timeremaining)
          else:
            # Stop travelling
            self.irc.privmsg(self.lambbot, '#stop')
            self.irc.get_response()
            # set the onsubway flag in case we don't stop
            onsubway = True
          break
    # The city precedes the '_' in the locations
    dstcity = location.split('_')[0]
    srccity = currloc.split('_')[0]
    # We are in the same city as the destination, we can walk directly there now
    if dstcity == srccity:
      # Walkpath will finish when we have arrived at the destination
      return self.walkpath([location])
    # We are in a different city, let's get to and take the subway
    if 'Subway' not in currloc:
      # We aren't at the subway, walk to the subway
      self.walkpath(['Subway'])
    # We are now at the subway in a different city
    # For subway direction: Chicago <-> Delaware <-> Seattle <-> Redmond
    if srccity == 'Redmond' or self.cityrank(srccity) > self.cityrank(dstcity):
      self.irc.privmsg(self.lambbot, '#travel 1')
    else:
      self.irc.privmsg(self.lambbot, '#travel 2')
    # The optional 'eta' parameter to the await response function
    #  will occasionally print an approximate time remaining
    etamsg = self.getlambmsg(self.awaitresponse('ETA: '))
    eta = 0
    # We can calculate our travel time
    etamsg = etamsg[etamsg.find('ETA: ')+5:]
    # We will always have minutes
    parts = etamsg.split('m')
    mins = int(parts[0])
    secs = 0
    # We also have seconds
    if len(parts) > 1 and 's' in parts[1]:
      parts = parts[1].split('s')
      if parts[0][0] == ' ':
        secs = int(parts[0][1:])
    # Set the ETA as future from the current time
    eta = int(time.time() + mins * 60 + secs)
    # Await the response that we have arrived in the next city
    self.awaitresponse('You arrive',eta=eta)
    # Recursive call to continue travelling to the destination
    self.gotoloc(location)

  ''' printloop

      This is the working thread's target function
      This operates in a loop, quitting when self.doquit == True
      When self.doloop == a function name, that function is then called
      When a self.doloop function is being called, we check for quit after each call
      There are longer sleeps at each iteration if no function is set
  '''
  def printloop(self):
    # While the user hasn't chosen to quit
    while not self.doquit and not self.softquit:
      # Get the current function in self.doloop
      # This value will be set to a string, but could be None, so must be cast
      func = str(self.doloop)
      # If we did not get a string representation of None
      if func != 'None':
        # Set the function counter to zero
        fncounter = 0
        # While the user has not selected to quit and the function has not changed
        while not self.doquit and func == str(self.doloop):
          # Call the selected function and pass the iteration counter
          starttime = time.time()
          print(' ~  ~~~~~~~~~~')
          print(' ~ { ' + time.asctime())
          print(' ~ { Beginning iteration ' + str(fncounter) + ' of ' + func)
          print(' ~  ~~~~~~~~~~')
          try:
            for cmd in self.precmds:
              self.irc.privmsg(self.lambbot, cmd)
              self.irc.get_response()
            getattr(self,func)(fncounter)
          except Exception as e:
            self.doloop = None
            if str(e) == 'Player quit':
              print(' ~ Quitting . . .')
              break
            if str(e) == 'Player died':
              print(' ~ The player has died')
              break
            elapsed = int(time.time()-starttime)
            msg = '*****\n'
            msg += ' ***\n'
            msg += ' ***  ' + time.asctime() +'\n'
            msg += ' ***  Exception in loop function ' + func + '\n'
            msg += ' ***  Exception: ' + str(e) + '\n'
            msg += ' ***  Exception at %d:%02d\n' % (elapsed//60,elapsed%60)
            msg += ' ***\n'
            msg += '*****\n'
            print(msg, end='')
            with open('exceptions','a') as outfile:
              outfile.write(msg)
          elapsed = int(time.time()-starttime)
          print(' ~  ~~~~~~~~~~')
          print(' ~ { ' + time.asctime())
          print(' ~ { Finished iteration ' + str(fncounter) + ' of ' + func)
          print(' ~ {   in %d:%02d' %  (elapsed//60,elapsed%60))
          print(' ~  ~~~~~~~~~~')
          # Increase the iteration counter
          fncounter+=1
          # Short sleep
          self.irc.get_response(timeout=5)
      else:
        # There was no function, need to continually check for PING messages
        # The get_response function has a timeout
        self.irc.get_response(timeout=30)

  ''' invflush
      If self.invstop is positive, this function {sells,pushes,drops} all items including that number
      This function should be called outside of travel, etc.
      An ideal place for this function would be before a loop function exits
  '''
  def invflush(self, cmd='#drop'):
    if self.invstop == 0:
      return
    self.irc.privmsg(self.lambbot, '#inventory')
    numpages = self.getlambmsg(self.awaitresponse('Your Inventory'))
    numpages = int(numpages.split(':')[0].split('/')[1])
    haveqty = re.compile('\([\d]+\)')
    numitems = 0
    while True:
      self.irc.privmsg(self.lambbot, '#inventory ' + str(numpages))
      numpages -= 1
      numitems = self.getlambmsg(self.awaitresponse('Your Inventory'))
      items = numitems.split(', ')
      numitems = items[len(items)-1].split('-')[0].strip()
      # If there is only one item on this inventory page's list it will be different
      if numitems.startswith('page'):
        numitems = numitems.split(': ')[1]
      numitems = int(numitems)
      pos = len(items)-1
      self.irc.get_response()
      while pos > 0:
        if numitems < self.invstop:
          break
        if haveqty.search(items[pos]):
          qty = items[pos][haveqty.search(items[pos]).span()[0]:]
          qty = re.sub('[()]','',qty)
          self.irc.privmsg(self.lambbot, cmd + ' ' + str(numitems) + ' ' + qty)
        else:
          self.irc.privmsg(self.lambbot, cmd + ' ' + str(numitems))
        # including a get_response to slow messages
        self.irc.get_response()
        numitems -= 1
        pos -= 1
      if numitems < self.invstop:
        break

  ''' getbacon
      This function goes to the OrkHQ_StorageRoom to battle the FatOrk
      There is some chance that the FatOrk will drop a bacon
      We must exit and re-enter the OrkHQ each time we kill the FatOrk

      Parameters
      fncounter   - Used to vary action depending on each Nth function call
                    On the first function call we go to Redmond_OrkHQ
                    On subsequent calls we are already at the Redmond_OrkHQ
  '''
  def getbacon(self, fncounter=0):
    # Get to the OrkHQ
    if fncounter < 1:
      self.gotoloc('Redmond_OrkHQ')
    else:
      # We are at the OrkHQ, enter the OrkHQ
      self.irc.privmsg(self.lambbot, '#enter')
      # Await the entrance message
      self.awaitresponse(entermsg['Redmond_OrkHQ'])
    # Go to the storage room, will fight the FatOrk on entrance, then go to the exit
    self.walkpath(['OrkHQ_StorageRoom','Exit'])
    # Leave the OrkHQ
    self.irc.privmsg(self.lambbot, '#leave')
    self.awaitresponse(entermsg['Redmond'])

  ''' explore
      This function simply explores the players current city in a loop.
      This uses the teleport spell to shed inventory
      This can be used to grind for xp
       to search for citizens to #say things to
        find locations
       *This can also be used to test the handlecombat method*

      Need to handle the subway case when fncounter==0
        'The command is not available for your current'
      Otherwise, don't call this while on a subway . . .
  '''
  def explore(self, fncounter=0):
    # Ensure we are stopped
    if fncounter < 1:
      '''
      Need to improve / perfect a "stop" procedure
      A stop needs to handle when we are actually in combat,
        when we are travelling in a subway,
        etc . . .
      '''
      self.irc.privmsg(self.lambbot, '#stop')
      stopped = False
      while not stopped:
        response = self.irc.get_response()
        line = self.getlambmsg(response)
        if 'What now?' in line:
          stopped = True
          break
        if not stopped:
          self.irc.privmsg(self.lambbot, '#party')
          response = self.awaitresponse('You are')
          line = self.getlambmsg(response)
          if 'You are outside' in line or 'You are inside' in line:
            stopped = True
          elif 'You are fighting' in line:
            self.handlecombat(response)
            self.irc.privmsg(self.lambbot, '#stop')
          else:
            self.sleepreceive()
            self.irc.privmsg(self.lambbot, '#stop')
    self.irc.privmsg(self.lambbot, '#explore')
    # Not sure if this is the right response if not all locations discovered yet.
    self.awaitresponse('explored')
    if self.invstop > 0:
      self.irc.privmsg(self.lambbot, '#cast teleportii redmond_secondhand')
      self.awaitresponse('now outside of')
      self.irc.privmsg(self.lambbot, '#enter')
      self.awaitresponse('You enter the')
      self.invflush('#sell')
      self.irc.get_response()
      self.irc.privmsg(self.lambbot, '#cast teleport bank')
      self.awaitresponse('now outside of')
      self.irc.privmsg(self.lambbot, '#enter')
      self.awaitresponse('In a bank')
      self.invflush('#push')
      self.irc.get_response()
    self.irc.privmsg(self.lambbot, '#cast teleport hotel')
    self.awaitresponse('now outside of')
    self.irc.privmsg(self.lambbot, '#enter')
    self.awaitresponse('You enter')
    self.irc.privmsg(self.lambbot, '#sleep')
    self.awaitresponse('ready to go')
    self.irc.privmsg(self.lambbot, '#cast teleportii chicago_hotel')
    self.irc.get_response()

