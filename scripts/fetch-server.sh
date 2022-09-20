#!/bin/bash

set -x
set -e

usage() {
    echo "$0 [-x] [-v <version>] [-t release|snapshot] [-H] [-s <seed>]"
    echo "         -x                   show debug output"
    echo "         -v <version>         specify a version to download, defaults to latest for the type"
    echo "         -t release|snapshot  type of server, defaults to 'release'"
    echo "         -s <seed>            generate ('g') or use a seed value"
    echo "         -H                   add a 'Hardcore' tag to the motd"
}

while getopts "h?xv:t:Hs:" opt; do
    case "$opt" in
    h | \?)
        usage
        exit 0
        ;;
    x)
        set -x
        ;;
    v)
        version=$OPTARG
        ;;
    t)
        typearg=$OPTARG
        ;;
    s)
        seed=$OPTARG
        ;;
    H)
        hardcore="1"
        ;;
    esac
done
shift "$(($OPTIND - 1))"

type=${typearg:-release}

game_manifest=/tmp/minecraft-game-manifest-$$.json
version_manifest=/tmp/minecraft-version-manifest-$$.json

echo "Fetching game manifest..."
curl -s -o ${game_manifest} -L https://launchermeta.mojang.com/mc/game/version_manifest.json

if [ -z "$version" ]; then
    version=$(jq -j ".latest.${type}" ${game_manifest})
    echo "Latest version for '${type}' is: ${version}"
else
    echo "Using specified version: ${version}"
fi

if [ "${seed}" = "g" ]; then
    echo "Generating seed value..."
    seed=$(cat /dev/urandom | env LC_ALL=C tr -dc '0-9' | fold -w 15 | head -n 1)
fi

version_manifest_url=$(jq -j ".versions[] | select(.id==\"${version}\") | .url" ${game_manifest})

if [ -z "${version_manifest_url}" ]; then
    echo "Version ${version} could not be found."
    exit 1
fi
echo "Fetching game version manifest..."
curl -s -o ${version_manifest} -L ${version_manifest_url}

server_file_url=$(jq -j '.downloads.server.url' ${version_manifest})
echo "Fetching server jar..."
curl -s -o minecraft_server.jar -L ${server_file_url}
echo "Server fetched."

if [ -w server.properties ]; then
    echo "Updating server.properties..."
    t=$(echo ${type} | sed -e 's/\b\(.\)/\u\1/g')
    date=$(date '+%a, %d %b %Y')

    if [ ! -z "${hardcore}" ]; then
        tags="${tags} (Hardcore)"
        echo "Setting hardcore mode in server.properties."
        sed -i -e "s/^hardcore=.*\$/hardcore=true/g" server.properties
    fi

    if [ ! -z "${seed}" ]; then
        echo "Setting seed value to ${seed}..."
        sed -i -e "s/^level-seed=.*\$/level-seed=${seed}/g" server.properties
    fi

    motd="${t} ${version} -- ${date}${tags}"
    sed -i -e "s/^motd=.*\$/motd=${motd}/g" server.properties
    echo "Updated MOTD in server.properties."
fi
