#! /usr/bin/env python3

import time, threading

entermsg = {'Redmond_Hotel':'You enter the Redmond Hotel',
            ################ The OrkHQ, for getting bacon
            'Redmond_OrkHQ':'You enter the ork headquarters',
            'OrkHQ_StorageRoom':'You continue inside OrkHQ_StorageRoom',
            # Confirm exit messages are the same for other dungeons
            'Exit':'You can use this location to ',
            # '#travel 1' moves to the right, 2 to left, (unless in redmond)
            # Chicago <-> Delaware <-> Seattle <-> Redmond
            'Subway':'You enter the Subway',
           }

class ShadowThread():
  th          = None
  starttime   = 0.0
  doloop      = None # 'func1'
  doquit      = False
  irc         = None
  lambbot     = ''

  def __init__(self, irc, lambbot='Lamb3'):
    self.lambbot = lambbot
    self.irc = irc
    self.th = threading.Thread(target=self.printloop, daemon=True)
    self.th.start()

  def __del__(self):
    self.doquit = True
    self.func = None
    self.th.join()

  def awaitresponse(self, quitmsg):
    print('  Awaiting response: '+str(quitmsg))
    while True:
      response = self.irc.get_response(timeout=120)
      response = response.split('\n')
      for line in response:
        if self.lambbot not in line: continue
        if ':' not in line: continue
        line = line.split(':')[-1]
        if quitmsg in line:
          return line
        #if 'You ENCOUNTER ' in line: # Starting combat
        #if 'You meet ' in line:      # Meet a civilian
        #if attacked, and hp falls below a threshhold ...
        print('  unhandled: \"'+line+'\"')

  def cityrank(self,city):
    if city=='Chicago': return 4
    if city=='Delaware': return 3
    if city=='Seattle': return 2
    return 1

  def walkpath(self,path):
    print('  Entering walkpath, path = '+str(path))
    for point in path:
      print('  Point = '+point)
      self.irc.privmsg(self.lambbot, '#goto ' + point)
      self.awaitresponse(entermsg[point])

  def gotoloc(self,location):
    self.irc.privmsg(self.lambbot, '#party')
    currloc = ''
    while currloc == '':
      resp = self.irc.get_response()
      # You are {inside,outside,fighting,exploring,going}
      # leave whatever location we are in, or enter if it is right
      for line in resp.split('\n'):
        if self.lambbot not in line or self.irc.username not in line: continue
        if ':' not in line: continue
        line = line.strip().split(':')[-1]
        print('The line = \"'+line+'\"')
        if line.startswith('You are inside'):
          if location in line:
            return
          self.irc.privmsg(self.lambbot, '#leave')
          self.irc.get_response()
          return self.gotoloc(location)
        elif line.startswith('You are outside'):
          print('You are outside is in line')
          if location in line:
            print('Location is in line')
            self.irc.privmsg(self.lambbot, '#enter')
            self.irc.get_response()
            return
          # last word
          print('Setting currloc')
          currloc = line.split(' ')[-1]
          print(currloc)
          if currloc[-1] == '.':
            currloc = currloc[:-1]
          print(currloc)
        elif line.startswith('You are fighting'): # any combat logic
          time.sleep(30)
          return self.gotoloc(location)
        elif line.startswith('You are'): # exploring / going to
          print('Matching the last you are ... saying stop')
          self.irc.privmsg(self.lambbot, '#stop')
          self.irc.get_response()
          return self.gotoloc(location)
    dstcity = location.split('_')[0]
    srccity = currloc.split('_')[0]
    if dstcity == srccity:
      return self.walkpath([location])
    # we are in a different city
    if 'Subway' not in currloc:
      self.walkpath(['Subway'])
      return self.gotoloc(location)
    # For subway Chicago <-> Delaware <-> Seattle <-> Redmond
    if srccity == 'Redmond' or self.cityrank(srccity) > self.cityrank(dstcity):
      self.irc.privmsg(self.lambbot, '#travel 1')
    else:
      self.irc.privmsg(self.lambbot, '#travel 2')
    self.gotoloc(location)

  def getbacon(self, fncounter=0):
    if fncounter < 1:
      self.gotoloc('Redmond_OrkHQ')
    else:
      self.irc.privmsg(self.lambbot, '#enter')
      self.awaitresponse('You enter the ork headquarters.')
    self.walkpath(['OrkHQ_StorageRoom','Exit'])
    self.irc.privmsg(self.lambbot, '#leave')
    self.awaitresponse('You arrive at Redmond.')

  def printloop(self):
    while not self.doquit:
      func = str(self.doloop)
      if func != 'None':
        fncounter = 0
        while not self.doquit and func == str(self.doloop):
          getattr(self,func)(fncounter)
          fncounter+=1
          time.sleep(3)
      else:
        self.irc.get_response()
        time.sleep(15)

