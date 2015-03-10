"""Module is a collection of scripts for migrating Colorado College's
Fedora 3.4 repository to an Islandora 7.x/Fedora 3.7x
"""
__author__ = "Jeremy Nelson"

import xml.etree.ElementTree as etree
import falcon
import rdflib
import requests
import semantic_server
from semantic_server.app import api, config, islandora_datastream
from semantic_server.app import islandora_object, islandora_relationship
import semantic_server.repository.resources.islandora as islandora
from semantic_server.repository.resources.fedora3 import NAMESPACES

class Migration(object):
    FEDORA_ACCESS = 'http://www.fedora.info/definitions/1/0/access/'

    def __init__(self, config=config):
        self.auth = (config['FEDORA3']['username'],
                     config['FEDORA3']['password'])
        self.fedora_rest_url = "http://{}:{}/fedora/objects".format(
            config['FEDORA3']['host'],
            config['FEDORA3']['port'])

    def __add_child_object__(self, pid, element, namespace="coccc"):
        """Internal method takes a PID and datastream element,
        retrieves content from datastream element and creates a
        new Islandora Object with a child relationship to the
        pid (pid must have islandora:compoundCModel compound object.

        Args:
            pid -- PID of parent object
            element -- datastream element
        """
        add_child_result = islandora_object.__add_stub__(
            element.get('label'),
            namespace)
        new_pid = add_child_result.get('pid')
        print("New pid is {}\n{}".format(new_pid, add_child_result))
        # Add as child to PID
        islandora_relationship.__add__(
            "info:fedora/fedora-system:def/relations-external#",
            "isConstituentOf",
            pid,
            new_pid)
        # Set Content Model
        content_model = self.__guess_islandora_content_model__(element.get('mimeType'))
        islandora_relationship.__add__(
            "info:fedora/fedora-system:def/model#",
            "hasModel",
            content_model,
            new_pid)
        print("After adding content_model={} pid={} new pid={}".format(content_model, pid, new_pid))
        # Add original datastream as new Islandora Object Datastream
        self.__add_datastream__(pid, element)



    def __add_datastream__(self, pid, element):
        """Internal method takes a PID and datastream element, retrieves
        content from origin repository and creates a new Islandora datastream
        from the downloaded file.

        Args:
            pid -- pid of Fedora and Islandora Object
            element -- datastream element
        """
        base_url = "/".join([self.fedora_rest_url,
                             pid,
                             "datastreams",
                             element.get('dsid')])
        info_url = "/".join([base_url, "?format=xml"])
        info_xml = self.__get_xml__(info_url)
        download_url = "/".join([base_url, "content?download=true"])
        print("Download url is {}".format(download_url))
        result = requests.get(download_url, auth=self.auth)
        if result.status_code > 399:
            raise falcon.HTTPInternalServerError(
                "Could not retrieve datastream {} for pid {}".format(
                   element.get('dsid'), pid),
                "Datastream download url is {}, error is\n{}".format(
                    download_url, result.text))
        datastream = result.text
        data = {
            'dsid': element.get('dsid'),
            'label': element.get('label'),
            'mimeType': element.get('mimeType'),
            'controlGroup': info_xml.get('{{{}}}dsControlGroup'.format(
                                Migration.FEDORA_ACCESS)).text,
            'state': info_xml.get("{{{}}}dsState".format(
                         Migration.FEDORA_ACCESS)).text}
        islandora_datastream.__add__(
            data,
            datastream,
            pid,
            element.get('dsid'))


    def __get_datastreams__(self, pid):
        datastream_url = "/".join([self.fedora_rest_url,
                                   pid,
                                   "datastreams?format=xml"])
        ds_xml = self.__get_xml__(datastream_url)
        return [ds for ds in ds_xml.findall("{{{}}}datastream".format(
                                            Migration.FEDORA_ACCESS))]




    def __get_parent_pid__(self, pid):
        rels_ext_url = "/".join([self.fedora_rest_url,
                                 pid,
                                 "datastreams",
                                 "RELS-EXT",
                                 "content"])
        rels_ext = self.__get_xml__(rels_ext_url)
        raw_pid = rels_ext.find("{{{}}}Description/{{{}}}isMemberOfCollection".format(
	    rdflib.RDF,
	    NAMESPACES.get('fedora'))).get("{{{}}}resource".format(rdflib.RDF))
        if raw_pid:
            return raw_pid.split("/")[-1]


    def __get_xml__(self, url):
        result = requests.get(url, auth=self.auth)
        if result.status_code > 399:
            return falcon.HTTPInternalServerError(
                "Could not retrieve XML",
                "XML url is {}, error is\n{}".format(
                    url, result.text))
        return etree.XML(result.text)


    def __guess_islandora_content_model__(self, mime_type):
        if ["image/jpeg",
            "image/png",
            "image/gif"].count(mime_type) > 0:
            return 'islandora:sp_basic_image'
        if mime_type.endswith("tiff"):
            return 'islandora:sp_large_image_cmodel'
        if ['audio/mpeg', 'audio/wav', 'audio/x-wav'].count(mime_type) > 0:
            return 'islandora:sp-audioCModel'
        if ['video/mp4', 'video/ogg'].count(mime_type) > 0:
            return 'islandora:sp_videoCModel'
        if mime_type.endswith("pdf"):
            return 'islandora:sp_pdf'
        # Default is a compound content model
        return 'islandora:compoundCModel'


    def __migrate_object__(self,
            pid,
            content_model='islandora:compoundCModel',
            namespace='coccc'):
        """Internal method takes a pid, creates a new Islandora Object

        Args:
            pid -- PID of Migrated object
            content_model -- Islandora content model, defaults to compoundCModel
        """
        object_data = self.get_object(pid)
        islandora_obj = islandora_object.__add_stub__(
            object_data.get('label'),
            namespace,
            pid)
        # Add Content Model relationship
        islandora_relationship.__add__(
            "info:fedora/fedora-system:def/model#",
            "hasModel",
            content_model,
            pid)
        # Add to Parent Collection
        parent_pid = self.__get_parent_pid__(pid)
        islandora_relationship.__add__(
            "info:fedora/fedora-system:def/relations-external#",
            "isMemberOfCollection",
            parent_pid,
            pid)




    def get_object(self, pid):
        profile_url = "{}/{}?format=xml".format(self.fedora_rest_url,
                                                pid)
        result = requests.get(profile_url, auth=self.auth)
        if result.status_code > 399:
            return falcon.HTTPInternalServerError(
                "Could retrieve object profile",
                "Profile url is {}".format(profile_url))
        profile = etree.XML(result.text)
        data = {"namespace": "coccc"}
        data['label'] = profile.find(
            "{{{}}}objLabel".format(Migration.FEDORA_ACCESS)).text
        data['state'] = profile.find(
            "{{{}}}objState".format(Migration.FEDORA_ACCESS)).text
        return data


class OralHistory(Migration):

    def __migrate__(self, pid):
        self.__migrate_object__(pid)
        datastreams = self.__get_datastreams__(pid)
        for ds in datastreams:
            print("\t{}".format(ds.get('dsid')))
            mime_type = ds.get('mimeType')
            # Saves DC and MODS as object datastreams
            if ['DC', 'MODS'].count(ds.get('dsid')):
                self.__add_datastream__(pid, ds)
            # Save any PDF as new Islandora Object
            if mime_type.endswith('pdf'):
                self.__add_child_object__(pid, ds)
            # Only saves images that do not have 'thumbnail' in label
            if ['image/jpeg',
                'image/jpg',
                'image/png',
                'image/gif'].count(mime_type) > 0:
                if ds.get('label').lower().find("thumbnail") < 0:
                    self.__add_child_object__(pid, ds)
            # Saves any wav files, ignores other mp3 or ogg files
            if mime_type.endswith("wav"):
                self.__add_child_object__(pid, ds)
        return True


    def on_post(self, req, resp, pid):
        if self.__migrate__(pid):
            resp.status = falcon.HTTP_201
            msg = "Oral History {} Successfully Migrated".format(pid)
        else:
            resp.status = falcon.HTTP_400
            msg = "Failed to migrate {}".format(pid)
        resp.body = {"message": msg}


api.add_route("/migrate/OralHistory/{pid}", OralHistory())


if __name__ == "__main__":
    semantic_server.app.main()


