# TODO: quando sarà disponibile un dominio, sostituire questo stage con
#       Certbot/ACME e montare i certificati Let's Encrypt invece di
#       generare un certificato self-signed.
FROM nginx:alpine AS certs
RUN apk add --no-cache openssl && \
    mkdir -p /etc/nginx/certs && \
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout /etc/nginx/certs/selfsigned.key \
        -out /etc/nginx/certs/selfsigned.crt \
        -subj '/CN=horilla/O=Horilla/C=IT'

FROM nginx:alpine
COPY --from=certs /etc/nginx/certs /etc/nginx/certs
