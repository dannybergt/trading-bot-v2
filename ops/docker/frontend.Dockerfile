FROM nginx:1.29-alpine

COPY ops/docker/frontend.nginx.conf /etc/nginx/conf.d/default.conf
COPY src/frontend-dist/ /usr/share/nginx/html/
