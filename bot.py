#! /usr/bin/env python3

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
            # Confirm exit messages are the same for other dungeons
            'Exit':'You can return to this location',
            #'You can use this location to ', <- ???
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

    Internal Methods
    islambmsg     - Returns bool indicating whether a message is from the Lamb bot
    getlambmsg    - Returns a string, the stripped message from the Lamb bot
    awaitresponse - Awaits a specific response from the Lamb bot, returns the string response
    handlecombat  - Called when in combat, returns when combat is over
    cityrank      - Returns an ordinal value for cities, used for subway travel
    walkpath      - Issues "goto" commands for all locations within a list to walk a path
    gotoloc       - Travels to a destination location
    printloop     - The thread function, calls method specified by doloop
    invflush      - This method flushes inventory up to a point

    Doloop Methods
    getbacon      - Goes to the OrkHQ, then repeatedly kills FatOrk to get bacon
    explore       - Explores the current city on a loop
'''
class ShadowThread():
  th         = None         # A reference to the running thread
  doloop     = None         # None, or a string with the name of the loop function to do
  doquit     = False        # A flag to tell the thread to quit
  irc        = None         # A reference to the IRC handler class with the current connection
  lambbot    = ''           # The nick of the Lamb bot we will be talking to
  meetsay    = 'invite'     # None, or a string we will say when we 'meet' civilians
  invstop    = 0            # Inventory stop position for selling and getting rid of inventory

  ''' init
      Assign the lambbot, the irc socket class, and start the thread
  '''
  def __init__(self, irc, lambbot='Lamb3'):
    self.lambbot = lambbot
    self.irc = irc
    self.th = threading.Thread(target=self.printloop, daemon=True)
    self.th.start()

  ''' del
      Set quit flags and join the thread
  '''
  def __del__(self):
    self.doquit = True
    self.func = None
    self.th.join()

  ''' islambmsg
      Returns True if the line matches the format of a PRIVMSG from the Lamb bot

      Parameters
      msg         - string, the full message line
  '''
  def islambmsg(self, msg):
    if re.compile('[:]?'+self.lambbot+'[\S]* PRIVMSG '+self.irc.username+' :').match(msg) is None:
      return False
    return True

  ''' getlambmsg
      Returns the text content of the message from the Lamb bot

      Parameters
      msg         - string, the full message line
                    * This should be a valid message from the Lamb bot
  '''
  def getlambmsg(self, msg):
    msg = msg[re.compile('[:]?'+self.lambbot+'[\S]* PRIVMSG '+self.irc.username+' :').match(msg).span()[1]:].strip()
    if msg[-1] == '.':
      msg = msg[:-1]
    return msg

  ''' awaitresponse
      Returns a list beginning with the line containing the quitmsg parameter once received

      Parameters
      quitmsg     - string, this is the string we are waiting to receive
      eta         - integer, this is an optional parameter used to print
                     periodic approximate time remaining messages
  '''
  def awaitresponse(self, quitmsg, eta=-1):
    print('  Awaiting response: '+str(quitmsg))
    # Repeat until we see the quitmsg parameter
    while True:
      # If there is an ETA, print an approximate time remaining
      if eta > 0:
        print(time.asctime())
        # ETA currently used only for subway travel
        # If the ETA becomes too negative then there may be some issue
        if eta-time.time() < -60:
          print('We are a minute past the ETA ... returning from awaitresponse ... !!!')
          return ['']
        # print the ETA
        print('About '+str(int(eta-time.time()))+'s remaining')
      # Get text from irc, set the timeout to 2 minutes
      response = self.irc.get_response(timeout=120)
      response = response.split('\n')
      i = 0
      while True:
        if i == len(response): break
        if not self.islambmsg(response[i]):
          i += 1
          continue
        line = self.getlambmsg(response[i])
        # We have seen our quit msg, return the line
        if quitmsg in line:
          return response[i:]
        # We meet a citizen or another player
        # This will occur when we are walking within cities
        elif 'You meet ' in line:
          # If we have a message set to say
          if self.meetsay is not None:
            # Say the message and get their reply
            self.irc.privmsg(self.lambbot, '#say ' + self.meetsay)
            # Give a moment of time for a response . . .
            time.sleep(15)
          # Say bye to them, this will close an interation with a citizen
          self.irc.privmsg(self.lambbot, '#bye')
        # Starting combat
        elif 'You ENCOUNTER ' in line or 'You are fighting' in line:
          x = i
          while x != len(response) and 'You continue' not in response[x]:
            x += 1
          # If 'You continue' was in the response
          if x < len(response):
            i = x
          else:
            # We get a new list from the handle combat function
            response = self.handlecombat(response[i:])
            # 'i' will be reset to zero at the bottom of this loop
            i = -1
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
          print('  unhandled: \"'+line+'\"')
        i += 1

  ''' handlecombat
      Combat handler, returns when combat is complete
      Any special combat actions go here

      Parameters
      msg         - list, each line a string in the current message buffer
                    Element zero will contain the line 'You ENCOUNTER' or 'are fighting'

      Returns
      msg         - list, each line a string in the current message buffer
                    Element zero will be the first line beyond 'You continue'
                    The returned list may be empty
  '''
  def handlecombat(self, msg=[]):
    class ShadowEnemy():
      name = ''
      distance = 0
      level = 0
      def __init__(self,nm,dist,lev):
        self.name = nm
        self.distance = dist
        self.level = lev

    line = self.getlambmsg(msg[0])
    if 'You ENCOUNTER' in line:
      line = line[14:]
    else:
      line = '.'.join(line.split('.')[:-2])
    parts = line.split(', ')

    enemies = {}
    havetarget = None
    for part in parts:
      num = int(part.split('-')[0].strip())
      name = part.split('-')[1].split('[')[0]
      dist = float(part.split('(')[1][:-2])
      lvl = int(part.split('(')[2][1:].split(')')[0])
      enemies[num] = ShadowEnemy(name,dist,lvl)
      print('Enemy '+str(num)+') '+name+' L'+str(lvl)+' at '+str(dist)+'m')
      if havetarget is None and 'Drone' in name:
        # Save the current target as the index of enemies[]
        havetarget = num

    if havetarget is None:
      lowlevel = 9999
      for enemy in enemies:
        if enemies[enemy].level < lowlevel:
          lowlevel = enemies[enemy].level
          havetarget = enemy

    # shouldn't be . . .
    if havetarget is not None:
      print('Target is '+str(havetarget))
      self.irc.privmsg(self.lambbot, '#attack ' + str(havetarget))

    calmcasttime = 0
    calmcastgap = 90

    i = 1
    while True:
      if i == len(msg):
        msg = self.irc.get_response(timeout=45).split('\n')
        i = 0
        continue
      if not self.islambmsg(msg[i]):
        i += 1
        continue
      line = self.getlambmsg(msg[i])
      if 'You continue' in line:
        break
      # Combat
      if 'misses' in line:
        pass
      elif 'attacks' in line:
        if line[re.search('[\d]+-',line).span()[1]:].startswith(self.irc.username):
          # We killed an enemy
          if 'killed them' in line:
            num = int(line.split('attacks ')[1].split('-')[0].strip())
            del(enemies[num])
            if len(enemies) == 0:
              break
            havetarget = None
            for enemy in enemies:
              if 'Drone' in enemies[enemy].name:
                self.irc.privmsg(self.lambbot, '#attack ' + str(enemy))
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
        # Enemy attacked
        else:
          # uh oh
          if 'killed' in line:
            self.doloop = None
            return msg[i+1:]
          # "68.7/72.6"
          health = line.split(', ')[1].split('HP')[0]
          numerator = health.split('/')[0]
          denominator = health.split('/')[1]
          health = float(numerator)/float(denominator)
          # Less than 30% health
          if health < 0.3:
            self.irc.privmsg(self.lambbot, '#cast calm')
          # Less than 50% health
          elif health < 0.5:
            if time.time() - castcalmtime > calmcastgap - 15:
              self.irc.privmsg(self.lambbot, '#cast calm')
              castcalmtime = time.time()
          # Less than 70% health
          elif health < 0.7:
            if time.time() - calmcasttime > calmcastgap:
              self.irc.privmsg(self.lambbot, '#cast calm')
              calmcasttime = time.time()
      i += 1
    # return any remaining text (as a list of lines) after combat
    return msg[i+1:]

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
    print('  Entering walkpath, path = '+str(path))
    # For each waypoint in the list of waypoints
    for point in path:
      print('  Point = '+point)
      # goto the waypoint
      self.irc.privmsg(self.lambbot, '#goto ' + point)
      # await the entrance message for this waypoint
      self.awaitresponse(entermsg[point])

  ''' gotoloc
      Handles getting to some starting point for a message loop.

      Parameters
      location    - string, the destination location, form of 'Redmond_Hotel'
                    * the destination location should not be within a dungeon
                    * the origin must be in the world (not in a dungeon)

      Returns       
                    When travel is complete, player is at the destination
                    If self.doloop becomes None (user has request to quit function)
                    * any function loops should check if self.doloop is None after this function
  '''
  def gotoloc(self,location):
    # The user has set the function loop to None, quit going to location
    # Calling functions must test whether self.doloop is None upon return
    if self.doloop is None:
      return
    # No current location
    currloc = ''
    # Limit repeated "#party" messages
    onsubway = False
    while currloc == '':
      # Find out where we are at
      self.irc.privmsg(self.lambbot, '#party')
      resp = self.irc.get_response()
      # You are {inside,outside,fighting,exploring,going}
      # leave whatever location we are in, or enter if it is right
      i = 0
      resp = resp.split('\n')
      while True:
        if i == len(resp): break
        if not self.islambmsg(resp[i]): continue
        line = self.getlambmsg(resp[i])
        print('The line = \"'+line+'\"')
        # We are inside or outside of a location
        if line.startswith('You are inside') or line.startswith('You are outside'):
          # If this location is the destination then return
          if location in line:
            return
          # The location is the last word in the line
          currloc = line.split(' ')[-1]
        # We are in combat
        elif line.startswith('You are fighting'):
          onsubway = False
          resp = handlecombat(resp[i:])
          i = -1
        # We are exploring, or going to a location, try to stop
        elif line.startswith('You are'):
          # If onsubway then we *just* tried to stop, and didn't
          if onsubway:
            # catch any later 'you are travelling' messages in the list . . .
            x = i+1
            while x != len(resp):
              if 'You are travel' in resp[x]:
                i=x
              x += 1
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
            secs += 15
            print('  It was detected that we are likely in a subway')
            print('  sleeping for ' + str(mins*60+secs) + 's')
            # Sleep for the remaining time before continuing
            time.sleep(mins*60+secs)
          else:
            # Stop travelling
            self.irc.privmsg(self.lambbot, '#stop')
            # set the onsubway flag in case we don't stop
            onsubway = True
        i += 1
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
    # We are now at the subway in a different city, ensure we are inside
    self.irc.privmsg(self.lambbot, '#enter')
    # For subway direction: Chicago <-> Delaware <-> Seattle <-> Redmond
    if srccity == 'Redmond' or self.cityrank(srccity) > self.cityrank(dstcity):
      self.irc.privmsg(self.lambbot, '#travel 1')
    else:
      self.irc.privmsg(self.lambbot, '#travel 2')
    # The optional 'eta' parameter to the await response function
    #  will occasionally print an approximate time remaining
    eta = 0
    # The initial response received may not have the ETA
    while eta == 0:
      response = self.irc.get_response()
      # We can calculate our travel time
      if 'ETA: ' in response:
        for line in response.split('\n'):
          if 'ETA' not in line: continue
          if not self.islambmsg(line): continue
          line = self.getlambmsg(line)
          print('ETA line = \"' + line + '\"')
          timeremaining = response[response.find('ETA: ')+5:]
          # We will always have minutes
          parts = timeremaining.split('m')
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
    while not self.doquit:
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
          getattr(self,func)(fncounter)
          # Increase the iteration counter
          fncounter+=1
          # Short sleep
          time.sleep(3)
      else:
        # There was no function, need to continually check for PING messages
        # The get_response function has a timeout
        self.irc.get_response(timeout=30)

  ''' invflush
      If self.invstop is positive, this function {sells,pushes,drops} all items including that number
      This function should be called outside of travel, etc.
      An ideal place for this function would be before a loop function exits
  '''
  def inventoryflush(self, cmd='#drop'):
    if self.invstop == 0:
      return
    self.irc.privmsg(self.lambbot, '#inventory')
    numpages = self.getlambmsg(self.awaitresponse('Your Inventory')[0])
    print('1) numpages = \"' + numpages +'\"')
    numpages = int(numpages.split(':')[0].split('/')[1])
    print('2) numpages = \"' + str(numpages) +'\"')
    haveqty = re.compile('\([\d]+\)')
    numitems = 0
    while True:
      self.irc.privmsg(self.lambbot, '#inventory ' + str(numpages))
      numpages -= 1
      numitems = self.getlambmsg(self.awaitresponse('Your Inventory')[0])
      print('numitems = \"' + numitems + '\"')
      items = numitems.split(', ')
      print('items = ' + str(items))
      numitems = int(items[len(items)-1].split('-')[0])
      print('numitems = ' + str(numitems))
      pos = len(items)-1
      while pos > 0:
        if numitems < self.invstop:
          break
        if haveqty.search(items[pos]):
          qty = items[pos][haveqty.search(items[pos]).span()[0]:]
          qty = re.sub('[()]','',qty)
          self.irc.privmsg(self.lambbot, cmd + ' ' + str(numitems) + ' ' + qty)
        else:
          self.irc.privmsg(self.lambbot, cmd + ' ' + str(numitems))
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
      # Ensure function not cancelled during travel
      if self.doloop is None:
        return
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
      This can be used to grind for xp
       to search for citizens to #say things to
        find locations
       *This can also be used to test the handlecombat method*
  '''
  def explore(self, fncounter=0):
    # Ensure we are stopped
    if fncounter < 1:
      self.irc.privmsg(self.lambbot, '#stop')
      response = self.irc.get_response()
      stopped = False
      while not stopped:
        for line in response.split('\n'):
          if 'What now?' in line:
            stopped = True
            break
        if not stopped:
          self.irc.privmsg(self.lambbot, '#party')
          response = self.irc.get_response()
          for line in response.split('\n'):
            if 'You are outside' or 'You are inside' in line:
              stopped = True
              break
        if not stopped:
          time.sleep(20)
          self.irc.privmsg(self.lambbot, '#stop')
          response = self.irc.get_response()
    self.irc.privmsg(self.lambbot, '#explore')
    # Not sure if this is the right response if not all locations discovered yet.
    self.awaitresponse('explored')
    self.irc.privmsg(self.lambbot, '#cast teleport secondhand')
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
    self.awaitresponse('#sleep')
    self.irc.privmsg(self.lambbot, '#sleep')
    self.awaitresponse('ready to go')

