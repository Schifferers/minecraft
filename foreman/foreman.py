#!/usr/bin/env python

from slackclient import SlackClient
import os
import time
import json
import argparse
import logging
import sys


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


def load_permissions(file):
    logging.info("Loading permissions from {}...".format(file))
    with open(file, 'r') as p:
        permissions = json.load(p)
        logging.debug("Permissions loaded.")
        return permissions


def load_servers(file):
    logging.info("Loading servers from {}...".format(file))
    with open(file, 'r') as s:
        servers = json.load(s)
        logging.debug("Servers loaded.")
        return servers


def load_config(file):
    logging.info("Loading configuration from {}...".format(file))
    with open(file, 'r') as c:
        config = json.load(c)
        logging.debug("Configuration loaded: {}".format(config))
        return config


def init_slack_client(token):
    logging.info("Creating Slack client.")
    sc = SlackClient(token)
    return sc


def load_members():
    logging.info("Requesting team member list...")
    members = sc.api_call("users.list")
    logging.debug("Got {} members.".format(len(members)))
    return members


def determine_identity(username):
    logging.info("Figuring out our user identity...")
    for m in members:
        if 'name' in m and 'id' in m:
            member_id = m['id']
            member_name = m['name']
            if member_name == username:
                return member_id
    return None


def get_user_id(username):
    for m in members:
        if 'name' in m and 'id' in m:
            name = m.get('name')
            user_id = m.get('id')
            if username == name:
                return user_id
    return None


def main():
    if sc.rtm_connect():
        while True:
            events = sc.rtm_read()
            logging.debug("events: {}, {}".format(type(events), events))

            for event in events:
                logging.debug("event: {}, {}".format(type(event), event))

                if type(event) is not dict:
                    logging.debug("Event wasn't a dictionary, so skipping it.")
                    continue

                event_type = event.get('type')
                if event_type is None:
                    logging.debug("Event type not found in dictionary, skipping it.")
                    continue

                if event_type == 'message':
                    channel_id = event.get('channel')
                    if channel_id is None:
                        logging.debug("Message event does not have a channel ID, skipping it.")
                        continue
                    event_text = event.get('text')
                    if event_text is None:
                        logging.debug("Event text not found in dictionary, skipping it.")
                        continue
                    sender_id = event.get('user')
                    if sender_id is None:
                        logging.debug("User ID not found in dictionary, skipping it.")
                        continue

                    # tokenize the text
                    tokens = event_text.split()
                    logging.debug("tokens: {}, {}".format(type(tokens), tokens))

                    # check if the text mentions us

                    # remove mentions from message text
                    words = filter(lambda x: not x.startswith('<@'), tokens)
                    logging.debug("words: {}, {}".format(type(words), words))
                    count = len(words)
                    if count == 0:
                        logging.info("Nothing found in command sequence, skipping it.")
                        continue

                    command = words[0]
                    if command not in permissions:
                        logging.warning("Command found in text '{}' is not in the permissions list.".format(command))
                        response = "Unable to process command '{}'; no permissions set. Please contact the bot administrator.".format(command)
                        sc.rtm_send_message(channel=channel_id, message=response)
                        continue

                    perm_list = permissions[command]
                    has_permission = False
                    if perm_list is None:
                        logging.info("Permissions check succeeded because no permissions required for command {}".format(command))
                        has_permission = True
                    elif type(perm_list) is list:
                        for username in perm_list:
                            user_id = get_user_id(username)
                            if user_id is None:
                                continue
                            if sender_id == user_id:
                                has_permission = True
                                break
                    else:
                        logging.warning("Value for permission key '{}' was not a list, abort.".format(command))
                        continue
                    if not has_permission:
                        logging.warning("User {} does not have permission to execute command {}.".format(sender_id, command))
                        response = "You can't execute that command."
                        sc.rtm_send_message(channel=channel_id, message=response)
                        continue

                    if command == 'list':
                        # format the list of servers for display
                        response = str(server)
                        sc.rtm_send_message(channel=channel_id, message=response)

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
    env_slack_token = os.environ["SLACK_API_TOKEN"]
    if env_slack_token:
        logging.info("Overriding Slack token from configuration with environment SLACK_API_TOKEN.")
        slack_token = env_slack_token
    sc = init_slack_client(slack_token)

    members = load_members()

    if 'username' not in config:
        logging.error("Bot username not found in configuration.")
        sys.exit(1)
    my_identity = determine_identity(config['username'])
    logging.info("My identity: {}".format(my_identity))

    main()
