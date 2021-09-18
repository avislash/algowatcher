import telegram
import logging
import pickle
import threading
import requests
import json
import math
import base64

from telegram.ext import Updater, CommandHandler, PicklePersistence
from telegram.ext import MessageHandler, Filters
from algosdk.v2client import algod
from datetime import datetime, timezone, timedelta
from time import sleep
from util import util
from mongoengine import connect
from db.AlgoWatcherAcct import AlgoWatcherAcct 


#Global variables. These objects need to be used by the command call back functions  below
#But there's no way of initializing them in main() and passing them in when handling
#the commands
algoClient = {}
planetAssetId = 27165954 #Asset ID for Planet ASA
planetAssetScaleFactor = 1e-6
version="2.0.0"

#Displays the start menu whenever user types /start in Telegram chat
#This contains all commands available to user along with brief description
def start(update, context):
    global version
    greeting_str = "Hello and welcome to AlgoWatcher v{}. You can type the following commands:\n\t\n".format(version)
    start_str = " /start  - Display this menu\n\t"
    address_str = "/addAcct <new address value> - Register Algorand Account for bot to monitor\n\t"
    listAcct_str = "/listAccts - List all registered accounts and monitor status\n"
    getAlgoBal_str = "/getAlgoBalance - Get Current ALGO Balance for all registred Algorand Accounts\n\t"
    getPlanetBal_str = "/getPlanetBalance - Get Current PLANET Balance for all registered Algorand Accounts\n\t"
    getAssetBal_str = "/getAssetBalance <acctIndex=index> <assetId=id> - Get Current Asset Balance for specified asset and account\n\t" 

    startMonitor_str = "\n/startPlanetMonitor acctIndex=index interval=period txnsPerInterval=num - Monitor Registered Account at index to verify the specified number of Planet Transactions have occured. This command will alert the user if 1 or more Planet Transactions are not detected at the specified interval. The default frequency is 2.5m but can be changed by specifing in seconds or minutes. The default transactions per monitor period is set to 1. No supplied interval or txnsPerInterval will use last set values. See example usage below. \n\t Ex: Only 1 account: /startPlanetMonitor interval=45s - Monitor every 45s. \n       /startPlanetMonitor acctIndex=2 interval=14.5m txnsPerInterval=2 - Monitor for 2 Planet Txns every 14.5 minutes. \n      /startPlanetMonitor acctIndex=0 - Start Monitor at last stored frequency and Tx/freq values\n\n\t"

    stopMonitor_str = "/stopPlanetMonitor acctIndex=index - Disable Planet Monitoring at <index>.\n\t\n"
    planetpayout_str = "/getLastPlanetPayout - Query Amount and Timestamp of the last Planet Payout for all registered accounts\n\t\n"
    average_payout_str = "/getAveragePlanetPayout - Get Running 7 Day Average Planet Payout for all registered accounts\n\t\n"
    deleteAcct_str = "/deleteAcct acctIndex=index - Delete/unregister the account at index from the bot's database\n"
    note_str = "NOTE: Account Index for all commands only needs to be specified if more than 1 Algorand Account is registered\n\n"
    coffe_str = "Like the bot and want to buy the developer coffe? Send ALGO to ONPJRXNOOAIZVJ3VPSZKFGBMSYQRACNZUMW5P6FNQTKUZ3BALYCDBUMNAM\n\n"
    support_str = "For Questions, Suggestions, and Feedback join the AlgoWatchers Telegram Group (t.me/algowatchers).\n" 

    final_str = coffe_str + support_str

    message = greeting_str + start_str + address_str + listAcct_str + getAlgoBal_str + getAssetBal_str + getPlanetBal_str + startMonitor_str + stopMonitor_str + planetpayout_str + average_payout_str + deleteAcct_str + note_str+ final_str
    context.bot.send_message(chat_id=update.effective_chat.id, text=message)

#Sets the Algo Public Address to monitor/query balances for
#and also initializes the user_data dictionary for the user
def addAcct(update, context):
   algoAddress = ''
   if len(context.args) > 0: 
       chatId=update.effective_chat.id
       account = AlgoWatcherAcct(chatId=chatId , address=context.args[0], monitorEnable=False, txnsPerInterval=1, interval= 150,  monitorTime=datetime.utcnow())
       account.save()
       message = "Registered Algorand account " + context.args[0] + " \n Total Accounts Registered: {}".format(AlgoWatcherAcct.objects(chatId=chatId).count())
   else:
       message = "No Address provided"

   context.bot.send_message(chat_id=update.effective_chat.id, text=message)

def listAccts(update, context):
   chatId = update.effective_chat.id
   accounts = AlgoWatcherAcct.objects(chatId=chatId)
   if len(accounts) > 0:
       message = "Accounts:\n"
       i = 0
       for account in accounts:
           message = message + "Acct {}: ".format(i) + account['address'] + " - txnsPerInterval: {}".format(account['txnsPerInterval']) + ", interval: {}".format(util.intervalToStr(account['interval'])) +", monitorEnabled: {}\n".format(account['monitorEnable'])
           i+=1

       context.bot.send_message(chat_id=chatId, text=message)
   else:
       context.bot.send_message(chat_id=chatId, text="No accounts registered. Use /addAcct to register an account")

def deleteAcct(update, context):
   chatId = update.effective_chat.id
   numAccounts = AlgoWatcherAcct.objects(chatId=chatId).count()
   args =  util.parseArgs(context.args)

   if numAccounts > 0:
       accounts = AlgoWatcherAcct.objects(chatId=chatId)
       if 1 == numAccounts:
           acctIndex = 0
       elif 'acctindex' in args and int(args['acctindex']) >= 0  and int(args['acctindex']) < numAccounts:
           acctIndex = int(args['acctindex'])
       else:
           context.bot.send_message(chat_id=chatId, text="Invalid account index provided. Pick valid index from list below: ")
           listAccts(update, context)
           return

       accounts[acctIndex].delete()
       context.bot.send_message(chat_id=chatId, text="Deleted Acct #{}".format(acctIndex))
       listAccts(update, context)
   else:
       context.bot.send_message(chat_id=chatId, text="No accounts registered. Use /addAcct to register an account")

#Method to query amount of ASA Txns an account has had since
#a given time interval
def getASATxns(address, time, asaId):
    txn_base_url =  "https://algoexplorerapi.io/idx2/v2/accounts/"
    txn_info =  "/transactions?tx-type=axfer&asset-id=" + str(asaId)
    time_str = "&after-time="+time.isoformat()+"Z"
    txn_url = txn_base_url+address+txn_info+time_str
    acct_info = json.loads(requests.get(txn_url).text)
    return acct_info['transactions']
    
#Helper method to get the number of Planet Transactions
#an account has received since an indicated time
def getPlanetTxns(address, time):
    return getASATxns(address, time, planetAssetId)

#Method to compute the running 7-day average
#of all Planet Payouts for the given address
def getAveragePlanetPayout(address):
    txnKey = 'asset-transfer-transaction'
    today = datetime.utcnow().isoformat() + "Z"
    lastWeek = (datetime.utcnow() - timedelta(days=7)).isoformat() + "Z"
    txn_base_url =  "https://algoexplorerapi.io/idx2/v2/accounts/" + address
    txn_info =  "/transactions?tx-type=axfer&asset-id=" + str(planetAssetId)
    end_time = "&before-time=" + today
    start_time = "&after-time="+ lastWeek
    val="&currency-greater-than=1"
    txn_url = txn_base_url + txn_info + start_time + end_time + val
    acct_info = json.loads(requests.get(txn_url).text)
    txns = acct_info['transactions']
    numTxns = 0
    amount = 0

    for txn in txns:
        if txnKey in txn:
            amount = amount + txn[txnKey]['amount']
            numTxns = numTxns + 1

    if numTxns > 0 : 
        amount = amount/numTxns

    return amount*planetAssetScaleFactor
    
#Method to get the last Planet Paid out for
#the given address
def getLastPlanetPayout(address):
    now = datetime.utcnow().isoformat() + "Z"
    txn_base_url =  "https://algoexplorerapi.io/idx2/v2/accounts/" + address
    txn_info =  "/transactions?tx-type=axfer&asset-id=" + str(planetAssetId)
    before_time = "&before-time=" + now
    val="&currency-greater-than=1"
    txn_url = txn_base_url + txn_info + before_time + val
    acct_info = json.loads(requests.get(txn_url).text)
    last_txn = acct_info['transactions'][0]
    note = last_txn['note']
    time = last_txn['round-time']
    amount = last_txn['asset-transfer-transaction']['amount'] * planetAssetScaleFactor
    return [amount, time, note]

#Helper function that gets the current number of ASA Tokens denoted by assetId
#in located at the public Algorand Address (algoAddress)
def getAssetBalance(algoAddress, assetId):
   global algoClient
   balance = 0
   account_info = algoClient.account_info(algoAddress)
   assets = account_info.get('assets')

   for asset in assets:
       if asset.get('asset-id') == int(assetId):
           balance = asset['amount']

   return balance


#Gets the current Amount of ALGO in 
#in the wallet address that was set using /address (updateAddress)
#Query all registered Algorand Address (set by addAcct)
#for current ALGO Balance (Algorand ASA)
def getAlgoBalance(update, context):
   global algoClient
   chatId = update.effective_chat.id
   addresses = AlgoWatcherAcct.objects(chatId=chatId).distinct('address')
   if len(addresses) > 0: 
       message = ""
       for algoAddress in addresses:
           try:
               account_info = algoClient.account_info(algoAddress)
               balance = account_info.get('amount')*1e-6
               message = message + "Account {} Balance: {} ALGO\n".format(algoAddress, format(balance, '.6f'))
           except:
               message = message + "Error getting balance for Account {}\n".format(algoAddress)
   else:
       message = "No accounts registered. Use /addAcct to register an account"

   context.bot.send_message(chat_id=chatId, text=message)

#Query all registered Algorand Address (set by addAcct)
#for current Planet Balance (Algorand ASA)
def getPlanetBalance(update, context):
   global algoClient
   global planetAssetId
   chatId = update.effective_chat.id
   addresses = AlgoWatcherAcct.objects(chatId=chatId).distinct('address')
   if len(addresses) > 0: 
       message = ""
       for algoAddress in addresses:
           try:
               balance = getAssetBalance(algoAddress, planetAssetId)*1e-6
               message = message + "Account {} Balance: {} PLANET\n".format(algoAddress, format(balance, '.3f'))
           except:
               message = message + "Error getting balance for Account {}\n".format(algoAddress)
   else:
       message = "No accounts registered. Use /addAcct to register an account"

   context.bot.send_message(chat_id=chatId, text=message)


#Enable Planet monitoring for Telegram user
#If no arguments are specified then the account will be
#monitor at the last set interval (default 30 seconds)
def startMonitor(update, context):
   chatId = update.effective_chat.id
   numAccounts = AlgoWatcherAcct.objects(chatId=chatId).count()
   accounts = AlgoWatcherAcct.objects(chatId=chatId)
   args = util.parseArgs(context.args)

   if 0 == numAccounts:
       context.bot.send_message(chat_id=chatId, text="No accounts registered. Use /addAcct to register an account")
       return

   if 1 == numAccounts:
       acctIndex = 0
   elif not 'acctindex' in args or int(args['acctindex']) < 0 or int(args['acctindex']) >= numAccounts:
       context.bot.send_message(chat_id=chatId, text="Invalid account index provided. Pick valid index from list below: ")
       listAccts(update, context)
       return
   else:
       acctIndex = int(args['acctindex'])
       
   if 'interval' in args:
       interval = util.getInterval(args['interval'])
       accounts[acctIndex].update(interval=interval)
   
   if 'txnsperinterval' in args:
       if int(args['txnsperinterval']) >= 0:
           accounts[acctIndex].update(txnsPerInterval=int(args['txnsperinterval']))
           

   accounts[acctIndex].update(monitorEnable=True)
   accounts[acctIndex].update(monitorTime=datetime.utcnow())

   txStr = accounts[acctIndex]['address'] + " for " + str(accounts[acctIndex]['txnsPerInterval'])

   txStr = txStr + " " +  ("transactions" if accounts[acctIndex]['txnsPerInterval'] != 1 else "transaction")

   message = "Monitor Enabled. Monitoring " + txStr + " every " + util.intervalToStr(accounts[acctIndex]['interval'])
   context.bot.send_message(chat_id=update.effective_chat.id, text=message)
 
#Disable Planet Monitoring for Telegram user
def stopMonitor(update, context):
   chatId = update.effective_chat.id
   numAccounts = AlgoWatcherAcct.objects(chatId=chatId).count()
   accounts = AlgoWatcherAcct.objects(chatId=chatId)
   args = util.parseArgs(context.args)

   if 0 == numAccounts:
       context.bot.send_message(chat_id=chatId, text="No accounts registered. Use /addAcct to register an account")
       return

   if 1 == numAccounts:
       acctIndex = 0
   elif not 'acctindex' in args or int(args['acctindex']) < 0 or int(args['acctindex']) >= numAccounts:
       context.bot.send_message(chat_id=chatId, text="Invalid account index provided. Pick valid index from list below: ")
       listAccts(update, context)
       return
   else:
       acctIndex = int(args['acctindex'])
   
   accounts[acctIndex].update(monitorEnable=False)

   context.bot.send_message(chat_id=update.effective_chat.id, text="Monitor disabled for " + accounts[acctIndex]['address'])

def getAveragePlanetPayoutCmd(update, context):
   chatId = update.effective_chat.id
   addresses = AlgoWatcherAcct.objects(chatId=chatId).distinct('address')

   if len(addresses) > 0:
       message = ""
       for algoAddress in addresses:
           try:
               amount = getAveragePlanetPayout(algoAddress)
               message = message + "{}\n{} PLANET paid out on average over the last 7 days\n\n".format(algoAddress, amount) 
           except:
               message = message + "No Planet Payouts found for {}\n\n".format(algoAddress)
   else:
       message = "No accounts registered. Use /addAcct to register an account"

   context.bot.send_message(chat_id=chatId, text=message)

#Callback function for reporting the last 
#recorded Planet payout to the user
def getLastPlanetPayoutCmd(update, context):
   chatId = update.effective_chat.id
   addresses = AlgoWatcherAcct.objects(chatId=chatId).distinct('address')

   if len(addresses) > 0:
       message = ""
       for algoAddress in addresses:
           try:
               [amount, round_time, note] = getLastPlanetPayout(algoAddress)
               timestamp = datetime.fromtimestamp(round_time, tz=timezone.utc).strftime("%B %d, %Y %H:%M:%S UTC")#datetime.utcfromtimestamp(round_time).strftime("%B %d, %Y %H:%M:%S UTC")
               planet_str = format(amount, '.3f') + " PLANET"
               message = message + "{} paid out on {} to {} with note:\n {}\n\n".format(planet_str, timestamp, algoAddress, base64.b64decode(note)) 
           except Exception as e:
               message = message + "No Planet Payouts found for account {}\n\n".format(algoAddress) 
               print(e)

   else:
        message = "No accounts registered. Use /addAcct to register an account"
   
   context.bot.send_message(chat_id=update.effective_chat.id, text=message)
    
#Query  Algorand Addres (set by updateAddress) 
#for Algorand ASA Balance denoted by
#passed in Asset ID (context.args[0]) 
def getAssetBalanceCmd(update, context):
   chatId = update.effective_chat.id
   numAccounts = AlgoWatcherAcct.objects(chatId=chatId).count()
   accounts = AlgoWatcherAcct.objects(chatId=chatId)
   args = util.parseArgs(context.args)

   if not 'assetid' in args:
       context.bot.send_message(chat_id=update.effective_chat.id, text="No ASA Asset Id specified")
       return

   if 0 == numAccounts:
       context.bot.send_message(chat_id=update.effective_chat.id, text="No accounts registered. Use /addAcct to register an account")
       return

   if 1 == numAccounts:
       acctIndex = 0
   elif numAccounts > 1 and (not 'acctindex' in args or int(args['acctindex']) < 0 or int(args['acctindex']) >= numAccounts):
       context.bot.send_message(chat_id=chatId, text="Invalid account index provided. Pick valid index from list below: ")
       listAccts(update, context)
   else:
       acctIndex = int(args['acctindex'])

   #The Indexer must be used to get ASA Meta data such as unit-name and
   #this requires an archival node. Instead of running my own archical ndoe
   #I instead grab this information using the AlgoExploer API
   algoExplorerAssetUrl = "https://api.algoexplorer.io/idx2/v2/assets/"
   algoExplorerAssetUrl= algoExplorerAssetUrl + str(args['assetid'])
   
   asset_info = json.loads(requests.get(algoExplorerAssetUrl).text)

   #Make sure ASA ID provided is valid
   if "asset" in asset_info:
       try:
           balance = getAssetBalance(accounts[acctIndex]['address'], args['assetid'])

           scaleFactor = 10 ** (-1*asset_info["asset"]["params"]["decimals"])
           balance = balance*scaleFactor
           units = asset_info["asset"]["params"]["unit-name"]
           message = accounts[acctIndex]['address'] + "\nAccount Balance for Asset ID " + str(args['assetid']) + ": {}".format(balance) + " " + units
       except:
           message = "No Balance found for Asset ID {} for Account{}\n ".format(args['assetid'], accounts[acctIndex]['address'])
   else:
       message = "Invalid Asset ID {}".format(args['assetid'])

   context.bot.send_message(chat_id=update.effective_chat.id, text=message)

def getStats(update, context):
    numUsers = AlgoWatcherAcct.objects().distinct('chatId')
    numAddresses = AlgoWatcherAcct.objects().count()
    message = "Number of registered users {} watching {} addresses".format(len(numUsers), numAddresses)
    context.bot.send_message(chat_id=update.effective_chat.id, text=message)
    

#Used when an unregistered command comes in
def unknown(update, context):
    message = "Unknown Command. Type /start to see list of available commands"
    context.bot.send_message(chat_id=update.effective_chat.id, text=message)

#Monitor Thread for mointoring Planets
#Thread will report to Telegram User if no new
#Planets came in over the set Monitor Interval
#TODO: Update to be able to monitor any existing ASA
def monitorAsset(dispatcher):

   while True:
       #Get all monitor enabled accounts sorted by earliest time
       accounts = AlgoWatcherAcct.objects(monitorEnable=True).order_by('monitorTime')
       for account in accounts:
           elapsedTime = (datetime.utcnow() - account['monitorTime']).total_seconds()
           if elapsedTime >= account['interval']:
               try:
                   account.update(monitorTime=datetime.utcnow())
                   numTxns = len(getPlanetTxns(account['address'], account['monitorTime']))
                   if numTxns < account['txnsPerInterval']:
                       message = "No New Planet Transactions Detected for " + account['address']

                       if account['txnsPerInterval'] > 1 :
                           message = message + ": Expected {} transactions | Got {} transaction{}".format(account['txnsPerInterval'], numTxns, "s" if numTxns != 1 else "")  
                      
                       message =  message + ". Please make sure your Sensor and App are still active." 
                       dispatcher.bot.send_message(chat_id=account['chatId'], text=message)
               except Exception as e:
                   try:
                       dispatcher.bot.send_message(chat_id=account['chatId'], text="Unable to get transaction status for {}".format(account['address']))
                       print("Unable to get transaction status for User {} (id #{}) address #{}".format(dispatcher.bot.get_chat(account['chatId']).username, account['chatId'], account['address']))
                       print("Exception: {}".format(e))
                   except Exception as e:
                       print("Alerting user {} of failure failed: Reason {}".format(account['chatId'],e))

       sleep(1)

def main():
   global algoClient
   global localContext
   with open('bot.pickle', "rb") as file:
       botProperties = pickle.load(file)

   algoNodeAddress = botProperties.get('algoNodeAddress') #algoNodeAddress = "http://NODE-URL:NODE-PORT"
   algoNodeToken = botProperties.get('algoNodeToken') #algoNodeToken = "Algorand Node API Token"
   botToken = botProperties.get('botToken') #botToken = 'Telegram API Token'
   #botToken = botProperties.get('testBotToken') #botToken = 'Telegram API Token'

   connect(db=botProperties['main_db'], host=botProperties['db_host'], port=botProperties['db_port'])
   #connect(db=botProperties['test_db'], host=botProperties['db_host'], port=botProperties['db_port'])

   algoClient = algod.AlgodClient(algoNodeToken, algoNodeAddress)
   updater = Updater(token=botToken, use_context=True)
   dispatcher = updater.dispatcher

   logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

   start_handler = CommandHandler('start', start)
   address_handler = CommandHandler('addAcct', addAcct)
   algo_balance_handler = CommandHandler('getAlgoBalance', getAlgoBalance)
   planet_balance_handler = CommandHandler('getPlanetBalance', getPlanetBalance)
   planet_monitor_handler = CommandHandler('startPlanetMonitor', startMonitor)
   planet_monitor_disable_handler = CommandHandler('stopPlanetMonitor', stopMonitor)
   asset_balance_handler = CommandHandler('getAssetBalance', getAssetBalanceCmd)
   planet_payout_handler = CommandHandler('getLastPlanetPayout', getLastPlanetPayoutCmd)
   average_planet_payout_handler = CommandHandler('getAveragePlanetPayout', getAveragePlanetPayoutCmd)
   list_acct_handler = CommandHandler('listAccts', listAccts)
   stats_handler = CommandHandler('stats', getStats)
   delete_acct_handler = CommandHandler('deleteAcct', deleteAcct)
   unknown_handler = MessageHandler(Filters.command, unknown)


   dispatcher.add_handler(start_handler)
   dispatcher.add_handler(address_handler)
   dispatcher.add_handler(algo_balance_handler)
   dispatcher.add_handler(planet_balance_handler)
   dispatcher.add_handler(asset_balance_handler)
   dispatcher.add_handler(planet_monitor_handler)
   dispatcher.add_handler(planet_monitor_disable_handler)
   dispatcher.add_handler(planet_payout_handler)
   dispatcher.add_handler(average_planet_payout_handler)
   dispatcher.add_handler(list_acct_handler)
   dispatcher.add_handler(delete_acct_handler)
   dispatcher.add_handler(stats_handler)
   dispatcher.add_handler(unknown_handler)

   t = threading.Thread(target=monitorAsset, args=([dispatcher]))
   t.setDaemon(True)
   t.start()

   updater.start_polling()
   updater.idle()

if __name__ == "__main__":
   main()
