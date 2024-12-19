#!/usr/bin/env bash

if [[ $# -ne 1 ]]; then
  echo './enter_container.sh <mount_dir>'
  exit 1
fi

docker_username="dev"
username=$(whoami)
workdir="$1"

docker run -it --rm -e HOST_UID=$(id -u) \
                    --mac-address 8c:8c:aa:e3:74:08 \
                    -v $workdir:/home/"$docker_username"/shared `# Empty shared directory between host and container` \
                    -e XDG_RUNTIME_DIR=/run/user/$(id -u) `# Login session passthrough` \
                    -e WAYLAND_DISPLAY=$WAYLAND_DISPLAY `# Wayland passthrough` \
                    -v $XDG_RUNTIME_DIR/$WAYLAND_DISPLAY:$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY `# Wayland passthrough` \
                    -e DISPLAY=$DISPLAY `# X11 passthrough` \
                    -v /tmp/.X11-unix:/tmp/.X11-unix:rw `# X11 passthrough` \
                    --ipc=host `# X11 passthrough (MIT-SHM)` \
                    -v /dev:/dev `# Device passthrough` \
                    radiant-container /bin/bash