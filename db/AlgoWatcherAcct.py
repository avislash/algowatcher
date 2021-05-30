from mongoengine import Document, StringField, LongField, BooleanField, DateTimeField
class AlgoWatcherAcct(Document):
    chatId = LongField(required=True)
    address = StringField(required=True)
    monitorEnable = BooleanField(required=True)
    interval = LongField(required=True)
    txnsPerInterval = LongField(required=True)
    monitorTime = DateTimeField(required=True)
    meta = {"indexes": [('-monitorEnable', 'monitorTime')]}

