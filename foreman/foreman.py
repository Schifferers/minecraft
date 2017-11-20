#!/usr/bin/env python

from slackclient import SlackClient
import os
import time
import json
import argparse
import logging
import sys
import re
import random
import docker


parser = argparse.ArgumentParser(description='Command-line arguments.')
parser.add_argument('--debug', help='output debug messages', action='store_true')
parser.add_argument('--quiet', '-q', help='be quiet', action='store_true')
parser.add_argument('--config', '-c', help='path to configuration file', default='./config.json')
parser.add_argument('--permissions', '-p', help='path to the permissions file', default='./permissions.json')
parser.add_argument('--servers', '-s', help='path to managed Minecraft servers', default='./servers.json')
args = parser.parse_args()
logging.basicConfig(level=logging.INFO)
if args.debug:
    logging.getLogger().setLevel(logging.DEBUG)
elif args.quiet:
    logging.getLogger().setLevel(logging.WARNING)


members = []
name_to_user_id_map = {}
user_id_to_name_map = {}
sc = None
dc = None
permissions = {}
servers = []
config = {}
user_cache = {}


# Exceptions
class ServerIdNotFoundException(Exception):
    def __init__(self, server_id):
        super(ServerIdNotFoundException, self).__init__(server_id)
        self.server_id = server_id

class MissingArgumentException(Exception):
    def __init__(self, arg_name):
        super(MissingArgumentException, self).__init__(arg_name)
        self.arg_name = arg_name

class ContainerCreationException(Exception):
    def __init__(self, message):
        super(ContainerCreationException, self).__init__(message)
        self.message = message


# Functions

def randhex(size=1):
    result = []
    for i in range(size):
        result.append(str(random.choice("0123456789ABCDEF")) + str(random.choice("0123456789ABCDEF")))
    return "".join(result)


def load_permissions(file):
    logging.info("Loading permissions from {}...".format(file))
    with open(file, 'r') as p:
        perms = json.load(p)
        logging.debug("Permissions loaded.")
        return perms


def load_servers(file):
    logging.info("Loading servers from {}...".format(file))
    with open(file, 'r') as s:
        srvs = json.load(s)
        logging.debug("Servers loaded.")
        return srvs


def load_config(file):
    logging.info("Loading configuration from {}...".format(file))
    if os.path.isfile(file):
        with open(file, 'r') as c:
            cfg = json.load(c)
            logging.debug("Configuration loaded: {}".format(cfg))
            return cfg
    logging.warning("No configuration file found for '{}'; returning empty default config.")
    return { 'token': "" }


def init_slack_client(token):
    logging.info("Creating Slack client.")
    client = SlackClient(token)
    logging.debug("client: {}".format(client))
    return client


def init_docker_client():
    logging.info("Creating Docker client.")
    client = docker.from_env()
    logging.debug("client: {}".format(client))
    return client


def load_members():
    logging.info("Requesting team member list...")
    members = sc.api_call("users.list")
    logging.info("Got {} members.".format(len(members)))

    name_to_user_id_map = {}
    user_id_to_name_map = {}

    for m in members:
        if 'name' in m and 'id' in m:
            name = m.get('name')
            user_id = m.get('id')
            name_to_user_id_map[name] = user_id
            user_id_to_name_map[user_id] = name

    return members, name_to_user_id_map, user_id_to_name_map


def load_im_channels():
    logging.info("Requesting IM channels...")
    c = sc.api_call("im.list")
    logging.debug("IM channels: {}".format(c))

    if 'ims' not in c:
        return []
    channels = c['ims']

    ims = []
    for im in channels:
        if 'id' in im and 'user' in im:
            t = (im['id'], im['user'])
            ims.append(t)

    return ims

def load_identity():
    logging.info("Requesting auth.test to get user identity...")
    info = sc.api_call("auth.test")
    logging.debug("info: {}".format(info))
    return info.get('user_id')


def is_mention(message_tokens):
    logging.debug("Checking if message tokens contain a mention.")
    if len(message_tokens) == 0:
        logging.debug("No message tokens provided for mention check.")
        return False
    first_token = message_tokens[0].strip()
    result = re.match("^\\<\\@(\\S+)\\>\\S*$", first_token)
    logging.debug("result: {}".format(result))
    if result is None:
        logging.debug("Regular expression match for user ID failed for token '{}'.".format(first_token))
        return False
    user_id = result.group(1)
    logging.debug("user_id: {}".format(user_id))
    return user_id == my_identity


def is_im(event):
    logging.debug("Checking if event is on an IM channel.")
    if event is None or type(event) is not dict:
        logging.debug("Event provided for IM check was empty or not a dictionary.")
        return False
    if 'channel' in event and 'user' in event and 'text' in event:
        channel_id = event['channel']
        user_id = event['user']
        text = event['text']

        # list of (channel_id, user_id) tuples
        im_channels = load_im_channels()
        logging.debug("im_channels: {}".format(im_channels))

        for c, u in im_channels:
            if channel_id == c and user_id == u:
                logging.debug("Found a matching IM channel with the user.")
                return True

    return False


def get_user(user_id):
    logging.debug("Getting user for ID {}".format(user_id))
    user = user_cache.get(user_id)
    logging.debug("user: {}".format(user))
    if user is not None:
        logging.debug("Returning cached user: {}".format(user))
        return user

    logging.info("Requesting user info for ID {}...".format(user_id))
    info = sc.api_call("users.info", user=user_id)
    logging.debug("info: {}".format(info))
    if 'user' in info:
        user = info['user']
        user_cache[user_id] = user
        return user

    return None


def get_server_status(server_id):
    logging.debug("Getting server status for ID '{}'".format(server_id))

    try:
        container = dc.containers.get(server_id)
        status = container.status
        return status.capitalize()
    except docker.errors.NotFound:
        return "Offline"
    except docker.errors.APIError:
        return "Error"

    return "WTF"


def handle_list_command():
    logging.debug("Handle list command.")

    # format the list of servers for display
    attachments = []
    for s in servers:
        attachment = server_status_attachment(container=None, server=s)
        attachments.append(attachment)

    return attachments


def container_for_server(server):
    return None


def server_status_attachment(container=None, server=None):
    status = "Offline"
    image = "None"

    if container:
        status = container.status.capitalize()
        image = container.image

    attachment = {
        'fallback': "{:>10}: {}\n  {}".format(server['id'], server['name'], server['info']),
        'color': "#{}".format(randhex(3)),
        # 'image_url': "minecraft.png",
        'title': server['name'],
        'text': server.get('info'),
        'fields': [
            {
                'title': "ID",
                'value': server['id'],
                'short': True
            },
            {
                'title': "Status",
                'value': status,
                'short': True
            },
            {
                'title': "Image",
                'value': image,
                'short': True
            },
        ]
    }
    return attachment

def handle_status_command(server_id):
    logging.debug("Handle status command.")

    attachments = []

    # server_id not found
    # server_id status
    # default server status
    if server_id is None:
        # figure out which server is running and display its status
        containers = dc.containers.list(all=True)

        for s in servers:
            server_image = s['image']

            found = False
            for c in containers:
                logging.debug("c: {}".format(c))
                container_image = c.attrs['Config']['Image']
                logging.debug("image: {}".format(container_image))

                if server_image == container_image:
                    attachment = server_status_attachment(container=c, server=s)
                    attachments.append(attachment)
                    found = True
                    break
            if not found:
                attachment = server_status_attachment(container=None, server=s)
                attachments.append(attachment)
    else:
        for s in servers:
            if s['id'] == server_id:
                c = container_for_server(s)
                a = server_status_attachment(container=c, server=s)
                attachments.append(a)
        if len(attachments) == 0:
            raise ServerIdNotFoundException(server_id)

    return attachments


def handle_start_command(server_id):
    logging.debug("Handle start command for server ID {}.".format(server_id))

    if server_id is None:
        raise MissingArgumentException('server_id')

    server = None
    for s in servers:
        if 'id' in s and s['id'] == server_id:
            server = s
            break
    if server is None:
        raise ServerIdNotFoundException(server_id)

    attachments = []

    try:
        container = dc.containers.run(image)
    except docker.errors.NotFound:
        pass
    except docker.errors.APIError:
        pass

    return attachments


def handle_stop_command(server_id):
    logging.debug("Handle stop command.")

    attachments = []

    return attachments


def send_message(channel_id, sender_id, response, attachments, message_is_im=False):
    logging.debug("Sending message to channel {}...".format(channel_id))
    api = "chat.postMessage"
    if not message_is_im:
        response = "<@{}> {}".format(sender_id, response)
        # api = "chat.postEphemeral"
    sc.api_call(api, channel=channel_id, as_user=True, text=response, attachments=attachments)


def handle_help():
    attachments = [
        {
            'fallback': "list",
            'color': "#ff0ff0",
            'title': "List",
            'text': "`list`\nList the servers that can be managed, and their current status",
            "mrkdwn_in": ["text"]
        }
        ,
        {
            'fallback': "status [<server-id>]",
            'color': "#0000ff",
            'title': "Status",
            'text': "`status [<server-id>]`\nGet the status of all servers, or for a particular server",
            "mrkdwn_in": ["text"]
        }
        ,
        {
            'fallback': "start <server-id>",
            'color': "#00ff00",
            'title': "Start",
            'text': "`start <server-id>`\nStart a particular server",
            "mrkdwn_in": ["text"]
        }
        ,
        {
            'fallback': "stop <server-id>",
            'color': "#ff0000",
            'title': "Stop",
            'text': "`stop <server-id>`\nStop a particular server",
            "mrkdwn_in": ["text"]
        }
    ]
    return attachments


def process_event(event):
    logging.debug("event: {}, {}".format(type(event), json.dumps(event, sort_keys=True, indent=4)))

    if type(event) is not dict:
        logging.debug("Event wasn't a dictionary, so skipping it.")
        return

    event_type = event.get('type')
    if event_type is None:
        logging.debug("Event type not found in dictionary, skipping it.")
        return

    if event_type == 'message':
        channel_id = event.get('channel')
        if channel_id is None:
            logging.debug("Message event does not have a channel ID, skipping it.")
            return
        event_text = event.get('text')
        if event_text is None:
            logging.debug("Event text not found in dictionary, skipping it.")
            return
        sender_id = event.get('user')
        if sender_id is None:
            logging.debug("User ID not found in dictionary, skipping it.")
            return
        if sender_id == my_identity:
            logging.debug("Sender of message was us; skipping it.")
            return
        user = get_user(sender_id)
        if user is None:
            logging.warning("User not found for sender ID {}.".format(sender_id))
            return

        user_name = user['name']

        # tokenize the text
        tokens = event_text.split()
        logging.debug("tokens: {}, {}".format(type(tokens), tokens))
        if len(tokens) == 0:
            logging.debug("No tokens in text; skipping.")
            return

        # is the message direct, or a mention in a channel?
        message_is_im = False
        if is_mention(tokens):
            logging.debug("Message is a mention of us ({}).".format(my_identity))
        elif is_im(event):
            message_is_im = True
            logging.debug("Message is an IM to us ({}).".format(my_identity))
        else:
            logging.debug("Message was neither a mention or an IM, skipping.")
            return

        # remove mentions from message text
        words = filter(lambda x: not x.startswith('<@'), tokens)
        logging.debug("words: {}, {}".format(type(words), words))
        count = len(words)
        if count == 0:
            logging.info("Nothing found in command sequence, skipping it.")
            return

        logging.debug("Do command check.")
        command = words[0].lower()
        logging.debug("COMMAND: {}".format(command))
        if command not in permissions:
            logging.warning("Command found in text '{}' is not in the permissions list.".format(command))
            if message_is_im:
                response = "Unknown command '{}'".format(command)
            else:
                response = "<@{}>: Unknown command '{}'".format(sender_id, command)
            sc.rtm_send_message(channel=channel_id, message=response)
            return

        logging.debug("Perform permissions check.")
        perm_list = permissions[command]
        has_permission = False
        if perm_list is None:
            logging.info("Permissions check succeeded because no permissions required for command {}".format(command))
            has_permission = True
        elif type(perm_list) is list:
            logging.debug("Permission list for command has users: {}".format(perm_list))
            for username in perm_list:
                logging.debug("username: {}".format(username))
                user_id = name_to_user_id_map.get(username)
                logging.debug("user_id: {}".format(user_id))
                if user_id is None:
                    logging.warning("Username not found in permission list for command '{}': {}".format(command, username))
                    return
                if sender_id == user_id:
                    has_permission = True
                    break
        else:
            logging.warning("Value for permission key '{}' was not a list, abort.".format(command))
            response = "<@{}>: Sorry, I didn't understand the command: {}".format(sender_id, words.join(" "))
            sc.rtm_send_message(channel=channel_id, message=response)
            return
        if not has_permission:
            logging.warning("User {} does not have permission to execute command {}.".format(user_name, command))
            response = "<@{}>: You can't execute that command.".format(sender_id)
            sc.rtm_send_message(channel=channel_id, message=response)
            return

        logging.debug("Handle command: {}, {}".format(command, words))
        try:
            if command == 'list':
                logging.debug("COMMAND: list; {}".format(words))
                attachments = handle_list_command()
                send_message(channel_id, sender_id, "Here's the server list:", attachments, message_is_im=message_is_im)
            elif command == 'status':
                logging.debug("COMMAND: status; {}".format(words))
                param1 = None
                message = "Current server status:"
                if len(words) > 1:
                    server_id = words[1]
                    message = "Server status for {}:".format(server_id)
                attachments = handle_status_command(server_id)
                if len(attachments) == 0:
                    if len(servers) > 0:
                        response = "Could not get server status, even though I manage {} server(s).".format(len(servers))
                        send_message(channel_id, sender_id, response, None, message_is_im=message_is_im)
                        return
                if len(attachments) != len(servers):
                    response = "Could not get status for all servers. Here are the ones I did get:"
                send_message(channel_id, sender_id, message, attachments, message_is_im=message_is_im)
            elif command == 'start':
                logging.debug("COMMAND: start; {}".format(words))
                if len(words) > 1:
                    server_id = words[1]
                    attachments = handle_start_command(server_id=server_id)
                    message = "Server '{}' started:".format(server_id)
                    send_message(channel_id, sender_id, message, attachments, message_is_im=message_is_im)
                else:
                    response = "<@{}>: Usage: `start <server-id>`".format(sender_id)
                    sc.rtm_send_message(channel=channel_id, message=response)
            elif command == 'stop':
                logging.debug("COMMAND: stop; {}".format(words))
                if len(words) > 1:
                    attachments = handle_stop_command(server_id=words[1])
                else:
                    response = "<@{}>: Usage: `stop <server-id>`".format(sender_id)
                    sc.rtm_send_message(channel=channel_id, message=response)
            elif command == 'help':
                logging.debug("COMMAND: help; {}".format(words))
                attachments = handle_help()
                response = "Here are the commands I understand:"
                send_message(channel_id, sender_id, response, attachments, message_is_im=message_is_im)
            else:
                logging.debug("COMMAND UNKNOWN")
                response = "Unknown command '{}'. Here are the commands I understand:".format(command)
                attachments = handle_help()
                send_message(channel_id, sender_id, response, attachments, message_is_im=message_is_im)
        except ServerIdNotFoundException as sinf:
            response = "Server '{}' not found.".format(sinf.server_id)
            send_message(channel_id, sender_id, response, None, message_is_im=message_is_im)
            return
        except MissingArgumentException as ma:
            response = "Missing value for argument '{}'.".format(sinf.arg_name)
            send_message(channel_id, sender_id, response, None, message_is_im=message_is_im)
            return
        except:
            logging.exception("Unknown exception raised.")
            return


def main():
    if sc.rtm_connect():
        while True:
            events = sc.rtm_read()
            if len(events) == 0:
                time.sleep(1)
                continue

            logging.debug("events: {}, {}".format(type(events), events))

            for event in events:
                process_event(event)

            time.sleep(1)
    else:
        logging.error("Connection failed.")


if __name__ == "__main__":
    logging.info("Starting Foreman Slack bot.")
    config = load_config(args.config)
    permissions = load_permissions(args.permissions)
    servers = load_servers(args.servers)

    if 'token' in config:
        slack_token = config['token']
    env_slack_token = os.environ.get("SLACK_API_TOKEN")
    if env_slack_token:
        logging.info("Overriding Slack token from configuration with environment SLACK_API_TOKEN.")
        slack_token = env_slack_token
    sc = init_slack_client(slack_token)
    dc = init_docker_client()

    members, name_to_user_id_map, user_id_to_name_map = load_members()
    my_identity = load_identity()
    logging.info("My identity: {}".format(my_identity))

    main()
