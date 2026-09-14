FROM stain/jena-fuseki:4.8.0

RUN cp /docker-entrypoint.sh /tmp/fuseki-base-entrypoint.sh
COPY config.ttl /fuseki/config.ttl
COPY shiro.ini /opt/vietheritage-shiro.ini
COPY docker-entrypoint.sh /docker-entrypoint.sh
