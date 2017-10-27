FROM java:8
LABEL maintainer="Paul Schifferer <paul@schifferers.net>"

RUN apt-get update && apt-get install -y wget 
RUN mkdir /server && cd /server && wget -O /server/minecraft-server.jar https://s3.amazonaws.com/Minecraft.Download/versions/1.12.2/minecraft_server.1.12.2.jar
COPY server.properties eula.txt /server/

EXPOSE 25565
VOLUME [ "/server/world" ]

WORKDIR /server
CMD java -Xmx1024M -Xms1024M -jar /server/minecraft-server.jar nogui
