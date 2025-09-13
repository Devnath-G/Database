export DEVICE=/dev/dri/renderD128
export DEVICE_GRP=$(ls -g $DEVICE | awk '{print $3}' | xargs getent group | awk -F: '{print $3}')

docker run -d \
   --name facility-v1 \
   --restart=always \
   --net=host \
   --device /dev/dri --group-add ${DEVICE_GRP} \
   -v /etc/timezone:/etc/timezone:ro \
   -v /etc/localtime:/etc/localtime:ro \
   -v /home/difinative/Management:/home/metro/Management \
   -e TZ=Asia/Kolkata \
   facility-image:1.0
