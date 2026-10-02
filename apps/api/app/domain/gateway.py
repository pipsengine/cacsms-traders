from abc import ABC,abstractmethod
class TradingGateway(ABC):
 @abstractmethod
 def health(self): ...
 @abstractmethod
 def account_snapshot(self,account): ...
class LocalMT5Gateway(TradingGateway):
 def health(self): return {'status':'DISCONNECTED','adapter':'LOCAL_MT5','message':'Local MT5 adapter foundation installed; terminal binding intentionally not enabled.'}
 def account_snapshot(self,account): return {'status':'NOT_CONNECTED','account_id':account.get('id')}
