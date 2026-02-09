import peewee as pw
from datetime import datetime

db = pw.SqliteDatabase(None)


class BaseModel(pw.Model):
    class Meta:
        database = db


class Order(BaseModel):
    symbol = pw.CharField()
    side = pw.CharField()              # buy / sell
    order_type = pw.CharField()        # market / limit
    price = pw.FloatField(null=True)
    amount = pw.FloatField()
    status = pw.CharField(default="pending")  # pending / filled / cancelled
    exchange_id = pw.CharField(null=True)
    created_at = pw.DateTimeField(default=datetime.now)


class Trade(BaseModel):
    order = pw.ForeignKeyField(Order, backref="trades")
    price = pw.FloatField()
    amount = pw.FloatField()
    fee = pw.FloatField(default=0)
    executed_at = pw.DateTimeField(default=datetime.now)


def init_db(path="tb.db"):
    db.init(path)
    db.connect()
    db.create_tables([Order, Trade])
