import telegram
import logging
import pickle
import threading
import requests
import json

from telegram.ext import Updater, CommandHandler, PicklePersistence
from telegram.ext import MessageHandler, Filters
from algosdk.v2client import algod
from datetime import datetime
from time import sleep

algoClient = {}
localContext = {}
planetAssetId = 27165954
init = False;

def _init(update, context):
   global localContext
   if False == init:
       localContext = context
       context.bot.send_message(chat_id=update.effective_chat.id, text="Initialized")


def getAssetBalance(algoAddress, assetId):
   global algoClient

   balance = 0
   account_info = algoClient.account_info(algoAddress)
   assets = account_info.get('assets')

   for asset in assets:
       if asset['asset-id'] == int(assetId):
           balance = asset['amount']
   return balance

def start(update, context):
    greeting_str = "Hello. You can type the following commands:\n\t\n"
    start_str = " /start  - Display this menu\n\t"
    address_str = "/address <new address value> - Algorand Address for bot to monitor\n\t"
    getAlgoBal_str = "/getAlgoBalance - Get Current Balance (Note: Address must be set using /address first)\n\t"
    getPlanetBal_str = "/getPlanetBalance - Get Current  Planet Balance (Note: Address must be set using /address first)\n\t"
    getAssetBal_str = "/getAssetBalance <AssetId> - Get Current Asset Balance\n\t" 
    startMonitor_str = "/startPlanetMonitor - Monitor Address to see if Planets have stopped being sent to the Account. This command will alert every 30 seconds if no new Planets are detected.\n\t" 
    stopMonitor_str = "/stopPlanetMonitor - Disable Planet Monitoring\n\t"
    monitorStatus_str = "/getMonitorStatus - Check if Planet Monitoring is enabled/disabled\n\t\n"

    coffe_str = "Like the bot and want to buy the developer coffe? Send an algo to ONPJRXNOOAIZVJ3VPSZKFGBMSYQRACNZUMW5P6FNQTKUZ3BALYCDBUMNAM\n\n"
    support_str = "For Questions, Suggestions, and Feedback join the AlgoWatchers Telegram Group (telegram.me/algowatchers).\n" 

    final_str = coffe_str + support_str

    message = greeting_str + start_str + address_str + getAlgoBal_str + getAssetBal_str + getPlanetBal_str + startMonitor_str + stopMonitor_str + monitorStatus_str + final_str
    context.bot.send_message(chat_id=update.effective_chat.id, text=message)

def updateAddress(update, context):
    global localContext
    context.user_data[update.effective_chat.id] = {'address' : context.args[0], 'monitor' : False, 'asset': 0, 'startTime': datetime(70,1,1), 'interval': 30}
    message = "Address updated to " + str(context.args[0])
    context.bot.send_message(chat_id=update.effective_chat.id, text=message)
    localContext = context

def getAlgoBalance(update, context):
    global algoClient
    try:
        algoAddress = context.user_data[update.effective_chat.id].get('address')
        account_info = algoClient.account_info(algoAddress)
        balance = account_info.get('amount')*1e-6
        message = "Account Balance: {} Algo".format(balance)
    except:
        message = "No valid address found. Please store address with /address first"

    context.bot.send_message(chat_id=update.effective_chat.id, text=message)

def getPlanetBalance(update, context):
    global algoClient
    global planetAssetId
    try:
        algoAddress = context.user_data[update.effective_chat.id].get('address')
        balance = getAssetBalance(algoAddress, planetAssetId)*1e-6
        message = "Account Balance: {} Planets".format(balance)
    except:
        message = "No valid address found. Please store address with /address first"

    context.bot.send_message(chat_id=update.effective_chat.id, text=message)

def monitorAsset(dispatcher):
   global algoClient
   global planetAssetId
   global localContext

   while True:
       if localContext:
           for userId in localContext.user_data:
               user_data = localContext.user_data[userId]
               if True == user_data.get('monitor'):
                   time_elapsed = (datetime.now() - user_data.get('startTime')).total_seconds()
                   if time_elapsed >= user_data.get('interval'):
                       planetsNow = getAssetBalance(user_data.get('address'), planetAssetId)
                       if planetsNow == user_data.get('asset'):
                           dispatcher.bot.send_message(chat_id=userId, text="No New Planets Detected. Please Make sure your Sensor and App are still active")
                       user_data['asset'] = planetsNow
                       user_data['startTime'] = datetime.now()
           sleep(1)

def startMonitor(update, context):
   global localContext
   try:
       context.user_data[update.effective_chat.id]['monitor'] = True
       localContext = context
       context.bot.send_message(chat_id=update.effective_chat.id, text="Monitor Enabled")
   except:
       context.bot.send_message(chat_id=update.effective_chat.id, text="Unable to start monitor. Make sure you set an address with /address first")
    
def stopMonitor(update, context):
    global localContext
    try:
        context.user_data[update.effective_chat.id]['monitor'] = False
        localContext = context
    except:
        pass

    context.bot.send_message(chat_id=update.effective_chat.id, text="Monitor Stopped")

def getAssetBalanceCmd(update, context):
   try:
       assetId = context.args[0]
   except:
       context.bot.send_message(chat_id=update.effective_chat.id, text="No Asset ID Provided")
       return
   algoExplorerAssetUrl = "https://api.algoexplorer.io/idx2/v2/assets/"
   algoExplorerAssetUrl= algoExplorerAssetUrl + str(assetId)
   
   asset_info = json.loads(requests.get(algoExplorerAssetUrl).text)

   if "asset" in asset_info:
       try:
           algoAddress = context.user_data[update.effective_chat.id].get('address')
       except:
           message = "No Address set. Set address using /address"
           context.bot.send_message(chat_id=update.effective_chat.id, text=message)
           return

       try:
           balance = getAssetBalance(algoAddress, context.args[0])

           scaleFactor = 10 ** (-1*asset_info["asset"]["params"]["decimals"])
           balance = balance*scaleFactor
           units = asset_info["asset"]["params"]["unit-name"]
           message = "Account Balance for Asset ID " + str(context.args[0]) + ": {}".format(balance) + " " + units
       except:
           message = "No Balance found for Asset ID " + str(context.args[0])
   else:
       message = "Invalid Asset ID " + str(assetId)

   context.bot.send_message(chat_id=update.effective_chat.id, text=message)

def getMonitorStatus(update, context):
   try:
       monitorStatus = context.user_data[update.effective_chat.id].get('monitor')
       if monitorStatus:
           message = "Monitor Enabled"
       else:
           message = "Monitor Disabled"
   except:
       message = "No Monitor Status. Initialize account using /address first"

   context.bot.send_message(chat_id=update.effective_chat.id, text=message)


def echo(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)
    context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)
    context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)

def unknown(update, context):
    message = "Unknown Command. Type /start to see list of available commands"
    context.bot.send_message(chat_id=update.effective_chat.id, text=message)

def main():
   global algoClient
   with open('bot.pickle', "rb") as file:
       botProperties = pickle.load(file)

   algoNodeAddress = botProperties.get('algoNodeAddress') #algoNodeAddress = "http://NODE-URL:NODE-PORT"
   algoNodeToken = botProperties.get('algoNodeToken') #algoNodeToken = "Algorand Node API Token"
   #botToken = botProperties.get('botToken') #botToken = 'Telegram API Token'
   botToken = botProperties.get('testBotToken') #botToken = 'Telegram API Token'

   algoClient = algod.AlgodClient(algoNodeToken, algoNodeAddress)
   persist = PicklePersistence(filename='botContext.pickle')
   bot = telegram.Bot(token=botToken)
   updater = Updater(token=botToken, persistence=persist, use_context=True)
   dispatcher = updater.dispatcher


   logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)


   init_handler = CommandHandler('init', _init)
   start_handler = CommandHandler('start', start)
   address_handler = CommandHandler('address', updateAddress)
   algo_balance_handler = CommandHandler('getAlgoBalance', getAlgoBalance)
   planet_balance_handler = CommandHandler('getPlanetBalance', getPlanetBalance)
   planet_monitor_handler = CommandHandler('startPlanetMonitor', startMonitor)
   planet_monitor_disable_handler = CommandHandler('stopPlanetMonitor', stopMonitor)
   planet_monitor_status_handler = CommandHandler('getMonitorStatus', getMonitorStatus)
   asset_balance_handler = CommandHandler('getAssetBalance', getAssetBalanceCmd)
   unknown_handler = MessageHandler(Filters.command, unknown)


   dispatcher.add_handler(init_handler)
   dispatcher.add_handler(start_handler)
   dispatcher.add_handler(address_handler)
   dispatcher.add_handler(algo_balance_handler)
   dispatcher.add_handler(planet_balance_handler)
   dispatcher.add_handler(asset_balance_handler)
   dispatcher.add_handler(planet_monitor_handler)
   dispatcher.add_handler(planet_monitor_disable_handler)
   dispatcher.add_handler(planet_monitor_status_handler)
   dispatcher.add_handler(unknown_handler)

   t = threading.Thread(target=monitorAsset, args=([dispatcher]))
   t.setDaemon(True)
   t.start()

   updater.start_polling()
   updater.idle()

if __name__ == "__main__":
   main()
