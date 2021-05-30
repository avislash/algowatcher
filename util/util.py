import math

def roundFloat(val):
    decimal = val - int(val)
    if 0.5 <= decimal:
        val = math.ceil(val)
    else:
        val = math.floor(val)

    return int(val)

def getTxnsPerInterval(args):
   txPerInterval = 1
   if len(args) > 1:
       txns = int(args[1])
       txPerInterval = txns if txns > 1 else 1

   return txPerInterval

def getInterval(args):
   MINIMUM_CHECK_INTERVAL = 5 #seconds. Monitor at each new Algorand Block
   interval = MINIMUM_CHECK_INTERVAL #default monitor rate is 30 seconds
   if len(args) > 0:
       if args.find('s') > 0: 
           interval = roundFloat(float(args.split('s')[0]))
       elif args.find('m') > 0:
           interval = args.split('m')[0]
           interval = int(float(interval)*60)

   interval = interval if MINIMUM_CHECK_INTERVAL < interval else MINIMUM_CHECK_INTERVAL

   return interval

def getIntervalUnits(interval):
   units = "seconds"
   if interval > 59:
       units = "minute"
       if (interval/60) > 1:
           units = units + "s"
   return units

def intervalToStr(interval):
    units = getIntervalUnits(interval)
    if interval > 59:
        interval = interval/60

    return str(interval) + " " + units


