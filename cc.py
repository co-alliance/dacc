"""Module is a collection of scripts for migrating Colorado College's
Fedora 3.4 repository to an Islandora 7.x/Fedora 3.7x 
"""
__author__ = "Jeremy Nelson"

import xml.etree.ElementTree as etree
import falcon
import requests
import semantic_server.app as semantic_server

class Migration(object):

    def __init__(self, config):
        self.auth = (config['FEDORA3']['username'],
                     config['FEDORA3']['password'])
        self.fedora_rest_url = "http://{}:{}/fedora/objects".format(
            config['FEDORA3']['host'],
            config['FEDORA3']['port'])

    def get_object(self, pid):
        profile_url = "{}/{}?format=xml".format(self.fedora_rest_url,
                                                pid)
        result = requests.get(profile_url, auth=self.auth)
        if result.status_code >= 399:
            return etree.XML(result.text)


class OralHistory(Migration):

    def on_put(self, req, resp, pid):
        resp.status = falcon.HTTP_201 
        

if __name__ == "__main__":
    semantic_server.main()


