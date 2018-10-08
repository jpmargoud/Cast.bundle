############################################################################
# This plugin will allow external calls, that the plugin can then handle
# See TODO doc for more details
#
# Made by
# dane22 & digitalhigh...Plex Community members
#
############################################################################

from __future__ import print_function

import StringIO
import datetime
import glob
import os
import sys
import threading
import time
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

import pychromecast
from helpers import PathHelper
from helpers.system import SystemHelper
from helpers.variable import pms_path
from pychromecast.controllers.media import MediaController
from pychromecast.controllers.plex import PlexController
from subzero.lib.io import FileIO

import log_helper
from CustomContainerOriginal import MediaContainer, DeviceContainer, CastContainer, ZipObject, StatusContainer, \
    MetaContainer
from CustomContainer import AnyContainer
from flex_container import FlexContainer
from lib import Plex

UNICODE_MAP = {
    65535: 'ucs2',
    1114111: 'ucs4'
}

META_TYPE_NAMES = {
    "movie": 1,
    "show": 2,
    "episode": 4,
    "album": 9,
    "track": 10
}

META_TYPE_IDS = {
    1: "movie",
    2: "show",
    3: "season",
    4: "episode",
    8: "artist",
    9: "album",
    10: "track",
    12: "extra",
    13: "photo",
    15: "playlist",
    18: "collection"
}

DEFAULT_CONTAINER_SIZE = 100000
DEFAULT_CONTAINER_START = 0
DATE_STRUCTURE = "%Y-%m-%d %H:%M:%S"
pms_path = pms_path()
Log.Debug("New PMS Path iss '%s'" % pms_path)
dbPath = os.path.join(pms_path, "Plug-in Support", "Databases", "com.plexapp.plugins.library.db")
Log.Debug("Setting DB path to '%s'" % dbPath)
os.environ['LIBRARY_DB'] = dbPath
os.environ["PMS_PATH"] = pms_path

os_platform = False
path = None
# Dummy Imports for PyCharm

# import Framework.context
# from Framework.api.objectkit import ObjectContainer, DirectoryObject
# from Framework.docutils import Plugin, HTTP, Log, Request
# from Framework.docutils import Data

NAME = 'Flex TV'
VERSION = '1.1.106'
APP_PREFIX = '/applications/Cast'
CAST_PREFIX = '/chromecast'
STAT_PREFIX = '/stats'
ICON = 'flextv.png'
ICON_CAST = 'icon-cast.png'
ICON_CAST_AUDIO = 'icon-cast_audio.png'
ICON_CAST_VIDEO = 'icon-cast_video.png'
ICON_CAST_GROUP = 'icon-cast_group.png'
ICON_CAST_REFRESH = 'icon-cast_refresh.png'
ICON_PLEX_CLIENT = 'icon-plex_client.png'
TEST_CLIP = 'test.mp3'
PLUGIN_IDENTIFIER = "com.plexapp.plugins.FlexTV"


# Start function
def Start():
    Plugin.AddViewGroup("Details", viewMode="InfoList", mediaType="items")
    distribution = None
    libraries_path = os.path.join(pms_path, "Plug-ins", "FlexTV.bundle", "Contents", "Libraries")
    loaded = insert_paths(distribution, libraries_path)
    if loaded:
        Log.Debug("Paths should be loaded!")
        os.environ["Loaded"] = "True"
    else:
        Log.Debug("Unable to load paths")
        os.environ["Loaded"] = "False"
    ObjectContainer.title1 = NAME
    DirectoryObject.thumb = R(ICON)
    HTTP.CacheTime = 5
    if Data.Exists('device_json') is not True:
        UpdateCache()

    ValidatePrefs()
    CacheTimer()
    RestartTimer()



def CacheTimer():
    mins = 60
    update_time = mins * 60
    Log.Debug("Cache timer started, updating in %s minutes, man", mins)
    threading.Timer(update_time, CacheTimer).start()
    UpdateCache()


def RestartTimer():
    hours = 4
    restart_time = hours * 60 * 60
    Log.Debug("Restart timer started, plugin will re-start in %s hours.", hours)
    threading.Timer(restart_time, DispatchRestart).start()


def UpdateCache():
    Log.Debug("UpdateCache called")
    scan_devices()


@handler(APP_PREFIX, NAME)
@handler(CAST_PREFIX, NAME)
@handler(STAT_PREFIX, NAME)
@route(APP_PREFIX + '/MainMenu')
def MainMenu(Rescanned=False):
    """
    Main menu
    and stuff
    """
    Log.Debug("**********  Starting MainMenu  **********")
    title = NAME + " - " + VERSION
    if Data.Exists('last_scan'):
        title = NAME + " - " + Data.Load('last_scan')

    oc = ObjectContainer(
        title1=title,
        no_cache=True,
        no_history=True,
        title_bar="Flex TV",
        view_group="Details")

    if Rescanned is True:
        oc.message = "Rescan complete!"

    #
    do = DirectoryObject(
        title="Rescan Devices",
        thumb=R(ICON_CAST_REFRESH),
        key=Callback(Rescan))

    oc.add(do)

    do = DirectoryObject(
        title="Advanced",
        thumb=R(ICON_CAST_REFRESH),
        key=Callback(AdvancedMenu))

    oc.add(do)

    do = DirectoryObject(
        title="Devices",
        thumb=R(ICON_CAST),
        key=Callback(Resources))

    oc.add(do)

    do = DirectoryObject(
        title="Broadcast",
        thumb=R(ICON_CAST_AUDIO),
        key=Callback(Broadcast))

    oc.add(do)

    do = DirectoryObject(
        title="Stats",
        thumb=R(ICON_PLEX_CLIENT),
        key=Callback(Statmenu))

    oc.add(do)

    return oc


@route(APP_PREFIX + '/ValidatePrefs')
def ValidatePrefs():
    """
    Called by the framework every time a user changes the prefs
    We add this dummy function, to avoid errors in the log
    and stuff.
    """

    dependencies = ["helpers"]
    log_helper.register_logging_handler(dependencies, level="DEBUG")
    return


####################################
# These are our cast endpoints
@route(APP_PREFIX + '/devices')
@route(CAST_PREFIX + '/devices')
def Devices():
    """

    Endpoint to scan LAN for cast devices
    """
    Log.Debug('Recieved a call to fetch cast devices')
    # Grab our response header?
    casts = fetch_devices()
    mc = MediaContainer()
    for cast in casts:
        Log.Debug("Cast type is " + cast['type'])
        if (cast['type'] == 'cast') | (cast['type'] == 'audio') | (cast['type'] == 'group'):
            dc = CastContainer(cast)
            mc.add(dc)

    return mc


@route(APP_PREFIX + '/clients')
@route(CAST_PREFIX + '/clients')
def Clients():
    """
    Endpoint to scan LAN for cast devices
    """
    Log.Debug('Recieved a call to fetch all devices')
    # Grab our response header?
    casts = fetch_devices()

    mc = MediaContainer()
    for cast in casts:
        dc = CastContainer(cast)
        mc.add(dc)

    return mc


@route(APP_PREFIX + '/resources')
@route(CAST_PREFIX + '/resources')
def Resources():
    """
    Endpoint to scan LAN for cast devices
    """
    Log.Debug('Recieved a call to fetch devices')
    # Grab our response header?
    casts = fetch_devices()

    oc = ObjectContainer(
        no_cache=True,
        no_history=True,
        view_group="Details")

    for cast in casts:
        cast_type = cast['type']
        icon = ICON_CAST
        if cast_type == "audio":
            icon = ICON_CAST_AUDIO
        if cast_type == "cast":
            icon = ICON_CAST_VIDEO
        if cast_type == "group":
            icon = ICON_CAST_GROUP
        if cast['app'] == "Plex Client":
            icon = ICON_PLEX_CLIENT
        do = DirectoryObject(
            title=cast['name'],
            duration=cast['status'],
            tagline=cast['uri'],
            summary=cast['app'],
            key=Callback(Status, input_name=cast['name']),
            thumb=R(icon))
        oc.add(do)

    return oc


@route(APP_PREFIX + '/rescan')
@route(CAST_PREFIX + '/rescan')
def Rescan():
    """
    Endpoint to scan LAN for cast devices
    """
    Log.Debug('Recieved a call to rescan devices')
    # Grab our response header?
    UpdateCache()
    return MainMenu(True)


@route(CAST_PREFIX + '/play')
def Play():
    """
    Endpoint to play media.
    """
    Log.Debug('Recieved a call to play media.')
    params = ['Clienturi', 'Contentid', 'Contenttype', 'Serverid', 'Serveruri',
              'Username', 'Transienttoken', 'Queueid', 'Version', 'Primaryserverid',
              'Primaryserveruri', 'Primaryservertoken']
    values = sort_headers(params, False)
    status = "Missing required headers and stuff"
    msg = status

    if values is not False:
        Log.Debug("Holy crap, we have all the headers we need.")
        client_uri = values['Clienturi'].split(":")
        host = client_uri[0]
        port = int(client_uri[1])
        pc = False
        msg = "No message received"
        if 'Serverid' in values:
            servers = fetch_servers()
            for server in servers:
                if server['id'] == values['Serverid']:
                    Log.Debug("Found a matching server!")
                    values['Serveruri'] = server['uri']
                    values['Version'] = server['version']

        try:
            cast = pychromecast.Chromecast(host, port)
            cast.wait()
            values['Type'] = cast.cast_type
            pc = PlexController(cast)
            cast.register_handler(pc)
            Log.Debug("Sending values to play command: " + JSON.StringFromObject(values))
            pc.play_media(values, log_data)
        except pychromecast.LaunchError, pychromecast.PyChromecastError:
            Log.Debug('Error connecting to host.')
            status = "Error"
        finally:
            if pc is not False:
                status = "Success"

    oc = MediaContainer({
        'Name': 'Playback Status',
        'Status': status,
        'Message': msg
    })

    return oc


@route(CAST_PREFIX + '/cmd')
def Cmd():
    """
    Media control command(s).

    Plex-specific commands use the format:


    Required params:
    Uri
    Cmd
    Vol(If setting volume, otherwise, ignored)

    Where <COMMAND> is one of:
    PLAY (resume)
    PAUSE
    STOP
    STEPFORWARD
    STEPBACKWARD Need to test, not in PHP cast app)
    PREVIOUS
    NEXT
    MUTE
    UNMUTE
    VOLUME - also requires an int representing level from 0-100

    """
    Log.Debug('Recieved a call to control playback')
    params = sort_headers(['Uri', 'Cmd', 'Val'], False)
    status = "Missing paramaters"
    response = "Error"

    if params is not False:
        uri = params['Uri'].split(":")
        cast = pychromecast.Chromecast(uri[0], int(uri[1]))
        cast.wait()
        pc = PlexController(cast)
        Log.Debug("Handler namespace is %s" % pc.namespace)
        cast.register_handler(pc)

        Log.Debug("Handler namespace is %s" % pc.namespace)

        cmd = params['Cmd']
        Log.Debug("Command is " + cmd)

        if cmd == "play":
            pc.play()
        if cmd == "pause":
            pc.pause()
        if cmd == "stop":
            pc.stop()
        if cmd == "next":
            pc.next()
        if (cmd == "offset") & ('Val' in params):
            pc.seek(params["Val"])
        if cmd == "previous":
            pc.previous()
        if cmd == "volume.mute":
            pc.mute(True)
        if cmd == "volume.unmute":
            pc.mute(False)
        if (cmd == "volume") & ('Val' in params):
            pc.set_volume(params["Val"])
        if cmd == "volume.down":
            pc.volume_down()
        if cmd == "volume.up":
            pc.volume_up()

        cast.disconnect()
        response = "Command successful"

    oc = ObjectContainer(
        title1=response,
        title2=status,
        no_cache=True,
        no_history=True)
    return oc


@route(CAST_PREFIX + '/audio')
def Audio():
    """
    Endpoint to cast audio to a specific device.
    """

    Log.Debug('Recieved a call to play an audio clip.')
    params = ['Uri', 'Path']
    values = sort_headers(params, True)
    status = "Missing required headers"
    if values is not False:
        Log.Debug("Holy crap, we have all the headers we need.")
        client_uri = values['Uri'].split(":")
        host = client_uri[0]
        port = int(client_uri[1])
        path = values['Path']
        try:
            cast = pychromecast.Chromecast(host, port)
            cast.wait()
            mc = cast.media_controller
            mc.play_media(path, 'audio/mp3', )
        except pychromecast.LaunchError, pychromecast.PyChromecastError:
            Log.Debug('Error connecting to host.')
        finally:
            Log.Debug("We have a cast")
            status = "Playback successful"

    oc = ObjectContainer(
        title1=status,
        no_cache=True,
        no_history=True)

    return oc


@route(CAST_PREFIX + '/broadcast/test')
def Test():
    values = {'Path': R(TEST_CLIP)}
    casts = fetch_devices()
    status = "Test successful!"
    try:
        for cast in casts:
            if cast['type'] == "audio":
                mc = MediaController()
                Log.Debug("We should be broadcasting to " + cast['name'])
                uri = cast['uri'].split(":")
                cast = pychromecast.Chromecast(uri[0], int(uri[1]))
                cast.wait()
                cast.register_handler(mc)
                mc.play_media(values['Path'], 'audio/mp3')

    except pychromecast.LaunchError, pychromecast.PyChromecastError:
        Log.Debug('Error connecting to host.')
        status = "Test failed!"
    finally:
        Log.Debug("We have a cast")

    oc = ObjectContainer(
        title1=status,
        no_cache=True,
        no_history=True)

    return oc


@route(CAST_PREFIX + '/broadcast')
def Broadcast():
    """
    Send audio to *all* cast devices on the network
    """
    Log.Debug('Recieved a call to broadcast an audio clip.')
    params = ['Path']
    values = sort_headers(params, True)
    status = "No clip specified"
    if values is not False:
        do = False
        casts = fetch_devices()
        disconnect = []
        controllers = []
        try:
            for cast in casts:
                if cast['type'] == "audio":
                    mc = MediaController()
                    Log.Debug("We should be broadcasting to " + cast['name'])
                    uri = cast['uri'].split(":")
                    cast = pychromecast.Chromecast(uri[0], int(uri[1]))
                    cast.wait()
                    cast.register_handler(mc)
                    controllers.append(mc)
                    disconnect.append(cast)

            for mc in controllers:
                mc.play_media(values['Path'], 'audio/mp3', )

        except pychromecast.LaunchError, pychromecast.PyChromecastError:
            Log.Debug('Error connecting to host.')
        finally:
            for cast in disconnect:
                cast.disconnect()
            Log.Debug("We have a cast")

    else:
        do = DirectoryObject(
            title='Test Broadcast',
            tagline="Send a test broadcast to audio devices.",
            key=Callback(Test))
        status = "Foo"

    oc = ObjectContainer(
        title1=status,
        no_cache=True,
        no_history=True)

    if do is not False:
        oc.add(do)

    return oc


####################################
# These are our /stat prefixes
@route(STAT_PREFIX + '/tag')
def All():
    mc = build_tag_container("all")
    return mc


@route(STAT_PREFIX + '/tag/actor')
def Actor():
    mc = build_tag_container("actor")
    return mc


@route(STAT_PREFIX + '/tag/director')
def Director():
    mc = build_tag_container("director")
    return mc


@route(STAT_PREFIX + '/tag/writer')
def Writer():
    mc = build_tag_container("writer")
    return mc


@route(STAT_PREFIX + '/tag/genre')
def Genre():
    mc = build_tag_container("genre")
    return mc


@route(STAT_PREFIX + '/library')
def Library():
    mc = MediaContainer()
    headers = sort_headers(["Container-Size", "Type"])
    Log.Debug("Here's where we fetch some library stats.")
    sections = {}
    recs = query_library_stats(headers)
    sizes = query_library_sizes()
    records = recs[0]
    sec_counts = recs[1]
    for record in records:
        section = record["sectionTitle"]
        if section not in sections:
            sections[section] = []
        del (record["sectionTitle"])
        sections[section].append(dict(record))

    for name in sections:
        Log.Debug("Looping through section '%s'" % name)
        sec_id = sections[name][0]["section"]
        sec_type = sections[name][0]["sectionType"]
        section_types = {
            1: "movie",
            2: "show",
            3: "music",
            4: "photo",
            8: "music",
            13: "photo"
        }
        if sec_type in section_types:
            sec_type = section_types[sec_type]

        item_count = 0
        play_count = 0
        playable_count = 0
        section_children = []
        for record in sections[name]:
            item_count += record["totalItems"]
            if record['playCount'] is not None:
                play_count += record['playCount']
            if record["type"] in ["episode", "track", "movie"]:
                playable_count = record["totalItems"]

            item_type = str(record["type"]).capitalize()
            record_data = {
                "totalItems": record["totalItems"]
            }
            vc = AnyContainer(record_data, item_type, False)

            if record["lastViewedAt"] is not None:
                last_item = {
                    "title": record['title'],
                    "grandparentTitle": record['grandparentTitle'],
                    "art": record['art'],
                    "thumb": record['thumb'],
                    "ratingKey": record['ratingKey'],
                    "lastViewedAt": record['lastViewedAt'],
                    "username": record['username'],
                    "userId": record['userId']
                }
                li = AnyContainer(last_item, "lastViewed", False)
                vc.add(li)

            section_children.append(vc)

        section_data = {
            "title": name,
            "id": sec_id,
            "totalItems": item_count,
            "playableItems": playable_count,
            "playCount": play_count,
            "type": sec_type
        }

        for sec_size in sizes:
            if sec_size['section_id'] == sec_id:
                Log.Debug("Found a matching section size...foo")
                section_data['mediaSize'] = sec_size['size']

        sec_unique_played = sec_counts.get(str(sec_id)) or None
        if sec_unique_played is not None:
            Log.Debug("Hey, we got the unique count")
            section_data["watchedItems"] = sec_unique_played["viewedItems"]
        ac = AnyContainer(section_data, "Section", "False")
        for child in section_children:
            ac.add(child)

        mc.add(ac)

    return mc


@route(STAT_PREFIX + '/library/growth')
def Growth():
    headers = sort_headers(["Interval", "Start", "End", "Container-Size", "Container-Start", "Type"])
    records = query_library_growth(headers)
    total_array = {}
    for record in records:
        dates = str(record["addedAt"])[:-9].split("-")

        year = str(dates[0])
        month = str(dates[1])
        day = str(dates[2])

        year_array = total_array.get(year) or {}
        month_array = year_array.get(month) or {}
        day_array = month_array.get(day) or []
        day_array.append(record)

        month_array[day] = day_array
        year_array[month] = month_array
        total_array[year] = year_array

    mc = MediaContainer()
    grand_total = 0
    types_all = {}
    for y in range(0000, 3000):
        y = str(y)
        year_total = 0
        if y in total_array:
            types_year = {}
            Log.Debug("Found a year %s" % y)
            year_container = FlexContainer("Year", {"value": y})
            year_array = total_array[y]
            Log.Debug("Year Array: %s" % JSON.StringFromObject(year_array))
            month_total = 0
            for m in range(1, 12):
                m = str(m).zfill(2)
                if m in year_array:
                    types_month = {}
                    Log.Debug("Found a month %s" % m)
                    month_container = FlexContainer("Month", {"value": m})
                    month_array = year_array[m]
                    for d in range(1, 32):
                        d = str(d).zfill(2)
                        if d in month_array:
                            types_day = {}
                            Log.Debug("Found a day %s" % d)
                            day_container = FlexContainer("Day", {"value": d}, False)
                            records = month_array[d]
                            for record in records:
                                ac = FlexContainer("Added", record, False)
                                record_type = record["type"]
                                temp_day_count = types_day.get(record_type) or 0
                                temp_month_count = types_month.get(record_type) or 0
                                temp_year_count = types_year.get(record_type) or 0
                                temp_all_count = types_all.get(record_type) or 0
                                types_day[record_type] = temp_day_count + 1
                                types_month[record_type] = temp_month_count + 1
                                types_year[record_type] = temp_year_count + 1
                                types_all[record_type] = temp_all_count + 1
                                day_container.add(ac)
                            month_total += day_container.size()
                            day_container.set("totalAdded", day_container.size())
                            for rec_type in types_day:
                                day_container.set("%sCount" % rec_type, types_day.get(rec_type))
                            month_container.add(day_container)
                    year_total += month_total
                    month_container.set("totalAdded", month_total)
                    for rec_type in types_month:
                        month_container.set("%sCount" % rec_type, types_month.get(rec_type))
                    year_container.add(month_container)
            year_container.set("totalAdded", year_total)
            for rec_type in types_year:
                year_container.set("%sCount" % rec_type, types_year.get(rec_type))
            grand_total += year_total
            mc.add(year_container)
    return mc


@route(STAT_PREFIX + '/user')
def User():
    mc = MediaContainer()
    headers = sort_headers(["Type", "Userid", "Username", "Container-start", "Container-Size", "Device", "Title"])
    container_start = int(headers.get("Container-Start") or DEFAULT_CONTAINER_START)
    container_size = int(headers.get("Container-Size") or DEFAULT_CONTAINER_SIZE)
    container_max = container_start + container_size
    users_data = query_user_stats(headers)

    if users_data is not None:
        users = users_data[0]
        devices = users_data[1]
        device_names = []
        for user, records in users.items():
            last_active = datetime.datetime.strptime("1900-01-01 00:00:00", DATE_STRUCTURE)
            uc = FlexContainer("User", {"userName": user}, False)
            sc = FlexContainer("Views")
            i = 0
            for record in records:
                viewed_at = datetime.datetime.fromtimestamp(record["lastViewedAt"])
                if viewed_at > last_active:
                    last_active = viewed_at
                if i >= container_max:
                    break
                if i >= container_start:
                    vc = FlexContainer("View", record, False)
                    if "deviceName" in record:
                        if record["deviceName"] not in device_names:
                            device_names.append(record["deviceName"])
                    sc.add(vc)
            uc.add(sc)
            uc.set("lastSeen", last_active)
            dp = FlexContainer("Devices", None, False)
            chrome_data = None
            for device in devices:
                if device["userName"] == user:
                    if device["deviceName"] in device_names:
                        if device["deviceName"] != "Chrome":
                            Log.Debug("Found a device for %s" % user)
                            dc = FlexContainer("Device", device)
                            dp.add(dc)
                        else:
                            chrome_bytes = 0
                            if chrome_data is None:
                                chrome_data = device
                            else:
                                chrome_bytes = device["totalBytes"] + chrome_data.get("totalBytes") or 0
                            chrome_data["totalBytes"] = chrome_bytes
            if chrome_data is not None:
                dc = FlexContainer("Device", chrome_data)
                dp.add(dc)
            uc.add(dp)
            mc.add(uc)

    Log.Debug("Still alive, returning data")

    return mc


####################################
# Finally, utility prefixes (logs, restart)
@route(APP_PREFIX + '/logs')
@route(CAST_PREFIX + '/logs')
@route(STAT_PREFIX + '/logs')
def DownloadLogs():
    buff = StringIO.StringIO()
    zip_archive = ZipFile(buff, mode='w', compression=ZIP_DEFLATED)
    paths = get_log_paths()
    if (paths[0] is not False) & (paths[1] is not False):
        logs = sorted(glob.glob(paths[0] + '*')) + [paths[1]]
        for path in logs:
            Log.Debug("Trying to read path: " + path)
            data = StringIO.StringIO()
            data.write(FileIO.read(path))
            zip_archive.writestr(os.path.basename(path), data.getvalue())

        zip_archive.close()

        return ZipObject(buff.getvalue())

    Log.Debug("No log path found, foo.")
    return ObjectContainer(
        no_cache=True,
        title1="No logs found",
        no_history=True,
        view_group="Details")


@route(APP_PREFIX + '/statmenu')
def Statmenu():
    Log.Debug("Building stats menu.")
    oc = ObjectContainer(
        no_cache=True,
        no_history=True,
        view_group="Details")

    do = DirectoryObject(
        title="Library",
        thumb=R(ICON_CAST_AUDIO),
        key=Callback(Library))

    oc.add(do)
    return oc


@route(CAST_PREFIX + '/status')
@route(CAST_PREFIX + '/resources/status')
def Status(input_name=False):
    """
    Fetch player status
    TODO: Figure out how to parse and return additional data here
    """
    uri = "FOOBAR"
    name = "FOOBAR"
    show_all = False
    Log.Debug('Trying to get cast device status here')
    for key, value in Request.Headers.items():
        Log.Debug("Header key %s is %s", key, value)
        if key in ("X-Plex-Clienturi", "Clienturi"):
            Log.Debug("We have a client URI")
            uri = value

        if key in ("X-Plex-Clientname", "Clientname"):
            Log.Debug("X-Plex-Clientname: " + value)
            name = value

    if input_name is not False:
        name = input_name
    if uri == name:
        show_all = True

    chromecasts = fetch_devices()
    devices = []

    for chromecast in chromecasts:
        cast = False
        if show_all is not True:
            if chromecast['name'] == name:
                Log.Debug("Found a matching chromecast: " + name)
                cast = chromecast

            if chromecast['uri'] == uri:
                Log.Debug("Found a matching uri:" + uri)
                cast = chromecast
        else:
            cast = chromecast

        if cast is not False:
            devices.append(cast)

    do = ""

    if len(devices) != 0:
        for device in devices:
            Log.Debug("We have set a chromecast here.")
            uris = device['uri'].split(":")
            host = uris[0]
            port = uris[1]
            Log.Debug("Host and port are %s and %s", host, port)
            cast = pychromecast.Chromecast(host, int(port))
            Log.Debug("Waiting for device")
            cast.wait(2)
            app_id = cast.app_id
            meta_dict = False
            if app_id == "9AC194DC":
                pc = PlexController(cast)
                cast.register_handler(pc)
                plex_status = pc.plex_status()
                raw_status = {
                    'state': plex_status['state'],
                    'volume': plex_status['volume'],
                    'muted': plex_status['muted']
                }
                meta_dict = plex_status['meta']
            else:
                raw_status = {"state": "idle"}

            Log.Debug("Did we get it?!?! %s", raw_status)

            do = StatusContainer(
                dict=raw_status
            )
            if meta_dict is not False:
                mc = MetaContainer(
                    dict=meta_dict
                )

                do.add(mc)

    return do


@route(APP_PREFIX + '/advanced')
def AdvancedMenu(header=None, message=None):
    oc = ObjectContainer(header=header or "Internal stuff, pay attention!", message=message, no_cache=True,
                         no_history=True,
                         replace_parent=False, title2="Advanced")

    oc.add(DirectoryObject(
        key=Callback(TriggerRestart),
        title="Restart the plugin",
    ))

    return oc


@route(APP_PREFIX + '/advanced/restart/trigger')
def TriggerRestart():
    DispatchRestart()
    oc = ObjectContainer(
        title1="restarting",
        no_cache=True,
        no_history=True,
        title_bar="Chromecast",
        view_group="Details")

    do = DirectoryObject(
        title="Rescan Devices",
        thumb=R(ICON_CAST_REFRESH),
        key=Callback(Rescan))

    oc.add(do)

    do = DirectoryObject(
        title="Devices",
        thumb=R(ICON_CAST),
        key=Callback(Resources))

    oc.add(do)

    do = DirectoryObject(
        title="Broadcast",
        thumb=R(ICON_CAST_AUDIO),
        key=Callback(Broadcast))

    oc.add(do)

    return oc


@route(APP_PREFIX + '/advanced/restart/execute')
def Restart():
    Plex[":/plugins"].restart(PLUGIN_IDENTIFIER)


####################################
# These functions are for cast-related stuff
def fetch_devices():
    if not Data.Exists('device_json'):
        Log.Debug("No cached data exists, re-scanning.")
        casts = scan_devices()

    else:
        Log.Debug("Returning cached data")
        casts_string = Data.Load('device_json')
        casts = JSON.ObjectFromString(casts_string)

    token = False
    for key, value in Request.Headers.items():
        Log.Debug("Header key %s is %s", key, value)
        if key in ("X-Plex-Token", "Token"):
            Log.Debug("We have a Token")
            token = value

    if token:
        port = os.environ.get("PLEXSERVERPORT")
        if port is None:
            port = "32400"
        url = Network.Address
        if url is None:
            url = "localhost"

        try:
            myurl = "http://" + url + ":" + port + "/clients?X-Plex-Token=" + token
        except TypeError:
            myurl = False
            pass

        if myurl:
            Log.Debug("Gonna connect to %s" % myurl)
            req = HTTP.Request(myurl)
            req.load()
            if hasattr(req, 'content'):
                client_data = req.content
                root = ET.fromstring(client_data)
                for device in root.iter('Server'):
                    local_item = {
                        "name": device.get('name'),
                        "uri": device.get('host') + ":" + str(device.get('port')),
                        "status": "n/a",
                        "type": device.get('product'),
                        "app": "Plex Client",
                        "id": device.get('machineIdentifier')
                    }
                    casts.append(local_item)

    return casts


def fetch_servers():
    token = False
    for key, value in Request.Headers.items():
        Log.Debug("Header key %s is %s", key, value)
        if key in ("X-Plex-Token", "Token"):
            Log.Debug("We have a Token")
            token = value

    servers = []

    if token:
        port = os.environ.get("PLEXSERVERPORT")
        url = Network.Address
        myurl = 'http://' + url + ':' + port + '/servers?X-Plex-Token=' + token
        Log.Debug("Gonna connect to %s" % myurl)
        req = HTTP.Request(myurl)
        req.load()
        client_data = req.content
        root = ET.fromstring(client_data)
        for device in root.iter('Server'):
            version = device.get("version").split("-")[0]
            local_item = {
                "name": device.get('name'),
                "uri": "http://" + device.get('host') + ":" + str(device.get('port')),
                "version": version,
                "id": device.get('machineIdentifier')
            }
            Log.Debug("Got me a server: %s" % local_item)
            servers.append(local_item)

    return servers


def scan_devices():
    Log.Debug("Re-fetching devices")
    casts = pychromecast.get_chromecasts(1, None, None, True)
    data_array = []
    for cast in casts:
        cast_item = {
            "uri": cast.uri,
            "name": cast.name,
            "status": cast.is_idle,
            "type": cast.cast_type,
            "app": cast.app_display_name,
            'id': cast.uri
        }
        data_array.append(cast_item)

    Log.Debug("Cast length is %s", str(len(data_array)))
    if len(data_array) == 0:
        if Data.Exists('restarts') is not True:
            Data.Save('restarts', 1)
            Log.Debug("No cast devices found, we need to restart the plugin.")
            DispatchRestart()
        else:
            restart_count = Data.Load('restarts')
            if restart_count >= 5:
                Log.Debug("It's been an hour, trying to restart the plugin again")
                Data.Remove('restarts')
                DispatchRestart()
            else:
                Log.Debug("Avoiding a restart in case it's not me, but you.")
                restart_count += 1
                Data.Save('restarts', restart_count)

    else:
        Log.Debug("Okay, we have cast devices, no need to get all postal up in this mutha...")
        if Data.Exists('restarts'):
            Data.Remove('restarts')

    Log.Debug("Item count is " + str(len(data_array)))
    cast_string = JSON.StringFromObject(data_array)
    Data.Save('device_json', cast_string)
    last_scan = "Last Scan: " + time.strftime("%B %d %Y - %H:%M")
    Data.Save('last_scan', last_scan)
    return data_array


def player_string(values):
    request_id = values['Requestid']
    content_id = values['Contentid'] + '?own=1&window=200'  # key
    content_type = values['Contenttype']
    offset = values['Offset']
    server_id = values['Serverid']
    transcoder_video = values['Transcodervideo']
    # TODO: Make this sexy, see if we can just use the current server. I think so.
    server_uri = values['Serveruri'].split("://")
    server_parts = server_uri[1].split(":")
    server_protocol = server_uri[0]
    server_ip = server_parts[0]
    server_port = server_parts[1]
    # TODO: Look this up instead of send it?
    username = values['Username']
    true = "true"
    false = "false"
    request_array = {
        "type": 'LOAD',
        'requestId': request_id,
        'media': {
            'contentId': content_id,
            'streamType': 'BUFFERED',
            'contentType': content_type,
            'customData': {
                'offset': offset,
                'directPlay': true,
                'directStream': true,
                'subtitleSize': 100,
                'audioBoost': 100,
                'server': {
                    'machineIdentifier': server_id,
                    'transcoderVideo': transcoder_video,
                    'transcoderVideoRemuxOnly': false,
                    'transcoderAudio': true,
                    'version': '1.4.3.3433',
                    'myPlexSubscription': true,
                    'isVerifiedHostname': true,
                    'protocol': server_protocol,
                    'address': server_ip,
                    'port': server_port,
                    'user': {
                        'username': username
                    }
                },
                'containerKey': content_id
            },
            'autoplay': true,
            'currentTime': 0
        }
    }
    Log.Debug("Player String: " + JSON.StringFromObject(request_array))

    return request_array


####################################
# These functions are for stats stuff
def build_tag_container(tag_type):
    selection = tag_type
    headers = sort_headers(["Container-Start", "Container-Size"])
    records = query_tag_stats(selection, headers)
    mc = MediaContainer()
    if records is not None:
        for record in records:
            sc = StatContainer(record)
            mc.add(sc)

    return mc


def query_library_sizes():
    conn = fetch_cursor()
    cursor = conn[0]
    connection = conn[1]
    results = []

    if cursor is not None:
        query = """select sum(size), library_section_id, ls.name from media_items 
                    inner join library_sections as ls
                    on ls.id = library_section_id
                    group by library_section_id;"""

        for size, section_id, section_name in cursor.execute(query):
            dictz = {
                "size": size,
                "section_id": section_id,
                "section_name": section_name
            }
            results.append(dictz)

        close_connection(connection)

    return results


def query_tag_stats(selection, headers):
    container_size = int(headers.get("Container-Size") or DEFAULT_CONTAINER_SIZE)
    container_start = int(headers.get("Container-Start") or DEFAULT_CONTAINER_START)
    Log.Debug("Container size is set to %s, start to %s" % (container_size, container_start))
    entitlements = get_entitlements()
    conn = fetch_cursor()
    cursor = conn[0]
    connection = conn[1]

    tag_types = {
        1: "genre",
        4: "director",
        5: "writer",
        6: "actor"
    }

    if cursor is not None:
        results = []

        options = ["all", "actor", "director", "writer", "genre"]
        tag_selection = ""
        if selection not in options:
            return False

        if selection == "all":
            fetch_values = "tags.tag, tags.tag_type, mt.metadata_type, mt.id, " \
                           "COUNT(tags.id)"
            tag_selection = "tags.tag_type = 6 OR tags.tag_type = 5 OR tags.tag_type = 4 OR tags.tag_type = 1"

        if selection == "actor":
            fetch_values = "tags.tag, mt.id, COUNT(tags.id)"
            tag_selection = "tags.tag_type = 6"

        if selection == "director":
            fetch_values = "tags.tag, mt.id, COUNT(tags.id)"
            tag_selection = "tags.tag_type = 4"

        if selection == "writer":
            fetch_values = "tags.tag, mt.id, COUNT(tags.id)"
            tag_selection = "tags.tag_type = 5"

        if selection == "genre":
            fetch_values = "tags.tag, mt.id, COUNT(tags.id)"
            tag_selection = "tags.tag_type = 1"

        tag_selection += " AND mt.library_section_id in %s" % entitlements

        query = """SELECT %s
                        AS Total FROM tags
                        LEFT JOIN taggings ON tags.id = taggings.tag_id
                        INNER JOIN metadata_items AS mt
                        ON taggings.metadata_item_id = mt.id
                        WHERE %s
                        GROUP BY tags.tag,tags.tag_type
                        ORDER BY Total
                        desc;""" % (fetch_values, tag_selection)
        i = 0
        container_max = int(container_start) + int(container_size)
        Log.Debug("Container max set to %s" % container_max)
        if selection == "all":
            for title, tag_type, meta_type, ratingkey, tag_count in cursor.execute(query):
                if i >= container_max:
                    break
                if i >= container_start:
                    if tag_type in tag_types:
                        tag_title = tag_types[tag_type]
                    else:
                        tag_title = "unknown"

                    if meta_type in META_TYPE_IDS:
                        meta_type = META_TYPE_IDS[meta_type]

                    dicts = {
                        "title": title,
                        "type": tag_title,
                        "totalItems": tag_count,
                        "metaType": meta_type,
                        "ratingKey": ratingkey,
                        "thumb": "/library/metadata/" + str(ratingkey) + "/thumb",
                        "art": "/library/metadata/" + str(ratingkey) + "/art"
                    }

                    if meta_type == "episode":
                        dicts["banner"] = "/library/metadata/" + str(ratingkey) + "/banner/"
                    Log.Debug("Appending record %s" % i)
                    results.append(dicts)
                else:
                    Log.Debug("Skipping record %s outside of requested range" % i)

                i += 1
        else:
            for tag, ratingkey, count in cursor.execute(query):
                if i >= container_max:
                    break
                if i < container_start:
                    Log.Debug("Count %s is less than start %s, skipping..." % (i, container_start))
                else:
                    Log.Debug("Appending record %s" % i)
                    dicts = {
                        "title": tag,
                        "totalItems": count,
                        "ratingKey": ratingkey,
                        "thumb": "/library/metadata/" + str(ratingkey) + "/thumb",
                        "art": "/library/metadata/" + str(ratingkey) + "/art"
                    }
                    results.append(dicts)
                i += 1
        close_connection(connection)
        return results
    else:
        Log.Error("DB Connection error!")
        return None


def query_user_stats(headers):
    query_types = [1, 4, 10]
    if "Type" in headers:
        meta_type = headers.get("Type")
        if meta_type in META_TYPE_NAMES:
            meta_type = META_TYPE_NAMES[headers['Type']]
        if int(meta_type) == meta_type:
            query_types = [int(meta_type)]

    conn = fetch_cursor()
    cursor = conn[0]
    connection = conn[1]

    if cursor is not None:
        selectors = {}
        entitlements = get_entitlements()
        selectors["sm.metadata_type"] = ["IN", query_types]
        selectors["count"] = ["""!=""", 0]
        results2 = []

        if len(headers.keys()) != 0:
            Log.Debug("We have headers...")
            selector_values = {
                "Userid": "sm.account_id",
                "Username": "accounts.name"
            }

            for header_key, value in headers.items():
                if header_key in selector_values:
                    Log.Debug("Valid selector %s found" % header_key)
                    selector = selector_values[header_key]
                    selectors[selector] = ["""=""", value]

        query_selectors = []
        query_params = []
        for key, data in selectors.items():
            select_action = data[0]
            select_value = data[1]
            Log.Debug("Select Value is %s, action is %s" % (select_value, select_action))
            if isinstance(select_value, list):
                query_selector = "%s %s (%s)" % (key, select_action, ",".join('?' * len(select_value)))
                for sv in select_value:
                    query_params.append(sv)
            else:
                query_selector = "%s %s ?" % (key, select_action)
                query_params.append(select_value)

            query_selectors.append(query_selector)

        query_string = "WHERE " + " AND ".join(query_selectors)
        Log.Debug("Query string is '%s'" % query_string)

        # TODO: Add another method here to get the user's ID by Plex Token and only return their info?

        byte_query = """select accounts.name, sm.at, sm.metadata_type, sm.account_id,
                    devices.name AS device_name, devices.identifier AS device_id,
                    sb.bytes from statistics_media AS sm
                    INNER JOIN statistics_bandwidth as sb
                     ON sb.at = sm.at AND sb.account_id = sm.account_id AND sb.device_id = sm.device_id
                    INNER JOIN accounts
                     ON accounts.id = sm.account_id
                    INNER JOIN devices
                     ON devices.id = sm.device_id
                    %s
                    ORDER BY sm.at DESC;""" % query_string

        Log.Debug("Query1) is '%s'" % byte_query)
        Log.Debug("Query selectors: %s" % JSON.StringFromObject(query_params))

        for user_name, viewed_at, meta_type, user_id, device_name, device_id, data_bytes in cursor.execute(
                byte_query, query_params):
            last_viewed = int(time.mktime(datetime.datetime.strptime(viewed_at, "%Y-%m-%d %H:%M:%S").timetuple()))
            meta_type = META_TYPE_IDS.get(meta_type) or meta_type
            dicts = {
                "userId": user_id,
                "userName": user_name,
                "lastViewedAt": last_viewed,
                "type": meta_type,
                "deviceName": device_name,
                "deviceId": device_id,
                "bytes": data_bytes
            }
            results2.append(dicts)
        Log.Debug("Query1 completed.")

        query = """SELECT 
                        sm.account_id, sm.library_section_id, sm.grandparent_title, sm.parent_title, sm.title,
                        mi.id as rating_key, mi.tags_genre as genre, mi.tags_country as country, mi.year,
                        sm.viewed_at, sm.metadata_type, accounts.name, accounts.id as count
                    FROM metadata_item_views as sm
                    JOIN accounts
                    ON 
                    sm.account_id = accounts.id
                    LEFT JOIN metadata_items as mi
                    ON 
                        sm.title = mi.title 
                        AND sm.thumb_url = mi.user_thumb_url 
                        AND mi.originally_available_at = sm.originally_available_at
                    %s                        
                    ORDER BY sm.viewed_at desc;""" % query_string

        Log.Debug("Query2 is '%s'" % query)
        Log.Debug("Query selectors: %s" % JSON.StringFromObject(query_params))

        results = []
        for user_id, library_section, grandparent_title, parent_title, title, \
            rating_key, genre, country, year, \
            viewed_at, meta_type, user_name, foo in cursor.execute(query, query_params):
            meta_type = META_TYPE_IDS.get(meta_type) or meta_type
            last_viewed = int(time.mktime(datetime.datetime.strptime(viewed_at, "%Y-%m-%d %H:%M:%S").timetuple()))

            dicts = {
                "userId": user_id,
                "userName": user_name,
                "title": title,
                "parentTitle": parent_title,
                "grandparentTitle": grandparent_title,
                "librarySection": library_section,
                "lastViewedAt": last_viewed,
                "type": meta_type,
                "ratingKey": rating_key,
                "thumb": "/library/metadata/" + str(rating_key) + "/thumb",
                "art": "/library/metadata/" + str(rating_key) + "/art",
                "year": year,
                "genre": genre,
                "country": country
            }

            if meta_type == "episode":
                dicts["banner"] = "/library/metadata/" + str(rating_key) + "/banner/"

            results.append(dicts)

        Log.Debug("Query2 completed")

        query3 = """SELECT sum(bytes), account_id, device_id,
                    accounts.name AS account_name,
                    devices.name AS device_name, devices.identifier AS machine_identifier
                    FROM statistics_bandwidth
                    INNER JOIN accounts
                    ON accounts.id = account_id
                    INNER JOIN devices
                    ON devices.id = device_id
                    GROUP BY account_id, device_id
                    """

        device_results = []
        for total_bytes, account_id, device_id, account_name, device_name, machine_identifier in cursor.execute(query3):
            device_dict = {
                "userId": account_id,
                "userName": account_name,
                "deviceId": device_id,
                "deviceName": device_name,
                "machineIdentifier": machine_identifier,
                "totalBytes": total_bytes
            }
            device_results.append(device_dict)
        close_connection(connection)
        output = {}
        for record in results:
            record_date = str(record["lastViewedAt"])[:6]
            record_user = record["userName"]
            record_type = record["type"]
            if record_user not in output:
                output[record_user] = []
            for check in results2:
                check_date = str(check["lastViewedAt"])[:6]
                check_user = check["userName"]
                check_type = check["type"]
                if check_date == record_date and check_user == record_user and check_type == record_type:
                    for value in ["deviceName", "deviceId", "bytes"]:
                        record[value] = check[value]

            output[record_user].append(record)

        return [output, device_results]
    else:
        Log.Error("DB Connection error!")
        return None


def query_library_stats(headers):
    conn = fetch_cursor()
    cursor = conn[0]
    connection = conn[1]
    if cursor is not None:
        entitlements = get_entitlements()
        query = """SELECT
            FirstSet.library_section_id,
            FirstSet.metadata_type,    
            FirstSet.item_count,
            SecondSet.play_count,
            SecondSet.rating_key,
            SecondSet.title,
            SecondSet.grandparent_title,
            SecondSet.last_viewed,
            SecondSet.user_name,
            SecondSet.user_id,
            FirstSet.section_name,
            FirstSet.section_type
        FROM 
            (
                SELECT
                    mi.library_section_id,
                    mi.metadata_type,
                    ls.name AS section_name, ls.section_type,
                    count(mi.metadata_type) AS item_count
                FROM metadata_items AS mi
                INNER JOIN library_sections AS ls
                    ON mi.library_section_id = ls.id
                WHERE library_section_id IS NOT NULL
                GROUP BY library_section_id, metadata_type
            ) AS FirstSet
        LEFT JOIN
            (
                SELECT 
                    mi.id AS rating_key,
                    miv.title AS title,
                    miv.library_section_id,
                    miv.viewed_at AS last_viewed,
                    miv.metadata_type,
                    miv.grandparent_title AS grandparent_title,
                    count(miv.metadata_type) AS play_count,
                    accounts.name AS user_name, accounts.id AS user_id,
                    ls.name AS section_name, ls.section_type AS section_type,
                    max(viewed_at) AS last_viewed 
                FROM metadata_item_views AS miv
                INNER JOIN library_sections AS ls
                    ON miv.library_section_id = ls.id
                INNER JOIN metadata_items AS mi
                    ON mi.title = miv.title
                INNER JOIN accounts
                    ON miv.account_id = accounts.id
                AND
                    mi.metadata_type = miv.metadata_type             
                WHERE mi.library_section_id IS NOT NULL
                AND mi.library_section_id in %s
                GROUP BY miv.metadata_type
            ) AS SecondSet
        ON FirstSet.library_section_id = SecondSet.library_section_id AND FirstSet.metadata_type = SecondSet.metadata_type
        WHERE FirstSet.library_section_id in %s
        GROUP BY FirstSet.library_section_id, FirstSet.metadata_type
        ORDER BY FirstSet.library_section_id;""" % (entitlements, entitlements)

        Log.Debug("Querys is '%s'" % query)
        results = []
        for section, meta_type, item_count, play_count, ratingkey, title, \
            grandparent_title, last_viewed, user_name, user_id, sec_name, sec_type in cursor.execute(
            query):

            meta_type = META_TYPE_IDS.get(meta_type) or meta_type

            if last_viewed is not None:
                last_viewed = int(time.mktime(time.strptime(last_viewed, '%Y-%m-%d %H:%M:%S')))

            dicts = {
                "section": section,
                "totalItems": item_count,
                "playCount": play_count,
                "title": title,
                "grandparentTitle": grandparent_title,
                "lastViewedAt": last_viewed,
                "type": meta_type,
                "username": user_name,
                "userId": user_id,
                "sectionType": sec_type,
                "sectionTitle": sec_name,
                "ratingKey": ratingkey,
                "thumb": "/library/metadata/" + str(ratingkey) + "/thumb",
                "art": "/library/metadata/" + str(ratingkey) + "/art"
            }

            if meta_type == "episode":
                dicts["banner"] = "/library/metadata/" + str(ratingkey) + "/banner/"

            results.append(dicts)
        count_query = """SELECT mi.total_items, miv.viewed_count, mi.metadata_type, mi.library_section_id
FROM (
    SELECT count(metadata_type) AS total_items, metadata_type, library_section_id
    FROM metadata_items
    GROUP BY metadata_type, library_section_id
) AS mi
INNER JOIN (
    SELECT count(metadata_type) AS viewed_count, metadata_type, library_section_id FROM (
        SELECT DISTINCT metadata_type, library_section_id, title, thumb_url
        FROM metadata_item_views
    ) AS umiv
    GROUP BY metadata_type, library_section_id
) AS miv
ON miv.library_section_id = mi.library_section_id AND miv.metadata_type = mi.metadata_type"""
        sec_counts = {}
        for total_items, viewed_count, meta_type, section_id in cursor.execute(count_query):
            meta_type = META_TYPE_IDS.get(meta_type) or meta_type
            dicts = {
                "sectionId": section_id,
                "type": meta_type,
                "totalItems": total_items,
                "viewedItems": viewed_count
            }
            sec_counts[str(section_id)] = dicts
        close_connection(connection)
        return [results, sec_counts]
    else:
        Log.Error("Error connecting to DB!")


def query_library_growth(headers):
    container_size = int(headers.get("Container-Size") or DEFAULT_CONTAINER_SIZE)
    container_start = int(headers.get("Container-Start") or DEFAULT_CONTAINER_START)
    results = []
    start_date = datetime.datetime.strftime(datetime.datetime.now(), DATE_STRUCTURE)
    end_date = "1900-01-01 00:00:00"
    if "Interval" in headers:
        interval = int(headers["Interval"])
        if "Start" in headers:
            start_check = headers.get("Start")
            if validate_date(start_check, DATE_STRUCTURE):
                Log.Debug("We have a start date, we'll use that.")
                start_date = start_check
                end_date = datetime.datetime.strftime(datetime.datetime.strptime(
                    start_date, DATE_STRUCTURE) - datetime.timedelta(days=interval), DATE_STRUCTURE)

        elif "End" in headers:
            end_check = headers.get("End")
            if validate_date(end_check, DATE_STRUCTURE):
                Log.Debug("We have an end date, we'll set interval from there.")
                end_date = end_check
                start_date = datetime.datetime.strftime(datetime.datetime.strptime(
                    end_date, DATE_STRUCTURE) + datetime.timedelta(days=interval), DATE_STRUCTURE)

        else:
            Log.Debug("No start or end params, going %s days from today." % interval)
            start_int = datetime.datetime.now()
            start_date = datetime.datetime.now().strftime(DATE_STRUCTURE)
            end_int = start_int - datetime.timedelta(days=interval)
            end_date = datetime.datetime.strftime(end_int, DATE_STRUCTURE)
            Log.Debug("start date is %s, end is %s" % (start_date, end_date))

    else:
        if "Start" in headers:
            start_check = headers.get("Start")
            if validate_date(start_check, DATE_STRUCTURE):
                Log.Debug("We have a start date, we'll use that.")
                start_date = start_check

        if "End" in headers:
            end_check = headers.get("End")
            if validate_date(end_check, DATE_STRUCTURE):
                Log.Debug("We have an end date, we'll set interval from there.")
                end_date = end_check

    Log.Debug("Okay, we should have start and end dates of %s and %s" % (start_date, end_date))

    conn = fetch_cursor()
    cursor = conn[0]
    connection = conn[1]
    if cursor is not None:
        Log.Debug("Ready to query!")
        query = """SELECT mi1.id, mi1.title, mi1.year, mi1.metadata_type, mi1.created_at, mi1.tags_genre AS genre, mi1.tags_country AS country, mi1.parent_id,
                    mi2.title AS parent_title, mi2.parent_id AS grandparent_id, mi2.tags_genre AS parent_genre, mi2.tags_country AS parent_country,
                    mi3.title AS grandparent_title, mi3.tags_genre AS grandparent_genre, mi3.tags_country AS grandparent_country
                    FROM metadata_items AS mi1
                    LEFT JOIN metadata_items AS mi2
                    ON mi1.parent_id = mi2.id
                    LEFT JOIN metadata_items AS mi3
                    ON mi2.parent_id = mi3.id
                    WHERE mi1.created_at BETWEEN ? AND ?
                    AND mi1.metadata_type IN (1, 4, 10)
                    AND mi1.title NOT IN ("", "com.plexapp.agents")
                    ORDER BY mi1.created_at DESC;
        """
        params = (end_date, start_date)
        Log.Debug("Query is '%s'" % query)
        i = 0
        container_max = container_start + container_size
        for rating_key, title, year, meta_type, created_at, genres, country, \
            parent_id, parent_title, parent_genre, parent_country, \
            grandparent_id, grandparent_title, grandparent_genre, grandparent_country in cursor.execute(query, params):
            if i >= container_max:
                break

            if i >= container_start:
                meta_type = META_TYPE_IDS.get(meta_type) or meta_type
                dicts = {
                    "ratingKey": rating_key,
                    "title": title,
                    "parentTitle": parent_title,
                    "parentId": parent_id,
                    "parentGenre": parent_genre,
                    "parentCountry": parent_country,
                    "grandparentTitle": grandparent_title,
                    "grandparentId": grandparent_id,
                    "grandparentGenre": grandparent_genre,
                    "grandparentCountry": grandparent_country,
                    "year": year,
                    "thumb": "/library/metadata/" + str(rating_key) + "/thumb",
                    "art": "/library/metadata/" + str(rating_key) + "/art",
                    "type": meta_type,
                    "genres": genres,
                    "country": country,
                    "addedAt": created_at
                }
                results.append(dicts)
            i += 1
        close_connection(connection)
    return results


def fetch_cursor():
    cursor = None
    connection = None
    if os.environ["Loaded"]:
        import apsw
        Log.Debug("Shit, we got the librarys!")
        connection = apsw.Connection(os.environ['LIBRARY_DB'])
        cursor = connection.cursor()
    return [cursor, connection]


def close_connection(connection):
    if connection is not None:
        Log.Debug("Closing connection..")
        connection.close()
    else:
        Log.Debug("No connection to close!")


def vcr_ver():
    msvcr_map = {
        'msvcr120.dll': 'vc12',
        'msvcr130.dll': 'vc14'
    }
    try:
        import ctypes.util

        # Retrieve linked msvcr dll
        name = ctypes.util.find_msvcrt()

        # Return VC++ version from map
        if name not in msvcr_map:
            Log.Error('Unknown VC++ runtime: %r', name)
            return None

        return msvcr_map[name]
    except Exception as ex:
        Log.Error('Unable to retrieve VC++ runtime version: %s' % ex, exc_info=True)
        return None


def init_apsw():
    try:
        import apsw
    except ImportError:
        Log.Error("Shit, module not imported")
    pass


def insert_paths(distribution, libraries_path):
    # Retrieve system details
    system = SystemHelper.name()
    architecture = SystemHelper.architecture()

    if not architecture:
        Log.Debug('Unable to retrieve system architecture')
        return False

    Log.Debug('System: %r, Architecture: %r', system, architecture)

    # Build architecture list
    architectures = [architecture]

    if architecture == 'i686':
        # Fallback to i386
        architectures.append('i386')

    # Insert library paths
    found = False

    for arch in architectures + ['universal']:
        if insert_architecture_paths(libraries_path, system, arch):
            Log.Debug('Inserted libraries path for system: %r, arch: %r', system, arch)
            found = True

    # Display interface message if no libraries were found
    if not found:
        if distribution and distribution.get('name'):
            message = 'Unable to find compatible native libraries in the %s distribution' % distribution['name']
        else:
            message = 'Unable to find compatible native libraries'
        Log.Debug(message)

        # InterfaceMessages.add(60, '%s (system: %r, architecture: %r)', message, system, architecture)

    return found


def insert_architecture_paths(libraries_path, system, architecture):
    architecture_path = os.path.join(libraries_path, system, architecture)

    if not os.path.exists(architecture_path):
        Log.Debug("Arch path %s doesn't exist!!" % architecture_path)
        return False

    # Architecture libraries
    Log.Debug("inserting libs path")
    PathHelper.insert(libraries_path, system, architecture)

    # System libraries
    if system == 'Windows':
        # Windows libraries (VC++ specific)
        insert_paths_windows(libraries_path, system, architecture)
    else:
        # Darwin/FreeBSD/Linux libraries
        insert_paths_unix(libraries_path, system, architecture)

    return True


def insert_paths_unix(libraries_path, system, architecture):
    # UCS specific libraries
    ucs = UNICODE_MAP.get(sys.maxunicode)
    Log.Debug('UCS: %r', ucs)

    if ucs:
        Log.Debug("inserting UCS path")
        PathHelper.insert(libraries_path, system, architecture, ucs)

    # CPU specific libraries
    cpu_type = SystemHelper.cpu_type()
    page_size = SystemHelper.page_size()

    Log.Debug('CPU Type: %r', cpu_type)
    Log.Debug('Page Size: %r', page_size)

    if cpu_type:
        Log.Debug("Inserting CPU Type path")
        PathHelper.insert(libraries_path, system, architecture, cpu_type)

        if page_size:
            Log.Debug("Page Size path")
            PathHelper.insert(libraries_path, system, architecture, '%s_%s' % (cpu_type, page_size))

    # UCS + CPU specific libraries
    if cpu_type and ucs:
        Log.Debug("CPU + UCS path")
        PathHelper.insert(libraries_path, system, architecture, cpu_type, ucs)

        if page_size:
            Log.Debug("And page size")
            PathHelper.insert(libraries_path, system, architecture, '%s_%s' % (cpu_type, page_size), ucs)


def insert_paths_windows(libraries_path, system, architecture):
    vcr = SystemHelper.vcr_version() or 'vc12'  # Assume "vc12" if call fails
    ucs = UNICODE_MAP.get(sys.maxunicode)

    Log.Debug('VCR: %r, UCS: %r', vcr, ucs)

    # VC++ libraries
    Log.Debug("Inserting vcr path")
    PathHelper.insert(libraries_path, system, architecture, vcr)

    # UCS libraries
    if ucs:
        Log.Debug("Inserting UCS path")
        PathHelper.insert(libraries_path, system, architecture, vcr, ucs)


def get_entitlements():
    token = False
    allowed_keys = []

    for key, value in Request.Headers.items():
        Log.Debug("Header key %s is %s", key, value)
        if key in ("X-Plex-Token", "Token"):
            Log.Debug("We have a Token")
            token = value

    if token:
        server_port = os.environ.get("PLEXSERVERPORT")
        if server_port is None:
            server_port = "32400"
        server_host = Network.Address
        if server_host is None:
            server_host = "localhost"

        try:
            my_url = "http://%s:%s/library/sections?X-Plex-Token=%s" % (server_host, server_port, token)
        except TypeError:
            my_url = False
            pass

        if my_url:
            Log.Debug("Gonna touch myself at '%s'" % my_url)
            req = HTTP.Request(my_url)
            req.load()
            if hasattr(req, 'content'):
                client_data = req.content
                root = ET.fromstring(client_data)
                for section in root.iter('Directory'):
                    Log.Debug("Section?")
                    allowed_keys.append(section.get("key"))

    if len(allowed_keys) != 0:
        allowed_keys = "(" + ", ".join(allowed_keys) + ")"
        Log.Debug("Hey, we got the keys: %s" % allowed_keys)
    else:
        allowed_keys = "()"
        Log.Debug("No keys, try again.")

    return allowed_keys


####################################
# These functions are for utility stuff
def get_time_difference(time_start, time_end):
    time_diff = time_end - time_start
    return time_diff.total_seconds() / 60


def sort_headers(header_list, strict=False):
    returns = {}
    for key, value in Request.Headers.items():
        Log.Debug("Header key %s is %s", key, value)
        for item in header_list:
            if key in ("X-Plex-" + item, item):
                Log.Debug("We have a " + item)
                value = unicode(value)
                is_int = False
                try:
                    test = int(value)
                    is_int = True
                except ValueError:
                    Log.Debug("Value is not a string")
                    pass
                else:
                    value = test

                if not is_int:
                    try:
                        value = value.split(",")
                    except ValueError:
                        Log.Debug("Value is not a csv")
                        pass
                    else:
                        Log.Debug("Value is a csv!")

                returns[item] = value
                header_list.remove(item)

    if strict:
        len2 = len(header_list)
        if len2 == 0:
            Log.Debug("We have all of our values: " + JSON.StringFromObject(returns))
            return returns

        else:
            Log.Error("Sorry, parameters are missing.")
            for item in header_list:
                Log.Error("Missing " + item)
            return False
    else:
        return returns


def get_log_paths():
    # find log handler
    server_log_path = False
    plugin_log_path = False
    for handler in Core.log.handlers:
        if getattr(getattr(handler, "__class__"), "__name__") in (
                'FileHandler', 'RotatingFileHandler', 'TimedRotatingFileHandler'):
            plugin_log_file = handler.baseFilename
            if os.path.isfile(os.path.realpath(plugin_log_file)):
                plugin_log_path = plugin_log_file
                Log.Debug("Found a plugin path: " + plugin_log_path)

            if plugin_log_file:
                server_log_file = os.path.realpath(os.path.join(plugin_log_file, "../../Plex Media Server.log"))
                if os.path.isfile(server_log_file):
                    server_log_path = server_log_file
                    Log.Debug("Found a server log path: " + server_log_path)

    return [plugin_log_path, server_log_path]


def log_data(data):
    Log.Debug("Is there data?? " + JSON.StringFromObject(data))


def DispatchRestart():
    Thread.CreateTimer(1.0, Restart)


def validate_date(date_text, date_format):
    try:
        datetime.datetime.strptime(date_text, date_format)
        return True
    except ValueError:
        Log.Error("Incorrect date format, should be %s" % date_format)
        return False
