import filecmp
import bsdiff4
import json

class L1:
    def __init__(self,name,path,url):
        self.name = name
        self.path = path
        self.url = url

    def install(self):
        pass
    def update(self):
        pass
    def verify(self):
        pass

    @property
    def name(self):
        return self.name
    @name.setter
    def name(self, value):
        self._name = value

    @property
    def installed_version(self) -> [str|None]: # Returns None if there is no version installed, or there's been no initialisation.
        pass
    @property
    def latest_version(self) -> [str|None]:
        pass


