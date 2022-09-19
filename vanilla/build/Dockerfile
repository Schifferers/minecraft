FROM openjdk:17-slim-bullseye
LABEL maintainer="Paul Schifferer <paul@schifferers.net>"

RUN apt-get update && apt-get install -y wget jq curl
COPY scripts/fetch-server.sh /bin
RUN mkdir /server && cd /server && /bin/fetch-server.sh -t release
COPY eula.txt /data

EXPOSE 25565
VOLUME [ "/data", "/config" ]

WORKDIR /data
CMD java @/config/user_jvm_args.txt "$@"
