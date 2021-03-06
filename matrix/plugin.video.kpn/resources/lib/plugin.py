import _strptime

import datetime, json, pytz, random, string, sys, time, xbmc, xbmcplugin

from fuzzywuzzy import fuzz
from resources.lib.api import API
from resources.lib.base import plugin, gui, signals, inputstream, settings
from resources.lib.base.exceptions import Error
from resources.lib.base.log import log
from resources.lib.base.util import check_key, convert_datetime_timezone, date_to_nl_dag, date_to_nl_maand, get_credentials, load_file
from resources.lib.constants import CONST_IMAGE_URL, CONST_BASE_HEADERS
from resources.lib.language import _

try:
    unicode
except NameError:
    unicode = str

api = API()
ADDON_HANDLE = int(sys.argv[1])
backend = ''
query_channel = {}

@plugin.route('')
def home(**kwargs):
    if settings.getBool(key='_first_boot') == True:
        first_boot()

    folder = plugin.Folder()

    if not plugin.logged_in:
        folder.add_item(label=_(_.LOGIN, _bold=True), path=plugin.url_for(func_or_url=login))
    else:
        folder.add_item(label=_(_.LIVE_TV, _bold=True),  path=plugin.url_for(func_or_url=live_tv))
        folder.add_item(label=_(_.CHANNELS, _bold=True), path=plugin.url_for(func_or_url=replaytv))

        if settings.getBool('showMoviesSeries') == True:
            folder.add_item(label=_(_.SERIES, _bold=True), path=plugin.url_for(func_or_url=vod, file='series', label=_.SERIES, start=0))
            folder.add_item(label=_(_.MOVIES, _bold=True), path=plugin.url_for(func_or_url=vod, file='movies', label=_.MOVIES, start=0))
            folder.add_item(label=_(_.KIDS_SERIES, _bold=True), path=plugin.url_for(func_or_url=vod, file='kidsseries', label=_.KIDS_SERIES, start=0))
            folder.add_item(label=_(_.KIDS_MOVIES, _bold=True), path=plugin.url_for(func_or_url=vod, file='kidsmovies', label=_.KIDS_MOVIES, start=0))

        folder.add_item(label=_(_.SEARCH, _bold=True), path=plugin.url_for(func_or_url=search_menu))

    folder.add_item(label=_.SETTINGS, path=plugin.url_for(func_or_url=settings_menu))

    return folder

#Main menu items
@plugin.route()
def login(**kwargs):
    if len(settings.get(key='_devicekey')) == 0:
        settings.set(key='_devicekey', value=''.join(random.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(64)))

    creds = get_credentials()
    username = gui.numeric(message=_.ASK_USERNAME, default=creds['username']).strip()

    if not len(username) > 0:
        gui.ok(message=_.EMPTY_USER, heading=_.LOGIN_ERROR_TITLE)
        return

    password = gui.numeric(message=_.ASK_PASSWORD).strip()

    if not len(password) > 0:
        gui.ok(message=_.EMPTY_PASS, heading=_.LOGIN_ERROR_TITLE)
        return

    api.login(username=username, password=password, channels=True)
    plugin.logged_in = api.logged_in

    gui.refresh()

@plugin.route()
def live_tv(**kwargs):
    folder = plugin.Folder(title=_.LIVE_TV)

    for row in get_live_channels(addon=settings.getBool(key='enable_simple_iptv')):
        folder.add_item(
            label = row['label'],
            info = {'plot': row['description']},
            art = {'thumb': row['image']},
            path = row['path'],
            playable = row['playable'],
        )

    return folder

@plugin.route()
def replaytv(**kwargs):
    folder = plugin.Folder(title=_.CHANNELS)

    folder.add_item(
        label = _.PROGSAZ,
        info = {'plot': _.PROGSAZDESC},
        path = plugin.url_for(func_or_url=replaytv_alphabetical),
    )

    for row in get_replay_channels():
        folder.add_item(
            label = row['label'],
            info = {'plot': row['description']},
            art = {'thumb': row['image']},
            path = row['path'],
            playable = row['playable'],
        )

    return folder

@plugin.route()
def replaytv_alphabetical(**kwargs):
    folder = plugin.Folder(title=_.PROGSAZ)
    label = _.OTHERTITLES

    folder.add_item(
        label = label,
        info = {'plot': _.OTHERTITLESDESC},
        path = plugin.url_for(func_or_url=replaytv_list, label=label, start=0, character='other'),
    )

    for character in string.ascii_uppercase:
        label = _.TITLESWITH + character

        folder.add_item(
            label = label,
            info = {'plot': _.TITLESWITHDESC + character},
            path = plugin.url_for(func_or_url=replaytv_list, label=label, start=0, character=character),
        )

    return folder

@plugin.route()
def replaytv_list(character, label='', start=0, **kwargs):
    start = int(start)
    folder = plugin.Folder(title=label)

    data = load_file(file='list_replay.json', isJSON=True)

    if not data:
        gui.ok(message=_.NO_REPLAY_TV_INFO, heading=_.NO_REPLAY_TV_INFO)
        return folder

    if not check_key(data, character):
        return folder

    processed = process_replaytv_list(data=data[character], start=start)

    if check_key(processed, 'items'):
        folder.add_items(processed['items'])

    if check_key(processed, 'count') and len(data[character]) > processed['count']:
        folder.add_item(
            label = _(_.NEXT_PAGE, _bold=True),
            path = plugin.url_for(func_or_url=replaytv_list, character=character, label=label, start=processed['count']),
        )

    return folder

@plugin.route()
def replaytv_by_day(label='', image='', description='', station='', **kwargs):
    folder = plugin.Folder(title=label)

    for x in range(0, 7):
        curdate = datetime.date.today() - datetime.timedelta(days=x)

        itemlabel = ''

        if x == 0:
            itemlabel = _.TODAY + " - "
        elif x == 1:
            itemlabel = _.YESTERDAY + " - "

        if xbmc.getLanguage(xbmc.ISO_639_1) == 'nl':
            itemlabel += date_to_nl_dag(curdate=curdate) + curdate.strftime(" %d ") + date_to_nl_maand(curdate=curdate) + curdate.strftime(" %Y")
        else:
            itemlabel += curdate.strftime("%A %d %B %Y").capitalize()

        folder.add_item(
            label = itemlabel,
            info = {'plot': description},
            art = {'thumb': image},
            path = plugin.url_for(func_or_url=replaytv_content, label=itemlabel, day=x, station=station),
        )

    return folder

@plugin.route()
def replaytv_item(ids=None, label=None, start=0, **kwargs):
    start = int(start)
    first = label[0]

    folder = plugin.Folder(title=label)

    if first.isalpha():
        data = load_file(file=first + "_replay.json", isJSON=True)
    else:
        data = load_file(file='other_replay.json', isJSON=True)

    if not data:
        return folder

    processed = process_replaytv_list_content(data=data, ids=ids, start=start)

    if check_key(processed, 'items'):
        folder.add_items(processed['items'])

    if check_key(processed, 'totalrows') and check_key(processed, 'count') and processed['totalrows'] > processed['count']:
        folder.add_item(
            label = _(_.NEXT_PAGE, _bold=True),
            path = plugin.url_for(func_or_url=replaytv_item, ids=ids, label=label, start=processed['count']),
        )

    return folder

@plugin.route()
def replaytv_content(label, day, station='', start=0, **kwargs):
    day = int(day)
    start = int(start)
    folder = plugin.Folder(title=label)

    data = load_file(file=station + "_replay.json", isJSON=True)

    if not data:
        gui.ok(_.DISABLE_ONLY_STANDARD, _.NO_REPLAY_TV_INFO)
        return folder

    totalrows = len(data)
    processed = process_replaytv_content(data=data, day=day, start=start)

    if check_key(processed, 'items'):
        folder.add_items(processed['items'])

    if check_key(processed, 'count') and totalrows > processed['count']:
        folder.add_item(
            label = _(_.NEXT_PAGE, _bold=True),
            path = plugin.url_for(func_or_url=replaytv_content, label=label, day=day, station=station, start=processed['count']),
        )

    return folder

@plugin.route()
def vod(file, label, start=0, **kwargs):
    start = int(start)
    folder = plugin.Folder(title=label)

    data = load_file(file='vod.json', isJSON=True)[file]

    if not data:
        return folder

    processed = process_vod_content(data=data, start=start, type=label)

    if check_key(processed, 'items'):
        folder.add_items(processed['items'])

    if check_key(processed, 'count') and len(data) > processed['count']:
        folder.add_item(
            label = _(_.NEXT_PAGE, _bold=True),
            path = plugin.url_for(func_or_url=vod, file=file, label=label, start=processed['count']),
        )

    return folder

@plugin.route()
def vod_series(label, description, image, id, **kwargs):
    folder = plugin.Folder(title=label)

    items = []

    seasons = api.vod_seasons(id)

    title = label

    for season in seasons:
        label = _.SEASON + " " + unicode(season['seriesNumber'])

        items.append(plugin.Item(
            label = label,
            info = {'plot': season['desc']},
            art = {
                'thumb': "{image_url}/vod/{image}/{img_size}.jpg?blurred=false".format(image_url=CONST_IMAGE_URL, image=season['image'], img_size=settings.get(key='_img_size')),
                'fanart': "{image_url}/vod/{image}/1920x1080.jpg?blurred=false".format(image_url=CONST_IMAGE_URL, image=season['image'])
            },
            path = plugin.url_for(func_or_url=vod_season, label=label, title=title, id=season['id']),
        ))

    folder.add_items(items)

    return folder

@plugin.route()
def vod_season(label, title, id, **kwargs):
    folder = plugin.Folder(title=label)

    items = []

    season = api.vod_season(id)

    for episode in season:
        items.append(plugin.Item(
            label = episode['episodeNumber'] + " - " + episode['title'],
            info = {
                'plot': episode['desc'],
                'duration': episode['duration'],
                'mediatype': 'video',
            },
            art = {
                'thumb': "{image_url}/vod/{image}/{img_size}.jpg?blurred=false".format(image_url=CONST_IMAGE_URL, image=episode['image'], img_size=settings.get(key='_img_size')),
                'fanart': "{image_url}/vod/{image}/1920x1080.jpg?blurred=false".format(image_url=CONST_IMAGE_URL, image=episode['image'])
            },
            path = plugin.url_for(func_or_url=play_video, type='vod', channel=None, id=episode['id'], asset_id=episode['assetid'], title=title, _is_live=False),
            playable = True,
        ))

    folder.add_items(items)

    return folder

@plugin.route()
def search_menu(**kwargs):
    folder = plugin.Folder(title=_.SEARCHMENU)
    label = _.NEWSEARCH

    folder.add_item(
        label = label,
        info = {'plot': _.NEWSEARCHDESC},
        path = plugin.url_for(func_or_url=search),
    )

    for x in range(1, 10):
        searchstr = settings.get(key='_search' + unicode(x))

        if searchstr != '':
            label = searchstr

            folder.add_item(
                label = label,
                info = {'plot': _(_.SEARCH_FOR, query=searchstr)},
                path = plugin.url_for(func_or_url=search, query=searchstr),
            )

    return folder

@plugin.route()
def search(query=None, **kwargs):
    items = []

    if not query:
        query = gui.input(message=_.SEARCH, default='').strip()

        if not query:
            return

        for x in reversed(list(range(2, 10))):
            settings.set(key='_search' + unicode(x), value=settings.get(key='_search' + unicode(x - 1)))

        settings.set(key='_search1', value=query)

    folder = plugin.Folder(title=_(_.SEARCH_FOR, query=query))

    data = load_file(file='list_replay.json', isJSON=True)
    processed = process_replaytv_search(data=data, start=0, search=query)
    items += processed['items']

    if settings.getBool('showMoviesSeries') == True:
        processed = process_vod_content(data=load_file(file='vod.json', isJSON=True)['series'], start=0, search=query, type=_.SERIES)
        items += processed['items']
        processed = process_vod_content(data=load_file(file='vod.json', isJSON=True)['movies'], start=0, search=query, type=_.MOVIES)
        items += processed['items']
        processed = process_vod_content(data=load_file(file='vod.json', isJSON=True)['kidsseries'], start=0, search=query, type=_.KIDS_SERIES)
        items += processed['items']
        processed = process_vod_content(data=load_file(file='vod.json', isJSON=True)['kidsmovies'], start=0, search=query, type=_.KIDS_MOVIES)
        items += processed['items']

    items[:] = sorted(items, key=_sort_replay_items, reverse=True)
    items = items[:25]

    folder.add_items(items)

    return folder

@plugin.route()
def settings_menu(**kwargs):
    folder = plugin.Folder(title=_.SETTINGS)

    folder.add_item(label=_.INSTALL_WV_DRM, path=plugin.url_for(func_or_url=plugin._ia_install))
    folder.add_item(label=_.SET_IPTV, path=plugin.url_for(func_or_url=plugin._set_settings_iptv))
    folder.add_item(label=_.SET_KODI, path=plugin.url_for(func_or_url=plugin._set_settings_kodi))
    folder.add_item(label=_.DOWNLOAD_SETTINGS, path=plugin.url_for(func_or_url=plugin._download_settings))
    folder.add_item(label=_.DOWNLOAD_EPG, path=plugin.url_for(func_or_url=plugin._download_epg))
    folder.add_item(label=_.RESET_SESSION, path=plugin.url_for(func_or_url=logout, delete=False))
    folder.add_item(label=_.RESET, path=plugin.url_for(func_or_url=plugin._reset))

    if plugin.logged_in:
        folder.add_item(label=_.LOGOUT, path=plugin.url_for(func_or_url=logout))

    folder.add_item(label="Addon " + _.SETTINGS, path=plugin.url_for(func_or_url=plugin._settings))

    return folder

@plugin.route()
def logout(delete=True, **kwargs):
    if delete == True:
        if not gui.yes_no(message=_.LOGOUT_YES_NO):
            return

        settings.remove(key='_username')
        settings.remove(key='_pswd')

    api.clear_session()
    api.new_session(force=True, channels=True)
    plugin.logged_in = api.logged_in
    gui.refresh()

@plugin.route()
@plugin.login_required()
def play_video(type=None, channel=None, id=None, title=None, **kwargs):
    properties = {}

    if not type and not len(type) > 0:
        return False

    if type == 'program':
        properties['seekTime'] = 1

    playdata = api.play_url(type=type, channel=channel, id=id)

    if not playdata or not check_key(playdata, 'path') or not check_key(playdata, 'token'):
        return False

    CDMHEADERS = CONST_BASE_HEADERS
    CDMHEADERS['User-Agent'] = settings.get(key='_user_agent')

    if type == 'channel':
        playdata['path'] = playdata['path'].split("&", 1)[0]
    else:
        playdata['path'] = playdata['path'].split("&min_bitrate", 1)[0]

    if check_key(playdata, 'license'):
        item_inputstream = inputstream.Widevine(
            license_key = playdata['license'],
            media_renewal_url = plugin.url_for(func_or_url=renew_token, type=type, channel=channel, id=id),
        )
    else:
        item_inputstream = inputstream.MPD(
            media_renewal_url = plugin.url_for(func_or_url=renew_token, type=type, channel=channel, id=id),
        )

    itemlabel = ''
    label2 = ''
    cast = []
    director = []
    writer = []
    genres = []
    description = ''
    program_image_large = ''
    duration = 0

    if playdata['info'] and check_key(playdata['info'], 'resultObj'):
        for row in playdata['info']['resultObj']['containers']:
            if check_key(row, 'metadata'):
                if check_key(row['metadata'], 'airingStartTime') and check_key(row['metadata'], 'airingEndTime'):
                    startT = datetime.datetime.fromtimestamp(int(int(row['metadata']['airingStartTime']) / 1000))
                    startT = convert_datetime_timezone(startT, "UTC", "UTC")
                    endT = datetime.datetime.fromtimestamp(int(int(row['metadata']['airingEndTime']) / 1000))
                    endT = convert_datetime_timezone(endT, "UTC", "UTC")

                    duration = int((endT - startT).total_seconds())

                    if xbmc.getLanguage(xbmc.ISO_639_1) == 'nl':
                        itemlabel = '{weekday} {day} {month} {yearhourminute} '.format(weekday=date_to_nl_dag(startT), day=startT.strftime("%d"), month=date_to_nl_maand(startT), yearhourminute=startT.strftime("%Y %H:%M"))
                    else:
                        itemlabel = startT.strftime("%A %d %B %Y %H:%M ").capitalize()

                    itemlabel += " - "


                if title:
                    itemlabel += title + ' - '

                if check_key(row['metadata'], 'title'):
                    itemlabel += row['metadata']['title']

                if check_key(row['metadata'], 'longDescription'):
                    description = row['metadata']['longDescription']

                if playdata['type'] == 'VOD':
                    imgtype = 'vod'
                else:
                    imgtype = 'epg'

                if check_key(row['metadata'], 'pictureUrl'):
                    program_image = "{image_url}/{imgtype}/{image}/{img_size}.jpg?blurred=false".format(image_url=CONST_IMAGE_URL, imgtype=imgtype, image=row['metadata']['pictureUrl'], img_size=settings.get(key='_img_size'))
                    program_image_large = "{image_url}/{imgtype}/{image}/1920x1080.jpg?blurred=false".format(image_url=CONST_IMAGE_URL, imgtype=imgtype, image=row['metadata']['pictureUrl'])

                if check_key(row['metadata'], 'actors'):
                    for castmember in row['metadata']['actors']:
                        cast.append(castmember)

                if check_key(row['metadata'], 'directors'):
                    for directormember in row['metadata']['directors']:
                        director.append(directormember)

                if check_key(row['metadata'], 'authors'):
                    for writermember in row['metadata']['authors']:
                        writer.append(writermember)

                if check_key(row['metadata'], 'genres'):
                    for genre in row['metadata']['genres']:
                        genres.append(genre)

                if check_key(row['metadata'], 'duration'):
                    duration = row['metadata']['duration']

                epcode = ''

                if check_key(row['metadata'], 'season'):
                    epcode += 'S' + unicode(row['metadata']['season'])

                if check_key(row['metadata'], 'episodeNumber'):
                    epcode += 'E' + unicode(row['metadata']['episodeNumber'])

                if check_key(row['metadata'], 'episodeTitle'):
                    label2 = row['metadata']['episodeTitle']

                    if len(epcode) > 0:
                        label2 += " (" + epcode + ")"
                elif check_key(row['metadata'], 'title'):
                    label2 = row['metadata']['title']

                if check_key(row, 'channel'):
                    if check_key(row['channel'], 'channelName'):
                        label2 += " - "  + row['channel']['channelName']

    settings.setInt(key='_stream_duration', value=duration)

    listitem = plugin.Item(
        label = itemlabel,
        label2 = label2,
        art = {
            'thumb': program_image,
            'fanart': program_image_large
        },
        info = {
            'cast': cast,
            'writer': writer,
            'director': director,
            'genre': genres,
            'plot': description,
            'duration': duration,
            'mediatype': 'video',
        },
        properties = properties,
        path = playdata['path'],
        headers = CDMHEADERS,
        inputstream = item_inputstream,
    )

    return listitem

@plugin.route()
@plugin.login_required()
def switchChannel(channel_uid, **kwargs):
    xbmc.executebuiltin('PlayMedia(pvr://channels/tv/{allchan}/{backend}_{channel_uid}.pvr)'.format(allchan=xbmc.getLocalizedString(19287), backend=backend, channel_uid=channel_uid))

@plugin.route()
@plugin.login_required()
def renew_token(type=None, channel=None, id=None, **kwargs):
    playdata = api.play_url(type=type, channel=channel, id=id, force=False)

    if not playdata or not check_key(playdata, 'path') or not check_key(playdata, 'token'):
        return False

    playdata['path'] = playdata['path'].rsplit('/', 1)[0]

    listitem = plugin.Item(
        path = playdata['path'],
    )

    newItem = listitem.get_li()

    xbmcplugin.addDirectoryItem(ADDON_HANDLE, playdata['path'], newItem)
    xbmcplugin.endOfDirectory(ADDON_HANDLE, cacheToDisc=False)
    time.sleep(0.1)

@signals.on(signals.BEFORE_DISPATCH)
def before_dispatch():
    api.new_session()
    plugin.logged_in = api.logged_in

#Support functions
def first_boot():
    if gui.yes_no(message=_.SET_IPTV):
        try:
            plugin._set_settings_iptv()
        except:
            pass
    if gui.yes_no(message=_.SET_KODI):
        try:
            plugin._set_settings_kodi()
        except:
            pass

    settings.setBool(key='_first_boot', value=False)

def get_live_channels(addon=False):
    global backend, query_channel
    channels = []
    rows = load_file(file='channels.json', isJSON=True)

    if rows:
        if addon == True:
            query_addons = json.loads(xbmc.executeJSONRPC('{"jsonrpc": "2.0", "id": 1, "method": "Addons.GetAddons", "params": {"type": "xbmc.pvrclient"}}'))

            if check_key(query_addons, 'result') and check_key(query_addons['result'], 'addons'):
                addons = query_addons['result']['addons']
                backend = addons[0]['addonid']

                query_channel = json.loads(xbmc.executeJSONRPC('{"jsonrpc": "2.0", "method": "PVR.GetChannels", "params": {"channelgroupid": "alltv", "properties" :["uniqueid"]},"id": 1}'))

        for row in rows:
            channeldata = api.get_channel_data(row=row)

            path = plugin.url_for(func_or_url=play_video, type='channel', channel=channeldata['channel_id'], id=channeldata['asset_id'], _is_live=True)
            playable = True

            if addon == True and 'result' in query_channel:
                if 'channels' in query_channel['result']:
                    pvrchannels = query_channel['result']['channels']

                    for channel in pvrchannels:
                        if channel['label'] == channeldata['label']:
                            channel_uid = channel['uniqueid']
                            path = plugin.url_for(func_or_url=switchChannel, channel_uid=channel_uid)
                            playable = False
                            break

            channels.append({
                'label': channeldata['label'],
                'channel': channeldata['channel_id'],
                'chno': channeldata['channel_number'],
                'description': channeldata['description'],
                'image': channeldata['station_image_large'],
                'path':  path,
                'playable': playable,
            })

        channels[:] = sorted(channels, key=_sort_live)

    return channels

def get_replay_channels():
    channels = []
    rows = load_file(file='channels.json', isJSON=True)

    if rows:
        for row in rows:
            channeldata = api.get_channel_data(row=row)

            channels.append({
                'label': channeldata['label'],
                'channel': channeldata['channel_id'],
                'chno': channeldata['channel_number'],
                'description': channeldata['description'],
                'image': channeldata['station_image_large'],
                'path': plugin.url_for(func_or_url=replaytv_by_day, image=channeldata['station_image_large'], description=channeldata['description'], label=channeldata['label'], station=channeldata['channel_id']),
                'playable': False,
            })

        channels[:] = sorted(channels, key=_sort_live)

    return channels

def process_replaytv_list(data, start=0):
    start = int(start)
    items = []
    count = 0
    item_count = 0
    time_now = int((datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds())

    for row in sorted(data):
        currow = data[row]

        if item_count == 51:
            break

        if count < start:
            count += 1
            continue

        count += 1

        if not check_key(currow, 'orig') or not check_key(currow, 'ids'):
            continue

        if check_key(currow, 'a') and check_key(currow, 'e') and (time_now < int(currow['a']) or time_now > int(currow['e'])):
            continue

        label = currow['orig']

        items.append(plugin.Item(
            label = label,
            path = plugin.url_for(func_or_url=replaytv_item, ids=json.dumps(currow['ids']), label=label, start=0),
        ))

        item_count += 1

    return {'items': items, 'count': count}

def process_replaytv_search(data, start=0, search=None):
    start = int(start)
    items = []
    count = 0
    item_count = 0
    time_now = int((datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds())

    for row in data:
        letter_row = data[row]

        for row2 in letter_row:
            currow = data[row][row2]

            if item_count == 51:
                break

            if count < start:
                count += 1
                continue

            count += 1

            if not check_key(currow, 'orig') or not check_key(currow, 'ids'):
                continue

            if check_key(currow, 'a') and check_key(currow, 'e') and (time_now < int(currow['a']) or time_now > int(currow['e'])):
                continue

            label = currow['orig'] + ' (ReplayTV)'

            fuzz_set = fuzz.token_set_ratio(label, search)
            fuzz_partial = fuzz.partial_ratio(label, search)
            fuzz_sort = fuzz.token_sort_ratio(label, search)

            if (fuzz_set + fuzz_partial + fuzz_sort) > 160:
                items.append(plugin.Item(
                    label = label,
                    properties = {"fuzz_set": fuzz_set, "fuzz_sort": fuzz_sort, "fuzz_partial": fuzz_partial, "fuzz_total": fuzz_set + fuzz_partial + fuzz_sort},
                    path = plugin.url_for(func_or_url=replaytv_item, ids=json.dumps(currow['ids']), label=label, start=0),
                ))

                item_count += 1

    return {'items': items, 'count': count}

def process_replaytv_content(data, day=0, start=0):
    day = int(day)
    start = int(start)
    curdate = datetime.date.today() - datetime.timedelta(days=day)

    startDate = convert_datetime_timezone(datetime.datetime(curdate.year, curdate.month, curdate.day, 0, 0, 0), "Europe/Amsterdam", "UTC")
    endDate = convert_datetime_timezone(datetime.datetime(curdate.year, curdate.month, curdate.day, 23, 59, 59), "Europe/Amsterdam", "UTC")
    startTime = startDate.strftime("%Y%m%d%H%M%S")
    endTime = endDate.strftime("%Y%m%d%H%M%S")

    items = []
    count = 0
    item_count = 0

    for row in data:
        currow = data[row]

        if item_count == 51:
            break

        if count < start:
            count += 1
            continue

        count += 1

        if not check_key(currow, 's') or not check_key(currow, 't') or not check_key(currow, 'c') or not check_key(currow, 'e'):
            continue

        startsplit = unicode(currow['s'].split(' ', 1)[0])
        endsplit = unicode(currow['e'].split(' ', 1)[0])

        if not startsplit.isdigit() or not len(startsplit) == 14 or startsplit < startTime or not endsplit.isdigit() or not len(endsplit) == 14 or startsplit >= endTime:
            continue

        startT = datetime.datetime.fromtimestamp(time.mktime(time.strptime(startsplit, "%Y%m%d%H%M%S")))
        startT = convert_datetime_timezone(startT, "UTC", "Europe/Amsterdam")
        endT = datetime.datetime.fromtimestamp(time.mktime(time.strptime(endsplit, "%Y%m%d%H%M%S")))
        endT = convert_datetime_timezone(endT, "UTC", "Europe/Amsterdam")

        if endT < (datetime.datetime.now(pytz.timezone("Europe/Amsterdam")) - datetime.timedelta(days=7)):
            continue

        label = startT.strftime("%H:%M") + " - " + currow['t']
        channel = ''
        description = ''
        program_image_large = ''

        if check_key(currow, 'desc'):
            description = currow['desc']

        duration = int((endT - startT).total_seconds())

        if check_key(currow, 'i'):
            program_image = currow['i']
            program_image_large = currow['i'].replace(settings.get('_img_size'), '1920x1080')

        if check_key(currow, 'c'):
            channel = currow['c']

        items.append(plugin.Item(
            label = label,
            info = {
                'plot': description,
                'duration': duration,
                'mediatype': 'video',
            },
            art = {'thumb': program_image, 'fanart': program_image_large},
            path = plugin.url_for(func_or_url=play_video, type='program', channel=channel, id=row, duration=duration, _is_live=False),
            playable = True,
        ))

        item_count += 1

    return {'items': items, 'count': count}

def process_replaytv_list_content(data, ids, start=0):
    start = int(start)
    items = []
    count = 0
    item_count = 0

    ids = json.loads(ids)
    totalrows = len(ids)

    for id in ids:
        currow = data[id]

        if item_count == 51:
            break

        if count < start:
            count += 1
            continue

        count += 1

        if not check_key(currow, 's') or not check_key(currow, 't') or not check_key(currow, 'c') or not check_key(currow, 'e'):
            continue

        startsplit = unicode(currow['s'].split(' ', 1)[0])
        endsplit = unicode(currow['e'].split(' ', 1)[0])

        if not startsplit.isdigit() or not len(startsplit) == 14 or not endsplit.isdigit() or not len(endsplit) == 14:
            continue

        startT = datetime.datetime.fromtimestamp(time.mktime(time.strptime(startsplit, "%Y%m%d%H%M%S")))
        startT = convert_datetime_timezone(startT, "UTC", "Europe/Amsterdam")
        endT = datetime.datetime.fromtimestamp(time.mktime(time.strptime(endsplit, "%Y%m%d%H%M%S")))
        endT = convert_datetime_timezone(endT, "UTC", "Europe/Amsterdam")

        if startT > datetime.datetime.now(pytz.timezone("Europe/Amsterdam")) or endT < (datetime.datetime.now(pytz.timezone("Europe/Amsterdam")) - datetime.timedelta(days=7)):
            continue

        if xbmc.getLanguage(xbmc.ISO_639_1) == 'nl':
            itemlabel = '{weekday} {day} {month} {yearhourminute} '.format(weekday=date_to_nl_dag(startT), day=startT.strftime("%d"), month=date_to_nl_maand(startT), yearhourminute=startT.strftime("%Y %H:%M"))
        else:
            itemlabel = startT.strftime("%A %d %B %Y %H:%M ").capitalize()

        itemlabel += currow['t'] + " (" + currow['cn'] + ")"
        channel = ''
        description = ''
        program_image_large = ''

        if check_key(currow, 'desc'):
            description = currow['desc']

        duration = int((endT - startT).total_seconds())

        if check_key(currow, 'i'):
            program_image = currow['i']
            program_image_large = currow['i'].replace(settings.get('_img_size'), '1920x1080')

        if check_key(currow, 'c'):
            channel = currow['c']

        items.append(plugin.Item(
            label = itemlabel,
            info = {
                'plot': description,
                'duration': duration,
                'mediatype': 'video',
            },
            art = {'thumb': program_image, 'fanart': program_image_large},
            path = plugin.url_for(func_or_url=play_video, type='program', channel=channel, id=id, duration=duration, _is_live=False),
            playable = True,
        ))

        item_count = item_count + 1

    return {'items': items, 'totalrows': totalrows, 'count': count}

def process_vod_content(data, start=0, search=None, type=None):
    subscription = load_file(file='vod_subscription.json', isJSON=True)
    start = int(start)
    items = []
    count = 0
    item_count = 0

    if sys.version_info >= (3, 0):
        subscription = list(subscription)

    for row in data:
        currow = row

        if item_count == 50:
            break

        if count < start:
            count += 1
            continue

        count += 1

        if not check_key(currow, 'id') or not check_key(currow, 'title'):
            continue

        id = currow['id']
        label = currow['title']

        if not int(id) in subscription:
            continue

        if search:
            fuzz_set = fuzz.token_set_ratio(label,search)
            fuzz_partial = fuzz.partial_ratio(label,search)
            fuzz_sort = fuzz.token_sort_ratio(label,search)

            if (fuzz_set + fuzz_partial + fuzz_sort) > 160:
                properties = {"fuzz_set": fuzz.token_set_ratio(label,search), "fuzz_sort": fuzz.token_sort_ratio(label,search), "fuzz_partial": fuzz.partial_ratio(label,search), "fuzz_total": fuzz.token_set_ratio(label,search) + fuzz.partial_ratio(label,search) + fuzz.token_sort_ratio(label,search)}
                label = label + " (" + type + ")"
            else:
                continue

        description = ''
        program_image_large = ''
        duration = 0
        properties = []

        if check_key(currow, 'desc'):
            description = currow['desc']

        if check_key(currow, 'duration'):
            duration = int(currow['duration'])

        if check_key(currow, 'image'):
            program_image = currow['image']
            program_image_large = currow['image'].replace(settings.get('_img_size'), '1920x1080')

        if not check_key(currow, 'type'):
            continue

        if currow['type'] == "show":
            path = plugin.url_for(func_or_url=vod_series, label=label, description=description, image=program_image_large, id=id)
            info = {'plot': description}
            playable = False
        else:
            path = plugin.url_for(func_or_url=play_video, type='vod', channel=None, id=id, duration=duration, _is_live=False)
            info = {'plot': description, 'duration': duration, 'mediatype': 'video'}
            playable = True

        items.append(plugin.Item(
            label = label,
            properties = properties,
            info = info,
            art = {'thumb': program_image, 'fanart': program_image_large},
            path = path,
            playable = playable,
        ))

        item_count += 1

    return {'items': items, 'count': count}

def _sort_live(element):
    return element['chno']

def _sort_replay_items(element):
    return element.get_li().getProperty('fuzz_total')