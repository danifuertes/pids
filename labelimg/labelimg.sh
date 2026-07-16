#!/usr/bin/env bash
set -e

# Allow local Docker containers to access the X server
xhost +local:docker >/dev/null

docker run --rm -it \
    --name labelimg \
    -e DISPLAY=$DISPLAY \
    -e QT_X11_NO_MITSHM=1 \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v "$(pwd)":/workspace \
    danielfuertes/labelimg:latest

# (Optional) revoke permission afterwards
xhost -local:docker >/dev/null
