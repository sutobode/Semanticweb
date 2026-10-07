FROM eclipse-temurin:21-jre

ARG JENA_VERSION=4.10.0
LABEL org.opencontainers.image.version="${JENA_VERSION}"

ENV FUSEKI_HOME=/fuseki
WORKDIR ${FUSEKI_HOME}

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL -o ${FUSEKI_HOME}/fuseki-server.jar \
    "https://repo1.maven.org/maven2/org/apache/jena/jena-fuseki-server/${JENA_VERSION}/jena-fuseki-server-${JENA_VERSION}.jar" \
 && mkdir -p ${FUSEKI_HOME}/databases

COPY config.ttl ${FUSEKI_HOME}/config.ttl
COPY docker-entrypoint.sh ${FUSEKI_HOME}/docker-entrypoint.sh
RUN chmod +x ${FUSEKI_HOME}/docker-entrypoint.sh

EXPOSE 3030
ENTRYPOINT ["/fuseki/docker-entrypoint.sh"]
