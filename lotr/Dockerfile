FROM java:8
LABEL maintainer="Paul Schifferer <paul@schifferers.net>"

RUN apt-get update && apt-get install -y wget
RUN mkdir /server && cd /server && mkdir -p bin bin/libraries data/mods data/config
COPY forge.jar minecraft_server.1.7.10.jar /server/bin/
COPY ops.json server.properties eula.txt /server/data/
COPY config/ /server/data/config/
COPY libraries/ /server/bin/libraries/
COPY mods/ /server/data/mods/

EXPOSE 25565
VOLUME [ "/server/data/world" ]
USER minecraft

WORKDIR /server/data
CMD /usr/bin/java -Dfml.queryResult=confirm -Djava.awt.headless=true -Xmx1536M -Xms512M -XX:+UseConcMarkSweepGC -XX:+CMSIncrementalPacing -XX:ParallelGCThreads=2 -XX:+AggressiveOpts -jar /server/bin/forge.jar nogui -o true
