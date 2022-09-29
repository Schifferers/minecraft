FROM openjdk:17-slim-bullseye
LABEL maintainer="Paul Schifferer <paul@schifferers.net>"

RUN apt-get update && apt-get install -y wget jq curl
COPY scripts/fetch-server.sh /bin
RUN mkdir -p /server /data /config && cd /server && /bin/fetch-server.sh -t release
ADD entrypoint.sh /
# COPY eula.txt /data
# COPY vanilla/build/user_jvm_args.txt /server

EXPOSE 25565
VOLUME [ "/data" ]

ENTRYPOINT [ "/entrypoint.sh" ]
WORKDIR /data

# CMD java @/config/user_jvm_args.txt "$@"
