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
from sys import exc_info
from traceback import format_exception

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
    escortnick    - The nick of the person we're escorting
    badcmds       - A list of commands we will not do during escort
    cancast       - Boolean indicating whether we can cast tele/calm/heal
    attacklow     - Boolean indicating whether to attack high or low levels

    Internal Methods
    getlambmsg    - Returns a string, the stripped message from the Lamb bot (or empty if not a Lamb msg)
    sleepreceive  - 'Sleeps' for ~ a duration, responding to IRC messages
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
  doloop      = None    # None, or a string with the name of the loop function to do
  softquit    = False   # A flag to tell the thread to quit 'soon'
  doquit      = False   # A flag to tell the thread to quit
  meetsay     = None    # None, or a string we will say when we 'meet' civilians
  invstop     = 0       # Inventory stop position for selling and getting rid of inventory
  lambmsg     = None    # a compiled re to test for / retrieve lamb messages
  bumsleft    = 0       # Number of bums left to kill
  precmds     = []      # List of commands to run when beginning doloop()
  escortnick  = ''      # The nick of the person we're escorting
  badcmds     = []      # List of commands not to do during escort loop
  cancast     = True    # Whether we can cast teleport/calm/heal
  escortcasts = False   # Whether our escort can cast spells
  attacklow   = True    # Default is to prioritize quicker kills during fight
  colors      = True    # Print color messages, init will toggle to false
  incombat    = False   # Whether we're in the handlecombat method

  ''' init
      Assign the lambbot, the irc socket class, and start the thread
  '''
  def __init__(self, irc, lambbot='Lamb3_1'):
    # Escort restricted commands
    self.badcmds = [
            '#unequip','#uq', # Unequip item
            '#swap','#sw',    # Swapping items could interfere with shedinv()
            '#l','#lvlup',    # Use karma to lvlup traits
            '#reset',         # Delete the player
            '#aslset',        # Change asl
            '#rm',           '#running_mode',
            '#gi','#gy',      # (give item/money)
            '#give','#giveny',
            '#dr',           '#drop',
            '#mo',           '#mount',
            '#sh',           '#shout',
            '#w',            '#whisper',
            '#cm',           '#clan_message',
            '#pm',           '#party_message',
            '#ban',          '#unban',
                   ]
    # Set money and XP earned to zero
    self.lootmoney = 0
    self.lootxp = 0
    # Toggle colors to set the print function
    self.togglecolors()
    # The IRCHandler
    self.irc = irc
    # We will handle incoming messages and whether to print them
    # ( by default prints are enabled in IRCHandler )
    # NOTE:
    #  this will eat _all_ incoming messages that _we_ do not print
    self.irc.toggle_prints()
    # Set the lamb bot nick
    self.setlambbot(lambbot)
    # Fork a background thread to handle IRC
    self.th = threading.Thread(target=self.printloop, daemon=True)
    self.th.start()

  ''' del
      Set quit flags and join the thread
  '''
  def __del__(self):
    self.doquit = True
    self.func = None
    self.th.join()

  def colorprint(self, *args, **kwargs):
    s = ''.join([str(arg) for arg in args])
    # "... used Stimpatch ..." message is missing "seconds" from busy.
    if re.search(r'\. [0-9]+ busy$', s):
      s = s[:-4] + 'seconds busy'
    # Print messages that start with 'You' in bright blue
    if s.startswith('You'):
      bgcolor = '\033[38;5;98;1m'
      s = bgcolor+s
    # Put text in a lighter "aqua" (?) color
    else:
      bgcolor = '\033[36;1m'
      # prepend bgcolor only if it doesn't start with a name
      if re.search(r'([0-9]+-)?\S+[\[{][0-9]+[\]}]', s) is None or \
          re.search(r'([0-9]+-)?\S+[\[{][0-9]+[\]}]', s).span()[0] > 0:
        s = bgcolor + s
    # Remove leading number and level from friendly names as we go
    # Replace the player's nick with a bright green
    s = re.sub(r'([0-9]+-)?'+self.irc.username+r'{[0-9]+}',
                '\033[32;1m'+self.irc.username+bgcolor, s)
    # Replace escort player's nick with a duller green
    # TODO: we could have a larger party, track all party members' names
    if self.escortnick != '' and self.escortnick in s:
      s = re.sub(r'([0-9]+-)?'+self.escortnick+r'{[0-9]+}',
                '\033[38;5;35m'+self.escortnick+bgcolor,s)
    # If we're in combat mark other players red, otherwise a dimmer blue
    pcolor = '\033[38;5;1;1m' if self.incombat else '\033[38;5;98m'
    # Players may or may not have a leading position number
    # They will have square brackets with another number
    players = re.compile(r'([0-9]+-)?([\S]+)\[[0-9]+\]')
    # Get the player name for all matches
    players = list(set([player[1] for player in players.findall(s)]))
    # Sort names by the longest first, some names contain others
    # (GiantTroll contains Troll)
    players.sort(key=lambda s: len(s), reverse=True)
    # Eat any leading position and trailing chars up to delimiter
    if 'ENCOUNTER' in s or 'You meet' in s:
      for player in players:
        s = re.sub(r'([0-9]+-)?'+player+r'[^, ]+',
                    pcolor+player+bgcolor,s)
    else:
      for player in players:
        s = re.sub(r'([0-9]+-)?'+player+r'[^, .]+',
                    pcolor+player+bgcolor,s)
    # Mark fighting words in purple-ish
    for word in set(re.findall(r'(attacks|killed|damage)',s)):
      s = re.sub(word,'\033[38;5;5;1m'+word+bgcolor,s)
    # Mark combat non-hurt words in bright blue
    if self.incombat:
      # include leading space for 'used' since 'used' appears in 'caused'
      for word in set(re.findall(r'(moves|casts|loads| used|misses)',s)):
        s = re.sub(word,'\033[38;5;98;1m'+word+bgcolor,s)
    # Add color reset to s and do the print
    s += '\033[0m'
    print(s, **kwargs)

  def togglecolors(self):
    self.colors = not self.colors
    if not self.colors:
      self.print = print
    else:
      self.print = self.colorprint

  def setlambbot(self, lambbot):
    self.lambbot = lambbot
    self.lambmsg = re.compile('[:]?'+self.lambbot+r'[\S]* PRIVMSG '+self.irc.username+' :')

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
    msg = msg[self.lambmsg.match(msg).span()[1]:].strip().rstrip('.')
    return msg

  ''' sleepreceive
      A receptive sleep, where we continue to accept PING messages
      Will 'sleep' for about as long as requested

      Parameters
      duration    - integer, time to 'sleep' for
      earlyexit   - return if we receive something early
  '''
  def sleepreceive(self, earlyexit=False, duration=30):
    lastprint = 0
    while duration > 1:
      # The user wants to quit, get back to the loop function
      if self.doquit:
        raise Exception('Player quit')
      if time.time() - lastprint > 30:
        self.print(' ~ sleepreceive, about %.1f seconds remaining' % duration)
        lastprint = time.time()
      starttime = time.time()
      response = self.irc.get_response(timeout=duration)
      line = self.getlambmsg(response)
      if line != '': self.print(line)
      if earlyexit: break
      duration -= time.time() - starttime

  ''' awaitresponse
      Returns the string with the line containing the quitmsg parameter

      Parameters
      quitmsg     - string, this is the string we are waiting to receive
      eta         - integer, this is an optional parameter used to print
                     periodic approximate time remaining messages
  '''
  def awaitresponse(self, quitmsg, eta=-1):
    escortmsg = None
    if self.doloop == 'escort':
      escortmsg = re.compile('[:]?' + self.escortnick + \
                              r'[\S]* PRIVMSG '+self.irc.username+' :')
    self.print(' ~ Awaiting response: '+str(quitmsg))
    # Repeat until we see the quitmsg parameter
    while True:
      # If there is an ETA, print an approximate time remaining
      if eta > 0:
        self.print(' ~ ' + time.asctime())
        # ETA currently used only for subway travel
        # If the ETA becomes too negative then there may be some issue
        if eta-time.time() < -60:
          self.print(' ~ We are a minute past the ETA ... ' + \
                  'returning from awaitresponse ... !!!')
          return ''
        # print the ETA
        self.print(' ~ About '+str(int(eta-time.time()))+'s remaining')
      # Get text from irc, set the timeout to 2 minutes
      response = self.irc.get_response()
      # The user wants to quit, get back to the loop function
      if self.doquit:
        raise Exception('Player quit')
      # TODO: Should handle messages other than stop here (?)
      if escortmsg is not None and escortmsg.match(response) is not None:
        if 'stop' in response[escortmsg.match(response).span()[1]:].strip():
          raise Exception('Escorted player said to stop')
        continue
      # We will print the line at the bottom of this long conditional
      line = self.getlambmsg(response)
      # Not a lamb message, continue to skip printing a blank line
      if line == '':
        continue
      #if line.startwith('The command is not available'):
      #  continue
      # Our quit msg, return the line
      # We can handle exceptions in quit here
      if quitmsg in line: # and 'somethingbad' in line:
        self.print(line)
        return response
      if line.startswith('Use #talk'): continue
      if line.startswith('I don\'t want'): continue
      # someone said something
      if ' says: ' in line: pass
      # sold to the secondhand store clerk
      elif line.startswith('The salesman smiles'): continue
      # We meet a citizen or another player
      # This will occur when we are walking within cities
      elif 'You meet ' in line:
        # We need to kill more bums
        # You meet 1-Bum[7852502](-7.5m)(L5(6))[H]
        # You meet 1-Bum[7852511](-7.5m)(L5(6))[H], 2-Bum[7852512] ...
        # NOTE: I have seen bums walking with other NPCs (Police Officers?)
        if self.bumsleft > 0 and 'Bum' in line:
          # Ensure there are only bums and get a count of them
          bumcount = 0
          for part in line.split(', '):
            if 'Bum' in part:
              bumcount += 1
            else: # if this isn't a bum, set counter to be too high to skip
              bumcount = self.bumsleft + 1
              break
          # Don't kill more bums than needed (or other NPC types)
          if bumcount <= self.bumsleft:
            self.print(line)
            self.irc.privmsg(self.lambbot, '#fight')
            self.bumsleft -= bumcount
            continue
        # If we have a message set to say
        elif self.meetsay is not None and self.meetsay != '':
          self.print(line)
          # Say the message and get their reply
          self.irc.privmsg(self.lambbot, '#say ' + self.meetsay)
          continue
        # Say bye to them, this will close an interation with a citizen
        self.print(line)
        self.irc.privmsg(self.lambbot, '#bye')
        continue
      # Starting combat
      elif 'You ENCOUNTER ' in line:
        self.handlecombat(line)
        continue
      # You gained some MP
      elif line.startswith('You gained +'): pass
      # Yes, we are going somewhere . . .
      elif line.startswith('You are going to'): pass
      # Someone has cast a spell
      elif 'casts a level' in line: pass
      # This is the response from #status
      # male darkelve L59(101). HP :58.5/72.6, MP :135.38/135.38, Atk :132.2, Def :9.2, Dmg :15.6-37.2, Arm (M/F):2.5/1.9, XP :25.87, Karma :18, $ :17340.23, Weight :48.16kg/42.62kg
      elif 'male' in line and ' Karma ' in line and ' Weight ' in line: pass
      # You sold 1 of your DarkBow for 56.63$. You now carry 25.85kg/45.19kg
      elif line.startswith('You sold'): pass
      # You put 1 of your ID4Card into your bank account. You now carry 25.22kg/45.19kg
      elif line.startswith('You put'): pass
      # You pay 79.29 nuyen
      elif line.startswith('You pay'): pass
      # Starting to explore
      elif line.startswith('You start to explore'): pass
      # Stopped
      elif line.startswith('The party'): pass
      elif line.startswith('You enter'): pass
      elif line.startswith('You awake'): pass
      elif line.startswith('You continue'): pass
      elif line.startswith('You see'): pass
      # This is an unhandled message type
      else:
        self.print(' ~ unhandled: ', end='')
      self.print(line)

  ''' handlecombat
      Combat handler, returns when combat is complete
      * This currently requires the calm spell for healing *
      Any special combat actions go here

      Parameters
      line        - string, the current message buffer
                    Should contain 'You ENCOUNTER' or 'are fighting'

      Returns
      msg         - string, the current message buffer
                    Will be the line 'You continue'
  '''
  def handlecombat(self, line=''):
    self.incombat = True
    if 'You ENCOUNTER' in line:
      self.print(line)
    # If we are escorting a player make an re object to respond to 'quit'
    escortmsg = None
    # dotarget returns True if we should prefer the level of x over y
    # (we always prefer attacking drones over other NPCs)
    dotarget = lambda x,y: True if self.attacklow and x < y \
                          else False if self.attacklow \
                          else True if x > y else False
    if self.doloop == 'escort':
      escortmsg = re.compile('[:]?' + self.escortnick + \
                              r'[\S]* PRIVMSG '+self.irc.username+' :')
    class ShadowEnemy():
      def __init__(self,num,name,pos,lvl):
        self.num = num
        self.name = name
        self.pos = pos
        self.lvl = lvl
      def __str__(self):
        return f' ~ Enemy {self.num}) {self.name} L{self.lvl} at {self.pos}m'

    if 'You ENCOUNTER' in line:
      line = line[14:]
    else: # 'You are fighting against' in line:
      line = '.'.join(line.split('.')[:-2])[25:]
      # If we are in a party . . .
      if 'you are fighting' in line:
        line = line.split('against ')[1]
    parts = line.split(', ')

    enemies = {}
    havetarget = None
    for part in parts:
      num = int(part.split('-')[0].strip())
      name = part.split('-')[1].split('[')[0]
      pos = float(part.split('(')[1][:-2])
      lvl = int(part.split('(')[2][1:].split(')')[0])
      enemies[num] = ShadowEnemy(num,name,pos,lvl)
      if 'Drone' in name:
        if havetarget is None or abs(pos) < abs(enemies[havetarget].pos):
          # Save the current target as the index of enemies[]
          havetarget = num

    if havetarget is None and len(enemies) > 1:
      targetlvl = 0
      for enemy in enemies:
        if havetarget is None:
          targetlvl = enemies[enemy].lvl
          havetarget = enemy
        elif dotarget(enemies[enemy].lvl, targetlvl):
          targetlvl = enemies[enemy].lvl
          havetarget = enemy
        elif not self.attacklow and enemies[enemy].lvl == targetlvl \
          and abs(enemies[enemy].pos) < abs(enemies[havetarget].pos):
          havetarget = enemy

    for enemy in enemies:
      self.print(enemies[enemy])

    # havetarget should be set
    if havetarget is not None and len(enemies) > 1:
      self.irc.privmsg(self.lambbot, '#attack ' + str(havetarget))

    calmcasttime = 0
    calmcastgap = 90

    #enemyattack = re.compile('[\d]+-[a-zA-Z]+\[[\d]+\]')
    friendlyattack = re.compile('[0-9]+-[a-zA-Z0-9]+{')

    mypos = 0
    myaction = re.compile(r'[0-9]+-'+self.irc.username+'{[0-9]+}')
    hostileaction = re.compile(r'[0-9]+-[\S]+\[[0-9]+\]')
    while True:
      msg = self.irc.get_response(timeout=45)
      if escortmsg is not None and escortmsg.match(msg) is not None:
        if 'stop' in msg[escortmsg.match(msg).span()[1]:].strip():
          #raise 'Escorted player said to stop'
          self.irc.privmsg(self.escortnick, 'Cannot stop while in combat')
        continue
      line = self.getlambmsg(msg)
      if line == '': continue
      self.print(line)
      if 'You continue' in line:
        break
      # The line starts with our player
      if myaction.match(line):
        action = line[myaction.match(line).span()[1]+1:]
        # We are moving
        if action.startswith('moves'):
          # Our current position
          mypos = float(action.split('position')[1].split()[0])
          continue
        # A calm was cast which did nothing, do a heal
        if line.startswith('casts') and '+0HP for' in line:
          target = line.split('.')[1].split(' ')[-1]
          self.irc.privmsg(self.lambbot, '#cast heal ' + target)
          continue
      # The line starts with an enemy
      elif hostileaction.match(line):
        action = line[hostileaction.match(line).span()[1]+1:]
        if action.startswith('moves'):
          enemy = int(hostileaction.search(line)[0].split('-')[0])
          enemies[enemy].pos = float(action.split('position')[1].split()[0])
          continue
      # An attack was made but it missed
      if 'misses' in line: pass
      # Combat
      elif 'attacks' in line:
        # Friendly attack
        if friendlyattack.match(line):
          # We killed an enemy
          if 'killed them' in line:
            if 'You loot' in line:
              num = line.split('loot')[1].lstrip()
              self.lootmoney += float(num.split('$')[0])
              self.lootxp += float(num.split()[-1][:-2])
            num = int(line.split('attacks ')[1].split('-')[0].strip())
            # If we didn't fill out the enemies dict
            if num not in enemies:
              continue
            del(enemies[num])
            for enemy in enemies:
              self.print(enemies[enemy])
            # it wasn't us that killed the enemy . . .
            if self.irc.username not in line:
              if havetarget is None or havetarget != num:
                continue
            # No need to explicitly set an enemy if there aren't multiple
            if len(enemies) < 2:
              continue
            havetarget = None
            for enemy in enemies:
              if 'Drone' not in enemies[enemy].name: continue
              if havetarget is None:
                havetarget = enemy
                targetdist = abs(mypos-enemies[enemy].pos)
              elif abs(mypos-enemies[enemy].pos) < targetdist:
                havetarget = enemy
                targetdist = abs(mypos-enemies[enemy].pos)
            if havetarget is None:
              for enemy in enemies:
                if havetarget is None:
                  targetlvl = enemies[enemy].lvl
                  havetarget = enemy
                  targetdist = abs(mypos-enemies[enemy].pos)
                elif dotarget(enemies[enemy].lvl, targetlvl):
                  targetlvl = enemies[enemy].lvl
                  havetarget = enemy
                  targetdist = abs(mypos-enemies[enemy].pos)
                elif not self.attacklow and enemies[enemy].lvl == targetlvl \
                  and abs(mypos-enemies[enemy].pos) < targetdist:
                  havetarget = enemy
                  targetdist = abs(mypos-enemies[enemy].pos)
            if havetarget is not None:
              self.irc.privmsg(self.lambbot, '#attack ' + str(havetarget))
        # An enemy attacked
        else: #if enemyattack.match(line) is not None:
          # uh oh
          if 'killed' in line:
            raise Exception('Player died')
          # Add some logic for using potions / first aid (?)
          if not self.cancast:
            continue
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
    self.incombat = False
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
    self.print(' ~ Entering walkpath, path = '+str(path))
    # For each waypoint in the list of waypoints
    for point in path:
      self.print(' ~ Point = ' + point)
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
            self.sleepreceive(duration=5)
          # If this location is the destination then return
          if location in line:
            return
          # The location is the last word in the line
          currloc = line.split(' ')[-1]
          break
        # We are in combat
        elif line.startswith('You are fighting'):
          onsubway = False
          resp = handlecombat(line)
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
            self.print(' ~ It was detected that we are likely in a subway')
            self.print(' ~ (sleeping for ~ ' + str(timeremaining) + 's)')
            self.sleepreceive(duration=timeremaining)
          else:
            # Stop travelling
            self.irc.privmsg(self.lambbot, '#stop')
            self.sleepreceive(duration=5)
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
      firststart = time.time()
      if func == 'None':
        # There was no function
        # Either handle combat here or ping msgs in the irc handler
        line = self.getlambmsg(self.irc.get_response())
        if 'You ENCOUNTER' in line:
          self.handlecombat(self.getlambmsg(line))
        elif 'attacks' in line:
          self.irc.privmsg(self.lambbot, cmd)
          line = self.awaitresponse('are fighting', eta=10)
          if line != '': self.handlecombat(self.getlambmsg(line))
        continue
      # Set the function counter to zero
      fncounter = 0
      # While the user has not selected to quit and the function has not changed
      while not self.doquit and func == str(self.doloop):
        # Call the selected function and pass the iteration counter
        starttime = time.time()
        self.print(' ~  ~~~~~~~~~~')
        self.print(' ~ { ' + time.asctime())
        self.print(' ~ { Beginning iteration ' + str(fncounter) + ' of ' + func)
        self.print(' ~  ~~~~~~~~~~')
        try:
          for cmd in self.precmds:
            try:
              # Lambbot commands start with an '#'
              if cmd.startswith('#'):
                self.irc.privmsg(self.lambbot, cmd)
                self.sleepreceive(duration=5)
              # We can issue a sleep as "sleep(30)", etc.
              elif cmd.startswith('sleep('):
                duration = cmd.split('(')[1].split(')')[0]
                self.sleepreceive(duration=int(duration))
              # This is intended to be used when we are being escorted
              #  though could serve any purpose
              # "msg nick some message"
              elif cmd.startswith('msg'):
                recipient = cmd.split(' ')[1].split(' ')[0]
                message = ' '.join(cmd.split(' ')[2:])
                self.irc.privmsg(recipient, message)
                self.sleepreceive(duration=5)
              else:
                self.print('Unknown pre-command: \"' + cmd + '\"')
            except Exception as e:
              self.print('Error with pre-command: \"' + cmd + '\"')
              etype, value, tb = exc_info()
              info, error = format_exception(etype, value, tb)[-2:]
              print(f'Exception:\n{info}\n{error}')
          getattr(self,func)(fncounter)
        except Exception as e:
          self.doloop = None
          if str(e) == 'Player quit':
            self.print(' ~ Quitting . . .')
            break
          if str(e) == 'Player died':
            self.print(' ~ The player has died')
            break
          elapsed = int(time.time()-starttime)
          msg = '***** ' + time.asctime() +'\n'
          msg += ' ***  In function loop ' + func + '()\n'
          etype, value, tb = exc_info()
          info, error = format_exception(etype, value, tb)[-2:]
          msg += f' ***  Exception:\n{info}\n{error}\n'
          msg += '***** Exception at %d:%02d\n' % (elapsed//60,elapsed%60)
          self.print(msg, end='')
          with open('exceptions','a') as outfile:
            outfile.write(msg)
        # Increase the iteration counter
        fncounter+=1
        elapsed = int(time.time()-starttime)
        self.print(' ~  ~~~~~~~~~~')
        self.print(' ~ { ' + time.asctime())
        self.print(' ~ { Finished iteration ' + str(fncounter) + ' of ' + func)
        self.print(' ~ {   in %d:%02d' %  (elapsed//60,elapsed%60))
        elapsed = int(time.time()-firststart)
        secs = elapsed%60
        elapsed //= 60
        mins = elapsed%60
        elapsed //= 60
        hours = elapsed%24
        days = elapsed//24
        if days > 0: timestr = f'{days}:{hours:02d}:{mins:02d}:{secs:02d}'
        elif hours > 0: timestr = f'{hours}:{mins:02d}:{secs:02d}'
        else: timestr = f'{mins:2d}:{secs:02d}'
        self.print(' ~ { Total elapsed time:', timestr)
        loot = f'${self.lootmoney:.2f} and {round(self.lootxp,2)}XP'
        self.print(' ~ { Total loot:', loot)
        self.print(' ~  ~~~~~~~~~~')
        # Short sleep
        self.sleepreceive(duration=5)

  ''' invflush
      If self.invstop is positive, this function {sells,pushes,drops} all items including that number
      This function should be called outside of travel, etc.
      An ideal place for this function would be before a loop function exits

      Parameters
      inescort    - boolean, whether we are a 'passenger' and our escort teleported us here
      cmd         - string, the command to use, e.g., "#drop", "#sell", "#push", "#give nick"
  '''
  def invflush(self, inescort=False, cmd='#drop'):
    if self.invstop == 0:
      return
    escortmsg = None
    getline = None
    if inescort:
      escortmsg = re.compile('[:]?'+self.escortnick+r'[\S]* PRIVMSG '+self.irc.username+' :')
      getline = lambda s: s[escortmsg.match(s).span()[1]:].strip() if escortmsg.match(s) is not None \
                          else self.getlambmsg(s)
    if getline is None:
      getline = lambda s: self.getlambmsg(s)
    self.irc.privmsg(self.lambbot, '#inventory')
    readyquit = True if escortmsg is None else False
    setquit = lambda b,s: True if b or 'Finished shedding inventory' in s else False
    numpages = ''
    while True:
      numpages = getline(self.irc.get_response())
      if 'Your Inventory' in numpages: break
      if 'There are no items here' in numpages:
        if escortmsg is not None:
          while not readyquit:
            numpages = getline(self.irc.get_response())
            readyquit = setquit(readyquit, numpages)
        return
      readyquit = setquit(readyquit, numpages)
    numpages = int(numpages.split(':')[0].split('/')[1])
    haveqty = re.compile(r'\([\d]+\)')
    while True:
      self.irc.privmsg(self.lambbot, '#inventory ' + str(numpages))
      numpages -= 1
      numitems = 0
      while True:
        numitems = getline(self.irc.get_response())
        if 'Your Inventory' in numitems: break
        readyquit = setquit(readyquit, numitems)
      items = numitems.split(', ')
      numitems = items[-1].split('-')[0].strip()
      # If there is only one item on this inventory page's list it will be different
      if numitems.startswith('page'):
        numitems = numitems.split(': ')[1]
      numitems = int(numitems)
      pos = len(items)-1
      readyquit = setquit(readyquit, getline(self.irc.get_response(timeout=2)))
      while pos > 0:
        if numitems < self.invstop:
          break
        if haveqty.search(items[pos]):
          qty = items[pos][haveqty.search(items[pos]).span()[0]:]
          qty = re.sub('[()]','',qty)
          self.irc.privmsg(self.lambbot, cmd + ' ' + str(numitems) + ' ' + qty)
        else:
          self.irc.privmsg(self.lambbot, cmd + ' ' + str(numitems))
        readyquit = setquit(readyquit, getline(self.irc.get_response(timeout=2)))
        numitems -= 1
        pos -= 1
      if numitems < self.invstop:
        break
    if escortmsg is not None:
      while not readyquit:
        readyquit = setquit(readyquit, getline(self.irc.get_response()))
    return

  ''' shedinv     - goes to the secondhand and then the bank to shed inventory
      Parameters
      fncounter   - unused, here only to match other "loop" functions
  '''
  def shedinv(self, fncounter=0):
    inescort = False
    if self.cancast:
      self.irc.privmsg(self.lambbot, '#cast teleport secondhand')
      self.awaitresponse('now outside of')
      self.irc.privmsg(self.lambbot, '#enter')
      self.awaitresponse('You enter the')
    elif self.escortcasts and self.escortnick != '':
      self.irc.privmsg(self.lambbot, '#part')
      self.awaitresponse('left the party')
      self.irc.privmsg(self.lambbot, '#join ' + self.escortnick)
      self.awaitresponse('joined the party')
      self.irc.privmsg(self.escortnick, 'docmd #cast teleport secondhand')
      self.awaitresponse('now outside of')
      self.irc.privmsg(self.escortnick, 'docmd #enter')
      self.awaitresponse('You enter the')
      self.irc.privmsg(self.escortnick, 'invflush #sell')
      inescort = True
    else:
      self.irc.privmsg(self.lambbot, '#goto secondhand')
      self.awaitresponse('You enter the')
    self.invflush(inescort=inescort, cmd='#sell')
    inescort = False
    if self.cancast:
      self.irc.privmsg(self.lambbot, '#cast teleport bank')
      self.awaitresponse('now outside of')
      self.irc.privmsg(self.lambbot, '#enter')
      self.awaitresponse('In a bank')
    elif self.escortcasts and self.escortnick != '':
      self.irc.privmsg(self.escortnick, 'docmd #cast teleport bank')
      self.awaitresponse('now outside of')
      self.irc.privmsg(self.escortnick, 'docmd #enter')
      self.awaitresponse('You enter the')
      self.irc.privmsg(self.escortnick, 'invflush #push')
      inescort = True
    else:
      self.irc.privmsg(self.lambbot, '#goto bank')
      self.awaitresponse('In a bank')
    self.invflush(inescort=inescort, cmd='#push')
    if inescort:
      self.irc.privmsg(self.escortnick, 'docmd #part')
      self.awaitresponse('left the party')
      self.irc.privmsg(self.escortnick, 'docmd #join ' + self.irc.username)
      self.awaitresponse('joined the party')

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
    # Go to the storage room, will fight the FatOrk on entrance, then go to the exit
    self.walkpath(['OrkHQ_StorageRoom','Exit'])
    # Leave the OrkHQ
    self.irc.privmsg(self.lambbot, '#leave')
    self.awaitresponse(entermsg['Redmond'])
    if self.invstop > 0 and fncounter > 0 and fncounter % 4 == 0:
      self.shedinv()
      if self.cancast:
        self.irc.privmsg(self.lambbot, '#cast teleport hotel')
        self.awaitresponse('now outside of')
        self.irc.privmsg(self.lambbot, '#enter')
      else:
        self.irc.privmsg(self.lambbot, '#goto hotel')
      self.awaitresponse('You enter')
      self.irc.privmsg(self.lambbot, '#sleep')
      self.awaitresponse('ready to go')
      if self.cancast:
        self.irc.privmsg(self.lambbot, '#cast teleport OrkHQ')
        self.irc.privmsg(self.lambbot, '#enter')
      else:
        self.irc.privmsg(self.lambbot, '#goto OrkHQ')
      # Await the entrance message
      self.awaitresponse(entermsg['Redmond_OrkHQ'])

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
      response = self.irc.get_response(timeout=5)
      stopped = False
      while not stopped:
        response = self.irc.get_response(timeout=5)
        line = self.getlambmsg(response)
        if 'What now?' in line:
          stopped = True
          break
        response = self.irc.get_response(timeout=5)
        self.irc.privmsg(self.lambbot, '#party')
        response = self.awaitresponse('You are')
        line = self.getlambmsg(response)
        if 'are outside' in line or 'are inside' in line:
          stopped = True
          break
        elif 'are fighting' in line:
          self.handlecombat(line)
        self.sleepreceive(earlyexit=True,duration=5)
        self.irc.privmsg(self.lambbot, '#stop')
    self.irc.privmsg(self.lambbot, '#explore')
    # Not sure if this is the right response if not all locations discovered yet.
    self.awaitresponse('explored')
    if self.invstop > 0:
      self.shedinv()
    if self.cancast:
      self.irc.privmsg(self.lambbot, '#cast teleport hotel')
      self.awaitresponse('now outside of')
      self.irc.privmsg(self.lambbot, '#enter')
      self.awaitresponse('You enter')
      self.irc.privmsg(self.lambbot, '#sleep')
      self.awaitresponse('ready to go')
    elif self.escortcasts and self.escortnick != '':
      self.irc.privmsg(self.lambbot, '#part')
      self.awaitresponse('left the party')
      self.irc.privmsg(self.lambbot, '#join ' + self.escortnick)
      self.awaitresponse('joined the party')
      self.irc.privmsg(self.escortnick, 'docmd #cast teleport hotel')
      self.awaitresponse('outside of')
      self.irc.privmsg(self.escortnick, 'docmd #enter')
      self.awaitresponse('enter the')
      self.irc.privmsg(self.escortnick, 'docmd #sleep')
      self.awaitresponse('ready to go')
      self.irc.privmsg(self.lambbot, '#part')
      self.awaitresponse('left the party')
      self.irc.privmsg(self.escortnick, 'docmd #join ' + self.irc.username)
      self.awaitresponse('joined the party')
    else:
      self.irc.privmsg(self.lambbot, '#goto hotel')
      self.awaitresponse('You enter')
      self.irc.privmsg(self.lambbot, '#sleep')
      self.awaitresponse('ready to go')
    self.sleepreceive(duration=5)

  ''' escort
      Escort someone else, handling combat / etc automatically
  '''
  def escort(self, fncounter=0):
    if self.escortnick == '':
      self.doloop = None
      self.print('Escort loop chosen but no nick set to escort !')
      return
    escortmsg = re.compile('[:]?'+self.escortnick+r'[\S]* PRIVMSG '+self.irc.username+' :')
    getline = lambda s: '' if escortmsg.match(s) is None \
                        else s[escortmsg.match(s).span()[1]:].strip()
    self.irc.privmsg(self.escortnick, 'Tell me when to \"start\"')
    while True:
      line = getline(self.irc.get_response())
      if 'start' in line:
        break
    helpstrings = ['Tell me to \"stop\" to quit',
                   'Tell me to manually \"shedinv\"',
                   'Tell me to \"invflush #sell\" to partially shedinv',
                   'Tell me to \"doloop explore fncounter 1 count 0\"',
                   'Tell me to \"docmd #lambcmd\"',
                   'Tell me to \"sharekp\" to get my known places',
                   'Tell me to \"sharekw\" to get my known words',
                   'Ask me for \"help\" to repeat this',
                  ]
    for helpstring in helpstrings:
      self.irc.privmsg(self.escortnick, helpstring)
    while not self.doquit and 'escort' == str(self.doloop):
      line = self.irc.get_response()
      if 'You ENCOUNTER' in self.getlambmsg(line):
        self.handlecombat(self.getlambmsg(line))
        continue
      line = getline(line)
      if line == '': continue
      elif 'docmd ' in line:
        cmd = line.split('docmd ')[1]
        bad = ''
        for badcmd in self.badcmds:
          for word in cmd.split(' '):
            if badcmd == word:
              bad = badcmd
              break
          if bad != '':
            break
        if bad == '':
          self.irc.privmsg(self.lambbot, cmd)
        else:
          bad = 'Refusing to do a command containing ' + bad
          self.irc.privmsg(self.escortnick, bad)
      elif 'sharekp' in line:
        self.irc.privmsg(self.escortnick, 'I will tell you when I am done')
        cities = ['Redmond','Seattle','Delaware','Chicago']
        cmd = '#givekp ' + self.escortnick + ' '
        for city in cities:
          self.irc.privmsg(self.lambbot, '#kp ' + city)
          fullcmd = cmd + city + '_'
          response = self.awaitresponse(city).strip('.')
          places = response.split(':')[-1].split(', ')
          places[0] = places[0].strip()
          # Redmond has numbered places, "1-Hotel", . . .
          # Could check the city or just . . .
          if any('-' in place for place in places):
            places = [place.split('-')[1] for place in places]
          for place in places:
            self.irc.privmsg(self.lambbot, fullcmd + place)
            self.sleepreceive(duration=3)
          self.sleepreceive(duration=3)
        self.irc.privmsg(self.escortnick, 'I am done sharing places !!!')
      elif 'sharekw' in line:
        self.irc.privmsg(self.escortnick, 'I will tell you when I am done')
        self.irc.privmsg(self.lambbot, '#kw')
        cmd = '#givekw ' + self.escortnick + ' '
        response = self.awaitresponse('Known Words').strip('.')
        words = response.split(':')[-1].split(', ')
        words = [word.strip().split('-')[1] for word in words]
        for word in words:
          self.irc.privmsg(self.lambbot, cmd + word)
          self.sleepreceive(duration=3)
        self.sleepreceive(duration=3)
        self.irc.privmsg(self.escortnick, 'I am done sharing words !!!')
      elif 'help' in line:
        for helpstring in helpstrings:
          self.irc.privmsg(self.escortnick, helpstring)
      elif 'stop' in line:
        self.doloop = None
        break
      elif 'shedinv' in line:
        if self.invstop > 0:
          self.shedinv()
          self.irc.privmsg(self.escortnick, 'Finished shedding inventory')
      elif 'invflush' in line:
        cmd = line.split('invflush ')[1]
        if self.invstop > 0:
          self.invflush(cmd=cmd)
        self.irc.privmsg(self.escortnick, 'Finished shedding inventory')
      # We catch the 'stop' command to exit a loop function
      # If the iterations is zero there is no other stop
      # Otherwise, the escorted player is required for iterations to end
      elif 'doloop ' in line:
        try:
          cmd = line.split('doloop ')[1]
          fncounter = cmd.split(' fncounter ')[1].split(' ')[0]
          iterations = int(cmd.split(' count ')[1])
          if iterations == 0: iterations = -1
          loop = cmd.split(' ')[0]
          while iterations != 0:
            for cmd in self.precmds:
              self.irc.privmsg(self.lambbot, cmd)
              self.sleepreceive(duration=3)
            getattr(self,loop)(int(fncounter))
            if iterations > 0:
              iterations -= 1
        except Exception as e:
          if str(e) == 'Escorted player said to stop':
            self.irc.privmsg(self.escortnick, 'Stopped the doloop method')
            self.irc.privmsg(self.escortnick, 'Say stop again to quit')
          else:
            etype, value, tb = exc_info()
            info, error = format_exception(etype, value, tb)[-2:]
            print(f'Exception:\n{info}\n{error}')
      else:
        self.irc.privmsg(self.escortnick, 'What do you mean, \"' + line + '\"?')

