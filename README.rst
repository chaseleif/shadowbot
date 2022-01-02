========================================================
ShadowBot  
========================================================
  
| This is an IRC bot designed to talk to another IRC bot  
| This bot will automate gameplay for the IRC game - *ShadowLamb*  
|  
  
========================================================
startbot.py  
========================================================
  
| This is the driver script  
| This script *requires* to load a password file,  
| the login credentials for your bot should be in a file ``pass``  
|  
| ``$ cat pass``  
| ``username``  
| ``password``  
|  
| The password are not kept in memory after use  
| The rest of the interaction is through the CLI menus provided  
|  
  
========================================================
bot.py  
========================================================
  
| This is the script specific to the ShadowLamb bot  
| There are various helper functions included within  
| Additional scripted functions and modifications would go here  
|  
  
========================================================
irchandler.py  
========================================================
  
| This script provides a class which handles the IRC connection  
| It should not be necessary to modify this script  
| This script is general enough to be used as a base for other IRC scripts  
|  
