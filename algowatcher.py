import telegram
import logging
from telegram.ext import Updater, CommandHandler
from telegram.ext import MessageHandler, Filters
from algosdk.v2client import algod
from datetime import datetime
from time import sleep
import threading

planetAssetId = 27165954
algoNodeAddress = "http://NODE-URL:NODE-PORT"
algoNodeToken = "Algorand Node API Token"
botToken = 'Telegram API Token'

algoClient = algod.AlgodClient(algoNodeToken, algoNodeAddress)
monitor = False
localContext = {}

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
    message = "Hello. You can type the following commands \n \t /start  - Display this menu \n \t /address <new address value> - Algorand Address for bot to monitor \n \t /getAlgoBalance - Get Current Balance (Note: Address must be set using /address first) \n \t /getPlanetBalance - Get Current  Planet Balance (Note: Address must be set using /address first) \n \t /getAssetBalance <AssetId> - Get Current Asset Balance \n \t /startPlanetMonitor - Monitor Address to see if Planets have stopped being sent to the Account. This command will alert every 30 seconds if no new Planets are detected. \n \t /stopPlanetMonitor - Disable Planet Monitoring"
    context.bot.send_message(chat_id=update.effective_chat.id, text=message)

def updateAddress(update, context):
    context.user_data[update.effective_chat.id] = {'address' : context.args[0], 'monitor' : False, 'asset': 0, 'startTime': datetime(70,1,1), 'interval': 30}
    message = "Address updated to " + str(context.args[0])
    context.bot.send_message(chat_id=update.effective_chat.id, text=message)


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

def monitorAsset():
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
                           localContext.bot.send_message(chat_id=userId, text="No New Planets Detected. Please Make sure your Sensor and App are still active")
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
       algoAddress = context.user_data[update.effective_chat.id].get('address')
   except:
       message = "No Address set. Set address using /address"
       context.bot.send_message(chat_id=update.effective_chat.id, text=message)
       return

   try:
       balance = getAssetBalance(algoAddress, context.args[0])
       message = "Account Balance for Asset ID " + str(context.args[0]) + ": {}".format(balance)
   except:
       message = "No Balance found for Asset ID " + str(context.args[0])

   context.bot.send_message(chat_id=update.effective_chat.id, text=message)

def echo(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)
    context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)
    context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)

def unknown(update, context):
    message = "Unknown Command. Type /start to see list of available commands"
    context.bot.send_message(chat_id=update.effective_chat.id, text=message)





bot = telegram.Bot(token=botToken)
updater = Updater(token=botToken, use_context=True)
dispatcher = updater.dispatcher


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)


start_handler = CommandHandler('start', start)
address_handler = CommandHandler('address', updateAddress)
algo_balance_handler = CommandHandler('getAlgoBalance', getAlgoBalance)
planet_balance_handler = CommandHandler('getPlanetBalance', getPlanetBalance)
#planet_monitor_handler = CommandHandler('monitorPlanets', monitorPlanets)
planet_monitor_handler = CommandHandler('startPlanetMonitor', startMonitor)
planet_monitor_disable_handler = CommandHandler('stopPlanetMonitor', stopMonitor)
#echo_handler = MessageHandler(Filters.text & (~Filters.command), echo)
asset_balance_handler = CommandHandler('getAssetBalance', getAssetBalanceCmd)
unknown_handler = MessageHandler(Filters.command, unknown)

t = threading.Thread(target=monitorAsset)
t.setDaemon(True)
t.start()

dispatcher.add_handler(start_handler)
dispatcher.add_handler(address_handler)
dispatcher.add_handler(algo_balance_handler)
dispatcher.add_handler(planet_balance_handler)
#dispatcher.add_handler(echo_handler)
dispatcher.add_handler(asset_balance_handler)
dispatcher.add_handler(planet_monitor_handler)
dispatcher.add_handler(planet_monitor_disable_handler)
dispatcher.add_handler(unknown_handler)
updater.start_polling()
updater.idle()
