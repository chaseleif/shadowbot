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

    Internal Methods
    islambmsg     - Returns bool indicating whether a message is from the Lamb bot
    getlambmsg    - Returns a string, the stripped message from the Lamb bot
    awaitresponse - Awaits a specific response from the Lamb bot, returns the string response
    cityrank      - Returns an ordinal value for cities, used for subway travel
    walkpath      - Issues "goto" commands for all locations within a list to walk a path
    gotoloc       - Travels to a destination location
    printloop     - The thread function, calls method specified by doloop

    Doloop Methods
    getbacon      - Goes to the OrkHQ, then repeatedly kills FatOrk to get bacon
'''
class ShadowThread():
  th         = None  # A reference to the running thread
  doloop     = None  # None, or a string with the name of the loop function to do
  doquit     = False # A flag to tell the thread to quit
  irc        = None  # A reference to the IRC handler class with the current connection
  lambbot    = ''    # The nick of the Lamb bot we will be talking to
  meetsay    = None  # None, or a string we will say when we 'meet' civilians

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
      Parameters
      msg         - string, the full message line

      Returns True if the line matches the format of a PRIVMSG from the Lamb bot
  '''
  def islambmsg(self, msg):
    if re.compile('[:]?'+self.lambbot+'[\S]* PRIVMSG '+self.irc.username+' :').match(msg) is None:
      return False
    return True

  ''' getlambmsg
      Parameters
      msg         - string, the full message line
                    * This should be a valid message from the Lamb bot

      Returns the text content of the message from the Lamb bot
  '''
  def getlambmsg(self, msg):
    msg = msg[re.compile('[:]?'+self.lambbot+'[\S]* PRIVMSG '+self.irc.username+' :').match(msg).span()[1]:]
    if msg[-1] == '.':
      msg = msg[:-1]
    return msg

  ''' awaitresponse
      Parameters
      quitmsg     - string, this is the string we are waiting to receive
      eta         - integer, this is an optional parameter used to print
                     periodic approximate time remaining messages

      Returns the string containing the quitmsg parameter once received
  '''
  def awaitresponse(self, quitmsg, eta=-1):
    print('  Awaiting response: '+str(quitmsg))
    # Repeat until we see the quitmsg parameter
    while True:
      # If there is an ETA, print an approximate time remaining
      if eta > 0:
        # ETA currently used only for subway travel
        # If the ETA becomes too negative then there may be some issue
        # if eta-time.time() < -5: return
        # print the ETA
        print('~'+str(int(eta-time.time()))+'s remaining')
      # Get text from irc, set the timeout to 2 minutes
      response = self.irc.get_response(timeout=120)
      response = response.split('\n')
      for line in response:
        if not self.islambmsg(line): continue
        line = self.getlambmsg(line)
        # We have seen our quit msg, return the line
        if quitmsg in line:
          return line
        # We meet a citizen or another player
        # This will occur when we are walking within cities
        elif 'You meet ' in line:
          # If we have a message set to say
          if self.meetsay is not None:
            # Say the message and get their reply
            self.irc.privmsg(self.lambbot, '#say ' + self.meetsay)
            self.irc.get_response()
          # Say bye to them, this will close an interation with a citizen
          self.irc.privmsg(self.lambbot, '#bye')
          self.irc.get_response()
        # This is an unhandled message type
        else:
          #if 'You ENCOUNTER ' in line: # Starting combat
          # if find in line 'drone', attack them first.
          # otherwise, attack players in increasing order of level, ...
          # ..., if hp falls below a threshhold, ...
          print('  unhandled: \"'+line+'\"')

  ''' cityrank
      Parameters
      city        - A string with a city name: Chicago, Delaware, Seattle, Redmond

      Returns an ordering, this is used to determine direction of subway travel
  '''
  def cityrank(self,city):
    if city=='Chicago': return 4
    if city=='Delaware': return 3
    if city=='Seattle': return 2
    return 1

  ''' walkpath
      Parameters
      path        - list, a list of strings, each a destination to "goto"

      Returns upon arrival of last entry in the list
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
      Parameters
      location    - string, the destination location, form of 'Redmond_Hotel'
                    * the destination location should not be within a dungeon
                    * the destination location should not be a subway
                    * the origin must be in the world (not in a dungeon)

      travelling  - boolean, only used internally to prevent flooding messages.
                    Do not use this parameter.
                    The player was previously thought to be exploring or going to,
                    a stop command was issued but the player is still travelling.
                    This will occur when the player is on a subway.

      Handles getting to some starting point for a message loop.
      Function is recursive, as needed.

      Returns       
                    When travel is complete, player is at the destination
                    If self.doloop becomes None (user has request to quit function)
                    * any function loops should check if self.doloop is None after this function
  '''
  def gotoloc(self,location,travelling=False):
    # The user has set the function loop to None, quit going to location
    # Calling functions must test whether self.doloop is None upon return
    if self.doloop is None:
      return
    # Find out where we are at
    self.irc.privmsg(self.lambbot, '#party')
    # No current location
    currloc = ''
    # The first irc response we get may not have the party information
    while currloc == '':
      resp = self.irc.get_response()
      # You are {inside,outside,fighting,exploring,going}
      # leave whatever location we are in, or enter if it is right
      for line in resp.split('\n'):
        if not self.islambmsg(line): continue
        line = self.getlambmsg(line)
        print('The line = \"'+line+'\"')
        # We are inside or outside of a location
        if line.startswith('You are inside') or line.startswith('You are outside'):
          # If this location is the destination, or a subway, ensure we are inside
          if location in line or 'Subway' in line:
            self.irc.privmsg(self.lambbot, '#enter')
            self.irc.get_response()
            # A subway cannot be the destination
            if 'Subway' not in line:
              return
          # The location is the last word in the line
          currloc = line.split(' ')[-1]
        # We are in combat, some combat function can be called here
        # We must finally return with a recursive call to this function
        #  as we need to say "#party" again and get the current location
        elif line.startswith('You are fighting'):
          # *some combat function could be called here*
          # combatfunction()
          # *there must be a sleep call before returning if still in combat*
          time.sleep(30)
          # retry "#party", etc.
          return self.gotoloc(location)
        # We are exploring, or going to a location, try to stop
        elif line.startswith('You are'):
          # If travelling then we *just* tried to stop, and didn't
          if travelling:
            # This should be a subway journey, which we cannot stop
            # Find out the remaining time for this travel
            line = line.split('.')[1][1:]
            mins = 0
            secs = 0
            if ' ' in line.split('m'):
              line = line.split('m')
              mins = int(line[0])
              secs = int(line[1][1:3])
            else:
              secs = int(line.split('s')[0])
            # ensure we have some time, this should never or rarely happen
            if mins == 0 and secs == 0:
              secs = 15
            # Sleep for the remaining time of the travel before trying again
            time.sleep(mins*60+secs)
            # Try to continue going to the destination
            return self.gotoloc(location)
          else:
            # Stop travelling
            self.irc.privmsg(self.lambbot, '#stop')
            self.irc.get_response()
            # Try to find out the location again, set the travelling flag to True
            return self.gotoloc(location,travelling=True)
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
      # We are now at the subway, recursively call this function
      return self.gotoloc(location)
    # We are at the subway in a different city
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
        timeremaining = response[response.find('ETA: ')+5:]
        # We will always have minutes
        parts = timeremaining.split('m')
        mins = int(parts[0])
        secs = 0
        # We also have seconds
        if len(parts) > 1 and len(parts[1])>1:
          secs = int(parts[1][1:3])
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
        # The get_response function has a default timeout
        self.irc.get_response()
        # Sleep for longer
        time.sleep(15)

  ''' getbacon
      Parameters
      fncounter   - Used to vary action depending on each Nth function call
                    On the first function call we go to Redmond_OrkHQ
                    On subsequent calls we are already at the Redmond_OrkHQ

      This function goes to the OrkHQ_StorageRoom to battle the FatOrk
      There is some chance that the FatOrk will drop a bacon
      We must exit and re-enter the OrkHQ each time we kill the FatOrk
  '''
  def getbacon(self, fncounter=0):
    # Get to the OrkHQ
    if fncounter < 1:
      self.gotoloc('Redmond_OrkHQ')
      # Ensure function not cancelled during travel
      if self.doloop is None:
        return
    # We are already at the OrkHQ
    else:
      # Enter the OrkHQ
      self.irc.privmsg(self.lambbot, '#enter')
      # Await the entrance message
      self.awaitresponse(entermsg['Redmond_OrkHQ'])
    # Go to the storage room, will fight the FatOrk on entrance, then go to the exit
    self.walkpath(['OrkHQ_StorageRoom','Exit'])
    # Leave the OrkHQ
    self.irc.privmsg(self.lambbot, '#leave')
    self.awaitresponse(entermsg['Redmond'])

