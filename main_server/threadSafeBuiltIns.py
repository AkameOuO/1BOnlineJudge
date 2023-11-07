from threading import RLock

def autoLock(cls):
    def decorator(func):
        def new_func(self,*args,**kwargs):
            self._RLock.acquire()
            try:
                ret = func(self,*args,**kwargs)
            finally:
                self._RLock.release()
            return ret
        new_func.__name__ = func.__name__
        return new_func
    cls._RLock = RLock()
    exclude = {"__getattribute__"}
    for attr in cls.__dict__:
        if callable(getattr(cls,attr)) and attr not in exclude:
            setattr(cls,attr,decorator((getattr(cls,attr))))
    for base in cls.__bases__:
        for attr in base.__dict__:
            if callable(getattr(base,attr)) and attr not in cls.__dict__ and attr not in exclude:
                setattr(cls,attr,decorator((getattr(cls,attr))))
    return cls

@autoLock
class TSSet(set): pass

@autoLock
class TSDict(dict):
    def __str__(self):
        return type(self).__name__ + "(" + super().__str__() + ")"
    def __repr__(self):
        return type(self).__name__ + "(" + super().__repr__() + ")"

